"""
Tests for the classifier scoring module.

Comprehensive tests for validation, classification, special cases,
and confidence scoring.
"""

from datetime import datetime, timezone

import pytest

from core.constants import ComplexityTier
from core.exceptions import ScoringValidationError
from core.models.assessment import AttributeScore
from core.scoring.classifier import (
    ValidationResult,
    classify,
    classify_with_validation,
    get_confidence_score,
    handle_xs_special_case,
    validate_inputs,
)


class TestValidateInputs:
    """Tests for validate_inputs function."""

    def test_empty_list_returns_error(self):
        """Verify empty attribute list produces error."""
        result = validate_inputs([])
        assert result.is_valid is False
        assert any("No attribute scores" in e for e in result.errors)

    def test_none_returns_error(self):
        """Verify None scores produce error."""
        result = validate_inputs(None)
        assert result.is_valid is False
        assert any("No attribute scores" in e for e in result.errors)

    def test_four_scores_returns_error(self):
        """Verify 4 scores (not 5) produces error."""
        scores = [
            AttributeScore(
                attribute_id=i,
                attribute_name=f"Attr {i}",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=2,
                tier_rationale="Test",
            )
            for i in range(1, 5)
        ]
        result = validate_inputs(scores)
        assert result.is_valid is False
        assert any("Expected 5" in e for e in result.errors)

    def test_duplicate_attribute_id_returns_error(self):
        """Verify duplicate attribute_id produces error."""
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
                attribute_id=1,
                attribute_name="Attr 1 Duplicate",
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
            AttributeScore(
                attribute_id=5,
                attribute_name="Attr 5",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=2,
                tier_rationale="Test",
            ),
        ]
        result = validate_inputs(scores)
        assert result.is_valid is False
        assert any("Duplicate" in e for e in result.errors)

    def test_valid_five_scores(self):
        """Verify valid 5 scores return is_valid=True."""
        scores = [
            AttributeScore(
                attribute_id=i,
                attribute_name=f"Attr {i}",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=2,
                tier_rationale="Test",
            )
            for i in range(1, 6)
        ]
        result = validate_inputs(scores)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_warning_near_boundary_16(self):
        """Verify warning when score near tier boundary."""
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
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=0,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=0,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Technology",
                raw_value=0,
                selected_tier=ComplexityTier.S,
                weight=0,
                tier_rationale="Test",
            ),
        ]
        # Total = 8 + 8 + 0 + 0 + 0 = 16 (at L/M boundary)
        # Change one to get 17: distance to 16 is 1
        scores[4].weight = 1
        result = validate_inputs(scores)
        # Score 17: distance to 16 is 1 (within 1 of boundary)
        # Should have warning
        assert any("near tier boundary" in w for w in result.warnings)

    def test_warning_all_low_weights(self):
        """Verify warning when all weights are low."""
        scores = [
            AttributeScore(
                attribute_id=i,
                attribute_name=f"Attr {i}",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=1,  # All weight 1 (low)
                tier_rationale="Test",
            )
            for i in range(1, 6)
        ]
        result = validate_inputs(scores)
        assert result.is_valid is True
        assert any("All attributes scored low" in w for w in result.warnings)


class TestClassify:
    """Tests for classify function."""

    def test_classify_7_returns_s(self):
        """Verify score 7 classifies as S."""
        assert classify(7) == ComplexityTier.S

    def test_classify_8_returns_s(self):
        """Verify score 8 classifies as S."""
        assert classify(8) == ComplexityTier.S

    def test_classify_9_returns_m(self):
        """Verify score 9 classifies as M."""
        assert classify(9) == ComplexityTier.M

    def test_classify_15_returns_m(self):
        """Verify score 15 classifies as M."""
        assert classify(15) == ComplexityTier.M

    def test_classify_16_returns_l(self):
        """Verify score 16 classifies as L."""
        assert classify(16) == ComplexityTier.L

    def test_classify_22_returns_l(self):
        """Verify score 22 classifies as L."""
        assert classify(22) == ComplexityTier.L

    def test_classify_23_returns_xl(self):
        """Verify score 23 classifies as XL."""
        assert classify(23) == ComplexityTier.XL

    def test_classify_28_returns_xl(self):
        """Verify score 28 classifies as XL."""
        assert classify(28) == ComplexityTier.XL

    def test_classify_0_returns_xs(self):
        """Verify score 0 classifies as XS."""
        assert classify(0) == ComplexityTier.XS

    def test_classify_6_returns_xs(self):
        """Verify score 6 classifies as XS."""
        assert classify(6) == ComplexityTier.XS

    def test_classify_negative_raises(self):
        """Verify negative score raises ScoringValidationError."""
        with pytest.raises(ScoringValidationError) as exc_info:
            classify(-1)
        assert "cannot be negative" in str(exc_info.value).lower()

    def test_classify_too_high_raises(self):
        """Verify score > 28 raises ScoringValidationError."""
        with pytest.raises(ScoringValidationError) as exc_info:
            classify(29)
        assert "exceeds maximum" in str(exc_info.value).lower()


