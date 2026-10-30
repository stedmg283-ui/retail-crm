"""Rabya Collection Retail CRM — Flask application factory."""
from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from app.extensions import db

ROOT = Path(__file__).resolve().parent.parent


def create_app(config_overrides: dict | None = None) -> Flask:
    load_dotenv(ROOT / ".env")

    # NOTE: do not name this variable `app` if we also `import app.*` in this
    # function — `import app.models` would rebind the local name to the package.
    flask_app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    flask_app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-change-me"),
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL", f"sqlite:///{ROOT / 'retail_crm.db'}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SHOP_NAME=os.getenv("SHOP_NAME", "Rabya Collection"),
        SHOP_ADDRESS=os.getenv("SHOP_ADDRESS", "Bengaluru, Karnataka, India"),
        SHOP_GSTIN=os.getenv("SHOP_GSTIN", "29AAAAA0000A1Z5"),
        SHOP_PHONE=os.getenv("SHOP_PHONE", "+919876543210"),
        SHOP_EMAIL=os.getenv("SHOP_EMAIL", "orders@rabyacollection.example"),
        SHOP_STATE_CODE=os.getenv("SHOP_STATE_CODE", "29"),
        OWNER_EMAIL=os.getenv("OWNER_EMAIL", ""),
        LOGO_PATH=os.getenv("LOGO_PATH", str(ROOT / "app/static/img/logo_placeholder.png")),
        DEFAULT_SHIFT_HOURS=float(os.getenv("DEFAULT_SHIFT_HOURS", "9")),
        OT_MULTIPLIER=float(os.getenv("OT_MULTIPLIER", "1.5")),
        DEFAULT_GST_RATE=float(os.getenv("DEFAULT_GST_RATE", "5")),
        DEFAULT_HSN=os.getenv("DEFAULT_HSN", "6211"),
        INVOICE_PREFIX=os.getenv("INVOICE_PREFIX", "RC"),
        WHATSAPP_TOKEN=os.getenv("WHATSAPP_TOKEN", ""),
        WHATSAPP_PHONE_NUMBER_ID=os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
        WHATSAPP_BUSINESS_ACCOUNT_ID=os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", ""),
        WHATSAPP_API_VERSION=os.getenv("WHATSAPP_API_VERSION", "v20.0"),
        WHATSAPP_TEMPLATE_NAME=os.getenv("WHATSAPP_TEMPLATE_NAME", "invoice_document"),
        WHATSAPP_TEMPLATE_LANG=os.getenv("WHATSAPP_TEMPLATE_LANG", "en"),
        WHATSAPP_WEBHOOK_VERIFY_TOKEN=os.getenv(
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "rabya-verify-change-me"
        ),
        SEND_ON_CREATE=os.getenv("SEND_ON_CREATE", "false").lower() in ("1", "true", "yes"),
        PENDING_SEND_DEBOUNCE_MINUTES=int(os.getenv("PENDING_SEND_DEBOUNCE_MINUTES", "30")),
        INVOICES_DIR=str(ROOT / "invoices"),
        SENT_INVOICES_DIR=str(ROOT / "invoices" / "sent"),
    )
    if config_overrides:
        flask_app.config.update(config_overrides)

    # INFO logs for WhatsApp / BCC go to stdout/stderr (picked up by nohup → server.log).
    # Never configure handlers that would print tokens; services already redact.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    logging.getLogger("werkzeug").setLevel(logging.INFO)
    logging.getLogger("app").setLevel(logging.INFO)

    Path(flask_app.config["INVOICES_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(flask_app.config["SENT_INVOICES_DIR"]).mkdir(parents=True, exist_ok=True)

    db.init_app(flask_app)

    # Register models without binding local name `app`
    importlib.import_module("app.models")

    from app.blueprints import register_blueprints
    from app.cli import register_cli

    register_blueprints(flask_app)
    register_cli(flask_app)

    with flask_app.app_context():
        db.create_all()

    @flask_app.context_processor
    def inject_shop():
        return {
            "shop_name": flask_app.config["SHOP_NAME"],
            "shop_gstin": flask_app.config["SHOP_GSTIN"],
        }

    return flask_app
