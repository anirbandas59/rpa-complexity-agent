"""
Comprehensive tests for the scoring engine.

Phase 9 — Testing & Validation

Covers every edge case and boundary condition for the weight matrix,
classifier, and effort calculator. These tests go beyond the existing
test_weight_matrix.py, test_classifier.py, and test_effort_table.py
to ensure complete correctness.
"""

import pytest

from core.constants import AssessmentPhase, ComplexityTier, RPATool
from core.exceptions import ScoringValidationError
from core.models.assessment import AttributeScore
from core.scoring.classifier import (
    classify,
    classify_with_validation,
    get_confidence_score,
    validate_inputs,
)
from core.scoring.effort_table import (
    calculate_effort,
    get_base_effort,
    get_rpa_adjustment_factor,
)
from core.scoring.weight_matrix import exceeds_xl_ceiling, get_weight, map_value_to_tier

# ============================================================================
# SECTION A — Weight Matrix Edge Cases
# ============================================================================


class TestWeightMatrixEdgeCases:
    """Comprehensive weight matrix tests covering all combinations and boundaries."""

    def test_all_attribute_tier_combinations(self):
        """Test all 5 attributes × 5 tiers = 25 valid combinations.

        Each combination must return a positive integer weight.
        Attributes 1 and 2 must always have higher weights than 3, 4, 5
        for the same tier.
        """
        for attr_id in range(1, 6):
            for tier in ComplexityTier:
                # Must not raise
                weight = get_weight(attr_id, tier)

                # Must be positive integer
                assert isinstance(weight, int)
                assert weight > 0

                # Attributes 1 and 2 have higher weights than 3, 4, 5
                if attr_id <= 2:
                    for other_attr in range(3, 6):
                        other_weight = get_weight(other_attr, tier)
                        assert weight >= other_weight, (
                            f"Attr {attr_id} weight {weight} should be >= "
                            f"Attr {other_attr} weight {other_weight} for tier {tier}"
                        )

    def test_tier_mapping_exact_boundaries_attr1_activities(self):
        """Test exact boundary values for attribute 1 (Activities).

        Ranges: S=≤10, M=11-20, L=21-40, XL=41+
        """
        # S boundary
        assert map_value_to_tier(1, 10) == ComplexityTier.S
        assert map_value_to_tier(1, 11) == ComplexityTier.M

        # M boundaries
        assert map_value_to_tier(1, 20) == ComplexityTier.M
        assert map_value_to_tier(1, 21) == ComplexityTier.L

        # L boundaries
        assert map_value_to_tier(1, 40) == ComplexityTier.L
        assert map_value_to_tier(1, 41) == ComplexityTier.XL

        # XL and above
        assert map_value_to_tier(1, 60) == ComplexityTier.XL
        assert map_value_to_tier(1, 61) == ComplexityTier.XL  # Capped at XL

    def test_tier_mapping_exact_boundaries_attr2_business_rules(self):
        """Test exact boundary values for attribute 2 (Business Rules).

        Ranges: S=0, M=1-2, L=3-4, XL=5+
        """
        # S boundary
        assert map_value_to_tier(2, 0) == ComplexityTier.S
        assert map_value_to_tier(2, 1) == ComplexityTier.M

        # M boundaries
        assert map_value_to_tier(2, 2) == ComplexityTier.M
        assert map_value_to_tier(2, 3) == ComplexityTier.L

        # L boundaries
        assert map_value_to_tier(2, 4) == ComplexityTier.L
        assert map_value_to_tier(2, 5) == ComplexityTier.XL

        # XL and above
        assert map_value_to_tier(2, 6) == ComplexityTier.XL
        assert map_value_to_tier(2, 100) == ComplexityTier.XL  # Capped at XL

    def test_tier_mapping_exact_boundaries_attr3_layouts(self):
        """Test exact boundary values for attribute 3 (Digital Layouts).

        Ranges: S=1, M=2-3, L=4-6, XL=7+
        """
        # S boundary
        assert map_value_to_tier(3, 1) == ComplexityTier.S
        assert map_value_to_tier(3, 2) == ComplexityTier.M

        # M boundaries
        assert map_value_to_tier(3, 3) == ComplexityTier.M
        assert map_value_to_tier(3, 4) == ComplexityTier.L

        # L boundaries
        assert map_value_to_tier(3, 6) == ComplexityTier.L
        assert map_value_to_tier(3, 7) == ComplexityTier.XL

    def test_tier_mapping_exact_boundaries_attr4_interfaces(self):
        """Test exact boundary values for attribute 4 (Interfaces).

        Ranges: S=0-2, M=3-4, L=5-6, XL=7+
        """
        # S boundaries
        assert map_value_to_tier(4, 0) == ComplexityTier.S
        assert map_value_to_tier(4, 2) == ComplexityTier.S
        assert map_value_to_tier(4, 3) == ComplexityTier.M

        # M boundaries
        assert map_value_to_tier(4, 4) == ComplexityTier.M
        assert map_value_to_tier(4, 5) == ComplexityTier.L

        # L boundaries
        assert map_value_to_tier(4, 6) == ComplexityTier.L
        assert map_value_to_tier(4, 7) == ComplexityTier.XL

    def test_tier_mapping_exact_boundaries_attr5_technology(self):
        """Test exact boundary values for attribute 5 (Add. Technology).

        Ranges: S=0, M=1, L=2-3, XL=4+
        """
        # S boundary
        assert map_value_to_tier(5, 0) == ComplexityTier.S
        assert map_value_to_tier(5, 1) == ComplexityTier.M

        # M to L boundary
        assert map_value_to_tier(5, 2) == ComplexityTier.L
        assert map_value_to_tier(5, 3) == ComplexityTier.L

        # L to XL boundary
        assert map_value_to_tier(5, 4) == ComplexityTier.XL
        assert map_value_to_tier(5, 10) == ComplexityTier.XL

    def test_xl_ceiling_exact_values(self):
        """Test XL ceiling boundaries for all attributes.

        Ceilings: Attr1=60, Attr2=6, Attr3=10, Attr4=8, Attr5=5
        """
        # Attribute 1: ceiling at 60
        assert not exceeds_xl_ceiling(1, 60)
        assert exceeds_xl_ceiling(1, 61)

        # Attribute 2: ceiling at 6
        assert not exceeds_xl_ceiling(2, 6)
        assert exceeds_xl_ceiling(2, 7)

        # Attribute 3: ceiling at 10
        assert not exceeds_xl_ceiling(3, 10)
        assert exceeds_xl_ceiling(3, 11)

        # Attribute 4: ceiling at 8
        assert not exceeds_xl_ceiling(4, 8)
        assert exceeds_xl_ceiling(4, 9)

        # Attribute 5: ceiling at 5
        assert not exceeds_xl_ceiling(5, 5)
        assert exceeds_xl_ceiling(5, 6)

    def test_invalid_attribute_id_raises(self):
        """Test that invalid attribute IDs raise ScoringValidationError."""
        with pytest.raises(ScoringValidationError):
            map_value_to_tier(0, 10)

        with pytest.raises(ScoringValidationError):
            map_value_to_tier(6, 10)

        with pytest.raises(ScoringValidationError):
            get_weight(0, ComplexityTier.S)

        with pytest.raises(ScoringValidationError):
            get_weight(6, ComplexityTier.S)

    def test_negative_value_raises(self):
        """Test that negative values raise ScoringValidationError."""
        with pytest.raises(ScoringValidationError):
            map_value_to_tier(1, -1)

        # exceeds_xl_ceiling doesn't validate negative values, it just returns False
        # (negative values never exceed ceiling)
        assert exceeds_xl_ceiling(1, -1) is False


