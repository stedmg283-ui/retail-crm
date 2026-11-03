"""Admin session auth — gates the entire CRM except healthz / login / static / tokened JSON."""
from __future__ import annotations

import time
from functools import wraps
from typing import Callable

from flask import (
    Flask,
    redirect,
    request,
    session,
    url_for,
    flash,
    current_app,
)
from werkzeug.security import check_password_hash

# In-process lockout tracker: ip -> {fails, locked_until}
_LOCKOUT: dict[str, dict] = {}


def is_logged_in() -> bool:
    return bool(session.get("admin_authenticated"))


def client_ip() -> str:
    # Prefer Cloudflare / proxy headers when present, else remote_addr
    return (
        request.headers.get("CF-Connecting-IP")
        or (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        or request.remote_addr
        or "unknown"
    )


def record_failed_login(ip: str) -> None:
    cfg = current_app.config
    max_fails = int(cfg.get("LOGIN_MAX_FAILURES", 5))
    lock_secs = int(cfg.get("LOGIN_LOCKOUT_SECONDS", 300))
    entry = _LOCKOUT.setdefault(ip, {"fails": 0, "locked_until": 0.0})
    entry["fails"] += 1
    if entry["fails"] >= max_fails:
        entry["locked_until"] = time.time() + lock_secs


def clear_failed_login(ip: str) -> None:
    _LOCKOUT.pop(ip, None)


def is_locked_out(ip: str) -> tuple[bool, int]:
    entry = _LOCKOUT.get(ip)
    if not entry:
        return False, 0
    remaining = int(entry.get("locked_until", 0) - time.time())
    if remaining > 0:
        return True, remaining
    if remaining <= 0 and entry.get("locked_until"):
        # lock expired — reset
        _LOCKOUT.pop(ip, None)
    return False, 0


def verify_admin_password(password: str) -> bool:
    pw_hash = (current_app.config.get("ADMIN_PASSWORD_HASH") or "").strip()
    if not pw_hash or not password:
        return False
    try:
        return check_password_hash(pw_hash, password)
    except Exception:  # noqa: BLE001
        return False


def login_user() -> None:
    session.clear()
    session["admin_authenticated"] = True
    session["admin_login_at"] = time.time()
    session.permanent = True


def logout_user() -> None:
    session.clear()


PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.logout",
    "auth.healthz",
    "static",
}
# Meta WhatsApp webhooks must remain reachable without a session.
PUBLIC_ENDPOINT_PREFIXES = (
    "webhook.",
    "webhooks.",
)
# Prefixes that may be accessed with REPORT_TOKEN (checked inside the view)
TOKEN_JSON_PATH_SUFFIXES = (".json",)


def install_auth_guard(app: Flask) -> None:
    @app.before_request
    def _require_admin():  # noqa: ANN202
        # Always allow health + static + login page
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if request.endpoint and request.endpoint.startswith("static"):
            return None
        if request.endpoint and request.endpoint.startswith(PUBLIC_ENDPOINT_PREFIXES):
            return None
        # JSON report token bypass (view still validates token)
        if request.path.startswith("/reports/") and request.path.endswith(".json"):
            return None
        if is_logged_in():
            return None
        # Unauthenticated — redirect to login for browsers; 401 for API-ish
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            from flask import jsonify

            return jsonify({"error": "authentication required"}), 401
        return redirect(url_for("auth.login", next=request.full_path if request.query_string else request.path))
