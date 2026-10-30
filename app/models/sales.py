"""Sales invoices, lines, WhatsApp message log."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.extensions import db


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    invoice_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    customer_name = db.Column(db.String(120), nullable=True)
    customer_phone = db.Column(db.String(20), nullable=True, index=True)
    # Intra-state (CGST+SGST) vs inter-state (IGST)
    place_of_supply = db.Column(db.String(10), nullable=False, default="intra")  # intra|inter
    customer_state_code = db.Column(db.String(5), nullable=True)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    taxable_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cgst_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sgst_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    igst_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    grand_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    # draft | finalized | sent | void
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    # pending | sent | simulated | skipped | failed | queued
    whatsapp_status = db.Column(db.String(20), nullable=False, default="pending")
    # Idempotency key for WhatsApp send (invoice_id + pdf_version)
    pdf_version = db.Column(db.Integer, nullable=False, default=1)
    last_sent_pdf_version = db.Column(db.Integer, nullable=True)
    pdf_path = db.Column(db.String(500), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    finalized_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="invoices")
    lines = db.relationship(
        "InvoiceLine",
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="joined",
        order_by="InvoiceLine.id",
    )
    whatsapp_messages = db.relationship(
        "WhatsAppMessage",
        back_populates="invoice",
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
        disc = Decimal(self.discount_amount or 0)
        self.taxable_total = taxable
        self.cgst_total = cgst
        self.sgst_total = sgst
        self.igst_total = igst
        self.grand_total = taxable + cgst + sgst + igst - disc
        if self.grand_total < 0:
            self.grand_total = Decimal("0")

    def __repr__(self) -> str:
        return f"<Invoice {self.invoice_number}>"


class InvoiceLine(db.Model):
    __tablename__ = "invoice_lines"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    item_name = db.Column(db.String(200), nullable=False)
    size = db.Column(db.String(40), nullable=True)
    hsn = db.Column(db.String(20), nullable=True)
    quantity = db.Column(db.Numeric(12, 2), nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(12, 2), nullable=False, default=0)  # line discount ₹
    gst_rate = db.Column(db.Numeric(5, 2), nullable=False, default=5)  # %
    taxable_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cgst_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    sgst_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    igst_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    invoice = db.relationship("Invoice", back_populates="lines")
    product = db.relationship("Product")

    def recalculate(self, place_of_supply: str = "intra") -> None:
        qty = Decimal(self.quantity)
        price = Decimal(self.unit_price)
        disc = Decimal(self.discount or 0)
        rate = Decimal(self.gst_rate or 0)
        taxable = (qty * price) - disc
        if taxable < 0:
            taxable = Decimal("0")
        tax = (taxable * rate / Decimal("100")).quantize(Decimal("0.01"))
        self.taxable_amount = taxable.quantize(Decimal("0.01"))
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


class WhatsAppMessage(db.Model):
    __tablename__ = "whatsapp_messages"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    direction = db.Column(db.String(10), nullable=False, default="outbound")  # inbound|outbound
    to_phone = db.Column(db.String(20), nullable=False)
    message_type = db.Column(db.String(40), nullable=True)  # freeform|template|status|text
    template_name = db.Column(db.String(80), nullable=True)
    wamid = db.Column(db.String(120), nullable=True, index=True)
    media_id = db.Column(db.String(120), nullable=True)
    # queued|sent|delivered|read|failed|simulated|received
    status = db.Column(db.String(40), nullable=False, default="queued")
    body_preview = db.Column(db.String(500), nullable=True)
    response_json = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    pdf_saved_path = db.Column(db.String(500), nullable=True)
    idempotency_key = db.Column(db.String(120), nullable=True, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    invoice = db.relationship("Invoice", back_populates="whatsapp_messages")
    customer = db.relationship("Customer")