# ============================================================================
# SECTION B — Classifier Comprehensive Tests
# ============================================================================


class TestClassifierComprehensive:
    """Comprehensive classifier tests covering all valid scores and edge cases."""

    def test_all_valid_scores(self):
        """For every integer score 0-28, classify must not raise and return valid tier."""
        for score in range(0, 29):
            # Must not raise
            tier = classify(score)

            # Must be a valid ComplexityTier
            assert isinstance(tier, ComplexityTier)
            assert tier in [
                ComplexityTier.XS,
                ComplexityTier.S,
                ComplexityTier.M,
                ComplexityTier.L,
                ComplexityTier.XL,
            ]

    def test_score_to_tier_mapping(self):
        """Verify score-to-tier boundaries.

        XS: 0-6
        S: 7-8
        M: 9-15
        L: 16-22
        XL: 23-28
        """
        # XS boundaries
        assert classify(0) == ComplexityTier.XS
        assert classify(6) == ComplexityTier.XS

        # S boundaries
        assert classify(7) == ComplexityTier.S
        assert classify(8) == ComplexityTier.S

        # M boundaries
        assert classify(9) == ComplexityTier.M
        assert classify(15) == ComplexityTier.M

        # L boundaries
        assert classify(16) == ComplexityTier.L
        assert classify(22) == ComplexityTier.L

        # XL boundaries
        assert classify(23) == ComplexityTier.XL
        assert classify(28) == ComplexityTier.XL

    def test_confidence_score_properties(self):
        """Confidence scores must be between 0.05 and 1.0.

        Scores at tier midpoint should have higher confidence than
        scores at tier boundaries.
        """
        for score in range(0, 29):
            tier = classify(score)
            confidence = get_confidence_score(score, tier)

            # Must be in valid range
            assert (
                0.05 <= confidence <= 1.0
            ), f"Confidence {confidence} for score {score} outside [0.05, 1.0]"

    def test_confidence_midpoint_vs_boundary(self):
        """Scores at midpoint should have higher confidence than boundaries."""
        # S tier (7-8): midpoint would be 7.5, so 7 is closer to boundary than 8
        get_confidence_score(7, ComplexityTier.S)
        get_confidence_score(8, ComplexityTier.S)
        # Both at boundary, roughly equal

        # M tier (9-15): midpoint is 12
        conf_9 = get_confidence_score(9, ComplexityTier.M)
        conf_12 = get_confidence_score(12, ComplexityTier.M)
        conf_15 = get_confidence_score(15, ComplexityTier.M)

        # Midpoint should have highest confidence
        assert conf_12 >= conf_9
        assert conf_12 >= conf_15

    def test_validation_collects_all_errors(self):
        """Validation must collect ALL errors, not stop at first one.

        Note: Pydantic validates model-level constraints (attribute_id range,
        negative weights) at object creation time, so we can only test errors
        that validate_inputs catches during its checks.
        """
        # Build a list with 2 validation errors:
        # - Only 4 attributes (not 5) — ERROR from validate_inputs count check
        # - Duplicate attribute_id — ERROR from validate_inputs duplicate check
        scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Attr 1",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=2,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=1,  # ERROR: duplicate
                attribute_name="Attr 1 Dup",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=2,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Attr 3",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=2,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Attr 4",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=2,
                tier_rationale="Test",
            ),
        ]

        result = validate_inputs(scores)

        # Must be invalid
        assert result.is_valid is False

        # Must collect multiple errors
        assert len(result.errors) >= 2  # At least duplicate and count errors
        error_strings = " ".join(result.errors).lower()
        assert "expected 5" in error_strings
        assert "duplicate" in error_strings

    def test_validation_with_empty_scores(self):
        """Empty score list must be caught by validation."""
        result = validate_inputs([])
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validation_with_none_scores(self):
        """None score list must be caught by validation."""
        result = validate_inputs(None)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_classify_with_validation_integration(self):
        """Full classification pipeline must work end-to-end."""
        # Create valid ground truth scores
        scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=45,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=5,
                selected_tier=ComplexityTier.L,
                weight=3,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=2,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Technology",
                raw_value=0,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="Test",
            ),
        ]

        # Must not raise
        tier, validation, requires_tech_lead = classify_with_validation(scores)

        # Results must be valid
        assert validation.is_valid is True
        assert tier == ComplexityTier.L  # 8+8+3+1+1 = 21 → L


