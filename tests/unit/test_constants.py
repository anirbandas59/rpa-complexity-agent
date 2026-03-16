"""
Tests for core constants and enums.

Verifies that all enums are properly defined with expected values,
methods, and behavior.
"""

import pytest

from core.constants import (
    AssessmentPhase,
    ComplexityTier,
    ReusabilityTag,
    RPATool,
    StepWeight,
)
from core.exceptions import ScoringValidationError


class TestComplexityTier:
    """Tests for ComplexityTier enum."""

    def test_all_tiers_exist(self):
        """Verify all tiers are defined."""
        expected = {"XS", "S", "M", "L", "XL"}
        actual = {tier.value for tier in ComplexityTier}
        assert actual == expected

    def test_tier_str_representation(self):
        """Verify str() returns human-readable tier name."""
        assert str(ComplexityTier.XS) == "XS"
        assert str(ComplexityTier.L) == "L"
        assert str(ComplexityTier.XL) == "XL"

    def test_numeric_rank(self):
        """Verify numeric ranks are correct."""
        assert ComplexityTier.XS.numeric_rank() == 1
        assert ComplexityTier.S.numeric_rank() == 2
        assert ComplexityTier.M.numeric_rank() == 3
        assert ComplexityTier.L.numeric_rank() == 4
        assert ComplexityTier.XL.numeric_rank() == 5

    def test_is_above_true(self):
        """Verify is_above returns True for higher tiers."""
        assert ComplexityTier.XL.is_above(ComplexityTier.L)
        assert ComplexityTier.L.is_above(ComplexityTier.M)
        assert ComplexityTier.M.is_above(ComplexityTier.S)
        assert ComplexityTier.S.is_above(ComplexityTier.XS)

    def test_is_above_false(self):
        """Verify is_above returns False for lower or equal tiers."""
        assert not ComplexityTier.S.is_above(ComplexityTier.M)
        assert not ComplexityTier.XS.is_above(ComplexityTier.L)
        assert not ComplexityTier.L.is_above(ComplexityTier.L)

    def test_min_score(self):
        """Verify min_score returns correct thresholds."""
        assert ComplexityTier.XS.min_score() == 0
        assert ComplexityTier.S.min_score() == 7
        assert ComplexityTier.M.min_score() == 9
        assert ComplexityTier.L.min_score() == 16
        assert ComplexityTier.XL.min_score() == 23

    def test_max_score(self):
        """Verify max_score returns correct thresholds."""
        assert ComplexityTier.XS.max_score() == 6
        assert ComplexityTier.S.max_score() == 8
        assert ComplexityTier.M.max_score() == 15
        assert ComplexityTier.L.max_score() == 22
        assert ComplexityTier.XL.max_score() == 28


class TestRPATool:
    """Tests for RPATool enum."""

    def test_all_tools_exist(self):
        """Verify all tools are defined."""
        expected = {"BLUE_PRISM", "UIPATH", "POWER_AUTOMATE", "AA360", "UNKNOWN"}
        actual = {tool.value for tool in RPATool}
        assert actual == expected

    def test_tool_str_representation(self):
        """Verify str() returns human-readable tool name."""
        assert str(RPATool.BLUE_PRISM) == "Blue Prism"
        assert str(RPATool.UIPATH) == "UiPath"
        assert str(RPATool.POWER_AUTOMATE) == "Power Automate"
        assert str(RPATool.AA360) == "Automation Anywhere 360"

    def test_from_string_blue_prism_aliases(self):
        """Verify Blue Prism aliases."""
        aliases = ["blue prism", "blueprism", "bp", "blue_prism", "BLUE PRISM", "BP"]
        for alias in aliases:
            assert RPATool.from_string(alias) == RPATool.BLUE_PRISM

    def test_from_string_uipath_aliases(self):
        """Verify UiPath aliases."""
        aliases = ["uipath", "ui path", "uip", "UIPATH", "UI PATH"]
        for alias in aliases:
            assert RPATool.from_string(alias) == RPATool.UIPATH

    def test_from_string_power_automate_aliases(self):
        """Verify Power Automate aliases."""
        aliases = [
            "power automate",
            "powerautomate",
            "pa",
            "power_automate",
            "POWER AUTOMATE",
            "PA",
        ]
        for alias in aliases:
            assert RPATool.from_string(alias) == RPATool.POWER_AUTOMATE

    def test_from_string_aa360_aliases(self):
        """Verify AA360 aliases."""
        aliases = ["automation anywhere", "aa360", "aa", "a360", "AA360"]
        for alias in aliases:
            assert RPATool.from_string(alias) == RPATool.AA360

    def test_from_string_unknown(self):
        """Verify unknown tools return UNKNOWN."""
        assert RPATool.from_string("unknown_tool") == RPATool.UNKNOWN
        assert RPATool.from_string("some random tool") == RPATool.UNKNOWN
        assert RPATool.from_string("") == RPATool.UNKNOWN

    def test_from_string_non_string_input(self):
        """Verify non-string input returns UNKNOWN."""
        assert RPATool.from_string(123) == RPATool.UNKNOWN
        assert RPATool.from_string(None) == RPATool.UNKNOWN

    def test_from_string_case_insensitive(self):
        """Verify from_string is case-insensitive."""
        assert RPATool.from_string("Blue Prism") == RPATool.BLUE_PRISM
        assert RPATool.from_string("BLUE PRISM") == RPATool.BLUE_PRISM
        assert RPATool.from_string("BluE PriSm") == RPATool.BLUE_PRISM


