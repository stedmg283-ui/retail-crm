"""ReportLab PDF generation for invoices, supplier bills, payroll."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
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


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name="ShopTitle", fontSize=16, leading=20, alignment=TA_CENTER, spaceAfter=4, fontName="Helvetica-Bold"))
    ss.add(ParagraphStyle(name="SubCenter", fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.grey))
    ss.add(ParagraphStyle(name="Section", fontSize=11, leading=14, fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=4))
    ss.add(ParagraphStyle(name="Right", fontSize=9, alignment=TA_RIGHT))
    ss.add(ParagraphStyle(name="Small", fontSize=8, leading=10))
    ss.add(ParagraphStyle(name="NormalLeft", fontSize=9, leading=12, alignment=TA_LEFT))
    return ss


def _shop_header(story, styles):
    logo = current_app.config.get("LOGO_PATH")
    if logo and Path(logo).exists():
        try:
            img = Image(logo, width=28 * mm, height=28 * mm)
            img.hAlign = "CENTER"
            story.append(img)
        except Exception:
            pass
    story.append(Paragraph(current_app.config["SHOP_NAME"], styles["ShopTitle"]))
    story.append(Paragraph(current_app.config["SHOP_ADDRESS"], styles["SubCenter"]))
    story.append(
        Paragraph(
            f"GSTIN: {current_app.config['SHOP_GSTIN']} &nbsp;|&nbsp; "
            f"Ph: {current_app.config['SHOP_PHONE']}",
            styles["SubCenter"],
        )
    )
    story.append(Spacer(1, 6 * mm))


def generate_invoice_pdf(invoice, dest_path: str | Path | None = None) -> bytes:
    """Generate branded tax invoice PDF. Returns bytes; optionally writes to dest_path."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = _styles()
    story = []
    _shop_header(story, styles)
    story.append(Paragraph("TAX INVOICE", styles["ShopTitle"]))
    story.append(Spacer(1, 3 * mm))

    meta = [
        [
            Paragraph(f"<b>Invoice No:</b> {invoice.invoice_number}", styles["NormalLeft"]),
            Paragraph(f"<b>Date:</b> {invoice.invoice_date.strftime('%d-%m-%Y')}", styles["Right"]),
        ],
        [
            Paragraph(
                f"<b>Bill To:</b> {invoice.customer_name or 'Walk-in Customer'}<br/>"
                f"Phone: {invoice.customer_phone or '—'}<br/>"
                f"Place of supply: {'Inter-state (IGST)' if invoice.place_of_supply == 'inter' else 'Intra-state (CGST+SGST)'}",
                styles["NormalLeft"],
            ),
            Paragraph("", styles["Right"]),
        ],
    ]
    t = Table(meta, colWidths=[110 * mm, 70 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))

    header = ["#", "Item", "Size", "HSN", "Qty", "Rate", "Disc", "GST%", "Taxable", "Tax", "Total"]
    data = [header]
    for i, ln in enumerate(invoice.lines, 1):
        tax = float(ln.cgst_amount) + float(ln.sgst_amount) + float(ln.igst_amount)
        data.append(
            [
                str(i),
                ln.item_name[:32],
                ln.size or "—",
                ln.hsn or "—",
                f"{float(ln.quantity):g}",
                f"{float(ln.unit_price):.2f}",
                f"{float(ln.discount):.2f}",
                f"{float(ln.gst_rate):g}",
                f"{float(ln.taxable_amount):.2f}",
                f"{tax:.2f}",
                f"{float(ln.line_total):.2f}",
            ]
        )
    col_w = [8 * mm, 42 * mm, 12 * mm, 14 * mm, 12 * mm, 18 * mm, 14 * mm, 12 * mm, 18 * mm, 14 * mm, 18 * mm]
    table = Table(data, colWidths=col_w, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    totals = [
        ["Taxable Amount", f"₹ {float(invoice.taxable_total):,.2f}"],
        ["CGST", f"₹ {float(invoice.cgst_total):,.2f}"],
        ["SGST", f"₹ {float(invoice.sgst_total):,.2f}"],
        ["IGST", f"₹ {float(invoice.igst_total):,.2f}"],
        ["Discount", f"₹ {float(invoice.discount_amount):,.2f}"],
        ["Grand Total", f"₹ {float(invoice.grand_total):,.2f}"],
    ]
    tt = Table(totals, colWidths=[40 * mm, 35 * mm])
    tt.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    tt.hAlign = "RIGHT"
    story.append(tt)
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f"<b>Amount in words:</b> {amount_in_words(invoice.grand_total)}",
            styles["NormalLeft"],
        )
    )
    if invoice.notes:
        story.append(Paragraph(f"<b>Notes:</b> {invoice.notes}", styles["Small"]))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("This is a computer-generated invoice.", styles["SubCenter"]))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    if dest_path:
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        Path(dest_path).write_bytes(pdf_bytes)
    return pdf_bytes


