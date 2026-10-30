"""Sales invoice create / same-day merge (dedup) / finalize / send pipeline."""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from flask import current_app, flash, has_request_context

from app.extensions import db
from app.models.customer import Customer
from app.models.sales import Invoice, InvoiceLine
from app.services.email_bcc import send_invoice_bcc
from app.services.invoice_number import next_invoice_number
from app.services.pdf_invoice import generate_invoice_pdf
from app.services.phone import normalize_phone
from app.services.whatsapp import send_invoice_whatsapp

logger = logging.getLogger(__name__)


def get_or_create_customer(phone: str, name: str | None = None) -> Customer:
    phone = normalize_phone(phone)
    if not phone:
        raise ValueError("Invalid phone number")
    customer = Customer.query.filter_by(phone=phone).first()
    if customer:
        if name and (not customer.name or customer.name != name):
            customer.name = name
        return customer
    customer = Customer(phone=phone, name=name)
    db.session.add(customer)
    db.session.flush()
    return customer


def find_same_day_invoice(phone: str, on_date: date | None = None) -> Invoice | None:
    """
    Dedup: find non-void invoice for this phone on the given date (IST 'today').
    Merges into this invoice instead of creating a second one.
    """
    on_date = on_date or date.today()
    phone = normalize_phone(phone) or phone
    return (
        Invoice.query.filter(
            Invoice.customer_phone == phone,
            Invoice.invoice_date == on_date,
            Invoice.status != "void",
        )
        .order_by(Invoice.id.desc())
        .first()
    )


def _make_line(item: dict) -> InvoiceLine:
    return InvoiceLine(
        product_id=item.get("product_id"),
        item_name=item["item_name"],
        size=item.get("size"),
        hsn=item.get("hsn") or current_app.config.get("DEFAULT_HSN", "6211"),
        quantity=Decimal(str(item.get("quantity", 1))),
        unit_price=Decimal(str(item.get("unit_price", 0))),
        discount=Decimal(str(item.get("discount", 0))),
        gst_rate=Decimal(str(item.get("gst_rate", current_app.config.get("DEFAULT_GST_RATE", 5)))),
    )


def create_or_merge_invoice(
    *,
    phone: str,
    name: str | None,
    items: list[dict],
    place_of_supply: str = "intra",
    discount_amount: Decimal | float = 0,
    notes: str | None = None,
    invoice_date: date | None = None,
    auto_finalize: bool = True,
) -> tuple[Invoice, bool]:
    """
    Create a new invoice OR merge items into today's existing invoice for this phone.

    Returns (invoice, merged: bool).

    Send behaviour (documented):
    - New/merged invoices start as draft (or finalized if auto_finalize).
    - WhatsApp/PDF send happens on **finalize** (or explicit "Send now"),
      NOT automatically on every merge — so multiple same-day purchases
      accumulate lines, then one PDF is generated and sent.
    - If SEND_ON_CREATE=true and auto_finalize, send immediately after finalize.
    - Re-send after merge: bump pdf_version, regenerate PDF, send with new
      idempotency key (inv-{id}-v{version}). Previous send is not revoked.
    """
    if not items:
        raise ValueError("At least one line item required")

    invoice_date = invoice_date or date.today()
    customer = get_or_create_customer(phone, name)
    existing = find_same_day_invoice(customer.phone, invoice_date)

    if existing:
        for item in items:
            existing.lines.append(_make_line(item))
        if discount_amount:
            existing.discount_amount = Decimal(str(existing.discount_amount or 0)) + Decimal(
                str(discount_amount)
            )
        if notes:
            existing.notes = ((existing.notes or "") + "\n" + notes).strip()
        if name:
            existing.customer_name = name
        existing.place_of_supply = place_of_supply
        existing.recalculate()
        # Content changed → new PDF version; mark pending resend
        existing.pdf_version = (existing.pdf_version or 1) + 1
        existing.whatsapp_status = "pending"
        if existing.status == "sent":
            existing.status = "finalized"  # ready to resend
        db.session.commit()
        return existing, True

    inv = Invoice(
        invoice_number=next_invoice_number(invoice_date),
        invoice_date=invoice_date,
        customer_id=customer.id,
        customer_name=name or customer.name,
        customer_phone=customer.phone,
        place_of_supply=place_of_supply,
        customer_state_code=current_app.config.get("SHOP_STATE_CODE", "29"),
        discount_amount=Decimal(str(discount_amount or 0)),
        notes=notes,
        status="draft",
        whatsapp_status="pending",
        pdf_version=1,
    )
    for item in items:
        inv.lines.append(_make_line(item))
    inv.recalculate()
    db.session.add(inv)
    db.session.commit()

    if auto_finalize:
        finalize_invoice(inv, send=current_app.config.get("SEND_ON_CREATE", False))
    return inv, False



def _report_bcc_result(invoice: Invoice, bcc: dict) -> None:
    """Log BCC outcome and flash a warning in request context when skipped/failed."""
    invoice_no = invoice.invoice_number
    if not bcc.get("ok"):
        err = bcc.get("error") or "unknown error"
        logger.error("BCC failed for %s: %s", invoice_no, err)
        if has_request_context():
            flash(f"Owner email copy failed for {invoice_no}: {err}", "warning")
        return
    if bcc.get("skipped") or bcc.get("dry_run"):
        reason = bcc.get("skipped") or "SMTP not configured"
        logger.info("BCC skipped for %s: %s (to=%s)", invoice_no, reason, bcc.get("to"))
        if has_request_context():
            flash(f"Owner email copy skipped: {reason}.", "warning")
        return
    logger.info("BCC sent for %s to %s", invoice_no, bcc.get("to"))


def finalize_invoice(invoice: Invoice, send: bool = True) -> Invoice:
    """
    Mark invoice finalized, generate PDF, optionally WhatsApp + BCC owner email.

    Call this when the cashier is done adding items for the visit (or after
    same-day merges settle). Send is gated by `send` flag / SEND_ON_CREATE.
    """
    if invoice.status == "void":
        raise ValueError("Cannot finalize a void invoice")

    invoice.recalculate()
    invoice.status = "finalized"
    invoice.finalized_at = datetime.utcnow()
    pdf_path = generate_invoice_pdf(invoice)
    invoice.pdf_path = pdf_path
    db.session.commit()

    # Always BCC owner for ledger (even if WhatsApp skipped)
    bcc = send_invoice_bcc(invoice, pdf_path)
    _report_bcc_result(invoice, bcc)

    if send and invoice.customer_phone:
        send_invoice_whatsapp(invoice, pdf_path)
    return invoice


def resend_invoice(invoice: Invoice) -> Invoice:
    """Regenerate PDF (current pdf_version) and send WhatsApp + BCC again."""
    if invoice.status == "void":
        raise ValueError("Cannot resend a void invoice")
    invoice.recalculate()
    if invoice.status == "draft":
        invoice.status = "finalized"
        invoice.finalized_at = datetime.utcnow()
    pdf_path = generate_invoice_pdf(invoice)
    invoice.pdf_path = pdf_path
    db.session.commit()
    bcc = send_invoice_bcc(invoice, pdf_path)
    _report_bcc_result(invoice, bcc)
    if invoice.customer_phone:
        send_invoice_whatsapp(invoice, pdf_path)
    return invoice
