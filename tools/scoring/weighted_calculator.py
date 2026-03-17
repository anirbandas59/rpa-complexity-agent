"""
Tool to calculate weighted complexity scores from attribute scores.

This module takes a list of AttributeScore objects and produces:
1. Total weighted score (sum of all attribute weights)
2. Complexity tier classification using the Phase 1 classifier
3. Confidence score based on distance from tier boundaries
4. List of attributes that exceed XL ceilings

Pure Python — no LLM calls.
"""

from core.constants import ComplexityTier
from core.exceptions import ScoringValidationError
from core.models.assessment import AttributeScore
from core.scoring.classifier import (
    classify_with_validation,
    get_confidence_score,
)
from core.scoring.weight_matrix import exceeds_xl_ceiling
from config.logging_config import get_logger

logger = get_logger("weighted_calculator")


class WeightedScore:
    """Result of weighted score calculation.

    Attributes:
        total_score: Sum of all attribute weights (0-28)
        complexity_tier: Final classification tier
        confidence_score: Confidence in the classification (0.0-1.0)
        exceeded_ceiling_attributes: List of attribute IDs that exceed XL ceiling
        ceiling_violations: Dict mapping attribute_id to (raw_value, ceiling)
        requires_tech_lead_review: True if XL tier, score > 25, or ceiling exceeded
    """

    def __init__(
        self,
        total_score: int,
        complexity_tier: ComplexityTier,
        confidence_score: float,
        exceeded_ceiling_attributes: list[int],
        ceiling_violations: dict[int, tuple[int, int]],
        requires_tech_lead_review: bool,
    ):
        """Initialize WeightedScore.

        Args:
            total_score: Sum of all attribute weights
            complexity_tier: Final ComplexityTier
            confidence_score: Confidence 0.0-1.0
            exceeded_ceiling_attributes: List of attribute IDs with ceiling violations
            ceiling_violations: Dict of attribute_id -> (raw_value, ceiling)
            requires_tech_lead_review: Whether Tech Lead review is needed
        """
        self.total_score = total_score
        self.complexity_tier = complexity_tier
        self.confidence_score = confidence_score
        self.exceeded_ceiling_attributes = exceeded_ceiling_attributes
        self.ceiling_violations = ceiling_violations
        self.requires_tech_lead_review = requires_tech_lead_review

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"WeightedScore(score={self.total_score}, tier={self.complexity_tier}, "
            f"confidence={self.confidence_score}, tech_lead={self.requires_tech_lead_review})"
        )


def calculate_weighted_score(attribute_scores: list[AttributeScore]) -> WeightedScore:
    """Calculate weighted complexity score from attribute scores.

    This function orchestrates the full scoring pipeline:
    1. Calculates total score (sum of weights)
    2. Classifies using the deterministic Phase 1 classifier
    3. Calculates confidence score based on tier position
    4. Checks for XL ceiling violations
    5. Determines if Tech Lead review is required

    Args:
        attribute_scores: List of 5 AttributeScore objects (one per attribute)

    Returns:
        WeightedScore with all results

    Raises:
        ScoringValidationError: If attribute_scores are invalid or incomplete
    """
    # Validate inputs (will raise if not valid)
    if not attribute_scores:
        raise ScoringValidationError(
            "No attribute scores provided",
            context={"count": 0},
        )

    if len(attribute_scores) != 5:
        raise ScoringValidationError(
            f"Expected 5 attribute scores, got {len(attribute_scores)}",
            context={"expected": 5, "received": len(attribute_scores)},
        )

    # Step 1: Classify with full validation (this also validates the scores)
    final_tier, validation_result, requires_tech_lead = classify_with_validation(
        attribute_scores
    )

    # Step 2: Calculate total score
    total_score = sum(score.weight for score in attribute_scores)

    # Step 3: Calculate confidence score
    confidence = get_confidence_score(total_score, final_tier)

    # Step 4: Check for XL ceiling violations
    exceeded_ceiling_attributes: list[int] = []
    ceiling_violations: dict[int, tuple[int, int]] = {}

    for score in attribute_scores:
        if exceeds_xl_ceiling(score.attribute_id, score.raw_value):
            exceeded_ceiling_attributes.append(score.attribute_id)
            # Get the ceiling value for context
            ceilings = {1: 60, 2: 6, 3: 10, 4: 8, 5: 5}
            ceiling = ceilings.get(score.attribute_id, 999)
            ceiling_violations[score.attribute_id] = (score.raw_value, ceiling)

    logger.info(
        f"Calculated weighted score: total={total_score}, tier={final_tier}, "
        f"confidence={confidence}, ceiling_violations={len(ceiling_violations)}"
    )

    # Step 5: Log any validation warnings
    if validation_result.warnings:
        for warning in validation_result.warnings:
            logger.warning(f"Scoring warning: {warning}")

    # Step 6: Return result
    return WeightedScore(
        total_score=total_score,
        complexity_tier=final_tier,
        confidence_score=confidence,
        exceeded_ceiling_attributes=exceeded_ceiling_attributes,
        ceiling_violations=ceiling_violations,
        requires_tech_lead_review=requires_tech_lead,
    )


def get_weighted_score_summary(weighted_score: WeightedScore) -> str:
    """Generate a formatted summary of the weighted score result.

    Args:
        weighted_score: The WeightedScore to summarize

    Returns:
        Multi-line formatted string with score breakdown
    """
    lines = [
        "═" * 50,
        "Weighted Score Summary",
        "═" * 50,
        f"Total Score:         {weighted_score.total_score}/28",
        f"Complexity Tier:     {weighted_score.complexity_tier}",
        f"Confidence:          {weighted_score.confidence_score:.1%}",
    ]

    # Add ceiling violation warnings if any
    if weighted_score.exceeded_ceiling_attributes:
        lines.append("")
        lines.append("⚠️  XL Ceiling Violations:")
        for attr_id in weighted_score.exceeded_ceiling_attributes:
            raw_val, ceiling = weighted_score.ceiling_violations[attr_id]
            lines.append(f"   • Attribute {attr_id}: {raw_val} (exceeds {ceiling})")

    # Add Tech Lead review flag
    if weighted_score.requires_tech_lead_review:
        lines.append("")
        lines.append("🚨 Requires Tech Lead Review")
        reasons = []
        if weighted_score.complexity_tier == ComplexityTier.XL:
            reasons.append("Complexity tier is XL")
        if weighted_score.total_score > 25:
            reasons.append("Score exceeds 25")
        if weighted_score.exceeded_ceiling_attributes:
            reasons.append("XL ceiling violations detected")
        if reasons:
            for reason in reasons:
                lines.append(f"   • {reason}")

    lines.append("═" * 50)
    return "\n".join(lines)
