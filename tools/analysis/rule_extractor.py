"""Business rule extractor for Process Design Documents.

Extracts business rules that create new process flows with more than 2 activities.
Enforces strict flow-creation criteria per Excel definition.

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
    BUSINESS_RULE_EXTRACTION_PROMPT,
    BUSINESS_RULE_EXTRACTION_SYSTEM,
    BUSINESS_RULE_RETRY_PROMPT,
)

logger = get_logger("rule_extractor")

# XL ceiling for business rules
XL_RULE_CEILING = 6


# ==================== INTERNAL SCHEMAS ====================


class ExtractedBusinessRule(BaseModel):
    """Represents a flow-creating business rule."""

    description: str = Field(
        ..., description="Description of the rule and its new flow"
    )
    condition: str = Field(
        default="", description="The IF condition that triggers this rule"
    )
    branch_name: str = Field(..., description="Short name for this branch/flow")
    estimated_branch_activities: int = Field(
        ..., description="Number of activities in the new flow"
    )
    evidence: str = Field(
        default="", description="Evidence from the document supporting this rule"
    )
    confidence: float = Field(
        default=0.5, description="Confidence 0.0-1.0 in this extraction"
    )

    @field_validator("estimated_branch_activities")
    @classmethod
    def validate_branch_activities(cls, v: int) -> int:
        """Enforce that flow-creating rules have >2 activities.

        Per Excel definition: "A Business Rule which results in creation
        of additional flow should contain more than 2 activities."

        Args:
            v: Estimated branch activities

        Returns:
            The validated value

        Raises:
            ValueError: If activities <= 2
        """
        if v <= 2:
            raise ValueError(
                "Flow-creating rules must have more than 2 branch activities "
                "— this rule does not qualify"
            )
        return v

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


class NonQualifyingRule(BaseModel):
    """Represents a rule that was considered but excluded."""

    description: str = Field(..., description="Description of the rule")
    reason_excluded: str = Field(default="", description="Why it does not qualify")


class BusinessRuleExtractionLLMResponse(BaseModel):
    """Response schema for business rule extraction from LLM."""

    flow_creating_rules: list[ExtractedBusinessRule] = Field(
        default_factory=list, description="List of qualifying rules"
    )
    non_qualifying_rules: list[NonQualifyingRule] = Field(
        default_factory=list, description="Rules that were excluded"
    )
    total_qualifying_count: int = Field(
        default=0, description="Total count of qualifying rules"
    )
    extraction_confidence: float = Field(
        default=0.5, description="Overall extraction confidence"
    )
    notes: str = Field(default="", description="Additional observations")

    @field_validator("total_qualifying_count")
    @classmethod
    def sync_count(cls, v: int, info) -> int:
        """Sync total_qualifying_count with len(flow_creating_rules).

        Args:
            v: Total count value
            info: Validation context

        Returns:
            Synced count
        """
        if hasattr(info, "data") and "flow_creating_rules" in info.data:
            return len(info.data["flow_creating_rules"])
        return v


class BusinessRuleExtractionResult(BaseModel):
    """Final result of business rule extraction."""

    rules: list[ExtractedBusinessRule] = Field(
        ..., description="List of qualifying flow-creating rules"
    )
    total_qualifying_count: int = Field(
        ..., description="Total number of qualifying rules"
    )
    non_qualifying_rules: list[NonQualifyingRule] = Field(
        default_factory=list, description="Rules that were excluded"
    )
    extraction_confidence: float = Field(
        ..., description="Overall extraction confidence"
    )
    notes: str = Field(default="", description="Additional notes")

    def rule_names(self) -> list[str]:
        """Get list of rule branch names.

        Returns:
            List of branch names
        """
        return [r.branch_name for r in self.rules]

    def exceeds_xl_ceiling(self) -> bool:
        """Check if rule count exceeds XL ceiling (6).

        Returns:
            True if total_qualifying_count > 6
        """
        return self.total_qualifying_count > XL_RULE_CEILING


# ==================== HELPER FUNCTIONS ====================


def _filter_relevant_sections(
    sections: list[ExtractedSection],
) -> list[ExtractedSection]:
    """Filter sections most relevant for business rule extraction.

    Priority order:
    1. section_type == "business_rules"
    2. If no business_rules: return all sections EXCEPT applications and inputs_outputs
       (business rules are scattered, but exclude pure reference sections)

    Args:
        sections: List of ExtractedSection objects

    Returns:
        Filtered list of relevant sections
    """
    if not sections:
        return []

    # Priority 1: business_rules section
    priority_1 = [s for s in sections if s.section_type == "business_rules"]
    if priority_1:
        return priority_1

    # Fallback: return all sections except applications and inputs_outputs
    # (business rules are often scattered throughout)
    return [
        s for s in sections if s.section_type not in {"applications", "inputs_outputs"}
    ]


def _prepare_sections_text(
    sections: list[ExtractedSection], max_chars: int = 5000
) -> str:
    """Format sections for LLM prompt.

    For each section:
      Format as:
      "## {section.title} ({section.section_type})\n{section.content}\n"

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


