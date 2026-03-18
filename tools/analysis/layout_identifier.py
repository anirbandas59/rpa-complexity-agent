"""Layout identifier tool for Process Design Documents.

Identifies distinct digital layouts/templates that the RPA bot reads from
or writes to. Enforces template-level deduplication per Excel definition.

All prompts defined in tools/analysis/prompts.py.
All LLM access via llm.manager.LLMManager abstraction.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from config.logging_config import get_logger
from core.exceptions import LLMProviderError
from core.models.document import ExtractedSection
from llm.manager import LLMManager
from tools.analysis.prompts import (
    LAYOUT_IDENTIFICATION_PROMPT,
    LAYOUT_IDENTIFICATION_RETRY_PROMPT,
    LAYOUT_IDENTIFICATION_SYSTEM,
)

logger = get_logger("layout_identifier")

# XL ceiling for layouts
XL_LAYOUT_CEILING = 10


# ==================== INTERNAL SCHEMAS ====================


class IdentifiedLayout(BaseModel):
    """Represents a digital layout/template identified in the process."""

    name: str = Field(..., description="Name of the layout/template")
    file_extension: str = Field(
        default="other",
        description="File extension: xlsx|pdf|csv|xml|docx|txt|json|other",
    )
    is_input: bool = Field(default=True, description="Whether bot reads this template")
    is_output: bool = Field(
        default=False, description="Whether bot writes this template"
    )
    template_type: str = Field(
        default="other",
        description="Type: input_template|output_report|schema_file|config_file|email_template|other",
    )
    evidence: str = Field(default="", description="Evidence from the document")
    confidence: float = Field(
        default=0.5, description="Confidence 0.0-1.0 in this identification"
    )

    @model_validator(mode="after")
    def ensure_at_least_one_flag(self) -> "IdentifiedLayout":
        """Ensure at least one of is_input or is_output is True.

        If both are False: set is_input=True silently.

        Returns:
            Self with validated flags
        """
        if not self.is_input and not self.is_output:
            self.is_input = True
        return self

    @field_validator("file_extension")
    @classmethod
    def validate_file_extension(cls, v: str) -> str:
        """Validate file_extension is one of allowed values.

        If invalid, defaults to "other" without raising.

        Args:
            v: File extension value

        Returns:
            Valid extension (or "other" default)
        """
        valid_extensions = {"xlsx", "pdf", "csv", "xml", "docx", "txt", "json", "other"}
        if v.lower() in valid_extensions:
            return v.lower()
        return "other"

    @field_validator("template_type")
    @classmethod
    def validate_template_type(cls, v: str) -> str:
        """Validate template_type is one of allowed values.

        If invalid, defaults to "other" without raising.

        Args:
            v: Template type value

        Returns:
            Valid template type (or "other" default)
        """
        valid_types = {
            "input_template",
            "output_report",
            "schema_file",
            "config_file",
            "email_template",
            "other",
        }
        if v.lower() in valid_types:
            return v.lower()
        return "other"

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """Clamp confidence to 0.0-1.0 range.

        Args:
            v: Confidence value

        Returns:
            Clamped confidence value
        """
        return max(0.0, min(1.0, v))


class LayoutIdentificationLLMResponse(BaseModel):
    """Response schema for layout identification from LLM."""

    layouts: list[IdentifiedLayout] = Field(
        default_factory=list, description="List of identified layouts"
    )
    total_count: int = Field(default=0, description="Total count of layouts")
    detection_confidence: float = Field(
        default=0.5, description="Overall detection confidence"
    )
    exceeds_ceiling: bool = Field(
        default=False, description="Whether layout count exceeds 10"
    )
    notes: str = Field(default="", description="Additional observations")

    @field_validator("total_count")
    @classmethod
    def sync_count(cls, v: int, info) -> int:
        """Sync total_count with len(layouts).

        Args:
            v: Total count value
            info: Validation context

        Returns:
            Synced count
        """
        if hasattr(info, "data") and "layouts" in info.data:
            return len(info.data["layouts"])
        return v


class LayoutIdentificationResult(BaseModel):
    """Final result of layout identification."""

    layouts: list[IdentifiedLayout] = Field(
        ..., description="List of identified layouts"
    )
    total_count: int = Field(..., description="Total number of layouts")
    detection_confidence: float = Field(..., description="Overall detection confidence")
    exceeds_ceiling: bool = Field(..., description="Whether layout count exceeds 10")
    notes: str = Field(default="", description="Additional notes")

    def layout_names(self) -> list[str]:
        """Get list of layout names.

        Returns:
            List of layout names
        """
        return [layout.name for layout in self.layouts]

    def input_count(self) -> int:
        """Get count of input layouts.

        Returns:
            Number of layouts where is_input=True
        """
        return sum(1 for layout in self.layouts if layout.is_input)

    def output_count(self) -> int:
        """Get count of output layouts.

        Returns:
            Number of layouts where is_output=True
        """
        return sum(1 for layout in self.layouts if layout.is_output)


# ==================== HELPER FUNCTIONS ====================


def _normalize_layout_name(name: str) -> str:
    """Normalize layout name for deduplication.

    - Lowercase
    - Strip whitespace
    - Remove common suffixes: .xlsx, .pdf, .csv, .xml
    - Replace underscores and hyphens with spaces
    - Collapse multiple spaces to single space

    Args:
        name: Layout name to normalize

    Returns:
        Normalized name
    """
    normalized = name.lower().strip()
    # Remove common file extensions
    for ext in [".xlsx", ".pdf", ".csv", ".xml", ".docx", ".txt", ".json"]:
        if normalized.endswith(ext):
            normalized = normalized[: -len(ext)]
    # Replace underscores and hyphens with spaces
    normalized = re.sub(r"[_\-]+", " ", normalized)
    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _deduplicate_layouts(
    layouts: list[IdentifiedLayout],
) -> list[IdentifiedLayout]:
    """Remove duplicate layouts from list.

    Two layouts are duplicates if their names normalize to the same value.
    When duplicates found: keep entry with higher confidence.
    Merge is_input and is_output flags across duplicates.

    Args:
        layouts: List of IdentifiedLayout objects

    Returns:
        Deduplicated list
    """
    if not layouts:
        return []

    seen: dict[str, IdentifiedLayout] = {}

    for layout in layouts:
        normalized = _normalize_layout_name(layout.name)
        if normalized not in seen:
            seen[normalized] = layout
        else:
            # Keep entry with higher confidence
            existing = seen[normalized]
            if layout.confidence > existing.confidence:
                # New entry has higher confidence
                # But merge the flags
                layout.is_input = layout.is_input or existing.is_input
                layout.is_output = layout.is_output or existing.is_output
                seen[normalized] = layout
            else:
                # Keep existing, merge flags
                existing.is_input = existing.is_input or layout.is_input
                existing.is_output = existing.is_output or layout.is_output

    return list(seen.values())


def _filter_relevant_sections(
    sections: list[ExtractedSection],
) -> list[ExtractedSection]:
    """Filter sections most relevant for layout identification.

    Priority order:
    1. section_type == "inputs_outputs"
    2. section_type == "process_steps"
    3. section_type == "process_overview"
    4. section_type == "general"

    Exclude: "business_rules", "exceptions", "applications"
    If no priority sections found: return all sections.

    Args:
        sections: List of ExtractedSection objects

    Returns:
        Filtered list of relevant sections
    """
    if not sections:
        return []

    # Priority 1: inputs_outputs
    priority_1 = [s for s in sections if s.section_type == "inputs_outputs"]
    if priority_1:
        return priority_1

    # Priority 2: process_steps
    priority_2 = [s for s in sections if s.section_type == "process_steps"]
    if priority_2:
        return priority_2

    # Priority 3: process_overview
    priority_3 = [s for s in sections if s.section_type == "process_overview"]
    if priority_3:
        return priority_3

    # Priority 4: general
    priority_4 = [s for s in sections if s.section_type == "general"]
    if priority_4:
        return priority_4

    # Fallback: return all sections
    return sections


def _prepare_sections_text(
    sections: list[ExtractedSection], max_chars: int = 4000
) -> str:
    """Format sections for LLM prompt.

    For each section:
      Format as:
      "## {section.title} ({section.section_type})\\n{section.content}\\n"

    Join all formatted sections.
    If total length > max_chars: truncate and append notice.

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


