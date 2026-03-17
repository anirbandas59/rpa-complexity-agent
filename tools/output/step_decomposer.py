"""
Process step decomposer for RPA automation projects.

Generates detailed step decomposition with effort weights and reusability
classifications. Uses LLM for intelligent step generation with fallback
to minimal decomposition on failure.

All prompts in tools.output.prompts.
All LLM access via llm.manager.LLMManager abstraction.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config.logging_config import get_logger
from core.constants import ReusabilityTag, StepWeight
from core.exceptions import LLMProviderError
from core.models.assessment import AssessmentResult
from core.models.document import ExtractedSection
from core.models.process import ProcessStep
from llm.manager import LLMManager
from tools.analysis.rule_extractor import BusinessRuleExtractionResult
from tools.output.prompts import (
    STEP_DECOMPOSITION_PROMPT,
    STEP_DECOMPOSITION_RETRY_PROMPT,
    STEP_DECOMPOSITION_SYSTEM,
)

logger = get_logger("step_decomposer")

# ===========================================================================
# INTERNAL SCHEMAS
# ===========================================================================


class StepData(BaseModel):
    """Represents a single step in a process decomposition."""

    model_config = ConfigDict(frozen=False)

    step_number: int = Field(..., description="Sequential step number (1-based)")
    description: str = Field(..., description="What the bot does in this step")
    weight: float = Field(default=1.0, description="Development effort weight")
    reusability_tag: str = Field(default="NONE", description="Reusability classification")
    reusability_comment: str = Field(default="", description="Explanation of reusability")

    @field_validator("weight", mode="before")
    @classmethod
    def normalize_weight(cls, v: float) -> float:
        """Normalize weight to nearest valid value.

        Valid weights: 0.0, 0.5, 1.0, 2.0
        If invalid: round to nearest valid value.

        Args:
            v: Weight value

        Returns:
            Nearest valid weight
        """
        if v not in (0.0, 0.5, 1.0, 2.0):
            # Find nearest valid value
            valid_values = [0.0, 0.5, 1.0, 2.0]
            v = min(valid_values, key=lambda x: abs(x - v))
        return v

    @field_validator("reusability_tag", mode="before")
    @classmethod
    def normalize_tag(cls, v: str) -> str:
        """Normalize reusability tag to valid enum value.

        Valid tags: FULL, PARTIAL, NONE
        If invalid: set to NONE.

        Args:
            v: Tag value

        Returns:
            Valid reusability tag
        """
        if v not in ("FULL", "PARTIAL", "NONE"):
            v = "NONE"
        return v

    @model_validator(mode="after")
    def enforce_tag_weight_consistency(self) -> StepData:
        """Enforce tag-weight consistency rules.

        - FULL tag → weight must be 0.0
        - PARTIAL tag → weight must be 0.5
        - NONE tag → weight must be 1.0 or 2.0

        Silently corrects inconsistencies.

        Returns:
            Corrected StepData
        """
        if self.reusability_tag == "FULL":
            self.weight = 0.0
        elif self.reusability_tag == "PARTIAL":
            self.weight = 0.5
        elif self.reusability_tag == "NONE":
            if self.weight not in (1.0, 2.0):
                self.weight = 1.0
        return self


class BranchData(BaseModel):
    """Represents a process branch with its steps."""

    model_config = ConfigDict(frozen=False)

    branch_name: str = Field(..., description="Name of this branch")
    description: str = Field(default="", description="What this branch does")
    steps: list[StepData] = Field(default_factory=list, description="Steps in this branch")

    @property
    def branch_total_weight(self) -> float:
        """Compute total weight for all steps in this branch.

        Returns:
            Sum of all step weights, rounded to 1 decimal place
        """
        return round(sum(s.weight for s in self.steps), 1)

    @property
    def step_count(self) -> int:
        """Count steps in this branch.

        Returns:
            Number of steps
        """
        return len(self.steps)


class StepDecompositionLLMResponse(BaseModel):
    """Response schema from LLM step decomposition."""

    model_config = ConfigDict(frozen=False)

    branches: list[BranchData] = Field(default_factory=list, description="Process branches")
    total_weighted_steps: float = Field(
        default=0.0, description="Sum of all step weights"
    )
    generation_notes: str = Field(default="", description="Notes about generation")

    @model_validator(mode="after")
    def sync_total_weight(self) -> StepDecompositionLLMResponse:
        """Sync total_weighted_steps with actual branch weights.

        Recalculates total from actual branches.

        Returns:
            Corrected response
        """
        self.total_weighted_steps = round(
            sum(branch.branch_total_weight for branch in self.branches), 1
        )
        return self


class StepDecompositionResult(BaseModel):
    """Final result of step decomposition."""

    model_config = ConfigDict(frozen=False)

    project_name: str = Field(..., description="Project name")
    branches: list[BranchData] = Field(default_factory=list, description="All branches")
    total_weighted_steps: float = Field(..., description="Total effort weight")
    total_step_count: int = Field(..., description="Total number of steps")
    generation_notes: str = Field(default="", description="Generation notes")

    @property
    def all_steps(self) -> list[ProcessStep]:
        """Convert all branch steps to ProcessStep objects.

        Renumbers steps sequentially across all branches.

        Returns:
            Flat list of ProcessStep objects
        """
        all_steps: list[ProcessStep] = []
        step_number = 1

        for branch in self.branches:
            for step_data in branch.steps:
                process_step = ProcessStep(
                    step_number=step_number,
                    description=step_data.description,
                    weight=StepWeight.from_float(step_data.weight),
                    reusability_tag=ReusabilityTag(step_data.reusability_tag),
                    branch_name=branch.branch_name,
                    reusability_comment=step_data.reusability_comment,
                )
                all_steps.append(process_step)
                step_number += 1

        return all_steps

    @property
    def branch_names(self) -> list[str]:
        """Get all branch names.

        Returns:
            List of branch names in order
        """
        return [b.branch_name for b in self.branches]


# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================


def _prepare_sections_text(sections: list[ExtractedSection], max_chars: int = 3000) -> str:
    """Format sections for the LLM prompt.

    Args:
        sections: List of extracted sections
        max_chars: Maximum characters to include

    Returns:
        Formatted section text for prompt
    """
    if not sections:
        return "No process sections identified."

    text_parts = []
    char_count = 0

    for i, section in enumerate(sections, 1):
        section_text = f"{i}. {section.title}\n{section.content[:200]}"
        if char_count + len(section_text) > max_chars:
            break
        text_parts.append(section_text)
        char_count += len(section_text)

    if not text_parts:
        return "Process sections available but truncated."

    return "\n\n".join(text_parts)


def _prepare_rules_text(rule_result: Optional[BusinessRuleExtractionResult]) -> str:
    """Format business rules for the LLM prompt.

    Args:
        rule_result: Business rule extraction result or None

    Returns:
        Formatted rules text for prompt
    """
    if not rule_result or not rule_result.rules:
        return "No business rules identified."

    text_parts = []
    for i, rule in enumerate(rule_result.rules, 1):
        rule_text = f"{i}. {rule.branch_name}: {rule.description}"
        text_parts.append(rule_text)

    return "\n".join(text_parts)


# ===========================================================================
# MAIN DECOMPOSER FUNCTION
# ===========================================================================


def decompose_steps(
    sections: list[ExtractedSection],
    assessment_result: AssessmentResult,
    rule_result: Optional[BusinessRuleExtractionResult] = None,
    llm_manager: Optional[LLMManager] = None,
    session_id: str = "",
) -> StepDecompositionResult:
    """Decompose RPA process into detailed steps with effort weights.

    Uses LLM for intelligent step generation. Falls back to minimal
    decomposition if LLM is unavailable.

    Args:
        sections: Extracted document sections
        assessment_result: Complexity assessment result
        rule_result: Business rule extraction result (optional)
        llm_manager: LLM manager instance (optional, auto-created if None)
        session_id: Session ID for logging

    Returns:
        StepDecompositionResult with branches and weighted steps

    Raises:
        No exceptions — always returns a valid result
    """
    # Prepare context for LLM
    sections_text = _prepare_sections_text(sections)
    rules_text = _prepare_rules_text(rule_result)

    activity_count = 0
    if assessment_result.attribute_scores:
        activity_count = assessment_result.attribute_scores[0].raw_value

    rule_count = len(rule_result.rules) if rule_result else 0

    # Format prompt
    prompt = STEP_DECOMPOSITION_PROMPT.format(
        project_name=assessment_result.project_name,
        rpa_tool=assessment_result.rpa_tool.value,
        tier=assessment_result.complexity_tier.value,
        activity_count=activity_count,
        rule_count=rule_count,
        sections_text=sections_text,
        rules_text=rules_text,
    )

    # Get LLM manager
    if llm_manager is None:
        llm_manager = LLMManager()

    # First LLM attempt
    try:
        llm_response = llm_manager.call_with_schema(
            system_prompt=STEP_DECOMPOSITION_SYSTEM,
            user_prompt=prompt,
            response_schema=StepDecompositionLLMResponse,
            max_tokens=2500,
        )
        if isinstance(llm_response, dict):
            llm_response = StepDecompositionLLMResponse(**llm_response)
    except (LLMProviderError, Exception) as e:
        # Retry with minimal prompt
        logger.warning(
            f"[{session_id}] Step decomposition LLM call failed: {e}. Retrying with fallback..."
        )
        try:
            llm_response = llm_manager.call_with_schema(
                system_prompt=STEP_DECOMPOSITION_SYSTEM,
                user_prompt=STEP_DECOMPOSITION_RETRY_PROMPT,
                response_schema=StepDecompositionLLMResponse,
                max_tokens=500,
            )
            if isinstance(llm_response, dict):
                llm_response = StepDecompositionLLMResponse(**llm_response)
        except (LLMProviderError, Exception):
            # Both attempts failed — return minimal fallback
            logger.warning(
                f"[{session_id}] Step decomposition failed completely. Using minimal fallback."
            )
            return StepDecompositionResult(
                project_name=assessment_result.project_name,
                branches=[
                    BranchData(
                        branch_name="Main Process Flow",
                        description="Fallback — manual decomposition required",
                        steps=[
                            StepData(
                                step_number=1,
                                description="Process steps to be defined manually",
                                weight=1.0,
                                reusability_tag="NONE",
                                reusability_comment="",
                            )
                        ],
                    )
                ],
                total_weighted_steps=1.0,
                total_step_count=1,
                generation_notes="Fallback — LLM unavailable",
            )

    # Post-process response
    actual_total = round(
        sum(branch.branch_total_weight for branch in llm_response.branches), 1
    )
    actual_count = sum(branch.step_count for branch in llm_response.branches)

    # Log result
    logger.info(
        f"[{session_id}] Steps decomposed: {len(llm_response.branches)} branches, "
        f"{actual_count} steps, {actual_total:.1f} weighted total"
    )

    # Return result
    return StepDecompositionResult(
        project_name=assessment_result.project_name,
        branches=llm_response.branches,
        total_weighted_steps=actual_total,
        total_step_count=actual_count,
        generation_notes=llm_response.generation_notes,
    )