def _validate_and_filter_rules(
    rules: list[ExtractedBusinessRule],
) -> list[ExtractedBusinessRule]:
    """Validate and filter business rules.

    Removes any rules where estimated_branch_activities <= 2 (safety net).
    Caps at 6 rules (XL ceiling).
    If more than 6: keeps the 6 with highest confidence.

    Args:
        rules: List of ExtractedBusinessRule objects

    Returns:
        Filtered, capped list
    """
    if not rules:
        return []

    # Filter out rules with activities <= 2 (safety net)
    filtered = []
    for rule in rules:
        if rule.estimated_branch_activities <= 2:
            logger.warning(
                f"Rule '{rule.branch_name}' has {rule.estimated_branch_activities} "
                f"activities — removed (must be >2)"
            )
        else:
            filtered.append(rule)

    # Cap at XL_RULE_CEILING
    if len(filtered) > XL_RULE_CEILING:
        logger.warning(
            f"Business rule count ({len(filtered)}) exceeds XL ceiling ({XL_RULE_CEILING}) "
            f"— keeping {XL_RULE_CEILING} with highest confidence"
        )
        # Sort by confidence descending, keep top 6
        filtered_sorted = sorted(filtered, key=lambda r: r.confidence, reverse=True)
        filtered = filtered_sorted[:XL_RULE_CEILING]

    return filtered


# ==================== PUBLIC API ====================


