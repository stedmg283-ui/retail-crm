# Rabya Collection — Retail CRM

Flask retail CRM for a Bengaluru clothing/fashion shop (Rabya Collection abayas).

**Modules:** attendance & payroll (OT, deductions, CSV/PDF export), supplier POs & bills, GST sales invoices (ReportLab), WhatsApp Cloud API document delivery (template + dry-run), customer profiles with same-day phone dedup, daily sales dashboard with 7/30-day Chart.js trends.

## Quick start

```bash
cd retail-crm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — set SECRET_KEY; leave WhatsApp blank for DRY_RUN

export FLASK_APP=run.py
flask seed          # products, employees, suppliers, ~30 days of sales
pytest -q           # 20 tests: payroll OT, GST, dedup, WhatsApp dry-run
python run.py       # http://127.0.0.1:5000
```

Production-ish:

```bash
gunicorn -b 0.0.0.0:5000 run:app
```

## Environment variables

See `.env.example`. Important keys:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | `sqlite:///retail_crm.db` (default) or `postgresql+psycopg2://...` |
| `SHOP_*` / `SHOP_GSTIN` | Branding on PDFs |
| `DEFAULT_SHIFT_HOURS` / `OT_MULTIPLIER` | Payroll (9h / 1.5×) |
| `DEFAULT_GST_RATE` / `DEFAULT_HSN` | Apparel defaults (5% / 6211) |
| `INVOICE_PREFIX` | e.g. `RC` → `RC/2026-27/0001` |
| `WHATSAPP_TOKEN` | Cloud API token |
| `WHATSAPP_PHONE_NUMBER_ID` | Sending phone number id |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | WABA id |
| `WHATSAPP_TEMPLATE_NAME` / `_LANG` | Approved utility template |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Meta webhook verify |
| `WHATSAPP_API_VERSION` | Default `v20.0` |
| `SEND_ON_CREATE` | `false` recommended |
| `PENDING_SEND_DEBOUNCE_MINUTES` | Default `30` |
| `OWNER_EMAIL` / `SMTP_*` | Optional invoice BCC to owner |

**DRY_RUN:** if `WHATSAPP_TOKEN` or `WHATSAPP_PHONE_NUMBER_ID` is empty, sends are simulated — PDF still saved under `invoices/sent/` and a `whatsapp_messages` row with `status=dry_run` is logged.

## Same-day dedup & WhatsApp send policy

1. Phone is normalized to **E.164** (`+91…`).
2. A second sale for the **same phone on the same calendar day** **merges** into the existing invoice (lines appended, `pdf_version` bumped). **No automatic duplicate WhatsApp** on merge.
3. Sending options:
   - **Send now** / finalize on the invoice detail page.
   - `flask send-pending` — finalizes/sends `pending` invoices older than the debounce window (end-of-day cron).
   - Optional `SEND_ON_CREATE=true` to send on finalize of *new* invoices.

## Cloudflare Tunnel note

```bash
cloudflared tunnel --url http://127.0.0.1:5000
```

Point Meta’s webhook to:

`https://<your-tunnel>/webhook/whatsapp`  
(alias also available: `/webhooks/whatsapp`)

Verify token must match `WHATSAPP_WEBHOOK_VERIFY_TOKEN`. For a stable hostname, use a named Cloudflare Zero Trust tunnel + DNS CNAME.

## Approving a WhatsApp document-header template

Utility templates with a **Document** header are required outside the 24-hour customer-care window.

### Steps (Meta Business Manager / WhatsApp Manager)

1. Open [Meta Business Suite](https://business.facebook.com/) → **WhatsApp Manager** for your WABA.
2. **Message templates** → **Create template**.
3. Category: **Utility**. Name: e.g. `invoice_document` (must match `WHATSAPP_TEMPLATE_NAME`). Language: `English` (`en`).
4. **Header**: type **Document** (upload a sample PDF for review).
5. **Body** sample:

   ```
   Hello {{1}},

   Thank you for shopping at Rabya Collection.
   Your invoice {{2}} for ₹{{3}} is attached.

   For any help, reply to this chat or call us.
   ```

   `{{1}}` customer name · `{{2}}` invoice number · `{{3}}` amount.
6. Optional footer: `Rabya Collection · Bengaluru`.
7. Submit for review. Once **Active**, set:

   ```
   WHATSAPP_TEMPLATE_NAME=invoice_document
   WHATSAPP_TEMPLATE_LANG=en
   ```

8. Configure the webhook, subscribe to `messages`, test with credentials set (DRY_RUN off).

Send flow (see `app/services/whatsapp.py`): upload PDF via `/{phone-number-id}/media` → template message with DOCUMENT header + body params. Inside the 24h window the app may use freeform document messages instead.

## Project layout

```
retail-crm/
  app/
    blueprints/   # dashboard, sales, customers, purchases, attendance, payroll, webhook
    models/
    services/     # sales, payroll, pdf_invoice, whatsapp, phone, gst, …
    templates/ static/
  invoices/       # generated PDFs; sent/ copies for WhatsApp
  scripts/seed.py
  tests/
  docs/SPEC.md
  schema.sql
  run.py
  requirements.txt
  .env.example
```

## Deployment checklist

- [ ] `.env` from `.env.example` — `SECRET_KEY`, shop GSTIN/address
- [ ] SQLite or Postgres (`DATABASE_URL`)
- [ ] `flask seed` (optional)
- [ ] Real logo at `LOGO_PATH`
- [ ] Approve WhatsApp utility document template
- [ ] Set WhatsApp env vars (confirm DRY_RUN off)
- [ ] Expose `/webhook/whatsapp` via Cloudflare Tunnel
- [ ] Cron: `0 21 * * * cd /path && .venv/bin/flask send-pending` (IST evening)
- [ ] Cloudflare Access / auth in front of the UI for production
- [ ] Back up DB + `invoices/` daily

## Tests

```bash
pytest -q
```

Covers payroll OT math, GST intra/inter totals, same-day dedup merge, WhatsApp dry-run PDF save + log.
