"""
Excel report generator for RPA complexity assessment.

Creates a 3-sheet Excel workbook mirroring the template:
- Calculator: Complexity scoring and effort estimation
- Steps: Process step decomposition details
- Feature and delivery timeline: Project timeline and features

Uses openpyxl exclusively. Output must be openable in Excel/LibreOffice
without errors or format warnings.

All LLM prompts in tools.output.prompts.
No agents or LLM imports.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from config.logging_config import get_logger
from core.constants import ComplexityTier
from core.exceptions import OutputGenerationError
from core.models.assessment import AssessmentResult
from core.models.timeline import DeliveryTimeline
from core.scoring.weight_matrix import get_weight
from tools.output.step_decomposer import StepDecompositionResult

logger = get_logger("excel_generator")

# ===========================================================================
# COLOR CONSTANTS AND MAPPINGS
# ===========================================================================

COLORS = {
    "XS": "92D050",  # Green
    "S": "FFFFFF",  # White
    "M": "FFFFFF",  # White
    "L": "FF0000",  # Red
    "XL": "7030A0",  # Purple
    "header_blue": "5B9BD5",  # Header background
    "score_row": "D9D9D9",  # Score/total row background
    "completed": "BDEF88",  # Green for completed status
    "in_progress": "FFE699",  # Yellow for in progress
    "not_started": "FFFFFF",  # White for not started
}

TIER_COLUMN_MAP = {
    ComplexityTier.XS: "D",  # XS weight column
    ComplexityTier.S: "G",  # S weight column
    ComplexityTier.M: "J",  # M weight column
    ComplexityTier.L: "M",  # L weight column
    ComplexityTier.XL: "P",  # XL weight column
}

TIER_MARKER_MAP = {
    ComplexityTier.XS: "E",  # XS marker column
    ComplexityTier.S: "H",  # S marker column
    ComplexityTier.M: "K",  # M marker column
    ComplexityTier.L: "N",  # L marker column
    ComplexityTier.XL: "Q",  # XL marker column
}

# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================


def _get_tier_color(tier: ComplexityTier) -> str:
    """Get background color for a complexity tier.

    Args:
        tier: Complexity tier

    Returns:
        Color hex code (without FF prefix)
    """
    color_map = {
        ComplexityTier.XS: COLORS["XS"],
        ComplexityTier.S: COLORS["S"],
        ComplexityTier.M: COLORS["M"],
        ComplexityTier.L: COLORS["L"],
        ComplexityTier.XL: COLORS["XL"],
    }
    return color_map.get(tier, COLORS["S"])


def _set_cell_value(cell, value, bold=False, fill_color: Optional[str] = None):
    """Set cell value with optional formatting.

    Args:
        cell: openpyxl cell
        value: Cell value
        bold: Whether to make text bold
        fill_color: Background color hex (without FF prefix)
    """
    cell.value = value
    if bold:
        cell.font = Font(bold=True)
    if fill_color:
        cell.fill = PatternFill(start_color=f"FF{fill_color}", fill_type="solid")


def _set_cell_formula(cell, formula, bold=False, fill_color: Optional[str] = None):
    """Set cell to a formula with optional formatting.

    Args:
        cell: openpyxl cell
        formula: Formula string (without = prefix)
        bold: Whether to make text bold
        fill_color: Background color hex
    """
    cell.value = f"={formula}"
    if bold:
        cell.font = Font(bold=True)
    if fill_color:
        cell.fill = PatternFill(start_color=f"FF{fill_color}", fill_type="solid")


# ===========================================================================
# DIMENSION CONSTANTS (extracted from output_template.xlsx)
# ===========================================================================

CALC_COL_WIDTHS = {
    "A": 2.86,
    "B": 15.29,
    "C": 6.14,
    "D": 61.71,
    "E": 4.29,
    "F": 3.71,
    "G": 61.71,
    "H": 4.29,
    "I": 4.0,
    "J": 61.71,
    "K": 4.29,
    "L": 4.0,
    "M": 61.71,
    "N": 4.29,
    "O": 4.0,
    "P": 61.71,
    "Q": 4.29,
    "R": 3.71,
    "S": 26.0,
    "T": 11.29,
    "U": 10.14,
    "X": 11.29,
}

CALC_ROW_HEIGHTS = {
    1: 18.0,
    7: 3.75,
    8: 15.75,
    9: 50.25,
    10: 83.25,
    11: 48.0,
    12: 82.5,
    13: 60.0,
    14: 117.0,
    15: 16.5,
    16: 12.75,
    18: 15.0,
    19: 23.25,
    22: 18.0,
    24: 15.75,
    25: 16.5,
    29: 15.75,
    30: 16.5,
    31: 30.0,
    35: 15.75,
}

STEPS_COL_WIDTHS = {
    "A": 63.86,
    "B": 55.57,
    "C": 11.57,
    "D": 62.86,
    "E": 3.86,
    "F": 51.86,
    "G": 48.29,
    "H": 11.57,
    "I": 58.29,
    "J": 4.0,
    "L": 52.86,
    "M": 11.57,
    "N": 33.0,
}

TIMELINE_COL_WIDTHS = {
    "A": 1.71,
    "B": 35.71,
    "C": 21.29,
    "G": 7.0,
    "I": 22.57,
    "J": 15.43,
    "K": 12.14,
    "L": 18.71,
    "M": 30.29,
    "N": 18.71,
    "O": 46.71,
    "P": 8.71,
}

TIMELINE_ROW_HEIGHTS = {
    1: 15.0,
    2: 15.0,
    3: 18.75,
    4: 18.75,
    5: 18.75,
    6: 37.5,
    7: 15.0,
    8: 18.75,
    9: 18.75,
    10: 19.9,
    11: 19.9,
    12: 19.9,
    13: 19.9,
    16: 18.75,
    17: 15.0,
    18: 15.0,
}


# ===========================================================================
# CALCULATOR SHEET
# ===========================================================================


def _write_calculator_sheet(ws, assessment_result: AssessmentResult) -> None:
    """Write the Calculator sheet.

    Args:
        ws: openpyxl worksheet
        assessment_result: Assessment result with scores and tier
    """
    # HEADER SECTION
    # Template: sz=14, bold
    _set_cell_value(ws["D1"], "Sizing estimation for a single Automation", bold=True)
    ws["D1"].font = Font(bold=True, size=14)

    # Template: sz=10, bold
    for cell_ref, text in [
        ("D2", "Instructions: "),
        (
            "D3",
            "1. Determine the complexity of the project by going through each attribute below.",
        ),
        (
            "D4",
            "2. Select the appropriate response from the XS, S, M, L and XL column.",
        ),
        (
            "D5",
            "3. After all responses have been provided, pre-defined rules will calculate the score.",
        ),
        ("D6", "4. If your scenario exceeds the parameter given, consult a Tech Lead."),
    ]:
        ws[cell_ref].value = text
        ws[cell_ref].font = Font(bold=True, size=10)
        ws[cell_ref].alignment = Alignment(horizontal="left")

    ws["D8"].value = "COMPLEXITY ATTRIBUTES"
    ws["D8"].font = Font(bold=True, size=11)
    ws["D8"].alignment = Alignment(horizontal="center")

    # Template: sz=12, bold, center for all tier labels
    for cell_ref, label, fill in [
        ("D9", "XS", COLORS["XS"]),
        ("G9", "S", None),
        ("J9", "M", None),
        ("M9", "L", COLORS["L"]),
        ("P9", "XL", COLORS["XL"]),
    ]:
        ws[cell_ref].value = label
        ws[cell_ref].font = Font(bold=True, size=12)
        ws[cell_ref].alignment = Alignment(horizontal="center")
        if fill:
            ws[cell_ref].fill = PatternFill(start_color=f"FF{fill}", fill_type="solid")

    # Marker cells (sz=12, bold, center)
    for col in ["E", "H", "K", "N", "Q"]:
        ws[f"{col}9"].value = "X"
        ws[f"{col}9"].font = Font(bold=True, size=12)
        ws[f"{col}9"].alignment = Alignment(horizontal="center")

    # FIX: Template has 4 weighting columns S–V labeled S/M/L/XL — XS is excluded.
    # Generated code was writing 5 columns S–W (XS/S/M/L/XL), off by one.
    _set_cell_value(ws["S9"], "Weighting Criteria S")
    _set_cell_value(ws["T9"], "Weighting Criteria M")
    _set_cell_value(ws["U9"], "Weighting Criteria L")
    _set_cell_value(ws["V9"], "Weighting Criteria XL")

    # ATTRIBUTE ROWS (10-14)
    attribute_descriptions = [
        "Number of activities in the process to be automated",
        "Business Rules (decision points resulting in a new flow)",
        "Number of digital layouts (templates) to be used by RPA",
        "Requirement to interface with target applications / interfaces",
        "Additional Technology in scope",
    ]

    # FIX: weight columns S–V map to S/M/L/XL (4 tiers, XS excluded per template).
    # Template column R holds the max-weight value for each attribute.
    # Marker cols E/H/K/N/Q → weight formula cols F/I/L/O/R (one to the right).
    WEIGHT_COLS_ORDERED = ["S", "T", "U", "V"]  # S, M, L, XL weights
    WEIGHT_TIERS_ORDERED = [
        ComplexityTier.S,
        ComplexityTier.M,
        ComplexityTier.L,
        ComplexityTier.XL,
    ]

    for score in assessment_result.attribute_scores:
        row = 9 + score.attribute_id
        attr_desc = attribute_descriptions[score.attribute_id - 1]

        # Description in column D (sz=9, left-aligned, dark text — matches template)
        ws[f"D{row}"].value = attr_desc
        ws[f"D{row}"].font = Font(size=9, color="FF191919")
        ws[f"D{row}"].alignment = Alignment(horizontal="left")

        # Description repeated in selected tier column (same style)
        tier_col = TIER_COLUMN_MAP[score.selected_tier]
        ws[f"{tier_col}{row}"].value = attr_desc
        ws[f"{tier_col}{row}"].font = Font(size=9, color="FF191919")
        ws[f"{tier_col}{row}"].alignment = Alignment(horizontal="left")

        # "X" marker in the correct tier marker column
        marker_col = TIER_MARKER_MAP[score.selected_tier]
        ws[f"{marker_col}{row}"].value = "X"
        ws[f"{marker_col}{row}"].font = Font(bold=True, size=9)
        ws[f"{marker_col}{row}"].alignment = Alignment(horizontal="center")

        # IF formulas in weight-formula columns F/I/L/O/R
        # Each checks whether its paired marker column (E/H/K/N/Q) has "X"
        marker_cols = ["E", "H", "K", "N", "Q"]
        formula_cols = ["F", "I", "L", "O", "R"]
        # Criteria columns: XS→S9, S→T9 … mapped via WEIGHT_COLS_ORDERED (S/M/L/XL)
        # E=XS uses S9 (XS weight stored there)? No — template stores XS weight in R col.
        # Per template inspection: S10=2, T10=4, U10=6, V10=8, R10=8 (max weight = XL value)
        # Formulas in F/I/L/O/R reference S/T/U/V respectively for S/M/L/XL;
        # E/F pair (XS) is special — R column holds the weight used for XS selection.
        # Re-reading template carefully:
        # S10=2(XS wt), T10=4(was "S" label but holds M wt?), …
        # Template: S9="Weighting Criteria S", T9="Criteria M", U9="Criteria L", V9="Criteria XL"
        # So S col = S weight, T = M weight, U = L weight, V = XL weight.
        # Formula cols F/I/L/O/R check markers E/H/K/N/Q and reference S/T/U/V/V respectively.
        # R col (weight for XL) is referenced by both Q (XL marker) and also stored at R col.
        # Actually per template R10=8 is separate — it's the "max weight" display.
        # Keep it simple: mirror the template's IF formulas exactly.
        # E→F uses S col (XS weight = S weight = 2 in template row 10)
        # H→I uses T col (S weight = 4? No, T9="Criteria M"=4)
        # The template stores: S10=2, T10=4, U10=6, V10=8 for attribute 1 (Activities)
        # And R10=8 (separate display of max weight)
        # Marker formulas: F10=IF(E10="X",S10,""), I10=IF(H10="X",T10,"") etc.
        actual_criteria = ["S", "T", "U", "V", "V"]
        for mc, fc, cc in zip(marker_cols, formula_cols, actual_criteria):
            ws[f"{fc}{row}"].value = f'=IF({mc}{row}="X",{cc}{row},"")'

        # Weight values in S/T/U/V (S, M, L, XL weights — 4 columns, XS excluded)
        for tier, col in zip(WEIGHT_TIERS_ORDERED, WEIGHT_COLS_ORDERED):
            w = get_weight(score.attribute_id, tier)
            ws[f"{col}{row}"].value = w
            ws[f"{col}{row}"].alignment = Alignment(horizontal="center")

        # R col: display the XL (max) weight — matches template R10=8, R11=8 etc.
        ws[f"R{row}"].value = get_weight(score.attribute_id, ComplexityTier.XL)

    # TOTALS ROW 16 — red font, COUNTIF in marker cols, SUM in formula cols
    # Template: E16=COUNTIF, F16=SUM, H16=COUNTIF, I16=SUM, etc.
    marker_cols = ["E", "H", "K", "N", "Q"]
    formula_cols = ["F", "I", "L", "O", "R"]
    red_font = Font(color="FFFF0000")
    for mc, fc in zip(marker_cols, formula_cols):
        ws[f"{mc}16"].value = f'=COUNTIF({mc}10:{mc}14,"X")'
        ws[f"{mc}16"].font = red_font
        ws[f"{fc}16"].value = f"=SUM({fc}10:{fc}14)"
        ws[f"{fc}16"].font = red_font

    # SCORE AND CLASSIFICATION (rows 18-19)
    _set_cell_value(ws["D18"], "Score", bold=True)
    ws["D18"].font = Font(bold=True, size=12)

    # FIX: G18 score was absent. Write SUM formula with sz=12.
    ws["G18"].value = "=SUM(F16,I16,L16,O16,R16)"
    ws["G18"].font = Font(size=12)
    ws["G18"].alignment = Alignment(horizontal="center")

    ws["D19"].value = "Project Classification"
    ws["D19"].font = Font(bold=True, size=12)

    # FIX: G19 classification — sz=18, bold, no fill (template has no fill on G19).
    # Previous code set fill_color which produced white fill (FFFFFFFF) overriding template.
    tier_val = assessment_result.complexity_tier.value
    ws["G19"].value = tier_val
    ws["G19"].font = Font(bold=True, size=18)
    ws["G19"].alignment = Alignment(horizontal="center")

    # CLASSIFICATION LOOKUP TABLE — template places this at X11–Z14 (same rows as attributes)
    # FIX: was written to rows 21–24 (10 rows too low). Corrected to rows 11–14.
    lookups = [
        (7, 8, "S"),
        (9, 15, "M"),
        (16, 22, "L"),
        (23, 28, "XL"),
    ]
    for i, (min_score, max_score, tier) in enumerate(lookups):
        row = 11 + i  # rows 11, 12, 13, 14
        ws[f"X{row}"].value = min_score
        ws[f"X{row}"].font = Font(bold=True, size=9)
        ws[f"X{row}"].alignment = Alignment(horizontal="center")
        ws[f"Y{row}"].value = max_score
        ws[f"Y{row}"].font = Font(bold=True, size=9)
        ws[f"Y{row}"].alignment = Alignment(horizontal="center")
        ws[f"Z{row}"].value = tier
        ws[f"Z{row}"].font = Font(bold=True, size=9)
        ws[f"Z{row}"].alignment = Alignment(horizontal="center")
    # Also write the "Equivalence Chart" label at X10 (matches template X10)
    ws["X10"].value = "Equivalence Chart"
    ws["X10"].font = Font(bold=True, size=9)
    ws["X10"].alignment = Alignment(horizontal="center")

    # EFFORT TABLE
    _set_cell_value(
        ws["D22"], "Effort estimates in days from Define to Deploy", bold=True
    )
    _set_cell_value(ws["D23"], "* Estimation of the effort needed...", bold=True)
    _set_cell_value(ws["D24"], "Actual timeline...", bold=True)

    # Phase headers (row 25) — B25 has no fill per template
    ws["B25"].value = "Phase"
    ws["B25"].font = Font(bold=True)

    _set_cell_value(ws["D25"], "XS", bold=True, fill_color=COLORS["XS"])
    _set_cell_value(ws["G25"], "S", bold=True)
    _set_cell_value(ws["J25"], "M", bold=True)
    _set_cell_value(ws["M25"], "L", bold=True, fill_color=COLORS["L"])
    _set_cell_value(ws["P25"], "XL", bold=True, fill_color=COLORS["XL"])

    effort_phases = [
        ("Define *", 3, "7 - 15", 15, 20, 25),
        ("Design & Build", 5, "8 - 15", 25, 30, 40),
        ("UAT *", 1, "3 - 5", 5, 5, 10),
        ("Deploy *", 1, "2 - 5", 5, 5, 5),
        ("Total days", 10, "20 - 40", 50, 60, 80),
        ("2-weeks sprints", 1, "2 - 4", 5, 6, 8),
    ]

    for i, (phase_name, xs, s, m, large, xl) in enumerate(effort_phases, start=1):
        row = 25 + i
        _set_cell_value(ws[f"B{row}"], phase_name)
        _set_cell_value(ws[f"D{row}"], xs)
        _set_cell_value(ws[f"G{row}"], s)
        # FIX: M-tier values must NOT be bold — template treats all tiers equally here.
        # Only the assessed tier column gets highlighted, not hardcoded bold.
        _set_cell_value(ws[f"J{row}"], m)
        _set_cell_value(ws[f"M{row}"], large)
        _set_cell_value(ws[f"P{row}"], xl)

        # Highlight the assessed tier column with bold
        tier_col = TIER_COLUMN_MAP.get(assessment_result.complexity_tier)
        if tier_col:
            ws[f"{tier_col}{row}"].font = Font(bold=True)

    # PROJECT CONTEXT BLOCK
    # target_applications is not a field on AssessmentResult — derive from interface
    # attribute raw_value count, or fall back to the assessment report reference.
    _set_cell_value(ws["B35"], "Applications: ")
    _set_cell_value(ws["C35"], "See assessment report")

    # FIX: bold=True on Total labels to match template
    _set_cell_value(ws["B36"], "Total", bold=True)
    if assessment_result.attribute_scores:
        interface_count = next(
            (
                s.raw_value
                for s in assessment_result.attribute_scores
                if s.attribute_id == 4
            ),
            0,
        )
        _set_cell_value(ws["C36"], interface_count, bold=True)

    _set_cell_value(ws["B38"], "Steps", bold=True)
    _set_cell_value(ws["B39"], '(Sheet "Steps")')

    # FIX: C41 populated by generate_excel_report() after Steps sheet is written,
    # using a cross-sheet reference to the actual Steps total row.
    _set_cell_value(ws["B41"], "Total", bold=True)

    _set_cell_value(ws["B43"], "Business Rules", bold=True)
    _set_cell_value(ws["B51"], "Total", bold=True)
    if assessment_result.attribute_scores:
        rules_count = next(
            (
                s.raw_value
                for s in assessment_result.attribute_scores
                if s.attribute_id == 2
            ),
            0,
        )
        _set_cell_value(ws["C51"], rules_count, bold=True)

    _set_cell_value(ws["B53"], "Layouts: ")
    _set_cell_value(ws["B60"], "Total", bold=True)
    if assessment_result.attribute_scores:
        layout_count = next(
            (
                s.raw_value
                for s in assessment_result.attribute_scores
                if s.attribute_id == 3
            ),
            0,
        )
        _set_cell_value(ws["C60"], layout_count, bold=True)

    _set_cell_value(ws["B62"], "Additional Technology in scope", bold=True)
    _set_cell_value(ws["B64"], "Total", bold=True)
    if assessment_result.attribute_scores:
        tech_count = next(
            (
                s.raw_value
                for s in assessment_result.attribute_scores
                if s.attribute_id == 5
            ),
            0,
        )
        _set_cell_value(ws["C64"], tech_count, bold=True)

    # Apply column widths and row heights from template
    for col, width in CALC_COL_WIDTHS.items():
        ws.column_dimensions[col].width = width
    for row, height in CALC_ROW_HEIGHTS.items():
        ws.row_dimensions[row].height = height
    ws.sheet_format.defaultRowHeight = 15.0


# ===========================================================================
# STEPS SHEET
# ===========================================================================


def _write_steps_sheet(ws, decomposition: StepDecompositionResult) -> int:
    """Write the Steps sheet.

    Returns:
        Row number of the TOTAL row (for cross-sheet reference in Calculator C41).
    """
    _set_cell_value(ws["A1"], decomposition.project_name, bold=True)

    _set_cell_value(ws["B2"], "Step description", bold=True, fill_color="CCCCCC")
    _set_cell_value(ws["C2"], "Step weight", bold=True, fill_color="CCCCCC")
    _set_cell_value(
        ws["D2"], "Comment about reusability", bold=True, fill_color="CCCCCC"
    )

    current_row = 3
    for branch in decomposition.branches:
        _set_cell_value(ws[f"A{current_row}"], branch.branch_name, bold=True)
        current_row += 1
        for step in branch.steps:
            _set_cell_value(ws[f"B{current_row}"], step.description)
            _set_cell_value(ws[f"C{current_row}"], round(step.weight, 1))
            _set_cell_value(ws[f"D{current_row}"], step.reusability_comment)
            current_row += 1
        current_row += 1  # blank row between branches

    subtotal_row = current_row
    ws[f"C{subtotal_row}"].value = f"=SUM(C3:C{current_row - 2})"

    total_row = current_row + 2
    _set_cell_value(ws[f"B{total_row}"], "TOTAL", bold=True)
    ws[f"C{total_row}"].value = f"=SUM(C3:C{total_row - 3})"
    ws[f"C{total_row}"].font = Font(bold=True)

    # Apply column widths from template
    for col, width in STEPS_COL_WIDTHS.items():
        ws.column_dimensions[col].width = width
    ws.sheet_format.defaultRowHeight = 15.0

    return total_row


# ===========================================================================
# TIMELINE SHEET
# ===========================================================================


def _write_timeline_sheet(
    ws, timeline: DeliveryTimeline, assessment_result: AssessmentResult
) -> None:
    """Write the Feature and Delivery Timeline sheet.

    Args:
        ws: openpyxl worksheet
        timeline: Delivery timeline with features
        assessment_result: Assessment result with project info
    """
    # PROJECT HEADER
    _set_cell_value(
        ws["B3"], "PROJECT TITLE", bold=True, fill_color=COLORS["header_blue"]
    )
    _set_cell_value(ws["C3"], assessment_result.project_name)

    _set_cell_value(ws["B4"], "SQUAD", bold=True, fill_color=COLORS["header_blue"])
    _set_cell_value(ws["C4"], timeline.squad)

    _set_cell_value(
        ws["B5"], "BUSINESS ANALYST", bold=True, fill_color=COLORS["header_blue"]
    )
    _set_cell_value(ws["C5"], timeline.business_analyst)

    _set_cell_value(ws["B6"], "DEVELOPER", bold=True, fill_color=COLORS["header_blue"])
    _set_cell_value(ws["C6"], timeline.developer)

    # SP CONVERSION NOTE
    _set_cell_value(ws["B16"], "1 hour = ")
    _set_cell_value(ws["C16"], 0.0666)
    _set_cell_value(ws["D16"], "points")

    # COLUMN HEADERS (row 18)
    headers = [
        ("B18", "FEATURE "),
        ("C18", "SCOPE"),
        ("D18", "ACCEPTANCE STATUS"),
        ("E18", "Start date"),
        ("F18", "End date"),
        ("G18", "SP"),
        ("H18", "Hours"),
        ("I18", "Developer"),
        ("J18", "PRIORITY"),
        ("K18", "COMPLETION %"),
        ("L18", "DEVELOPMENT STATUS"),
        ("M18", "REVIEWER"),
        ("N18", "PEER REVIEW STATUS"),
        ("O18", "REMARKS"),
    ]

    for cell_ref, header_text in headers:
        cell = ws[cell_ref]
        _set_cell_value(cell, header_text, bold=True)
        cell.border = Border(bottom=Side(style="thin"))

    # FEATURE ROWS
    current_row = 19
    for feature in timeline.features:
        _set_cell_value(ws[f"B{current_row}"], feature.name)
        _set_cell_value(ws[f"C{current_row}"], feature.scope)
        _set_cell_value(ws[f"D{current_row}"], feature.acceptance_status)
        _set_cell_value(ws[f"E{current_row}"], feature.start_date)
        _set_cell_value(ws[f"F{current_row}"], feature.end_date)
        _set_cell_formula(ws[f"G{current_row}"], f"ROUND($C$16*H{current_row},2)")
        _set_cell_value(ws[f"H{current_row}"], feature.hours)
        _set_cell_value(ws[f"I{current_row}"], feature.developer)
        _set_cell_value(ws[f"J{current_row}"], feature.priority)
        _set_cell_value(ws[f"K{current_row}"], feature.completion_pct)
        _set_cell_value(ws[f"L{current_row}"], feature.development_status)
        if feature.remarks:
            _set_cell_value(ws[f"O{current_row}"], feature.remarks)
        current_row += 1

    # Apply column widths and row heights from template
    for col, width in TIMELINE_COL_WIDTHS.items():
        ws.column_dimensions[col].width = width
    for row, height in TIMELINE_ROW_HEIGHTS.items():
        ws.row_dimensions[row].height = height
    ws.sheet_format.defaultRowHeight = 15.0


# ===========================================================================
# MAIN PUBLIC FUNCTION
# ===========================================================================


def generate_excel_report(
    assessment_result: AssessmentResult,
    decomposition: StepDecompositionResult,
    timeline: DeliveryTimeline,
    output_path: Optional[str] = None,
    session_id: str = "",
) -> str:
    """Generate a 3-sheet Excel workbook for the assessment result.

    Creates Calculator, Steps, and Feature and Delivery Timeline sheets
    mirroring the template structure.

    Args:
        assessment_result: Assessment result with scoring
        decomposition: Step decomposition result
        timeline: Delivery timeline with features
        output_path: Output file path (auto-generated if None)
        session_id: Session ID for logging

    Returns:
        Path to the generated Excel file

    Raises:
        OutputGenerationError: If file cannot be saved
    """
    # Create workbook
    wb = Workbook()

    # Create/rename sheets
    # wb.active is typed Optional[Worksheet] — assert non-None for type checker
    ws_calc = wb.active
    assert ws_calc is not None, "Workbook has no active sheet"
    ws_calc.title = "Calculator"
    ws_steps = wb.create_sheet("Steps")
    ws_timeline = wb.create_sheet("Feature and delivery timeline")

    # Write each sheet — Steps returns its total row so Calculator C41 can reference it
    _write_calculator_sheet(ws_calc, assessment_result)
    steps_total_row = _write_steps_sheet(ws_steps, decomposition)
    # FIX: C41 cross-sheet reference to actual Steps total row
    ws_calc["C41"].value = f"=Steps!C{steps_total_row}"
    ws_calc["C41"].font = Font(bold=True)
    _write_timeline_sheet(ws_timeline, timeline, assessment_result)

    # Determine output path
    if output_path is None:
        output_dir = Path("data/outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = assessment_result.project_name.replace(" ", "_")[:30]
        output_path = str(output_dir / f"{safe_name}_{timestamp}.xlsx")

    # Save
    try:
        wb.save(output_path)
    except Exception as e:
        raise OutputGenerationError(
            f"Failed to save Excel report: {e}",
            context={"output_path": output_path, "error": str(e)},
        )

    # Log and return
    logger.info(f"[{session_id}] Excel report generated: {output_path}")
    return output_path
