"""Invoice number generation: PREFIX/FY/SEQ e.g. RC/2026-27/0001."""
from __future__ import annotations

from datetime import date

from flask import current_app
from sqlalchemy import func

from app.config import financial_year
from app.extensions import db
from app.models.sales import Invoice


def next_invoice_number(d: date | None = None) -> str:
    d = d or date.today()
    fy = financial_year(d)
    prefix = current_app.config.get("INVOICE_PREFIX", "RC")
    pattern = f"{prefix}/{fy}/%"
    # Find max existing sequence for this FY
    existing = (
        db.session.query(func.max(Invoice.invoice_number))
        .filter(Invoice.invoice_number.like(pattern))
        .scalar()
    )
    seq = 1
    if existing:
        try:
            seq = int(existing.rsplit("/", 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}/{fy}/{seq:04d}"
