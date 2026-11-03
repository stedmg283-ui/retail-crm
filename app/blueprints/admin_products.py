"""Admin product import UI."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from app.services.product_import import import_from_path
from app.services.top_sellers import export_top_sellers

bp = Blueprint("admin_products", __name__)


@bp.route("/products/import", methods=["GET", "POST"])
def import_products():
    report = None
    if request.method == "POST":
        # CSRF
        from flask import session

        token = request.form.get("csrf_token") or ""
        if not token or token != session.get("_csrf"):
            flash("Invalid form token. Refresh and try again.", "danger")
            return redirect(url_for("admin_products.import_products"))

        f = request.files.get("catalog_zip")
        if not f or not f.filename:
            flash("Choose a .zip file to upload.", "warning")
            return redirect(url_for("admin_products.import_products"))
        name = secure_filename(f.filename)
        if not name.lower().endswith(".zip"):
            flash("Only .zip archives are accepted.", "danger")
            return redirect(url_for("admin_products.import_products"))

        incoming = Path(current_app.config["INCOMING_DIR"])
        incoming.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        dest = incoming / f"upload-{stamp}-{name}"
        f.save(dest)

        report = import_from_path(
            dest,
            static_root=Path(current_app.static_folder),
            extract_root=Path(current_app.config["INCOMING_EXTRACT_DIR"]),
            reports_dir=Path(current_app.config["INCOMING_REPORTS_DIR"]),
            commit=True,
        )
        exports = current_app.config.get("EXPORTS_DIR")
        if exports:
            export_top_sellers(Path(exports))

        flash(
            f"Import done: {report.created} created, {report.updated} updated, "
            f"{report.errors} errors.",
            "success" if report.errors == 0 else "warning",
        )
        if request.form.get("goto_top_sellers"):
            return redirect(url_for("reports.top_sellers_html"))

    # ensure csrf
    from flask import session
    import secrets

    if not session.get("_csrf"):
        session["_csrf"] = secrets.token_urlsafe(32)

    return render_template(
        "admin/products_import.html",
        report=report,
        csrf_token=session["_csrf"],
    )
