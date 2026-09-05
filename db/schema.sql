-- SQL Schema for Razorpay ReconAgent (DuckDB OLAP Layer)
-- Enforces DECIMAL(18,2) exact financial precision on all monetary fields.

-- 1. RAW STAGING TABLES
CREATE TABLE IF NOT EXISTS raw_oms_orders (
    order_id VARCHAR PRIMARY KEY,
    amount DECIMAL(18,2),
    currency VARCHAR,
    payment_method VARCHAR,
    risk_tier VARCHAR,
    status VARCHAR,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_gateway_payments (
    payment_id VARCHAR PRIMARY KEY,
    order_id VARCHAR,
    settlement_id VARCHAR,
    amount DECIMAL(18,2),
    payment_method VARCHAR,
    fee DECIMAL(18,2),
    tax DECIMAL(18,2),
    holdback DECIMAL(18,2),
    net_amount DECIMAL(18,2),
    status VARCHAR,
    captured_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_gateway_settlements (
    settlement_id VARCHAR PRIMARY KEY,
    order_ids VARCHAR,
    utr VARCHAR,
    gross_amount DECIMAL(18,2),
    mdr_fee DECIMAL(18,2),
    gst_fee DECIMAL(18,2),
    holdback_amount DECIMAL(18,2),
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

-- 2. LEG 1: COMMERCIAL RECONCILIATION LEDGER (OMS <-> Gateway Payments)
CREATE TABLE IF NOT EXISTS commercial_recon_ledger (
    order_id VARCHAR PRIMARY KEY,
    payment_id VARCHAR,
    settlement_id VARCHAR,
    oms_amount DECIMAL(18,2),
    gateway_amount DECIMAL(18,2),
    payment_method VARCHAR,
    risk_tier VARCHAR,
    expected_fee DECIMAL(18,2),
    gateway_fee DECIMAL(18,2),
    status_oms VARCHAR,
    status_gateway VARCHAR,
    recon_status VARCHAR,        -- MATCHED_CLEAN | STATUS_MISMATCH | FEE_VARIANCE | AMOUNT_MISMATCH
    discrepancy_reason VARCHAR,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. LEG 2: CASH RECONCILIATION LEDGER (Gateway Batches <-> Bank Statements)
CREATE TABLE IF NOT EXISTS recon_ledger (
    bank_stmt_id VARCHAR PRIMARY KEY,
    settlement_id VARCHAR,
    utr VARCHAR,
    recon_status VARCHAR,        -- MATCHED_DETERMINISTIC | MATCHED_AI | MATCHED_RULE | MATCHED_HUMAN_OVERRIDE | EXCEPTION_HUMAN | CONFIRMED_FRAUD | ESCALATED_BANK
    recon_tier VARCHAR,          -- TIER_1_SQL | TIER_1_5_RULE | TIER_2_AI | HUMAN_OVERRIDE
    variance_explained DECIMAL(18,2),
    ai_confidence DOUBLE,
    tokens_used INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    reason VARCHAR,
    matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
