"""Flask CLI commands."""
from __future__ import annotations

from pathlib import Path

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
        from app.services.schema_migrate import ensure_product_columns

        db.create_all()
        added = ensure_product_columns()
        click.echo("Database tables created." + (f" Added columns: {added}" if added else ""))

    # --- products group ---
    @app.cli.group("products")
    def products_group():
        """Product catalog import / export."""

    @products_group.command("import")
    @click.argument("path", type=click.Path(exists=True, path_type=Path))
    def products_import(path: Path):
        """Import products from a zip or directory (CSV/XLSX/JSON + photos)."""
        from app.services.product_import import import_from_path
        from app.services.top_sellers import export_top_sellers

        report = import_from_path(
            path,
            static_root=Path(app.static_folder),
            extract_root=Path(app.config["INCOMING_EXTRACT_DIR"]),
            reports_dir=Path(app.config["INCOMING_REPORTS_DIR"]),
            commit=True,
        )
        export_top_sellers(Path(app.config["EXPORTS_DIR"]))
        click.echo(
            f"Import complete: read={report.rows_read} created={report.created} "
            f"updated={report.updated} errors={report.errors} "
            f"sku_gen={report.sku_generated_count}"
        )
        click.echo(f"Missing photos: {len(report.missing_photos)} "
                   f"Missing prices: {len(report.missing_prices)}")
        for n in report.notes:
            if n.startswith("report written:"):
                click.echo(n)

    @products_group.command("export-top-sellers")
    @click.option("--limit", default=None, type=int)
    def products_export_top_sellers(limit):
        """Write exports/top_sellers.json and .html (no customer data)."""
        from app.services.top_sellers import export_top_sellers

        jp, hp = export_top_sellers(Path(app.config["EXPORTS_DIR"]), limit=limit)
        click.echo(f"Wrote {jp}")
        click.echo(f"Wrote {hp}")

    @products_group.command("ensure-schema")
    def products_ensure_schema():
        """Add fabric/colors/image_paths columns if missing."""
        from app.services.schema_migrate import ensure_product_columns

        added = ensure_product_columns()
        click.echo("Added: " + (", ".join(added) if added else "(none, already present)"))
