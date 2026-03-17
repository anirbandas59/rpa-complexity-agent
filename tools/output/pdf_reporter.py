"""
PDF summary report generator for RPA complexity assessments.

Generates a professional 2-page PDF with complexity assessment results
and effort/timeline estimates using reportlab.

No LLM involvement — purely deterministic rendering.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

from config.logging_config import get_logger
from core.constants import ComplexityTier
from core.exceptions import OutputGenerationError
from core.models.assessment import AssessmentResult
from core.models.timeline import DeliveryTimeline
from core.scoring.effort_table import calculate_effort

logger = get_logger("pdf_reporter")

# ===========================================================================
# COLOR AND STYLE CONSTANTS
# ===========================================================================

PDF_COLORS = {
    # FIX #3: Each tier now has a semantically correct color.
    # XS/S = green (simple), M = amber (moderate), L = orange (complex), XL = red/purple (critical)
    "XS": HexColor("#16a34a"),     # Green — simple
    "S":  HexColor("#16a34a"),     # Green — simple
    "M":  HexColor("#d97706"),     # Amber — moderate
    "L":  HexColor("#ea580c"),     # Orange — complex (was pure red #FF0000)
    "XL": HexColor("#dc2626"),     # Red — extra large / critical (was purple)
    "header":    HexColor("#2E4057"),
    "subheader": HexColor("#5B9BD5"),
    "row_alt":   HexColor("#F2F2F2"),
    "border":    HexColor("#BFBFBF"),
    "text_dark": HexColor("#1F2937"),
    "text_light": HexColor("#6B7280"),
    "accent":    HexColor("#0EA5E9"),
}

# FIX #6: Status badge colors for the timeline table
STATUS_COLORS = {
    "COMPLETED":   HexColor("#16a34a"),  # Green
    "IN PROGRESS": HexColor("#d97706"),  # Amber
    "NOT STARTED": HexColor("#6B7280"),  # Grey — neutral, not alarming
}

PAGE_WIDTH, PAGE_HEIGHT = A4

# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================


def _get_tier_color(tier: ComplexityTier) -> Color:
    """Get color for a complexity tier."""
    return PDF_COLORS.get(tier.value, PDF_COLORS["M"])


def _tier_badge(
    canvas: rl_canvas.Canvas,
    tier: ComplexityTier,
    x: float,
    y: float,
    width: float = 80,
    height: float = 28,
) -> None:
    """Draw a filled rounded rectangle tier badge.

    Args:
        canvas: reportlab canvas
        tier: Complexity tier
        x: X position (left edge)
        y: Y position (bottom edge, reportlab convention)
        width: Badge width
        height: Badge height
    """
    try:
        bg_color = _get_tier_color(tier)
        canvas.setFillColor(bg_color)
        canvas.setStrokeColor(bg_color)
        canvas.roundRect(x, y, width, height, radius=4, fill=1, stroke=0)

        # FIX #1 (partial): Badge label font size scales with badge height.
        # Small table badges (height=14) use 9pt to match column text.
        # Large hero badge uses 24pt for prominence.
        label_font_size = 9 if height <= 16 else (24 if height >= 40 else 14)
        canvas.setFont("Helvetica-Bold", label_font_size)
        canvas.setFillColor(white)
        canvas.drawCentredString(x + width / 2, y + height / 2 - label_font_size * 0.3, tier.value)
    except Exception as e:
        logger.warning(f"Error drawing tier badge: {e}")


def _status_badge(
    canvas: rl_canvas.Canvas,
    status: str,
    x: float,
    y: float,
    width: float = 72,
    height: float = 12,
) -> None:
    """FIX #6: Draw a colored status pill badge instead of plain text.

    Args:
        canvas: reportlab canvas
        status: Status string (COMPLETED / IN PROGRESS / NOT STARTED)
        x: X position (left edge)
        y: Y position (bottom edge)
        width: Badge width
        height: Badge height
    """
    try:
        bg_color = STATUS_COLORS.get(status, PDF_COLORS["text_light"])
        canvas.setFillColor(bg_color)
        canvas.roundRect(x, y, width, height, radius=3, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.setFillColor(white)
        canvas.drawCentredString(x + width / 2, y + height / 2 - 2.5, status)
    except Exception as e:
        logger.warning(f"Error drawing status badge: {e}")


def _horizontal_rule(
    canvas: rl_canvas.Canvas,
    y: float,
    color: Color = PDF_COLORS["border"],
    thickness: float = 0.5,
) -> None:
    """Draw a full-width horizontal line."""
    try:
        canvas.setStrokeColor(color)
        canvas.setLineWidth(thickness)
        canvas.line(40, y, PAGE_WIDTH - 40, y)
    except Exception as e:
        logger.warning(f"Error drawing horizontal rule: {e}")


def _section_header(
    canvas: rl_canvas.Canvas,
    text: str,
    y: float,
    font_size: int = 11,
) -> float:
    """Draw a section header with navy background bar.

    Returns:
        Y position below the header bar
    """
    try:
        bar_height = font_size + 10
        canvas.setFillColor(PDF_COLORS["header"])
        canvas.rect(40, y - bar_height, PAGE_WIDTH - 80, bar_height, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", font_size)
        canvas.setFillColor(white)
        canvas.drawString(48, y - font_size - 4, text)
        return y - bar_height - 8
    except Exception as e:
        logger.warning(f"Error drawing section header: {e}")
        return y - font_size - 18


def _wrap_text(text: str, max_width: int = 80) -> list[str]:
    """Wrap text to approximate line width."""
    lines = []
    for paragraph in text.split("\n"):
        while len(paragraph) > max_width:
            break_pos = max_width
            for i in range(max_width - 1, 0, -1):
                if paragraph[i] == " ":
                    break_pos = i
                    break
            lines.append(paragraph[:break_pos].rstrip())
            paragraph = paragraph[break_pos:].lstrip()
        if paragraph:
            lines.append(paragraph)
    return lines


# ===========================================================================
# PAGE 1: COMPLEXITY ASSESSMENT RESULT
# ===========================================================================


def _draw_page1(canvas: rl_canvas.Canvas, assessment_result: AssessmentResult) -> None:
    """Draw Page 1 — Complexity Assessment Result."""
    try:
        # TOP HEADER
        y = PAGE_HEIGHT - 50

        canvas.setFont("Helvetica-Bold", 16)
        canvas.setFillColor(PDF_COLORS["header"])
        canvas.drawCentredString(PAGE_WIDTH / 2, y, "RPA COMPLEXITY ASSESSMENT REPORT")

        y -= 20
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(PDF_COLORS["text_light"])
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        canvas.drawCentredString(PAGE_WIDTH / 2, y, f"Generated: {timestamp}")

        y -= 15
        _horizontal_rule(canvas, y)
        y -= 25

        # PROJECT INFO BLOCK
        info_y = y
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(PDF_COLORS["text_light"])

        x_left = 50
        canvas.drawString(x_left, info_y, "Project:")
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        proj_name = assessment_result.project_name[:40]
        canvas.drawString(x_left + 55, info_y, proj_name)

        info_y -= 12
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(PDF_COLORS["text_light"])
        canvas.drawString(x_left, info_y, "RPA Platform:")
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        canvas.drawString(x_left + 55, info_y, assessment_result.rpa_tool.value)

        info_y -= 12
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(PDF_COLORS["text_light"])
        canvas.drawString(x_left, info_y, "Assessed:")
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        assessed_date = assessment_result.created_at.strftime("%Y-%m-%d")
        canvas.drawString(x_left + 55, info_y, assessed_date)

        # Right column
        info_y_right = y
        x_right = PAGE_WIDTH / 2 + 10
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(PDF_COLORS["text_light"])

        canvas.drawString(x_right, info_y_right, "Session ID:")
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        # Available column: page right margin (555pt) minus text start (x_right+65 ≈ 373pt)
        # = ~182pt at 8pt font ≈ 26 chars safely. Truncate only beyond that.
        session_short = (
            assessment_result.session_id[:26] + "..."
            if len(assessment_result.session_id) > 26
            else assessment_result.session_id
        )
        canvas.drawString(x_right + 65, info_y_right, session_short)

        info_y_right -= 12
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(PDF_COLORS["text_light"])
        canvas.drawString(x_right, info_y_right, "Assessor:")
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        canvas.drawString(x_right + 65, info_y_right, "RPA Agent (AI)")

        y -= 55

        # COMPLEXITY RESULT
        y = _section_header(canvas, "COMPLEXITY CLASSIFICATION", y)
        y -= 20

        # FIX #2: Much larger hero badge — was 80×28, now 120×48 with 24pt font.
        # Centered on page, clearly the primary output of the report.
        badge_width = 120
        badge_height = 48
        badge_x = PAGE_WIDTH / 2 - badge_width / 2
        _tier_badge(canvas, assessment_result.complexity_tier, badge_x, y - badge_height, width=badge_width, height=badge_height)
        y -= badge_height + 16

        # Score and confidence
        canvas.setFont("Helvetica-Bold", 13)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        score_text = f"Score: {assessment_result.total_score} / 28"
        canvas.drawCentredString(PAGE_WIDTH / 2, y, score_text)

        y -= 18
        confidence_pct = int(assessment_result.confidence_score * 100)
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(PDF_COLORS["text_light"])
        conf_text = (
            f"Confidence: {confidence_pct}% | High Confidence"
            if confidence_pct >= 80
            else f"Confidence: {confidence_pct}%"
        )
        canvas.drawCentredString(PAGE_WIDTH / 2, y, conf_text)

        y -= 50

        # ATTRIBUTE SCORE BREAKDOWN TABLE
        y = _section_header(canvas, "ATTRIBUTE SCORE BREAKDOWN", y)
        y -= 20

        # Column header bar
        canvas.setFillColor(PDF_COLORS["header"])
        canvas.rect(40, y - 16, PAGE_WIDTH - 80, 16, fill=1, stroke=0)

        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(white)
        col_x = [50, 165, 225, 275, 330]
        headers = ["Attribute", "Raw Value", "Tier", "Weight", "Rationale"]
        for i, header in enumerate(headers):
            canvas.drawString(col_x[i], y - 13, header)

        y -= 22

        # FIX #8: Draw ALL row backgrounds first, then draw ALL text on top.
        # Original code interleaved bg rect + text per row, causing rects to
        # overwrite the previous row's text on alternating rows.
        row_height = 20
        rows_data = list(enumerate(assessment_result.attribute_scores))

        # Pass 1: backgrounds only
        bg_y = y
        for idx, score in rows_data:
            if idx % 2 == 1:
                canvas.setFillColor(PDF_COLORS["row_alt"])
                canvas.rect(40, bg_y - row_height, PAGE_WIDTH - 80, row_height, fill=1, stroke=0)
            bg_y -= row_height

        # Totals row background
        canvas.setFillColor(PDF_COLORS["row_alt"])
        canvas.rect(40, bg_y - row_height, PAGE_WIDTH - 80, row_height, fill=1, stroke=0)

        # Pass 2: content (badges + text) drawn on top of all backgrounds
        # FIX #1: Table row font is 9pt regular — matches header font size.
        canvas.setFont("Helvetica", 9)
        text_y = y
        for idx, score in rows_data:
            canvas.setFillColor(PDF_COLORS["text_dark"])

            # FIX #4: Rationale column — use a wider truncation limit (38 chars)
            # to use the full available column width without overflow.
            attr_name = score.attribute_name[:15]
            canvas.drawString(col_x[0], text_y - 13, attr_name)
            canvas.drawString(col_x[1], text_y - 13, str(score.raw_value))

            # Small tier badge (height=14 → 9pt label via _tier_badge logic)
            _tier_badge(canvas, score.selected_tier, col_x[2] - 10, text_y - row_height + 3, width=40, height=14)

            canvas.setFillColor(PDF_COLORS["text_dark"])
            canvas.setFont("Helvetica", 9)
            canvas.drawString(col_x[3], text_y - 13, str(score.weight))

            # FIX #4: Wider rationale — 38 chars uses the full 155pt column
            rationale = score.tier_rationale[:38]
            if len(score.tier_rationale) > 38:
                rationale += "..."
            canvas.drawString(col_x[4], text_y - 13, rationale)

            text_y -= row_height

        # Totals row text
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        canvas.drawString(col_x[0], text_y - 13, "TOTAL SCORE")
        _tier_badge(canvas, assessment_result.complexity_tier, col_x[2] - 10, text_y - row_height + 3, width=40, height=14)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(col_x[3], text_y - 13, str(assessment_result.total_score))

        y = text_y - row_height - 10

        # REASONING NARRATIVE
        y = _section_header(canvas, "ASSESSMENT REASONING", y)
        y -= 15

        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        wrapped = _wrap_text(assessment_result.reasoning, max_width=80)
        for line in wrapped[:8]:
            canvas.drawString(50, y, line)
            y -= 12

        if len(wrapped) > 8:
            canvas.drawString(50, y, "(continued in Excel report)")

        y -= 20

        # TECH LEAD NOTE
        if assessment_result.requires_tech_lead_review:
            y -= 10
            try:
                canvas.setFillColor(HexColor("#FEF2F2"))
                canvas.rect(40, y - 35, PAGE_WIDTH - 80, 35, fill=1, stroke=1)

                canvas.setStrokeColor(PDF_COLORS["L"])
                canvas.setLineWidth(1.5)
                canvas.rect(40, y - 35, PAGE_WIDTH - 80, 35, fill=0, stroke=1)

                canvas.setFont("Helvetica-Bold", 10)
                canvas.setFillColor(PDF_COLORS["L"])
                canvas.drawString(50, y - 12, "Tech Lead Review Required")

                canvas.setFont("Helvetica", 8)
                canvas.setFillColor(PDF_COLORS["text_dark"])
                canvas.drawString(50, y - 25, "This complex project requires architectural review before execution.")
            except Exception as e:
                logger.warning(f"Error drawing tech lead note: {e}")

        # PAGE FOOTER
        y = 30
        _horizontal_rule(canvas, y + 10)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(PDF_COLORS["text_light"])
        canvas.drawCentredString(
            PAGE_WIDTH / 2,
            y,
            "Page 1 of 2  |  RPA Complexity Assessment Agent  |  Powered by IBM watsonx",
        )

    except Exception as e:
        logger.error(f"Error rendering page 1: {e}")


# ===========================================================================
# PAGE 2: EFFORT ESTIMATE & TIMELINE
# ===========================================================================


def _draw_page2(
    canvas: rl_canvas.Canvas,
    assessment_result: AssessmentResult,
    timeline: DeliveryTimeline,
) -> None:
    """Draw Page 2 — Effort Estimate & Delivery Timeline."""
    try:
        # HEADER
        y = PAGE_HEIGHT - 50

        canvas.setFont("Helvetica-Bold", 16)
        canvas.setFillColor(PDF_COLORS["header"])
        canvas.drawCentredString(PAGE_WIDTH / 2, y, "EFFORT ESTIMATE & DELIVERY TIMELINE")

        y -= 35
        _horizontal_rule(canvas, y)
        y -= 25

        # EFFORT ESTIMATE TABLE
        y = _section_header(canvas, "EFFORT ESTIMATE BY PHASE", y)
        y -= 20

        effort = calculate_effort(assessment_result.complexity_tier, assessment_result.rpa_tool)

        # Column header bar
        canvas.setFillColor(PDF_COLORS["header"])
        canvas.rect(40, y - 16, PAGE_WIDTH - 80, 16, fill=1, stroke=0)

        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(white)
        canvas.drawString(50, y - 13, "Phase")
        canvas.drawString(200, y - 13, "Days")
        canvas.drawString(290, y - 13, "Notes")

        y -= 22

        # FIX #8 (page 2): Same two-pass pattern — backgrounds first, text second.
        row_height = 17
        phase_labels = ["Define", "Build", "UAT", "Deploy"]
        phase_notes = [
            "BA + Developer effort",
            "Core development sprint(s)",
            "Business testing + fixes",
            "Production deployment",
        ]

        # Pass 1: backgrounds
        bg_y = y
        for idx in range(len(phase_labels)):
            if idx % 2 == 1:
                canvas.setFillColor(PDF_COLORS["row_alt"])
                canvas.rect(40, bg_y - row_height, PAGE_WIDTH - 80, row_height, fill=1, stroke=0)
            bg_y -= row_height

        # Totals row background
        canvas.setFillColor(PDF_COLORS["row_alt"])
        canvas.rect(40, bg_y - row_height, PAGE_WIDTH - 80, row_height, fill=1, stroke=0)

        # Pass 2: text
        canvas.setFont("Helvetica", 9)
        text_y = y
        for phase_effort, label, note in zip(effort.phases, phase_labels, phase_notes):
            canvas.setFillColor(PDF_COLORS["text_dark"])
            canvas.drawString(50, text_y - 12, label)
            canvas.drawString(200, text_y - 12, phase_effort.days_display)
            canvas.drawString(290, text_y - 12, note)
            text_y -= row_height

        # Totals row text
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        canvas.drawString(50, text_y - 12, "TOTAL")
        canvas.drawString(200, text_y - 12, effort.total_days_display)
        canvas.drawString(290, text_y - 12, f"({effort.sprint_display})")

        y = text_y - row_height + 5

        y -= 15

        # Adjustment note
        if effort.adjustment_applied:
            canvas.setFont("Helvetica-Oblique", 8)
            canvas.setFillColor(PDF_COLORS["text_light"])
            canvas.drawString(
                50,
                y,
                f"* RPA tool adjustment applied for {assessment_result.rpa_tool.value}",
            )
            y -= 12

        y -= 10

        # DELIVERY TIMELINE TABLE
        y = _section_header(canvas, "FEATURE DELIVERY TIMELINE", y)
        y -= 8

        # FIX #7: Developer meta line now sits inside a light background strip
        # so it reads as a sub-header attached to the table, not floating text.
        meta_strip_height = 18
        canvas.setFillColor(HexColor("#EBF5FB"))
        canvas.rect(40, y - meta_strip_height, PAGE_WIDTH - 80, meta_strip_height, fill=1, stroke=0)

        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(PDF_COLORS["text_dark"])
        meta_text = (
            f"Developer: {timeline.developer}  |  "
            f"Total Hours: {timeline.total_hours:.0f}h  |  "
            f"Total SP: {timeline.total_sp:.2f}"
        )
        canvas.drawString(50, y - 13, meta_text)
        y -= meta_strip_height + 6

        # Feature table header bar
        canvas.setFillColor(PDF_COLORS["header"])
        canvas.rect(40, y - 15, PAGE_WIDTH - 80, 15, fill=1, stroke=0)

        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(white)
        timeline_col_x = [50, 185, 255, 320, 375, 430]
        timeline_headers = ["Feature", "Start", "End", "Hours", "SP", "Status"]
        for i, header in enumerate(timeline_headers):
            canvas.drawString(timeline_col_x[i], y - 11, header)

        y -= 19

        # FIX #8 (feature rows): two-pass — backgrounds first, content second.
        row_height = 16
        max_features = 15
        features_to_draw = timeline.features[:max_features]

        # Pass 1: backgrounds
        bg_y = y
        for idx in range(len(features_to_draw)):
            if idx % 2 == 1:
                canvas.setFillColor(PDF_COLORS["row_alt"])
                canvas.rect(40, bg_y - row_height, PAGE_WIDTH - 80, row_height, fill=1, stroke=0)
            bg_y -= row_height
            if bg_y < 120:
                break

        # Pass 2: text + status badges
        canvas.setFont("Helvetica", 8.5)
        text_y = y
        for idx, feature in enumerate(features_to_draw):
            canvas.setFillColor(PDF_COLORS["text_dark"])

            feature_name = feature.name[:20]
            if len(feature.name) > 20:
                feature_name += "..."
            canvas.drawString(timeline_col_x[0], text_y - 11, feature_name)
            canvas.drawString(timeline_col_x[1], text_y - 11, str(feature.start_date))
            canvas.drawString(timeline_col_x[2], text_y - 11, str(feature.end_date))
            canvas.drawString(timeline_col_x[3], text_y - 11, f"{feature.hours:.0f}")
            canvas.drawString(timeline_col_x[4], text_y - 11, f"{feature.sp:.2f}")

            # FIX #6: Status is now a colored pill badge, not plain text
            status = feature.development_status
            _status_badge(canvas, status, timeline_col_x[5], text_y - row_height + 2, width=72, height=12)

            text_y -= row_height
            if text_y < 120:
                break

        y = text_y

        if len(timeline.features) > max_features:
            canvas.setFont("Helvetica-Oblique", 7)
            canvas.setFillColor(PDF_COLORS["text_light"])
            canvas.drawString(
                50,
                y,
                f"(+{len(timeline.features) - max_features} more features — see Excel report for full list)",
            )

        # PAGE FOOTER — drawn first so the safe zone boundary is established.
        # Rule at y=50, text at y=35. Summary box must sit entirely above y=50.
        _horizontal_rule(canvas, 50)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(PDF_COLORS["text_light"])
        canvas.drawCentredString(
            PAGE_WIDTH / 2,
            35,
            "Page 2 of 2  |  RPA Complexity Assessment Agent  |  Powered by IBM watsonx",
        )

        # SUMMARY BOX — top at y=105, box is 45pt tall, bottom edge at y=60.
        # Leaves a clean 10pt gap above the footer rule at y=50.
        summary_top = 105
        try:
            canvas.setStrokeColor(PDF_COLORS["subheader"])
            canvas.setLineWidth(1)
            canvas.rect(40, summary_top - 45, PAGE_WIDTH - 80, 45, fill=0, stroke=1)

            canvas.setFont("Helvetica-Bold", 10)
            canvas.setFillColor(PDF_COLORS["header"])
            canvas.drawString(50, summary_top - 16, "Assessment Summary")

            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(PDF_COLORS["text_dark"])
            summary = (
                f"Complexity: {assessment_result.complexity_tier.value}  |  "
                f"Score: {assessment_result.total_score}/28  |  "
                f"Effort: {effort.total_days_display}  |  "
                f"Sprints: {effort.sprint_display}"
            )
            canvas.drawString(50, summary_top - 32, summary)
        except Exception as e:
            logger.warning(f"Error drawing summary box: {e}")

    except Exception as e:
        logger.error(f"Error rendering page 2: {e}")


# ===========================================================================
# MAIN PUBLIC FUNCTION
# ===========================================================================


def generate_pdf_report(
    assessment_result: AssessmentResult,
    timeline: DeliveryTimeline,
    output_path: str | None = None,
    session_id: str = "",
) -> str:
    """Generate a 2-page PDF summary report.

    Args:
        assessment_result: Assessment result data
        timeline: Delivery timeline data
        output_path: Output file path (auto-generated if None)
        session_id: Session ID for logging

    Returns:
        Path to generated PDF file

    Raises:
        OutputGenerationError: If PDF generation fails or file is empty
    """
    try:
        # Step 1: Determine output path
        if output_path is None:
            output_dir = Path(__file__).parent.parent.parent / "data" / "outputs"
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            project_name = assessment_result.project_name.replace(" ", "_")[:20]
            output_path = str(output_dir / f"{project_name}_{timestamp}.pdf")

        output_path_obj = Path(output_path)

        # Step 2: Create canvas
        c = rl_canvas.Canvas(output_path, pagesize=A4)

        # Step 3: Draw Page 1
        _draw_page1(c, assessment_result)
        c.showPage()

        # Step 4: Draw Page 2
        _draw_page2(c, assessment_result, timeline)

        # Step 5: Save
        c.save()

        # Step 6: Verify file exists and is non-empty
        if not output_path_obj.exists():
            raise OutputGenerationError("PDF generation failed — file was not created")

        file_size = output_path_obj.stat().st_size
        if file_size == 0:
            raise OutputGenerationError("PDF generation produced empty file")

        # Step 7: Log and return
        log_msg = f"PDF report generated: {output_path} ({file_size:,} bytes)"
        if session_id:
            logger.info(f"[{session_id}] {log_msg}")
        else:
            logger.info(log_msg)

        return output_path

    except OutputGenerationError:
        raise
    except Exception as e:
        raise OutputGenerationError(
            f"PDF generation failed: {str(e)}",
            context={"output_path": output_path},
        ) from e