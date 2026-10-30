"""Customer profiles — phone (E.164) is the unique key."""
from __future__ import annotations

from datetime import datetime

from app.extensions import db


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # WhatsApp 24h service window: updated on inbound webhook messages
    last_inbound_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    invoices = db.relationship("Invoice", back_populates="customer", lazy="dynamic")

    def within_service_window(self, now: datetime | None = None, hours: int = 24) -> bool:
        """True if last inbound WhatsApp message was within `hours`."""
        if not self.last_inbound_at:
            return False
        now = now or datetime.utcnow()
        return (now - self.last_inbound_at).total_seconds() <= hours * 3600

    def lifetime_total(self) -> float:
        from sqlalchemy import func
        from app.models.sales import Invoice

        total = (
            db.session.query(func.coalesce(func.sum(Invoice.grand_total), 0))
            .filter(Invoice.customer_id == self.id, Invoice.status != "void")
            .scalar()
        )
        return float(total or 0)

    def __repr__(self) -> str:
        return f"<Customer {self.phone}>"
