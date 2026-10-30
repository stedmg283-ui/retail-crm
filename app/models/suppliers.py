"""Suppliers, purchase orders / supplier bills, payments."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.extensions import db


class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    contact_name = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    gstin = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    state_code = db.Column(db.String(5), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchase_orders = db.relationship("PurchaseOrder", back_populates="supplier", lazy="dynamic")

    def outstanding_balance(self) -> Decimal:
        total = Decimal("0")
        for po in self.purchase_orders:
            total += po.balance_due()
        return total

    def __repr__(self) -> str:
        return f"<Supplier {self.name}>"


class PurchaseOrder(db.Model):
    """Supplier bill / purchase invoice with GST breakdown."""
    __tablename__ = "purchase_orders"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    bill_number = db.Column(db.String(60), nullable=False)
    po_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    place_of_supply = db.Column(db.String(10), nullable=False, default="intra")  # intra|inter
    taxable_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cgst_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sgst_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    igst_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    grand_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    # paid | partial | outstanding
    payment_status = db.Column(db.String(20), nullable=False, default="outstanding")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    supplier = db.relationship("Supplier", back_populates="purchase_orders")
    lines = db.relationship(
        "PurchaseOrderLine",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        lazy="joined",
    )
    payments = db.relationship(
        "SupplierPayment",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def recalculate(self) -> None:
        taxable = Decimal("0")
        cgst = Decimal("0")
        sgst = Decimal("0")
        igst = Decimal("0")
        for ln in self.lines:
            ln.recalculate(self.place_of_supply)
            taxable += Decimal(ln.taxable_amount)
            cgst += Decimal(ln.cgst_amount)
            sgst += Decimal(ln.sgst_amount)
            igst += Decimal(ln.igst_amount)
        self.taxable_total = taxable
        self.cgst_total = cgst
        self.sgst_total = sgst
        self.igst_total = igst
        self.grand_total = taxable + cgst + sgst + igst

    def subtotal(self) -> Decimal:
        return Decimal(self.grand_total or 0)

    def amount_paid(self) -> Decimal:
        return sum((Decimal(p.amount) for p in self.payments), Decimal("0"))

    def balance_due(self) -> Decimal:
        return self.subtotal() - self.amount_paid()

    def refresh_payment_status(self) -> None:
        paid = self.amount_paid()
        total = self.subtotal()
        if paid <= 0:
            self.payment_status = "outstanding"
        elif paid >= total:
            self.payment_status = "paid"
        else:
            self.payment_status = "partial"

    def __repr__(self) -> str:
        return f"<PO {self.bill_number}>"


class PurchaseOrderLine(db.Model):
    __tablename__ = "purchase_order_lines"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    hsn = db.Column(db.String(20), nullable=True)
    quantity = db.Column(db.Numeric(12, 2), nullable=False, default=1)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    gst_rate = db.Column(db.Numeric(5, 2), nullable=False, default=5)
    taxable_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cgst_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sgst_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    igst_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    purchase_order = db.relationship("PurchaseOrder", back_populates="lines")

    def recalculate(self, place_of_supply: str = "intra") -> None:
        qty = Decimal(self.quantity)
        cost = Decimal(self.unit_cost)
        rate = Decimal(self.gst_rate or 0)
        taxable = (qty * cost).quantize(Decimal("0.01"))
        tax = (taxable * rate / Decimal("100")).quantize(Decimal("0.01"))
        self.taxable_amount = taxable
        if place_of_supply == "inter":
            self.igst_amount = tax
            self.cgst_amount = Decimal("0")
            self.sgst_amount = Decimal("0")
        else:
            half = (tax / Decimal("2")).quantize(Decimal("0.01"))
            self.cgst_amount = half
            self.sgst_amount = tax - half
            self.igst_amount = Decimal("0")
        self.line_total = (
            self.taxable_amount + self.cgst_amount + self.sgst_amount + self.igst_amount
        )

    def line_total_fn(self) -> Decimal:
        return Decimal(self.line_total or 0)


class SupplierPayment(db.Model):
    __tablename__ = "supplier_payments"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    paid_on = db.Column(db.Date, nullable=False, default=date.today)
    method = db.Column(db.String(40), nullable=True, default="UPI")
    reference = db.Column(db.String(80), nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchase_order = db.relationship("PurchaseOrder", back_populates="payments")
