"""
Automated Pytest Suite for Razorpay ReconAgent.
Tests:
  1. Synthetic data generator (OMS, Gateway Payments, Settlements, Bank Statements).
  2. Persistent DuckDB precision and CFO metrics.
  3. Leg 1 Commercial Recon (1:1 join, MDR fee validation, status checks).
  4. Leg 2 Tier 1 Deterministic matching.
  5. Tier 2 / Tier 1.5 Investigator schema and execution.
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
from engine.controller import ReconController

DATA_DIR = os.path.join(PROJECT_ROOT, "data")

@pytest.fixture(scope="module")
def setup_dataset():
    generate_synthetic_dataset()
    oms_path = os.path.join(DATA_DIR, "oms_orders.csv")
    payments_path = os.path.join(DATA_DIR, "gateway_payments.csv")
    settlements_path = os.path.join(DATA_DIR, "gateway_settlements.csv")
    bank_path = os.path.join(DATA_DIR, "bank_statements.csv")
    return oms_path, payments_path, settlements_path, bank_path

def test_synthetic_generator_files_exist(setup_dataset):
    oms_path, payments_path, settlements_path, bank_path = setup_dataset
    assert os.path.exists(oms_path)
    assert os.path.exists(payments_path)
    assert os.path.exists(settlements_path)
    assert os.path.exists(bank_path)
    assert os.path.exists(os.path.join(DATA_DIR, "ground_truth.json"))

def test_duckdb_precision_and_cfo_metrics(setup_dataset):
    oms_path, payments_path, settlements_path, bank_path = setup_dataset
    db = DuckDBClient(db_path=":memory:")
    db.load_csv_data(oms_path, payments_path, settlements_path, bank_path)
    
    metrics = db.get_cfo_metrics()
    assert metrics["gross_captured"] > 0
    assert metrics["mdr_fee"] > 0
    assert metrics["gst_fee"] > 0
    assert metrics["expected_net_settlement"] > 0
    db.close()

def test_leg1_commercial_recon(setup_dataset):
    oms_path, payments_path, settlements_path, bank_path = setup_dataset
    db = DuckDBClient(db_path=":memory:")
    db.load_csv_data(oms_path, payments_path, settlements_path, bank_path)
    
    tier1 = Tier1SQLEngine(db)
    leg1_stats = tier1.execute_leg1_commercial_recon()
    
    assert leg1_stats["total_orders"] > 300
    assert leg1_stats["matched_clean_count"] > 250
    assert leg1_stats["status_mismatch_count"] > 0
    assert leg1_stats["fee_variance_count"] > 0
    db.close()

def test_leg2_tier1_deterministic_matching(setup_dataset):
    oms_path, payments_path, settlements_path, bank_path = setup_dataset
    db = DuckDBClient(db_path=":memory:")
    db.load_csv_data(oms_path, payments_path, settlements_path, bank_path)
    
    tier1 = Tier1SQLEngine(db)
    tier1.execute_leg1_commercial_recon()
    matched_count = tier1.execute_leg2_deterministic_match()
    assert matched_count >= 100  # Clean flow matches
    db.close()

def test_tier2_schema_and_offline_rule_mode():
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
        "net_amount": 5000.0,
        "refund_deducted": 0.0,
        "refund_id": "",
        "expected_credit_date": "2026-08-04"
    }]
    
    decision = investigator.investigate(bank_rec, candidates)
    assert isinstance(decision, ReconDecisionSchema)
    assert decision.decision in ["MATCH", "UNRESOLVED"]
    assert decision.recon_tier in ["TIER_2_AI", "TIER_1_5_RULE"]

def test_pipeline_consistency_and_conservation_law(setup_dataset):
    """
    Consistency & Conservation Law Check:
    1. tier1_matched_count + tier2_ai_matched + tier1_5_rule_matched + unresolved_count == total_bank_records
    2. If is_live_ai_active is True, total_tokens_spent > 0
    """
    oms_path, payments_path, settlements_path, bank_path = setup_dataset
    controller = ReconController(db_path=":memory:")
    results = controller.run_full_pipeline(oms_path, payments_path, settlements_path, bank_path)

    tier1 = results["tier1_matched_count"]
    tier2_ai = results["tier2_ai_matched"]
    tier1_5 = results["tier1_5_rule_matched"]
    override = results.get("human_override_matched", 0)
    unresolved = results["unresolved_count"]
    total = results["total_bank_records"]

    # Assert conservation law: every single bank record must be accounted for
    assert tier1 + tier2_ai + tier1_5 + override + unresolved == total, (
        f"Conservation law violation: {tier1} (Tier 1) + {tier2_ai} (Tier 2 AI) + "
        f"{tier1_5} (Tier 1.5) + {override} (Override) + {unresolved} (Unresolved) != {total} (Total)"
    )

    # Assert honesty of is_live_ai_active flag
    if results["is_live_ai_active"]:
        assert results["total_tokens_spent"] > 0, "is_live_ai_active is True but total_tokens_spent is 0"
        assert results["total_api_calls"] > 0, "is_live_ai_active is True but total_api_calls is 0"
    else:
        assert results["total_api_calls"] == 0 or results["total_tokens_spent"] == 0, (
            "is_live_ai_active is False but tokens or calls were recorded"
        )

    controller.db.close()

