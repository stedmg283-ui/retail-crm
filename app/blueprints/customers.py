"""Customer profiles — phone is unique key."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models.customer import Customer
from app.models.sales import Invoice
from app.services.phone import normalize_phone

bp = Blueprint("customers", __name__)


@bp.route("/")
def list_customers():
    q = request.args.get("q", "").strip()
    query = Customer.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Customer.phone.ilike(like), Customer.name.ilike(like))
        )
    customers = query.order_by(Customer.updated_at.desc()).limit(200).all()
    return render_template("customers/list.html", customers=customers, q=q)


@bp.route("/<int:customer_id>")
def profile(customer_id: int):
    customer = Customer.query.get_or_404(customer_id)
    invoices = (
        Invoice.query.filter_by(customer_id=customer.id)
        .filter(Invoice.status != "void")
        .order_by(Invoice.invoice_date.desc(), Invoice.id.desc())
        .all()
    )
    return render_template(
        "customers/profile.html",
        customer=customer,
        invoices=invoices,
        lifetime=customer.lifetime_total(),
    )


@bp.route("/by-phone/<path:phone>")
def by_phone(phone: str):
    phone = normalize_phone(phone) or phone
    customer = Customer.query.filter_by(phone=phone).first_or_404()
    return redirect(url_for("customers.profile", customer_id=customer.id))
