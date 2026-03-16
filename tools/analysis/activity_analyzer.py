"""Activity analyzer tool for Process Design Documents.

Counts the number of distinct activities in the process to be automated.
Uses LLM-powered semantic analysis with few-shot prompting.

All prompts defined in tools/analysis/prompts.py.
All LLM access via llm.manager.LLMManager abstraction.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from config.logging_config import get_logger
from core.exceptions import LLMProviderError
from core.models.document import ExtractedSection
from llm.manager import LLMManager
from tools.analysis.prompts import (
    ACTIVITY_ANALYSIS_PROMPT,
    ACTIVITY_ANALYSIS_RETRY_PROMPT,
    ACTIVITY_ANALYSIS_SYSTEM,
)

logger = get_logger("activity_analyzer")

# Module-level constant for XL tier ceiling
XL_ACTIVITY_CEILING = 60


# ==================== INTERNAL SCHEMAS ====================


class ActivityAnalysisResult(BaseModel):
    """Result of activity analysis from LLM."""

    raw_activity_count: int = Field(
        ..., description="Number of distinct activities identified"
    )
    activity_list: list[str] = Field(..., description="List of activity descriptions")
    count_confidence: float = Field(
        ..., description="Confidence score 0.0-1.0 of the count"
    )
    counting_rationale: str = Field(
        ..., description="Explanation of how activities were counted"
    )
    ambiguous_items: list[str] = Field(
        default_factory=list, description="Items that were unclear to classify"
    )

    @field_validator("raw_activity_count")
    @classmethod
    def validate_activity_count(cls, v: int) -> int:
        """Ensure raw_activity_count is >= 0.

        Args:
            v: Activity count value

        Returns:
            The validated activity count

        Raises:
            ValueError: If count is negative
        """
        if v < 0:
            raise ValueError("raw_activity_count must be >= 0")
        return v

    @field_validator("count_confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """Clamp count_confidence to 0.0-1.0 range.

        Args:
            v: Confidence value

        Returns:
            Clamped confidence value
        """
        return max(0.0, min(1.0, v))

    @field_validator("activity_list")
    @classmethod
    def sync_list_with_count(cls, v: list[str], info) -> list[str]:
        """Sync activity_list length with raw_activity_count.

        If count != len(list), truncate or pad list to match.
        Does not raise — adjusts silently.

        Args:
            v: The activity list
            info: Validation context with other field values

        Returns:
            Adjusted activity list
        """
        # Get the raw_activity_count from data if available
        if hasattr(info, "data") and "raw_activity_count" in info.data:
            count = info.data["raw_activity_count"]
            if count != len(v):
                if len(v) > count:
                    # Truncate to match count
                    return v[:count]
                else:
                    # Pad with placeholder items
                    return v + [f"Activity {i+1}" for i in range(len(v), count)]
        return v


# ==================== HELPER FUNCTIONS ====================


def _filter_relevant_sections(
    sections: list[ExtractedSection],
) -> list[ExtractedSection]:
    """Filter sections most relevant for activity counting.

    Priority order:
    1. section_type == "process_steps"  (highest priority)
    2. section_type == "process_overview"
    3. If no priority 1 or 2 found: return ALL sections

    Exclude: "business_rules", "applications", "exceptions"
    (only when process_steps IS present)

    Args:
        sections: List of ExtractedSection objects

    Returns:
        Filtered list of relevant sections
    """
    if not sections:
        return []

    # Priority 1: process_steps
    priority_1 = [s for s in sections if s.section_type == "process_steps"]
    if priority_1:
        return priority_1

    # Priority 2: process_overview
    priority_2 = [s for s in sections if s.section_type == "process_overview"]
    if priority_2:
        return priority_2

    # Fallback: return ALL sections if no priority 1 or 2 found
    # (better to over-include than miss steps)
    return sections


def _prepare_sections_text(
    sections: list[ExtractedSection], max_chars: int = 5000
) -> str:
    """Format sections for LLM prompt.

    For each section:
      Format as:
      "## {section.title} ({section.section_type})\n{section.content}\n"

    Join all formatted sections.
    If total length > max_chars: truncate to max_chars and
      append "\n[Document truncated for processing]"

    Args:
        sections: List of ExtractedSection objects
        max_chars: Maximum characters to include

    Returns:
        Formatted sections text
    """
    if not sections:
        return ""

    formatted_parts = []

    for section in sections:
        formatted = f"## {section.title} ({section.section_type})\n{section.content}\n"
        formatted_parts.append(formatted)

    full_text = "".join(formatted_parts)

    if len(full_text) > max_chars:
        full_text = full_text[:max_chars]
        full_text += "\n[Document truncated for processing]"

    return full_text


# ==================== PUBLIC API ====================


def analyze_activities(
    sections: list[ExtractedSection],
    llm_manager: LLMManager | None = None,
    session_id: str = "",
) -> ActivityAnalysisResult:
    """Analyze activities in a process from document sections using LLM.

    Uses LLM as primary strategy with retry on failure.
    Returns default result on complete failure (does not raise).

    Args:
        sections: List of ExtractedSection objects from section_identifier
        llm_manager: Optional LLMManager. If None, creates default instance.
        session_id: Optional session ID for logging

    Returns:
        ActivityAnalysisResult with raw activity count and details.
        Returns default result with count=0 if sections is empty or
        LLM extraction fails.
    """
    # STEP 1: Filter relevant sections
    relevant = _filter_relevant_sections(sections)
    logger.debug(f"Analysing activities from {len(relevant)} sections")

    # STEP 2: Prepare sections text
    sections_text = _prepare_sections_text(relevant)

    # STEP 3: Get LLM manager
    if llm_manager is None:
        llm_manager = LLMManager.create_default()

    # STEP 4: First LLM attempt
    result: ActivityAnalysisResult | None = None
    try:
        prompt = ACTIVITY_ANALYSIS_PROMPT.format(sections_text=sections_text)
        response = llm_manager.complete_structured(
            prompt=prompt,
            response_schema=ActivityAnalysisResult,
            system=ACTIVITY_ANALYSIS_SYSTEM,
            max_tokens=1500,
            session_id=session_id or "activity_analyzer",
        )
        result = response if isinstance(response, ActivityAnalysisResult) else None
    except LLMProviderError as e:
        logger.warning(f"Activity analysis failed on first attempt, retrying: {e}")
        # Go to Step 5 (retry)
        pass

    # STEP 5: Retry with simplified prompt if first attempt failed
    if result is None:
        try:
            truncated = sections_text[:1500]
            retry_prompt = ACTIVITY_ANALYSIS_RETRY_PROMPT.format(
                sections_text_truncated=truncated
            )
            response = llm_manager.complete_structured(
                prompt=retry_prompt,
                response_schema=ActivityAnalysisResult,
                system=ACTIVITY_ANALYSIS_SYSTEM,
                max_tokens=1000,
                session_id=(session_id or "activity_analyzer") + "_retry",
            )
            result = response if isinstance(response, ActivityAnalysisResult) else None
        except LLMProviderError as e:
            logger.error(f"Activity analysis failed after retry: {e}")
            return ActivityAnalysisResult(
                raw_activity_count=0,
                activity_list=[],
                count_confidence=0.0,
                counting_rationale="Analysis failed — manual review required",
            )

        if result is None:
            return ActivityAnalysisResult(
                raw_activity_count=0,
                activity_list=[],
                count_confidence=0.0,
                counting_rationale="Analysis failed — manual review required",
            )

    # STEP 6: Post-process result
    # Cap raw_activity_count at 60 (XL ceiling)
    if result.raw_activity_count > XL_ACTIVITY_CEILING:
        result.counting_rationale += (
            f" [Capped at {XL_ACTIVITY_CEILING} from {result.raw_activity_count}]"
        )
        result.raw_activity_count = XL_ACTIVITY_CEILING
        result.activity_list = result.activity_list[:XL_ACTIVITY_CEILING]

    # STEP 7: Log and return
    logger.info(
        f"[{session_id or 'activity_analyzer'}] Activity count: "
        f"{result.raw_activity_count}, confidence: {result.count_confidence:.2f}"
    )
    return result


def get_activity_tier_hint(result: ActivityAnalysisResult) -> str:
    """Get human-readable tier hint from activity count.

    Returns a string hint about which tier the count suggests.
    Does NOT call the scoring engine.
    For logging and debugging only.

    Args:
        result: ActivityAnalysisResult from analyze_activities()

    Returns:
        Human-readable tier hint string
    """
    count = result.raw_activity_count

    if count <= 10:
        return "Likely XS or S (< 10 activities)"
    elif count <= 20:
        return "Likely M (11-20 activities)"
    elif count <= 40:
        return "Likely L (21-40 activities)"
    elif count <= XL_ACTIVITY_CEILING:
        return "Likely XL (41-60 activities)"
    else:
        return "Exceeds XL ceiling — Tech Lead review needed"