def extract_business_rules(
    sections: list[ExtractedSection],
    llm_manager: LLMManager | None = None,
    session_id: str = "",
) -> BusinessRuleExtractionResult:
    """Extract flow-creating business rules from document sections.

    Uses LLM analysis with retry on failure.
    Returns empty result on complete failure (does not raise).

    Args:
        sections: List of ExtractedSection objects
        llm_manager: Optional LLMManager. If None, creates default.
        session_id: Optional session ID for logging

    Returns:
        BusinessRuleExtractionResult with extracted rules.
        Returns empty result if sections is empty or LLM fails.
    """
    # STEP 1: Filter sections
    relevant = _filter_relevant_sections(sections)
    logger.debug(f"Analysing business rules from {len(relevant)} sections")

    # STEP 2: Prepare text
    sections_text = _prepare_sections_text(relevant, max_chars=5000)

    # STEP 3: Get LLM manager
    if llm_manager is None:
        llm_manager = LLMManager.create_default()

    # STEP 4: LLM extraction — first attempt
    result: BusinessRuleExtractionLLMResponse | None = None
    try:
        prompt = BUSINESS_RULE_EXTRACTION_PROMPT.format(sections_text=sections_text)
        response = llm_manager.complete_structured(
            prompt=prompt,
            response_schema=BusinessRuleExtractionLLMResponse,
            system=BUSINESS_RULE_EXTRACTION_SYSTEM,
            max_tokens=1500,
            session_id=session_id or "rule_extractor",
        )
        result = (
            response
            if isinstance(response, BusinessRuleExtractionLLMResponse)
            else None
        )
    except LLMProviderError as e:
        logger.warning(
            f"Business rule extraction failed on first attempt, retrying: {e}"
        )
        pass

    # STEP 5: Retry on failure
    if result is None:
        try:
            truncated = sections_text[:1500]
            retry_prompt = BUSINESS_RULE_RETRY_PROMPT.format(
                sections_text_truncated=truncated
            )
            response = llm_manager.complete_structured(
                prompt=retry_prompt,
                response_schema=BusinessRuleExtractionLLMResponse,
                system=BUSINESS_RULE_EXTRACTION_SYSTEM,
                max_tokens=1000,
                session_id=(session_id or "rule_extractor") + "_retry",
            )
            result = (
                response
                if isinstance(response, BusinessRuleExtractionLLMResponse)
                else None
            )
        except LLMProviderError as e:
            logger.error(f"Business rule extraction failed after retry: {e}")
            # Return empty result on both failures
            return BusinessRuleExtractionResult(
                rules=[],
                total_qualifying_count=0,
                extraction_confidence=0.0,
                notes="Extraction failed — manual review required",
            )

        if result is None:
            return BusinessRuleExtractionResult(
                rules=[],
                total_qualifying_count=0,
                extraction_confidence=0.0,
                notes="Extraction failed — manual review required",
            )

    # STEP 7: Post-process
    validated_rules = _validate_and_filter_rules(result.flow_creating_rules)

    if len(validated_rules) < len(result.flow_creating_rules):
        logger.warning(
            f"{len(result.flow_creating_rules) - len(validated_rules)} rules removed "
            f"during validation (did not meet flow-creation criteria)"
        )

    if len(validated_rules) > XL_RULE_CEILING:
        logger.warning(f"Business rule count capped at {XL_RULE_CEILING} (XL ceiling)")

    # STEP 8: Log
    logger.info(
        f"[{session_id or 'rule_extractor'}] Business rules: "
        f"{len(validated_rules)} qualifying, "
        f"{len(result.non_qualifying_rules)} non-qualifying, "
        f"confidence={result.extraction_confidence:.2f}"
    )

    for rule in validated_rules:
        logger.debug(
            f"  - {rule.branch_name} ({rule.estimated_branch_activities} activities)"
        )

    # STEP 9: Return result
    return BusinessRuleExtractionResult(
        rules=validated_rules,
        total_qualifying_count=len(validated_rules),
        non_qualifying_rules=result.non_qualifying_rules,
        extraction_confidence=result.extraction_confidence,
        notes=result.notes,
    )


def get_rule_count(result: BusinessRuleExtractionResult) -> int:
    """Get count of flow-creating business rules from extraction result.

    Args:
        result: BusinessRuleExtractionResult from extract_business_rules()

    Returns:
        Number of qualifying rules (for scoring attribute #2)
    """
    return result.total_qualifying_count


def get_rule_tier_hint(result: BusinessRuleExtractionResult) -> str:
    """Get human-readable tier hint from rule count.

    Returns a string hint about which tier the count suggests.
    Does NOT call the scoring engine.
    For logging and debugging only.

    Args:
        result: BusinessRuleExtractionResult from extract_business_rules()

    Returns:
        Human-readable tier hint string
    """
    count = result.total_qualifying_count

    if count == 0:
        return "Likely XS or S (0 flow-creating rules)"
    elif count <= 2:
        return "Likely M (1-2 flow-creating rules)"
    elif count <= 4:
        return "Likely L (3-4 flow-creating rules)"
    elif count <= XL_RULE_CEILING:
        return "Likely XL (5-6 flow-creating rules)"
    else:
        return "Exceeds XL ceiling — Tech Lead review needed"
