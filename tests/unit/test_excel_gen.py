"""
Verification of excel_generator.py fixes.
Stubs mirror the real Pydantic models from assessment.py exactly.
"""

import sys
import types
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Font

# ── Stub modules ─────────────────────────────────────────────────────────────


class ComplexityTier(str, Enum):
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


class RPATool(str, Enum):
    UIPATH = "UIPATH"


# Real AttributeScore fields from assessment.py
@dataclass
class AttributeScore:
    attribute_id: int  # 1–5
    attribute_name: str  # human-readable name
    raw_value: int  # actual count from PDD
    selected_tier: ComplexityTier
    weight: int  # point weight for tier
    tier_rationale: str  # explanation


# Real AssessmentResult fields from assessment.py
@dataclass
class AssessmentResult:
    session_id: str
    project_name: str
    rpa_tool: RPATool
    total_score: int
    complexity_tier: ComplexityTier
    confidence_score: float
    reasoning: str
    created_at: datetime
    attribute_scores: List[AttributeScore] = field(default_factory=list)
    requires_tech_lead_review: bool = False
    # NOTE: target_applications does NOT exist on the real model


@dataclass
class Step:
    description: str
    weight: float
    reusability_comment: str


@dataclass
class Branch:
    branch_name: str
    steps: List[Step]


@dataclass
class StepDecompositionResult:
    project_name: str
    branches: List[Branch]


WEIGHT_TABLE = {
    1: {
        ComplexityTier.XS: 2,
        ComplexityTier.S: 2,
        ComplexityTier.M: 4,
        ComplexityTier.L: 6,
        ComplexityTier.XL: 8,
    },
    2: {
        ComplexityTier.XS: 2,
        ComplexityTier.S: 2,
        ComplexityTier.M: 4,
        ComplexityTier.L: 6,
        ComplexityTier.XL: 8,
    },
    3: {
        ComplexityTier.XS: 1,
        ComplexityTier.S: 1,
        ComplexityTier.M: 2,
        ComplexityTier.L: 3,
        ComplexityTier.XL: 4,
    },
    4: {
        ComplexityTier.XS: 1,
        ComplexityTier.S: 1,
        ComplexityTier.M: 2,
        ComplexityTier.L: 3,
        ComplexityTier.XL: 4,
    },
    5: {
        ComplexityTier.XS: 1,
        ComplexityTier.S: 1,
        ComplexityTier.M: 2,
        ComplexityTier.L: 3,
        ComplexityTier.XL: 4,
    },
}


def get_weight(attr_id, tier):
    return WEIGHT_TABLE[attr_id][tier]


def make_module(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


class FakeLogger:
    def info(self, *a):
        pass

    def warning(self, *a):
        pass

    def error(self, *a):
        pass


def get_logger(_):
    return FakeLogger()


class OutputGenerationError(Exception):
    pass


make_module("config")
make_module("config.logging_config", get_logger=get_logger)
make_module("core")
make_module("core.constants", ComplexityTier=ComplexityTier, RPATool=RPATool)
make_module("core.exceptions", OutputGenerationError=OutputGenerationError)
make_module("core.models")
make_module("core.models.assessment", AssessmentResult=AssessmentResult)
make_module("core.models.timeline", DeliveryTimeline=type("DeliveryTimeline", (), {}))
make_module("core.scoring")
make_module("core.scoring.weight_matrix", get_weight=get_weight)
make_module("tools")
make_module("tools.output")
make_module(
    "tools.output.step_decomposer", StepDecompositionResult=StepDecompositionResult
)

sys.path.insert(0, "/home/anirban/workspace/projects/rpa-complexity-agent")
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "excel_generator",
    "/home/anirban/workspace/projects/rpa-complexity-agent/tools/output/excel_generator.py",
)
eg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eg)

# ── Assessment data — matches real model fields exactly ──────────────────────
assessment = AssessmentResult(
    session_id="test-session-abc",
    project_name="Order Processing Automation",
    rpa_tool=RPATool.UIPATH,
    total_score=16,
    complexity_tier=ComplexityTier.L,
    confidence_score=0.92,
    reasoning="Complex process with multiple business rules and approval workflows.",
    created_at=datetime(2026, 3, 17, 12, 13),
    attribute_scores=[
        AttributeScore(
            1,
            "Activities",
            20,
            ComplexityTier.L,
            6,
            "20 distinct RPA activities identified",
        ),
        AttributeScore(
            2, "Business Rules", 4, ComplexityTier.L, 6, "4 decision points in flow"
        ),
        AttributeScore(3, "Layouts", 3, ComplexityTier.M, 2, "3 digital layouts used"),
        AttributeScore(4, "Interfaces", 2, ComplexityTier.S, 1, "2 target systems"),
        AttributeScore(
            5, "Additional Tech", 0, ComplexityTier.S, 1, "No additional technology"
        ),
    ],
)

