# ReconAgent: Comprehensive Technical Architecture & System Documentation

This document provides exhaustive reference documentation for **ReconAgent**, detailing database schemas, mathematical settlement formulas, multi-tier engine orchestration, AI governance guardrails, public deployment safeguards, and automated verification suites.

For a high-level overview and quick-start instructions, refer to [README.md](README.md).

---

## Table of Contents
1. [Core Architecture & 3-Way Reconciliation Model](#1-core-architecture--3-way-reconciliation-model)
2. [Complete Database Schema & OLAP Layer (DuckDB)](#2-complete-database-schema--olap-layer-duckdb)
3. [Mathematical Settlement Formulas & Worked Examples](#3-mathematical-settlement-formulas--worked-examples)
4. [4-Archetype Breakdown & Ground-Truth Performance](#4-4-archetype-breakdown--ground-truth-performance)
5. [Complete Security & Governance Framework (6 Pillars)](#5-complete-security--governance-framework-6-pillars)
6. [API & Module Reference](#6-api--module-reference)
7. [Golden Baseline Database & Cloud Deployment Safeguards](#7-golden-baseline-database--cloud-deployment-safeguards)
8. [Automated Test Suite & Verification Matrix](#8-automated-test-suite--verification-matrix)
9. [Architecture Evolution & Implementation History](#9-architecture-evolution--implementation-history)

---

## 1. Core Architecture & 3-Way Reconciliation Model

Every day, a high-growth D2C merchant's cash moves across three disparate data systems:
- **Order Management System (OMS)**: Merchant order book capturing transaction amounts, payment methods, and risk classifications.
- **Payment Gateway (Razorpay)**: Payment captures, fee deductions, dispute holdbacks, refund netting, and settlement batches.
- **Bank Statement Feeds (Cash OLAP)**: Bank credit records containing clearing dates, net credit amounts, and raw bank narration strings.

```
                               ┌──────────────────────────────┐
                               │   Raw Transaction Sources    │
                               │  - OMS Order Ledger          │
                               │    (payment_method, risk_tier)│
                               │  - Gateway Payments & Batches│
                               │    (order_ids, fees, net)    │
                               │  - Bank Statement Feeds      │
                               └──────────────┬───────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                      PERSISTENT OLAP (DuckDB: data/recon_agent.duckdb)                  │
│                                                                                         │
│  [RAW_STAGE]    : Ingested OMS, Gateway Payments, Settlement Batches, and Bank Feeds    │
│  [FACT_STAGE]   : Order-level MDR/GST/Holdback math, batch aggregation, clearing dates  │
└─────────────────────────────────────────────┬───────────────────────────────────────────┘
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
┌───────────────────────────────────────┐               ┌───────────────────────────────────────┐
│       LEG 1: COMMERCIAL RECON         │               │     LEG 2: SETTLEMENT CASH RECON      │
│     OMS Orders <──> Gateway Payments  │               │   Gateway Batches <──> Bank Feeds     │
│  - Key: order_id (1:1 join)           │               └───────────────────┬───────────────────┘
│  - Status match (COMPLETED vs CAPTURED)                                   │
│  - MDR fee validation by payment type │                         ┌─────────┴─────────┐
│  - High-risk holdback (10%) check     │                         ▼                   ▼
│  - Output: commercial_recon_ledger    │              ┌────────────────────┐ ┌───────────────────┐
└───────────────────────────────────────┘              │ Tier 1: SQL Engine │ │  Unmatched Queue  │
                                                       │ - Exact UTR token  │ └─────────┬─────────┘
                                                       │ - Net Amount ±₹1   │           │
                                                       │ - T+0 to T+5 Dates │           ▼
                                                       └─────────┬──────────┘ ┌───────────────────┐
                                                                 │            │ Candidate Filter  │
                                                                 │            │ Top-3 SQL Scored  │
                                                                 │            └─────────┬─────────┘
                                                                 │                      │
                                                                 │                      ▼
                                                                 │            ┌───────────────────┐
                                                                 │            │ Tier 1.5 / Tier 2 │
                                                                 │            ├───────────────────┤
                                                                 │            │ [If API Key]:     │
                                                                 │            │ Tier 2 Gemini AI  │
                                                                 │            │ (Live tokens/time)│
                                                                 │            │                   │
                                                                 │            │ [If Offline]:     │
                                                                 │            │ Tier 1.5 Rule Eng │
                                                                 │            │ (Deterministic)   │
                                                                 │            └─────────┬─────────┘
                                                                 ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                        RECON_LEDGER & AUDIT TRAIL (DuckDB)                              │
│  Status: MATCHED_DETERMINISTIC | MATCHED_AI | MATCHED_RULE | EXCEPTION_HUMAN            │
│  Metrics: tokens_used, latency_ms, variance_explained, audit_reason                     │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### The Two Reconciliation Legs
1. **Leg 1: Commercial Reconciliation (OMS $\leftrightarrow$ Gateway)**:
   - Audits contract compliance at order level via a 1:1 join on `order_id`.
   - Recomputes contract Merchant Discount Rate (MDR) and GST to detect overcharges and status discrepancies (e.g. order marked completed in OMS while payment failed or was refunded in Gateway).
2. **Leg 2: Cash Settlement Reconciliation (Gateway Batches $\leftrightarrow$ Bank Statements)**:
   - Matches aggregated batch payouts against cash actually credited to the merchant's bank account.
   - Solves non-trivial banking challenges: truncated UTR numbers, narration formatting variances across banks (HDFC, ICICI, SBI, Axis), netting adjustments, and adversarial trap transactions.

---

## 2. Complete Database Schema & OLAP Layer (DuckDB)

All tables are defined in [`db/schema.sql`](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/db/schema.sql) and managed in DuckDB with `DECIMAL(18,2)` fixed-point precision.

### 2.1 Staging Tables (`RAW_STAGE`)

#### `raw_oms_orders`
Stores order records originating from the merchant's eCommerce or ERP system.
```sql
CREATE TABLE IF NOT EXISTS raw_oms_orders (
    order_id VARCHAR PRIMARY KEY,
    amount DECIMAL(18,2),
    currency VARCHAR,
    payment_method VARCHAR,      -- UPI | DEBIT_CARD | CREDIT_CARD | NETBANKING
    risk_tier VARCHAR,           -- STANDARD | HIGH_RISK
    status VARCHAR,              -- COMPLETED | CANCELLED | PENDING
    created_at TIMESTAMP
);
```

#### `raw_gateway_payments`
Stores captured payment transactions from the gateway before batch netting.
```sql
CREATE TABLE IF NOT EXISTS raw_gateway_payments (
    payment_id VARCHAR PRIMARY KEY,
    order_id VARCHAR,
    settlement_id VARCHAR,
    amount DECIMAL(18,2),
    payment_method VARCHAR,
    fee DECIMAL(18,2),           -- MDR fee billed by gateway
    tax DECIMAL(18,2),           -- 18% GST billed on MDR
    holdback DECIMAL(18,2),      -- 10% reserve holdback for high-risk orders
    net_amount DECIMAL(18,2),
    status VARCHAR,              -- CAPTURED | FAILED | REFUNDED
    captured_at TIMESTAMP
);
```

#### `raw_gateway_settlements`
Stores batched payout summaries generated by the gateway for bank transfer.
```sql
CREATE TABLE IF NOT EXISTS raw_gateway_settlements (
    settlement_id VARCHAR PRIMARY KEY,
    order_ids VARCHAR,           -- Comma-delimited constituent order IDs
    utr VARCHAR,                 -- Gateway-generated 12-to-16 character UTR reference
    gross_amount DECIMAL(18,2),  -- Sum of captured payment amounts
    mdr_fee DECIMAL(18,2),       -- Sum of MDR fees
    gst_fee DECIMAL(18,2),       -- Sum of GST taxes
    holdback_amount DECIMAL(18,2),-- Dispute reserve holdbacks
    net_amount DECIMAL(18,2),    -- Net amount transferred to merchant bank
    refund_deducted DECIMAL(18,2),-- Chargebacks/refunds netted against payout
    refund_id VARCHAR,
    captured_at DATE,
    expected_credit_date DATE
);
```

#### `raw_bank_statements`
Stores raw credits downloaded from bank statements.
```sql
CREATE TABLE IF NOT EXISTS raw_bank_statements (
    bank_stmt_id VARCHAR PRIMARY KEY,
    credit_date DATE,
    credit_amount DECIMAL(18,2),
    raw_narration VARCHAR        -- Unstructured string containing bank metadata & UTR tokens
);
```

### 2.2 Reconciled Ledgers (`FACT_STAGE`)

#### `commercial_recon_ledger` (Leg 1 Ledger)
Records the line-by-line verification between OMS orders and Gateway payment captures.
```sql
CREATE TABLE IF NOT EXISTS commercial_recon_ledger (
    order_id VARCHAR PRIMARY KEY,
    payment_id VARCHAR,
    settlement_id VARCHAR,
    oms_amount DECIMAL(18,2),
    gateway_amount DECIMAL(18,2),
    payment_method VARCHAR,
    risk_tier VARCHAR,
    expected_fee DECIMAL(18,2),  -- Mathematically recalculated MDR + GST
    gateway_fee DECIMAL(18,2),   -- Fee actually billed by gateway
    status_oms VARCHAR,
    status_gateway VARCHAR,
    recon_status VARCHAR,        -- MATCHED_CLEAN | STATUS_MISMATCH | FEE_VARIANCE | AMOUNT_MISMATCH
    discrepancy_reason VARCHAR,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `recon_ledger` (Leg 2 Cash Settlement Ledger)
Records final cash reconciliation decisions between gateway settlement batches and bank credits.
```sql
CREATE TABLE IF NOT EXISTS recon_ledger (
    bank_stmt_id VARCHAR PRIMARY KEY,
    settlement_id VARCHAR,
    utr VARCHAR,
    recon_status VARCHAR,        -- MATCHED_DETERMINISTIC | MATCHED_AI | MATCHED_RULE | MATCHED_HUMAN_OVERRIDE | EXCEPTION_HUMAN | CONFIRMED_FRAUD | ESCALATED_BANK
    recon_tier VARCHAR,          -- TIER_1_SQL | TIER_1_5_RULE | TIER_2_AI | HUMAN_OVERRIDE
    variance_explained DECIMAL(18,2),
    ai_confidence DOUBLE,
    tokens_used INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    reason VARCHAR,
    matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. Mathematical Settlement Formulas & Worked Examples

### 3.1 Commercial Contract Fee Schedule
In accordance with standard Indian digital payment merchant agreements, MDR fees and dispute holdbacks are strictly tiered:

| Payment Method | Base MDR Rate | Statutory GST Rate | Effective Total Fee | High-Risk Reserve Holdback |
|---|---|---|---|---|
| **UPI** | 0.00% | 18.00% | **0.00%** | 10.00% (if `risk_tier == HIGH_RISK`) |
| **Debit Card** | 0.90% | 18.00% on MDR | **1.062%** | 10.00% (if `risk_tier == HIGH_RISK`) |
| **Credit Card** | 2.00% | 18.00% on MDR | **2.360%** | 10.00% (if `risk_tier == HIGH_RISK`) |
| **Netbanking** | 1.80% | 18.00% on MDR | **2.124%** | 10.00% (if `risk_tier == HIGH_RISK`) |

### 3.2 Indian Gateway Net Settlement Payout Formula
Payment gateways batch multiple captured orders into a single net disbursement to the merchant's bank account:

$$\text{Net Settlement} = \sum_{i=1}^{N} \text{Gross Amount}_i - \sum_{i=1}^{N} \text{MDR}_i - \sum_{i=1}^{N} \text{GST}_i - \sum_{i=1}^{N} \text{Holdback}_i - \text{Refunds Deducted} \pm \text{Adjustments}$$

Where:
- $\text{MDR}_i = \text{ROUND}(\text{Gross}_i \times \text{Rate}(\text{method}_i), 2)$
- $\text{GST}_i = \text{ROUND}(\text{MDR}_i \times 0.18, 2)$
- $\text{Holdback}_i = \begin{cases} \text{ROUND}(\text{Gross}_i \times 0.10, 2) & \text{if } \text{risk\_tier}_i = \text{'HIGH\_RISK'} \\ 0.00 & \text{otherwise} \end{cases}$

### 3.3 Worked Numerical Example
Consider a batch containing 3 orders settled together:
- **Order 1**: ₹5,000.00 via `CREDIT_CARD` (`STANDARD` risk)
  - $\text{MDR} = 5,000.00 \times 0.02 = ₹100.00$
  - $\text{GST} = 100.00 \times 0.18 = ₹18.00$
  - $\text{Holdback} = ₹0.00$
  - $\text{Order 1 Net} = 5,000 - 100 - 18 = ₹4,882.00$
- **Order 2**: ₹10,000.00 via `DEBIT_CARD` (`HIGH_RISK` risk)
  - $\text{MDR} = 10,000.00 \times 0.009 = ₹90.00$
  - $\text{GST} = 90.00 \times 0.18 = ₹16.20$
  - $\text{Holdback} = 10,000.00 \times 0.10 = ₹1,000.00$
  - $\text{Order 2 Net} = 10,000 - 90 - 16.20 - 1,000 = ₹8,893.80$
- **Order 3**: ₹2,500.00 via `UPI` (`STANDARD` risk)
  - $\text{MDR} = ₹0.00$
  - $\text{GST} = ₹0.00$
  - $\text{Holdback} = ₹0.00$
  - $\text{Order 3 Net} = ₹2,500.00$
- **Batch Level Refund**: ₹1,200.00 deducted from prior return netting.

**Final Batch Aggregate**:
- Gross GMV: ₹17,500.00
- Total MDR: ₹190.00
- Total GST: ₹34.20
- Dispute Holdback: ₹1,000.00
- Refund Netting: ₹1,200.00
- **Expected Net Bank Credit**:
  $$17,500.00 - 190.00 - 34.20 - 1,000.00 - 1,200.00 = \mathbf{₹15,075.80}$$

When the bank statement feed shows a credit of ₹15,075.80 with narration `CMS/RAZORPAY/SETTL_9421/00049281`, ReconAgent verifies every sub-component exactly to the paise without IEEE-754 floating-point drift.

---

## 4. 4-Archetype Breakdown & Ground-Truth Performance

ReconAgent is measured against a curated 150-record ground truth benchmark ([`data/ground_truth.json`](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/data/ground_truth.json)) spanning 4 realistic operational archetypes:

### 4.1 Archetype Breakdown Table

| Archetype ID & Name | Description & Banking Simulation | Ground-Truth Records | Passed | Measured Accuracy | Engine Routing |
|---|---|---|---|---|---|
| **Archetype 1: Clean 1:1 UTR** | Standard clearing. Exact 12–16 digit UTR token present in narration, net amount matches batch within $\pm ₹1.00$, clearing date within T+0 to T+5. | 105 | 105 | **100.0%** | **Tier 1 (DuckDB SQL)** at **₹0 token cost** |
| **Archetype 2: Truncated UTR / Typo** | Real-world bank narration truncation (e.g. `NEFT-RZPX-83921...`), OCR digit swaps (0 vs O), or bank-specific prefixes (`CMS/`, `INB/`). | 19 | 19 | **100.0%** | **Tier 2 (Gemini 2.5 Flash)** or **Tier 1.5 (Rule Matcher)** |
| **Archetype 3: Fee & Refund Netting** | Net credit reflects multi-component netting ($\Delta = \text{MDR} + \text{GST} + \text{Refund}$). AI explains exact variance breakdown. | 19 | 18 | **94.7%** | **Tier 2 (Gemini 2.5 Flash)** or **Tier 1.5 (Rule Matcher)** |
| **Archetype 4: Adversarial Traps** | Phantom credits, duplicate twin transactions (identical amounts, same day, different batches), and circular routing. Safely held in review queue. | 7 | 7 | **100.0%** | **Confidence Gate (<0.85)** routes to `EXCEPTION_HUMAN` |
| **Total Benchmark** | **Full 150-Record Cash Settlement Population** | **150** | **149** | **99.33%** | **Blended Autonomous System** |

### 4.2 Confusion Matrix

```
=================================================================
CONFUSION MATRIX (150 Bank Settlement Records):
-----------------------------------------------------------------
  True Positives  (TP) : 142  (Legitimate settlements matched correctly)
  True Negatives  (TN) :   7  (Adversarial traps safely held in review)
  False Positives (FP) :   0  (ZERO financial hallucinations)
  False Negatives (FN) :   1  (Ambiguous variance escalated to auditor)
-----------------------------------------------------------------
  Ground-Truth Accuracy: 99.33% [(142 + 7) / 150]
  Precision            : 100.0% [142 / (142 + 0)]
  Recall               :  99.3% [142 / (142 + 1)]
=================================================================
```

---

## 5. Complete Security & Governance Framework (6 Pillars)

### Pillar 1: Zero PII Ingestion
Financial controllers must never leak customer Personally Identifiable Information (PII) to public LLM endpoints. ReconAgent isolates customer identifiers at the ingestion perimeter: customer names, telephone numbers, billing addresses, and credit card PANs never enter DuckDB tables or LLM inference prompts. Prompts sent to Gemini 2.5 Flash receive only internal pseudo-identifiers (`bank_stmt_103`, `settlement_882`), batch net amounts, and sanitized bank narration strings.

### Pillar 2: Propose, Never Post
In enterprise finance, autonomous agents must not possess direct write access to general ledgers or bank disbursement rails. ReconAgent treats Gemini strictly as an investigative analyst. The model generates structured proposals containing matching settlement IDs, variance explanations, and confidence ratings. These proposals are verified by DuckDB deterministic constraints before entering `recon_ledger`. The LLM cannot unilaterally modify ledger balances, write journal entries, or execute money movements.

### Pillar 3: Strict Confidence Gating (<0.85)
All model outputs are subjected to automated confidence thresholding. If the calculated decision confidence is $< 0.85$, or if the LLM identifies conflicting evidence (such as identical twin payout batches or unknown narration tokens), the system automatically aborts auto-posting. The record is assigned status `EXCEPTION_HUMAN` and routed to Tab 4 (Auditor Exception Workbench) with the full model reasoning preserved.

### Pillar 4: Exact DECIMAL(18,2) Fixed-Point Math
Standard floating-point calculations (`float` / IEEE-754) accumulate rounding errors over thousands of micro-transactions, causing artificial audit variances. ReconAgent executes all arithmetic exclusively using DuckDB `DECIMAL(18,2)` types. Whether calculating 18% GST on a ₹4.12 MDR charge or computing high-risk dispute reserves, calculations remain accurate to the exact paise.

### Pillar 5: Deterministic Rule Fallback (Tier 1.5)
Enterprise financial controllers cannot afford downtime when third-party cloud APIs experience outages or rate limits. ReconAgent features a dual-engine architecture:
- When `GEMINI_API_KEY` is present, it uses live **Gemini 2.5 Flash** for deep contextual inference.
- When running in an offline environment or when quotas are exhausted, the engine automatically falls back to **Tier 1.5 Rule Mode**, executing deterministic regex token matching, window netting heuristics, and date proximity scoring with zero operational interruption.

### Pillar 6: Double-Entry Conservation Laws & 3-Way Closed Loop
ReconAgent bounds cash movement through mathematical conservation:
$$\text{OMS Gross GMV} = \text{Gateway Net Settlements} + \text{Total MDR Fees} + \text{GST} + \text{Dispute Holdbacks} + \text{Pending Float}$$
By cross-referencing all three systems (OMS, Gateway, Bank), any unallocated rupee is explicitly highlighted as either **Commercial Fee Leakage** (in Leg 1) or **Cash Float in Transit** (in Leg 2).

---

## 6. API & Module Reference

### 6.1 `engine.controller.ReconController`
Located in [`engine/controller.py`](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/engine/controller.py). Main orchestrator for the reconciliation pipeline.

- **`__init__(db_path: str, api_key: Optional[str])`**: Initializes DuckDB connection, SQL Tier 1 engine, and AI Tier 2 engine.
- **`load_existing_results() -> Optional[Dict[str, Any]]`**: Reads pre-computed metrics and ledger state from DuckDB. If the ledger is unpopulated, attempts an automatic restore from the golden baseline before falling back.
- **`restore_golden_ledger() -> Optional[Dict[str, Any]]`**: Clones `golden_recon_agent.duckdb` into the live working database and refreshes session state.
- **`run_full_pipeline(oms_path, payments_path, settlements_path, bank_path) -> Dict[str, Any]`**: Executes complete multi-stage pipeline:
  1. Ingests CSVs into `RAW_STAGE`.
  2. Runs Leg 1 commercial 1:1 matching and fee validation.
  3. Runs Leg 2 deterministic Tier 1 matching.
  4. Dispatches unmatched bank records to Tier 2 (Gemini) or Tier 1.5 (Rule Fallback).
  5. Computes final CFO and auditor metrics.

### 6.2 `engine.tier1_sql.Tier1SQLEngine`
Located in [`engine/tier1_sql.py`](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/engine/tier1_sql.py). Executes deterministic relational queries.

- **`execute_leg1_commercial_recon() -> Dict[str, Any]`**: Performs 1:1 join between `raw_oms_orders` and `raw_gateway_payments`, recalculates contract MDR/GST, and populates `commercial_recon_ledger`.
- **`execute_leg2_deterministic_match() -> int`**: Matches clean bank records against gateway settlements where exact UTR tokens match, net amounts match within ₹1.00, and dates fall within clearing windows.
- **`get_top3_candidates(bank_record: dict) -> List[dict]`**: Parameterized SQL query retrieving the 3 best candidate settlements based on date proximity, amount closeness, and UTR overlap.
- **`get_unmatched_bank_records() -> List[dict]`**: Retrieves bank statements remaining unmatched after Tier 1.

### 6.3 `engine.tier2_ai.Tier2AIInvestigator`
Located in [`engine/tier2_ai.py`](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/engine/tier2_ai.py). Handles GenAI reasoning and rule fallback.

- **`investigate(bank_rec: dict, candidates: List[dict]) -> ReconDecisionSchema`**: Analyzes cryptic bank statements against top-3 candidates. Calls Gemini 2.5 Flash via `google-genai` SDK with strict Pydantic structured output (`ReconDecisionSchema`). If offline, falls back to deterministic rule matching.
- **`ReconDecisionSchema`**: Pydantic schema enforcing output contract:
  - `decision`: `"MATCH"` | `"UNRESOLVED"`
  - `selected_settlement_id`: Optional string
  - `confidence`: Float between 0.0 and 1.0
  - `variance_explained`: Decimal variance amount
  - `reason`: Structured textual explanation of match or trap detection

### 6.4 `db.duckdb_client.DuckDBClient`
Located in [`db/duckdb_client.py`](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/db/duckdb_client.py). Persistence and OLAP management.

- **`__init__(db_path: str)`**: Connects to DuckDB file. If running on a fresh cloud container without an existing live DB, auto-bootstraps from `golden_recon_agent.duckdb`.
- **`_connect()`**: Opens connection. If the database file is locked by a concurrent process, gracefully falls back to an in-memory session cloned from the golden baseline.
- **`init_schema()`**: Runs DDL from `schema.sql`.
- **`get_cfo_metrics() -> Dict[str, float]`**: Returns liquidity metrics (Gross GMV, Expected Net, MDR, GST, Holdbacks, Float).
- **`get_recon_ledger_metrics() -> Dict[str, int]`**: Returns counts by tier (Tier 1 SQL, Tier 2 AI, Tier 1.5 Rule, Human Override, Unresolved).

---

## 7. Golden Baseline Database & Cloud Deployment Safeguards

### 7.1 Instant Cold-Start Boot
To prevent a 3–5 minute latency penalty during cloud deployment (where Streamlit Cloud boots a blank container without pre-existing DuckDB tables), ReconAgent tracks [`data/golden_recon_agent.duckdb`](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/data/golden_recon_agent.duckdb) (`6.8 MB`) in Git.

When the application boots:
```python
# db/duckdb_client.py & app/streamlit_app.py
if not os.path.exists(live_db_path) or os.path.getsize(live_db_path) < 100_000:
    if os.path.exists(golden_db_path):
        shutil.copyfile(golden_db_path, live_db_path)
```
The verified golden state (150 evaluated records, CFO metrics, 99.3% accuracy) loads in **under 50 milliseconds**.

### 7.2 Public Demo Lock (`IS_PUBLIC_DEPLOY`)
When hosted for public evaluation or judge review, mutation buttons ("▶ Run Pipeline", "🎲 Regenerate Data", "🔄 Reset DB") can be locked to prevent quota exhaustion or data tampering.

In Streamlit Cloud **App Settings → Secrets**:
```toml
IS_PUBLIC_DEPLOY = true
```
- In the Header: Displays `🔒 Golden Baseline Active (Public Demo)`.
- In the Sidebar: Locks pipeline execution controls with an explanatory note.
- In local development (`IS_PUBLIC_DEPLOY = false`), all buttons remain active.

---

## 8. Automated Test Suite & Verification Matrix

The test suite contains **11 automated tests** across 4 test modules:

```bash
pytest tests/ -v
```

### Test Case Directory & Verification Objectives

| Test File | Test Function | Verification Objective |
|---|---|---|
| **`tests/test_reconciliation.py`** | `test_synthetic_generator_files_exist` | Validates that synthetic generator creates all required CSVs (OMS, Payments, Settlements, Bank). |
| | `test_duckdb_precision_and_cfo_metrics` | Validates that DuckDB client connects with `DECIMAL(18,2)` precision and computes CFO metrics without floating-point error. |
| | `test_leg1_commercial_recon` | Validates 1:1 OMS-to-Gateway join, fee recomputation, and detection of status mismatches and fee overcharges. |
| | `test_leg2_tier1_deterministic_matching` | Validates that clean 1:1 UTR records match deterministically in SQL at ₹0 token cost. |
| | `test_tier2_schema_and_offline_rule_mode` | Validates Pydantic schema validation and Tier 1.5 offline rule fallback when no API key is present. |
| | `test_pipeline_consistency_and_conservation_law` | Validates double-entry accounting identity: $\text{Gross} = \text{Net} + \text{MDR} + \text{GST} + \text{Holdback} + \text{Float}$. |
| **`tests/test_tab3_display.py`** | `test_tab3_ground_truth_and_segmented_accuracy` | Validates Ground-Truth Accuracy calculation, 4-archetype breakdown display, and illustrative BPO labor benchmarks. |
| **`tests/test_override_guard.py`** | `test_human_override_guard` | Validates that auto-reconciled records are strictly locked against unauthorized manual modification in Tab 4. |
| **`tests/test_ui_polish.py`** | `test_landing_page_source_structure` | Validates button placement above description, 1.25rem font, cyan gradient, full-width card, and removal of duplicate back button. |
| | `test_multipage_home_structure` | Validates that `0_🏠_Home.py` mirrors updated landing page layout and expanded sidebar defaults. |
| | `test_apptest_interaction` | Streamlit `AppTest` acceptance test simulating landing page click and clean state transition into Dashboard cockpit. |

---

## 9. Architecture Evolution & Implementation History

ReconAgent underwent a systematic architecture overhaul to transition from an initial prototype to a verified, production-grade financial controller:

1. **Elimination of Mock Inference**:
   - Initial versions utilized mocked outputs returning synthetic confidence floats.
   - Refactored to genuine live Gemini 2.5 Flash inference with structured Pydantic schema validation, backed by an honest deterministic Tier 1.5 rule engine when offline.
2. **True 1:1 Commercial Matching (Leg 1)**:
   - Initial versions only performed single-table counts on OMS orders.
   - Replaced with true relational joining between OMS orders and Gateway captures on `order_id`, recalculating contract MDR rates and flagging overcharged fees.
3. **Database Concurrency & Precision**:
   - Replaced transient in-memory DuckDB sessions with persistent file-backed OLAP storage (`data/recon_agent.duckdb`).
   - Implemented automatic in-memory cloning when files are locked by active dev servers to allow simultaneous testing and UI previewing.
   - Enforced `DECIMAL(18,2)` precision across all schemas to eliminate floating-point drift.
4. **Zero-PII Perimeter & Silent Authentication**:
   - Eliminated plaintext API key inputs from UI surfaces.
   - Configured silent `.env` loading and zero transmission of customer PII in inference prompts.
5. **Instant Cloud Deployment via Golden Baseline**:
   - Created `golden_recon_agent.duckdb` and automated cold-start bootstrap logic, reducing Streamlit Cloud cold boot latency from 5 minutes to under 50 milliseconds.
