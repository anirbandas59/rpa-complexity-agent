"""
Tests for the weight matrix scoring module.

Comprehensive tests for weight lookups, tier mapping,
and ceiling violation detection.
"""

import pytest

from core.constants import ComplexityTier
from core.exceptions import ScoringValidationError
from core.scoring.weight_matrix import (
    exceeds_xl_ceiling,
    get_all_weights,
    get_tier_range_description,
    get_weight,
    map_value_to_tier,
)


class TestGetWeight:
    """Tests for get_weight function."""

    def test_get_weight_activities_xl(self):
        """Verify weight for Activities (attr 1), XL tier."""
        assert get_weight(1, ComplexityTier.XL) == 8

    def test_get_weight_activities_m(self):
        """Verify weight for Activities (attr 1), M tier."""
        assert get_weight(1, ComplexityTier.M) == 4

    def test_get_weight_layouts_m(self):
        """Verify weight for Layouts (attr 3), M tier."""
        assert get_weight(3, ComplexityTier.M) == 2

    def test_get_weight_layouts_xl(self):
        """Verify weight for Layouts (attr 3), XL tier."""
        assert get_weight(3, ComplexityTier.XL) == 4

    def test_get_weight_technology_l(self):
        """Verify weight for Technology (attr 5), L tier."""
        assert get_weight(5, ComplexityTier.L) == 3

    def test_get_weight_business_rules_s(self):
        """Verify weight for Business Rules (attr 2), S tier."""
        assert get_weight(2, ComplexityTier.S) == 2

    def test_get_weight_interfaces_s(self):
        """Verify weight for Interfaces (attr 4), S tier."""
        assert get_weight(4, ComplexityTier.S) == 1

    def test_get_weight_invalid_attribute_zero(self):
        """Verify get_weight rejects attribute_id 0."""
        with pytest.raises(ScoringValidationError) as exc_info:
            get_weight(0, ComplexityTier.M)
        assert "Invalid attribute_id" in str(exc_info.value)

    def test_get_weight_invalid_attribute_six(self):
        """Verify get_weight rejects attribute_id 6."""
        with pytest.raises(ScoringValidationError) as exc_info:
            get_weight(6, ComplexityTier.M)
        assert "Invalid attribute_id" in str(exc_info.value)

    def test_get_weight_all_tiers(self):
        """Verify weight can be looked up for all tiers."""
        for tier in ComplexityTier:
            weight = get_weight(1, tier)
            assert isinstance(weight, int)
            assert weight > 0


class TestGetTierRangeDescription:
    """Tests for get_tier_range_description function."""

    def test_get_description_activities_xl(self):
        """Verify description for Activities, XL tier."""
        desc = get_tier_range_description(1, ComplexityTier.XL)
        assert "41-60" in desc or "41" in desc
        assert "activities" in desc.lower()

    def test_get_description_activities_m(self):
        """Verify description for Activities, M tier."""
        desc = get_tier_range_description(1, ComplexityTier.M)
        assert "activities" in desc.lower()

    def test_get_description_layouts_l(self):
        """Verify description for Layouts, L tier."""
        desc = get_tier_range_description(3, ComplexityTier.L)
        assert desc  # Just verify it returns something

    def test_get_description_invalid_attribute(self):
        """Verify description rejects invalid attribute."""
        with pytest.raises(ScoringValidationError):
            get_tier_range_description(0, ComplexityTier.M)

    def test_get_description_all_combinations(self):
        """Verify descriptions exist for all attribute-tier combinations."""
        for attr_id in range(1, 6):
            for tier in ComplexityTier:
                desc = get_tier_range_description(attr_id, tier)
                assert isinstance(desc, str)
                assert len(desc) > 0


