"""
Delivery timeline builder for RPA projects.

Builds delivery timeline from step decomposition using deterministic
calculations. Maps steps to features with effort estimation and
scheduling.

No LLM involvement — fully deterministic.
"""

from __future__ import annotations

from datetime import date, timedelta

from config.logging_config import get_logger
from core.models.assessment import AssessmentResult
from core.models.timeline import DeliveryFeature, DeliveryTimeline
from tools.output.step_decomposer import BranchData, StepDecompositionResult

logger = get_logger("timeline_builder")

# ===========================================================================
# CONSTANTS
# ===========================================================================

SP_CONVERSION_RATE = 0.0666  # 1 hour = 0.0666 SP
HOURS_PER_WORKING_DAY = 9  # 9-hour working days

STEP_WEIGHT_TO_HOURS: dict[float, float] = {
    0.0: 0,  # Reused — no hours
    0.5: 4.5,  # Half day
    1.0: 9.0,  # One full day
    2.0: 18.0,  # Two full days
}

# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================


def _weight_to_hours(weight: float) -> float:
    """Convert step weight to development hours.

    Args:
        weight: Step weight (0.0, 0.5, 1.0, or 2.0)

    Returns:
        Hours, defaulting to 9.0 if weight not recognized
    """
    return STEP_WEIGHT_TO_HOURS.get(weight, 9.0)


def _calculate_feature_hours(branch: BranchData) -> float:
    """Calculate total hours for a branch.

    Args:
        branch: Branch with steps

    Returns:
        Sum of hours for all steps in branch
    """
    return sum(_weight_to_hours(step.weight) for step in branch.steps)


def _next_working_day(current: date) -> date:
    """Get next working day, skipping weekends.

    Monday=0, Sunday=6

    Args:
        current: Current date

    Returns:
        Next working day (skips Saturday/Sunday)
    """
    next_date = current + timedelta(days=1)
    weekday = next_date.weekday()

    # Skip Saturday (5) and Sunday (6)
    if weekday == 5:  # Saturday
        return next_date + timedelta(days=2)
    elif weekday == 6:  # Sunday
        return next_date + timedelta(days=1)

    return next_date


# ===========================================================================
# MAIN TIMELINE BUILDER
# ===========================================================================


def build_timeline(
    decomposition: StepDecompositionResult,
    assessment_result: AssessmentResult,
    start_date: date,
    developer_name: str = "TBD",
    business_analyst: str = "TBD",
    squad: str = "RPA Team",
) -> DeliveryTimeline:
    """Build delivery timeline from step decomposition.

    Maps each branch to a DeliveryFeature with effort estimation
    and sequential scheduling.

    Args:
        decomposition: Step decomposition result
        assessment_result: Assessment result with project info
        start_date: Project start date
        developer_name: Developer assigned (default "TBD")
        business_analyst: BA assigned (default "TBD")
        squad: Team/squad name (default "RPA Team")

    Returns:
        DeliveryTimeline with features and schedule
    """
    features: list[DeliveryFeature] = []
    current_start = start_date

    for branch in decomposition.branches:
        # Calculate hours and story points
        hours = _calculate_feature_hours(branch)
        if hours == 0:
            hours = 9.0  # Minimum 1 day per feature

        # Calculate working days needed
        working_days_needed = max(1, round(hours / HOURS_PER_WORKING_DAY))

        # Calculate end date by advancing working days
        feature_end = current_start
        for _ in range(working_days_needed - 1):
            feature_end = _next_working_day(feature_end)

        # Create feature
        feature = DeliveryFeature(
            name=branch.branch_name,
            scope="ORIGINAL",
            acceptance_status="APPROVED",
            start_date=current_start,
            end_date=feature_end,
            hours=hours,
            developer=developer_name,
            priority="MUST",
            completion_pct=0.0,
            development_status="NOT STARTED",
            remarks=branch.description if branch.description else None,
        )
        features.append(feature)

        # Next feature starts day after this one ends
        current_start = _next_working_day(feature_end)

    # Return timeline
    return DeliveryTimeline(
        project_name=assessment_result.project_name,
        squad=squad,
        business_analyst=business_analyst,
        developer=developer_name,
        features=features,
    )


# ===========================================================================
# SUMMARY FORMATTER
# ===========================================================================


def get_timeline_summary(timeline: DeliveryTimeline) -> str:
    """Format timeline as human-readable summary.

    Args:
        timeline: Delivery timeline

    Returns:
        Multi-line formatted summary
    """
    lines = [
        f"Delivery Timeline — {timeline.project_name}",
        "─" * 50,
        f"Squad:       {timeline.squad}",
        f"Developer:   {timeline.developer}",
        f"BA:          {timeline.business_analyst}",
    ]

    if timeline.start_date:
        lines.append(f"Start Date:  {timeline.start_date}")
    if timeline.end_date:
        lines.append(f"End Date:    {timeline.end_date}")

    lines.extend(
        [
            "─" * 50,
            f"Total Features: {len(timeline.features)}",
            f"Total Hours:    {timeline.total_hours:.0f}",
            f"Total SP:       {timeline.total_sp:.2f}",
        ]
    )

    if timeline.start_date and timeline.end_date:
        duration_days = (timeline.end_date - timeline.start_date).days
        lines.append(f"Duration:       {duration_days} calendar days")

    lines.extend(["─" * 50, "Features:"])

    for feature in timeline.features:
        lines.append(
            f"  {feature.name}: {feature.hours:.0f}h / {feature.sp}SP "
            f"({feature.start_date} → {feature.end_date})"
        )

    return "\n".join(lines)
