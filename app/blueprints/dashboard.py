"""Per-day sales tally dashboard + revenue trends."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import func

from app.extensions import db
from app.models.sales import Invoice, InvoiceLine

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    day_str = request.args.get("date")
    if day_str:
        try:
            day = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            day = date.today()
    else:
        day = date.today()

    invoices = (
        Invoice.query.filter(
            Invoice.invoice_date == day,
            Invoice.status != "void",
        )
        .order_by(Invoice.id.desc())
        .all()
    )
    total_sales = sum((Decimal(inv.grand_total or 0) for inv in invoices), Decimal("0"))
    txn_count = len(invoices)

    # Top items last 30 days (and also show day's items if empty)
    since = day - timedelta(days=30)
    top_rows = (
        db.session.query(
            InvoiceLine.item_name,
            func.sum(InvoiceLine.quantity).label("qty"),
            func.sum(InvoiceLine.line_total).label("revenue"),
        )
        .join(Invoice)
        .filter(Invoice.invoice_date >= since, Invoice.invoice_date <= day, Invoice.status != "void")
        .group_by(InvoiceLine.item_name)
        .order_by(func.sum(InvoiceLine.line_total).desc())
        .limit(10)
        .all()
    )
    top_items = [
        {"name": r.item_name, "qty": float(r.qty or 0), "revenue": Decimal(r.revenue or 0)}
        for r in top_rows
    ]

    return render_template(
        "dashboard/index.html",
        day=day,
        total_sales=total_sales,
        txn_count=txn_count,
        invoices=invoices,
        top_items=top_items,
    )


@bp.route("/api/revenue-trend")
def revenue_trend():
    today = date.today()
    days_7, days_30 = [], []
    for n in range(6, -1, -1):
        d = today - timedelta(days=n)
        total = (
            db.session.query(func.coalesce(func.sum(Invoice.grand_total), 0))
            .filter(Invoice.invoice_date == d, Invoice.status != "void")
            .scalar()
        )
        days_7.append({"date": d.isoformat(), "total": float(total)})
    for n in range(29, -1, -1):
        d = today - timedelta(days=n)
        total = (
            db.session.query(func.coalesce(func.sum(Invoice.grand_total), 0))
            .filter(Invoice.invoice_date == d, Invoice.status != "void")
            .scalar()
        )
        days_30.append({"date": d.isoformat(), "total": float(total)})
    return jsonify({"days_7": days_7, "days_30": days_30})