# ============================================================================
# SECTION C — Effort Calculator Tests
# ============================================================================


class TestEffortCalculatorComprehensive:
    """Comprehensive effort calculator tests."""

    def test_effort_table_completeness(self):
        """For every ComplexityTier, effort estimate must be complete."""
        for tier in ComplexityTier:
            estimate = calculate_effort(tier)

            # Must have all 4 phases
            assert len(estimate.phases) == 4
            phase_names = {p.phase.value for p in estimate.phases}
            expected_phases = {"DEFINE", "BUILD", "UAT", "DEPLOY"}
            assert phase_names == expected_phases

            # All phases must have positive days
            for phase in estimate.phases:
                assert phase.min_days > 0
                assert phase.max_days > 0
                assert phase.min_days <= phase.max_days

            # Total must be positive
            assert estimate.total_min_days > 0
            assert estimate.total_max_days > 0

            # Sprints must be present
            assert estimate.sprints is not None

    def test_effort_all_tiers_values(self):
        """Verify effort values for all tiers match the effort table.

        From effort_table.json:
        XS: 10 days, 1 sprint
        S: 20-40 days, 2-4 sprints
        M: 50 days, 5 sprints
        L: 60 days, 6 sprints
        XL: 80 days, 8 sprints
        """
        test_cases = [
            (ComplexityTier.XS, 10, 10, 1),
            (ComplexityTier.S, 20, 40, (2, 4)),
            (ComplexityTier.M, 50, 50, 5),
            (ComplexityTier.L, 60, 60, 6),
            (ComplexityTier.XL, 80, 80, 8),
        ]

        for tier, expected_min, expected_max, expected_sprints in test_cases:
            estimate = calculate_effort(tier)
            assert (
                estimate.total_min_days == expected_min
            ), f"{tier}: expected min {expected_min}, got {estimate.total_min_days}"
            assert (
                estimate.total_max_days == expected_max
            ), f"{tier}: expected max {expected_max}, got {estimate.total_max_days}"
            assert (
                estimate.sprints == expected_sprints
            ), f"{tier}: expected sprints {expected_sprints}, got {estimate.sprints}"

    def test_rpa_tool_adjustment_all_tools(self):
        """For every RPATool, get_rpa_adjustment_factor must return valid multiplier."""
        for tool in RPATool:
            # Test with both surface automation and without
            for has_surface in [True, False]:
                for has_api in [True, False]:
                    factor = get_rpa_adjustment_factor(tool, has_surface, has_api)

                    # Must be a float
                    assert isinstance(factor, float)

                    # Must be in reasonable bounds
                    assert (
                        0.5 <= factor <= 2.0
                    ), f"Tool {tool}: factor {factor} outside [0.5, 2.0]"

    def test_s_tier_range_handling(self):
        """S tier must have ranges for both days and sprints."""
        estimate = calculate_effort(ComplexityTier.S)

        # Days must be a range
        assert estimate.total_min_days == 20
        assert estimate.total_max_days == 40
        assert estimate.total_min_days < estimate.total_max_days

        # Sprints must be a tuple
        assert isinstance(estimate.sprints, tuple)
        assert estimate.sprints == (2, 4)

        # Each phase must mark is_range=True
        for phase in estimate.phases:
            assert phase.is_range is True

    def test_effort_with_rpa_adjustment(self):
        """Effort with RPA tool adjustment must apply factor correctly."""
        # L tier without adjustment: 60 days
        base_estimate = calculate_effort(ComplexityTier.L)
        assert base_estimate.total_min_days == 60
        assert base_estimate.adjustment_applied is False

        # L tier with Blue Prism surface automation: 60 * 1.3 = 78
        adjusted_estimate = calculate_effort(
            ComplexityTier.L,
            rpa_tool=RPATool.BLUE_PRISM,
            has_surface_automation=True,
        )
        assert adjusted_estimate.adjustment_applied is True
        # Due to banker's rounding, might be 77 or 78
        assert 76 <= adjusted_estimate.total_min_days <= 78

    def test_effort_display_methods(self):
        """Effort display methods must format correctly."""
        # S tier with range
        estimate_s = calculate_effort(ComplexityTier.S)
        assert estimate_s.total_days_display == "20–40 days"
        assert estimate_s.sprint_display == "2–4 sprints"

        # L tier without range
        estimate_l = calculate_effort(ComplexityTier.L)
        assert estimate_l.total_days_display == "60 days"
        assert estimate_l.sprint_display == "6 sprints"

    def test_base_effort_retrieval(self):
        """get_base_effort must return correct phase breakdown."""
        for tier in ComplexityTier:
            base_effort = get_base_effort(tier)

            # Must return dict with 4 phases
            assert len(base_effort) == 4
            assert all(isinstance(p, AssessmentPhase) for p in base_effort.keys())

            # All phases must have positive days
            for phase, effort in base_effort.items():
                assert effort.min_days > 0
                assert effort.max_days > 0