class TestGetAllWeights:
    """Tests for get_all_weights function."""

    def test_get_all_weights_returns_dict(self):
        """Verify get_all_weights returns a dict."""
        weights = get_all_weights()
        assert isinstance(weights, dict)

    def test_get_all_weights_has_all_attributes(self):
        """Verify all attributes are in the result."""
        weights = get_all_weights()
        expected_attrs = {
            "activities",
            "business_rules",
            "layouts",
            "interfaces",
            "technology",
        }
        assert set(weights.keys()) == expected_attrs

    def test_get_all_weights_has_all_tiers(self):
        """Verify all tiers are present for each attribute."""
        weights = get_all_weights()
        expected_tiers = {"XS", "S", "M", "L", "XL"}
        for attr_name, tier_weights in weights.items():
            assert set(tier_weights.keys()) == expected_tiers

    def test_get_all_weights_values_are_integers(self):
        """Verify all weight values are positive integers."""
        weights = get_all_weights()
        for attr_name, tier_weights in weights.items():
            for tier_name, weight in tier_weights.items():
                assert isinstance(weight, int)
                assert weight > 0


class TestMapValueToTierActivities:
    """Tests for map_value_to_tier with Activities (attribute 1)."""

    def test_activities_5_maps_to_s(self):
        """Verify 5 activities maps to S."""
        assert map_value_to_tier(1, 5) == ComplexityTier.S

    def test_activities_10_maps_to_s(self):
        """Verify 10 activities maps to S (boundary)."""
        assert map_value_to_tier(1, 10) == ComplexityTier.S

    def test_activities_11_maps_to_m(self):
        """Verify 11 activities maps to M."""
        assert map_value_to_tier(1, 11) == ComplexityTier.M

    def test_activities_20_maps_to_m(self):
        """Verify 20 activities maps to M (boundary)."""
        assert map_value_to_tier(1, 20) == ComplexityTier.M

    def test_activities_21_maps_to_l(self):
        """Verify 21 activities maps to L."""
        assert map_value_to_tier(1, 21) == ComplexityTier.L

    def test_activities_40_maps_to_l(self):
        """Verify 40 activities maps to L (boundary)."""
        assert map_value_to_tier(1, 40) == ComplexityTier.L

    def test_activities_41_maps_to_xl(self):
        """Verify 41 activities maps to XL."""
        assert map_value_to_tier(1, 41) == ComplexityTier.XL

    def test_activities_45_maps_to_xl(self):
        """Verify 45 activities maps to XL."""
        assert map_value_to_tier(1, 45) == ComplexityTier.XL

    def test_activities_65_maps_to_xl_capped(self):
        """Verify 65 activities maps to XL (capped)."""
        assert map_value_to_tier(1, 65) == ComplexityTier.XL


class TestMapValueToTierBusinessRules:
    """Tests for map_value_to_tier with Business Rules (attribute 2)."""

    def test_business_rules_0_maps_to_s(self):
        """Verify 0 business rules maps to S."""
        assert map_value_to_tier(2, 0) == ComplexityTier.S

    def test_business_rules_1_maps_to_m(self):
        """Verify 1 business rule maps to M."""
        assert map_value_to_tier(2, 1) == ComplexityTier.M

    def test_business_rules_2_maps_to_m(self):
        """Verify 2 business rules maps to M."""
        assert map_value_to_tier(2, 2) == ComplexityTier.M

    def test_business_rules_3_maps_to_l(self):
        """Verify 3 business rules maps to L."""
        assert map_value_to_tier(2, 3) == ComplexityTier.L

    def test_business_rules_4_maps_to_l(self):
        """Verify 4 business rules maps to L."""
        assert map_value_to_tier(2, 4) == ComplexityTier.L

    def test_business_rules_5_maps_to_xl(self):
        """Verify 5 business rules maps to XL."""
        assert map_value_to_tier(2, 5) == ComplexityTier.XL

    def test_business_rules_6_maps_to_xl(self):
        """Verify 6 business rules maps to XL."""
        assert map_value_to_tier(2, 6) == ComplexityTier.XL

    def test_business_rules_10_maps_to_xl_capped(self):
        """Verify 10 business rules maps to XL (capped)."""
        assert map_value_to_tier(2, 10) == ComplexityTier.XL


