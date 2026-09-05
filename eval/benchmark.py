"""
Ground-Truth Evaluation & Confusion Matrix Benchmark.
Evaluates:
  1. Leg 1 Commercial Recon Accuracy (OMS vs Gateway Payments & Dynamic MDR validation).
  2. Leg 2 Cash Settlement Recon Accuracy (Tier 1 SQL + Tier 2 Gemini AI / Tier 1.5 Rule Fallback).
  3. Live API Telemetry & Cost / Token Benchmark.
"""

import os
import sys
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data.generator import generate_synthetic_dataset
from engine.controller import ReconController

DATA_DIR = os.path.join(PROJECT_ROOT, "data")

def run_benchmark():
    oms_path = os.path.join(DATA_DIR, "oms_orders.csv")
    payments_path = os.path.join(DATA_DIR, "gateway_payments.csv")
    settlements_path = os.path.join(DATA_DIR, "gateway_settlements.csv")
    bank_path = os.path.join(DATA_DIR, "bank_statements.csv")
    gt_path = os.path.join(DATA_DIR, "ground_truth.json")

    if not (os.path.exists(oms_path) and os.path.exists(gt_path)):
        generate_synthetic_dataset()

    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    gt_leg2 = ground_truth.get("leg2", {})
    gt_leg1 = ground_truth.get("leg1", {})

    # Run Controller Pipeline
    controller = ReconController()
    results = controller.run_full_pipeline(oms_path, payments_path, settlements_path, bank_path)

    # -------------------------------------------------------------
    # 1. EVALUATE LEG 1: COMMERCIAL RECON (OMS <-> Gateway Payments)
    # -------------------------------------------------------------
    leg1_df = controller.db.conn.execute("SELECT * FROM commercial_recon_ledger;").df()
    leg1_dict = leg1_df.set_index("order_id").to_dict(orient="index")

    leg1_total = len(gt_leg1)
    leg1_correct = 0
    for order_id, gt in gt_leg1.items():
        actual = leg1_dict.get(order_id, {})
        if actual.get("recon_status") == gt["expected_label"]:
            leg1_correct += 1

    leg1_acc = (leg1_correct / leg1_total) * 100 if leg1_total else 0.0

    # -------------------------------------------------------------
    # 2. EVALUATE LEG 2: CASH SETTLEMENT RECON
    # -------------------------------------------------------------
    leg2_df = controller.db.conn.execute("SELECT * FROM recon_ledger;").df()
    ledger_dict = leg2_df.set_index("bank_stmt_id").to_dict(orient="index")

    total_records = len(gt_leg2)
    tp, fp, tn, fn = 0, 0, 0, 0
    tier1_correct = 0
    tier2_correct = 0
    traps_handled_correctly = 0

    for bank_id, gt in gt_leg2.items():
        actual_rec = ledger_dict.get(bank_id, {})
        actual_status = actual_rec.get("recon_status")

        if gt["archetype"] == "Type_1":
            if actual_status == "MATCHED_DETERMINISTIC":
                tier1_correct += 1
                tp += 1
            else:
                fn += 1

        elif gt["archetype"] in ["Type_2", "Type_3"]:
            if actual_status in ["MATCHED_AI", "MATCHED_RULE", "MATCHED_DETERMINISTIC"]:
                tier2_correct += 1
                tp += 1
            else:
                fn += 1

        elif gt["archetype"] == "Type_4":  # Adversarial Traps
            if actual_status == "EXCEPTION_HUMAN":
                traps_handled_correctly += 1
                tn += 1
            else:
                fp += 1  # False positive / hallucination!

    type1_count = sum(1 for gt in gt_leg2.values() if gt["archetype"] == "Type_1")
    type23_count = sum(1 for gt in gt_leg2.values() if gt["archetype"] in ["Type_2", "Type_3"])
    type4_count = sum(1 for gt in gt_leg2.values() if gt["archetype"] == "Type_4")

    tier1_rate = (tier1_correct / type1_count) * 100 if type1_count else 0
    tier2_precision = (tier2_correct / type23_count) * 100 if type23_count else 0
    hallucination_rate = (fp / type4_count) * 100 if type4_count else 0
    overall_accuracy = ((tp + tn) / total_records) * 100 if total_records else 0

    mode_label = "[LIVE GEMINI 2.5 FLASH]" if results["is_live_ai_active"] else "[TIER 1.5 RULE ENGINE (OFFLINE)]"

    print("\n" + "=" * 65)
    print("      RAZORPAY RECONAGENT: BENCHMARK & EVALUATION REPORT")
    print("=" * 65)
    print(f"Tier 2 Execution Engine      : {mode_label}")
    print(f"Total Tokens Consumed        : {results['total_tokens_spent']}")
    print(f"Total LLM API Calls          : {results['total_api_calls']}")
    print("-" * 65)
    print(f"LEG 1: Commercial Recon Acc  : {leg1_correct}/{leg1_total} ({leg1_acc:.2f}%)")
    print(f"  Clean Orders Matched       : {results['leg1_stats']['matched_clean_count']}")
    print(f"  Status Mismatches Detected : {results['leg1_stats']['status_mismatch_count']}")
    print(f"  Fee Variances Detected     : {results['leg1_stats']['fee_variance_count']}")
    print(f"  Total Fee Leakage Flagged  : Rs.{results['leg1_stats']['total_fee_leakage']:,.2f}")
    print("-" * 65)
    print(f"LEG 2: Bank Records Evaluated: {total_records}")
    print(f"  Tier 1 Deterministic Match : {tier1_correct}/{type1_count} ({tier1_rate:.1f}%) [Rs.0 Tokens]")
    if results["is_live_ai_active"]:
        print(f"  Tier 2 Gemini AI Match     : {tier2_correct}/{type23_count} ({tier2_precision:.1f}%) [Live GenAI]")
    else:
        print(f"  Tier 1.5 Rule Fallback     : {tier2_correct}/{type23_count} ({tier2_precision:.1f}%) [Deterministic]")
    print(f"  Adversarial Traps Handled  : {traps_handled_correctly}/{type4_count} ({100-hallucination_rate:.1f}%)")
    print(f"  Hallucination / False Pos  : {fp} ({hallucination_rate:.2f}%)")
    print(f"  Overall Cash Recon Acc     : {overall_accuracy:.2f}%")
    print("-" * 65)
    print("CONFUSION MATRIX:")
    print(f"  True Positives (Matched Correctly) : {tp}")
    print(f"  True Negatives (Traps Unresolved)  : {tn}")
    print(f"  False Positives (Hallucinations)   : {fp}")
    print(f"  False Negatives (Missed Matches)   : {fn}")
    print("=" * 65 + "\n")

    controller.db.close()

if __name__ == "__main__":
    run_benchmark()
