"""Register all blueprints."""
from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from app.blueprints.attendance import bp as attendance_bp
    from app.blueprints.customers import bp as customers_bp
    from app.blueprints.dashboard import bp as dashboard_bp
    from app.blueprints.payroll import bp as payroll_bp
    from app.blueprints.purchases import bp as purchases_bp
    from app.blueprints.sales import bp as sales_bp
    from app.blueprints.webhook import bp as webhook_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(sales_bp, url_prefix="/sales")
    app.register_blueprint(customers_bp, url_prefix="/customers")
    app.register_blueprint(purchases_bp, url_prefix="/purchases")
    app.register_blueprint(attendance_bp, url_prefix="/attendance")
    app.register_blueprint(payroll_bp, url_prefix="/payroll")
    app.register_blueprint(webhook_bp, url_prefix="/webhook")
    # Meta docs often use /webhooks/whatsapp — same handlers
    app.register_blueprint(webhook_bp, url_prefix="/webhooks", name="webhooks")
