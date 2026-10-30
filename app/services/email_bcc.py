"""BCC invoice PDF to shop owner via SMTP (configurable, no secrets in code)."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from flask import current_app

logger = logging.getLogger(__name__)


def send_invoice_bcc(invoice, pdf_path: str) -> dict:
    """
    Email the invoice PDF to OWNER_EMAIL (BCC-style ledger copy).
    Uses SMTP_* env vars. Returns {ok, dry_run, error}.
    """
    owner = os.getenv("OWNER_EMAIL") or current_app.config.get("OWNER_EMAIL") or ""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM") or smtp_user or current_app.config.get("SHOP_EMAIL", "")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    if not owner:
        logger.info("OWNER_EMAIL not set — skipping BCC for %s", invoice.invoice_number)
        return {"ok": True, "dry_run": True, "error": None, "skipped": "OWNER_EMAIL not set"}

    if not smtp_host or not smtp_from:
        logger.info(
            "SMTP not configured — skipping BCC for %s to %s",
            invoice.invoice_number,
            owner,
        )
        return {
            "ok": True,
            "dry_run": True,
            "error": None,
            "skipped": "SMTP not configured",
            "to": owner,
        }

    if not smtp_pass:
        logger.info(
            "SMTP_PASSWORD missing — skipping BCC for %s to %s",
            invoice.invoice_number,
            owner,
        )
        return {
            "ok": True,
            "dry_run": True,
            "error": None,
            "skipped": "SMTP_PASSWORD missing",
            "to": owner,
        }

    msg = EmailMessage()
    shop = current_app.config.get("SHOP_NAME", "Shop")
    msg["Subject"] = f"[{shop}] Invoice {invoice.invoice_number} — ₹{invoice.grand_total}"
    msg["From"] = smtp_from
    msg["To"] = owner
    msg.set_content(
        f"Invoice {invoice.invoice_number}\n"
        f"Customer: {invoice.customer_name or '—'} ({invoice.customer_phone or '—'})\n"
        f"Date: {invoice.invoice_date}\n"
        f"Grand Total: ₹{invoice.grand_total}\n\n"
        f"PDF attached for internal ledger.\n"
    )
    pdf = Path(pdf_path)
    if pdf.is_file():
        msg.add_attachment(
            pdf.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=pdf.name,
        )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info("BCC email sent for %s to %s", invoice.invoice_number, owner)
        return {"ok": True, "dry_run": False, "error": None, "to": owner}
    except Exception as exc:
        logger.exception("SMTP BCC failed for %s", invoice.invoice_number)
        return {"ok": False, "dry_run": False, "error": str(exc), "to": owner}
