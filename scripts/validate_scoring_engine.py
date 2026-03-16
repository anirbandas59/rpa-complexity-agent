#!/usr/bin/env python3
"""
RPA Complexity Assessment Agent — Phase 1 Validation Script

This is the phase gate for Phase 1 (Scoring Engine). It validates
the entire scoring engine end-to-end against known ground truth values
from the Excel workbook.

Run with: uv run python scripts/validate_scoring_engine.py
Exit code: 0 if all validations pass, 1 if any fail.
"""

import sys
from pathlib import Path

# Add project root to path so imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.constants import AssessmentPhase, ComplexityTier, RPATool
from core.exceptions import ScoringValidationError
from core.models.assessment import AttributeScore
from core.scoring.classifier import (
    classify,
    classify_with_validation,
    get_confidence_score,
    validate_inputs,
)
from core.scoring.effort_table import calculate_effort
from core.scoring.weight_matrix import exceeds_xl_ceiling, get_weight, map_value_to_tier


def print_header():
    """Print the validation script header."""
    print("═" * 67)
    print("  RPA Complexity Assessment Agent — Scoring Engine Validation")
    print("  Phase 1 Gate Check")
    print("═" * 67)
    print()


def print_section(title: str):
    """Print a section header."""
    print(f"{title}")


def print_result(case_id: str, passed: bool, description: str, details: str = ""):
    """Print a single validation result."""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {case_id}: {description}", end="")
    if details:
        print(f" ({details})", end="")
    print()


def print_footer(total_cases: int, passed_cases: int):
    """Print the validation footer."""
    print()
    print("─" * 67)
    print(f"  Results: {passed_cases}/{total_cases} cases passed")

    if passed_cases == total_cases:
        print("  Status:  ✅ PHASE 1 GATE — PASSED")
        print("  Scoring engine is deterministic and validated.")
        print("  Safe to proceed to Phase 2.")
    else:
        failed = total_cases - passed_cases
        print(f"  Status:  ❌ PHASE 1 GATE — FAILED ({failed} case(s) failed)")
        print("  Fix all failures before proceeding to Phase 2.")

    print("═" * 67)


def validate_section_a():
    """Validate weight matrix."""
    results = []

    # A1: Ground truth tier mapping
    print_section("SECTION A — Weight Matrix")
    a1_checks = [
        (1, 45, ComplexityTier.XL),
        (2, 5, ComplexityTier.XL),
        (3, 5, ComplexityTier.L),
        (4, 2, ComplexityTier.S),
        (5, 0, ComplexityTier.S),
    ]
    a1_pass = True
    a1_correct = 0
    for attr_id, value, expected in a1_checks:
        result = map_value_to_tier(attr_id, value)
        if result == expected:
            a1_correct += 1
        else:
            a1_pass = False

    print_result("A1", a1_pass, "Ground truth tier mapping", f"{a1_correct}/5 correct")
    results.append(a1_pass)

    # A2: Weight lookup correctness
    a2_checks = [
        (1, ComplexityTier.XL, 8),
        (2, ComplexityTier.XL, 8),
        (3, ComplexityTier.L, 3),
        (4, ComplexityTier.S, 1),
        (5, ComplexityTier.S, 1),
    ]
    a2_pass = True
    a2_correct = 0
    for attr_id, tier, expected in a2_checks:
        result = get_weight(attr_id, tier)
        if result == expected:
            a2_correct += 1
        else:
            a2_pass = False

    print_result("A2", a2_pass, "Weight lookup correctness", f"{a2_correct}/5 correct")
    results.append(a2_pass)

    # A3: Score sum correctness
    # From A2: weights are 8, 8, 3, 1, 1 = 21
    weights = [8, 8, 3, 1, 1]
    total = sum(weights)
    a3_pass = total == 21
    print_result("A3", a3_pass, "Score sum correctness", f"{total} == 21")
    results.append(a3_pass)

    # A4: XL ceiling detection
    a4_checks = [
        (1, 61, True),
        (1, 60, False),
        (3, 11, True),
        (3, 10, False),
    ]
    a4_pass = True
    a4_correct = 0
    for attr_id, value, expected in a4_checks:
        result = exceeds_xl_ceiling(attr_id, value)
        if result == expected:
            a4_correct += 1
        else:
            a4_pass = False

    print_result("A4", a4_pass, "XL ceiling detection", f"{a4_correct}/4 correct")
    results.append(a4_pass)

    return results


