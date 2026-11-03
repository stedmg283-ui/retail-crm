"""Top-sellers summary for reel automation — no customer PII."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import and_, case, func, or_

from app.extensions import db
from app.models.product import Product
from app.models.sales import Invoice, InvoiceLine


def _units_sold_subquery(since: date):
    """Sum quantity from invoice_lines for non-void invoices since `since`.

    Prefer product_id join; also attribute free-text lines whose item_name
    matches a product name (case-insensitive) when product_id is null.
    """
    return (
        db.session.query(
            Product.id.label("product_id"),
            func.coalesce(func.sum(InvoiceLine.quantity), 0).label("units"),
        )
        .outerjoin(
            InvoiceLine,
            or_(
                InvoiceLine.product_id == Product.id,
                and_(
                    InvoiceLine.product_id.is_(None),
                    func.lower(InvoiceLine.item_name) == func.lower(Product.name),
                ),
            ),
        )
        .outerjoin(Invoice, InvoiceLine.invoice_id == Invoice.id)
        .filter(
            or_(
                Invoice.id.is_(None),
                and_(Invoice.status != "void", Invoice.invoice_date >= since),
            )
        )
        .group_by(Product.id)
        .subquery()
    )


def build_top_sellers(limit: int | None = None) -> list[dict[str, Any]]:
    today = date.today()
    since_7 = today - timedelta(days=7)
    since_30 = today - timedelta(days=30)

    # Aggregate per product via two lightweight queries to keep dialect-simple
    def units_map(since: date) -> dict[int, float]:
        rows = (
            db.session.query(
                Product.id,
                func.coalesce(func.sum(InvoiceLine.quantity), 0),
            )
            .outerjoin(
                InvoiceLine,
                or_(
                    InvoiceLine.product_id == Product.id,
                    and_(
                        InvoiceLine.product_id.is_(None),
                        func.lower(InvoiceLine.item_name) == func.lower(Product.name),
                    ),
                ),
            )
            .outerjoin(Invoice, InvoiceLine.invoice_id == Invoice.id)
            .filter(Product.is_active.is_(True))
            .filter(
                or_(
                    Invoice.id.is_(None),
                    and_(Invoice.status != "void", Invoice.invoice_date >= since),
                )
            )
            .group_by(Product.id)
            .all()
        )
        return {pid: float(qty or 0) for pid, qty in rows}

    u7 = units_map(since_7)
    u30 = units_map(since_30)

    products = Product.query.filter(Product.is_active.is_(True)).all()
    items: list[dict[str, Any]] = []
    for p in products:
        base = p.to_catalog_dict()
        base["units_sold_7d"] = u7.get(p.id, 0.0)
        base["units_sold_30d"] = u30.get(p.id, 0.0)
        # strip internal flags not needed by reel agent
        base.pop("is_active", None)
        items.append(base)

    items.sort(
        key=lambda x: (
            -x["units_sold_30d"],
            -x["stock_qty"],
            x.get("sku") or "",
        )
    )
    if limit is not None:
        items = items[:limit]
    return items


def top_sellers_payload(limit: int | None = None) -> dict[str, Any]:
    items = build_top_sellers(limit=limit)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "currency": "INR",
        "gst_note": "price_incl_gst = unit_price * (1 + gst_rate/100); default gst 5%",
        "privacy": "No customer names, phones, or invoice IDs are included.",
        "count": len(items),
        "products": items,
    }


def render_top_sellers_html(payload: dict[str, Any]) -> str:
    rows = []
    for p in payload["products"]:
        colors = ", ".join(p.get("colors") or []) or "—"
        imgs = ", ".join(p.get("image_paths") or []) or "—"
        rows.append(
            "<tr>"
            f"<td>{_esc(p.get('sku'))}</td>"
            f"<td>{_esc(p.get('name'))}</td>"
            f"<td>{_esc(p.get('category'))}</td>"
            f"<td>{_esc(p.get('fabric'))}</td>"
            f"<td>{_esc(colors)}</td>"
            f"<td>₹{p.get('unit_price', 0):,.2f}</td>"
            f"<td>₹{p.get('price_incl_gst', 0):,.2f}</td>"
            f"<td>{p.get('stock_qty', 0):g}</td>"
            f"<td>{'yes' if p.get('in_stock') else 'no'}</td>"
            f"<td>{p.get('units_sold_7d', 0):g}</td>"
            f"<td>{p.get('units_sold_30d', 0):g}</td>"
            f"<td class='small'>{_esc(imgs)}</td>"
            "</tr>"
        )
    body = "\n".join(rows) or "<tr><td colspan='12'>No active products</td></tr>"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Top sellers — Rabiyacollections</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;color:#3b1530}}
h1{{color:#3b1530}} .gold{{color:#b8860b}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{border:1px solid #ddd;padding:.4rem .55rem;text-align:left}}
th{{background:#3b1530;color:#f5e6c8}}
.meta{{color:#666;margin-bottom:1rem}}
.small{{font-size:12px;word-break:break-all}}
</style></head><body>
<h1>Top sellers <span class="gold">· Rabiyacollections</span></h1>
<p class="meta">Generated { _esc(payload.get('generated_at')) } ·
{payload.get('count', 0)} products · {_esc(payload.get('privacy'))}</p>
<table>
<thead><tr>
<th>SKU</th><th>Name</th><th>Category</th><th>Fabric</th><th>Colors</th>
<th>Price</th><th>Incl. GST</th><th>Stock</th><th>In stock</th>
<th>Sold 7d</th><th>Sold 30d</th><th>Images</th>
</tr></thead>
<tbody>
{body}
</tbody></table>
</body></html>
"""


def _esc(val: Any) -> str:
    s = "" if val is None else str(val)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def export_top_sellers(
    exports_dir: Path | str,
    limit: int | None = None,
) -> tuple[Path, Path]:
    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    payload = top_sellers_payload(limit=limit)
    json_path = exports_dir / "top_sellers.json"
    html_path = exports_dir / "top_sellers.html"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    html_path.write_text(render_top_sellers_html(payload), encoding="utf-8")
    return json_path, html_path
