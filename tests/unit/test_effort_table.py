"""
Tests for the effort table and effort estimation module.

Comprehensive tests for effort loading, RPA adjustments,
and complete effort calculations.
"""

from core.constants import AssessmentPhase, ComplexityTier, RPATool
from core.scoring.effort_table import (
    PhaseEffort,
    apply_rpa_adjustment,
    calculate_effort,
    get_base_effort,
    get_effort_summary,
    get_rpa_adjustment_factor,
)


class TestGetBaseEffort:
    """Tests for get_base_effort function."""

    def test_get_base_effort_xs(self):
        """Verify XS tier effort loads correctly."""
        effort = get_base_effort(ComplexityTier.XS)
        assert len(effort) == 4  # 4 phases
        total = sum(e.min_days for e in effort.values())
        assert total == 10

    def test_get_base_effort_s_has_ranges(self):
        """Verify S tier has range values."""
        effort = get_base_effort(ComplexityTier.S)
        for phase_effort in effort.values():
            assert phase_effort.is_range is True
            assert phase_effort.min_days < phase_effort.max_days

    def test_get_base_effort_m(self):
        """Verify M tier effort loads correctly."""
        effort = get_base_effort(ComplexityTier.M)
        total = sum(e.min_days for e in effort.values())
        assert total == 50
        # Define phase should be 15
        assert effort[AssessmentPhase.DEFINE].min_days == 15

    def test_get_base_effort_l(self):
        """Verify L tier effort loads correctly."""
        effort = get_base_effort(ComplexityTier.L)
        total = sum(e.min_days for e in effort.values())
        assert total == 60

    def test_get_base_effort_xl(self):
        """Verify XL tier effort loads correctly."""
        effort = get_base_effort(ComplexityTier.XL)
        total = sum(e.min_days for e in effort.values())
        assert total == 80
        # Build phase should be 40
        assert effort[AssessmentPhase.BUILD].min_days == 40

    def test_get_base_effort_non_range_tiers(self):
        """Verify non-S tiers have fixed values (is_range=False)."""
        for tier in [
            ComplexityTier.XS,
            ComplexityTier.M,
            ComplexityTier.L,
            ComplexityTier.XL,
        ]:
            effort = get_base_effort(tier)
            for phase_effort in effort.values():
                assert phase_effort.is_range is False
                assert phase_effort.min_days == phase_effort.max_days


class TestGetRpaAdjustmentFactor:
    """Tests for get_rpa_adjustment_factor function."""

    def test_unknown_tool_returns_1_0(self):
        """Verify UNKNOWN tool returns no adjustment."""
        assert get_rpa_adjustment_factor(RPATool.UNKNOWN) == 1.0
        assert get_rpa_adjustment_factor(RPATool.UNKNOWN, True, False) == 1.0
        assert get_rpa_adjustment_factor(RPATool.UNKNOWN, False, True) == 1.0

    def test_blue_prism_surface_automation(self):
        """Verify Blue Prism surface automation factor."""
        assert (
            get_rpa_adjustment_factor(RPATool.BLUE_PRISM, has_surface_automation=True)
            == 1.3
        )

    def test_blue_prism_api_integration(self):
        """Verify Blue Prism API integration factor."""
        assert (
            get_rpa_adjustment_factor(RPATool.BLUE_PRISM, has_api_integration=True)
            == 1.1
        )

    def test_blue_prism_default(self):
        """Verify Blue Prism default factor."""
        assert get_rpa_adjustment_factor(RPATool.BLUE_PRISM) == 1.0

    def test_uipath_surface_automation(self):
        """Verify UiPath surface automation factor."""
        assert (
            get_rpa_adjustment_factor(RPATool.UIPATH, has_surface_automation=True)
            == 1.1
        )

    def test_uipath_api_integration(self):
        """Verify UiPath API integration factor."""
        assert (
            get_rpa_adjustment_factor(RPATool.UIPATH, has_api_integration=True) == 1.0
        )

    def test_power_automate_surface_automation(self):
        """Verify Power Automate surface automation factor."""
        assert (
            get_rpa_adjustment_factor(
                RPATool.POWER_AUTOMATE, has_surface_automation=True
            )
            == 1.4
        )

    def test_power_automate_api_integration(self):
        """Verify Power Automate API integration factor."""
        assert (
            get_rpa_adjustment_factor(RPATool.POWER_AUTOMATE, has_api_integration=True)
            == 0.9
        )

    def test_aa360_surface_automation(self):
        """Verify AA360 surface automation factor."""
        assert (
            get_rpa_adjustment_factor(RPATool.AA360, has_surface_automation=True) == 1.2
        )

    def test_aa360_api_integration(self):
        """Verify AA360 API integration factor."""
        assert get_rpa_adjustment_factor(RPATool.AA360, has_api_integration=True) == 1.1

    def test_surface_takes_precedence_over_api(self):
        """Verify surface automation is used when both flags are True."""
        # Blue Prism: surface=1.3, api=1.1
        assert (
            get_rpa_adjustment_factor(
                RPATool.BLUE_PRISM,
                has_surface_automation=True,
                has_api_integration=True,
            )
            == 1.3
        )


