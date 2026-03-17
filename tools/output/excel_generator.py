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

import logging
from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from config.logging_config import get_logger
from core.constants import ComplexityTier, RPATool
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
    "XS": "92D050",      # Green
    "S": "FFFFFF",       # White
    "M": "FFFFFF",       # White
    "L": "FF0000",       # Red
    "XL": "7030A0",      # Purple
    "header_blue": "5B9BD5",     # Header background
    "score_row": "D9D9D9",       # Score/total row background
    "completed": "BDEF88",       # Green for completed status
    "in_progress": "FFE699",     # Yellow for in progress
    "not_started": "FFFFFF",     # White for not started
}

TIER_COLUMN_MAP = {
    ComplexityTier.XS: "D",   # XS weight column
    ComplexityTier.S: "G",    # S weight column
    ComplexityTier.M: "J",    # M weight column
    ComplexityTier.L: "M",    # L weight column
    ComplexityTier.XL: "P",   # XL weight column
}

TIER_MARKER_MAP = {
    ComplexityTier.XS: "E",   # XS marker column
    ComplexityTier.S: "H",    # S marker column
    ComplexityTier.M: "K",    # M marker column
    ComplexityTier.L: "N",    # L marker column
    ComplexityTier.XL: "Q",   # XL marker column
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
# CALCULATOR SHEET
# ===========================================================================


def _write_calculator_sheet(ws, assessment_result: AssessmentResult) -> None:
    """Write the Calculator sheet.

    Args:
        ws: openpyxl worksheet
        assessment_result: Assessment result with scores and tier
    """
    # HEADER SECTION
    _set_cell_value(ws["D1"], "Sizing estimation for a single Automation", bold=True)
    ws["D1"].font = Font(bold=True, size=12)

    _set_cell_value(ws["D2"], "Instructions: ", bold=True)
    _set_cell_value(ws["D3"], "1. Determine the complexity...", bold=True)
    _set_cell_value(ws["D4"], "2. Select the appropriate response...", bold=True)
    _set_cell_value(ws["D5"], "3. After all responses have been provided...", bold=True)
    _set_cell_value(ws["D6"], "4. If your scenario exceeds the parameter...", bold=True)

    _set_cell_value(ws["D8"], "COMPLEXITY ATTRIBUTES", bold=True)

    # TIER HEADERS (row 9)
    _set_cell_value(ws["D9"], "XS", bold=True, fill_color=COLORS["XS"])
    _set_cell_value(ws["G9"], "S", bold=True)
    _set_cell_value(ws["J9"], "M", bold=True)
    _set_cell_value(ws["M9"], "L", bold=True, fill_color=COLORS["L"])
    _set_cell_value(ws["P9"], "XL", bold=True, fill_color=COLORS["XL"])

    # Marker cells
    for col in ["E", "H", "K", "N", "Q"]:
        _set_cell_value(ws[f"{col}9"], "X", bold=True)

    # Weighting criteria headers
    _set_cell_value(ws["S9"], "Weighting Criteria XS")
    _set_cell_value(ws["T9"], "Weighting Criteria S")
    _set_cell_value(ws["U9"], "Weighting Criteria M")
    _set_cell_value(ws["V9"], "Weighting Criteria L")
    _set_cell_value(ws["W9"], "Weighting Criteria XL")

    # ATTRIBUTE ROWS (10-14)
    attribute_descriptions = [
        "Number of activities in the process",
        "Business Rules (decision points)",
        "Number of layouts / digital file templates",
        "Number of target application / interfaces",
        "Additional Technology",
    ]

    for score in assessment_result.attribute_scores:
        row = 9 + score.attribute_id
        attr_desc = attribute_descriptions[score.attribute_id - 1]

        # Write description in column D
        _set_cell_value(ws[f"D{row}"], attr_desc)

        # Write description in selected tier column
        tier_col = TIER_COLUMN_MAP[score.selected_tier]
        _set_cell_value(ws[f"{tier_col}{row}"], attr_desc)

        # Write X in marker cell
        marker_col = TIER_MARKER_MAP[score.selected_tier]
        _set_cell_value(ws[f"{marker_col}{row}"], "X", bold=True)

        # Write formulas in weight columns (F, I, L, O, R) - one column after marker
        # These formulas check if the marker column has X and if so, sum the weight
        marker_cols = ["E", "H", "K", "N", "Q"]
        weight_cols = ["F", "I", "L", "O", "R"]
        weight_criteria = ["S", "T", "U", "V", "W"]
        for marker_col, weight_col, criteria_col in zip(marker_cols, weight_cols, weight_criteria):
            _set_cell_formula(ws[f"{weight_col}{row}"], f'IF({marker_col}{row}="X",{criteria_col}{row},"")')

        # Write weight values in S/T/U/V/W columns
        weights = [
            get_weight(score.attribute_id, ComplexityTier.XS),
            get_weight(score.attribute_id, ComplexityTier.S),
            get_weight(score.attribute_id, ComplexityTier.M),
            get_weight(score.attribute_id, ComplexityTier.L),
            get_weight(score.attribute_id, ComplexityTier.XL),
        ]
        for i, (col, weight) in enumerate(zip(["S", "T", "U", "V", "W"], weights)):
            _set_cell_value(ws[f"{col}{row}"], weight)

    # TOTALS ROW (row 16)
    for col in ["E", "H", "K", "N", "Q"]:
        col_num = ord(col) - ord("A") + 1
        col_letter = get_column_letter(col_num + 1)  # Weight column next to marker
        _set_cell_formula(ws[f"{col}{16}"], f"COUNTIF({col}10:{col}14,\"X\")")
        ws[f"{col}{16}"].font = Font(color="FF0000")  # Red font
        _set_cell_formula(ws[f"{col_letter}{16}"], f"SUM({col_letter}10:{col_letter}14)")
        ws[f"{col_letter}{16}"].font = Font(color="FF0000")

    # SCORE AND CLASSIFICATION (rows 18-19)
    _set_cell_value(ws["D18"], "Score", bold=True)
    _set_cell_formula(ws["G18"], "SUM(F16,I16,L16,O16,R16)")

    _set_cell_value(ws["D19"], "Project Classification", bold=True)
    _set_cell_value(
        ws["G19"], assessment_result.complexity_tier.value, bold=True,
        fill_color=_get_tier_color(assessment_result.complexity_tier)
    )

    # CLASSIFICATION LOOKUP TABLE (rows 21-24, columns X-Z)
    lookups = [
        (7, 8, "S"),
        (9, 15, "M"),
        (16, 22, "L"),
        (23, 28, "XL"),
    ]
    for i, (min_score, max_score, tier) in enumerate(lookups, start=1):
        row = 20 + i
        _set_cell_value(ws[f"X{row}"], min_score)
        _set_cell_value(ws[f"Y{row}"], max_score)
        _set_cell_value(ws[f"Z{row}"], tier)

    # EFFORT TABLE
    _set_cell_value(ws["D22"], "Effort estimates in days from Define to Deploy", bold=True)
    _set_cell_value(ws["D23"], "* Estimation of the effort needed...", bold=True)
    _set_cell_value(ws["D24"], "Actual timeline...", bold=True)

    # Phase headers (row 25)
    _set_cell_value(ws["B25"], "Phase", bold=True, fill_color="CCCCCC")
    _set_cell_value(ws["D25"], "XS", bold=True, fill_color=COLORS["XS"])
    _set_cell_value(ws["G25"], "S", bold=True)
    _set_cell_value(ws["J25"], "M", bold=True)
    _set_cell_value(ws["M25"], "L", bold=True, fill_color=COLORS["L"])
    _set_cell_value(ws["P25"], "XL", bold=True, fill_color=COLORS["XL"])

    # Effort data
    effort_phases = [
        ("Define *", 3, "7 - 15", 15, 20, 25),
        ("Design & Build", 5, "8 - 15", 25, 30, 40),
        ("UAT *", 1, "3 - 5", 5, 5, 10),
        ("Deploy *", 1, "2 - 5", 5, 5, 5),
        ("Total days", 10, "20 - 40", 50, 60, 80),
        ("2-weeks sprints", 1, "2 - 4", 5, 6, 8),
    ]

    for i, (phase_name, xs, s, m, l, xl) in enumerate(effort_phases, start=1):
        row = 25 + i
        _set_cell_value(ws[f"B{row}"], phase_name)
        _set_cell_value(ws[f"D{row}"], xs)
        _set_cell_value(ws[f"G{row}"], s)
        _set_cell_value(ws[f"J{row}"], m)
        _set_cell_value(ws[f"M{row}"], l)
        _set_cell_value(ws[f"P{row}"], xl)

        # Bold the column matching assessed tier
        tier_col = TIER_COLUMN_MAP.get(assessment_result.complexity_tier)
        if tier_col:
            ws[f"{tier_col}{row}"].font = Font(bold=True)

    # PROJECT CONTEXT BLOCK
    _set_cell_value(ws["B35"], "Applications: ")
    _set_cell_value(ws["C35"], "See assessment report")
    _set_cell_value(ws["B36"], "Total")
    if assessment_result.attribute_scores:
        interface_count = next(
            (s.raw_value for s in assessment_result.attribute_scores if s.attribute_id == 4),
            0
        )
        _set_cell_value(ws["C36"], interface_count)

    _set_cell_value(ws["B38"], "Steps")
    _set_cell_value(ws["B39"], '(Sheet "Steps")')
    _set_cell_value(ws["B41"], "Total")
    _set_cell_value(ws["C41"], "See Steps sheet")

    _set_cell_value(ws["B43"], "Business Rules", bold=True)
    _set_cell_value(ws["B51"], "Total")
    if assessment_result.attribute_scores:
        rules_count = next(
            (s.raw_value for s in assessment_result.attribute_scores if s.attribute_id == 2),
            0
        )
        _set_cell_value(ws["C51"], rules_count)

    _set_cell_value(ws["B53"], "Layouts: ")
    _set_cell_value(ws["B60"], "Total")
    if assessment_result.attribute_scores:
        layout_count = next(
            (s.raw_value for s in assessment_result.attribute_scores if s.attribute_id == 3),
            0
        )
        _set_cell_value(ws["C60"], layout_count)

    _set_cell_value(ws["B62"], "Additional Technology in scope", bold=True)
    _set_cell_value(ws["B64"], "Total")
    if assessment_result.attribute_scores:
        tech_count = next(
            (s.raw_value for s in assessment_result.attribute_scores if s.attribute_id == 5),
            0
        )
        _set_cell_value(ws["C64"], tech_count)


# ===========================================================================
# STEPS SHEET
# ===========================================================================


def _write_steps_sheet(ws, decomposition: StepDecompositionResult) -> None:
    """Write the Steps sheet.

    Args:
        ws: openpyxl worksheet
        decomposition: Step decomposition result
    """
    # Sheet title
    _set_cell_value(ws["A1"], decomposition.project_name, bold=True)

    # Header row
    _set_cell_value(ws["B2"], "Step description", bold=True, fill_color="CCCCCC")
    _set_cell_value(ws["C2"], "Step weight", bold=True, fill_color="CCCCCC")
    _set_cell_value(ws["D2"], "Comment about reusability", bold=True, fill_color="CCCCCC")

    # Write branches and steps
    current_row = 3
    total_weight = 0

    for branch in decomposition.branches:
        # Branch header
        _set_cell_value(ws[f"A{current_row}"], branch.branch_name, bold=True)
        current_row += 1

        # Steps in branch
        for step in branch.steps:
            _set_cell_value(ws[f"B{current_row}"], step.description)
            _set_cell_value(ws[f"C{current_row}"], round(step.weight, 1))
            _set_cell_value(ws[f"D{current_row}"], step.reusability_comment)
            total_weight += step.weight
            current_row += 1

        # Blank row between branches
        current_row += 1

    # Subtotal row
    subtotal_row = current_row
    _set_cell_formula(ws[f"C{subtotal_row}"], f"SUM(C3:C{current_row - 2})")

    # Total row
    current_row += 2
    _set_cell_value(ws[f"B{current_row}"], "TOTAL", bold=True)
    _set_cell_formula(ws[f"C{current_row}"], f"SUM(C3:C{current_row - 3})")


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
    _set_cell_value(ws["B3"], "PROJECT TITLE", bold=True, fill_color=COLORS["header_blue"])
    _set_cell_value(ws["C3"], assessment_result.project_name)

    _set_cell_value(ws["B4"], "SQUAD", bold=True, fill_color=COLORS["header_blue"])
    _set_cell_value(ws["C4"], timeline.squad)

    _set_cell_value(ws["B5"], "BUSINESS ANALYST", bold=True, fill_color=COLORS["header_blue"])
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

    # Set column widths
    col_widths = {
        "B": 45,
        "C": 12,
        "D": 18,
        "E": 12,
        "F": 12,
        "G": 8,
        "H": 8,
        "I": 20,
        "J": 10,
        "K": 14,
        "L": 18,
        "M": 15,
        "N": 18,
        "O": 30,
    }
    for col, width in col_widths.items():
        ws.column_dimensions[col].width = width


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
    ws_calc = wb.active
    ws_calc.title = "Calculator"
    ws_steps = wb.create_sheet("Steps")
    ws_timeline = wb.create_sheet("Feature and delivery timeline")

    # Write each sheet
    _write_calculator_sheet(ws_calc, assessment_result)
    _write_steps_sheet(ws_steps, decomposition)
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
