"""
Tool to generate complexity assessment results with LLM-based reasoning narratives.

This module takes AttributeScore objects from the deterministic scoring engine
(Phase 1) and uses an LLM to generate human-readable reasoning narratives
explaining the complexity classification.

The tier classification itself is deterministic (Phase 1 engine) — the LLM
only generates the explanation, never changes the tier.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from config.logging_config import get_logger
from core.constants import ComplexityTier, RPATool
from core.exceptions import LLMProviderError, ScoringValidationError
from core.models.assessment import AttributeScore, AssessmentResult
from core.scoring.classifier import classify_with_validation, get_confidence_score
from llm.manager import LLMManager
from tools.scoring.prompts import (
    REASONING_GENERATION_PROMPT,
    REASONING_GENERATION_SYSTEM,
    REASONING_RETRY_PROMPT,
)

logger = get_logger("classifier_tool")


# ==================== INTERNAL SCHEMA ====================


class ReasoningResponse(BaseModel):
    """Response from the LLM containing reasoning narrative."""

    reasoning: str = Field(..., description="Professional explanation of tier")
    key_drivers: list[str] = Field(
        default_factory=list, description="Main complexity drivers"
    )
    simplification_opportunities: list[str] = Field(
        default_factory=list, description="Ways to reduce complexity"
    )
    tech_lead_note: str = Field(
        default="", description="Note for Tech Lead review if needed"
    )

    @field_validator("reasoning")
    @classmethod
    def reasoning_not_empty(cls, v: str) -> str:
        """Ensure reasoning is non-empty.

        Args:
            v: The reasoning string

        Returns:
            The validated reasoning string, or a default if empty

        Raises:
            No exception — fills with default if empty
        """
        if not v or v.strip() == "":
            return "Assessment complete. See score summary for details."
        return v


# ==================== HELPER FUNCTIONS ====================


def _build_attribute_breakdown(attribute_scores: list[AttributeScore]) -> str:
    """Build formatted attribute breakdown for LLM prompt.

    Args:
        attribute_scores: List of 5 AttributeScore objects

    Returns:
        Multi-line formatted string with attribute details
    """
    lines = []
    for score in attribute_scores:
        attr_name_singular = score.attribute_name
        # Format: #1 Number of Activities: 45 → XL tier (weight: 8)
        line = (
            f"#{score.attribute_id} {attr_name_singular}: {score.raw_value} "
            f"→ {score.selected_tier.value} tier (weight: {score.weight})"
        )
        lines.append(line)
    return "\n".join(lines)


def _check_requires_tech_lead_review(
    attribute_scores: list[AttributeScore],
    tier: ComplexityTier,
    total_score: int,
) -> bool:
    """Check if Tech Lead review is required.

    Returns True if ANY of these conditions are true:
    - tier == XL
    - total_score > 25
    - Any attribute's tier_rationale contains "⚠️"

    Args:
        attribute_scores: List of AttributeScore objects
        tier: The ComplexityTier classification
        total_score: The total weighted score

    Returns:
        True if Tech Lead review is needed
    """
    # Condition 1: XL tier
    if tier == ComplexityTier.XL:
        return True

    # Condition 2: Score > 25
    if total_score > 25:
        return True

    # Condition 3: Any ceiling violations (indicated by ⚠️ in rationale)
    for score in attribute_scores:
        if "⚠️" in score.tier_rationale:
            return True

    return False


def _build_score_summary(
    attribute_scores: list[AttributeScore],
    tier: ComplexityTier,
    total_score: int,
    confidence: float,
) -> str:
    """Build formatted score summary for LLM prompt.

    Args:
        attribute_scores: List of 5 AttributeScore objects
        tier: The ComplexityTier classification
        total_score: The total weighted score
        confidence: Confidence score 0.0-1.0

    Returns:
        Formatted string with score summary
    """
    lines = [
        f"Total Score: {total_score}/28",
        f"Complexity Tier: {tier.value}",
        f"Confidence: {confidence:.0%}",
    ]
    return "\n".join(lines)


# ==================== MAIN FUNCTIONS ====================


def generate_reasoning(
    attribute_scores: list[AttributeScore],
    tier: ComplexityTier,
    total_score: int,
    confidence: float,
    project_name: str = "RPA Process",
    rpa_tool: RPATool = RPATool.UNKNOWN,
    llm_manager: LLMManager | None = None,
    session_id: str = "",
) -> ReasoningResponse:
    """Generate reasoning narrative using LLM.

    Uses LLM to create a professional, client-facing explanation of why the
    process received a particular complexity tier. The tier itself is already
    determined by the Phase 1 deterministic engine — the LLM only explains it.

    On LLM failure, returns a fallback response with default messaging.

    Args:
        attribute_scores: List of 5 AttributeScore objects
        tier: The ComplexityTier classification (deterministic)
        total_score: The total weighted score (0-28)
        confidence: Confidence score (0.0-1.0)
        project_name: Name of the RPA project (default "RPA Process")
        rpa_tool: Detected RPATool (default UNKNOWN)
        llm_manager: LLMManager instance; if None, creates default
        session_id: Session identifier for logging

    Returns:
        ReasoningResponse with narrative, drivers, and notes
    """
    if not session_id:
        session_id = "classifier_tool"

    # Step 1: Build prompt context
    breakdown = _build_attribute_breakdown(attribute_scores)
    summary = _build_score_summary(attribute_scores, tier, total_score, confidence)
    confidence_pct = round(confidence * 100)

    # Step 2: Format prompt
    prompt = REASONING_GENERATION_PROMPT.format(
        project_name=project_name,
        rpa_tool=rpa_tool.value,
        tier=tier.value,
        total_score=total_score,
        confidence_pct=confidence_pct,
        attribute_breakdown=breakdown,
        score_summary=summary,
    )

    # Step 3: Get LLM manager
    if llm_manager is None:
        llm_manager = LLMManager()

    # Step 4: First LLM attempt
    try:
        result = llm_manager.complete_structured(
            prompt=prompt,
            response_schema=ReasoningResponse,
            system=REASONING_GENERATION_SYSTEM,
            max_tokens=800,
            session_id=session_id,
        )
        logger.info(
            f"[{session_id}] Reasoning generated for {tier.value} tier, "
            f"{len(result.key_drivers)} drivers identified"
        )
        return result
    except LLMProviderError as e:
        logger.warning(f"[{session_id}] LLM first attempt failed: {e}")

        # Step 5: Fallback attempt
        fallback_prompt = REASONING_RETRY_PROMPT.format(
            tier=tier.value,
            total_score=total_score,
        )

        try:
            fallback_result = llm_manager.complete_structured(
                prompt=fallback_prompt,
                response_schema=ReasoningResponse,
                system=REASONING_GENERATION_SYSTEM,
                max_tokens=200,
                session_id=session_id,
            )
            logger.info(f"[{session_id}] Fallback reasoning succeeded")
            return fallback_result
        except LLMProviderError as fallback_error:
            logger.warning(
                f"[{session_id}] Fallback LLM attempt also failed: {fallback_error}"
            )

            # Step 6: Return hardcoded fallback
            return ReasoningResponse(
                reasoning=(
                    f"This process has been assessed as {tier.value} complexity "
                    f"with a score of {total_score}/28. Manual review recommended."
                ),
                key_drivers=["Assessment data available in score summary"],
                simplification_opportunities=[],
                tech_lead_note="",
            )


def classify_and_explain(
    attribute_scores: list[AttributeScore],
    project_name: str = "RPA Process",
    rpa_tool: RPATool = RPATool.UNKNOWN,
    session_id: str = "",
    llm_manager: LLMManager | None = None,
) -> AssessmentResult:
    """Orchestrate classification and narrative generation.

    The main public function that produces a complete AssessmentResult by:
    1. Running deterministic Phase 1 classification
    2. Calculating confidence score
    3. Checking Tech Lead review requirements
    4. Generating LLM-based reasoning narrative
    5. Building and returning final AssessmentResult

    Args:
        attribute_scores: List of 5 AttributeScore objects
        project_name: Name of the RPA project (default "RPA Process")
        rpa_tool: Detected RPATool (default UNKNOWN)
        session_id: Session identifier; if empty, generates new UUID
        llm_manager: LLMManager instance; if None, creates default

    Returns:
        AssessmentResult with all classification and reasoning details

    Raises:
        ScoringValidationError: If attribute_scores are invalid
    """
    if not session_id:
        session_id = str(uuid.uuid4())[:8]

    # Step 1: Classify using deterministic Phase 1 engine
    tier, validation_result, requires_tech_lead = classify_with_validation(
        attribute_scores
    )

    # Step 2: Calculate total score and confidence
    total_score = sum(score.weight for score in attribute_scores)
    confidence = get_confidence_score(total_score, tier)

    # Step 3: Check Tech Lead review (redundant but explicit)
    requires_review = _check_requires_tech_lead_review(
        attribute_scores, tier, total_score
    )

    # Step 4: Generate reasoning narrative
    reasoning_response = generate_reasoning(
        attribute_scores=attribute_scores,
        tier=tier,
        total_score=total_score,
        confidence=confidence,
        project_name=project_name,
        rpa_tool=rpa_tool,
        llm_manager=llm_manager,
        session_id=session_id,
    )

    # Step 5: Append Tech Lead note if present
    full_reasoning = reasoning_response.reasoning
    if reasoning_response.tech_lead_note:
        full_reasoning = (
            f"{full_reasoning}\n\nTech Lead Note: {reasoning_response.tech_lead_note}"
        )

    # Step 6: Build and return AssessmentResult
    result = AssessmentResult(
        session_id=session_id,
        project_name=project_name,
        rpa_tool=rpa_tool,
        attribute_scores=attribute_scores,
        total_score=total_score,
        complexity_tier=tier,
        confidence_score=confidence,
        reasoning=full_reasoning,
        requires_tech_lead_review=requires_review,
        created_at=datetime.utcnow(),
    )

    logger.info(
        f"[{session_id}] Classification complete. Tier: {tier.value}, "
        f"Score: {total_score}, Confidence: {confidence:.2f}"
    )

    return result
