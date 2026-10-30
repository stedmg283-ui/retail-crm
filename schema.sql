-- Rabya Collection Retail CRM — reference SQL schema
-- SQLite / Postgres compatible (INTEGER PK; Numeric as DECIMAL)

CREATE TABLE IF NOT EXISTS employees (
  id INTEGER PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  role VARCHAR(80) NOT NULL DEFAULT 'Sales Associate',
  shift VARCHAR(40) NOT NULL DEFAULT 'Day',
  rate_type VARCHAR(20) NOT NULL DEFAULT 'daily', -- hourly|daily
  rate_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attendance (
  id INTEGER PRIMARY KEY,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  work_date DATE NOT NULL,
  check_in TIME,
  check_out TIME,
  notes VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (employee_id, work_date)
);

CREATE TABLE IF NOT EXISTS suppliers (
  id INTEGER PRIMARY KEY,
  name VARCHAR(160) NOT NULL UNIQUE,
  contact_name VARCHAR(120),
  phone VARCHAR(20),
  email VARCHAR(120),
  gstin VARCHAR(20),
  address TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_orders (
  id INTEGER PRIMARY KEY,
  supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
  bill_number VARCHAR(60) NOT NULL,
  po_date DATE NOT NULL,
  notes TEXT,
  payment_status VARCHAR(20) NOT NULL DEFAULT 'outstanding', -- paid|partial|outstanding
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
  id INTEGER PRIMARY KEY,
  purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  item_name VARCHAR(200) NOT NULL,
  quantity DECIMAL(12,2) NOT NULL DEFAULT 1,
  unit_cost DECIMAL(12,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS supplier_payments (
  id INTEGER PRIMARY KEY,
  purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  amount DECIMAL(12,2) NOT NULL,
  paid_on DATE NOT NULL,
  method VARCHAR(40),
  reference VARCHAR(80),
  notes VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY,
  phone VARCHAR(20) NOT NULL UNIQUE, -- E.164 e.g. +9198...
  name VARCHAR(120),
  email VARCHAR(120),
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY,
  invoice_number VARCHAR(40) NOT NULL UNIQUE, -- RC/2026-27/0001
  invoice_date DATE NOT NULL,
  customer_id INTEGER REFERENCES customers(id),
  customer_name VARCHAR(120),
  customer_phone VARCHAR(20),
  place_of_supply VARCHAR(10) NOT NULL DEFAULT 'intra', -- intra|inter
  customer_state_code VARCHAR(5),
  discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  taxable_total DECIMAL(12,2) NOT NULL DEFAULT 0,
  cgst_total DECIMAL(12,2) NOT NULL DEFAULT 0,
  sgst_total DECIMAL(12,2) NOT NULL DEFAULT 0,
  igst_total DECIMAL(12,2) NOT NULL DEFAULT 0,
  grand_total DECIMAL(12,2) NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'finalized',
  whatsapp_status VARCHAR(20) NOT NULL DEFAULT 'pending',
  pdf_path VARCHAR(500),
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS invoice_lines (
  id INTEGER PRIMARY KEY,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  item_name VARCHAR(200) NOT NULL,
  size VARCHAR(40),
  hsn VARCHAR(20),
  quantity DECIMAL(12,2) NOT NULL DEFAULT 1,
  unit_price DECIMAL(12,2) NOT NULL DEFAULT 0,
  discount DECIMAL(12,2) NOT NULL DEFAULT 0,
  gst_rate DECIMAL(5,2) NOT NULL DEFAULT 5,
  taxable_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  cgst_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  sgst_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  igst_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  line_total DECIMAL(12,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
  id INTEGER PRIMARY KEY,
  invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
  to_phone VARCHAR(20) NOT NULL,
  template_name VARCHAR(80),
  wamid VARCHAR(120),
  media_id VARCHAR(120),
  status VARCHAR(40) NOT NULL DEFAULT 'queued',
  response_json TEXT,
  error_message TEXT,
  pdf_saved_path VARCHAR(500),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_attendance_work_date ON attendance(work_date);
CREATE INDEX IF NOT EXISTS ix_invoices_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS ix_invoices_phone ON invoices(customer_phone);
CREATE INDEX IF NOT EXISTS ix_customers_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS ix_wa_wamid ON whatsapp_messages(wamid);


-- Extended tables (products, payroll runs, WA extras)

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY,
  sku VARCHAR(40) UNIQUE,
  name VARCHAR(200) NOT NULL,
  category VARCHAR(80),
  size VARCHAR(40),
  hsn VARCHAR(20) DEFAULT '6211',
  gst_rate DECIMAL(5,2) NOT NULL DEFAULT 5,
  unit_price DECIMAL(12,2) NOT NULL DEFAULT 0,
  cost_price DECIMAL(12,2),
  stock_qty DECIMAL(12,2) NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payroll_deductions (
  id INTEGER PRIMARY KEY,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  deduction_type VARCHAR(40) NOT NULL,
  amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  notes VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payroll_runs (
  id INTEGER PRIMARY KEY,
  period_type VARCHAR(20) NOT NULL DEFAULT 'monthly',
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'draft',
  gross_total DECIMAL(12,2) NOT NULL DEFAULT 0,
  deductions_total DECIMAL(12,2) NOT NULL DEFAULT 0,
  net_total DECIMAL(12,2) NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  finalized_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payroll_run_lines (
  id INTEGER PRIMARY KEY,
  payroll_run_id INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  days_worked DECIMAL(8,2) NOT NULL DEFAULT 0,
  regular_hours DECIMAL(10,2) NOT NULL DEFAULT 0,
  ot_hours DECIMAL(10,2) NOT NULL DEFAULT 0,
  gross_pay DECIMAL(12,2) NOT NULL DEFAULT 0,
  deductions DECIMAL(12,2) NOT NULL DEFAULT 0,
  net_pay DECIMAL(12,2) NOT NULL DEFAULT 0
);