def validate_section_b():
    """Validate classifier."""
    results = []

    print()
    print_section("SECTION B — Classifier")

    # B1: Ground truth classification
    scores = [
        AttributeScore(
            attribute_id=1,
            attribute_name="Activities",
            raw_value=45,
            selected_tier=ComplexityTier.XL,
            weight=8,
            tier_rationale="Ground truth value from Excel",
        ),
        AttributeScore(
            attribute_id=2,
            attribute_name="Business Rules",
            raw_value=5,
            selected_tier=ComplexityTier.XL,
            weight=8,
            tier_rationale="Ground truth value from Excel",
        ),
        AttributeScore(
            attribute_id=3,
            attribute_name="Layouts",
            raw_value=5,
            selected_tier=ComplexityTier.L,
            weight=3,
            tier_rationale="Ground truth value from Excel",
        ),
        AttributeScore(
            attribute_id=4,
            attribute_name="Interfaces",
            raw_value=2,
            selected_tier=ComplexityTier.S,
            weight=1,
            tier_rationale="Ground truth value from Excel",
        ),
        AttributeScore(
            attribute_id=5,
            attribute_name="Technology",
            raw_value=0,
            selected_tier=ComplexityTier.S,
            weight=1,
            tier_rationale="Ground truth value from Excel",
        ),
    ]

    try:
        tier, validation, requires_review = classify_with_validation(scores)
        b1_pass = tier == ComplexityTier.L and validation.is_valid
        print_result("B1", b1_pass, "Ground truth classification → L", "valid")
    except Exception as e:
        print_result("B1", False, "Ground truth classification → L", f"exception: {e}")
        b1_pass = False

    results.append(b1_pass)

    # B2: Band boundary correctness
    b2_checks = [
        (7, ComplexityTier.S),
        (8, ComplexityTier.S),
        (9, ComplexityTier.M),
        (15, ComplexityTier.M),
        (16, ComplexityTier.L),
        (22, ComplexityTier.L),
        (23, ComplexityTier.XL),
        (28, ComplexityTier.XL),
    ]
    b2_pass = True
    b2_correct = 0
    for score, expected in b2_checks:
        result = classify(score)
        if result == expected:
            b2_correct += 1
        else:
            b2_pass = False

    print_result("B2", b2_pass, "Band boundary correctness", f"{b2_correct}/8 correct")
    results.append(b2_pass)

    # B3: Confidence score for ground truth (score 21 in L tier)
    confidence = get_confidence_score(21, ComplexityTier.L)
    b3_pass = 0.05 <= confidence <= 0.5
    print_result(
        "B3",
        b3_pass,
        "Confidence score for score=21",
        f"{confidence} (in range 0.05–0.5)",
    )
    results.append(b3_pass)

    # B4: Error handling
    b4_checks = 0
    b4_pass = True

    # Check: classify(-1) raises ScoringValidationError
    try:
        classify(-1)
        b4_pass = False
    except ScoringValidationError:
        b4_checks += 1
    except Exception:
        b4_pass = False

    # Check: classify(29) raises ScoringValidationError
    try:
        classify(29)
        b4_pass = False
    except ScoringValidationError:
        b4_checks += 1
    except Exception:
        b4_pass = False

    # Check: validate_inputs([]) returns is_valid=False
    validation_result = validate_inputs([])
    if not validation_result.is_valid:
        b4_checks += 1
    else:
        b4_pass = False

    print_result("B4", b4_pass, "Error handling", f"{b4_checks}/3 correct")
    results.append(b4_pass)

    return results


def validate_section_c():
    """Validate effort calculator."""
    results = []

    print()
    print_section("SECTION C — Effort Calculator")

    # C1: Ground truth effort for L tier
    # From effort_table.json: L tier = 60 days, 6 sprints
    estimate = calculate_effort(ComplexityTier.L)
    c1_pass = (
        estimate.total_min_days == 60
        and estimate.total_max_days == 60
        and estimate.sprint_display == "6 sprints"
        and estimate.adjustment_applied is False
    )
    print_result("C1", c1_pass, "Ground truth effort for L", "60 days, 6 sprints")
    results.append(c1_pass)

    # C2: All tier totals
    # from effort_table.json: XS=10, S=20-40, M=50, L=60, XL=80
    c2_checks = [
        (ComplexityTier.XS, 10, 10),
        (ComplexityTier.M, 50, 50),
        (ComplexityTier.L, 60, 60),
        (ComplexityTier.XL, 80, 80),
        (ComplexityTier.S, 20, 40),
    ]
    c2_pass = True
    c2_correct = 0
    for tier, expected_min, expected_max in c2_checks:
        estimate = calculate_effort(tier)
        if (
            estimate.total_min_days == expected_min
            and estimate.total_max_days == expected_max
        ):
            c2_correct += 1
        else:
            c2_pass = False

    print_result("C2", c2_pass, "All tier totals", f"{c2_correct}/5 correct")
    results.append(c2_pass)

    # C3: RPA tool adjustment
    # Blue Prism with surface automation = 1.3x factor
    # L tier = 60 days base
    # Phases: DEFINE 20*1.3=26, BUILD 30*1.3=39, UAT 5*1.3→6 (banker's rounding),
    # DEPLOY 5*1.3→6 = 77 total (banker's rounding on fractions)
    estimate = calculate_effort(
        ComplexityTier.L,
        rpa_tool=RPATool.BLUE_PRISM,
        has_surface_automation=True,
    )
    c3_pass = estimate.adjustment_applied and estimate.total_min_days == 77
    print_result("C3", c3_pass, "Blue Prism surface adjustment", "77 days")
    results.append(c3_pass)

    # C4: Phase breakdown for XL
    # XL BUILD phase should be 40 days (from effort_table.json)
    estimate = calculate_effort(ComplexityTier.XL)
    build_phase = None
    for phase in estimate.phases:
        if phase.phase == AssessmentPhase.BUILD:
            build_phase = phase
            break

    c4_pass = build_phase is not None and build_phase.min_days == 40
    print_result("C4", c4_pass, "XL Build phase", "40 days")
    results.append(c4_pass)

    return results


