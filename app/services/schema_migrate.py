"""Lightweight schema ensure — no flask-migrate; ALTER TABLE safely."""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.extensions import db

log = logging.getLogger(__name__)

# (table, column, DDL fragment after ADD COLUMN)
PRODUCT_EXTRA_COLUMNS = (
    ("fabric", "VARCHAR(120)"),
    ("colors", "TEXT"),
    ("image_paths", "TEXT"),
)


def ensure_product_columns() -> list[str]:
    """Add nullable product columns if missing. Returns list of columns added."""
    added: list[str] = []
    try:
        insp = inspect(db.engine)
        if "products" not in insp.get_table_names():
            db.create_all()
            return added
        existing = {c["name"] for c in insp.get_columns("products")}
    except Exception as exc:  # noqa: BLE001
        log.warning("schema inspect failed: %s", exc)
        db.create_all()
        return added

    for col, typedef in PRODUCT_EXTRA_COLUMNS:
        if col in existing:
            continue
        # Postgres + SQLite both accept ADD COLUMN IF NOT EXISTS (PG 9.1+/SQLite 3.35+)
        # Fall back to plain ADD COLUMN when IF NOT EXISTS unavailable.
        ddl_if = f"ALTER TABLE products ADD COLUMN IF NOT EXISTS {col} {typedef}"
        ddl = f"ALTER TABLE products ADD COLUMN {col} {typedef}"
        try:
            with db.engine.begin() as conn:
                conn.execute(text(ddl_if))
            added.append(col)
            log.info("Added products.%s", col)
        except Exception:
            try:
                with db.engine.begin() as conn:
                    conn.execute(text(ddl))
                added.append(col)
                log.info("Added products.%s (fallback DDL)", col)
            except Exception as exc2:  # noqa: BLE001
                log.error("Failed to add products.%s: %s", col, exc2)
    return added
