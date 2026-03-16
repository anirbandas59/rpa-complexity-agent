"""
Data models for delivery timeline and features.

Defines models for delivery features and overall project timelines.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class DeliveryFeature(BaseModel):
    """Represents a feature or task in the delivery timeline."""

    model_config = ConfigDict(frozen=False)

    name: str = Field(..., description="Feature/task description")
    scope: str = Field(default="ORIGINAL", description="Scope category")
    acceptance_status: str = Field(default="APPROVED", description="Approval status")
    start_date: date = Field(..., description="Planned start date")
    end_date: date = Field(..., description="Planned end date")
    hours: float = Field(..., description="Estimated development hours")
    developer: str = Field(..., description="Assigned developer name")
    priority: str = Field(default="MUST", description="Priority level")
    completion_pct: float = Field(
        default=0.0, description="Completion percentage (0.0-1.0)"
    )
    development_status: str = Field(
        default="NOT STARTED", description="Current development status"
    )
    remarks: str | None = Field(default=None, description="Optional notes")

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v: float) -> float:
        """Validate hours is greater than 0.

        Args:
            v: Hours value

        Returns:
            The validated hours

        Raises:
            ValueError: If hours <= 0
        """
        if v <= 0:
            raise ValueError("hours must be greater than 0")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: date, info) -> date:
        """Validate end_date is >= start_date.

        Args:
            v: End date value
            info: Validation context

        Returns:
            The validated end date

        Raises:
            ValueError: If end_date < start_date
        """
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date cannot be before start_date")
        return v

    @field_validator("completion_pct")
    @classmethod
    def validate_completion_pct(cls, v: float) -> float:
        """Validate completion_pct is between 0.0 and 1.0.

        Args:
            v: Completion percentage

        Returns:
            The validated percentage

        Raises:
            ValueError: If percentage is outside [0.0, 1.0]
        """
        if not (0.0 <= v <= 1.0):
            raise ValueError("completion_pct must be between 0.0 and 1.0")
        return v

    @computed_field  # type: ignore[misc]
    @property
    def sp(self) -> float:
        """Compute story points from hours.

        Story points = hours * 0.0666 (1 SP ≈ 15 hours).

        Returns:
            Story points rounded to 2 decimal places
        """
        return round(0.0666 * self.hours, 2)


class DeliveryTimeline(BaseModel):
    """Represents the full delivery timeline for a project."""

    model_config = ConfigDict(frozen=False)

    project_name: str = Field(..., description="Project name")
    squad: str = Field(..., description="Team/squad name")
    business_analyst: str = Field(..., description="BA name")
    developer: str = Field(..., description="Developer name")
    features: list[DeliveryFeature] = Field(
        default_factory=list, description="All tasks/features"
    )

    @computed_field  # type: ignore[misc]
    @property
    def total_hours(self) -> float:
        """Compute total hours across all features.

        Returns:
            Sum of hours from all features
        """
        return sum(feature.hours for feature in self.features)

    @computed_field  # type: ignore[misc]
    @property
    def total_sp(self) -> float:
        """Compute total story points across all features.

        Returns:
            Sum of story points rounded to 2 decimal places
        """
        return round(sum(feature.sp for feature in self.features), 2)

    @computed_field  # type: ignore[misc]
    @property
    def start_date(self) -> date | None:
        """Get earliest start date across all features.

        Returns:
            Earliest start_date, or None if no features
        """
        if not self.features:
            return None
        return min(feature.start_date for feature in self.features)

    @computed_field  # type: ignore[misc]
    @property
    def end_date(self) -> date | None:
        """Get latest end date across all features.

        Returns:
            Latest end_date, or None if no features
        """
        if not self.features:
            return None
        return max(feature.end_date for feature in self.features)

    def completed_count(self) -> int:
        """Count features with development_status == "COMPLETED".

        Returns:
            Number of completed features
        """
        return sum(
            1 for feature in self.features if feature.development_status == "COMPLETED"
        )

    def in_progress_count(self) -> int:
        """Count features with development_status == "IN PROGRESS".

        Returns:
            Number of in-progress features
        """
        return sum(
            1
            for feature in self.features
            if feature.development_status == "IN PROGRESS"
        )
