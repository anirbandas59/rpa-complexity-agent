"""Tests for reference data JSON files."""

import json
from pathlib import Path

import pytest

REFERENCE_DIR = Path(__file__).parent.parent.parent / "data" / "reference"
EXPECTED_ATTRIBUTES = {"activities", "business_rules", "layouts", "interfaces", "technology"}
EXPECTED_TIERS = {"XS", "S", "M", "L", "XL"}
EXPECTED_TOOLS = {"blue_prism", "uipath", "power_automate", "aa360"}


@pytest.fixture
def weight_matrix():
    path = REFERENCE_DIR / "weight_matrix.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def effort_table():
    path = REFERENCE_DIR / "effort_table.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def rpa_tool_factors():
    path = REFERENCE_DIR / "rpa_tool_factors.json"
    with open(path) as f:
        return json.load(f)


def test_weight_matrix_file_exists():
    assert (REFERENCE_DIR / "weight_matrix.json").exists()


def test_effort_table_file_exists():
    assert (REFERENCE_DIR / "effort_table.json").exists()


def test_rpa_tool_factors_file_exists():
    assert (REFERENCE_DIR / "rpa_tool_factors.json").exists()


def test_weight_matrix_has_5_attributes(weight_matrix):
    attributes = set(weight_matrix["weights"].keys())
    assert attributes == EXPECTED_ATTRIBUTES


def test_weight_matrix_has_5_tiers_per_attribute(weight_matrix):
    for attribute, tiers in weight_matrix["weights"].items():
        assert set(tiers.keys()) == EXPECTED_TIERS, f"{attribute} missing tiers"


def test_weight_matrix_correct_weights_high_complexity(weight_matrix):
    """activities and business_rules should have XS=2, S=2, M=4, L=6, XL=8."""
    for attr in ("activities", "business_rules"):
        assert weight_matrix["weights"][attr]["XS"]["weight"] == 2
        assert weight_matrix["weights"][attr]["S"]["weight"] == 2
        assert weight_matrix["weights"][attr]["M"]["weight"] == 4
        assert weight_matrix["weights"][attr]["L"]["weight"] == 6
        assert weight_matrix["weights"][attr]["XL"]["weight"] == 8


def test_weight_matrix_correct_weights_low_complexity(weight_matrix):
    """layouts, interfaces, technology should have XS=1, S=1, M=2, L=3, XL=4."""
    for attr in ("layouts", "interfaces", "technology"):
        assert weight_matrix["weights"][attr]["XS"]["weight"] == 1
        assert weight_matrix["weights"][attr]["S"]["weight"] == 1
        assert weight_matrix["weights"][attr]["M"]["weight"] == 2
        assert weight_matrix["weights"][attr]["L"]["weight"] == 3
        assert weight_matrix["weights"][attr]["XL"]["weight"] == 4


def test_effort_table_has_all_5_tiers(effort_table):
    assert set(effort_table["efforts"].keys()) == EXPECTED_TIERS


def test_effort_table_xs_values(effort_table):
    xs = effort_table["efforts"]["XS"]
    assert xs["define"] == 3
    assert xs["build"] == 5
    assert xs["uat"] == 1
    assert xs["deploy"] == 1
    assert xs["total"] == 10
    assert xs["sprints"] == 1


def test_effort_table_s_values_are_ranges(effort_table):
    s = effort_table["efforts"]["S"]
    assert s["total"] == [20, 40]
    assert s["sprints"] == [2, 4]
    for key in ("define", "build", "uat", "deploy", "total", "sprints"):
        assert isinstance(s[key], list) and len(s[key]) == 2, f"S.{key} should be [min, max]"


def test_effort_table_m_values(effort_table):
    m = effort_table["efforts"]["M"]
    assert m["total"] == 50
    assert m["sprints"] == 5


def test_effort_table_l_values(effort_table):
    l = effort_table["efforts"]["L"]
    assert l["total"] == 60
    assert l["sprints"] == 6


def test_effort_table_xl_values(effort_table):
    xl = effort_table["efforts"]["XL"]
    assert xl["total"] == 80
    assert xl["sprints"] == 8


def test_rpa_tool_factors_has_all_4_tools(rpa_tool_factors):
    assert set(rpa_tool_factors["factors"].keys()) == EXPECTED_TOOLS


def test_rpa_tool_factors_blue_prism(rpa_tool_factors):
    bp = rpa_tool_factors["factors"]["blue_prism"]
    assert bp["surface_automation"] == 1.3
    assert bp["api_integration"] == 1.1
    assert bp["default"] == 1.0


def test_rpa_tool_factors_uipath(rpa_tool_factors):
    ui = rpa_tool_factors["factors"]["uipath"]
    assert ui["surface_automation"] == 1.1
    assert ui["api_integration"] == 1.0
    assert ui["default"] == 1.0


def test_rpa_tool_factors_power_automate(rpa_tool_factors):
    pa = rpa_tool_factors["factors"]["power_automate"]
    assert pa["surface_automation"] == 1.4
    assert pa["api_integration"] == 0.9
    assert pa["default"] == 1.0


def test_rpa_tool_factors_aa360(rpa_tool_factors):
    aa = rpa_tool_factors["factors"]["aa360"]
    assert aa["surface_automation"] == 1.2
    assert aa["api_integration"] == 1.1
    assert aa["default"] == 1.0
