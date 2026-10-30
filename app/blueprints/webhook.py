"""WhatsApp Cloud API webhook: verify token + inbound + status updates."""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, request

from app.services.whatsapp import record_inbound, update_status_by_wamid

bp = Blueprint("webhook", __name__)
logger = logging.getLogger(__name__)


@bp.route("/whatsapp", methods=["GET", "POST"])
def whatsapp():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        expected = current_app.config.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
        if mode == "subscribe" and token == expected:
            return challenge or "", 200
        return "Forbidden", 403

    payload = request.get_json(silent=True) or {}
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                # Inbound messages
                for msg in value.get("messages", []):
                    from_phone = msg.get("from")  # digits without +
                    body = None
                    if msg.get("type") == "text":
                        body = (msg.get("text") or {}).get("body")
                    wamid = msg.get("id")
                    if from_phone:
                        record_inbound("+" + from_phone if not from_phone.startswith("+") else from_phone, body, wamid)
                # Status updates
                for st in value.get("statuses", []):
                    wamid = st.get("id")
                    status = st.get("status")
                    if wamid and status:
                        update_status_by_wamid(wamid, status)
    except Exception:
        logger.exception("Webhook processing error")
    return jsonify({"ok": True}), 200
