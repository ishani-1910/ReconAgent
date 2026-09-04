"""
Ground-Truth Evaluation & Confusion Matrix Benchmark.
Verifies recon accuracy, deterministic match rate, AI precision, and 0% hallucination rate.
"""

import os
import sys
import json
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data.generator import generate_synthetic_dataset
from engine.controller import ReconController

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

def run_benchmark():
    # 1. Ensure synthetic data is generated
    oms_path = os.path.join(DATA_DIR, "oms_orders.csv")
    gateway_path = os.path.join(DATA_DIR, "gateway_settlements.csv")
    bank_path = os.path.join(DATA_DIR, "bank_statements.csv")
    gt_path = os.path.join(DATA_DIR, "ground_truth.json")

    if not os.path.exists(oms_path) or not os.path.exists(gt_path):
        generate_synthetic_dataset()

    with open(gt_path, "r") as f:
        ground_truth = json.load(f)

    # 2. Run Recon Controller Pipeline
    controller = ReconController()
    results = controller.run_full_pipeline(oms_path, gateway_path, bank_path)

    # 3. Load Recon Ledger for Comparison
    ledger_df = controller.db.conn.execute("SELECT * FROM recon_ledger;").df()
    ledger_dict = ledger_df.set_index("bank_stmt_id").to_dict(orient="index")

    # 4. Compute Metrics
    total_records = len(ground_truth)
    tp, fp, tn, fn = 0, 0, 0, 0
    tier1_correct = 0
    tier2_correct = 0
    traps_handled_correctly = 0

    for bank_id, gt in ground_truth.items():
        actual_rec = ledger_dict.get(bank_id, {})
        actual_status = actual_rec.get("recon_status")
        expected_status = gt["ground_label"]

        if gt["archetype"] == "Type_1":
            if actual_status == "MATCHED_DETERMINISTIC":
                tier1_correct += 1
                tp += 1
            else:
                fn += 1

        elif gt["archetype"] in ["Type_2", "Type_3"]:
            if actual_status in ["MATCHED_AI", "MATCHED_DETERMINISTIC"]:
                tier2_correct += 1
                tp += 1
            else:
                fn += 1

        elif gt["archetype"] == "Type_4": # Adversarial Traps
            if actual_status == "EXCEPTION_HUMAN":
                traps_handled_correctly += 1
                tn += 1
            else:
                fp += 1 # False positive / hallucinated match!

    type1_count = sum(1 for gt in ground_truth.values() if gt["archetype"] == "Type_1")
    type23_count = sum(1 for gt in ground_truth.values() if gt["archetype"] in ["Type_2", "Type_3"])
    type4_count = sum(1 for gt in ground_truth.values() if gt["archetype"] == "Type_4")

    tier1_rate = (tier1_correct / type1_count) * 100 if type1_count else 0
    tier2_precision = (tier2_correct / type23_count) * 100 if type23_count else 0
    hallucination_rate = (fp / type4_count) * 100 if type4_count else 0
    overall_accuracy = ((tp + tn) / total_records) * 100

    print("=" * 60)
    print("      RAZORPAY RECONAGENT: BENCHMARK & EVALUATION REPORT")
    print("=" * 60)
    print(f"Total Bank Records Evaluated : {total_records}")
    print(f"Tier 1 Deterministic Match   : {tier1_correct}/{type1_count} ({tier1_rate:.1f}%)")
    print(f"Tier 2 AI Escalation Match   : {tier2_correct}/{type23_count} ({tier2_precision:.1f}%)")
    print(f"Adversarial Traps Handled   : {traps_handled_correctly}/{type4_count} ({100-hallucination_rate:.1f}%)")
    print(f"Hallucination / False Pos   : {fp} ({hallucination_rate:.2f}%)")
    print(f"Overall Ground-Truth Acc     : {overall_accuracy:.2f}%")
    print("-" * 60)
    print("CONFUSION MATRIX:")
    print(f"  True Positives (Matched Correctly)  : {tp}")
    print(f"  True Negatives (Traps Unresolved)   : {tn}")
    print(f"  False Positives (Hallucinations)    : {fp}")
    print(f"  False Negatives (Missed Matches)    : {fn}")
    print("=" * 60)

    controller.db.close()
    return {
        "tier1_rate": tier1_rate,
        "tier2_precision": tier2_precision,
        "hallucination_rate": hallucination_rate,
        "overall_accuracy": overall_accuracy
    }

if __name__ == "__main__":
    run_benchmark()
