# Rabya Collection Retail CRM — Module Spec

Bengaluru clothing/fashion shop CRM (owner: Sted). Flask + SQLAlchemy + ReportLab + WhatsApp Cloud API.

## 1. Attendance + Payroll

**Employees** store name, role, shift (Day/Evening), rate type (`hourly` | `daily`), rate amount, optional PF/ESI %.

**Attendance** is one row per employee per calendar day (`check_in`, `check_out`, status). Hours derive from the time delta (overnight-safe).

**Payroll rules**
- `DEFAULT_SHIFT_HOURS` (default **9**) and `OT_MULTIPLIER` (default **1.5**).
- Hours ≤ shift → regular; beyond → OT.
- **Hourly**: regular = hours × rate; OT = OT hours × rate × multiplier.
- **Daily**: full day if hours ≥ shift; prorated if under; OT = OT hours × (daily/shift) × multiplier.
- Deductions (absence/late/advance/PF/ESI/other) and payroll **runs** (snapshots).
- Monthly/weekly/daily views; **CSV** and **PDF** export (`/payroll/export.csv`, `/payroll/export.pdf`).

## 2. Purchase orders + supplier bills

**Suppliers** with contact/GSTIN. **Purchase orders** have bill number, date, line items, payment status `outstanding` | `partial` | `paid`.

**Supplier payments** append to a PO; status recomputed from paid vs subtotal.

**Views** under `/purchases` (and `/suppliers` alias): list, detail, outstanding, branded **supplier bill PDF**.

## 3. Sales invoices (POS)

POS form: customer phone/name, place of supply (`intra` → CGST+SGST, `inter` → IGST), per-line item/size/HSN/qty/rate/discount/GST%, invoice-level discount. Optional product catalog.

**Numbering**: `{INVOICE_PREFIX}/{FY}/{seq:04d}` e.g. `RC/2026-27/0001` (Indian FY Apr–Mar).

**PDF**: shop name, logo placeholder, GSTIN, line table, CGST/SGST/IGST, grand total, **amount in words**.

## 4. WhatsApp delivery

Meta **WhatsApp Cloud API** (`graph.facebook.com/{version}/{phone_number_id}`).

Flow:
1. Ensure PDF on disk; copy under `invoices/sent/`.
2. Upload PDF → `media_id`.
3. Inside 24h service window: freeform document; otherwise **template** with DOCUMENT header + body params (name, invoice no, amount).
4. Persist `WhatsAppMessage` (wamid, status, idempotency key `inv-{id}-v{pdf_version}`).

**DRY_RUN** when token/phone id missing.

**Webhook**: `GET/POST /webhook/whatsapp` (+ `/webhooks/whatsapp`) — verify token, inbound (opens 24h window), status callbacks.

## 5. Customers + same-day dedup

Phone normalized to **E.164** (`+91` default) is the unique key. History view + lifetime total. Lookup by phone.

**Same-day dedup:** merge lines into today’s non-void invoice for that phone; bump `pdf_version`; mark `whatsapp_status=pending`. **No auto re-send on merge.**

**Send policy:** finalize / **Send now** / `flask send-pending` (debounce). Optional `SEND_ON_CREATE` on finalize of new invoices only.

## 6. Dashboard

Today’s (or selected day’s) revenue + transaction count, top items (30d), Chart.js 7-day and 30-day revenue (`/api/revenue-trend`).

## Tech notes

- Default DB: SQLite. Postgres via `DATABASE_URL`.
- Optional owner BCC of invoice PDFs via `OWNER_EMAIL` + `SMTP_*`.
- Put Cloudflare Access or basic auth in front for production.
