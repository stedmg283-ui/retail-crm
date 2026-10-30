"""Purchase orders / supplier bills."""
from __future__ import annotations

from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models.suppliers import PurchaseOrder, PurchaseOrderLine, Supplier, SupplierPayment

bp = Blueprint("purchases", __name__)


@bp.route("/")
def list_pos():
    pos = PurchaseOrder.query.order_by(PurchaseOrder.po_date.desc()).limit(100).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("purchases/list.html", purchase_orders=pos, suppliers=suppliers)


@bp.route("/suppliers", methods=["GET", "POST"])
def suppliers():
    if request.method == "POST":
        s = Supplier(
            name=request.form["name"].strip(),
            contact_name=request.form.get("contact_name") or None,
            phone=request.form.get("phone") or None,
            email=request.form.get("email") or None,
            gstin=request.form.get("gstin") or None,
            address=request.form.get("address") or None,
            state_code=request.form.get("state_code") or None,
        )
        db.session.add(s)
        db.session.commit()
        flash(f"Supplier {s.name} added.", "success")
        return redirect(url_for("purchases.suppliers"))
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("purchases/suppliers.html", suppliers=suppliers)


@bp.route("/new", methods=["GET", "POST"])
def new_po():
    suppliers = Supplier.query.order_by(Supplier.name).all()
    if request.method == "POST":
        po = PurchaseOrder(
            supplier_id=int(request.form["supplier_id"]),
            bill_number=request.form["bill_number"].strip(),
            place_of_supply=request.form.get("place_of_supply", "intra"),
            notes=request.form.get("notes") or None,
        )
        names = request.form.getlist("item_name[]")
        qtys = request.form.getlist("quantity[]")
        costs = request.form.getlist("unit_cost[]")
        hsns = request.form.getlist("hsn[]")
        rates = request.form.getlist("gst_rate[]")
        for i, n in enumerate(names):
            if not n.strip():
                continue
            po.lines.append(
                PurchaseOrderLine(
                    item_name=n.strip(),
                    quantity=Decimal(qtys[i] if i < len(qtys) else 1),
                    unit_cost=Decimal(costs[i] if i < len(costs) else 0),
                    hsn=hsns[i] if i < len(hsns) else None,
                    gst_rate=Decimal(rates[i] if i < len(rates) else 5),
                )
            )
        po.recalculate()
        db.session.add(po)
        db.session.commit()
        flash(f"Supplier bill {po.bill_number} recorded.", "success")
        return redirect(url_for("purchases.view_po", po_id=po.id))
    return render_template("purchases/new.html", suppliers=suppliers)


@bp.route("/<int:po_id>")
def view_po(po_id: int):
    po = PurchaseOrder.query.get_or_404(po_id)
    return render_template("purchases/view.html", po=po)


@bp.route("/<int:po_id>/payment", methods=["POST"])
def add_payment(po_id: int):
    po = PurchaseOrder.query.get_or_404(po_id)
    payment = SupplierPayment(
        purchase_order_id=po.id,
        amount=Decimal(request.form["amount"]),
        method=request.form.get("method") or "UPI",
        reference=request.form.get("reference") or None,
        notes=request.form.get("notes") or None,
    )
    db.session.add(payment)
    db.session.flush()
    po.refresh_payment_status()
    db.session.commit()
    flash("Payment recorded.", "success")
    return redirect(url_for("purchases.view_po", po_id=po.id))
