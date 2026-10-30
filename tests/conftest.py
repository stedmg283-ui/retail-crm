"""Pytest fixtures — isolated SQLite app."""
from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app(tmp_path):
    invoices = tmp_path / "invoices"
    sent = invoices / "sent"
    invoices.mkdir()
    sent.mkdir()
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
            "SECRET_KEY": "test",
            "INVOICES_DIR": str(invoices),
            "SENT_INVOICES_DIR": str(sent),
            "WHATSAPP_TOKEN": "",
            "WHATSAPP_PHONE_NUMBER_ID": "",
            "SEND_ON_CREATE": False,
            "DEFAULT_SHIFT_HOURS": 9,
            "OT_MULTIPLIER": 1.5,
            "DEFAULT_GST_RATE": 5,
            "INVOICE_PREFIX": "RC",
            "OWNER_EMAIL": "",
        }
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()


@pytest.fixture()
def client(app):
    return app.test_client()
