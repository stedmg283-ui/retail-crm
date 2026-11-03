# Product import & top-sellers

## Schema extras
`products` gained nullable columns: `fabric`, `colors` (JSON text), `image_paths` (JSON text).
Applied via `ensure_product_columns()` on app start / `flask products ensure-schema`.
No flask-migrate; ALTER TABLE IF NOT EXISTS.

## Size policy
If a row lists multiple sizes (`S,M,L` / `sizes` column), one Product row is created per size.
- With a base SKU `RC-001` → `RC-001-S`, `RC-001-M`, …
- Without a SKU → `RC-<SLUG>-<SIZE>` (deterministic). Flagged in the import report.

## CLI
```bash
cd /workspace/retail-crm
.venv/bin/flask --app wsgi products import /path/to/catalog.zip
.venv/bin/flask --app wsgi products export-top-sellers
.venv/bin/flask --app wsgi products ensure-schema
```

## Watcher
```bash
.venv/bin/python scripts/watch_product_imports.py          # poll every 15s
.venv/bin/python scripts/watch_product_imports.py --once   # one scan
```
Watches `/workspace/incoming`, `/workspace/uploads`, and product-ish `*.zip` at `/workspace/`.
Extracts to `/workspace/incoming/extracted/<name>/`, reports to `/workspace/incoming/reports/import-<timestamp>.md` (+ `.json`), moves zips to `/workspace/incoming/processed/`.

## Top sellers (no customer PII)
- HTML: `GET /reports/top-sellers` (admin session)
- JSON: `GET /reports/top-sellers.json` (admin session **or** `X-Report-Token` / `?token=` matching `REPORT_TOKEN`)
- Static daily export: `exports/top_sellers.json` + `exports/top_sellers.html`
  Fields: sku, name, category, fabric, colors, unit_price, price_incl_gst (5%), stock_qty, in_stock, units_sold_7d, units_sold_30d, image_paths.

## Admin UI
- `/admin/products/import` — upload zip, run pipeline, show validation, link to top-sellers.

## Auth
Entire app requires admin session except `/login`, `/healthz`, static, WhatsApp webhooks, and tokened `/reports/*.json`.
Password hash: `ADMIN_PASSWORD_HASH` in `.env`. Plaintext only in `ADMIN_PASSWORD.txt` (chmod 600, gitignored).
Report token plaintext: `REPORT_TOKEN.txt` (chmod 600, gitignored).
