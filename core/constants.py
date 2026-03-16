"""
Core constants and enums for RPA Complexity Assessment.

Defines all domain enums including complexity tiers, RPA tools,
assessment phases, step weights, and reusability tags.
"""

from enum import Enum

from core.exceptions import ScoringValidationError


class ComplexityTier(str, Enum):
    """Complexity classification tiers."""

    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"

    def __str__(self) -> str:
        """Return human-readable tier name."""
        return self.value

    def numeric_rank(self) -> int:
        """Return numeric rank for comparison (XS=1 to XL=5)."""
        ranks = {"XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5}
        return ranks[self.value]

    def is_above(self, other: "ComplexityTier") -> bool:
        """Check if this tier is above another tier.

        Args:
            other: Another ComplexityTier to compare

        Returns:
            True if this tier's rank is higher than the other tier
        """
        return self.numeric_rank() > other.numeric_rank()

    def min_score(self) -> int:
        """Return minimum score for this tier.

        Returns:
            Minimum score threshold for this tier
        """
        scores = {"XS": 0, "S": 7, "M": 9, "L": 16, "XL": 23}
        return scores[self.value]

    def max_score(self) -> int:
        """Return maximum score for this tier.

        Returns:
            Maximum score threshold for this tier
        """
        scores = {"XS": 6, "S": 8, "M": 15, "L": 22, "XL": 28}
        return scores[self.value]


class RPATool(str, Enum):
    """Supported RPA tools."""

    BLUE_PRISM = "BLUE_PRISM"
    UIPATH = "UIPATH"
    POWER_AUTOMATE = "POWER_AUTOMATE"
    AA360 = "AA360"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        """Return human-readable tool name."""
        display_names = {
            "BLUE_PRISM": "Blue Prism",
            "UIPATH": "UiPath",
            "POWER_AUTOMATE": "Power Automate",
            "AA360": "Automation Anywhere 360",
            "UNKNOWN": "Unknown Tool",
        }
        return display_names.get(self.value, self.value)

    @classmethod
    def from_string(cls, value: str) -> "RPATool":
        """Convert string to RPATool enum, handling aliases.

        Aliases are case-insensitive. Unknown values return UNKNOWN.

        Args:
            value: String to convert (e.g., "bp", "Blue Prism", "blue_prism")

        Returns:
            RPATool enum value, or UNKNOWN if not recognized
        """
        if not isinstance(value, str):
            return cls.UNKNOWN

        lower_value = value.lower().strip()

        # Blue Prism aliases
        if lower_value in ("blue prism", "blueprism", "bp", "blue_prism"):
            return cls.BLUE_PRISM

        # UiPath aliases
        if lower_value in ("uipath", "ui path", "uip"):
            return cls.UIPATH

        # Power Automate aliases
        if lower_value in (
            "power automate",
            "powerautomate",
            "pa",
            "power_automate",
        ):
            return cls.POWER_AUTOMATE

        # AA360 aliases
        if lower_value in ("automation anywhere", "aa360", "aa", "a360"):
            return cls.AA360

        # Unknown
        return cls.UNKNOWN


class AssessmentPhase(str, Enum):
    """Phases of RPA assessment and delivery."""

    DEFINE = "DEFINE"
    BUILD = "BUILD"
    UAT = "UAT"
    DEPLOY = "DEPLOY"

    def __str__(self) -> str:
        """Return human-readable phase name."""
        return self.value

    def order(self) -> int:
        """Return phase order (DEFINE=1 to DEPLOY=4).

        Returns:
            Phase sequence number
        """
        orders = {"DEFINE": 1, "BUILD": 2, "UAT": 3, "DEPLOY": 4}
        return orders[self.value]


class StepWeight(float, Enum):
    """Weight multipliers for RPA steps based on complexity/reusability."""

    ZERO = 0.0
    HALF = 0.5
    ONE = 1.0
    TWO = 2.0

    def __str__(self) -> str:
        """Return human-readable weight description."""
        return str(self.value)

    def description(self) -> str:
        """Return human-readable description of what this weight means.

        Returns:
            Description of the weight's meaning in context
        """
        descriptions = {
            0.0: "Fully reusable — no new development effort",
            0.5: "Partially reusable — minor modification needed",
            1.0: "Standard new step — typical development effort",
            2.0: "Complex step — multi-path logic or significant effort",
        }
        return descriptions.get(self.value, "Unknown weight")

    @classmethod
    def from_float(cls, value: float) -> "StepWeight":
        """Convert float to StepWeight enum.

        Args:
            value: Float value to convert (0.0, 0.5, 1.0, or 2.0)

        Returns:
            StepWeight enum value

        Raises:
            ScoringValidationError: If value is not a valid step weight
        """
        valid_values = {0.0: cls.ZERO, 0.5: cls.HALF, 1.0: cls.ONE, 2.0: cls.TWO}

        if value in valid_values:
            return valid_values[value]

        raise ScoringValidationError(
            f"Invalid step weight: {value}. Must be one of 0.0, 0.5, 1.0, 2.0",
            context={"invalid_value": value, "valid_values": [0.0, 0.5, 1.0, 2.0]},
        )


class ReusabilityTag(str, Enum):
    """Tags indicating step reusability level."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NONE = "NONE"

    def __str__(self) -> str:
        """Return human-readable tag name."""
        return self.value

    def description(self) -> str:
        """Return human-readable description of reusability level.

        Returns:
            Description of what this reusability tag means
        """
        descriptions = {
            "FULL": "Step is reused as-is from another automation",
            "PARTIAL": "Step requires modification for this automation",
            "NONE": "Step is entirely new, no reusability",
        }
        return descriptions.get(self.value, "Unknown reusability tag")
