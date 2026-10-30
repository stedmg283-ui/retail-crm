"""GST calculation helpers (India: CGST/SGST intra-state, IGST inter-state)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


TWOPLACES = Decimal("0.01")


def q(amount) -> Decimal:
    return Decimal(str(amount)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def split_gst(
    taxable: Decimal,
    gst_rate: Decimal,
    place_of_supply: str = "intra",
) -> dict[str, Decimal]:
    """Return cgst, sgst, igst, tax_total for a taxable amount."""
    taxable = q(taxable)
    rate = Decimal(str(gst_rate))
    tax = q(taxable * rate / Decimal("100"))
    if place_of_supply == "inter":
        return {
            "cgst": Decimal("0.00"),
            "sgst": Decimal("0.00"),
            "igst": tax,
            "tax_total": tax,
        }
    half = q(tax / Decimal("2"))
    sgst = tax - half
    return {
        "cgst": half,
        "sgst": sgst,
        "igst": Decimal("0.00"),
        "tax_total": tax,
    }


def line_totals(
    quantity,
    unit_price,
    gst_rate,
    discount=0,
    place_of_supply: str = "intra",
) -> dict[str, Decimal]:
    qty = Decimal(str(quantity))
    price = Decimal(str(unit_price))
    disc = Decimal(str(discount or 0))
    taxable = q(qty * price - disc)
    if taxable < 0:
        taxable = Decimal("0.00")
    gst = split_gst(taxable, gst_rate, place_of_supply)
    return {
        "taxable": taxable,
        "cgst": gst["cgst"],
        "sgst": gst["sgst"],
        "igst": gst["igst"],
        "line_total": q(taxable + gst["tax_total"]),
    }
