"""
Tests for the attribute_scorer tool.

Comprehensive tests for scoring individual attributes with the Phase 1
scoring engine, including tier mapping, weight lookup, and rationale
generation.
"""

import pytest

from core.constants import ComplexityTier
from core.exceptions import ScoringValidationError
from core.models.assessment import AttributeScore
from tools.scoring.attribute_scorer import (
    ATTRIBUTE_METADATA,
    score_attribute,
    validate_attribute_score,
)


class TestAttributeMetadata:
    """Tests for ATTRIBUTE_METADATA constant."""

    def test_metadata_has_all_five_attributes(self):
        """Verify all 5 attributes are defined."""
        assert len(ATTRIBUTE_METADATA) == 5
        assert set(ATTRIBUTE_METADATA.keys()) == {1, 2, 3, 4, 5}

    def test_metadata_structure(self):
        """Verify each attribute has required fields."""
        for attr_id, metadata in ATTRIBUTE_METADATA.items():
            assert "name" in metadata
            assert "display_name" in metadata
            assert "description" in metadata
            assert isinstance(metadata["name"], str)
            assert isinstance(metadata["display_name"], str)
            assert isinstance(metadata["description"], str)

    def test_attribute_names_correct(self):
        """Verify attribute names match expected values."""
        expected = {
            1: "activities",
            2: "business_rules",
            3: "layouts",
            4: "interfaces",
            5: "technology",
        }
        for attr_id, name in expected.items():
            assert ATTRIBUTE_METADATA[attr_id]["name"] == name


