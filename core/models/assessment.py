"""
Data models for complexity assessment and scoring.

Defines models for assessment inputs, results, and scoring details.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from core.constants import ComplexityTier, RPATool


class AttributeScore(BaseModel):
    """Represents a single attribute score in the assessment."""

    model_config = ConfigDict(frozen=False)

    attribute_id: int = Field(
        ..., description="Attribute ID must be 1-5 inclusive"
    )
    attribute_name: str = Field(..., description="Human-readable attribute name")
    raw_value: int = Field(
        ..., description="Actual count extracted from the PDD"
    )
    selected_tier: ComplexityTier = Field(
        ..., description="Tier this raw value maps to"
    )
    weight: int = Field(
        ..., description="Point weight for this tier"
    )
    tier_rationale: str = Field(
        ..., description="Explanation of why this tier was selected"
    )

    @field_validator("attribute_id")
    @classmethod
    def validate_attribute_id(cls, v: int) -> int:
        """Validate attribute_id is between 1 and 5.

        Args:
            v: Attribute ID value

        Returns:
            The validated attribute ID

        Raises:
            ValueError: If attribute_id is not in [1, 5]
        """
        if not (1 <= v <= 5):
            raise ValueError("attribute_id must be between 1 and 5")
        return v

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, v: int) -> int:
        """Validate weight is non-negative.

        Args:
            v: Weight value

        Returns:
            The validated weight

        Raises:
            ValueError: If weight is negative
        """
        if v < 0:
            raise ValueError("weight cannot be negative")
        return v


class AssessmentInput(BaseModel):
    """Represents input parameters for an assessment."""

    model_config = ConfigDict(frozen=False)

    file_path: str = Field(..., description="Path to the PDD file")
    rpa_tool: RPATool = Field(..., description="Target RPA platform")
    project_name: str = Field(..., description="Name of automation project")
    assessor_name: str = Field(..., description="Name of assessor")
    start_date: date = Field(..., description="Planned project start date")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """Validate file_path is not empty.

        Args:
            v: File path value

        Returns:
            The validated file path

        Raises:
            ValueError: If file_path is empty
        """
        if not v or v.strip() == "":
            raise ValueError("file_path cannot be empty")
        return v


class AssessmentResult(BaseModel):
    """Represents the final assessment result."""

    model_config = ConfigDict(frozen=False)

    session_id: str = Field(..., description="UUID for this assessment run")
    project_name: str = Field(..., description="Name of automation project")
    rpa_tool: RPATool = Field(..., description="Target RPA platform")
    attribute_scores: list[AttributeScore] = Field(
        default_factory=list, description="All 5 attribute scores"
    )
    total_score: int = Field(..., description="Sum of all attribute weights")
    complexity_tier: ComplexityTier = Field(
        ..., description="Final XS/S/M/L/XL classification"
    )
    confidence_score: float = Field(
        ..., description="Confidence 0.0-1.0 in the result"
    )
    reasoning: str = Field(..., description="Narrative explanation of result")
    requires_tech_lead_review: bool = Field(
        default=False, description="True if XL or score > 25"
    )
    created_at: datetime = Field(..., description="Timestamp of assessment")

    @field_validator("total_score")
    @classmethod
    def validate_total_score(cls, v: int) -> int:
        """Validate total_score is between 0 and 28 inclusive.

        Args:
            v: Total score value

        Returns:
            The validated total score

        Raises:
            ValueError: If score is outside [0, 28]
        """
        if not (0 <= v <= 28):
            raise ValueError("total_score must be between 0 and 28")
        return v

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence_score(cls, v: float) -> float:
        """Validate confidence_score is between 0.0 and 1.0.

        Args:
            v: Confidence score value

        Returns:
            The validated confidence score

        Raises:
            ValueError: If score is outside [0.0, 1.0]
        """
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        return v

    @computed_field  # type: ignore[misc]
    @property
    def score_summary(self) -> str:
        """Generate a formatted summary of the assessment scores.

        Returns:
            Multi-line formatted table of attribute scores and totals,
            or "No scores available." if no attributes are scored
        """
        if not self.attribute_scores:
            return "No scores available."

        # Build the summary table
        lines = [
            "┌─────────────────────────────────────────┐",
            "│  Attribute              Tier    Weight  │",
        ]

        # Add each attribute score
        for score in self.attribute_scores:
            # Format: "  #{id} {name:<20} {tier:>3} {weight:>5}  │"
            attr_label = f"#{score.attribute_id} {score.attribute_name}"
            tier_str = str(score.selected_tier)
            weight_str = str(score.weight)

            # Pad attribute name to 22 chars
            attr_padded = attr_label.ljust(22)
            # Pad tier to 3 chars (right-aligned)
            tier_padded = tier_str.rjust(3)
            # Pad weight to 5 chars (right-aligned)
            weight_padded = weight_str.rjust(5)

            line = f"│  {attr_padded} {tier_padded}    {weight_padded}  │"
            lines.append(line)

        # Add separator and total
        lines.append("│  ─────────────────────────────────────  │")

        total_line = f"│  Total Score: {self.total_score:<2}        Tier: {str(self.complexity_tier):<2}         │"
        lines.append(total_line)

        lines.append("└─────────────────────────────────────────┘")

        return "\n".join(lines)
