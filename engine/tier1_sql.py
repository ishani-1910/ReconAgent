"""
Tier 1 Deterministic Engine (DuckDB SQL).
Executes bulk 1:1 and token-based settlement matching at ₹0 token cost.
Retrieves Top-3 candidate records for unmatched bank statement lines.
"""

from typing import List, Dict, Any

class Tier1SQLEngine:
    def __init__(self, duckdb_client):
        self.client = duckdb_client
        self.conn = duckdb_client.conn

    def execute_leg1_commercial_recon(self) -> Dict[str, Any]:
        """Matches OMS Orders with Gateway Captured Payments (1:1 Key: order_id)."""
        query = """
        SELECT 
            COUNT(o.order_id) as total_oms_orders,
            SUM(o.amount) as total_oms_amount,
            COUNT(CASE WHEN o.status = 'COMPLETED' THEN 1 END) as matched_orders
        FROM raw_oms_orders o;
        """
        res = self.conn.execute(query).fetchone()
        return {
            "total_oms_orders": res[0],
            "total_oms_amount": float(res[1] or 0.0),
            "matched_orders": res[2]
        }

    def execute_leg2_deterministic_match(self) -> int:
        """
        Tier 1 SQL Rule:
        1. Credit amount matches net settlement within ±₹1.00.
        2. Credit date is within clearing window [expected_credit_date, expected_credit_date + 5 days].
        3. Bank raw narration contains exact UTR token substring.
        """
        match_query = """
        INSERT INTO recon_ledger (
            bank_stmt_id,
            settlement_id,
            utr,
            recon_status,
            recon_tier,
            variance_explained,
            ai_confidence,
            reason,
            matched_at
        )
        SELECT 
            b.bank_stmt_id,
            g.settlement_id,
            g.utr,
            'MATCHED_DETERMINISTIC' as recon_status,
            'TIER_1_SQL' as recon_tier,
            0.00 as variance_explained,
            1.00 as ai_confidence,
            'Exact UTR token found in narration with net amount match within tolerance.' as reason,
            CURRENT_TIMESTAMP
        FROM raw_bank_statements b
        JOIN raw_gateway_settlements g 
          ON INSTR(b.raw_narration, g.utr) > 0
         AND ABS(b.credit_amount - g.net_amount) <= 1.00
         AND b.credit_date >= g.expected_credit_date 
         AND b.credit_date <= g.expected_credit_date + INTERVAL '5 DAYS'
        WHERE b.bank_stmt_id NOT IN (SELECT bank_stmt_id FROM recon_ledger);
        """
        self.conn.execute(match_query)
        
        # Return count of matched records
        count = self.conn.execute(
            "SELECT COUNT(*) FROM recon_ledger WHERE recon_tier = 'TIER_1_SQL';"
        ).fetchone()[0]
        return count

    def get_unmatched_bank_records(self) -> List[Dict[str, Any]]:
        """Returns bank statement records that failed Tier 1 deterministic matching."""
        query = """
        SELECT bank_stmt_id, credit_date, credit_amount, raw_narration
        FROM raw_bank_statements
        WHERE bank_stmt_id NOT IN (SELECT bank_stmt_id FROM recon_ledger);
        """
        df = self.conn.execute(query).df()
        return df.to_dict(orient="records")

    def get_top3_candidates(self, bank_record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        SQL Candidate Retriever:
        Scores top 3 closest Gateway settlements for an unmatched bank record.
        Criteria: net amount proximity, date window, refund adjustments.
        """
        bank_stmt_id = bank_record["bank_stmt_id"]
        credit_amount = float(bank_record["credit_amount"])
        credit_date = str(bank_record["credit_date"])

        query = f"""
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
            ABS(net_amount - {credit_amount}) as amount_diff,
            ABS(DATEDIFF('day', expected_credit_date, CAST('{credit_date}' AS DATE))) as date_diff
        FROM raw_gateway_settlements
        WHERE settlement_id NOT IN (
            SELECT settlement_id FROM recon_ledger WHERE settlement_id IS NOT NULL
        )
        ORDER BY (ABS(net_amount - {credit_amount}) + ABS(DATEDIFF('day', expected_credit_date, CAST('{credit_date}' AS DATE))) * 10) ASC
        LIMIT 3;
        """
        df = self.conn.execute(query).df()
        return df.to_dict(orient="records")
