"""
Seed reference data JSON files from domain knowledge.

This script generates three JSON files in data/reference/:
1. weight_matrix.json - 5-attribute weight table across all tiers
2. effort_table.json - effort in days per phase per tier
3. rpa_tool_factors.json - per-tool effort multipliers
"""

import json
from pathlib import Path


def create_weight_matrix():
    """Generate weight_matrix.json with tier descriptions."""
    weight_matrix = {
        "metadata": {
            "attributes": [
                "activities",
                "business_rules",
                "layouts",
                "interfaces",
                "technology",
            ],
            "tiers": ["XS", "S", "M", "L", "XL"],
            "description": "Weight assignment for each attribute-tier combination with tier definitions",
        },
        "weights": {
            "activities": {
                "XS": {"weight": 2, "range": "1-5 activities"},
                "S": {"weight": 2, "range": "6-15 activities"},
                "M": {"weight": 4, "range": "16-30 activities"},
                "L": {"weight": 6, "range": "31-40 activities"},
                "XL": {"weight": 8, "range": "41-60+ activities"},
            },
            "business_rules": {
                "XS": {"weight": 2, "range": "0-1 rule"},
                "S": {"weight": 2, "range": "2-3 rules"},
                "M": {"weight": 4, "range": "4 rules"},
                "L": {"weight": 6, "range": "5 rules"},
                "XL": {"weight": 8, "range": "6+ rules"},
            },
            "layouts": {
                "XS": {"weight": 1, "range": "0-1 screen"},
                "S": {"weight": 1, "range": "2-3 screens"},
                "M": {"weight": 2, "range": "4 screens"},
                "L": {"weight": 3, "range": "5-6 screens"},
                "XL": {"weight": 4, "range": "7+ screens"},
            },
            "interfaces": {
                "XS": {"weight": 1, "range": "0 interfaces"},
                "S": {"weight": 1, "range": "1-2 interfaces"},
                "M": {"weight": 2, "range": "3-4 interfaces"},
                "L": {"weight": 3, "range": "5-6 interfaces"},
                "XL": {"weight": 4, "range": "7+ interfaces"},
            },
            "technology": {
                "XS": {"weight": 1, "range": "0 integrations"},
                "S": {"weight": 1, "range": "1 integration"},
                "M": {"weight": 2, "range": "2 integrations"},
                "L": {"weight": 3, "range": "3-4 integrations"},
                "XL": {"weight": 4, "range": "5+ integrations"},
            },
        },
    }
    return weight_matrix


def create_effort_table():
    """Generate effort_table.json with days per phase."""
    effort_table = {
        "metadata": {
            "tiers": ["XS", "S", "M", "L", "XL"],
            "phases": ["define", "build", "uat", "deploy"],
            "units": "days",
            "note": "S tier values are [min, max] ranges; all others are fixed integers",
        },
        "efforts": {
            "XS": {
                "define": 3,
                "build": 5,
                "uat": 1,
                "deploy": 1,
                "total": 10,
                "sprints": 1,
            },
            "S": {
                "define": [7, 15],
                "build": [8, 15],
                "uat": [3, 5],
                "deploy": [2, 5],
                "total": [20, 40],
                "sprints": [2, 4],
            },
            "M": {
                "define": 15,
                "build": 25,
                "uat": 5,
                "deploy": 5,
                "total": 50,
                "sprints": 5,
            },
            "L": {
                "define": 20,
                "build": 30,
                "uat": 5,
                "deploy": 5,
                "total": 60,
                "sprints": 6,
            },
            "XL": {
                "define": 25,
                "build": 40,
                "uat": 10,
                "deploy": 5,
                "total": 80,
                "sprints": 8,
            },
        },
    }
    return effort_table


def create_rpa_tool_factors():
    """Generate rpa_tool_factors.json with tool-specific multipliers."""
    rpa_tool_factors = {
        "metadata": {
            "tools": ["blue_prism", "uipath", "power_automate", "aa360"],
            "multiplier_types": [
                "surface_automation",
                "api_integration",
                "default",
            ],
            "description": "Per-tool effort multipliers based on automation type",
        },
        "factors": {
            "blue_prism": {
                "surface_automation": 1.3,
                "api_integration": 1.1,
                "default": 1.0,
            },
            "uipath": {
                "surface_automation": 1.1,
                "api_integration": 1.0,
                "default": 1.0,
            },
            "power_automate": {
                "surface_automation": 1.4,
                "api_integration": 0.9,
                "default": 1.0,
            },
            "aa360": {
                "surface_automation": 1.2,
                "api_integration": 1.1,
                "default": 1.0,
            },
        },
    }
    return rpa_tool_factors


def main():
    """Generate and write all reference data files."""
    reference_dir = Path(__file__).parent.parent / "data" / "reference"
    reference_dir.mkdir(parents=True, exist_ok=True)

    # Generate weight_matrix.json
    weight_matrix = create_weight_matrix()
    weight_matrix_path = reference_dir / "weight_matrix.json"
    with open(weight_matrix_path, "w") as f:
        json.dump(weight_matrix, f, indent=2)
    print(f"✓ Generated {weight_matrix_path}")

    # Generate effort_table.json
    effort_table = create_effort_table()
    effort_table_path = reference_dir / "effort_table.json"
    with open(effort_table_path, "w") as f:
        json.dump(effort_table, f, indent=2)
    print(f"✓ Generated {effort_table_path}")

    # Generate rpa_tool_factors.json
    rpa_tool_factors = create_rpa_tool_factors()
    rpa_tool_factors_path = reference_dir / "rpa_tool_factors.json"
    with open(rpa_tool_factors_path, "w") as f:
        json.dump(rpa_tool_factors, f, indent=2)
    print(f"✓ Generated {rpa_tool_factors_path}")

    # Verify all files exist and are valid JSON
    for file_path in [weight_matrix_path, effort_table_path, rpa_tool_factors_path]:
        with open(file_path, "r") as f:
            json.load(f)
        print(f"✓ Verified {file_path.name} is valid JSON")

    print("\n✅ All reference data files generated successfully!")


if __name__ == "__main__":
    main()
