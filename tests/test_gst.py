"""GST totals — intra CGST/SGST vs inter IGST."""
from decimal import Decimal

from app.models.sales import Invoice, InvoiceLine


def test_intra_state_splits_cgst_sgst(app):
    inv = Invoice(invoice_number="T/1", place_of_supply="intra")
    ln = InvoiceLine(item_name="Abaya", quantity=2, unit_price=1000, discount=0, gst_rate=5)
    inv.lines.append(ln)
    inv.recalculate()
    assert inv.taxable_total == Decimal("2000.00")
    assert inv.cgst_total == Decimal("50.00")
    assert inv.sgst_total == Decimal("50.00")
    assert inv.igst_total == Decimal("0")
    assert inv.grand_total == Decimal("2100.00")


def test_inter_state_igst(app):
    inv = Invoice(invoice_number="T/2", place_of_supply="inter")
    ln = InvoiceLine(item_name="Hijab", quantity=1, unit_price=500, gst_rate=12)
    inv.lines.append(ln)
    inv.recalculate()
    assert inv.igst_total == Decimal("60.00")
    assert inv.cgst_total == Decimal("0")
    assert inv.sgst_total == Decimal("0")
    assert inv.grand_total == Decimal("560.00")


def test_line_discount_reduces_taxable(app):
    inv = Invoice(invoice_number="T/3", place_of_supply="intra")
    ln = InvoiceLine(item_name="X", quantity=1, unit_price=1000, discount=100, gst_rate=5)
    inv.lines.append(ln)
    inv.recalculate()
    assert inv.taxable_total == Decimal("900.00")
    assert inv.grand_total == Decimal("945.00")