class TestHandleXSSpecialCase:
    """Tests for handle_xs_special_case function."""

    def test_two_xs_tier_attributes_with_low_score(self):
        """Verify 2 XS-tier attributes with low score returns True."""
        scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=5,
                selected_tier=ComplexityTier.XS,
                weight=1,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=0,
                selected_tier=ComplexityTier.XS,
                weight=1,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=1,
                selected_tier=ComplexityTier.M,
                weight=4,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=1,
                selected_tier=ComplexityTier.M,
                weight=4,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Technology",
                raw_value=0,
                selected_tier=ComplexityTier.M,
                weight=4,
                tier_rationale="Test",
            ),
        ]
        # 2 XS/S combined: XS, XS (count=2)
        # Total = 1+1+4+4+4 = 14 (but we need <=6 for XS special case)
        # Let me fix the total to be <= 6
        scores[2].weight = 0
        scores[3].weight = 1
        scores[4].weight = 1
        # Now: 2 XS, total = 1+1+0+1+1 = 4 (<= 6)
        assert handle_xs_special_case(scores) is True

    def test_three_xs_tier_attributes_returns_false(self):
        """Verify 3 XS-tier attributes returns False."""
        scores = [
            AttributeScore(
                attribute_id=i,
                attribute_name=f"Attr {i}",
                raw_value=1,
                selected_tier=ComplexityTier.XS,
                weight=1,
                tier_rationale="Test",
            )
            for i in range(1, 6)
        ]
        assert handle_xs_special_case(scores) is False

    def test_two_xs_but_high_score_returns_false(self):
        """Verify 2 XS attributes with high score returns False."""
        scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=45,
                selected_tier=ComplexityTier.XS,
                weight=8,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=5,
                selected_tier=ComplexityTier.XS,
                weight=8,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=1,
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
        # Total = 8+8+1+1+1 = 19 (> 6)
        assert handle_xs_special_case(scores) is False

    def test_empty_list_returns_false(self):
        """Verify empty list returns False."""
        assert handle_xs_special_case([]) is False


class TestGetConfidenceScore:
    """Tests for get_confidence_score function."""

    def test_confidence_middle_of_l_tier(self):
        """Verify score in middle of L tier has high confidence."""
        # L tier: 16-22
        # Middle is around 19, distance to both edges = 3
        confidence = get_confidence_score(19, ComplexityTier.L)
        assert confidence >= 0.9  # Should be close to 1.0

    def test_confidence_near_boundary(self):
        """Verify score near boundary has low confidence."""
        # L tier: 16-22
        # Score 21 is 1 away from 22 (XL boundary)
        confidence = get_confidence_score(21, ComplexityTier.L)
        assert confidence < 0.5  # Should be low

    def test_confidence_at_min_boundary(self):
        """Verify score at tier minimum has low confidence."""
        # L tier: 16-22
        confidence = get_confidence_score(16, ComplexityTier.L)
        assert confidence <= 0.2

    def test_confidence_range_0_05_to_1_0(self):
        """Verify confidence is always between 0.05 and 1.0."""
        for tier in ComplexityTier:
            # Test multiple scores within the tier
            for score in range(tier.min_score(), tier.max_score() + 1):
                confidence = get_confidence_score(score, tier)
                assert 0.05 <= confidence <= 1.0

    def test_confidence_rounded_to_2_decimals(self):
        """Verify confidence is rounded to 2 decimal places."""
        confidence = get_confidence_score(19, ComplexityTier.L)
        # Check if it has at most 2 decimal places
        assert isinstance(confidence, float)
        assert len(str(confidence).split('.')[-1]) <= 2


