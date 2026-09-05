"""
Synthetic Data & Ground Truth Generator for Razorpay ReconAgent.
Generates multi-source financial feeds:
  1. raw_oms_orders (with payment_method, risk_tier, status)
  2. raw_gateway_payments (1:1 with OMS orders, includes MDR/GST/Holdback)
  3. raw_gateway_settlements (batches aggregating constituent order payments)
  4. raw_bank_statements (150 bank records across 4 archetypes)
  5. ground_truth.json (ground truth for Leg 1 Commercial & Leg 2 Cash Recon)
"""

import os
import json
import random
from datetime import datetime, timedelta
import pandas as pd

random.seed(42)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

def calculate_order_fees(amount: float, method: str, risk_tier: str):
    """Calculates MDR, GST, and Holdback based on payment method and risk tier."""
    if method == "UPI":
        mdr_rate = 0.00
    elif method == "DEBIT_CARD":
        mdr_rate = 0.009
    elif method == "CREDIT_CARD":
        mdr_rate = 0.020
    elif method == "NETBANKING":
        mdr_rate = 0.018
    else:
        mdr_rate = 0.020

    mdr_fee = round(amount * mdr_rate, 2)
    gst_fee = round(mdr_fee * 0.18, 2)
    holdback = round(amount * 0.10, 2) if risk_tier == "HIGH_RISK" else 0.00
    net = round(amount - mdr_fee - gst_fee - holdback, 2)
    return mdr_fee, gst_fee, holdback, net

