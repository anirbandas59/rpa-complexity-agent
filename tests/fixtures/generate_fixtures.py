"""Generate PDF test fixtures for pdf_parser tests."""

from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors


def generate_simple_pdf():
    """Generate sample_simple.pdf with 2 pages of text content."""
    output_path = Path(__file__).parent.parent.parent / "data" / "sample_pdds" / "sample_simple.pdf"

    # Use canvas-based approach to ensure 2 distinct pages
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    # PAGE 1
    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "Process Overview")
    y -= 40

    c.setFont("Helvetica", 11)
    text_lines = [
        "This is a Process Design Document (PDD) for an automated RPA process",
        "involving integration with SAP and Excel systems. The process handles",
        "order fulfillment and inventory management.",
        "",
        "Process Steps:",
        "1. Extract order data from SAP system using OData API",
        "2. Validate inventory levels against Excel warehouse database",
        "3. Generate picking lists and shipping labels",
        "4. Update order status in SAP with confirmation",
        "5. Archive completed orders in Excel archives",
    ]

    for line in text_lines:
        c.drawString(50, y, line)
        y -= 20

    c.showPage()  # Force page break

    # PAGE 2
    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "Business Rules")
    y -= 40

    c.setFont("Helvetica", 11)
    rules_lines = [
        "Rule 1: Orders exceeding 50 items must be split into multiple",
        "shipments.",
        "",
        "Rule 2: Items out of stock must be flagged and escalated to the",
        "procurement team within 4 hours of order receipt.",
        "",
        "Rule 3: All orders must be processed within 24 hours of receipt",
        "unless marked as expedited.",
    ]

    for line in rules_lines:
        c.drawString(50, y, line)
        y -= 20

    c.save()
    print(f"Created {output_path}")


def generate_table_pdf():
    """Generate sample_table.pdf with table data."""
    output_path = Path(__file__).parent.parent.parent / "data" / "sample_pdds" / "sample_table.pdf"

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=colors.HexColor("#003366"),
        spaceAfter=12,
    )

    elements.append(Paragraph("System Interfaces", title_style))
    elements.append(Spacer(1, 0.2 * inch))

    # Create a table with 3 columns and 4 rows (including header)
    table_data = [
        ["System Name", "Interface Type", "Frequency"],
        ["SAP ECC", "REST API", "Real-time"],
        ["Excel Warehouse DB", "ODBC", "Daily Batch"],
        ["Email Service", "SMTP", "On-demand"],
    ]

    # Create table with styling
    table = Table(table_data, colWidths=[2 * inch, 2 * inch, 2 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )

    elements.append(table)
    doc.build(elements)
    print(f"Created {output_path}")


if __name__ == "__main__":
    output_dir = Path(__file__).parent.parent.parent / "data" / "sample_pdds"
    output_dir.mkdir(parents=True, exist_ok=True)
    generate_simple_pdf()
    generate_table_pdf()
    print("All fixtures generated successfully!")