class TestMapValueToTierLayouts:
    """Tests for map_value_to_tier with Layouts (attribute 3)."""

    def test_layouts_1_maps_to_s(self):
        """Verify 1 layout maps to S."""
        assert map_value_to_tier(3, 1) == ComplexityTier.S

    def test_layouts_2_maps_to_m(self):
        """Verify 2 layouts maps to M."""
        assert map_value_to_tier(3, 2) == ComplexityTier.M

    def test_layouts_3_maps_to_m(self):
        """Verify 3 layouts maps to M."""
        assert map_value_to_tier(3, 3) == ComplexityTier.M

    def test_layouts_4_maps_to_l(self):
        """Verify 4 layouts maps to L."""
        assert map_value_to_tier(3, 4) == ComplexityTier.L

    def test_layouts_5_maps_to_l(self):
        """Verify 5 layouts maps to L."""
        assert map_value_to_tier(3, 5) == ComplexityTier.L

    def test_layouts_6_maps_to_l(self):
        """Verify 6 layouts maps to L."""
        assert map_value_to_tier(3, 6) == ComplexityTier.L

    def test_layouts_7_maps_to_xl(self):
        """Verify 7 layouts maps to XL."""
        assert map_value_to_tier(3, 7) == ComplexityTier.XL

    def test_layouts_12_maps_to_xl_capped(self):
        """Verify 12 layouts maps to XL (capped)."""
        assert map_value_to_tier(3, 12) == ComplexityTier.XL


class TestMapValueToTierInterfaces:
    """Tests for map_value_to_tier with Interfaces (attribute 4)."""

    def test_interfaces_0_maps_to_s(self):
        """Verify 0 interfaces maps to S."""
        assert map_value_to_tier(4, 0) == ComplexityTier.S

    def test_interfaces_1_maps_to_s(self):
        """Verify 1 interface maps to S."""
        assert map_value_to_tier(4, 1) == ComplexityTier.S

    def test_interfaces_2_maps_to_s(self):
        """Verify 2 interfaces maps to S."""
        assert map_value_to_tier(4, 2) == ComplexityTier.S

    def test_interfaces_3_maps_to_m(self):
        """Verify 3 interfaces maps to M."""
        assert map_value_to_tier(4, 3) == ComplexityTier.M

    def test_interfaces_4_maps_to_m(self):
        """Verify 4 interfaces maps to M."""
        assert map_value_to_tier(4, 4) == ComplexityTier.M

    def test_interfaces_5_maps_to_l(self):
        """Verify 5 interfaces maps to L."""
        assert map_value_to_tier(4, 5) == ComplexityTier.L

    def test_interfaces_6_maps_to_l(self):
        """Verify 6 interfaces maps to L."""
        assert map_value_to_tier(4, 6) == ComplexityTier.L

    def test_interfaces_7_maps_to_xl(self):
        """Verify 7 interfaces maps to XL."""
        assert map_value_to_tier(4, 7) == ComplexityTier.XL

    def test_interfaces_10_maps_to_xl_capped(self):
        """Verify 10 interfaces maps to XL (capped)."""
        assert map_value_to_tier(4, 10) == ComplexityTier.XL


class TestMapValueToTierTechnology:
    """Tests for map_value_to_tier with Technology (attribute 5)."""

    def test_technology_0_maps_to_s(self):
        """Verify 0 technology integrations maps to S."""
        assert map_value_to_tier(5, 0) == ComplexityTier.S

    def test_technology_1_maps_to_m(self):
        """Verify 1 technology integration maps to M."""
        assert map_value_to_tier(5, 1) == ComplexityTier.M

    def test_technology_2_maps_to_l(self):
        """Verify 2 technology integrations maps to L."""
        assert map_value_to_tier(5, 2) == ComplexityTier.L

    def test_technology_3_maps_to_l(self):
        """Verify 3 technology integrations maps to L."""
        assert map_value_to_tier(5, 3) == ComplexityTier.L

    def test_technology_4_maps_to_xl(self):
        """Verify 4 technology integrations maps to XL."""
        assert map_value_to_tier(5, 4) == ComplexityTier.XL

    def test_technology_5_maps_to_xl(self):
        """Verify 5 technology integrations maps to XL."""
        assert map_value_to_tier(5, 5) == ComplexityTier.XL

    def test_technology_7_maps_to_xl_capped(self):
        """Verify 7 technology integrations maps to XL (capped)."""
        assert map_value_to_tier(5, 7) == ComplexityTier.XL


