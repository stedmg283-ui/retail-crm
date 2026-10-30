"""WhatsApp 24h service window logic."""
from datetime import datetime, timedelta

from app.extensions import db
from app.models.customer import Customer
from app.services.whatsapp import record_inbound, within_service_window


def test_no_inbound_outside_window(app):
    with app.app_context():
        c = Customer(phone="+919876500003", name="Cold")
        db.session.add(c)
        db.session.commit()
        assert within_service_window(c) is False
        assert c.within_service_window() is False


def test_inbound_opens_window(app):
    with app.app_context():
        c = record_inbound("+919876500004", body="Hi", wamid="wamid.test.1")
        assert c is not None
        assert c.last_inbound_at is not None
        assert within_service_window(c) is True


def test_window_expires(app):
    with app.app_context():
        c = Customer(
            phone="+919876500005",
            last_inbound_at=datetime.utcnow() - timedelta(hours=25),
        )
        db.session.add(c)
        db.session.commit()
        assert c.within_service_window() is False
        # Just inside
        c.last_inbound_at = datetime.utcnow() - timedelta(hours=23)
        db.session.commit()
        assert c.within_service_window() is True
