"""Invoice creation, numbering, same-day dedup merge."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from flask import current_app

from app.config import financial_year
from app.extensions import db
from app.models.customer import Customer
from app.models.sales import Invoice, InvoiceLine
from app.services.phone import normalize_phone
from app.services.pdfs import generate_invoice_pdf


def next_invoice_number(on_date: date | None = None) -> str:
    """Sequential FY-based numbers: RC/2026-27/0001."""
    on_date = on_date or date.today()
    fy = financial_year(on_date)
    prefix = current_app.config.get("INVOICE_PREFIX", "RC")
    pattern = f"{prefix}/{fy}/"
    last = (
        Invoice.query.filter(Invoice.invoice_number.like(f"{pattern}%"))
        .order_by(Invoice.invoice_number.desc())
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(last.invoice_number.rsplit("/", 1)[-1]) + 1
        except ValueError:
            seq = 1
    return f"{pattern}{seq:04d}"


def get_or_create_customer(phone: str | None, name: str | None = None) -> Customer | None:
    norm = normalize_phone(phone)
    if not norm:
        return None
    cust = Customer.query.filter_by(phone=norm).first()
    if cust:
        if name and not cust.name:
            cust.name = name
        return cust
    cust = Customer(phone=norm, name=name)
    db.session.add(cust)
    db.session.flush()
    return cust


def find_same_day_invoice(phone: str, on_date: date | None = None) -> Invoice | None:
    """Same-day dedup: existing non-void invoice for this phone today."""
    on_date = on_date or date.today()
    norm = normalize_phone(phone)
    if not norm:
        return None
    return (
        Invoice.query.filter(
            Invoice.customer_phone == norm,
            Invoice.invoice_date == on_date,
            Invoice.status != "void",
        )
        .order_by(Invoice.id.desc())
        .first()
    )


def _line_from_dict(d: dict, default_gst: float, default_hsn: str) -> InvoiceLine:
    return InvoiceLine(
        item_name=d["item_name"],
        size=d.get("size") or None,
        hsn=d.get("hsn") or default_hsn,
        quantity=Decimal(str(d.get("quantity", 1))),
        unit_price=Decimal(str(d.get("unit_price", 0))),
        discount=Decimal(str(d.get("discount", 0))),
        gst_rate=Decimal(str(d.get("gst_rate", default_gst))),
    )


def create_or_merge_sale(
    *,
    customer_phone: str | None,
    customer_name: str | None = None,
    lines: list[dict],
    place_of_supply: str = "intra",
    customer_state_code: str | None = None,
    discount_amount: Decimal | float = 0,
    notes: str | None = None,
    invoice_date: date | None = None,
    send_now: bool = False,
) -> tuple[Invoice, bool]:
    """
    Create a new invoice OR append lines to today's invoice for the same phone.

    Returns (invoice, merged: bool).

    WhatsApp send policy (documented choice):
      - Same-day merge never triggers an automatic re-send.
      - New invoices are marked whatsapp_status=pending.
      - SEND_ON_CREATE=true will send immediately for *new* invoices only.
      - Otherwise use the UI "Send now" button, or `flask send-pending`
        (respects PENDING_SEND_DEBOUNCE_MINUTES) as an end-of-day / debounce job.
    """
    on_date = invoice_date or date.today()
    default_gst = float(current_app.config.get("DEFAULT_GST_RATE", 5))
    default_hsn = current_app.config.get("DEFAULT_HSN", "6211")
    norm = normalize_phone(customer_phone)

    existing = find_same_day_invoice(norm, on_date) if norm else None
    if existing:
        for d in lines:
            existing.lines.append(_line_from_dict(d, default_gst, default_hsn))
        existing.discount_amount = Decimal(str(existing.discount_amount or 0)) + Decimal(
            str(discount_amount or 0)
        )
        if customer_name and not existing.customer_name:
            existing.customer_name = customer_name
        if notes:
            existing.notes = ((existing.notes or "") + "\n" + notes).strip()
        existing.recalculate()
        existing.updated_at = datetime.utcnow()
        # Regenerated PDF; do NOT auto-send again
        pdf_path = _pdf_path_for(existing)
        generate_invoice_pdf(existing, dest_path=pdf_path)
        existing.pdf_path = str(pdf_path)
        # Keep pending if never sent; leave sent alone (manual re-send if needed)
        if existing.whatsapp_status == "sent":
            existing.whatsapp_status = "pending"  # content changed; queue for send-pending / Send now
        db.session.commit()
        return existing, True

    cust = get_or_create_customer(norm, customer_name)
    inv = Invoice(
        invoice_number=next_invoice_number(on_date),
        invoice_date=on_date,
        customer_id=cust.id if cust else None,
        customer_name=customer_name or (cust.name if cust else None),
        customer_phone=norm,
        place_of_supply=place_of_supply if place_of_supply in ("intra", "inter") else "intra",
        customer_state_code=customer_state_code,
        discount_amount=Decimal(str(discount_amount or 0)),
        notes=notes,
        status="finalized",
        whatsapp_status="pending",
    )
    for d in lines:
        inv.lines.append(_line_from_dict(d, default_gst, default_hsn))
    db.session.add(inv)
    db.session.flush()
    inv.recalculate()
    pdf_path = _pdf_path_for(inv)
    generate_invoice_pdf(inv, dest_path=pdf_path)
    inv.pdf_path = str(pdf_path)
    db.session.commit()

    should_send = send_now or current_app.config.get("SEND_ON_CREATE", False)
    if should_send and norm:
        from app.services.whatsapp import send_invoice_document

        send_invoice_document(inv, pdf_path=pdf_path)
    return inv, False


def _pdf_path_for(invoice: Invoice) -> Path:
    base = Path(current_app.config["INVOICES_DIR"])
    safe = invoice.invoice_number.replace("/", "-")
    return base / f"{safe}.pdf"


def send_pending_invoices(debounce_minutes: int | None = None) -> list[Invoice]:
    """
    Send invoices with whatsapp_status=pending whose updated_at is older than
    the debounce window (so same-day merges can settle). Used by `flask send-pending`.
    """
    from datetime import timedelta

    from app.services.whatsapp import send_invoice_document

    minutes = (
        debounce_minutes
        if debounce_minutes is not None
        else int(current_app.config.get("PENDING_SEND_DEBOUNCE_MINUTES", 30))
    )
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    pending = (
        Invoice.query.filter(
            Invoice.whatsapp_status == "pending",
            Invoice.customer_phone.isnot(None),
            Invoice.status != "void",
            Invoice.updated_at <= cutoff,
        )
        .order_by(Invoice.id)
        .all()
    )
    sent = []
    for inv in pending:
        send_invoice_document(inv, pdf_path=inv.pdf_path)
        sent.append(inv)
    return sent
