def test_webhook_verify(client, app):
    with app.app_context():
        token = app.config["WHATSAPP_WEBHOOK_VERIFY_TOKEN"]
    resp = client.get(
        "/webhook/whatsapp",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": token,
            "hub.challenge": "12345",
        },
    )
    assert resp.status_code == 200
    assert resp.data == b"12345"


def test_webhook_verify_bad_token(client):
    resp = client.get(
        "/webhook/whatsapp",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "12345",
        },
    )
    assert resp.status_code == 403


def test_webhook_inbound(client, app):
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919876500077",
                                    "id": "wamid.inbound.test",
                                    "type": "text",
                                    "text": {"body": "Hello"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    resp = client.post("/webhook/whatsapp", json=payload)
    assert resp.status_code == 200
    with app.app_context():
        from app.models.customer import Customer

        c = Customer.query.filter_by(phone="+919876500077").first()
        assert c is not None
        assert c.last_inbound_at is not None
