"""WhatsApp Cloud API: media upload, document send, freeform vs template, webhook."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import requests
from flask import current_app

from app.extensions import db
from app.models.customer import Customer
from app.models.sales import Invoice, WhatsAppMessage
from app.services.phone import normalize_phone

logger = logging.getLogger(__name__)


def _configured() -> bool:
    return bool(
        current_app.config.get("WHATSAPP_TOKEN")
        and current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
    )


def _api_base() -> str:
    ver = current_app.config.get("WHATSAPP_API_VERSION", "v20.0")
    phone_id = current_app.config["WHATSAPP_PHONE_NUMBER_ID"]
    return f"https://graph.facebook.com/{ver}/{phone_id}"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {current_app.config['WHATSAPP_TOKEN']}",
        "Content-Type": "application/json",
    }


def within_service_window(customer: Customer | None, phone: str | None = None) -> bool:
    """True if last inbound message from this customer is within 24 hours."""
    if customer and customer.last_inbound_at:
        return customer.within_service_window()
    if phone:
        phone = normalize_phone(phone) or phone
        cust = Customer.query.filter_by(phone=phone).first()
        if cust:
            return cust.within_service_window()
    return False


def upload_media(pdf_path: str) -> str | None:
    """Upload PDF to WhatsApp media endpoint; return media_id or None in dry-run."""
    if not _configured():
        logger.info("WhatsApp dry-run: skip media upload for %s", pdf_path)
        return f"dry_run_media_{Path(pdf_path).stem}"

    ver = current_app.config.get("WHATSAPP_API_VERSION", "v20.0")
    phone_id = current_app.config["WHATSAPP_PHONE_NUMBER_ID"]
    url = f"https://graph.facebook.com/{ver}/{phone_id}/media"
    headers = {"Authorization": f"Bearer {current_app.config['WHATSAPP_TOKEN']}"}
    with open(pdf_path, "rb") as f:
        files = {
            "file": (Path(pdf_path).name, f, "application/pdf"),
            "messaging_product": (None, "whatsapp"),
            "type": (None, "application/pdf"),
        }
        resp = requests.post(url, headers=headers, files=files, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("id")


def send_document_freeform(
    to_phone: str,
    media_id: str,
    filename: str,
    caption: str = "",
) -> dict:
    """Send document message inside 24h service window (freeform)."""
    to = (normalize_phone(to_phone) or to_phone).lstrip("+")
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": filename,
        },
    }
    if caption:
        payload["document"]["caption"] = caption[:1024]

    if not _configured():
        logger.info("WhatsApp dry-run freeform document to %s", to)
        return {"messages": [{"id": f"dry_run_wamid_{to}"}], "dry_run": True}

    url = f"{_api_base()}/messages"
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def send_document_template(
    to_phone: str,
    media_id: str,
    filename: str,
    body_params: list[str] | None = None,
) -> dict:
    """
    Send Meta-approved template with DOCUMENT header outside 24h window.
    Template must be pre-approved with a document header component.
    """
    to = (normalize_phone(to_phone) or to_phone).lstrip("+")
    template_name = current_app.config.get("WHATSAPP_TEMPLATE_NAME", "invoice_document")
    lang = current_app.config.get("WHATSAPP_TEMPLATE_LANG", "en")
    components = [
        {
            "type": "header",
            "parameters": [
                {
                    "type": "document",
                    "document": {"id": media_id, "filename": filename},
                }
            ],
        }
    ]
    if body_params:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body_params],
            }
        )
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
            "components": components,
        },
    }

    if not _configured():
        logger.info("WhatsApp dry-run template %s to %s", template_name, to)
        return {
            "messages": [{"id": f"dry_run_wamid_tpl_{to}"}],
            "dry_run": True,
            "template": template_name,
        }

    url = f"{_api_base()}/messages"
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def send_invoice_whatsapp(invoice: Invoice, pdf_path: str) -> WhatsAppMessage:
    """
    Upload PDF and send via freeform (inside window) or template (outside).
    Idempotency: skip if same invoice pdf_version already sent successfully.
    """
    phone = invoice.customer_phone
    if not phone:
        raise ValueError("Invoice has no customer phone")

    idem = f"inv-{invoice.id}-v{invoice.pdf_version}"
    existing = WhatsAppMessage.query.filter_by(idempotency_key=idem).first()
    if existing and existing.status in ("sent", "delivered", "read", "dry_run", "queued"):
        logger.info("Idempotent skip for %s", idem)
        return existing

    customer = invoice.customer
    if not customer and phone:
        customer = Customer.query.filter_by(phone=normalize_phone(phone) or phone).first()

    use_freeform = within_service_window(customer, phone)
    media_id = upload_media(pdf_path)
    filename = Path(pdf_path).name
    caption = (
        f"Invoice {invoice.invoice_number} from {current_app.config['SHOP_NAME']}. "
        f"Total: ₹{invoice.grand_total}"
    )

    msg = WhatsAppMessage(
        invoice_id=invoice.id,
        customer_id=customer.id if customer else None,
        direction="outbound",
        to_phone=normalize_phone(phone) or phone,
        message_type="freeform" if use_freeform else "template",
        template_name=None
        if use_freeform
        else current_app.config.get("WHATSAPP_TEMPLATE_NAME"),
        media_id=media_id,
        status="queued",
        idempotency_key=idem,
        pdf_saved_path=pdf_path,
    )
    db.session.add(msg)
    db.session.flush()

    try:
        if use_freeform:
            result = send_document_freeform(phone, media_id, filename, caption=caption)
        else:
            result = send_document_template(
                phone,
                media_id,
                filename,
                body_params=[
                    invoice.customer_name or "Customer",
                    invoice.invoice_number,
                    str(invoice.grand_total),
                ],
            )
        msg.response_json = json.dumps(result)
        wamid = None
        if result.get("messages"):
            wamid = result["messages"][0].get("id")
        msg.wamid = wamid
        msg.status = "dry_run" if result.get("dry_run") else "sent"
        invoice.whatsapp_status = "sent"
        invoice.last_sent_pdf_version = invoice.pdf_version
        invoice.status = "sent" if invoice.status == "finalized" else invoice.status

        # Archive a copy under invoices/sent/
        sent_dir = Path(current_app.config["SENT_INVOICES_DIR"])
        sent_dir.mkdir(parents=True, exist_ok=True)
        dest = sent_dir / filename
        if Path(pdf_path).resolve() != dest.resolve():
            shutil.copy2(pdf_path, dest)
            msg.pdf_saved_path = str(dest)
    except Exception as exc:
        logger.exception("WhatsApp send failed for invoice %s", invoice.invoice_number)
        msg.status = "failed"
        msg.error_message = str(exc)
        invoice.whatsapp_status = "failed"

    db.session.commit()
    return msg


def record_inbound(phone: str, body: str | None = None, wamid: str | None = None) -> Customer | None:
    """Update customer's last_inbound_at from webhook; open 24h window."""
    phone = normalize_phone(phone)
    if not phone:
        return None
    customer = Customer.query.filter_by(phone=phone).first()
    if not customer:
        customer = Customer(phone=phone, name=None)
        db.session.add(customer)
        db.session.flush()
    customer.last_inbound_at = datetime.utcnow()
    msg = WhatsAppMessage(
        customer_id=customer.id,
        direction="inbound",
        to_phone=phone,
        message_type="text",
        wamid=wamid,
        status="received",
        body_preview=(body or "")[:500],
    )
    db.session.add(msg)
    db.session.commit()
    return customer


