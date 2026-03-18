"""
Data models for RPA process design and structure.

Defines models for process steps, business rules, layouts, and interfaces.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.constants import ReusabilityTag, StepWeight


class ProcessStep(BaseModel):
    """Represents a single step in an RPA process."""

    model_config = ConfigDict(frozen=False)

    step_number: int = Field(..., description="Sequential step number (1-based)")
    description: str = Field(..., description="Human-readable step description")
    weight: StepWeight = Field(..., description="Development effort weight")
    reusability_tag: ReusabilityTag = Field(
        ..., description="Reusability classification"
    )
    branch_name: str = Field(
        ..., description="Business rule branch this step belongs to"
    )
    reusability_comment: str = Field(
        ..., description="Explanation of why this reusability was assigned"
    )

    @field_validator("step_number")
    @classmethod
    def validate_step_number(cls, v: int) -> int:
        """Validate step_number is >= 1.

        Args:
            v: Step number value

        Returns:
            The validated step number

        Raises:
            ValueError: If step_number < 1
        """
        if v < 1:
            raise ValueError("step_number must be >= 1")
        return v


class BusinessRule(BaseModel):
    """Represents a business rule in the RPA process."""

    model_config = ConfigDict(frozen=False)

    description: str = Field(..., description="What the rule checks or decides")
    creates_new_flow: bool = Field(
        ..., description="True if rule spawns additional process flow"
    )
    branch_activity_count: int = Field(
        ..., description="Estimated activities in the resulting branch"
    )
    branch_name: str = Field(..., description="Name of the branch this rule creates")

    @field_validator("branch_activity_count")
    @classmethod
    def validate_branch_activity_count(cls, v: int, info) -> int:
        """Validate branch_activity_count when creates_new_flow is True.

        Flow-creating rules must have more than 2 activities.

        Args:
            v: Branch activity count
            info: Validation context

        Returns:
            The validated activity count

        Raises:
            ValueError: If creates_new_flow is True but activity count <= 2
        """
        # Check if creates_new_flow is in the data being validated
        if info.data.get("creates_new_flow") is True and v <= 2:
            raise ValueError(
                "Flow-creating rules must have more than 2 branch activities"
            )
        return v


class DigitalLayout(BaseModel):
    """Represents a digital layout/file template used in RPA."""

    model_config = ConfigDict(frozen=False)

    name: str = Field(..., description="Descriptive name of the layout")
    file_extension: str = Field(
        ..., description='File extension (e.g. "xlsx", "pdf", "csv", "xml")'
    )
    is_input: bool = Field(..., description="True if RPA reads this layout")
    is_output: bool = Field(..., description="True if RPA writes this layout")
    template_type: str = Field(
        ...,
        description='Type of template: "input_template", "output_report", "schema_file", "config_file"',
    )

    @model_validator(mode="after")
    def validate_input_output(self) -> DigitalLayout:
        """Validate at least one of is_input or is_output is True.

        Raises:
            ValueError: If both is_input and is_output are False
        """
        if not self.is_input and not self.is_output:
            raise ValueError("Layout must be either input, output, or both")
        return self


class TargetInterface(BaseModel):
    """Represents a target application or system interface."""

    model_config = ConfigDict(frozen=False)

    name: str = Field(..., description="Application or system name")
    interface_type: str = Field(
        ...,
        description='Type of interface: "web", "desktop", "api", "database", "file_system", "email"',
    )
    automation_method: str = Field(
        ...,
        description='Method: "ui_automation", "api_call", "file_read_write", "email_trigger"',
    )
