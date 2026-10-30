"""Same-day phone dedup — merge lines, no duplicate invoice."""
from app.models.sales import Invoice
from app.services.phone import normalize_phone
from app.services.sales import create_or_merge_invoice


def test_normalize_phone_india(app):
    assert normalize_phone("9876543210") == "+919876543210"
    assert normalize_phone("+91 98765 43210") == "+919876543210"
    assert normalize_phone("09876543210") == "+919876543210"


def test_same_day_merge(app):
    inv1, merged1 = create_or_merge_invoice(
        phone="9876500001",
        name="Test",
        items=[{"item_name": "Abaya", "quantity": 1, "unit_price": 1000, "gst_rate": 5}],
        auto_finalize=False,
    )
    assert merged1 is False
    assert Invoice.query.count() == 1
    n_lines = len(inv1.lines)

    inv2, merged2 = create_or_merge_invoice(
        phone="9876500001",
        name="Test",
        items=[{"item_name": "Hijab", "quantity": 2, "unit_price": 400, "gst_rate": 5}],
        auto_finalize=False,
    )
    assert merged2 is True
    assert inv2.id == inv1.id
    assert Invoice.query.count() == 1
    assert len(inv2.lines) == n_lines + 1


def test_different_phone_new_invoice(app):
    create_or_merge_invoice(
        phone="9876500002",
        name=None,
        items=[{"item_name": "A", "quantity": 1, "unit_price": 100, "gst_rate": 5}],
        auto_finalize=False,
    )
    create_or_merge_invoice(
        phone="9876500003",
        name=None,
        items=[{"item_name": "B", "quantity": 1, "unit_price": 100, "gst_rate": 5}],
        auto_finalize=False,
    )
    assert Invoice.query.count() == 2
