"""
DuckDB Client and Persistence Layer for ReconAgent.
Manages embedded OLAP session, CSV staging, and query execution.
"""

import os
import duckdb

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recon_agent.duckdb")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

class DuckDBClient:
    def __init__(self, db_path: str = ":memory:"):
        self.conn = duckdb.connect(db_path)
        self.init_schema()

    def init_schema(self):
        """Executes schema.sql DDL script."""
        if os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH, "r") as f:
                sql_script = f.read()
            self.conn.execute(sql_script)

    def load_csv_data(self, oms_path: str, gateway_path: str, bank_path: str):
        """Loads synthetic or production CSV data into DuckDB stage tables."""
        self.conn.execute("DELETE FROM raw_oms_orders;")
        self.conn.execute("DELETE FROM raw_gateway_settlements;")
        self.conn.execute("DELETE FROM raw_bank_statements;")
        self.conn.execute("DELETE FROM recon_ledger;")

        self.conn.execute(f"INSERT INTO raw_oms_orders SELECT * FROM read_csv_auto('{oms_path}');")
        self.conn.execute(f"INSERT INTO raw_gateway_settlements SELECT * FROM read_csv_auto('{gateway_path}');")
        self.conn.execute(f"INSERT INTO raw_bank_statements SELECT * FROM read_csv_auto('{bank_path}');")

    def get_cfo_metrics(self):
        """Calculates executive cash liquidity and MDR fee metrics."""
        query = """
        SELECT 
            COALESCE(SUM(gross_amount), 0.0) as total_gross_captured,
            COALESCE(SUM(net_amount), 0.0) as total_expected_settlements,
            COALESCE(SUM(mdr_fee), 0.0) as total_mdr_fee,
            COALESCE(SUM(gst_fee), 0.0) as total_gst_fee,
            COALESCE(SUM(refund_deducted), 0.0) as total_refunds_deducted
        FROM raw_gateway_settlements;
        """
        res = self.conn.execute(query).fetchone()
        
        bank_settled_query = """
        SELECT COALESCE(SUM(credit_amount), 0.0)
        FROM raw_bank_statements b
        JOIN recon_ledger r ON b.bank_stmt_id = r.bank_stmt_id
        WHERE r.recon_status IN ('MATCHED_DETERMINISTIC', 'MATCHED_AI');
        """
        bank_settled = self.conn.execute(bank_settled_query).fetchone()[0]

        return {
            "gross_captured": float(res[0]),
            "expected_net_settlement": float(res[1]),
            "mdr_fee": float(res[2]),
            "gst_fee": float(res[3]),
            "refunds_deducted": float(res[4]),
            "bank_settled_cash": float(bank_settled),
            "float_in_transit": float(res[1]) - float(bank_settled)
        }

    def close(self):
        self.conn.close()
