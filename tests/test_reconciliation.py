"""
Automated Pytest Suite for Razorpay ReconAgent.
Tests synthetic data generation, DuckDB precision, Tier 1 SQL, and Tier 2 AI bounding.
"""

import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data.generator import generate_synthetic_dataset
from db.duckdb_client import DuckDBClient
from engine.tier1_sql import Tier1SQLEngine
from engine.tier2_ai import Tier2AIInvestigator, ReconDecisionSchema

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

@pytest.fixture(scope="module")
def setup_dataset():
    generate_synthetic_dataset()
    oms_path = os.path.join(DATA_DIR, "oms_orders.csv")
    gateway_path = os.path.join(DATA_DIR, "gateway_settlements.csv")
    bank_path = os.path.join(DATA_DIR, "bank_statements.csv")
    return oms_path, gateway_path, bank_path

def test_synthetic_generator_files_exist(setup_dataset):
    oms_path, gateway_path, bank_path = setup_dataset
    assert os.path.exists(oms_path)
    assert os.path.exists(gateway_path)
    assert os.path.exists(bank_path)

def test_duckdb_precision_and_cfo_metrics(setup_dataset):
    oms_path, gateway_path, bank_path = setup_dataset
    db = DuckDBClient()
    db.load_csv_data(oms_path, gateway_path, bank_path)
    
    metrics = db.get_cfo_metrics()
    assert metrics["gross_captured"] > 0
    assert metrics["mdr_fee"] > 0
    assert metrics["gst_fee"] > 0
    assert abs(metrics["mdr_fee"] * 0.18 - metrics["gst_fee"]) < 0.50
    db.close()

def test_tier1_deterministic_matching(setup_dataset):
    oms_path, gateway_path, bank_path = setup_dataset
    db = DuckDBClient()
    db.load_csv_data(oms_path, gateway_path, bank_path)
    
    tier1 = Tier1SQLEngine(db)
    leg1_stats = tier1.execute_leg1_commercial_recon()
    assert leg1_stats["matched_orders"] > 0

    matched_count = tier1.execute_leg2_deterministic_match()
    assert matched_count >= 100 # Type 1 Clean flow should be matched in Tier 1 SQL
    db.close()

def test_tier2_bounded_investigator_schema():
    investigator = Tier2AIInvestigator()
    bank_rec = {
        "bank_stmt_id": "stmt_test",
        "credit_date": "2026-08-05",
        "credit_amount": 5000.0,
        "raw_narration": "CMS/RZP/UTR9999/NET"
    }
    candidates = [{
        "settlement_id": "setl_9999",
        "utr": "UTR9999",
        "gross_amount": 5110.0,
        "mdr_fee": 102.2,
        "gst_fee": 18.4,
        "net_amount": 4989.4,
        "refund_deducted": 0.0,
        "refund_id": "",
        "expected_credit_date": "2026-08-04"
    }]
    
    decision = investigator.investigate(bank_rec, candidates)
    assert isinstance(decision, ReconDecisionSchema)
    assert decision.decision in ["MATCH", "UNRESOLVED"]
    assert 0.0 <= decision.confidence <= 1.0
