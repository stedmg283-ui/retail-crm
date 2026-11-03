"""Product import + top-sellers tests (no WhatsApp)."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.product import Product
from app.models.sales import Invoice, InvoiceLine
from app.services.product_import import (
    expand_row,
    generate_sku,
    import_from_path,
    map_headers,
)
from app.services.schema_migrate import ensure_product_columns
from app.services.top_sellers import build_top_sellers, top_sellers_payload


@pytest.fixture()
def app(tmp_path):
    from app import create_app

    invoices = tmp_path / "invoices"
    sent = invoices / "sent"
    invoices.mkdir()
    sent.mkdir()
    exports = tmp_path / "exports"
    incoming = tmp_path / "incoming"
    (incoming / "extracted").mkdir(parents=True)
    (incoming / "reports").mkdir(parents=True)
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
            "SECRET_KEY": "test-secret-key-not-for-prod",
            "INVOICES_DIR": str(invoices),
            "SENT_INVOICES_DIR": str(sent),
            "EXPORTS_DIR": str(exports),
            "INCOMING_DIR": str(incoming),
            "INCOMING_EXTRACT_DIR": str(incoming / "extracted"),
            "INCOMING_REPORTS_DIR": str(incoming / "reports"),
            "WHATSAPP_TOKEN": "",
            "WHATSAPP_PHONE_NUMBER_ID": "",
            "SEND_ON_CREATE": False,
            "ADMIN_PASSWORD_HASH": generate_password_hash("test-admin-pass"),
            "REPORT_TOKEN": "test-report-token-abc",
            "SESSION_COOKIE_SECURE": False,
        }
    )
    with application.app_context():
        db.create_all()
        ensure_product_columns()
        yield application
        db.session.remove()


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_sample_zip(path: Path) -> Path:
    zpath = path / "sample-catalog.zip"
    buf = io.StringIO()
    w = csv.DictWriter(
        buf,
        fieldnames=["sku", "name", "fabric", "price", "sizes", "colors", "stock", "category"],
    )
    w.writeheader()
    w.writerow(
        {
            "sku": "RC-EX-001",
            "name": "Example Midnight Abaya",
            "fabric": "Nida",
            "price": "2499",
            "sizes": "M,L",
            "colors": "Black,Navy",
            "stock": "5",
            "category": "Abaya",
        }
    )
    w.writerow(
        {
            "sku": "",
            "name": "Example Pearl Abaya",
            "fabric": "Crepe",
            "price": "1999",
            "sizes": "S",
            "colors": "Ivory",
            "stock": "2",
            "category": "Abaya",
        }
    )
    w.writerow(
        {
            "sku": "RC-EX-BAD",
            "name": "Broken Price Abaya",
            "fabric": "Cotton",
            "price": "0",
            "sizes": "M",
            "colors": "Grey",
            "stock": "1",
            "category": "Abaya",
        }
    )
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("products.csv", buf.getvalue())
        # tiny 1x1 png
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        zf.writestr("RC-EX-001.png", png)
        zf.writestr("photos/RC-EX-001-M/front.png", png)
    return zpath


def test_header_mapping():
    m = map_headers(["Product Name", "MRP", "SKU Code", "Colour"])
    assert set(m.values()) >= {"name", "unit_price", "sku", "colors"}


def test_generate_sku_deterministic():
    assert generate_sku("Pearl Abaya", "S") == generate_sku("Pearl Abaya", "S")
    assert "RC-" in generate_sku("Pearl Abaya", "S")


def test_expand_sizes():
    rows = expand_row({"sku": "X", "name": "A", "size": "S,M"})
    assert len(rows) == 2
    assert rows[0]["sku"] == "X-S"
    assert rows[1]["sku"] == "X-M"


def test_import_zip_and_validation(app, tmp_path):
    zpath = _make_sample_zip(tmp_path)
    with app.app_context():
        report = import_from_path(
            zpath,
            static_root=Path(app.static_folder),
            extract_root=Path(app.config["INCOMING_EXTRACT_DIR"]),
            reports_dir=Path(app.config["INCOMING_REPORTS_DIR"]),
            commit=True,
        )
        # 2 sizes for first + 1 for second + 1 bad price = 4 rows read
        assert report.rows_read == 4
        assert report.created == 3  # two size variants + pearl
        assert report.errors == 1
        assert "RC-EX-BAD" in report.missing_prices or any(
            "RC-EX-BAD" in (r.sku or "") for r in report.row_results if r.action == "error"
        )
        products = Product.query.order_by(Product.sku).all()
        skus = [p.sku for p in products]
        assert "RC-EX-001-M" in skus
        assert "RC-EX-001-L" in skus
        pearl = [p for p in products if p.name == "Example Pearl Abaya"][0]
        assert pearl.sku and pearl.sku.startswith("RC-")
        assert pearl.unit_price == Decimal("1999")
        # reports written
        reports = list(Path(app.config["INCOMING_REPORTS_DIR"]).glob("import-*.md"))
        assert reports


def test_top_sellers_no_customer_fields(app):
    with app.app_context():
        p = Product(
            sku="RC-TS-1",
            name="Top Seller Abaya",
            category="Abaya",
            unit_price=Decimal("1000"),
            stock_qty=Decimal("3"),
            is_active=True,
        )
        db.session.add(p)
        db.session.flush()
        inv = Invoice(
            invoice_number="RC/TEST/0001",
            customer_name="SHOULD_NOT_APPEAR",
            customer_phone="+919999999999",
            status="finalized",
        )
        db.session.add(inv)
        db.session.flush()
        db.session.add(
            InvoiceLine(
                invoice_id=inv.id,
                product_id=p.id,
                item_name=p.name,
                quantity=2,
                unit_price=1000,
                line_total=2000,
                taxable_amount=2000,
            )
        )
        db.session.commit()
        payload = top_sellers_payload()
        blob = json.dumps(payload)
        assert "SHOULD_NOT_APPEAR" not in blob
        assert "+919999999999" not in blob
        assert "invoice" not in blob.lower() or "No customer" in payload["privacy"]
        assert payload["products"][0]["units_sold_30d"] == 2.0
        assert "customer" not in payload["products"][0]


def test_auth_redirects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 301)
    assert "/login" in r.headers.get("Location", "")
    r2 = client.get("/customers/", follow_redirects=False)
    assert r2.status_code in (302, 301)
    assert "/login" in r2.headers.get("Location", "")
    hz = client.get("/healthz")
    assert hz.status_code == 200


def test_report_json_token(client, app):
    r = client.get("/reports/top-sellers.json")
    assert r.status_code == 401
    r2 = client.get("/reports/top-sellers.json", headers={"X-Report-Token": "test-report-token-abc"})
    assert r2.status_code == 200
    data = r2.get_json()
    assert "products" in data
    assert "privacy" in data


def test_login_and_top_sellers_html(client):
    # get csrf
    page = client.get("/login")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    import re

    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m
    csrf = m.group(1)
    bad = client.post("/login", data={"password": "wrong", "csrf_token": csrf}, follow_redirects=False)
    assert bad.status_code == 200
    page2 = client.get("/login")
    m2 = re.search(r'name="csrf_token" value="([^"]+)"', page2.get_data(as_text=True))
    ok = client.post(
        "/login",
        data={"password": "test-admin-pass", "csrf_token": m2.group(1)},
        follow_redirects=False,
    )
    assert ok.status_code in (302, 301)
    ts = client.get("/reports/top-sellers")
    assert ts.status_code == 200


def test_photo_only_catalog_no_invented_prices(app, tmp_path):
    """Photo zip with numeric filenames → products created inactive, price 0, no invented prices."""
    from PIL import Image

    folder = tmp_path / "photos"
    folder.mkdir()
    img = Image.new("RGB", (8, 8), color=(20, 20, 40))
    img.save(folder / "48001.jpg")
    img2 = Image.new("RGB", (8, 8), color=(40, 20, 20))
    img2.save(folder / "chat_camera_upload_x.jpg")
    zpath = tmp_path / "photos-only.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.write(folder / "48001.jpg", "abaya/48001.jpg")
        zf.write(folder / "chat_camera_upload_x.jpg", "abaya/chat_camera_upload_x.jpg")

    with app.app_context():
        report = import_from_path(
            zpath,
            static_root=Path(app.static_folder),
            extract_root=Path(app.config["INCOMING_EXTRACT_DIR"]),
            reports_dir=Path(app.config["INCOMING_REPORTS_DIR"]),
            commit=True,
        )
        assert report.created == 2
        assert report.errors == 2  # both missing price
        assert len(report.missing_prices) == 2
        p1 = Product.query.filter_by(sku="48001").first()
        assert p1 is not None
        assert p1.unit_price == Decimal("0")
        assert p1.is_active is False
        assert p1.images_list()
        gens = [r for r in report.row_results if r.sku_generated]
        assert len(gens) == 1