class TestScoreAttribute:
    """Tests for score_attribute function."""

    # Test Activities (Attribute 1)
    def test_score_activities_small(self):
        """Activities: 5 → S tier → weight 2."""
        score = score_attribute(1, 5)
        assert score.attribute_id == 1
        assert score.attribute_name == "Activities"
        assert score.raw_value == 5
        assert score.selected_tier == ComplexityTier.S
        assert score.weight == 2
        assert "5" in score.tier_rationale
        assert "Small" in score.tier_rationale or "S" in score.tier_rationale

    def test_score_activities_medium(self):
        """Activities: 15 → M tier → weight 4."""
        score = score_attribute(1, 15)
        assert score.attribute_id == 1
        assert score.selected_tier == ComplexityTier.M
        assert score.weight == 4

    def test_score_activities_large(self):
        """Activities: 30 → L tier → weight 6."""
        score = score_attribute(1, 30)
        assert score.attribute_id == 1
        assert score.selected_tier == ComplexityTier.L
        assert score.weight == 6

    def test_score_activities_xlarge(self):
        """Activities: 50 → XL tier → weight 8."""
        score = score_attribute(1, 50)
        assert score.attribute_id == 1
        assert score.selected_tier == ComplexityTier.XL
        assert score.weight == 8

    # Test Business Rules (Attribute 2)
    def test_score_business_rules_zero(self):
        """Business Rules: 0 → S tier → weight 2."""
        score = score_attribute(2, 0)
        assert score.attribute_id == 2
        assert score.attribute_name == "Business Rules"
        assert score.selected_tier == ComplexityTier.S
        assert score.weight == 2

    def test_score_business_rules_medium(self):
        """Business Rules: 1 → M tier → weight 4."""
        score = score_attribute(2, 1)
        assert score.attribute_id == 2
        assert score.selected_tier == ComplexityTier.M
        assert score.weight == 4

    def test_score_business_rules_large(self):
        """Business Rules: 4 → L tier → weight 6."""
        score = score_attribute(2, 4)
        assert score.attribute_id == 2
        assert score.selected_tier == ComplexityTier.L
        assert score.weight == 6

    def test_score_business_rules_xlarge(self):
        """Business Rules: 5 → XL tier → weight 8."""
        score = score_attribute(2, 5)
        assert score.attribute_id == 2
        assert score.selected_tier == ComplexityTier.XL
        assert score.weight == 8

    # Test Layouts (Attribute 3)
    def test_score_layouts_small(self):
        """Layouts: 1 → S tier → weight 1."""
        score = score_attribute(3, 1)
        assert score.attribute_id == 3
        assert score.attribute_name == "Layouts"
        assert score.selected_tier == ComplexityTier.S
        assert score.weight == 1

    def test_score_layouts_medium(self):
        """Layouts: 2 → M tier → weight 2."""
        score = score_attribute(3, 2)
        assert score.attribute_id == 3
        assert score.selected_tier == ComplexityTier.M
        assert score.weight == 2

    def test_score_layouts_large(self):
        """Layouts: 5 → L tier → weight 3."""
        score = score_attribute(3, 5)
        assert score.attribute_id == 3
        assert score.selected_tier == ComplexityTier.L
        assert score.weight == 3

    def test_score_layouts_xlarge(self):
        """Layouts: 7 → XL tier → weight 4."""
        score = score_attribute(3, 7)
        assert score.attribute_id == 3
        assert score.selected_tier == ComplexityTier.XL
        assert score.weight == 4

    # Test Interfaces (Attribute 4)
    def test_score_interfaces_small_zero(self):
        """Interfaces: 0 → S tier → weight 1."""
        score = score_attribute(4, 0)
        assert score.attribute_id == 4
        assert score.attribute_name == "Interfaces"
        assert score.selected_tier == ComplexityTier.S
        assert score.weight == 1

    def test_score_interfaces_small_one(self):
        """Interfaces: 1 → S tier → weight 1."""
        score = score_attribute(4, 1)
        assert score.attribute_id == 4
        assert score.selected_tier == ComplexityTier.S
        assert score.weight == 1

    def test_score_interfaces_medium(self):
        """Interfaces: 3 → M tier → weight 2."""
        score = score_attribute(4, 3)
        assert score.attribute_id == 4
        assert score.selected_tier == ComplexityTier.M
        assert score.weight == 2

    def test_score_interfaces_large(self):
        """Interfaces: 5 → L tier → weight 3."""
        score = score_attribute(4, 5)
        assert score.attribute_id == 4
        assert score.selected_tier == ComplexityTier.L
        assert score.weight == 3

    def test_score_interfaces_xlarge(self):
        """Interfaces: 7 → XL tier → weight 4."""
        score = score_attribute(4, 7)
        assert score.attribute_id == 4
        assert score.selected_tier == ComplexityTier.XL
        assert score.weight == 4

    # Test Technology (Attribute 5)
    def test_score_technology_small_zero(self):
        """Technology: 0 → S tier → weight 1."""
        score = score_attribute(5, 0)
        assert score.attribute_id == 5
        assert score.attribute_name == "Additional Technology"
        assert score.selected_tier == ComplexityTier.S
        assert score.weight == 1

    def test_score_technology_medium(self):
        """Technology: 1 → M tier → weight 2."""
        score = score_attribute(5, 1)
        assert score.attribute_id == 5
        assert score.selected_tier == ComplexityTier.M
        assert score.weight == 2

    def test_score_technology_large(self):
        """Technology: 2 → L tier → weight 3."""
        score = score_attribute(5, 2)
        assert score.attribute_id == 5
        assert score.selected_tier == ComplexityTier.L
        assert score.weight == 3

    def test_score_technology_xlarge(self):
        """Technology: 4 → XL tier → weight 4."""
        score = score_attribute(5, 4)
        assert score.attribute_id == 5
        assert score.selected_tier == ComplexityTier.XL
        assert score.weight == 4

    # Ground truth test from CLAUDE.md
    def test_ground_truth_case(self):
        """Verify ground truth case from CLAUDE.md.

        Activities: XL (41-60) → weight 8
        Business Rules: XL (5-6) → weight 8
        Layouts: L (4-6) → weight 3
        Interfaces: S (1-2) → weight 1
        Technology: S (0) → weight 1
        Total: 8+8+3+1+1 = 21 → L
        """
        # Activities: 41-60 → XL
        score1 = score_attribute(1, 50)
        assert score1.selected_tier == ComplexityTier.XL
        assert score1.weight == 8

        # Business Rules: 5-6 → XL
        score2 = score_attribute(2, 5)
        assert score2.selected_tier == ComplexityTier.XL
        assert score2.weight == 8

        # Layouts: 4-6 → L
        score3 = score_attribute(3, 4)
        assert score3.selected_tier == ComplexityTier.L
        assert score3.weight == 3

        # Interfaces: 1-2 → S
        score4 = score_attribute(4, 1)
        assert score4.selected_tier == ComplexityTier.S
        assert score4.weight == 1

        # Technology: 0 → S
        score5 = score_attribute(5, 0)
        assert score5.selected_tier == ComplexityTier.S
        assert score5.weight == 1

        # Total should be 21
        total = sum(s.weight for s in [score1, score2, score3, score4, score5])
        assert total == 21

    # Error handling
    def test_invalid_attribute_id_zero(self):
        """Attribute ID 0 should raise error."""
        with pytest.raises(ScoringValidationError) as exc_info:
            score_attribute(0, 5)
        assert "Invalid attribute_id" in str(exc_info.value)

    def test_invalid_attribute_id_six(self):
        """Attribute ID 6 should raise error."""
        with pytest.raises(ScoringValidationError) as exc_info:
            score_attribute(6, 5)
        assert "Invalid attribute_id" in str(exc_info.value)

    def test_negative_raw_value(self):
        """Negative raw_value should raise error."""
        with pytest.raises(ScoringValidationError) as exc_info:
            score_attribute(1, -1)
        assert "Invalid raw_value" in str(exc_info.value)

    def test_rationale_is_populated(self):
        """Rationale should never be empty."""
        for attr_id in range(1, 6):
            score = score_attribute(attr_id, 5)
            assert score.tier_rationale
            assert len(score.tier_rationale) > 0


class TestValidateAttributeScore:
    """Tests for validate_attribute_score function."""

    def test_valid_score(self):
        """Valid score should not raise."""
        score = AttributeScore(
            attribute_id=1,
            attribute_name="Activities",
            raw_value=10,
            selected_tier=ComplexityTier.M,
            weight=4,
            tier_rationale="Test rationale",
        )
        # Should not raise
        validate_attribute_score(score)

    def test_invalid_attribute_id(self):
        """Invalid attribute_id should raise during AttributeScore creation."""
        # Pydantic validates at creation time, not in validate_attribute_score
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AttributeScore(
                attribute_id=6,
                attribute_name="Invalid",
                raw_value=10,
                selected_tier=ComplexityTier.M,
                weight=4,
                tier_rationale="Test",
            )

    def test_negative_raw_value_in_score(self):
        """Negative raw_value should raise."""
        score = AttributeScore(
            attribute_id=1,
            attribute_name="Activities",
            raw_value=-1,
            selected_tier=ComplexityTier.M,
            weight=4,
            tier_rationale="Test",
        )
        with pytest.raises(ScoringValidationError):
            validate_attribute_score(score)

    def test_negative_weight_in_score(self):
        """Negative weight should raise during AttributeScore creation."""
        # Pydantic validates at creation time, not in validate_attribute_score
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AttributeScore(
                attribute_id=1,
                attribute_name="Activities",
                raw_value=10,
                selected_tier=ComplexityTier.M,
                weight=-1,
                tier_rationale="Test",
            )
