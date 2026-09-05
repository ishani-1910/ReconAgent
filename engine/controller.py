"""
Reconciliation Controller Pipeline.
Orchestrates:
  1. Multi-source CSV ingestion into persistent DuckDB.
  2. Leg 1 Commercial Recon (OMS <-> Gateway Payments 1:1 join & MDR validation).
  3. Leg 2 Tier 1 Deterministic Match (SQL Netting + UTR token).
  4. Top-3 Candidate Retrieval (Parameterized SQL).
  5. Tier 2 AI Investigation (Gemini GenAI) / Tier 1.5 Rule Fallback.
  6. Parameterized persistence into recon_ledger.
"""

import os
from typing import Dict, Any, Optional
from db.duckdb_client import DuckDBClient, DEFAULT_DB_PATH
from engine.tier1_sql import Tier1SQLEngine
from engine.tier2_ai import Tier2AIInvestigator

class ReconController:
    def __init__(self, db_path: str = DEFAULT_DB_PATH, api_key: Optional[str] = None):
        self.db = DuckDBClient(db_path)
        self.tier1 = Tier1SQLEngine(self.db)
        self.tier2 = Tier2AIInvestigator(api_key=api_key)

    def load_existing_results(self) -> Optional[Dict[str, Any]]:
        """
        Loads reconciliation KPIs directly from the persistent DuckDB ledger if already populated.
        Avoids re-executing API calls or queries when data already exists.
        """
        try:
            row_count = self.db.conn.execute("SELECT COUNT(*) FROM recon_ledger;").fetchone()[0]
            if row_count == 0:
                if self.restore_golden_ledger():
                    row_count = self.db.conn.execute("SELECT COUNT(*) FROM recon_ledger;").fetchone()[0]
                if row_count == 0:
                    return None

            cfo_metrics = self.db.get_cfo_metrics()
            leg1_stats = self.db.get_commercial_recon_metrics()
            leg2_metrics = self.db.get_recon_ledger_metrics()

            telemetry = self.db.conn.execute("""
                SELECT 
                    COALESCE(SUM(tokens_used), 0) as total_tokens,
                    COUNT(CASE WHEN recon_tier = 'TIER_2_AI' THEN 1 END) as total_calls
                FROM recon_ledger;
            """).fetchone()

            total_tokens = int(telemetry[0] or 0)
            total_calls = int(telemetry[1] or 0)

            return {
                "leg1_stats": leg1_stats,
                "cfo_metrics": cfo_metrics,
                "total_bank_records": leg2_metrics["total_bank_records"],
                "tier1_matched_count": leg2_metrics["tier1_matched_count"],
                "tier2_ai_matched": leg2_metrics["tier2_ai_matched"],
                "tier1_5_rule_matched": leg2_metrics["tier1_5_rule_matched"],
                "human_override_matched": leg2_metrics["human_override_matched"],
                "tier2_total_matched": leg2_metrics["tier2_total_matched"],
                "unresolved_count": leg2_metrics["unresolved_count"],
                "total_tokens_spent": total_tokens,
                "total_api_calls": total_calls,
                "is_live_ai_active": (total_calls > 0 and total_tokens > 0)
            }
        except Exception:
            return None

    def restore_golden_ledger(self) -> Optional[Dict[str, Any]]:
        """Restores live DuckDB database from golden baseline and returns fresh results."""
        if self.db.restore_golden_ledger():
            return self.load_existing_results()
        return None

    def run_full_pipeline(
        self,
        oms_path: str,
        payments_path: str,
        settlements_path: str,
        bank_path: str
    ) -> Dict[str, Any]:
        """Executes full multi-stage reconciliation pipeline with strictly parameterized statements."""
        # 1. Staging Data Ingestion
        self.db.load_csv_data(oms_path, payments_path, settlements_path, bank_path)

        # 2. Leg 1 Commercial Recon (OMS Orders <-> Gateway Payments)
        leg1_stats = self.tier1.execute_leg1_commercial_recon()

        # 3. Leg 2 Tier 1 Deterministic SQL Cash Matching
        tier1_matched_count = self.tier1.execute_leg2_deterministic_match()

        # 4. Tier 2 / Tier 1.5 Escalation for Unmatched Records
        unmatched_bank_records = self.tier1.get_unmatched_bank_records()
        tier2_ai_matched = 0
        tier1_5_rule_matched = 0
        unresolved_count = 0

        insert_sql = """
        INSERT OR REPLACE INTO recon_ledger (
            bank_stmt_id, settlement_id, utr, recon_status, recon_tier,
            variance_explained, ai_confidence, tokens_used, latency_ms, reason, matched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
        """

        for bank_rec in unmatched_bank_records:
            bank_stmt_id = bank_rec["bank_stmt_id"]
            candidates = self.tier1.get_top3_candidates(bank_rec)

            decision = self.tier2.investigate(bank_rec, candidates)

            if decision.decision == "MATCH" and decision.selected_settlement_id:
                # Retrieve UTR for the selected settlement via parameterized query
                utr_res = self.db.conn.execute(
                    "SELECT utr FROM raw_gateway_settlements WHERE settlement_id = ?;",
                    [decision.selected_settlement_id]
                ).fetchone()
                utr = utr_res[0] if utr_res else ""

                status = "MATCHED_AI" if decision.recon_tier == "TIER_2_AI" else "MATCHED_RULE"
                if decision.recon_tier == "TIER_2_AI":
                    tier2_ai_matched += 1
                else:
                    tier1_5_rule_matched += 1

                self.db.conn.execute(insert_sql, [
                    bank_stmt_id,
                    decision.selected_settlement_id,
                    utr,
                    status,
                    decision.recon_tier,
                    decision.variance_explained,
                    decision.confidence,
                    decision.tokens_used,
                    decision.latency_ms,
                    decision.reason
                ])
            else:
                unresolved_count += 1
                self.db.conn.execute(insert_sql, [
                    bank_stmt_id,
                    None,
                    None,
                    "EXCEPTION_HUMAN",
                    decision.recon_tier,
                    0.00,
                    decision.confidence,
                    decision.tokens_used,
                    decision.latency_ms,
                    decision.reason
                ])

        cfo_metrics = self.db.get_cfo_metrics()
        leg2_metrics = self.db.get_recon_ledger_metrics()

        return {
            "leg1_stats": leg1_stats,
            "cfo_metrics": cfo_metrics,
            "total_bank_records": leg2_metrics["total_bank_records"],
            "tier1_matched_count": leg2_metrics["tier1_matched_count"],
            "tier2_ai_matched": leg2_metrics["tier2_ai_matched"],
            "tier1_5_rule_matched": leg2_metrics["tier1_5_rule_matched"],
            "human_override_matched": leg2_metrics["human_override_matched"],
            "tier2_total_matched": leg2_metrics["tier2_total_matched"],
            "unresolved_count": leg2_metrics["unresolved_count"],
            "total_tokens_spent": self.tier2.total_tokens_spent,
            "total_api_calls": self.tier2.total_api_calls,
            "is_live_ai_active": self.tier2.is_live_ai_active
        }
