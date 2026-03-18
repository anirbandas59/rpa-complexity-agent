"""
Effort estimation for RPA automation projects.

This module loads effort data and RPA tool adjustment factors,
then calculates effort estimates based on complexity tier and tool.

Pure Python — no LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from core.constants import AssessmentPhase, ComplexityTier, RPATool
from core.exceptions import ScoringValidationError

# Load effort table and tool factors at module level
_EFFORT_TABLE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "reference" / "effort_table.json"
)
_TOOL_FACTORS_PATH = (
    Path(__file__).parent.parent.parent / "data" / "reference" / "rpa_tool_factors.json"
)

try:
    with open(_EFFORT_TABLE_PATH) as f:
        _EFFORT_DATA: dict[str, Any] = json.load(f)
except FileNotFoundError as e:
    raise ScoringValidationError(
        f"effort_table.json not found at {_EFFORT_TABLE_PATH}. "
        f"Run scripts/seed_reference_data.py first."
    ) from e

try:
    with open(_TOOL_FACTORS_PATH) as f:
        _TOOL_FACTORS_DATA: dict[str, Any] = json.load(f)
except FileNotFoundError as e:
    raise ScoringValidationError(
        f"rpa_tool_factors.json not found at {_TOOL_FACTORS_PATH}. "
        f"Run scripts/seed_reference_data.py first."
    ) from e

# Extract the effort and factors dicts
_EFFORTS: dict[str, dict[str, Any]] = _EFFORT_DATA.get("efforts", {})
_TOOL_FACTORS: dict[str, dict[str, float]] = _TOOL_FACTORS_DATA.get("factors", {})

# Tier to effort key mapping
_TIER_TO_EFFORT_KEY = {
    "XS": "XS",
    "S": "S",
    "M": "M",
    "L": "L",
    "XL": "XL",
}

# Phase order for consistent display
_PHASE_ORDER = [
    AssessmentPhase.DEFINE,
    AssessmentPhase.BUILD,
    AssessmentPhase.UAT,
    AssessmentPhase.DEPLOY,
]


class PhaseEffort(BaseModel):
    """Effort estimate for a single project phase."""

    model_config = ConfigDict(frozen=False)

    phase: AssessmentPhase = Field(..., description="Project phase")
    min_days: int = Field(..., description="Minimum days (range start for S tier)")
    max_days: int = Field(..., description="Maximum days (range end for S tier)")
    is_range: bool = Field(
        default=False, description="True only for S tier (has range)"
    )

    @computed_field  # type: ignore[misc]
    @property
    def days_display(self) -> str:
        """Display effort with range notation if applicable.

        Returns:
            Formatted string like "15 days" or "7–15 days"
        """
        if self.is_range:
            return f"{self.min_days}–{self.max_days} days"
        return f"{self.min_days} days"


class EffortEstimate(BaseModel):
    """Complete effort estimate for an automation project."""

    model_config = ConfigDict(frozen=False)

    complexity_tier: ComplexityTier = Field(..., description="Complexity tier")
    rpa_tool: RPATool = Field(..., description="Target RPA tool")
    phases: list[PhaseEffort] = Field(
        default_factory=list, description="Per-phase effort estimates"
    )
    total_min_days: int = Field(..., description="Minimum total days")
    total_max_days: int = Field(..., description="Maximum total days")
    sprints: int | tuple[int, int] = Field(
        ..., description="Sprint count (int or range tuple)"
    )
    has_surface_automation: bool = Field(
        default=False, description="Uses surface/UI automation"
    )
    has_api_integration: bool = Field(default=False, description="Uses API integration")
    adjustment_applied: bool = Field(
        default=False, description="RPA tool adjustment applied"
    )

    @computed_field  # type: ignore[misc]
    @property
    def total_days_display(self) -> str:
        """Display total effort with range notation if applicable.

        Returns:
            Formatted string like "60 days" or "20–40 days"
        """
        if self.total_min_days == self.total_max_days:
            return f"{self.total_min_days} days"
        return f"{self.total_min_days}–{self.total_max_days} days"

    @computed_field  # type: ignore[misc]
    @property
    def sprint_display(self) -> str:
        """Display sprint count with range notation if applicable.

        Returns:
            Formatted string like "6 sprints" or "2–4 sprints"
        """
        if isinstance(self.sprints, tuple):
            return f"{self.sprints[0]}–{self.sprints[1]} sprints"
        return f"{self.sprints} sprints"


def get_base_effort(tier: ComplexityTier) -> dict[AssessmentPhase, PhaseEffort]:
    """Get base effort for a complexity tier.

    Loads from effort_table.json and returns per-phase efforts.
    For S tier, phases have ranges (is_range=True).
    For all other tiers, phases have fixed values (is_range=False).

    Args:
        tier: The ComplexityTier to get effort for

    Returns:
        Dict mapping AssessmentPhase to PhaseEffort

    Raises:
        ScoringValidationError: If tier not found in effort table
    """
    tier_key = tier.value

    if tier_key not in _EFFORTS:
        raise ScoringValidationError(
            f"Effort data not found for tier: {tier_key}",
            context={"tier": tier_key},
        )

    effort_data = _EFFORTS[tier_key]
    result: dict[AssessmentPhase, PhaseEffort] = {}
    is_range = tier_key == "S"

    for phase in _PHASE_ORDER:
        phase_key = phase.value.lower()

        if phase_key not in effort_data:
            raise ScoringValidationError(
                f"Phase {phase_key} not found in effort data for tier {tier_key}",
                context={"tier": tier_key, "phase": phase_key},
            )

        phase_effort_value = effort_data[phase_key]

        # Handle range values (S tier) vs fixed values (others)
        if isinstance(phase_effort_value, list):
            min_days = phase_effort_value[0]
            max_days = phase_effort_value[1]
        else:
            min_days = phase_effort_value
            max_days = phase_effort_value

        result[phase] = PhaseEffort(
            phase=phase,
            min_days=min_days,
            max_days=max_days,
            is_range=is_range,
        )

    return result


def get_rpa_adjustment_factor(
    rpa_tool: RPATool,
    has_surface_automation: bool = False,
    has_api_integration: bool = False,
) -> float:
    """Get RPA tool adjustment factor.

    Returns a multiplier based on the tool and automation type.
    Surface automation takes precedence if both flags are True.

    Args:
        rpa_tool: The RPA tool to get adjustment for
        has_surface_automation: Whether using surface/UI automation
        has_api_integration: Whether using API integration

    Returns:
        Adjustment factor (float). Never raises — unknown tools return 1.0.
    """
    # Unknown tools have no adjustment
    if rpa_tool == RPATool.UNKNOWN:
        return 1.0

    tool_key = rpa_tool.value.lower()

    # If tool not in factors, return 1.0
    if tool_key not in _TOOL_FACTORS:
        return 1.0

    tool_factors = _TOOL_FACTORS[tool_key]

    # Determine which factor to use (surface > api > default)
    if has_surface_automation:
        return tool_factors.get("surface_automation", 1.0)
    elif has_api_integration:
        return tool_factors.get("api_integration", 1.0)
    else:
        return tool_factors.get("default", 1.0)


def apply_rpa_adjustment(
    base_effort: dict[AssessmentPhase, PhaseEffort],
    factor: float,
) -> dict[AssessmentPhase, PhaseEffort]:
    """Apply RPA adjustment factor to effort estimates.

    If factor == 1.0, returns the input unchanged.
    Otherwise returns a new dict with adjusted values.

    Args:
        base_effort: Dict mapping phases to their efforts
        factor: Multiplier to apply

    Returns:
        New dict with adjusted efforts (or same dict if factor == 1.0)
    """
    if factor == 1.0:
        return base_effort

    result: dict[AssessmentPhase, PhaseEffort] = {}

    for phase, effort in base_effort.items():
        adjusted_min = round(effort.min_days * factor)
        adjusted_max = round(effort.max_days * factor)

        result[phase] = PhaseEffort(
            phase=phase,
            min_days=adjusted_min,
            max_days=adjusted_max,
            is_range=effort.is_range,
        )

    return result


def calculate_effort(
    tier: ComplexityTier,
    rpa_tool: RPATool = RPATool.UNKNOWN,
    has_surface_automation: bool = False,
    has_api_integration: bool = False,
) -> EffortEstimate:
    """Calculate complete effort estimate.

    Main entry point that orchestrates the full calculation pipeline.

    Args:
        tier: Complexity tier
        rpa_tool: RPA platform (default: UNKNOWN)
        has_surface_automation: Whether using surface/UI automation
        has_api_integration: Whether using API integration

    Returns:
        EffortEstimate with all calculations
    """
    # Step 1: Get base effort
    base_effort = get_base_effort(tier)

    # Step 2: Get adjustment factor
    factor = get_rpa_adjustment_factor(
        rpa_tool, has_surface_automation, has_api_integration
    )

    # Step 3: Apply adjustment if needed
    adjusted_effort = (
        apply_rpa_adjustment(base_effort, factor) if factor != 1.0 else base_effort
    )

    # Step 4: Calculate totals
    total_min_days = sum(effort.min_days for effort in adjusted_effort.values())
    total_max_days = sum(effort.max_days for effort in adjusted_effort.values())

    # Step 5: Get sprints from effort table
    tier_key = tier.value
    sprint_value = _EFFORTS[tier_key].get("sprints")

    if isinstance(sprint_value, list):
        sprints: int | tuple[int, int] = tuple(sprint_value)  # type: ignore[assignment]
    else:
        sprints = sprint_value

    # Step 6: Return estimate
    return EffortEstimate(
        complexity_tier=tier,
        rpa_tool=rpa_tool,
        phases=list(adjusted_effort.values()),
        total_min_days=total_min_days,
        total_max_days=total_max_days,
        sprints=sprints,
        has_surface_automation=has_surface_automation,
        has_api_integration=has_api_integration,
        adjustment_applied=factor != 1.0,
    )


def get_effort_summary(estimate: EffortEstimate) -> str:
    """Generate a formatted effort estimate summary.

    Args:
        estimate: The EffortEstimate to summarize

    Returns:
        Multi-line formatted string
    """
    lines = [
        f"Effort Estimate — {estimate.complexity_tier} ({estimate.rpa_tool})",
        "────────────────────────────────────",
    ]

    # Add phase efforts
    for effort in estimate.phases:
        phase_name = effort.phase.value
        lines.append(f"{phase_name:15}{effort.days_display}")

    lines.append("────────────────────────────────────")
    lines.append(f"Total:         {estimate.total_days_display}")
    lines.append(f"Sprints:       {estimate.sprint_display}")

    # Add adjustment note if applied
    if estimate.adjustment_applied:
        factor = get_rpa_adjustment_factor(
            estimate.rpa_tool,
            estimate.has_surface_automation,
            estimate.has_api_integration,
        )
        lines.append(f"* RPA tool adjustment applied ({factor}x)")

    return "\n".join(lines)