def update_status_by_wamid(wamid: str, status: str) -> None:
    msg = WhatsAppMessage.query.filter_by(wamid=wamid).first()
    if msg:
        msg.status = status
        msg.updated_at = datetime.utcnow()
        db.session.commit()


# --- Compatibility aliases (tests / invoices service) ---
def dry_run_mode() -> bool:
    return not _configured()


def credentials_configured() -> bool:
    return _configured()


def send_invoice_document(invoice: Invoice, pdf_bytes=None, pdf_path=None) -> WhatsAppMessage:
    """Alias used by older callers; wraps send_invoice_whatsapp."""
    path = pdf_path or invoice.pdf_path
    if not path and pdf_bytes:
        sent_dir = Path(current_app.config["SENT_INVOICES_DIR"])
        sent_dir.mkdir(parents=True, exist_ok=True)
        safe = (invoice.invoice_number or f"inv-{invoice.id}").replace("/", "-")
        path = str(sent_dir / f"{safe}.pdf")
        Path(path).write_bytes(pdf_bytes)
    if not path:
        raise ValueError("No PDF path for invoice")
    return send_invoice_whatsapp(invoice, str(path))


def handle_status_webhook(payload: dict) -> int:
    updated = 0
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for st in value.get("statuses") or []:
                wamid = st.get("id")
                status = st.get("status")
                if wamid and status:
                    update_status_by_wamid(wamid, status)
                    updated += 1
            for msg in value.get("messages") or []:
                from_phone = (msg.get("from") or "")
                body = None
                if msg.get("type") == "text":
                    body = (msg.get("text") or {}).get("body")
                if from_phone:
                    record_inbound(from_phone, body=body, wamid=msg.get("id"))
    return updated
