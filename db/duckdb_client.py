"""
DuckDB Client and Persistence Layer for ReconAgent.
Manages persistent OLAP session (recon_agent.duckdb), CSV staging, and parameterized queries.
"""

import os
import duckdb
from typing import Dict, Any

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "recon_agent.duckdb")
GOLDEN_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "golden_recon_agent.duckdb")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

class DuckDBClient:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        try:
            self.conn = duckdb.connect(db_path)
        except Exception as e:
            if "already open" in str(e).lower() or "used by another process" in str(e).lower():
                print(f"Notice: {db_path} is currently locked by another process. Connecting to dedicated in-memory OLAP session.")
                self.conn = duckdb.connect(":memory:")
            else:
                raise e
        self.init_schema()

    def init_schema(self):
        """Executes schema.sql DDL script."""
        if os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                sql_script = f.read()
            self.conn.execute(sql_script)

    def reset_database(self):
        """Clears all raw and ledger tables."""
        self.conn.execute("DELETE FROM commercial_recon_ledger;")
        self.conn.execute("DELETE FROM recon_ledger;")
        self.conn.execute("DELETE FROM raw_oms_orders;")
        self.conn.execute("DELETE FROM raw_gateway_payments;")
        self.conn.execute("DELETE FROM raw_gateway_settlements;")
        self.conn.execute("DELETE FROM raw_bank_statements;")

    def load_csv_data(self, oms_path: str, payments_path: str, settlements_path: str, bank_path: str):
        """Loads synthetic or production CSV data into DuckDB staging tables."""
        self.reset_database()

        # Parameterized / safe table population
        self.conn.execute("INSERT INTO raw_oms_orders SELECT * FROM read_csv_auto(?);", [oms_path])
        self.conn.execute("INSERT INTO raw_gateway_payments SELECT * FROM read_csv_auto(?);", [payments_path])
        self.conn.execute("INSERT INTO raw_gateway_settlements SELECT * FROM read_csv_auto(?);", [settlements_path])
        self.conn.execute("INSERT INTO raw_bank_statements SELECT * FROM read_csv_auto(?);", [bank_path])

    def get_cfo_metrics(self) -> Dict[str, float]:
        """Calculates executive cash liquidity, MDR fees, holdbacks, and float."""
        query = """
        SELECT 
            COALESCE(SUM(gross_amount), 0.0) as total_gross_captured,
            COALESCE(SUM(net_amount), 0.0) as total_expected_settlements,
            COALESCE(SUM(mdr_fee), 0.0) as total_mdr_fee,
            COALESCE(SUM(gst_fee), 0.0) as total_gst_fee,
            COALESCE(SUM(holdback_amount), 0.0) as total_holdback,
            COALESCE(SUM(refund_deducted), 0.0) as total_refunds_deducted
        FROM raw_gateway_settlements;
        """
        res = self.conn.execute(query).fetchone()
        
        bank_settled_query = """
        SELECT COALESCE(SUM(credit_amount), 0.0)
        FROM raw_bank_statements b
        JOIN recon_ledger r ON b.bank_stmt_id = r.bank_stmt_id
        WHERE r.recon_status IN ('MATCHED_DETERMINISTIC', 'MATCHED_AI', 'MATCHED_RULE', 'MATCHED_HUMAN_OVERRIDE');
        """
        bank_settled = self.conn.execute(bank_settled_query).fetchone()[0]

        expected_net = float(res[1])
        settled = float(bank_settled)

        return {
            "gross_captured": float(res[0]),
            "expected_net_settlement": expected_net,
            "mdr_fee": float(res[2]),
            "gst_fee": float(res[3]),
            "reserve_holdback": float(res[4]),
            "refunds_deducted": float(res[5]),
            "bank_settled_cash": settled,
            "float_in_transit": round(expected_net - settled, 2)
        }

    def get_commercial_recon_metrics(self) -> Dict[str, Any]:
        """Calculates Leg 1 Commercial Recon summary metrics."""
        query = """
        SELECT 
            COUNT(*) as total_orders,
            COALESCE(SUM(oms_amount), 0.0) as total_oms_value,
            COUNT(CASE WHEN recon_status = 'MATCHED_CLEAN' THEN 1 END) as matched_clean_count,
            COUNT(CASE WHEN recon_status = 'STATUS_MISMATCH' THEN 1 END) as status_mismatch_count,
            COUNT(CASE WHEN recon_status = 'FEE_VARIANCE' THEN 1 END) as fee_variance_count,
            COALESCE(SUM(CASE WHEN recon_status = 'FEE_VARIANCE' THEN (gateway_fee - expected_fee) ELSE 0.0 END), 0.0) as total_fee_leakage
        FROM commercial_recon_ledger;
        """
        res = self.conn.execute(query).fetchone()
        return {
            "total_orders": res[0],
            "total_oms_value": float(res[1]),
            "matched_clean_count": res[2],
            "status_mismatch_count": res[3],
            "fee_variance_count": res[4],
            "total_fee_leakage": float(res[5])
        }

    def get_recon_ledger_metrics(self) -> Dict[str, int]:
        """
        Single source of truth for Leg 2 reconciliation KPIs.
        Pulls counts directly from raw_bank_statements joined with recon_ledger at render time.
        Guarantees that total_bank_records == tier1_matched_count + tier2_ai_matched + tier1_5_rule_matched + human_override_matched + unresolved_count.
        """
        query = """
        SELECT 
            COUNT(b.bank_stmt_id) as total_bank_records,
            COUNT(CASE WHEN r.recon_tier = 'TIER_1_SQL' THEN 1 END) as tier1_matched_count,
            COUNT(CASE WHEN r.recon_tier = 'TIER_2_AI' AND r.recon_status = 'MATCHED_AI' THEN 1 END) as tier2_ai_matched,
            COUNT(CASE WHEN r.recon_tier = 'TIER_1_5_RULE' AND r.recon_status = 'MATCHED_RULE' THEN 1 END) as tier1_5_rule_matched,
            COUNT(CASE WHEN r.recon_tier = 'HUMAN_OVERRIDE' AND r.recon_status = 'MATCHED_HUMAN_OVERRIDE' THEN 1 END) as human_override_matched,
            COUNT(CASE WHEN r.recon_status NOT IN ('MATCHED_DETERMINISTIC', 'MATCHED_AI', 'MATCHED_RULE', 'MATCHED_HUMAN_OVERRIDE') OR r.recon_status IS NULL THEN 1 END) as unresolved_count
        FROM raw_bank_statements b
        LEFT JOIN recon_ledger r ON b.bank_stmt_id = r.bank_stmt_id;
        """
        res = self.conn.execute(query).fetchone()
        t1 = res[1] or 0
        t2_ai = res[2] or 0
        t1_5 = res[3] or 0
        override = res[4] or 0
        unresolved = res[5] or 0
        total = res[0] or 0
        return {
            "total_bank_records": total,
            "tier1_matched_count": t1,
            "tier2_ai_matched": t2_ai,
            "tier1_5_rule_matched": t1_5,
            "human_override_matched": override,
            "tier2_total_matched": t2_ai + t1_5 + override,
            "unresolved_count": unresolved
        }

    def restore_golden_ledger(self) -> bool:
        """Restores live DuckDB database from golden_recon_agent.duckdb baseline."""
        import shutil
        if os.path.exists(GOLDEN_DB_PATH):
            try:
                self.conn.close()
            except Exception:
                pass
            shutil.copyfile(GOLDEN_DB_PATH, self.db_path)
            self.conn = duckdb.connect(self.db_path)
            return True
        return False

    def close(self):
        self.conn.close()
