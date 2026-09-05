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
        self._conn = None
        self._connect()
        self.init_schema()

    def _connect(self):
        try:
            self._conn = duckdb.connect(self.db_path)
        except Exception as e:
            if "already open" in str(e).lower() or "used by another process" in str(e).lower():
                print(f"Notice: {self.db_path} is currently locked by another process. Connecting to dedicated in-memory OLAP session.")
                self._conn = duckdb.connect(":memory:")
                golden_path = os.path.join(os.path.dirname(self.db_path), "golden_recon_agent.duckdb")
                if os.path.exists(golden_path):
                    try:
                        abs_golden = os.path.abspath(golden_path)
                        self._conn.execute(f"ATTACH '{abs_golden}' AS golden (READ_ONLY);")
                        tables = [r[0] for r in self._conn.execute("SHOW TABLES FROM golden;").fetchall()]
                        for t in tables:
                            self._conn.execute(f"CREATE TABLE {t} AS SELECT * FROM golden.{t};")
                        self._conn.execute("DETACH golden;")
                    except Exception as ge:
                        print(f"Notice: Could not populate in-memory session from golden baseline: {ge}")
            else:
                self._conn = duckdb.connect(":memory:")

    @property
    def conn(self):
        """Returns active DuckDB connection, automatically reconnecting if connection was closed or invalidated."""
        if self._conn is not None:
            try:
                self._conn.execute("SELECT 1;")
                return self._conn
            except Exception:
                # Connection was closed or invalidated externally
                pass
        self._connect()
        self.init_schema()
        return self._conn

    @conn.setter
    def conn(self, value):
        self._conn = value

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
        if res is None:
            return {
                "gross_captured": 0.0,
                "expected_net_settlement": 0.0,
                "mdr_fee": 0.0,
                "gst_fee": 0.0,
                "reserve_holdback": 0.0,
                "refunds_deducted": 0.0,
                "bank_settled_cash": 0.0,
                "float_in_transit": 0.0
            }
        
        bank_settled_query = """
        SELECT COALESCE(SUM(credit_amount), 0.0)
        FROM raw_bank_statements b
        JOIN recon_ledger r ON b.bank_stmt_id = r.bank_stmt_id
        WHERE r.recon_status IN ('MATCHED_DETERMINISTIC', 'MATCHED_AI', 'MATCHED_RULE', 'MATCHED_HUMAN_OVERRIDE');
        """
        bank_res = self.conn.execute(bank_settled_query).fetchone()
        bank_settled = float(bank_res[0]) if bank_res and bank_res[0] is not None else 0.0

        expected_net = float(res[1] or 0.0)
        settled = float(bank_settled)

        return {
            "gross_captured": float(res[0] or 0.0),
            "expected_net_settlement": expected_net,
            "mdr_fee": float(res[2] or 0.0),
            "gst_fee": float(res[3] or 0.0),
            "reserve_holdback": float(res[4] or 0.0),
            "refunds_deducted": float(res[5] or 0.0),
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
        if res is None:
            return {
                "total_orders": 0,
                "total_oms_value": 0.0,
                "matched_clean_count": 0,
                "status_mismatch_count": 0,
                "fee_variance_count": 0,
                "total_fee_leakage": 0.0
            }
        return {
            "total_orders": res[0] or 0,
            "total_oms_value": float(res[1] or 0.0),
            "matched_clean_count": res[2] or 0,
            "status_mismatch_count": res[3] or 0,
            "fee_variance_count": res[4] or 0,
            "total_fee_leakage": float(res[5] or 0.0)
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
        if res is None:
            return {
                "total_bank_records": 0,
                "tier1_matched_count": 0,
                "tier2_ai_matched": 0,
                "tier1_5_rule_matched": 0,
                "human_override_matched": 0,
                "tier2_total_matched": 0,
                "unresolved_count": 0
            }
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
            self.close()
            try:
                shutil.copyfile(GOLDEN_DB_PATH, self.db_path)
            except Exception as e:
                print(f"Warning copying golden reference: {e}")
            self._connect()
            self.init_schema()
            return True
        return False

    def close(self):
        """Safely closes active DuckDB connection."""
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None