class TestAssessmentPhase:
    """Tests for AssessmentPhase enum."""

    def test_all_phases_exist(self):
        """Verify all phases are defined."""
        expected = {"DEFINE", "BUILD", "UAT", "DEPLOY"}
        actual = {phase.value for phase in AssessmentPhase}
        assert actual == expected

    def test_phase_str_representation(self):
        """Verify str() returns human-readable phase name."""
        assert str(AssessmentPhase.DEFINE) == "DEFINE"
        assert str(AssessmentPhase.BUILD) == "BUILD"
        assert str(AssessmentPhase.UAT) == "UAT"
        assert str(AssessmentPhase.DEPLOY) == "DEPLOY"

    def test_order(self):
        """Verify phase order is correct."""
        assert AssessmentPhase.DEFINE.order() == 1
        assert AssessmentPhase.BUILD.order() == 2
        assert AssessmentPhase.UAT.order() == 3
        assert AssessmentPhase.DEPLOY.order() == 4


class TestStepWeight:
    """Tests for StepWeight enum."""

    def test_all_weights_exist(self):
        """Verify all weights are defined."""
        expected = {0.0, 0.5, 1.0, 2.0}
        actual = {weight.value for weight in StepWeight}
        assert actual == expected

    def test_weight_str_representation(self):
        """Verify str() returns the numeric value."""
        assert str(StepWeight.ZERO) == "0.0"
        assert str(StepWeight.HALF) == "0.5"
        assert str(StepWeight.ONE) == "1.0"
        assert str(StepWeight.TWO) == "2.0"

    def test_description(self):
        """Verify description() returns appropriate text."""
        assert "Fully reusable" in StepWeight.ZERO.description()
        assert "Partially reusable" in StepWeight.HALF.description()
        assert "Standard new step" in StepWeight.ONE.description()
        assert "Complex step" in StepWeight.TWO.description()

    def test_from_float_valid_values(self):
        """Verify from_float works for valid values."""
        assert StepWeight.from_float(0.0) == StepWeight.ZERO
        assert StepWeight.from_float(0.5) == StepWeight.HALF
        assert StepWeight.from_float(1.0) == StepWeight.ONE
        assert StepWeight.from_float(2.0) == StepWeight.TWO

    def test_from_float_invalid_values(self):
        """Verify from_float raises for invalid values."""
        with pytest.raises(ScoringValidationError):
            StepWeight.from_float(0.25)

        with pytest.raises(ScoringValidationError):
            StepWeight.from_float(1.5)

        with pytest.raises(ScoringValidationError):
            StepWeight.from_float(99.0)

    def test_from_float_error_message(self):
        """Verify from_float error includes helpful context."""
        with pytest.raises(ScoringValidationError) as exc_info:
            StepWeight.from_float(99.0)

        error = exc_info.value
        assert "99.0" in str(error)
        assert "Invalid step weight" in str(error)


class TestReusabilityTag:
    """Tests for ReusabilityTag enum."""

    def test_all_tags_exist(self):
        """Verify all tags are defined."""
        expected = {"FULL", "PARTIAL", "NONE"}
        actual = {tag.value for tag in ReusabilityTag}
        assert actual == expected

    def test_tag_str_representation(self):
        """Verify str() returns the tag name."""
        assert str(ReusabilityTag.FULL) == "FULL"
        assert str(ReusabilityTag.PARTIAL) == "PARTIAL"
        assert str(ReusabilityTag.NONE) == "NONE"

    def test_description(self):
        """Verify description() returns appropriate text."""
        full_desc = ReusabilityTag.FULL.description()
        assert "reused as-is" in full_desc.lower() or "reused" in full_desc

        partial_desc = ReusabilityTag.PARTIAL.description()
        assert "modification" in partial_desc.lower() or "requires" in partial_desc

        none_desc = ReusabilityTag.NONE.description()
        assert "entirely new" in none_desc.lower() or "new" in none_desc
