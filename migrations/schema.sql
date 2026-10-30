-- Rabya Collection Retail CRM — Postgres schema
-- Also created automatically via SQLAlchemy db.create_all()

CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(120),
    email VARCHAR(120),
    notes TEXT,
    last_inbound_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_customers_phone ON customers (phone);
CREATE INDEX IF NOT EXISTS ix_customers_last_inbound ON customers (last_inbound_at);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(40) UNIQUE,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(80),
    size VARCHAR(40),
    hsn VARCHAR(20) DEFAULT '6211',
    gst_rate NUMERIC(5,2) NOT NULL DEFAULT 5,
    unit_price NUMERIC(12,2) NOT NULL DEFAULT 0,
    cost_price NUMERIC(12,2),
    stock_qty NUMERIC(12,2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_products_name ON products (name);

CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(40) NOT NULL UNIQUE,
    invoice_date DATE NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    customer_name VARCHAR(120),
    customer_phone VARCHAR(20),
    place_of_supply VARCHAR(10) NOT NULL DEFAULT 'intra',
    customer_state_code VARCHAR(5),
    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    taxable_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    cgst_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    sgst_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    igst_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    grand_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    whatsapp_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    pdf_version INTEGER NOT NULL DEFAULT 1,
    last_sent_pdf_version INTEGER,
    pdf_path VARCHAR(500),
    notes TEXT,
    finalized_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_invoices_date ON invoices (invoice_date);
CREATE INDEX IF NOT EXISTS ix_invoices_phone ON invoices (customer_phone);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    item_name VARCHAR(200) NOT NULL,
    size VARCHAR(40),
    hsn VARCHAR(20),
    quantity NUMERIC(12,2) NOT NULL DEFAULT 1,
    unit_price NUMERIC(12,2) NOT NULL DEFAULT 0,
    discount NUMERIC(12,2) NOT NULL DEFAULT 0,
    gst_rate NUMERIC(5,2) NOT NULL DEFAULT 5,
    taxable_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    cgst_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    sgst_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    igst_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    line_total NUMERIC(12,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
    customer_id INTEGER REFERENCES customers(id),
    direction VARCHAR(10) NOT NULL DEFAULT 'outbound',
    to_phone VARCHAR(20) NOT NULL,
    message_type VARCHAR(40),
    template_name VARCHAR(80),
    wamid VARCHAR(120),
    media_id VARCHAR(120),
    status VARCHAR(40) NOT NULL DEFAULT 'queued',
    body_preview VARCHAR(500),
    response_json TEXT,
    error_message TEXT,
    pdf_saved_path VARCHAR(500),
    idempotency_key VARCHAR(120) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_wa_wamid ON whatsapp_messages (wamid);

CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(160) NOT NULL UNIQUE,
    contact_name VARCHAR(120),
    phone VARCHAR(20),
    email VARCHAR(120),
    gstin VARCHAR(20),
    address TEXT,
    state_code VARCHAR(5),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id SERIAL PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    bill_number VARCHAR(60) NOT NULL,
    po_date DATE NOT NULL,
    place_of_supply VARCHAR(10) NOT NULL DEFAULT 'intra',
    taxable_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    cgst_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    sgst_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    igst_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    grand_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    notes TEXT,
    payment_status VARCHAR(20) NOT NULL DEFAULT 'outstanding',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
    id SERIAL PRIMARY KEY,
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    item_name VARCHAR(200) NOT NULL,
    hsn VARCHAR(20),
    quantity NUMERIC(12,2) NOT NULL DEFAULT 1,
    unit_cost NUMERIC(12,2) NOT NULL DEFAULT 0,
    gst_rate NUMERIC(5,2) NOT NULL DEFAULT 5,
    taxable_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    cgst_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    sgst_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    igst_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    line_total NUMERIC(12,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS supplier_payments (
    id SERIAL PRIMARY KEY,
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    amount NUMERIC(12,2) NOT NULL,
    paid_on DATE NOT NULL,
    method VARCHAR(40),
    reference VARCHAR(80),
    notes VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    role VARCHAR(80) NOT NULL DEFAULT 'Sales Associate',
    phone VARCHAR(20),
    shift VARCHAR(40) NOT NULL DEFAULT 'Day',
    shift_start TIME,
    shift_end TIME,
    rate_type VARCHAR(20) NOT NULL DEFAULT 'daily',
    rate_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    pf_percent NUMERIC(5,2) DEFAULT 0,
    esi_percent NUMERIC(5,2) DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attendance (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    work_date DATE NOT NULL,
    check_in TIME,
    check_out TIME,
    status VARCHAR(20) NOT NULL DEFAULT 'present',
    late_minutes INTEGER NOT NULL DEFAULT 0,
    notes VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (employee_id, work_date)
);

CREATE TABLE IF NOT EXISTS payroll_deductions (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    deduction_type VARCHAR(40) NOT NULL,
    amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    notes VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id SERIAL PRIMARY KEY,
    period_type VARCHAR(20) NOT NULL DEFAULT 'monthly',
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    gross_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    deductions_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    net_total NUMERIC(12,2) NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    finalized_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payroll_run_lines (
    id SERIAL PRIMARY KEY,
    payroll_run_id INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    days_worked NUMERIC(8,2) NOT NULL DEFAULT 0,
    regular_hours NUMERIC(10,2) NOT NULL DEFAULT 0,
    ot_hours NUMERIC(10,2) NOT NULL DEFAULT 0,
    gross_pay NUMERIC(12,2) NOT NULL DEFAULT 0,
    deductions NUMERIC(12,2) NOT NULL DEFAULT 0,
    net_pay NUMERIC(12,2) NOT NULL DEFAULT 0
);
