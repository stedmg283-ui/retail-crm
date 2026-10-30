"""Invoice PDF generation smoke test."""
from pathlib import Path

from app.services.sales import create_or_merge_invoice, finalize_invoice


def test_pdf_generated(app):
    with app.app_context():
        inv, _ = create_or_merge_invoice(
            phone="9876500099",
            name="PDF Test",
            items=[
                {"item_name": "Kurti", "quantity": 1, "unit_price": 899, "gst_rate": 5, "hsn": "6211"},
            ],
            auto_finalize=False,
        )
        finalize_invoice(inv, send=False)
        assert inv.pdf_path
        assert Path(inv.pdf_path).is_file()
        assert Path(inv.pdf_path).stat().st_size > 500