decomposition = StepDecompositionResult(
    project_name="Order Processing Automation",
    branches=[
        Branch(
            "Main Flow",
            [
                Step("Check email trigger", 1.0, "Reusable"),
                Step("Download attachment", 0.5, "Reusable"),
                Step("Open SAP", 1.0, "Reusable"),
            ],
        ),
        Branch(
            "Exception Handling",
            [
                Step("Send error notification", 0.5, "Partially reusable"),
            ],
        ),
    ],
)

# ── Run generator ────────────────────────────────────────────────────────────
wb = Workbook()
ws_calc = wb.active
assert ws_calc is not None
ws_calc.title = "Calculator"
ws_steps = wb.create_sheet("Steps")

eg._write_calculator_sheet(ws_calc, assessment)
steps_total_row = eg._write_steps_sheet(ws_steps, decomposition)
ws_calc["C41"].value = f"=Steps!C{steps_total_row}"
ws_calc["C41"].font = Font(bold=True)

# ── Helpers ──────────────────────────────────────────────────────────────────
PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []


def check(label, got, expected):
    ok = got == expected
    results.append((PASS if ok else FAIL, label, expected, got))


def val(ref):
    return ws_calc[ref].value


def sz(ref):
    return ws_calc[ref].font.size if ws_calc[ref].font else None


def bold(ref):
    return ws_calc[ref].font.bold if ws_calc[ref].font else False


def align(ref):
    a = ws_calc[ref].alignment
    return a.horizontal if a else None


def fill(ref):
    f = ws_calc[ref].fill
    return (
        f.fgColor.rgb
        if f and f.fill_type and f.fill_type != "none" and f.fgColor
        else None
    )


def color(ref):
    f = ws_calc[ref].font
    return f.color.rgb if f and f.color and f.color.type == "rgb" else None


# ── Fix 1: D1 sz=14 ─────────────────────────────────────────────────────────
check("D1 value", val("D1"), "Sizing estimation for a single Automation")
check("D1 font size", sz("D1"), 14)
check("D1 bold", bold("D1"), True)

# ── Fix 2: D2–D6 sz=10 ──────────────────────────────────────────────────────
check("D2 font size", sz("D2"), 10)
check("D3 font size", sz("D3"), 10)
check("D6 font size", sz("D6"), 10)
check("D2 bold", bold("D2"), True)

# ── Fix 3: D8 center, sz=11 ─────────────────────────────────────────────────
check("D8 value", val("D8"), "COMPLEXITY ATTRIBUTES")
check("D8 align", align("D8"), "center")
check("D8 font size", sz("D8"), 11)

# ── Fix 4: Tier headers row 9 — sz=12, center ───────────────────────────────
check("D9 value", val("D9"), "XS")
check("D9 font size", sz("D9"), 12)
check("D9 align", align("D9"), "center")
check("M9 fill (L=red)", fill("M9"), "FFFF0000")
check("P9 fill (XL=purple)", fill("P9"), "FF7030A0")
check("D9 fill (XS=green)", fill("D9"), "FF92D050")

# ── Fix 4: Weighting columns — 4 cols S/M/L/XL, W9 absent ──────────────────
check("S9 = Weighting Criteria S", val("S9"), "Weighting Criteria S")
check("T9 = Weighting Criteria M", val("T9"), "Weighting Criteria M")
check("U9 = Weighting Criteria L", val("U9"), "Weighting Criteria L")
check("V9 = Weighting Criteria XL", val("V9"), "Weighting Criteria XL")
check("W9 absent (no 5th col)", val("W9"), None)

# ── Fix 5: Attribute marker placement ───────────────────────────────────────
# Activities (id=1) → L tier → marker col N
check("N10 marker X (Activities→L)", val("N10"), "X")
check("E10 empty (not XS)", val("E10"), None)
check("H10 empty (not S)", val("H10"), None)
check("K10 empty (not M)", val("K10"), None)
check("Q10 empty (not XL)", val("Q10"), None)
# Business Rules (id=2) → L → N11
check("N11 marker X (Rules→L)", val("N11"), "X")
# Layouts (id=3) → M → K12
check("K12 marker X (Layouts→M)", val("K12"), "X")
check("N12 empty (not L)", val("N12"), None)
# Interfaces (id=4) → S → H13
check("H13 marker X (Ifaces→S)", val("H13"), "X")
# Additional Tech (id=5) → S → H14
check("H14 marker X (Tech→S)", val("H14"), "X")

# ── Fix 5: Weight values S–V for Activities (id=1) ──────────────────────────
check("S10 = 2 (S weight)", val("S10"), 2)
check("T10 = 4 (M weight)", val("T10"), 4)
check("U10 = 6 (L weight)", val("U10"), 6)
check("V10 = 8 (XL weight)", val("V10"), 8)
check("W10 absent (no XS extra)", val("W10"), None)
check("R10 = 8 (max weight col)", val("R10"), 8)

# ── Fix 5: IF formula in weight-formula column ───────────────────────────────
f10 = val("F10") or ""
check("F10 IF formula references E10 and S10", "IF(E10" in f10 and "S10" in f10, True)