def identify_layouts(
    sections: list[ExtractedSection],
    llm_manager: LLMManager | None = None,
    session_id: str = "",
) -> LayoutIdentificationResult:
    """Identify distinct digital layouts from document sections.

    Uses LLM analysis with retry on failure.
    Returns empty result on complete failure (does not raise).

    Args:
        sections: List of ExtractedSection objects
        llm_manager: Optional LLMManager. If None, creates default.
        session_id: Optional session ID for logging

    Returns:
        LayoutIdentificationResult with identified layouts.
        Returns empty result if sections is empty or LLM fails.
    """
    # STEP 1: Filter sections
    relevant = _filter_relevant_sections(sections)
    logger.debug(f"Analysing layouts from {len(relevant)} sections")

    # STEP 2: Prepare text
    sections_text = _prepare_sections_text(relevant, max_chars=4000)

    # STEP 3: Get LLM manager
    if llm_manager is None:
        llm_manager = LLMManager.create_default()

    # STEP 4: LLM identification — first attempt
    result: LayoutIdentificationLLMResponse | None = None
    try:
        prompt = LAYOUT_IDENTIFICATION_PROMPT.format(sections_text=sections_text)
        response = llm_manager.complete_structured(
            prompt=prompt,
            response_schema=LayoutIdentificationLLMResponse,
            system=LAYOUT_IDENTIFICATION_SYSTEM,
            max_tokens=1200,
            session_id=session_id or "layout_identifier",
        )
        result = (
            response if isinstance(response, LayoutIdentificationLLMResponse) else None
        )
    except LLMProviderError as e:
        logger.warning(f"Layout identification failed on first attempt, retrying: {e}")
        pass

    # STEP 5: Retry on failure
    if result is None:
        try:
            truncated = sections_text[:1500]
            retry_prompt = LAYOUT_IDENTIFICATION_RETRY_PROMPT.format(
                sections_text_truncated=truncated
            )
            response = llm_manager.complete_structured(
                prompt=retry_prompt,
                response_schema=LayoutIdentificationLLMResponse,
                system=LAYOUT_IDENTIFICATION_SYSTEM,
                max_tokens=800,
                session_id=(session_id or "layout_identifier") + "_retry",
            )
            result = (
                response
                if isinstance(response, LayoutIdentificationLLMResponse)
                else None
            )
        except LLMProviderError as e:
            logger.error(f"Layout identification failed after retry: {e}")
            # Return empty result on both failures
            return LayoutIdentificationResult(
                layouts=[],
                total_count=0,
                detection_confidence=0.0,
                exceeds_ceiling=False,
                notes="Identification failed — manual review required",
            )

        if result is None:
            return LayoutIdentificationResult(
                layouts=[],
                total_count=0,
                detection_confidence=0.0,
                exceeds_ceiling=False,
                notes="Identification failed — manual review required",
            )

    # STEP 6: Post-process
    # a) Deduplicate
    layouts = _deduplicate_layouts(result.layouts)

    # b) Enforce XL ceiling of 10
    exceeds_ceiling = False
    if len(layouts) > XL_LAYOUT_CEILING:
        logger.warning(
            f"Layout count ({len(layouts)}) exceeds XL ceiling ({XL_LAYOUT_CEILING}) "
            f"— keeping {XL_LAYOUT_CEILING} with highest confidence"
        )
        # Sort by confidence descending, keep top 10
        layouts_sorted = sorted(
            layouts, key=lambda layout: layout.confidence, reverse=True
        )
        layouts = layouts_sorted[:XL_LAYOUT_CEILING]
        exceeds_ceiling = True
    else:
        exceeds_ceiling = result.exceeds_ceiling

    # STEP 7: Log
    logger.info(
        f"[{session_id or 'layout_identifier'}] Layouts identified: {len(layouts)} total, "
        f"{sum(1 for layout in layouts if layout.is_input)} inputs, "
        f"{sum(1 for layout in layouts if layout.is_output)} outputs, "
        f"confidence={result.detection_confidence:.2f}"
    )

    # STEP 8: Return result
    return LayoutIdentificationResult(
        layouts=layouts,
        total_count=len(layouts),
        detection_confidence=result.detection_confidence,
        exceeds_ceiling=exceeds_ceiling,
        notes=result.notes,
    )


def get_layout_count(result: LayoutIdentificationResult) -> int:
    """Get count of distinct layouts from identification result.

    Args:
        result: LayoutIdentificationResult from identify_layouts()

    Returns:
        Number of distinct layouts (for scoring attribute #3)
    """
    return result.total_count


def get_layout_tier_hint(result: LayoutIdentificationResult) -> str:
    """Get human-readable tier hint from layout count.

    Returns a string hint about which tier the count suggests.
    Does NOT call the scoring engine.
    For logging and debugging only.

    Args:
        result: LayoutIdentificationResult from identify_layouts()

    Returns:
        Human-readable tier hint string
    """
    count = result.total_count

    if count == 1:
        return "Likely XS or S (1 layout)"
    elif count <= 3:
        return "Likely M (2-3 layouts)"
    elif count <= 6:
        return "Likely L (4-6 layouts)"
    elif count <= XL_LAYOUT_CEILING:
        return "Likely XL (7-10 layouts)"
    else:
        return "Exceeds XL ceiling — Tech Lead review needed"
