"""
Synthetic Data & Ground Truth Generator for Razorpay ReconAgent.
Generates 150 synthetic financial records across 4 explicit archetypes:
  1. Type 1: Clean Flow (70% - 105 txns) -> MATCHED_DETERMINISTIC (Tier 1 SQL)
  2. Type 2: Cryptic Narration (15% - 23 txns) -> MATCHED_AI (Tier 2 AI)
  3. Type 3: Netting Variance (10% - 15 txns) -> MATCHED_AI (Tier 2 AI)
  4. Type 4: Adversarial Traps (5% - 7 txns) -> EXCEPTION_HUMAN (Tier 2 Unresolved)
Outputs:
  - data/oms_orders.csv
  - data/gateway_settlements.csv
  - data/bank_statements.csv
  - data/ground_truth.json
"""

import os
import json
import random
from datetime import datetime, timedelta
import pandas as pd

# Set fixed seed for deterministic reproducibility
random.seed(42)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

def generate_synthetic_dataset():
    base_date = datetime(2026, 8, 1, 10, 0, 0)
    
    oms_records = []
    gateway_records = []
    bank_records = []
    ground_truth = {}

    order_counter = 1000
    settlement_counter = 5000
    utr_counter = 900000

    # Total 150 settlements
    # Type 1: 105
    # Type 2: 23
    # Type 3: 15
    # Type 4: 7
    
    archetypes = (
        [1] * 105 +
        [2] * 23 +
        [3] * 15 +
        [4] * 7
    )
    random.shuffle(archetypes)

    for i, arch in enumerate(archetypes):
        settlement_id = f"setl_{settlement_counter + i}"
        utr_raw = f"UTR{utr_counter + i}"
        
        # Capture date between Aug 1 and Aug 20
        days_offset = random.randint(0, 19)
        capture_date = base_date + timedelta(days=days_offset)
        
        # Calculate expected bank credit date (T+1 to T+2 clearing window)
        clearing_delay = random.choice([1, 2])
        bank_credit_date = (capture_date + timedelta(days=clearing_delay)).strftime("%Y-%m-%d")
        
        # Number of orders in this settlement batch (1 to 5)
        num_orders = random.randint(1, 4)
        gross_amount = 0.0
        
        for j in range(num_orders):
            order_id = f"ord_{order_counter}"
            order_counter += 1
            item_gross = round(random.uniform(500.0, 15000.0), 2)
            gross_amount += item_gross
            
            oms_records.append({
                "order_id": order_id,
                "amount": item_gross,
                "currency": "INR",
                "status": "COMPLETED",
                "created_at": capture_date.strftime("%Y-%m-%d %H:%M:%S")
            })

        gross_amount = round(gross_amount, 2)
        mdr_fee = round(gross_amount * 0.02, 2)          # 2% MDR
        gst_fee = round(mdr_fee * 0.18, 2)              # 18% GST on MDR
        total_fee = round(mdr_fee + gst_fee, 2)
        
        # Default net amount
        net_amount = round(gross_amount - total_fee, 2)
        refund_amount = 0.0
        refund_id = None
        
        if arch == 1:
            # Type 1: Clean Flow
            bank_credit_amount = net_amount
            narration = f"CMS/RZP/{utr_raw}/NET_SETTL"
            ground_label = "MATCHED_DETERMINISTIC"
            expected_engine = "TIER_1_SQL"
            
        elif arch == 2:
            # Type 2: Cryptic Narration (Truncated UTR / Bank Noise)
            bank_credit_amount = net_amount
            # Truncated or nested UTR narration patterns
            noise_prefix = random.choice([
                "HDFC CMP RZP BATCH ",
                "NEFT-CMS-RAZORPAY-",
                "SETTL-REF-NO-",
                "CMS/PAY/RZP/"
            ])
            short_utr = utr_raw[-6:] # Truncated token
            narration = f"{noise_prefix}{short_utr} NET"
            ground_label = "MATCHED_AI"
            expected_engine = "TIER_2_AI"

        elif arch == 3:
            # Type 3: Netting Variance (Past Refund / Chargeback Hold deducted)
            refund_amount = round(random.uniform(200.0, 1500.0), 2)
            refund_id = f"rfnd_{random.randint(10000, 99999)}"
            bank_credit_amount = round(net_amount - refund_amount, 2)
            narration = f"CMS/RZP/{utr_raw}/NET_LESS_RFND"
            ground_label = "MATCHED_AI"
            expected_engine = "TIER_2_AI"

        elif arch == 4:
            # Type 4: Adversarial Traps
            trap_sub_type = random.choice(["phantom", "duplicate_ambiguous", "unnotified_fee"])
            
            if trap_sub_type == "phantom":
                # Bank has credit but gateway has no matching batch amount or UTR is fake
                bank_credit_amount = round(net_amount + round(random.uniform(500, 2000), 2), 2)
                narration = f"UNKNOWN NEFT CREDIT NO_UTR_{random.randint(100,999)}"
            elif trap_sub_type == "duplicate_ambiguous":
                # Amount is round and identical to another batch, narration has no unique token
                bank_credit_amount = 5000.00
                narration = "BULK SETTLEMENT CLEARING"
            else: # unnotified_fee
                bank_credit_amount = round(net_amount - 850.50, 2)
                narration = f"CMS/RZP/{utr_raw}/ADJ_UNKN"

            ground_label = "EXCEPTION_HUMAN"
            expected_engine = "TIER_2_UNRESOLVED"

        # Record Gateway Batch
        gateway_records.append({
            "settlement_id": settlement_id,
            "utr": utr_raw,
            "gross_amount": gross_amount,
            "mdr_fee": mdr_fee,
            "gst_fee": gst_fee,
            "net_amount": net_amount,
            "refund_deducted": refund_amount,
            "refund_id": refund_id or "",
            "captured_at": capture_date.strftime("%Y-%m-%d"),
            "expected_credit_date": bank_credit_date
        })

        # Record Bank Statement line
        bank_stmt_id = f"stmt_{i+101}"
        bank_records.append({
            "bank_stmt_id": bank_stmt_id,
            "credit_date": bank_credit_date,
            "credit_amount": bank_credit_amount,
            "raw_narration": narration
        })

        # Ground Truth Registry
        ground_truth[bank_stmt_id] = {
            "settlement_id": settlement_id,
            "utr": utr_raw,
            "archetype": f"Type_{arch}",
            "ground_label": ground_label,
            "expected_engine": expected_engine,
            "expected_variance": refund_amount if arch == 3 else 0.0
        }

    # Save to CSV and JSON
    df_oms = pd.DataFrame(oms_records)
    df_gateway = pd.DataFrame(gateway_records)
    df_bank = pd.DataFrame(bank_records)

    df_oms.to_csv(os.path.join(DATA_DIR, "oms_orders.csv"), index=False)
    df_gateway.to_csv(os.path.join(DATA_DIR, "gateway_settlements.csv"), index=False)
    df_bank.to_csv(os.path.join(DATA_DIR, "bank_statements.csv"), index=False)

    with open(os.path.join(DATA_DIR, "ground_truth.json"), "w") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"Generated {len(oms_records)} OMS orders, {len(gateway_records)} Gateway settlements, {len(bank_records)} Bank statements.")
    print(f"Ground truth saved to {os.path.join(DATA_DIR, 'ground_truth.json')}")

if __name__ == "__main__":
    generate_synthetic_dataset()
