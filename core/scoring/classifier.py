"""
Deterministic classifier for RPA complexity tier assignment.

This module takes AttributeScore objects and produces the final
ComplexityTier classification with validation and confidence scoring.

Pure Python — no LLM calls.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core.constants import ComplexityTier
from core.exceptions import ScoringValidationError
from core.models.assessment import AttributeScore
from core.scoring.weight_matrix import exceeds_xl_ceiling


class ValidationResult(BaseModel):
    """Result of input validation for scoring."""

    model_config = ConfigDict(frozen=False)

    is_valid: bool = Field(..., description="Whether validation passed")
    errors: list[str] = Field(
        default_factory=list, description="List of error messages"
    )
    warnings: list[str] = Field(
        default_factory=list, description="List of warning messages"
    )

    def has_errors(self) -> bool:
        """Check if validation has errors.

        Returns:
            True if validation failed or has any errors
        """
        return not self.is_valid or len(self.errors) > 0


def validate_inputs(
    attribute_scores: list[AttributeScore] | None,
) -> ValidationResult:
    """Validate attribute scores before classification.

    Runs all checks and collects errors/warnings before returning.
    Does not stop at first error.

    Args:
        attribute_scores: List of AttributeScore objects to validate

    Returns:
        ValidationResult with is_valid, errors, and warnings
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check 1: Scores provided
    if not attribute_scores:
        return ValidationResult(
            is_valid=False,
            errors=["No attribute scores provided"],
            warnings=[],
        )

    # Check 2: Exactly 5 scores
    if len(attribute_scores) != 5:
        errors.append(f"Expected 5 attribute scores, got {len(attribute_scores)}")

    # Track seen attribute IDs
    seen_ids: set[int] = set()

    # Calculate total and check individual scores
    total_weight = 0
    low_weight_count = 0

    for score in attribute_scores:
        # Check 3: No duplicates
        if score.attribute_id in seen_ids:
            errors.append(f"Duplicate attribute_id: {score.attribute_id}")
        seen_ids.add(score.attribute_id)

        # Check 4: Valid attribute_id range
        if not (1 <= score.attribute_id <= 5):
            errors.append(
                f"Invalid attribute_id {score.attribute_id}: must be between 1 and 5"
            )

        # Check 5: Non-negative weight
        if score.weight < 0:
            errors.append(f"Attribute {score.attribute_id} has negative weight: {score.weight}")

        total_weight += score.weight

        # Track low weights for warning
        if score.weight <= 2:
            low_weight_count += 1

    # Check 6: Total score in valid range
    if not (0 <= total_weight <= 28):
        errors.append(f"Total score {total_weight} is outside valid range 0–28")

    # Check 7: Warning if score near tier boundary
    # Boundaries: 7 (S|M), 9 (M|L), 16 (L|XL), 23 (XL)
    tier_boundaries = [7, 9, 16, 23]
    for boundary in tier_boundaries:
        if abs(total_weight - boundary) == 1:
            warnings.append(
                f"Score {total_weight} is near tier boundary {boundary} — "
                f"consider manual review"
            )
            break  # Only warn for the closest boundary

    # Check 8: Warning if all weights are low
    if low_weight_count == 5:
        warnings.append(
            "All attributes scored low — verify PDD completeness"
        )

    is_valid = len(errors) == 0

    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
    )


def classify(total_score: int) -> ComplexityTier:
    """Classify a score to a complexity tier.

    Uses tier boundaries defined in ComplexityTier to determine
    the appropriate classification.

    Args:
        total_score: Sum of all attribute weights (0-28)

    Returns:
        The ComplexityTier classification

    Raises:
        ScoringValidationError: If score is out of valid range
    """
    if total_score < 0:
        raise ScoringValidationError(
            f"Score cannot be negative: {total_score}",
            context={"total_score": total_score},
        )

    if total_score > 28:
        raise ScoringValidationError(
            f"Score {total_score} exceeds maximum possible (28)",
            context={"total_score": total_score},
        )

    # Classify based on tier boundaries
    # Using the ComplexityTier min_score() and max_score() methods
    if total_score <= ComplexityTier.XS.max_score():  # 0-6
        return ComplexityTier.XS
    elif total_score <= ComplexityTier.S.max_score():  # 7-8
        return ComplexityTier.S
    elif total_score <= ComplexityTier.M.max_score():  # 9-15
        return ComplexityTier.M
    elif total_score <= ComplexityTier.L.max_score():  # 16-22
        return ComplexityTier.L
    else:  # 23-28
        return ComplexityTier.XL


