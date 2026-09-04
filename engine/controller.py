"""
Reconciliation Controller Pipeline.
Orchestrates data loading, Leg 1 commercial recon, Tier 1 SQL deterministic match,
Top-3 candidate retrieval, Tier 2 Gemini AI investigation, and ledger persistence.
"""

import os
from typing import Dict, Any
from db.duckdb_client import DuckDBClient
from engine.tier1_sql import Tier1SQLEngine
from engine.tier2_ai import Tier2AIInvestigator

class ReconController:
    def __init__(self, db_path: str = ":memory:"):
        self.db = DuckDBClient(db_path)
        self.tier1 = Tier1SQLEngine(self.db)
        self.tier2 = Tier2AIInvestigator()

    def run_full_pipeline(self, oms_path: str, gateway_path: str, bank_path: str) -> Dict[str, Any]:
        """Executes full multi-stage reconciliation pipeline."""
        # 1. Data Ingestion
        self.db.load_csv_data(oms_path, gateway_path, bank_path)

        # 2. Leg 1 Commercial Recon (OMS <-> Gateway)
        leg1_stats = self.tier1.execute_leg1_commercial_recon()

        # 3. Leg 2 Tier 1 Deterministic SQL Matching
        tier1_matched_count = self.tier1.execute_leg2_deterministic_match()

        # 4. Tier 2 Bounded AI Escalation for Unmatched Records
        unmatched_bank_records = self.tier1.get_unmatched_bank_records()
        tier2_matched_count = 0
        unresolved_count = 0

        for bank_rec in unmatched_bank_records:
            bank_stmt_id = bank_rec["bank_stmt_id"]
            candidates = self.tier1.get_top3_candidates(bank_rec)
            
            # Invoke Tier 2 AI Investigator
            decision = self.tier2.investigate(bank_rec, candidates)

            if decision.decision == "MATCH" and decision.confidence >= 0.85 and decision.selected_settlement_id:
                # Retrieve UTR for selected settlement
                utr_res = self.db.conn.execute(
                    f"SELECT utr FROM raw_gateway_settlements WHERE settlement_id = '{decision.selected_settlement_id}';"
                ).fetchone()
                utr = utr_res[0] if utr_res else ""

                self.db.conn.execute(f"""
                    INSERT INTO recon_ledger (
                        bank_stmt_id, settlement_id, utr, recon_status, recon_tier,
                        variance_explained, ai_confidence, reason, matched_at
                    ) VALUES (
                        '{bank_stmt_id}', '{decision.selected_settlement_id}', '{utr}',
                        'MATCHED_AI', 'TIER_2_AI', {decision.variance_explained},
                        {decision.confidence}, '{decision.reason.replace("'", "''")}', CURRENT_TIMESTAMP
                    );
                """)
                tier2_matched_count += 1
            else:
                self.db.conn.execute(f"""
                    INSERT INTO recon_ledger (
                        bank_stmt_id, settlement_id, utr, recon_status, recon_tier,
                        variance_explained, ai_confidence, reason, matched_at
                    ) VALUES (
                        '{bank_stmt_id}', NULL, NULL,
                        'EXCEPTION_HUMAN', 'TIER_2_AI', 0.00,
                        {decision.confidence}, '{decision.reason.replace("'", "''")}', CURRENT_TIMESTAMP
                    );
                """)
                unresolved_count += 1

        # 5. Calculate Final Recon Summary Metrics
        cfo_metrics = self.db.get_cfo_metrics()
        total_bank_records = len(unmatched_bank_records) + tier1_matched_count

        return {
            "leg1_stats": leg1_stats,
            "total_bank_records": total_bank_records,
            "tier1_matched_count": tier1_matched_count,
            "tier2_matched_count": tier2_matched_count,
            "unresolved_count": unresolved_count,
            "cfo_metrics": cfo_metrics
        }
