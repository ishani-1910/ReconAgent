"""
Tier 1 Deterministic Engine (DuckDB SQL).
Executes:
  1. Leg 1 Commercial Recon (OMS <-> Gateway Payments 1:1 join & MDR validation).
  2. Leg 2 Deterministic Cash Matching (UTR token, tolerance, clearing window).
  3. Top-3 Candidate Scoring (Strictly Parameterized SQL).
"""

from typing import List, Dict, Any

class Tier1SQLEngine:
    def __init__(self, duckdb_client):
        self.client = duckdb_client
        self.conn = duckdb_client.conn

    def execute_leg1_commercial_recon(self) -> Dict[str, Any]:
        """
        Executes true 1:1 order-level commercial reconciliation between OMS and Gateway.
        Validates:
          - Gross amount consistency (OMS amount vs Gateway captured amount)
          - State consistency (OMS COMPLETED vs Gateway CAPTURED)
          - Contractual fee adherence (MDR by payment method: UPI 0%, Debit 0.9%, Credit 2.0%, Netbanking 1.8%)
        """
        self.conn.execute("DELETE FROM commercial_recon_ledger;")

        query = """
        INSERT OR REPLACE INTO commercial_recon_ledger (
            order_id,
            payment_id,
            settlement_id,
            oms_amount,
            gateway_amount,
            payment_method,
            risk_tier,
            expected_fee,
            gateway_fee,
            status_oms,
            status_gateway,
            recon_status,
            discrepancy_reason,
            checked_at
        )
        WITH expected_fees AS (
            SELECT 
                o.order_id,
                o.amount as oms_amount,
                o.payment_method,
                o.risk_tier,
                o.status as status_oms,
                p.payment_id,
                p.settlement_id,
                p.amount as gateway_amount,
                p.fee as gateway_fee,
                p.status as status_gateway,
                CASE 
                    WHEN o.payment_method = 'UPI' THEN 0.00
                    WHEN o.payment_method = 'DEBIT_CARD' THEN ROUND(o.amount * 0.009, 2)
                    WHEN o.payment_method = 'CREDIT_CARD' THEN ROUND(o.amount * 0.020, 2)
                    WHEN o.payment_method = 'NETBANKING' THEN ROUND(o.amount * 0.018, 2)
                    ELSE ROUND(o.amount * 0.020, 2)
                END as expected_fee
            FROM raw_oms_orders o
            LEFT JOIN raw_gateway_payments p ON o.order_id = p.order_id
        )
        SELECT 
            order_id,
            payment_id,
            settlement_id,
            oms_amount,
            gateway_amount,
            payment_method,
            risk_tier,
            expected_fee,
            gateway_fee,
            status_oms,
            status_gateway,
            CASE 
                WHEN status_gateway IS NULL OR status_gateway != 'CAPTURED' THEN 'STATUS_MISMATCH'
                WHEN ABS(COALESCE(gateway_amount, 0.0) - oms_amount) > 0.01 THEN 'AMOUNT_MISMATCH'
                WHEN ABS(COALESCE(gateway_fee, 0.0) - expected_fee) > 1.00 THEN 'FEE_VARIANCE'
                ELSE 'MATCHED_CLEAN'
            END as recon_status,
            CASE 
                WHEN status_gateway IS NULL THEN 'Order missing from Gateway'
                WHEN status_gateway != 'CAPTURED' THEN 'Gateway payment not captured (Status: ' || status_gateway || ')'
                WHEN ABS(COALESCE(gateway_amount, 0.0) - oms_amount) > 0.01 THEN 'Captured amount does not match OMS order amount'
                WHEN ABS(COALESCE(gateway_fee, 0.0) - expected_fee) > 1.00 THEN 'MDR overcharged: billed ₹' || CAST(gateway_fee AS VARCHAR) || ' vs contractual ₹' || CAST(expected_fee AS VARCHAR)
                ELSE 'Order verified clean with contractual fee'
            END as discrepancy_reason,
            CURRENT_TIMESTAMP
        FROM expected_fees;
        """
        self.conn.execute(query)
        return self.client.get_commercial_recon_metrics()

    def execute_leg2_deterministic_match(self) -> int:
        """
        Tier 1 Deterministic SQL Cash Matching:
        1. Net settlement amount matches within ±₹1.00.
        2. Credit date is within clearing window [expected_credit_date, expected_credit_date + 5 days].
        3. Bank raw narration contains exact UTR token substring.
        4. Strict tie detection: ensures only unambiguous 1:1 matches are auto-cleared.
        """
        match_query = """
        WITH candidates AS (
            SELECT 
                b.bank_stmt_id,
                g.settlement_id,
                g.utr,
                COUNT(*) OVER (PARTITION BY b.bank_stmt_id) as bank_match_count,
                COUNT(*) OVER (PARTITION BY g.settlement_id) as setl_match_count
            FROM raw_bank_statements b
            JOIN raw_gateway_settlements g 
              ON INSTR(b.raw_narration, g.utr) > 0
             AND ABS(b.credit_amount - g.net_amount) <= 1.00
             AND b.credit_date >= g.expected_credit_date 
             AND b.credit_date <= g.expected_credit_date + INTERVAL '5 DAYS'
            WHERE b.bank_stmt_id NOT IN (SELECT bank_stmt_id FROM recon_ledger)
        )
        INSERT OR REPLACE INTO recon_ledger (
            bank_stmt_id,
            settlement_id,
            utr,
            recon_status,
            recon_tier,
            variance_explained,
            ai_confidence,
            tokens_used,
            latency_ms,
            reason,
            matched_at
        )
        SELECT 
            c.bank_stmt_id,
            c.settlement_id,
            c.utr,
            'MATCHED_DETERMINISTIC' as recon_status,
            'TIER_1_SQL' as recon_tier,
            0.00 as variance_explained,
            1.00 as ai_confidence,
            0 as tokens_used,
            0 as latency_ms,
            'Exact UTR token found in narration with net amount match within tolerance (Unambiguous 1:1).' as reason,
            CURRENT_TIMESTAMP
        FROM candidates c
        WHERE c.bank_match_count = 1 AND c.setl_match_count = 1;
        """
        self.conn.execute(match_query)
        
        count = self.conn.execute(
            "SELECT COUNT(*) FROM recon_ledger WHERE recon_tier = 'TIER_1_SQL';"
        ).fetchone()[0]
        return count

    def get_unmatched_bank_records(self) -> List[Dict[str, Any]]:
        """Returns bank statement records that failed Tier 1 deterministic matching."""
        query = """
        SELECT bank_stmt_id, credit_date, credit_amount, raw_narration
        FROM raw_bank_statements
        WHERE bank_stmt_id NOT IN (SELECT bank_stmt_id FROM recon_ledger)
        ORDER BY bank_stmt_id ASC;
        """
        df = self.conn.execute(query).df()
        return df.to_dict(orient="records")

    def get_top3_candidates(self, bank_record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        SQL Candidate Retriever using STRICT PARAMETERIZED QUERIES.
        Scores top 3 closest Gateway settlements by amount proximity and date drift.
        """
        credit_amount = float(bank_record["credit_amount"])
        credit_date = str(bank_record["credit_date"])

        query = """
        SELECT 
            settlement_id,
            utr,
            gross_amount,
            mdr_fee,
            gst_fee,
            net_amount,
            refund_deducted,
            refund_id,
            expected_credit_date,
            ABS(net_amount - ?) as amount_diff,
            ABS(DATEDIFF('day', expected_credit_date, CAST(? AS DATE))) as date_diff
        FROM raw_gateway_settlements
        WHERE settlement_id NOT IN (
            SELECT settlement_id FROM recon_ledger WHERE settlement_id IS NOT NULL
        )
        ORDER BY (ABS(net_amount - ?) + ABS(DATEDIFF('day', expected_credit_date, CAST(? AS DATE))) * 10) ASC
        LIMIT 3;
        """
        df = self.conn.execute(query, [credit_amount, credit_date, credit_amount, credit_date]).df()
        return df.to_dict(orient="records")
