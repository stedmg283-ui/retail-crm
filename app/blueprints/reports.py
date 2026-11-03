"""Read-only catalog reports for reel automation (no customer PII)."""
from __future__ import annotations

import hmac
import os
from functools import wraps

from flask import Blueprint, current_app, jsonify, render_template, request, abort

from app.services.top_sellers import export_top_sellers, top_sellers_payload

bp = Blueprint("reports", __name__)


def _report_token_ok() -> bool:
    expected = (current_app.config.get("REPORT_TOKEN") or "").strip()
    if not expected:
        return False
    provided = (
        request.headers.get("X-Report-Token")
        or request.args.get("token")
        or ""
    ).strip()
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


def require_report_access(view):
    """HTML pages need session login; JSON may use REPORT_TOKEN instead."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        from app.auth import is_logged_in

        wants_json = request.path.endswith(".json") or request.accept_mimetypes.best == "application/json"
        if wants_json or request.path.endswith(".json"):
            if is_logged_in() or _report_token_ok():
                return view(*args, **kwargs)
            abort(401)
        if not is_logged_in():
            from flask import redirect, url_for

            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@bp.route("/top-sellers")
@require_report_access
def top_sellers_html():
    payload = top_sellers_payload()
    # also refresh static export for the reel agent
    exports = current_app.config.get("EXPORTS_DIR")
    if exports:
        export_top_sellers(exports)
    return render_template("reports/top_sellers.html", payload=payload)


@bp.route("/top-sellers.json")
@require_report_access
def top_sellers_json():
    payload = top_sellers_payload()
    exports = current_app.config.get("EXPORTS_DIR")
    if exports:
        export_top_sellers(exports)
    return jsonify(payload)
