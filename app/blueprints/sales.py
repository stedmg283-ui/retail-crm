"""Sales invoices UI + API."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from app.extensions import db
from app.models.product import Product
from app.models.sales import Invoice
from app.services.sales import create_or_merge_invoice, finalize_invoice, resend_invoice

bp = Blueprint("sales", __name__)


@bp.route("/")
def list_invoices():
    invoices = Invoice.query.order_by(Invoice.id.desc()).limit(100).all()
    return render_template("sales/list.html", invoices=invoices)


@bp.route("/new", methods=["GET", "POST"])
def new_invoice():
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        name = request.form.get("name", "").strip() or None
        place = request.form.get("place_of_supply", "intra")
        discount = Decimal(request.form.get("discount_amount") or 0)
        notes = request.form.get("notes") or None
        send_now = request.form.get("send_now") == "1"

        names = request.form.getlist("item_name[]")
        qtys = request.form.getlist("quantity[]")
        prices = request.form.getlist("unit_price[]")
        sizes = request.form.getlist("size[]")
        hsns = request.form.getlist("hsn[]")
        rates = request.form.getlist("gst_rate[]")
        items = []
        for i, n in enumerate(names):
            if not n.strip():
                continue
            items.append(
                {
                    "item_name": n.strip(),
                    "quantity": qtys[i] if i < len(qtys) else 1,
                    "unit_price": prices[i] if i < len(prices) else 0,
                    "size": sizes[i] if i < len(sizes) else None,
                    "hsn": hsns[i] if i < len(hsns) else current_app.config["DEFAULT_HSN"],
                    "gst_rate": rates[i] if i < len(rates) else current_app.config["DEFAULT_GST_RATE"],
                }
            )
        if not phone or not items:
            flash("Phone and at least one item are required.", "danger")
            return render_template("sales/new.html", products=products)

        try:
            inv, merged = create_or_merge_invoice(
                phone=phone,
                name=name,
                items=items,
                place_of_supply=place,
                discount_amount=discount,
                notes=notes,
                auto_finalize=False,
            )
            if request.form.get("action") == "finalize" or send_now:
                finalize_invoice(inv, send=send_now or current_app.config.get("SEND_ON_CREATE"))
                flash(
                    f"{'Merged into' if merged else 'Created'} {inv.invoice_number} and finalized"
                    + (" + sent" if send_now or current_app.config.get('SEND_ON_CREATE') else "")
                    + ".",
                    "success",
                )
            else:
                # Save as draft / merge without send
                if not merged:
                    inv.status = "draft"
                    db.session.commit()
                flash(
                    f"{'Merged items into' if merged else 'Draft'} {inv.invoice_number}.",
                    "success",
                )
            return redirect(url_for("sales.view_invoice", invoice_id=inv.id))
        except Exception as exc:
            flash(str(exc), "danger")
            return render_template("sales/new.html", products=products)

    return render_template("sales/new.html", products=products)


@bp.route("/<int:invoice_id>")
def view_invoice(invoice_id: int):
    inv = Invoice.query.get_or_404(invoice_id)
    return render_template("sales/view.html", invoice=inv)


@bp.route("/<int:invoice_id>/finalize", methods=["POST"])
def finalize(invoice_id: int):
    inv = Invoice.query.get_or_404(invoice_id)
    send = request.form.get("send") == "1"
    try:
        finalize_invoice(inv, send=send)
        flash(
            f"Invoice {inv.invoice_number} finalized"
            + (" and WhatsApp queued/sent." if send else "."),
            "success",
        )
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("sales.view_invoice", invoice_id=inv.id))


@bp.route("/<int:invoice_id>/send", methods=["POST"])
def send(invoice_id: int):
    inv = Invoice.query.get_or_404(invoice_id)
    try:
        resend_invoice(inv)
        flash(f"Invoice {inv.invoice_number} PDF regenerated and sent.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("sales.view_invoice", invoice_id=inv.id))


@bp.route("/<int:invoice_id>/pdf")
def download_pdf(invoice_id: int):
    inv = Invoice.query.get_or_404(invoice_id)
    if not inv.pdf_path or not Path(inv.pdf_path).is_file():
        from app.services.pdf_invoice import generate_invoice_pdf

        inv.pdf_path = generate_invoice_pdf(inv)
        db.session.commit()
    return send_file(inv.pdf_path, mimetype="application/pdf", as_attachment=False)
