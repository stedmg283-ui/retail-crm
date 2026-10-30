"""ReportLab GST tax invoice PDF generator."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.amount_words import amount_in_words


def format_inr(amount) -> str:
    """Format as Indian Rupee string with two decimals."""
    d = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    # Simple Indian grouping for display
    s = f"{d:,.2f}"
    return f"₹ {s}"


def generate_invoice_pdf(invoice, output_path: str | Path | None = None) -> str:
    """
    Render a GST tax invoice PDF for `invoice`.
    Returns absolute path to the written PDF.
    """
    invoices_dir = Path(current_app.config["INVOICES_DIR"])
    invoices_dir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        safe_num = invoice.invoice_number.replace("/", "-")
        output_path = invoices_dir / f"{safe_num}_v{invoice.pdf_version}.pdf"
    else:
        output_path = Path(output_path)

    shop_name = current_app.config["SHOP_NAME"]
    shop_address = current_app.config["SHOP_ADDRESS"]
    shop_gstin = current_app.config["SHOP_GSTIN"]
    shop_phone = current_app.config["SHOP_PHONE"]
    shop_email = current_app.config["SHOP_EMAIL"]
    logo_path = current_app.config.get("LOGO_PATH", "")

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ShopTitle", fontSize=16, leading=20, alignment=TA_CENTER, spaceAfter=2, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Center", fontSize=9, leading=12, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Small", fontSize=8, leading=10, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="SmallRight", fontSize=8, leading=10, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="Label", fontSize=10, leading=13, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Words", fontSize=8, leading=11, fontName="Helvetica-Oblique"))

    story = []

    # Header
    header_bits = []
    if logo_path and os.path.isfile(logo_path):
        try:
            header_bits.append(Image(logo_path, width=40 * mm, height=18 * mm))
        except Exception:
            pass
    header_bits.append(Paragraph(shop_name, styles["ShopTitle"]))
    header_bits.append(Paragraph(shop_address, styles["Center"]))
    header_bits.append(
        Paragraph(
            f"GSTIN: {shop_gstin} &nbsp;&nbsp; Phone: {shop_phone} &nbsp;&nbsp; {shop_email}",
            styles["Center"],
        )
    )
    header_bits.append(Paragraph("<b>TAX INVOICE</b>", styles["Center"]))
    for h in header_bits:
        story.append(h)
    story.append(Spacer(1, 6 * mm))

    # Meta + bill-to
    inv_date = invoice.invoice_date.strftime("%d-%m-%Y") if invoice.invoice_date else ""
    meta_data = [
        [
            Paragraph(
                f"<b>Invoice No:</b> {invoice.invoice_number}<br/>"
                f"<b>Date:</b> {inv_date}<br/>"
                f"<b>Place of supply:</b> {'Intra-state (CGST+SGST)' if invoice.place_of_supply == 'intra' else 'Inter-state (IGST)'}",
                styles["Small"],
            ),
            Paragraph(
                f"<b>Bill To</b><br/>"
                f"{invoice.customer_name or 'Walk-in Customer'}<br/>"
                f"Phone: {invoice.customer_phone or '—'}<br/>"
                f"State code: {invoice.customer_state_code or current_app.config.get('SHOP_STATE_CODE', '29')}",
                styles["Small"],
            ),
        ]
    ]
    meta = Table(meta_data, colWidths=[90 * mm, 90 * mm])
    meta.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 4 * mm))

    # Line items
    is_intra = invoice.place_of_supply != "inter"
    if is_intra:
        headers = ["#", "Item", "HSN", "Qty", "Rate", "Disc", "Taxable", "CGST", "SGST", "Amount"]
        col_w = [8 * mm, 42 * mm, 14 * mm, 12 * mm, 18 * mm, 14 * mm, 18 * mm, 16 * mm, 16 * mm, 20 * mm]
    else:
        headers = ["#", "Item", "HSN", "Qty", "Rate", "Disc", "Taxable", "IGST", "Amount"]
        col_w = [8 * mm, 50 * mm, 16 * mm, 14 * mm, 20 * mm, 14 * mm, 20 * mm, 18 * mm, 22 * mm]

    rows = [headers]
    for i, ln in enumerate(invoice.lines, start=1):
        name = ln.item_name
        if ln.size:
            name = f"{name} ({ln.size})"
        base = [
            str(i),
            name[:40],
            ln.hsn or "",
            f"{Decimal(ln.quantity):.2f}".rstrip("0").rstrip("."),
            format_inr(ln.unit_price).replace("₹ ", ""),
            format_inr(ln.discount).replace("₹ ", "") if ln.discount else "—",
            format_inr(ln.taxable_amount).replace("₹ ", ""),
        ]
        if is_intra:
            rate = Decimal(ln.gst_rate or 0) / 2
            base += [
                f"{format_inr(ln.cgst_amount).replace('₹ ', '')}\n({rate}%)",
                f"{format_inr(ln.sgst_amount).replace('₹ ', '')}\n({rate}%)",
            ]
        else:
            base.append(
                f"{format_inr(ln.igst_amount).replace('₹ ', '')}\n({ln.gst_rate}%)"
            )
        base.append(format_inr(ln.line_total).replace("₹ ", ""))
        rows.append(base)

    items = Table(rows, colWidths=col_w, repeatRows=1)
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(items)
    story.append(Spacer(1, 4 * mm))

    # Totals
    totals_rows = [
        ["Taxable Value", format_inr(invoice.taxable_total)],
    ]
    if is_intra:
        totals_rows += [
            ["CGST", format_inr(invoice.cgst_total)],
            ["SGST", format_inr(invoice.sgst_total)],
        ]
    else:
        totals_rows.append(["IGST", format_inr(invoice.igst_total)])
    if invoice.discount_amount and Decimal(invoice.discount_amount) > 0:
        totals_rows.append(["Invoice Discount", f"- {format_inr(invoice.discount_amount)}"])
    totals_rows.append(["Grand Total", format_inr(invoice.grand_total)])

    totals = Table(totals_rows, colWidths=[40 * mm, 35 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(totals)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(amount_in_words(invoice.grand_total), styles["Words"]))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Thank you for shopping at Rabya Collection!", styles["Center"]))
    story.append(Paragraph("This is a computer-generated invoice.", styles["Center"]))

    doc.build(story)
    return str(output_path.resolve())
