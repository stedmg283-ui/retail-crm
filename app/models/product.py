"""Product / item catalog."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.extensions import db


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(40), unique=True, nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    category = db.Column(db.String(80), nullable=True)  # e.g. Saree, Kurti, Kids
    size = db.Column(db.String(40), nullable=True)
    hsn = db.Column(db.String(20), nullable=True, default="6211")
    gst_rate = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("5"))
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cost_price = db.Column(db.Numeric(12, 2), nullable=True)
    stock_qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Product {self.name}>"
