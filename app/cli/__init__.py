"""Flask CLI commands."""
from __future__ import annotations

import click
from flask import Flask


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_cmd():
        """Load demo seed data."""
        from scripts.seed import run_seed

        run_seed()
        click.echo("Seed data loaded.")

    @app.cli.command("send-pending")
    @click.option("--debounce-minutes", default=None, type=int)
    def send_pending(debounce_minutes):
        """
        Finalize + send invoices that are pending WhatsApp and older than debounce.
        Useful as an end-of-day cron so same-day merges settle before one send.
        """
        from datetime import datetime, timedelta

        from app.extensions import db
        from app.models.sales import Invoice
        from app.services.sales import finalize_invoice, resend_invoice

        mins = debounce_minutes
        if mins is None:
            mins = app.config.get("PENDING_SEND_DEBOUNCE_MINUTES", 30)
        cutoff = datetime.utcnow() - timedelta(minutes=mins)
        pending = (
            Invoice.query.filter(
                Invoice.whatsapp_status == "pending",
                Invoice.status.in_(["draft", "finalized", "sent"]),
                Invoice.customer_phone.isnot(None),
                Invoice.updated_at <= cutoff,
            ).all()
        )
        click.echo(f"Found {len(pending)} pending invoice(s) older than {mins}m.")
        for inv in pending:
            try:
                if inv.status == "draft":
                    finalize_invoice(inv, send=True)
                else:
                    resend_invoice(inv)
                click.echo(f"  sent {inv.invoice_number}")
            except Exception as exc:
                click.echo(f"  FAIL {inv.invoice_number}: {exc}")
        db.session.commit()

    @app.cli.command("init-db")
    def init_db():
        """Create all tables (also runs on app start)."""
        from app.extensions import db
        import app.models  # noqa: F401

        db.create_all()
        click.echo("Database tables created.")
