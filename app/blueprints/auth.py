"""Login / logout / healthz."""
from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.auth import (
    clear_failed_login,
    client_ip,
    is_locked_out,
    is_logged_in,
    login_user,
    logout_user,
    record_failed_login,
    verify_admin_password,
)

bp = Blueprint("auth", __name__)


@bp.route("/healthz")
def healthz():
    return {"status": "ok", "service": "retail-crm"}, 200


@bp.route("/login", methods=["GET", "POST"])
def login():
    if is_logged_in():
        return redirect(url_for("dashboard.index"))

    ip = client_ip()
    locked, remaining = is_locked_out(ip)
    error = None

    if request.method == "POST":
        if locked:
            error = f"Too many failed attempts. Try again in {remaining}s."
        else:
            password = request.form.get("password") or ""
            # CSRF: Flask-WTF optional — we use a simple session token
            token = request.form.get("csrf_token") or ""
            expected = _csrf_token()
            if not token or token != expected:
                error = "Invalid form token. Refresh and try again."
                record_failed_login(ip)
            elif verify_admin_password(password):
                clear_failed_login(ip)
                login_user()
                nxt = request.args.get("next") or url_for("dashboard.index")
                # prevent open redirect
                if not nxt.startswith("/"):
                    nxt = url_for("dashboard.index")
                flash("Signed in.", "success")
                return redirect(nxt)
            else:
                record_failed_login(ip)
                locked, remaining = is_locked_out(ip)
                if locked:
                    error = f"Too many failed attempts. Try again in {remaining}s."
                else:
                    error = "Incorrect password."

    return render_template(
        "auth/login.html",
        error=error,
        csrf_token=_csrf_token(),
        locked=locked,
        remaining=remaining,
    )


@bp.route("/logout", methods=["POST", "GET"])
def logout():
    logout_user()
    flash("Signed out.", "info")
    return redirect(url_for("auth.login"))


def _csrf_token() -> str:
    from flask import session
    import secrets

    tok = session.get("_csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf"] = tok
    return tok