def handle_xs_special_case(attribute_scores: list[AttributeScore]) -> bool:
    """Check if XS classification is valid.

    XS is only valid when:
    a) 2 or fewer attributes have tier XS or S (which share weights)
    b) Total score is <= 6

    Args:
        attribute_scores: List of AttributeScore objects

    Returns:
        True if XS classification is valid, False otherwise
    """
    if not attribute_scores:
        return False

    # Count XS and S tier attributes (they share the same weights)
    xs_or_s_count = sum(
        1
        for score in attribute_scores
        if score.selected_tier in (ComplexityTier.XS, ComplexityTier.S)
    )

    # Calculate total score
    total_score = sum(score.weight for score in attribute_scores)

    # Both conditions must be met
    return xs_or_s_count <= 2 and total_score <= 6


def classify_with_validation(
    attribute_scores: list[AttributeScore],
) -> tuple[ComplexityTier, ValidationResult, bool]:
    """Classify with full validation and confidence scoring.

    The main entry point that orchestrates the full classification
    pipeline including validation, classification, and special case
    handling.

    Args:
        attribute_scores: List of AttributeScore objects

    Returns:
        Tuple of (final_tier, validation_result, requires_tech_lead_review)

    Raises:
        ScoringValidationError: If validation fails
    """
    # Step 1: Validate inputs
    validation_result = validate_inputs(attribute_scores)

    # Step 2: Raise if validation failed
    if not validation_result.is_valid:
        raise ScoringValidationError(
            "Scoring validation failed",
            context={"errors": validation_result.errors},
        )

    # Step 3: Calculate total score
    total_score = sum(score.weight for score in attribute_scores)

    # Step 4: Get candidate tier
    candidate_tier = classify(total_score)

    # Step 5: Handle XS special case
    final_tier = candidate_tier
    if candidate_tier == ComplexityTier.XS:
        if not handle_xs_special_case(attribute_scores):
            # XS special case not met, fall back to S
            final_tier = ComplexityTier.S

    # Step 6: Check if Tech Lead review is needed
    requires_tech_lead = (
        final_tier == ComplexityTier.XL
        or total_score > 25
        or any(
            exceeds_xl_ceiling(score.attribute_id, score.raw_value)
            for score in attribute_scores
        )
    )

    # Step 7: Return results
    return final_tier, validation_result, requires_tech_lead


def get_confidence_score(total_score: int, tier: ComplexityTier) -> float:
    """Calculate confidence score based on distance from tier boundaries.

    Confidence is higher when the score is in the middle of a tier
    range and lower when near boundaries.

    Args:
        total_score: The score within the tier
        tier: The ComplexityTier for this score

    Returns:
        Confidence score between 0.05 and 1.0, rounded to 2 decimals
    """
    tier_min = tier.min_score()
    tier_max = tier.max_score()
    tier_range = tier_max - tier_min

    if tier_range == 0:
        # Special case: XS tier has range 0-6 (width of 6, but special)
        # Just return a reasonable confidence
        return 0.5

    # Distance from nearest edge
    distance_from_min = total_score - tier_min
    distance_from_max = tier_max - total_score
    distance_from_edge = min(distance_from_min, distance_from_max)

    # Confidence: how far from edge relative to half the range
    confidence = distance_from_edge / (tier_range / 2)

    # Clamp to 0.05-1.0
    confidence = max(0.05, min(1.0, confidence))

    # Round to 2 decimal places
    return round(confidence, 2)