class TestApplyRpaAdjustment:
    """Tests for apply_rpa_adjustment function."""

    def test_factor_1_0_returns_same_object(self):
        """Verify factor 1.0 returns the same object."""
        base = get_base_effort(ComplexityTier.L)
        adjusted = apply_rpa_adjustment(base, 1.0)
        assert adjusted is base

    def test_factor_1_3_on_l_tier_build(self):
        """Verify 1.3x adjustment on L tier Build phase (30 → 39)."""
        base = get_base_effort(ComplexityTier.L)
        adjusted = apply_rpa_adjustment(base, 1.3)

        # Build phase in L tier is 30 days
        assert adjusted[AssessmentPhase.BUILD].min_days == round(30 * 1.3)
        assert adjusted[AssessmentPhase.BUILD].min_days == 39

    def test_factor_0_9_on_m_tier_define(self):
        """Verify 0.9x adjustment on M tier Define phase (15 → 14)."""
        base = get_base_effort(ComplexityTier.M)
        adjusted = apply_rpa_adjustment(base, 0.9)

        # Define phase in M tier is 15 days
        assert adjusted[AssessmentPhase.DEFINE].min_days == round(15 * 0.9)
        assert adjusted[AssessmentPhase.DEFINE].min_days == 14

    def test_adjustment_returns_new_dict(self):
        """Verify adjustment returns a new dict (not the original)."""
        base = get_base_effort(ComplexityTier.L)
        adjusted = apply_rpa_adjustment(base, 1.2)

        # Should be different objects
        assert adjusted is not base
        # Original should be unchanged
        assert base[AssessmentPhase.BUILD].min_days == 30
        # Adjusted should be different
        assert adjusted[AssessmentPhase.BUILD].min_days == round(30 * 1.2)


class TestCalculateEffort:
    """Tests for calculate_effort function."""

    def test_l_tier_no_adjustment(self):
        """Verify L tier with no tool gives 60 days."""
        estimate = calculate_effort(ComplexityTier.L)
        assert estimate.total_min_days == 60
        assert estimate.total_max_days == 60
        assert estimate.adjustment_applied is False

    def test_l_tier_blue_prism_surface(self):
        """Verify L tier with Blue Prism surface automation > 60 days."""
        estimate = calculate_effort(
            ComplexityTier.L,
            rpa_tool=RPATool.BLUE_PRISM,
            has_surface_automation=True,
        )
        assert estimate.total_min_days > 60
        assert estimate.adjustment_applied is True
        assert estimate.has_surface_automation is True

    def test_s_tier_has_sprint_range(self):
        """Verify S tier sprints is a tuple."""
        estimate = calculate_effort(ComplexityTier.S)
        assert isinstance(estimate.sprints, tuple)
        assert len(estimate.sprints) == 2

    def test_xs_tier_fixed_sprints(self):
        """Verify XS tier sprints is int (1)."""
        estimate = calculate_effort(ComplexityTier.XS)
        assert isinstance(estimate.sprints, int)
        assert estimate.sprints == 1

    def test_xl_tier_effort(self):
        """Verify XL tier has 80 days and 8 sprints."""
        estimate = calculate_effort(ComplexityTier.XL)
        assert estimate.total_min_days == 80
        assert estimate.total_max_days == 80
        assert estimate.sprints == 8

    def test_calculate_effort_has_all_phases(self):
        """Verify calculated effort includes all 4 phases."""
        estimate = calculate_effort(ComplexityTier.M)
        assert len(estimate.phases) == 4
        phase_set = {p.phase for p in estimate.phases}
        assert phase_set == {
            AssessmentPhase.DEFINE,
            AssessmentPhase.BUILD,
            AssessmentPhase.UAT,
            AssessmentPhase.DEPLOY,
        }

    def test_m_tier_50_days(self):
        """Verify M tier has 50 total days."""
        estimate = calculate_effort(ComplexityTier.M)
        assert estimate.total_min_days == 50
        assert estimate.total_max_days == 50


