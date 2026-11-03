"""Product / item catalog."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.extensions import db


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(40), unique=True, nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    category = db.Column(db.String(80), nullable=True)  # e.g. Abaya, Saree, Kurti
    size = db.Column(db.String(40), nullable=True)
    fabric = db.Column(db.String(120), nullable=True)
    # JSON array text, e.g. '["Black","Navy"]' — also accepts plain comma-separated on import
    colors = db.Column(db.Text, nullable=True)
    # JSON array of paths relative to app/static, e.g. '["products/RC-001/a.jpg"]'
    image_paths = db.Column(db.Text, nullable=True)
    hsn = db.Column(db.String(20), nullable=True, default="6211")
    gst_rate = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("5"))
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cost_price = db.Column(db.Numeric(12, 2), nullable=True)
    stock_qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def colors_list(self) -> list[str]:
        return _parse_list_field(self.colors)

    def images_list(self) -> list[str]:
        return _parse_list_field(self.image_paths)

    def set_colors(self, values: list[str] | str | None) -> None:
        self.colors = _encode_list_field(values)

    def set_images(self, values: list[str] | str | None) -> None:
        self.image_paths = _encode_list_field(values)

    def price_incl_gst(self) -> Decimal:
        rate = Decimal(self.gst_rate or 0)
        price = Decimal(self.unit_price or 0)
        return (price * (Decimal("1") + rate / Decimal("100"))).quantize(Decimal("0.01"))

    def to_catalog_dict(self) -> dict[str, Any]:
        """Public product fields only — never customer data."""
        return {
            "sku": self.sku,
            "name": self.name,
            "category": self.category,
            "size": self.size,
            "fabric": self.fabric,
            "colors": self.colors_list(),
            "unit_price": float(self.unit_price or 0),
            "price_incl_gst": float(self.price_incl_gst()),
            "gst_rate": float(self.gst_rate or 0),
            "stock_qty": float(self.stock_qty or 0),
            "in_stock": float(self.stock_qty or 0) > 0,
            "image_paths": self.images_list(),
            "is_active": bool(self.is_active),
        }

    def __repr__(self) -> str:
        return f"<Product {self.sku or self.name}>"


def _parse_list_field(raw: str | None) -> list[str]:
    if not raw:
        return []
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return [p.strip() for p in text.split(",") if p.strip()]


def _encode_list_field(values: list[str] | str | None) -> str | None:
    if values is None:
        return None
    if isinstance(values, str):
        items = _parse_list_field(values)
    else:
        items = [str(x).strip() for x in values if str(x).strip()]
    if not items:
        return None
    return json.dumps(items, ensure_ascii=False)