def generate_synthetic_dataset():
    base_date = datetime(2026, 8, 1, 10, 0, 0)
    
    oms_records = []
    gateway_payments = []
    gateway_settlements = []
    bank_records = []
    ground_truth = {"leg2": {}, "leg1": {}}

    order_counter = 1000
    payment_counter = 2000
    settlement_counter = 5000
    utr_counter = 900000

    # 150 settlement batches across 4 archetypes
    # Type 1 Clean: 105
    # Type 2 Cryptic: 23
    # Type 3 Netting Variance: 15
    # Type 4 Adversarial Traps: 7
    archetypes = (
        [1] * 105 +
        [2] * 23 +
        [3] * 15 +
        [4] * 7
    )
    random.shuffle(archetypes)

    payment_methods = ["UPI", "DEBIT_CARD", "CREDIT_CARD", "NETBANKING"]
    method_weights = [0.45, 0.20, 0.25, 0.10]

    for i, arch in enumerate(archetypes):
        settlement_id = f"setl_{settlement_counter + i}"
        utr_raw = f"UTR{utr_counter + i}"
        
        days_offset = random.randint(0, 19)
        capture_date = base_date + timedelta(days=days_offset)
        clearing_delay = random.choice([1, 2])
        bank_credit_date = (capture_date + timedelta(days=clearing_delay)).strftime("%Y-%m-%d")

        # Settlement batch contains 1 to 4 constituent orders
        num_orders = random.randint(1, 4)
        batch_order_ids = []
        batch_gross = 0.0
        batch_mdr = 0.0
        batch_gst = 0.0
        batch_holdback = 0.0
        batch_net = 0.0

        for j in range(num_orders):
            order_id = f"ord_{order_counter}"
            payment_id = f"pay_{payment_counter}"
            order_counter += 1
            payment_counter += 1
            batch_order_ids.append(order_id)

            item_amount = round(random.uniform(500.0, 15000.0), 2)
            method = random.choices(payment_methods, weights=method_weights)[0]
            risk_tier = "HIGH_RISK" if random.random() < 0.10 else "STANDARD"

            # Compute standard contractual fees
            mdr_fee, gst_fee, holdback, net_item = calculate_order_fees(item_amount, method, risk_tier)

            # Leg 1 Discrepancy Injection (small deliberate edge cases for real commercial testing)
            leg1_label = "MATCHED_CLEAN"
            oms_status = "COMPLETED"
            gw_status = "CAPTURED"
            gw_amount = item_amount
            gw_fee = mdr_fee

            dice = random.random()
            if dice < 0.03:
                # Discrepancy: Gateway failed / charged back but OMS marked completed
                gw_status = "FAILED"
                leg1_label = "STATUS_MISMATCH"
            elif dice < 0.06:
                # Discrepancy: Gateway overbilled fee by ₹50-₹150
                gw_fee = round(mdr_fee + random.uniform(50.0, 150.0), 2)
                leg1_label = "FEE_VARIANCE"

            oms_records.append({
                "order_id": order_id,
                "amount": item_amount,
                "currency": "INR",
                "payment_method": method,
                "risk_tier": risk_tier,
                "status": oms_status,
                "created_at": capture_date.strftime("%Y-%m-%d %H:%M:%S")
            })

            gateway_payments.append({
                "payment_id": payment_id,
                "order_id": order_id,
                "settlement_id": settlement_id,
                "amount": gw_amount,
                "payment_method": method,
                "fee": gw_fee,
                "tax": gst_fee,
                "holdback": holdback,
                "net_amount": round(gw_amount - gw_fee - gst_fee - holdback, 2),
                "status": gw_status,
                "captured_at": capture_date.strftime("%Y-%m-%d %H:%M:%S")
            })

            ground_truth["leg1"][order_id] = {
                "expected_label": leg1_label,
                "oms_amount": item_amount,
                "expected_mdr": mdr_fee,
                "gateway_fee": gw_fee
            }

            batch_gross += gw_amount
            batch_mdr += gw_fee
            batch_gst += gst_fee
            batch_holdback += holdback
            batch_net += round(gw_amount - gw_fee - gst_fee - holdback, 2)

        batch_gross = round(batch_gross, 2)
        batch_mdr = round(batch_mdr, 2)
        batch_gst = round(batch_gst, 2)
        batch_holdback = round(batch_holdback, 2)
        batch_net = round(batch_net, 2)

        refund_amount = 0.0
        refund_id = None

        if arch == 1:
            # Type 1: Clean Flow
            bank_credit_amount = batch_net
            narration = f"CMS/RZP/{utr_raw}/NET_SETTL"
            ground_label = "MATCHED_DETERMINISTIC"
            expected_engine = "TIER_1_SQL"

        elif arch == 2:
            # Type 2: Cryptic Narration (Truncated UTR / Bank Noise)
            bank_credit_amount = batch_net
            noise_prefix = random.choice([
                "HDFC CMP RZP BATCH ",
                "NEFT-CMS-RAZORPAY-",
                "SETTL-REF-NO-",
                "CMS/PAY/RZP/"
            ])
            short_utr = utr_raw[-6:]
            narration = f"{noise_prefix}{short_utr} NET"
            ground_label = "MATCHED_AI"
            expected_engine = "TIER_2_AI"

        elif arch == 3:
            # Type 3: Netting Variance (Past Refund / Chargeback Deducted)
            refund_amount = round(random.uniform(200.0, 1500.0), 2)
            refund_id = f"rfnd_{random.randint(10000, 99999)}"
            bank_credit_amount = round(batch_net - refund_amount, 2)
            narration = f"CMS/RZP/{utr_raw}/NET_LESS_RFND"
            ground_label = "MATCHED_AI"
            expected_engine = "TIER_2_AI"

        elif arch == 4:
            # Type 4: Adversarial Traps
            trap_sub_type = random.choice(["phantom", "duplicate_ambiguous", "unnotified_fee"])
            if trap_sub_type == "phantom":
                bank_credit_amount = round(batch_net + round(random.uniform(500, 2000), 2), 2)
                narration = f"UNKNOWN NEFT CREDIT NO_UTR_{random.randint(100,999)}"
            elif trap_sub_type == "duplicate_ambiguous":
                bank_credit_amount = 5000.00
                narration = "BULK SETTLEMENT CLEARING"
            else: # unnotified_fee
                bank_credit_amount = round(batch_net - 850.50, 2)
                narration = f"CMS/RZP/{utr_raw}/ADJ_UNKN"

            ground_label = "EXCEPTION_HUMAN"
            expected_engine = "TIER_2_UNRESOLVED"

        gateway_settlements.append({
            "settlement_id": settlement_id,
            "order_ids": ",".join(batch_order_ids),
            "utr": utr_raw,
            "gross_amount": batch_gross,
            "mdr_fee": batch_mdr,
            "gst_fee": batch_gst,
            "holdback_amount": batch_holdback,
            "net_amount": batch_net,
            "refund_deducted": refund_amount,
            "refund_id": refund_id or "",
            "captured_at": capture_date.strftime("%Y-%m-%d"),
            "expected_credit_date": bank_credit_date
        })

        bank_stmt_id = f"stmt_{i+101}"
        bank_records.append({
            "bank_stmt_id": bank_stmt_id,
            "credit_date": bank_credit_date,
            "credit_amount": bank_credit_amount,
            "raw_narration": narration
        })

        ground_truth["leg2"][bank_stmt_id] = {
            "settlement_id": settlement_id,
            "utr": utr_raw,
            "archetype": f"Type_{arch}",
            "ground_label": ground_label,
            "expected_engine": expected_engine,
            "expected_variance": refund_amount if arch == 3 else 0.0
        }

    # Save to CSV and JSON
    pd.DataFrame(oms_records).to_csv(os.path.join(DATA_DIR, "oms_orders.csv"), index=False)
    pd.DataFrame(gateway_payments).to_csv(os.path.join(DATA_DIR, "gateway_payments.csv"), index=False)
    pd.DataFrame(gateway_settlements).to_csv(os.path.join(DATA_DIR, "gateway_settlements.csv"), index=False)
    pd.DataFrame(bank_records).to_csv(os.path.join(DATA_DIR, "bank_statements.csv"), index=False)

    with open(os.path.join(DATA_DIR, "ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"Generated {len(oms_records)} OMS orders, {len(gateway_payments)} Gateway payments, "
          f"{len(gateway_settlements)} Settlements, {len(bank_records)} Bank statements.")
    print(f"Ground truth saved to {os.path.join(DATA_DIR, 'ground_truth.json')}")

if __name__ == "__main__":
    generate_synthetic_dataset()