def generate_supplier_bill_pdf(po, dest_path: str | Path | None = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = _styles()
    story = []
    _shop_header(story, styles)
    story.append(Paragraph("SUPPLIER BILL / PURCHASE RECORD", styles["ShopTitle"]))
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            f"<b>Bill No:</b> {po.bill_number} &nbsp; <b>Date:</b> {po.po_date.strftime('%d-%m-%Y')}<br/>"
            f"<b>Supplier:</b> {po.supplier.name}<br/>"
            f"Contact: {po.supplier.contact_name or '—'} | Phone: {po.supplier.phone or '—'}<br/>"
            f"GSTIN: {po.supplier.gstin or '—'}<br/>"
            f"<b>Payment status:</b> {po.payment_status.upper()}",
            styles["NormalLeft"],
        )
    )
    story.append(Spacer(1, 4 * mm))
    data = [["#", "Item", "Qty", "Unit Cost", "Line Total"]]
    for i, ln in enumerate(po.lines, 1):
        data.append(
            [
                str(i),
                ln.item_name,
                f"{float(ln.quantity):g}",
                f"₹ {float(ln.unit_cost):,.2f}",
                f"₹ {float(ln.line_total()):,.2f}",
            ]
        )
    table = Table(data, colWidths=[12 * mm, 90 * mm, 25 * mm, 30 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f"<b>Subtotal:</b> ₹ {float(po.subtotal()):,.2f} &nbsp; "
            f"<b>Paid:</b> ₹ {float(po.amount_paid()):,.2f} &nbsp; "
            f"<b>Balance:</b> ₹ {float(po.balance_due()):,.2f}",
            styles["NormalLeft"],
        )
    )
    if po.notes:
        story.append(Paragraph(f"Notes: {po.notes}", styles["Small"]))
    doc.build(story)
    pdf_bytes = buf.getvalue()
    if dest_path:
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        Path(dest_path).write_bytes(pdf_bytes)
    return pdf_bytes


def generate_payroll_pdf(year: int, month: int, summaries, dest_path: str | Path | None = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = _styles()
    story = []
    _shop_header(story, styles)
    story.append(Paragraph(f"PAYROLL SUMMARY — {month:02d}/{year}", styles["ShopTitle"]))
    story.append(Spacer(1, 4 * mm))
    data = [["Employee", "Role", "Hours", "Reg Hrs", "OT Hrs", "Total Pay (₹)"]]
    for s in summaries:
        data.append(
            [
                s.employee.name,
                s.employee.role,
                f"{s.total_hours:.2f}",
                f"{s.total_regular_hours:.2f}",
                f"{s.total_ot_hours:.2f}",
                f"{float(s.total_pay):,.2f}",
            ]
        )
    table = Table(data, colWidths=[40 * mm, 35 * mm, 22 * mm, 22 * mm, 22 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f3460")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    pdf_bytes = buf.getvalue()
    if dest_path:
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        Path(dest_path).write_bytes(pdf_bytes)
    return pdf_bytes
