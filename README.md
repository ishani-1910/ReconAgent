# Razorpay ReconAgent: 3-Way Bounded AI Financial Controller

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/OLAP-DuckDB-yellow.svg)](https://duckdb.org/)
[![Gemini GenAI](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-green.svg)](https://ai.google.dev/)
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An enterprise-grade autonomous financial reconciliation and settlement controller that verifies cash liquidity, matches multi-source records (**OMS** $\leftrightarrow$ **Gateway** $\leftrightarrow$ **Bank**), detects fee/refund variances, and resolves cryptic banking narrations using a bounded, cost-aware two-tier engine (DuckDB SQL + Gemini LLM).

---

## Architecture Blueprint

```
                     ┌──────────────────────────────┐
                     │   Raw Transaction Sources    │
                     │  - OMS Order Ledger          │
                     │  - Razorpay Gateway Ledger   │
                     │  - Bank Account Statement    │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     PERSISTENT OLAP (DuckDB)                          │
│                                                                       │
│  [RAW_STAGE]  : Unmodified raw CSV feeds                              │
│  [FACT_STAGE] : Standardized ledgers, calculated fees (DECIMAL 18,2), │
│                 deducted refunds, T+1/T+2 clearing calendars          │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          ▼                                                   ▼
┌───────────────────────────┐               ┌───────────────────────────────────┐
│  LEG 1: COMMERCIAL RECON  │               │   LEG 2: SETTLEMENT CASH RECON    │
│  OMS <──> Razorpay Gateway│               │   Gateway Batches <──> Bank Feeds │
│  - Key: order_id (1:1)    │               └─────────────────┬─────────────────┘
│  - Verifies captured GOV  │                                 │
└───────────────────────────┘                     ┌───────────┴───────────┐
                                                  ▼                       ▼
                                       ┌────────────────────┐   ┌───────────────────┐
                                       │ Tier 1: SQL Engine │   │ Unmatched Queue   │
                                       │ - Exact UTR token  │   └─────────┬─────────┘
                                       │ - Net Amount ±₹1   │             │
                                       │ - T+0 to T+5 Dates │             ▼
                                       └─────────┬──────────┘   ┌───────────────────┐
                                                 │              │ Candidate Filter  │
                                                 │              │ Top-3 SQL Scored  │
                                                 │              └─────────┬─────────┘
                                                 │                        │
                                                 │                        ▼
                                                 │              ┌───────────────────┐
                                                 │              │ Tier 2: AI Agent  │
                                                 │              │ Bounded JSON,     │
                                                 │              │ Confidence >=0.85 │
                                                 │              └─────────┬─────────┘
                                                 ▼                        ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           RECON_LEDGER & AUDIT TRAIL                              │
│  Status: MATCHED_DETERMINISTIC | MATCHED_AI | EXCEPTION_HUMAN                     │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT CONTROLLER COCKPIT                               │
│  1. CFO Liquidity & Cash Flow KPIs   2. Ground-Truth Accuracy Matrix              │
│  3. Categorized Exception Buckets    4. Interactive Auditor Workbench             │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Highlights & Innovations

1. **Domain Precision (Indian Net Settlement Formula)**:
   - Accurately models real-world payment gateway netting:
     $$\text{Net Settlement} = \sum(\text{Gross}) - \text{MDR}(2.00\%) - \text{GST}(18.00\% \text{ on MDR}) - \text{Refunds} - \text{Reserves} \pm \text{Adjustments}$$
   - Enforces exact `DECIMAL(18,2)` arithmetic across DuckDB tables, preventing floating-point rounding bugs.

2. **90%+ Token Cost Reduction (Two-Tier Model)**:
   - **Tier 1 (DuckDB SQL)** processes clean records at **₹0 token cost**.
   - **Tier 2 (Gemini AI)** is only invoked for cryptic narrations, truncated UTRs, and fee/refund variances.

3. **Context Efficiency via SQL Candidate Retriever**:
   - Instead of dumping raw transaction logs into prompts, SQL pre-scores and retrieves only the **Top-3 closest candidate Gateway settlements**.

4. **Zero-Hallucination Guardrail (Circuit Breaker)**:
   - Enforces structured Pydantic schema validation (`response_mime_type="application/json"`).
   - If AI confidence is `< 0.85` or duplicate ambiguity exists (e.g. twin amounts, phantom bank credits), the engine sets `"decision": "UNRESOLVED"` and routes to `EXCEPTION_HUMAN`.

---

## Evaluation Benchmark & Verification

Evaluated against 150 synthetic records across 4 explicit real-world archetypes:

```
============================================================
      RAZORPAY RECONAGENT: BENCHMARK & EVALUATION REPORT
============================================================
Total Bank Records Evaluated : 150
Tier 1 Deterministic Match   : 105/105 (100.0%)
Tier 2 AI Escalation Match   : 36/38 (94.7%)
Adversarial Traps Handled   : 7/7 (100.0%)
Hallucination / False Pos   : 0 (0.00%)
Overall Ground-Truth Acc     : 98.67%
------------------------------------------------------------
CONFUSION MATRIX:
  True Positives (Matched Correctly)  : 141
  True Negatives (Traps Unresolved)   : 7
  False Positives (Hallucinations)    : 0
  False Negatives (Missed Matches)    : 2
============================================================
```

---

## Project Structure

```
ReconAgent/
├── data/
│   ├── generator.py            # 150-record multi-archetype generator
│   └── ground_truth.json       # Ground truth evaluation registry
├── db/
│   ├── duckdb_client.py        # Embedded DuckDB session & CFO metrics view
│   └── schema.sql              # RAW_STAGE, FACT_STAGE, and RECON_LEDGER DDL
├── engine/
│   ├── tier1_sql.py            # Deterministic SQL engine & Top-3 candidate retriever
│   ├── tier2_ai.py             # Bounded Gemini LLM investigator (Pydantic schema)
│   └── controller.py           # Master reconciliation pipeline orchestrator
├── app/
│   └── streamlit_app.py        # 3-Tab interactive CFO & Auditor cockpit
├── eval/
│   └── benchmark.py            # Programmatic confusion matrix & accuracy evaluator
├── tests/
│   └── test_reconciliation.py  # Automated pytest test suite
├── requirements.txt            # duckdb, streamlit, pydantic, google-genai, pandas, pytest
└── README.md                   # System documentation & architectural pitch
```

---

## Quick Start

### 1. Installation
```powershell
pip install -r requirements.txt
```

### 2. Generate Synthetic Dataset
```powershell
python -u data/generator.py
```

### 3. Run Automated Tests
```powershell
pytest tests/
```

### 4. Run Accuracy Benchmark
```powershell
python -u eval/benchmark.py
```

### 5. Launch Streamlit Controller Cockpit
```powershell
streamlit run app/streamlit_app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.
