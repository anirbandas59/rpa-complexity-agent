"""
Weight matrix for RPA complexity assessment.

This module loads the weight matrix from data/reference/weight_matrix.json
and provides functions to look up weights, map values to tiers, and
check for ceiling violations.

The weight matrix is the single source of truth for all scoring weights
and tier range mappings.
"""

import json
from pathlib import Path
from typing import Any

from core.constants import ComplexityTier
from core.exceptions import DocumentProcessingError, ScoringValidationError

# Load weight matrix at module level
_WEIGHT_MATRIX_PATH = Path(__file__).parent.parent.parent / "data" / "reference" / "weight_matrix.json"

try:
    with open(_WEIGHT_MATRIX_PATH) as f:
        _WEIGHT_DATA: dict[str, Any] = json.load(f)
except FileNotFoundError as e:
    raise DocumentProcessingError(
        f"weight_matrix.json not found at {_WEIGHT_MATRIX_PATH}. "
        f"Run scripts/seed_reference_data.py first."
    ) from e

# Extract the weights dict for easy access
_WEIGHTS: dict[str, dict[str, dict[str, Any]]] = _WEIGHT_DATA.get("weights", {})

# Attribute ID to name mapping
_ATTRIBUTE_NAMES = {
    1: "activities",
    2: "business_rules",
    3: "layouts",
    4: "interfaces",
    5: "technology",
}

# Reverse mapping for getting attribute ID from name
_ATTRIBUTE_IDS = {v: k for k, v in _ATTRIBUTE_NAMES.items()}

# XL ceilings for each attribute
_XL_CEILINGS = {
    1: 60,  # Activities
    2: 6,   # Business Rules
    3: 10,  # Layouts
    4: 8,   # Interfaces
    5: 5,   # Technology
}


def get_weight(attribute_id: int, tier: ComplexityTier) -> int:
    """Get the point weight for an attribute and tier combination.

    Args:
        attribute_id: Attribute ID (1-5)
        tier: ComplexityTier (XS, S, M, L, XL)

    Returns:
        The point weight for this combination

    Raises:
        ScoringValidationError: If attribute_id or tier is invalid
    """
    if attribute_id not in _ATTRIBUTE_NAMES:
        raise ScoringValidationError(
            f"Invalid attribute_id: {attribute_id}. Must be 1-5.",
            context={"attribute_id": attribute_id},
        )

    if not isinstance(tier, ComplexityTier):
        raise ScoringValidationError(
            f"Invalid tier: {tier}. Must be a ComplexityTier.",
            context={"tier": tier},
        )

    attribute_name = _ATTRIBUTE_NAMES[attribute_id]
    tier_name = tier.value

    try:
        weight_info = _WEIGHTS[attribute_name][tier_name]
        return weight_info["weight"]
    except (KeyError, TypeError) as e:
        raise ScoringValidationError(
            f"Weight not found for attribute {attribute_id} ({attribute_name}) "
            f"and tier {tier_name}",
            context={"attribute_id": attribute_id, "tier": tier_name},
        ) from e


def get_tier_range_description(attribute_id: int, tier: ComplexityTier) -> str:
    """Get the human-readable range description for an attribute-tier pair.

    Args:
        attribute_id: Attribute ID (1-5)
        tier: ComplexityTier (XS, S, M, L, XL)

    Returns:
        The range description (e.g., "41-60 activities")

    Raises:
        ScoringValidationError: If attribute_id or tier is invalid
    """
    if attribute_id not in _ATTRIBUTE_NAMES:
        raise ScoringValidationError(
            f"Invalid attribute_id: {attribute_id}. Must be 1-5.",
            context={"attribute_id": attribute_id},
        )

    if not isinstance(tier, ComplexityTier):
        raise ScoringValidationError(
            f"Invalid tier: {tier}. Must be a ComplexityTier.",
            context={"tier": tier},
        )

    attribute_name = _ATTRIBUTE_NAMES[attribute_id]
    tier_name = tier.value

    try:
        tier_info = _WEIGHTS[attribute_name][tier_name]
        return tier_info.get("range", "Unknown range")
    except (KeyError, TypeError) as e:
        raise ScoringValidationError(
            f"Range description not found for attribute {attribute_id} "
            f"({attribute_name}) and tier {tier_name}",
            context={"attribute_id": attribute_id, "tier": tier_name},
        ) from e