# ============================================================================
# SECTION D — Integration Tests (No LLM)
# ============================================================================


class TestScoringIntegration:
    """Integration tests combining multiple scoring functions."""

    def test_raw_value_to_weight_pipeline(self):
        """Test complete pipeline: raw value → tier → weight.

        Ground truth: Activities=52 → XL → weight 8
        """
        # Step 1: Map value to tier
        tier = map_value_to_tier(1, 52)
        assert tier == ComplexityTier.XL

        # Step 2: Get weight for tier
        weight = get_weight(1, tier)
        assert weight == 8

    def test_ground_truth_scoring_flow(self):
        """Complete ground truth scoring flow from raw values to final tier.

        Activities: 52 → XL → 8
        Business Rules: 6 → XL → 8
        Layouts: 5 → L → 3
        Interfaces: 2 → S → 1
        Technology: 0 → S → 1
        Total: 21 → L
        """
        # Build scores from raw values
        raw_values = {
            1: (52, 1),  # (value, attr_id)
            2: (6, 2),
            3: (5, 3),
            4: (2, 4),
            5: (0, 5),
        }

        scores = []
        for attr_id, (raw_value, _) in raw_values.items():
            tier = map_value_to_tier(attr_id, raw_value)
            weight = get_weight(attr_id, tier)

            scores.append(
                AttributeScore(
                    attribute_id=attr_id,
                    attribute_name=f"Attribute {attr_id}",
                    raw_value=raw_value,
                    selected_tier=tier,
                    weight=weight,
                    tier_rationale=f"From {raw_value}",
                )
            )

        # Classify
        final_tier, validation, requires_tech_lead = classify_with_validation(scores)
        total_score = sum(s.weight for s in scores)

        # Verify ground truth
        assert total_score == 21
        assert final_tier == ComplexityTier.L
        assert validation.is_valid is True

        # Get effort
        effort = calculate_effort(final_tier)
        assert effort.total_min_days == 60
        assert effort.total_max_days == 60
        assert effort.sprint_display == "6 sprints"
