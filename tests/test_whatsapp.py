"""WhatsApp DRY_RUN when credentials missing."""
from pathlib import Path

from app.models.sales import WhatsAppMessage
from app.services.sales import create_or_merge_invoice, finalize_invoice
from app.services.whatsapp import dry_run_mode, send_invoice_document


def test_dry_run_mode_without_creds(app):
    assert dry_run_mode() is True


def test_send_saves_pdf_and_logs_dry_run(app):
    inv, _ = create_or_merge_invoice(
        phone="9876511111",
        name="Fatima",
        items=[{"item_name": "Abaya", "quantity": 1, "unit_price": 2000, "gst_rate": 5}],
        auto_finalize=False,
    )
    finalize_invoice(inv, send=False)
    assert inv.pdf_path and Path(inv.pdf_path).exists()
    msg = send_invoice_document(inv, pdf_path=inv.pdf_path)
    assert msg.status == "dry_run"
    assert msg.wamid and "dry_run" in msg.wamid
    assert msg.pdf_saved_path
    assert Path(msg.pdf_saved_path).exists()
    assert WhatsAppMessage.query.count() >= 1
    assert inv.whatsapp_status == "sent"
