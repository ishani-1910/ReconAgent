-- SQL Schema for Razorpay ReconAgent (DuckDB OLAP Layer)
-- Enforces DECIMAL(18,2) exact precision on all monetary fields.

-- 1. RAW STAGING TABLES
CREATE TABLE IF NOT EXISTS raw_oms_orders (
    order_id VARCHAR PRIMARY KEY,
    amount DECIMAL(18,2),
    currency VARCHAR,
    status VARCHAR,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_gateway_settlements (
    settlement_id VARCHAR,
    utr VARCHAR,
    gross_amount DECIMAL(18,2),
    mdr_fee DECIMAL(18,2),
    gst_fee DECIMAL(18,2),
    net_amount DECIMAL(18,2),
    refund_deducted DECIMAL(18,2),
    refund_id VARCHAR,
    captured_at DATE,
    expected_credit_date DATE
);

CREATE TABLE IF NOT EXISTS raw_bank_statements (
    bank_stmt_id VARCHAR PRIMARY KEY,
    credit_date DATE,
    credit_amount DECIMAL(18,2),
    raw_narration VARCHAR
);

-- 2. RECONCILIATION LEDGER
CREATE TABLE IF NOT EXISTS recon_ledger (
    bank_stmt_id VARCHAR PRIMARY KEY,
    settlement_id VARCHAR,
    utr VARCHAR,
    recon_status VARCHAR,        -- MATCHED_DETERMINISTIC | MATCHED_AI | EXCEPTION_HUMAN
    recon_tier VARCHAR,          -- TIER_1_SQL | TIER_2_AI | HUMAN_OVERRIDE
    variance_explained DECIMAL(18,2),
    ai_confidence DOUBLE,
    reason VARCHAR,
    matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
