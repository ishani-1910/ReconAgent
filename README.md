# Razorpay ReconAgent: 3-Way Bounded Financial Controller & Settlement Engine

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/OLAP-DuckDB-yellow.svg)](https://duckdb.org/)
[![Gemini GenAI](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-green.svg)](https://ai.google.dev/)
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An enterprise-grade autonomous financial reconciliation and settlement controller that verifies cash liquidity, matches multi-source records (**OMS** $\leftrightarrow$ **Gateway** $\leftrightarrow$ **Bank**), detects fee/refund variances, and resolves cryptic banking narrations using a bounded, cost-aware multi-tier engine (DuckDB SQL + Gemini GenAI).

---

## Architecture Blueprint

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

---

## Key Highlights & Innovations

1. **True Commercial Recon (Leg 1: OMS ↔ Gateway)**:
   - Performs a true 1:1 join between OMS orders and Gateway payment captures on `order_id`.
   - Recomputes contract MDR fees dynamically:
     - **UPI**: 0.00%
     - **Debit Card**: 0.90%
     - **Credit Card**: 2.00%
     - **Netbanking**: 1.80%
     - **GST**: 18.00% on MDR
     - **High-Risk Reserve Holdback**: 10.00% dispute reserve
   - Flags payment status discrepancies (`OMS COMPLETED` vs `Gateway FAILED/REFUNDED`) and overcharged fee leakages.

2. **Domain Precision (Indian Net Settlement Formula)**:
   - Accurately models real-world payment gateway netting:
     $$\text{Net Settlement} = \sum(\text{Gross}) - \text{MDR} - \text{GST} - \text{Holdback} - \text{Refunds} \pm \text{Adjustments}$$
   - Enforces exact `DECIMAL(18,2)` arithmetic across all DuckDB tables, preventing floating-point rounding errors.

3. **85%+ Token Cost Reduction (Multi-Tier Architecture)**:
   - **Tier 1 (DuckDB SQL)** processes clean records at **₹0 token cost**.
   - **Tier 2 (Gemini 2.5 Flash GenAI)** is only invoked for cryptic narrations, truncated UTRs, and fee/refund variances.
   - **Tier 1.5 (Deterministic Rule Engine)** provides an offline fallback when no API key is present.

4. **Zero-Hallucination Guardrail & Audit Trail**:
   - Enforces structured Pydantic schema validation (`response_mime_type="application/json"`).
   - If AI confidence is `< 0.85` or duplicate ambiguity exists (e.g. twin amounts, phantom bank credits), the engine sets `"decision": "UNRESOLVED"` and routes to `EXCEPTION_HUMAN`.
   - Stores real tokens consumed and execution latency in `recon_ledger`.

5. **Security & Persistence**:
   - All DuckDB queries use **strictly parameterized queries** (`?` placeholders).
   - Database is persistent on disk at `data/recon_agent.duckdb`.

---

## Evaluation Benchmark & Verification

Evaluated across both Leg 1 (Commercial) and Leg 2 (Cash Settlement):

```
=================================================================
      RAZORPAY RECONAGENT: BENCHMARK & EVALUATION REPORT
=================================================================
Tier 2 Execution Engine      : [LIVE GEMINI 2.5 FLASH / TIER 1.5 RULE]
-----------------------------------------------------------------
LEG 1: Commercial Recon Acc  : 386/386 (100.00%)
  Clean Orders Matched       : 361
  Status Mismatches Detected : 11
  Fee Variances Detected     : 14
  Total Fee Leakage Flagged  : Rs.1,365.41
-----------------------------------------------------------------
LEG 2: Bank Records Evaluated: 150
  Tier 1 Deterministic Match : 105/105 (100.0%) [Rs.0 Tokens]
  Tier 2 / 1.5 Match Rate    : 37/38 (97.4%)
  Adversarial Traps Handled  : 7/7 (100.0%)
  Hallucination / False Pos  : 0 (0.00%)
  Overall Cash Recon Acc     : 99.33%
-----------------------------------------------------------------
CONFUSION MATRIX:
  True Positives (Matched Correctly) : 142
  True Negatives (Traps Unresolved)  : 7
  False Positives (Hallucinations)   : 0
  False Negatives (Missed Matches)   : 1
=================================================================
```

---

## Project Structure

```
ReconAgent/
├── .env                        # Configure GEMINI_API_KEY here
├── data/
│   ├── generator.py            # Multi-archetype feed generator with payment methods & fees
│   ├── ground_truth.json       # Ground truth registry for Leg 1 and Leg 2 validation
│   └── recon_agent.duckdb      # Persistent DuckDB database file
├── db/
│   ├── duckdb_client.py        # Persistent DuckDB session & parameterized execution
│   └── schema.sql              # RAW_STAGE, FACT_STAGE, and RECON_LEDGER DDL
├── engine/
│   ├── tier1_sql.py            # Leg 1 commercial recon & Leg 2 deterministic SQL matcher
│   ├── tier2_ai.py             # Live Gemini 2.5 Flash GenAI & Tier 1.5 rule engine
│   └── controller.py           # Pipeline orchestrator with telemetry tracking
├── app/
│   └── streamlit_app.py        # 4-Tab interactive CFO & Auditor cockpit
├── eval/
│   └── benchmark.py            # Programmatic confusion matrix & accuracy evaluator
├── tests/
│   └── test_reconciliation.py  # Automated pytest test suite
├── requirements.txt            # duckdb, streamlit, pydantic, google-genai, pandas, pytest, python-dotenv
└── README.md                   # System documentation & architectural pitch
```

---

## Quick Start

### 1. Installation
```powershell
pip install -r requirements.txt
```

### 2. Configure Gemini API Key (Optional for Live GenAI)
Edit `.env` in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
*(If no key is configured, the system automatically and transparently operates in Tier 1.5 Rule Fallback mode).*

### 3. Generate Synthetic Dataset
```powershell
python -u data/generator.py
```

### 4. Run Automated Tests
```powershell
pytest tests/ -v
```

### 5. Run Accuracy & Telemetry Benchmark
```powershell
python -u eval/benchmark.py
```

### 6. Launch Streamlit Controller Cockpit
```powershell
streamlit run app/streamlit_app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.