def get_all_weights() -> dict[str, dict[str, int]]:
    """Get the full weight matrix for inspection.

    Returns:
        Nested dict: attribute_name -> tier_name -> weight value
    """
    result: dict[str, dict[str, int]] = {}
    for attr_name, tiers in _WEIGHTS.items():
        result[attr_name] = {}
        for tier_name, tier_info in tiers.items():
            result[attr_name][tier_name] = tier_info["weight"]
    return result


def map_value_to_tier(attribute_id: int, raw_value: int) -> ComplexityTier:
    """Map a raw value count to the appropriate ComplexityTier.

    Each attribute has defined ranges that map to specific tiers.
    Values are capped at XL if they exceed the maximum.

    Args:
        attribute_id: Attribute ID (1-5)
        raw_value: The raw count value to map

    Returns:
        The ComplexityTier for this value

    Raises:
        ScoringValidationError: If attribute_id is invalid or raw_value < 0
    """
    if attribute_id not in _ATTRIBUTE_NAMES:
        raise ScoringValidationError(
            f"Invalid attribute_id: {attribute_id}. Must be 1-5.",
            context={"attribute_id": attribute_id},
        )

    if raw_value < 0:
        raise ScoringValidationError(
            f"Invalid raw_value: {raw_value}. Must be >= 0.",
            context={"attribute_id": attribute_id, "raw_value": raw_value},
        )

    # Map based on attribute ID
    if attribute_id == 1:  # Activities
        if raw_value <= 10:
            return ComplexityTier.S
        elif raw_value <= 20:
            return ComplexityTier.M
        elif raw_value <= 40:
            return ComplexityTier.L
        else:  # 41+
            return ComplexityTier.XL

    elif attribute_id == 2:  # Business Rules
        if raw_value == 0:
            return ComplexityTier.S
        elif raw_value <= 2:
            return ComplexityTier.M
        elif raw_value <= 4:
            return ComplexityTier.L
        else:  # 5+
            return ComplexityTier.XL

    elif attribute_id == 3:  # Layouts
        if raw_value == 1:
            return ComplexityTier.S
        elif raw_value <= 3:
            return ComplexityTier.M
        elif raw_value <= 6:
            return ComplexityTier.L
        else:  # 7+
            return ComplexityTier.XL

    elif attribute_id == 4:  # Interfaces
        if raw_value == 0:
            return ComplexityTier.S
        elif raw_value <= 2:
            return ComplexityTier.S
        elif raw_value <= 4:
            return ComplexityTier.M
        elif raw_value <= 6:
            return ComplexityTier.L
        else:  # 7+
            return ComplexityTier.XL

    elif attribute_id == 5:  # Additional Technology
        if raw_value == 0:
            return ComplexityTier.S
        elif raw_value == 1:
            return ComplexityTier.M
        elif raw_value <= 3:
            return ComplexityTier.L
        else:  # 4+
            return ComplexityTier.XL

    # Should never reach here
    raise ScoringValidationError(
        f"Unexpected attribute_id: {attribute_id}",
        context={"attribute_id": attribute_id},
    )


def exceeds_xl_ceiling(attribute_id: int, raw_value: int) -> bool:
    """Check if a value exceeds the XL ceiling for an attribute.

    XL ceilings define the maximum normal values for each attribute.
    Values exceeding the ceiling may require Tech Lead review.

    Args:
        attribute_id: Attribute ID (1-5)
        raw_value: The raw value to check

    Returns:
        True if raw_value exceeds the XL ceiling

    Raises:
        ScoringValidationError: If attribute_id is invalid
    """
    if attribute_id not in _ATTRIBUTE_NAMES:
        raise ScoringValidationError(
            f"Invalid attribute_id: {attribute_id}. Must be 1-5.",
            context={"attribute_id": attribute_id},
        )

    ceiling = _XL_CEILINGS.get(attribute_id, float('inf'))
    return raw_value > ceiling