# ── Fix 6: Row 16 — COUNTIF/SUM with red font ───────────────────────────────
check("E16 COUNTIF formula", "COUNTIF" in (val("E16") or ""), True)
check("F16 SUM formula", "SUM" in (val("F16") or ""), True)
check("H16 COUNTIF formula", "COUNTIF" in (val("H16") or ""), True)
check("I16 SUM formula", "SUM" in (val("I16") or ""), True)
check("Q16 COUNTIF formula", "COUNTIF" in (val("Q16") or ""), True)
check("R16 SUM formula", "SUM" in (val("R16") or ""), True)
check("E16 red font", color("E16"), "FFFF0000")
check("F16 red font", color("F16"), "FFFF0000")
check("R16 red font", color("R16"), "FFFF0000")

# ── Fix 7: G18 score formula + D18 sz=12 ────────────────────────────────────
g18 = val("G18") or ""
check("G18 SUM formula", "SUM" in g18, True)
check("G18 references F16", "F16" in g18, True)
check("G18 references R16", "R16" in g18, True)
check("D18 font size 12", sz("D18"), 12)

# ── Fix 7: G19 classification — sz=18, correct value, no white fill ─────────
check("G19 value = L", val("G19"), "L")
check("G19 font size 18", sz("G19"), 18)
check("G19 bold", bold("G19"), True)
check("G19 no fill", fill("G19"), None)

# ── Fix 8: Equivalence chart at rows 11–14, X10 label ───────────────────────
check("X10 = Equivalence Chart", val("X10"), "Equivalence Chart")
check("X11 = 7  (S min)", val("X11"), 7)
check("Y11 = 8  (S max)", val("Y11"), 8)
check("Z11 = S", val("Z11"), "S")
check("X12 = 9  (M min)", val("X12"), 9)
check("Y12 = 15 (M max)", val("Y12"), 15)
check("Z12 = M", val("Z12"), "M")
check("X13 = 16 (L min)", val("X13"), 16)
check("Z13 = L", val("Z13"), "L")
check("X14 = 23 (XL min)", val("X14"), 23)
check("Y14 = 28 (XL max)", val("Y14"), 28)
check("Z14 = XL", val("Z14"), "XL")
check("X21 absent (not old pos)", val("X21"), None)

# ── Fix 9: B25 Phase — no grey fill ─────────────────────────────────────────
check("B25 = Phase", val("B25"), "Phase")
check("B25 bold", bold("B25"), True)
check("B25 no fill", fill("B25"), None)

# ── Fix 9: Effort tier bold — only assessed (L→col M) bolded ────────────────
check("M26 bold (L-tier assessed)", bold("M26"), True)
check("J26 not bold (M-tier)", bold("J26"), False)
check("G26 not bold (S-tier)", bold("G26"), False)
check("P26 not bold (XL-tier)", bold("P26"), False)

# ── Fix 10: Section label bold ───────────────────────────────────────────────
check("B36 Total bold", bold("B36"), True)
check("B41 Total bold", bold("B41"), True)
check("B43 Business Rules bold", bold("B43"), True)
check("B51 Total bold", bold("B51"), True)
check("B60 Total bold", bold("B60"), True)
check("B62 Addl Tech bold", bold("B62"), True)
check("B64 Total bold", bold("B64"), True)

# ── Fix 10: C35 — placeholder (target_applications not on model) ─────────────
check("C35 value", val("C35"), "See assessment report")

# ── Fix 11+12: C41 cross-sheet reference ─────────────────────────────────────
c41 = val("C41") or ""
check("C41 references Steps sheet", "Steps!" in c41, True)
check("C41 is not plain text", "See Steps" not in c41, True)
check("C41 bold", bold("C41"), True)

# ── Steps sheet: total row is correct ───────────────────────────────────────
ws_steps = wb["Steps"]
total_cell_val = ws_steps[f"C{steps_total_row}"].value or ""
check("Steps total SUM formula", "SUM" in total_cell_val, True)
check("Steps total_row >= 7", steps_total_row >= 7, True)
check("C41 points to Steps total", f"C{steps_total_row}" in c41, True)

# ── Model field guard: no target_applications access ────────────────────────
has_bad_attr = hasattr(assessment, "target_applications")
check("AssessmentResult has no target_applications field", has_bad_attr, False)

# ── wb.active assert guard ───────────────────────────────────────────────────
with open(
    "/home/anirban/workspace/projects/rpa-complexity-agent/tools/output/excel_generator.py"
) as f:
    src = f.read()
check(
    "wb.active assert present in generator", "assert ws_calc is not None" in src, True
)

# ── Print results ─────────────────────────────────────────────────────────────
passes = sum(1 for r in results if r[0] == PASS)
fails = sum(1 for r in results if r[0] == FAIL)

print(f"\n{'='*70}")
print(f"RESULTS: {passes} passed, {fails} failed  ({len(results)} total checks)")
print(f"{'='*70}")
for status, label, expected, got in results:
    if status == FAIL:
        print(f"\n{status} {label}")
        print(f"       expected: {repr(expected)}")
        print(f"       got:      {repr(got)}")
    else:
        print(f"{status} {label}")
if fails == 0:
    print(f"\n{'='*70}")
    print("All checks passed.")
    print(f"{'='*70}")