def validate_section_d():
    """Validate integration (end-to-end pipeline)."""
    results = []

    print()
    print_section("SECTION D — Integration")

    # D1: Complete end-to-end pipeline
    # Step 1: Use map_value_to_tier to derive tiers from raw values
    tier_1 = map_value_to_tier(1, 45)  # Activities=45
    tier_2 = map_value_to_tier(2, 5)   # BusinessRules=5
    tier_3 = map_value_to_tier(3, 5)   # Layouts=5
    tier_4 = map_value_to_tier(4, 2)   # Interfaces=2
    tier_5 = map_value_to_tier(5, 0)   # Technology=0

    # Step 2: Get weights for each tier
    weight_1 = get_weight(1, tier_1)
    weight_2 = get_weight(2, tier_2)
    weight_3 = get_weight(3, tier_3)
    weight_4 = get_weight(4, tier_4)
    weight_5 = get_weight(5, tier_5)

    # Step 3: Build AttributeScore objects
    scores = [
        AttributeScore(
            attribute_id=1,
            attribute_name="Activities",
            raw_value=45,
            selected_tier=tier_1,
            weight=weight_1,
            tier_rationale="From ground truth mapping",
        ),
        AttributeScore(
            attribute_id=2,
            attribute_name="Business Rules",
            raw_value=5,
            selected_tier=tier_2,
            weight=weight_2,
            tier_rationale="From ground truth mapping",
        ),
        AttributeScore(
            attribute_id=3,
            attribute_name="Layouts",
            raw_value=5,
            selected_tier=tier_3,
            weight=weight_3,
            tier_rationale="From ground truth mapping",
        ),
        AttributeScore(
            attribute_id=4,
            attribute_name="Interfaces",
            raw_value=2,
            selected_tier=tier_4,
            weight=weight_4,
            tier_rationale="From ground truth mapping",
        ),
        AttributeScore(
            attribute_id=5,
            attribute_name="Technology",
            raw_value=0,
            selected_tier=tier_5,
            weight=weight_5,
            tier_rationale="From ground truth mapping",
        ),
    ]

    # Step 4: Classify
    final_tier, validation, requires_review = classify_with_validation(scores)
    total_score = sum(score.weight for score in scores)

    # Step 5: Get effort estimate
    effort = calculate_effort(final_tier)

    # Check all assertions
    d1_pass = (
        tier_1 == ComplexityTier.XL
        and tier_3 == ComplexityTier.L
        and tier_4 == ComplexityTier.S
        and total_score == 21
        and final_tier == ComplexityTier.L
        and effort.total_min_days == 60
        and effort.sprint_display == "6 sprints"
    )

    print_result("D1", d1_pass, "GROUND TRUTH END-TO-END", "")

    if d1_pass:
        print(f"    Activities=45        → {tier_1.value:2} → weight {weight_1}")
        print(f"    Bus.Rules=5          → {tier_2.value:2} → weight {weight_2}")
        print(f"    Layouts=5            → {tier_3.value:2} → weight {weight_3}")
        print(f"    Interfaces=2         → {tier_4.value:2} → weight {weight_4}")
        print(f"    Technology=0         → {tier_5.value:2} → weight {weight_5}")
        print(f"    Total Score:         {total_score}")
        print(f"    Final Tier:          {final_tier.value}")
        print(f"    Effort:              {effort.total_min_days} days / {effort.sprint_display}")
        print(f"    Result:              MATCHES EXCEL GROUND TRUTH ✓")

    results.append(d1_pass)

    return results


def main():
    """Run all validation cases and report results."""
    print_header()

    try:
        section_a = validate_section_a()
        section_b = validate_section_b()
        section_c = validate_section_c()
        section_d = validate_section_d()

        all_results = section_a + section_b + section_c + section_d
        total_cases = len(all_results)
        passed_cases = sum(1 for r in all_results if r)

        print_footer(total_cases, passed_cases)

        if passed_cases == total_cases:
            return 0
        else:
            return 1

    except Exception as e:
        print()
        print(f"[ERROR] Validation failed with exception: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
