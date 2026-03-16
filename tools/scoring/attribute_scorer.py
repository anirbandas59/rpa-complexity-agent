"""
Tool to map raw attribute counts to scored AttributeScore objects.

This module takes a single raw count and deterministically maps it to an
AttributeScore using the Phase 1 scoring engine (weight_matrix).

Pure Python — no LLM calls.
"""

from config.logging_config import get_logger
from core.constants import ComplexityTier
from core.exceptions import ScoringValidationError
from core.models.assessment import AttributeScore
from core.scoring.weight_matrix import (
    get_tier_range_description,
    get_weight,
    map_value_to_tier,
)

logger = get_logger("attribute_scorer")

# Attribute metadata: ID to name and description mapping
ATTRIBUTE_METADATA = {
    1: {
        "name": "activities",
        "display_name": "Activities",
        "description": "Number of distinct activities/steps in the process",
    },
    2: {
        "name": "business_rules",
        "display_name": "Business Rules",
        "description": "Number of significant business rules or decision points",
    },
    3: {
        "name": "layouts",
        "display_name": "Layouts",
        "description": "Number of unique UI layouts/screens to interact with",
    },
    4: {
        "name": "interfaces",
        "display_name": "Interfaces",
        "description": "Number of external system interfaces/APIs",
    },
    5: {
        "name": "technology",
        "display_name": "Additional Technology",
        "description": "Count of non-standard or additional technologies required",
    },
}


def score_attribute(attribute_id: int, raw_value: int) -> AttributeScore:
    """Map a raw attribute count to an AttributeScore.

    This function implements the core scoring logic:
    1. Validates attribute_id (1-5)
    2. Maps raw_value to a ComplexityTier using the weight matrix
    3. Retrieves the weight for the (attribute_id, tier) pair
    4. Generates a human-readable rationale
    5. Returns a complete AttributeScore

    Args:
        attribute_id: Attribute ID (1-5)
        raw_value: The raw count extracted from the PDD (must be >= 0)

    Returns:
        AttributeScore with tier, weight, and rationale populated

    Raises:
        ScoringValidationError: If attribute_id is invalid or raw_value < 0
    """
    # Validate inputs
    if attribute_id not in ATTRIBUTE_METADATA:
        raise ScoringValidationError(
            f"Invalid attribute_id: {attribute_id}. Must be 1-5.",
            context={"attribute_id": attribute_id},
        )

    if raw_value < 0:
        raise ScoringValidationError(
            f"Invalid raw_value: {raw_value}. Must be >= 0.",
            context={"attribute_id": attribute_id, "raw_value": raw_value},
        )

    metadata = ATTRIBUTE_METADATA[attribute_id]
    attribute_name = metadata["display_name"]

    # Step 1: Map raw value to tier
    selected_tier = map_value_to_tier(attribute_id, raw_value)

    # Step 2: Get the weight for this tier
    weight = get_weight(attribute_id, selected_tier)

    # Step 3: Get the range description for rationale
    range_desc = get_tier_range_description(attribute_id, selected_tier)

    # Step 4: Generate rationale
    tier_rationale = _generate_rationale(
        attribute_id, attribute_name, raw_value, selected_tier, range_desc
    )

    logger.info(
        f"Scored attribute {attribute_id} ({attribute_name}): "
        f"raw={raw_value} → tier={selected_tier} weight={weight}"
    )

    # Step 5: Create and return AttributeScore
    return AttributeScore(
        attribute_id=attribute_id,
        attribute_name=attribute_name,
        raw_value=raw_value,
        selected_tier=selected_tier,
        weight=weight,
        tier_rationale=tier_rationale,
    )


def _generate_rationale(
    attribute_id: int,
    attribute_name: str,
    raw_value: int,
    tier: ComplexityTier,
    range_desc: str,
) -> str:
    """Generate a human-readable rationale for the tier selection.

    Args:
        attribute_id: The attribute ID (for reference)
        attribute_name: Display name of the attribute
        raw_value: The raw count value
        tier: The selected ComplexityTier
        range_desc: Range description from weight matrix (e.g., "41-60 activities")

    Returns:
        A formatted string explaining the tier selection
    """
    tier_display = {
        ComplexityTier.XS: "Extra Small (XS)",
        ComplexityTier.S: "Small (S)",
        ComplexityTier.M: "Medium (M)",
        ComplexityTier.L: "Large (L)",
        ComplexityTier.XL: "Extra Large (XL)",
    }

    return (
        f"{raw_value} {attribute_name.lower()} ({range_desc}) "
        f"→ {tier_display[tier]} complexity tier"
    )


def validate_attribute_score(score: AttributeScore) -> None:
    """Validate an AttributeScore for internal consistency.

    Confirms that:
    - attribute_id is valid (1-5)
    - raw_value >= 0
    - weight >= 0
    - selected_tier is a valid ComplexityTier

    Args:
        score: The AttributeScore to validate

    Raises:
        ScoringValidationError: If validation fails
    """
    if score.attribute_id not in ATTRIBUTE_METADATA:
        raise ScoringValidationError(
            f"Invalid attribute_id in score: {score.attribute_id}. Must be 1-5.",
            context={"attribute_id": score.attribute_id},
        )

    if score.raw_value < 0:
        raise ScoringValidationError(
            f"Invalid raw_value in score: {score.raw_value}. Must be >= 0.",
            context={"attribute_id": score.attribute_id, "raw_value": score.raw_value},
        )

    if score.weight < 0:
        raise ScoringValidationError(
            f"Invalid weight in score: {score.weight}. Must be >= 0.",
            context={"attribute_id": score.attribute_id, "weight": score.weight},
        )

    if not isinstance(score.selected_tier, ComplexityTier):
        raise ScoringValidationError(
            f"Invalid selected_tier in score: {score.selected_tier}. "
            f"Must be a ComplexityTier.",
            context={"attribute_id": score.attribute_id, "tier": score.selected_tier},
        )

    logger.info(
        f"Validated AttributeScore #{score.attribute_id} ({score.attribute_name})"
    )