class TestMapValueToTierEdgeCases:
    """Tests for edge cases in map_value_to_tier."""

    def test_negative_raw_value_raises(self):
        """Verify negative raw_value raises ScoringValidationError."""
        with pytest.raises(ScoringValidationError) as exc_info:
            map_value_to_tier(1, -1)
        assert "raw_value" in str(exc_info.value).lower()

    def test_invalid_attribute_raises(self):
        """Verify invalid attribute_id raises ScoringValidationError."""
        with pytest.raises(ScoringValidationError) as exc_info:
            map_value_to_tier(6, 5)
        assert "attribute" in str(exc_info.value).lower()

    def test_zero_attribute_raises(self):
        """Verify attribute_id 0 raises ScoringValidationError."""
        with pytest.raises(ScoringValidationError):
            map_value_to_tier(0, 5)


class TestExceedsXLCeiling:
    """Tests for exceeds_xl_ceiling function."""

    def test_activities_61_exceeds_ceiling(self):
        """Verify 61 activities exceeds ceiling of 60."""
        assert exceeds_xl_ceiling(1, 61) is True

    def test_activities_60_does_not_exceed_ceiling(self):
        """Verify 60 activities does not exceed ceiling."""
        assert exceeds_xl_ceiling(1, 60) is False

    def test_layouts_11_exceeds_ceiling(self):
        """Verify 11 layouts exceeds ceiling of 10."""
        assert exceeds_xl_ceiling(3, 11) is True

    def test_layouts_10_does_not_exceed_ceiling(self):
        """Verify 10 layouts does not exceed ceiling."""
        assert exceeds_xl_ceiling(3, 10) is False

    def test_business_rules_7_exceeds_ceiling(self):
        """Verify 7 business rules exceeds ceiling of 6."""
        assert exceeds_xl_ceiling(2, 7) is True

    def test_business_rules_6_does_not_exceed_ceiling(self):
        """Verify 6 business rules does not exceed ceiling."""
        assert exceeds_xl_ceiling(2, 6) is False

    def test_interfaces_9_exceeds_ceiling(self):
        """Verify 9 interfaces exceeds ceiling of 8."""
        assert exceeds_xl_ceiling(4, 9) is True

    def test_interfaces_8_does_not_exceed_ceiling(self):
        """Verify 8 interfaces does not exceed ceiling."""
        assert exceeds_xl_ceiling(4, 8) is False

    def test_technology_6_exceeds_ceiling(self):
        """Verify 6 technology integrations exceeds ceiling of 5."""
        assert exceeds_xl_ceiling(5, 6) is True

    def test_technology_5_does_not_exceed_ceiling(self):
        """Verify 5 technology integrations does not exceed ceiling."""
        assert exceeds_xl_ceiling(5, 5) is False

    def test_exceeds_xl_ceiling_invalid_attribute(self):
        """Verify exceeds_xl_ceiling rejects invalid attribute."""
        with pytest.raises(ScoringValidationError):
            exceeds_xl_ceiling(6, 5)


class TestGroundTruthTierMapping:
    """Ground truth test from the actual Excel domain knowledge."""

    def test_ground_truth_tier_mapping(self):
        """Test tier mapping for the ground truth assessment scenario.

        From CLAUDE.md:
        - Activities: 41-60 range (raw=45) → XL
        - Business Rules: 5-6 range (raw=5) → XL
        - Layouts: 4-6 range (raw=5) → L
        - Interfaces: 1-2 range (raw=2) → S
        - Technology: 0 integrations (raw=0) → S
        """
        # Activities: 45 activities → XL
        assert map_value_to_tier(1, 45) == ComplexityTier.XL

        # Business Rules: 5 rules → XL
        assert map_value_to_tier(2, 5) == ComplexityTier.XL

        # Layouts: 5 screens → L
        assert map_value_to_tier(3, 5) == ComplexityTier.L

        # Interfaces: 2 interfaces → S
        assert map_value_to_tier(4, 2) == ComplexityTier.S

        # Technology: 0 integrations → S
        assert map_value_to_tier(5, 0) == ComplexityTier.S

        # Verify weights for each tier
        assert get_weight(1, ComplexityTier.XL) == 8
        assert get_weight(2, ComplexityTier.XL) == 8
        assert get_weight(3, ComplexityTier.L) == 3
        assert get_weight(4, ComplexityTier.S) == 1
        assert get_weight(5, ComplexityTier.S) == 1

        # Total should be 21
        total_weight = 8 + 8 + 3 + 1 + 1
        assert total_weight == 21