class TestPhaseEffort:
    """Tests for PhaseEffort model."""

    def test_phase_effort_fixed_value(self):
        """Verify fixed phase displays correctly."""
        phase = PhaseEffort(
            phase=AssessmentPhase.DEFINE,
            min_days=15,
            max_days=15,
            is_range=False,
        )
        assert phase.days_display == "15 days"

    def test_phase_effort_range_value(self):
        """Verify range phase displays correctly."""
        phase = PhaseEffort(
            phase=AssessmentPhase.DEFINE,
            min_days=7,
            max_days=15,
            is_range=True,
        )
        assert phase.days_display == "7–15 days"


class TestEffortEstimate:
    """Tests for EffortEstimate model."""

    def test_effort_estimate_total_days_fixed(self):
        """Verify fixed total days display."""
        estimate = calculate_effort(ComplexityTier.L)
        assert estimate.total_days_display == "60 days"

    def test_effort_estimate_total_days_range(self):
        """Verify range total days display."""
        estimate = calculate_effort(ComplexityTier.S)
        assert "–" in estimate.total_days_display
        assert "days" in estimate.total_days_display

    def test_effort_estimate_sprint_display_fixed(self):
        """Verify fixed sprint display."""
        estimate = calculate_effort(ComplexityTier.XL)
        assert estimate.sprint_display == "8 sprints"

    def test_effort_estimate_sprint_display_range(self):
        """Verify range sprint display."""
        estimate = calculate_effort(ComplexityTier.S)
        assert "–" in estimate.sprint_display
        assert "sprints" in estimate.sprint_display


class TestGetEffortSummary:
    """Tests for get_effort_summary function."""

    def test_summary_returns_string(self):
        """Verify summary returns non-empty string."""
        estimate = calculate_effort(ComplexityTier.L)
        summary = get_effort_summary(estimate)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_summary_contains_tier(self):
        """Verify summary contains tier name."""
        estimate = calculate_effort(ComplexityTier.L)
        summary = get_effort_summary(estimate)
        assert "L" in summary

    def test_summary_contains_tool(self):
        """Verify summary contains tool name."""
        estimate = calculate_effort(ComplexityTier.M, rpa_tool=RPATool.BLUE_PRISM)
        summary = get_effort_summary(estimate)
        assert "Blue Prism" in summary

    def test_summary_contains_total(self):
        """Verify summary contains total effort."""
        estimate = calculate_effort(ComplexityTier.L)
        summary = get_effort_summary(estimate)
        assert "Total:" in summary

    def test_summary_contains_sprints(self):
        """Verify summary contains sprint estimate."""
        estimate = calculate_effort(ComplexityTier.L)
        summary = get_effort_summary(estimate)
        assert "Sprints:" in summary

    def test_summary_contains_adjustment_note(self):
        """Verify summary mentions adjustment when applied."""
        estimate = calculate_effort(
            ComplexityTier.L,
            rpa_tool=RPATool.BLUE_PRISM,
            has_surface_automation=True,
        )
        summary = get_effort_summary(estimate)
        assert "adjustment applied" in summary
        assert "1.3x" in summary

    def test_summary_no_adjustment_note_when_not_applied(self):
        """Verify summary omits adjustment note when not applied."""
        estimate = calculate_effort(ComplexityTier.L)
        summary = get_effort_summary(estimate)
        assert "adjustment applied" not in summary

    def test_summary_multiline(self):
        """Verify summary is multi-line."""
        estimate = calculate_effort(ComplexityTier.L)
        summary = get_effort_summary(estimate)
        assert "\n" in summary


class TestGroundTruthEffort:
    """Ground truth test from the actual Excel domain knowledge."""

    def test_ground_truth_effort(self):
        """Test the exact ground truth effort scenario.

        The known project in the Excel was classified as L tier.
        Developer: single developer.
        Applications: GMP + Excel (2 interfaces, no surface automation,
        no API integration).
        """
        estimate = calculate_effort(
            ComplexityTier.L,
            rpa_tool=RPATool.UNKNOWN,
            has_surface_automation=False,
            has_api_integration=False,
        )

        # Assertions from acceptance criteria
        assert estimate.total_min_days == 60, "L tier should have 60 min days"
        assert estimate.total_max_days == 60, "L tier should have 60 max days"
        assert estimate.sprint_display == "6 sprints", "L tier should have 6 sprints"
        assert estimate.adjustment_applied is False, "No tool adjustment applied"

        # Verify all phases present
        assert len(estimate.phases) == 4, "Should have 4 phases"

        # Verify tier and tool
        assert estimate.complexity_tier == ComplexityTier.L
        assert estimate.rpa_tool == RPATool.UNKNOWN
