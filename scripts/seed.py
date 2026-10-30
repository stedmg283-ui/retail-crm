"""Sample data seeder for Rabya Collection retail CRM."""
from __future__ import annotations

import random
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

from flask import current_app

from app.extensions import db
from app.models.attendance import (
    Attendance,
    Employee,
    PayrollDeduction,
    PayrollRun,
    PayrollRunLine,
)
from app.models.customer import Customer
from app.models.product import Product
from app.models.sales import Invoice, InvoiceLine, WhatsAppMessage
from app.models.suppliers import PurchaseOrder, PurchaseOrderLine, Supplier, SupplierPayment
from app.services.phone import normalize_phone
from app.services.sales import create_or_merge_invoice, finalize_invoice

ITEMS = [
    ("Abaya Classic Black", "M", "Abaya", 5, 1899, 850),
    ("Abaya Embroidered Navy", "L", "Abaya", 5, 2499, 1100),
    ("Abaya Open Front Beige", "S", "Abaya", 5, 2199, 980),
    ("Hijab Chiffon Set", "Free", "Hijab", 5, 499, 180),
    ("Hijab Jersey Premium", "Free", "Hijab", 5, 399, 140),
    ("Kids Abaya Pink", "8Y", "Kids", 5, 1299, 520),
    ("Prayer Dress White", "XL", "Dress", 5, 999, 400),
    ("Abaya Butterfly Cut", "M", "Abaya", 12, 3299, 1500),
    ("Modest Kurti Set", "L", "Kurti", 5, 1599, 650),
    ("Scarf Pin Pack", "—", "Accessories", 5, 149, 40),
]

PHONES = [
    "9876501234", "9876502345", "9876503456", "9876504567",
    "9876505678", "9123456780", "9988776655", "9001122334",
]
NAMES = [
    "Fatima Khan", "Ayesha Begum", "Zainab Ali", "Maryam Sheikh",
    "Sara Hussain", "Noor Ahmed", "Hana Rahman", "Layla Yusuf",
]


def run_seed(*, clear: bool = True) -> None:
    if clear:
        for model in (
            WhatsAppMessage,
            InvoiceLine,
            Invoice,
            Customer,
            SupplierPayment,
            PurchaseOrderLine,
            PurchaseOrder,
            Supplier,
            PayrollRunLine,
            PayrollRun,
            PayrollDeduction,
            Attendance,
            Employee,
            Product,
        ):
            model.query.delete()
        db.session.commit()

    products = []
    for i, (name, size, cat, gst, price, cost) in enumerate(ITEMS):
        p = Product(
            sku=f"RC-{1000+i}",
            name=name,
            category=cat,
            size=size,
            hsn=current_app.config.get("DEFAULT_HSN", "6211"),
            gst_rate=Decimal(str(gst)),
            unit_price=Decimal(str(price)),
            cost_price=Decimal(str(cost)),
            stock_qty=Decimal(50),
        )
        products.append(p)
    db.session.add_all(products)

    employees = [
        Employee(name="Priya Sharma", role="Store Manager", shift="Day", rate_type="daily", rate_amount=900),
        Employee(name="Ananya Reddy", role="Sales Associate", shift="Day", rate_type="hourly", rate_amount=120),
        Employee(name="Meera Iyer", role="Sales Associate", shift="Evening", rate_type="hourly", rate_amount=110),
        Employee(name="Rafi Khan", role="Tailor", shift="Day", rate_type="daily", rate_amount=750),
        Employee(name="Sana Mirza", role="Cashier", shift="Day", rate_type="hourly", rate_amount=100),
    ]
    db.session.add_all(employees)
    db.session.flush()

    today = date.today()
    for emp in employees:
        for d_offset in range(30):
            d = today - timedelta(days=d_offset)
            if d.weekday() == 6:
                continue
            if random.random() < 0.1:
                continue
            cin = time(9, random.randint(0, 30))
            extra = random.choice([0, 0, 0, 1, 2, 3])
            cout = time(min(18 + extra, 23), random.randint(0, 45))
            db.session.add(
                Attendance(employee_id=emp.id, work_date=d, check_in=cin, check_out=cout, status="present")
            )

    suppliers = [
        Supplier(name="Dubai Modest Wear Traders", contact_name="Omar Al-Farsi", phone="+971501234567", address="Deira, Dubai"),
        Supplier(name="Bengaluru Silk House", contact_name="Venkatesh Rao", phone="+919845551122", gstin="29BBBDD1234B1Z2", address="Chickpet, Bengaluru"),
        Supplier(name="Hijab Hub Wholesale", contact_name="Amina Patel", phone="+919900112233", gstin="27CCCEE5678C1Z9", address="Mumbai"),
    ]
    db.session.add_all(suppliers)
    db.session.flush()

    for i, s in enumerate(suppliers):
        po = PurchaseOrder(
            supplier_id=s.id,
            bill_number=f"SUP-{1000 + i}",
            po_date=today - timedelta(days=10 + i * 3),
            notes="Seed purchase",
        )
        for prod in random.sample(products, 3):
            po.lines.append(
                PurchaseOrderLine(
                    item_name=prod.name,
                    quantity=Decimal(random.randint(5, 20)),
                    unit_cost=prod.cost_price or Decimal("100"),
                )
            )
        db.session.add(po)
        db.session.flush()
        if i == 0:
            db.session.add(SupplierPayment(purchase_order_id=po.id, amount=po.subtotal(), paid_on=po.po_date + timedelta(days=2), method="NEFT"))
        elif i == 1:
            db.session.add(SupplierPayment(purchase_order_id=po.id, amount=(po.subtotal() / 2).quantize(Decimal("0.01")), paid_on=po.po_date + timedelta(days=1), method="UPI"))
        po.refresh_payment_status()

    db.session.commit()

    # Historical sales (~30 days), with occasional same-day merge
    for d_offset in range(29, -1, -1):
        d = today - timedelta(days=d_offset)
        used = set()
        for _ in range(random.randint(2, 5)):
            idx = random.randint(0, len(PHONES) - 1)
            phone = PHONES[idx]
            name = NAMES[idx]
            prod = random.choice(products)
            items = [{
                "product_id": prod.id,
                "item_name": prod.name,
                "size": prod.size,
                "quantity": random.randint(1, 2),
                "unit_price": float(prod.unit_price),
                "discount": 0,
                "gst_rate": float(prod.gst_rate),
                "hsn": prod.hsn,
            }]
            # Occasional second add same phone → merge
            merge_extra = phone in used and random.random() < 0.35
            inv, merged = create_or_merge_invoice(
                phone=phone,
                name=name,
                items=items,
                place_of_supply="intra",
                invoice_date=d,
                auto_finalize=False,
            )
            used.add(phone)
            if not merged or d_offset > 0:
                # Finalize without WhatsApp spam for historical; today leave some pending
                send = False
                finalize_invoice(inv, send=send)
                if d_offset > 0:
                    inv.whatsapp_status = "sent"
                    db.session.commit()

    print(
        f"Seeded products={Product.query.count()} employees={Employee.query.count()} "
        f"suppliers={Supplier.query.count()} invoices={Invoice.query.count()} "
        f"customers={Customer.query.count()}"
    )