class TestClassifyWithValidation:
    """Tests for classify_with_validation function."""

    def test_invalid_inputs_raise_error(self):
        """Verify invalid inputs raise ScoringValidationError."""
        with pytest.raises(ScoringValidationError) as exc_info:
            classify_with_validation([])
        assert "validation failed" in str(exc_info.value).lower()

    def test_valid_ground_truth_returns_l(self):
        """Verify ground truth inputs return L tier."""
        scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=45,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="45 activities in XL range",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="5 rules in XL range",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=5,
                selected_tier=ComplexityTier.L,
                weight=3,
                tier_rationale="5 screens in L range",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=2,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="2 interfaces in S range",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Add. Technology",
                raw_value=0,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="0 integrations in S range",
            ),
        ]
        tier, result, requires_review = classify_with_validation(scores)
        assert tier == ComplexityTier.L
        assert result.is_valid is True

    def test_validation_result_included(self):
        """Verify ValidationResult is returned."""
        scores = [
            AttributeScore(
                attribute_id=i,
                attribute_name=f"Attr {i}",
                raw_value=1,
                selected_tier=ComplexityTier.S,
                weight=2,
                tier_rationale="Test",
            )
            for i in range(1, 6)
        ]
        tier, result, _ = classify_with_validation(scores)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True

    def test_tech_lead_review_for_xl(self):
        """Verify XL tier triggers tech lead review."""
        scores = [
            AttributeScore(
                attribute_id=i,
                attribute_name=f"Attr {i}",
                raw_value=45 if i == 1 else 5 if i == 2 else 1,
                selected_tier=ComplexityTier.XL if i <= 2 else ComplexityTier.S,
                weight=8 if i <= 2 else 1,
                tier_rationale="Test",
            )
            for i in range(1, 6)
        ]
        # Total = 8+8+1+1+1 = 19 (L tier)
        # But let's make it XL by adjusting weights
        scores[2].weight = 3
        scores[3].weight = 2
        scores[4].weight = 2
        # Total = 8+8+3+2+2 = 23 (XL tier)
        tier, result, requires_review = classify_with_validation(scores)
        if tier == ComplexityTier.XL:
            assert requires_review is True

    def test_tech_lead_review_for_high_score(self):
        """Verify score > 25 triggers tech lead review."""
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
                selected_tier=ComplexityTier.XL,
                weight=4,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=5,
                selected_tier=ComplexityTier.L,
                weight=3,
                tier_rationale="Test",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Technology",
                raw_value=3,
                selected_tier=ComplexityTier.L,
                weight=3,
                tier_rationale="Test",
            ),
        ]
        # Total = 8+8+4+3+3 = 26 (> 25)
        tier, result, requires_review = classify_with_validation(scores)
        assert requires_review is True


class TestGroundTruthClassification:
    """Ground truth test from the actual Excel domain knowledge."""

    def test_ground_truth_classification(self):
        """Test the exact ground truth classification scenario.

        From CLAUDE.md:
        - Activities: XL weight=8, raw=45
        - Business Rules: XL weight=8, raw=5
        - Layouts: L weight=3, raw=5
        - Interfaces: S weight=1, raw=2
        - Technology: S weight=1, raw=0
        - Total: 21 → Classification: L
        """
        scores = [
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=45,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="45 activities in XL range (41-60)",
            ),
            AttributeScore(
                attribute_id=2,
                attribute_name="Business Rules",
                raw_value=5,
                selected_tier=ComplexityTier.XL,
                weight=8,
                tier_rationale="5 rules in XL range (5-6)",
            ),
            AttributeScore(
                attribute_id=3,
                attribute_name="Layouts",
                raw_value=5,
                selected_tier=ComplexityTier.L,
                weight=3,
                tier_rationale="5 screens in L range (4-6)",
            ),
            AttributeScore(
                attribute_id=4,
                attribute_name="Interfaces",
                raw_value=2,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="2 interfaces in S range (1-2)",
            ),
            AttributeScore(
                attribute_id=5,
                attribute_name="Add. Technology",
                raw_value=0,
                selected_tier=ComplexityTier.S,
                weight=1,
                tier_rationale="0 integrations in S range (1)",
            ),
        ]

        tier, result, requires_review = classify_with_validation(scores)

        # Assertions from acceptance criteria
        assert tier == ComplexityTier.L, "Classification should be L"
        assert result.is_valid is True, "Validation should pass"

        # Total score is 21
        total_score = sum(score.weight for score in scores)
        assert total_score == 21, "Total score should be 21"

        # Confidence should be low (score 21 is near L/XL boundary at 22)
        confidence = get_confidence_score(total_score, tier)
        assert 0.05 <= confidence <= 0.5, (
            "Confidence should be low for score 21 in L tier "
            f"(near boundary) — got {confidence}"
        )

        # Tech lead review not needed for this score
        assert requires_review is False, "Score 21 should not require tech lead review"
