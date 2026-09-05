# ReconAgent: 3-Way Bounded Financial Controller (OMS ↔ Gateway ↔ Bank OLAP)

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/OLAP-DuckDB-yellow.svg)](https://duckdb.org/)
[![Gemini GenAI](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-green.svg)](https://ai.google.dev/)
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Accuracy](https://img.shields.io/badge/Ground--Truth%20Accuracy-99.33%25-brightgreen.svg)]()

An enterprise-grade autonomous financial reconciliation and settlement controller that closes the loop between three disconnected systems: the **Order Management System (OMS)**, the **Payment Gateway (Razorpay)**, and the **Bank Statement (Cash OLAP)**.

ReconAgent detects commercial fee leakages, matches multi-source cash settlements, audits high-risk dispute holdbacks, and resolves cryptic banking narrations using a cost-bounded multi-tier engine (DuckDB fixed-point SQL + Gemini 2.5 Flash GenAI).

---

## ⚡ Quick Start: Open & Run the Project

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/ishani-1910/ReconAgent.git
cd ReconAgent
pip install -r requirements.txt
```
*(Recommended Python version: **3.12** or 3.11)*

### 2. Configure Gemini API Key (Optional for Live GenAI)
Create or edit `.env` in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
> **Security & Governance Note:** The API key is loaded silently from `.env` and is **never** exposed in the UI. If no API key is provided, ReconAgent operates seamlessly in **Deterministic Tier 1.5 Rule Fallback Mode** with zero disruptions and complete uptime.

### 3. Launch the Application
```bash
streamlit run app/streamlit_app.py
```
Open **[http://localhost:8501](http://localhost:8501)** in your browser.  
Click the cyan **"→ Open Dashboard"** button on the landing page to enter the live controller cockpit.

### 4. Run Automated Tests & Benchmark
```bash
# Run full 11-test automated test suite
pytest tests/ -v

# Run ground-truth accuracy benchmark & confusion matrix
python -u eval/benchmark.py
```

---

## 🛡️ Why Trust External AI in Finance? (Security & Governance)

Financial systems cannot tolerate hallucinated ledger entries or floating-point rounding drifts. ReconAgent enforces strict architectural guardrails:

1. **Zero PII Ingestion**: No customer names, phone numbers, email addresses, or card PANs are ever transmitted to Gemini. Only internal pseudo-identifiers, batch settlement amounts, and sanitized bank narration strings enter inference prompts.
2. **Propose, Never Post**: The LLM acts strictly as an investigative intelligence layer. It proposes matches with structured rationales, but cannot unilaterally alter account balances or commit transactions to general ledger without mathematical validation.
3. **Strict Confidence Gating (<0.85)**: Every AI match must achieve confidence $\ge 0.85$. Any ambiguous narration, conflicting delta, or adversarial trap automatically bypasses auto-match and halts in the **Human Auditor Review Queue**.
4. **Exact DECIMAL(18,2) Math**: All commercial fee calculations (UPI 0%, Debit 0.9%, Credit 2.0%, Netbanking 1.8%), 18% GST, and 10% risk dispute holdbacks are computed using DuckDB fixed-point math — eliminating IEEE-754 floating-point rounding discrepancies.
5. **Deterministic Rule Fallback**: If Gemini API quotas are exhausted or network access is severed, the system gracefully falls back to a 100% deterministic Tier 1.5 rule engine with zero downtime.
6. **Double-Entry Conservation Laws**: Links OMS orders $\leftrightarrow$ Gateway settlements $\leftrightarrow$ Bank statement credits. Commercial fee leakages and cash float in transit are continuously bounded and audited.

---

## 🏛️ Architecture Blueprint

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

## 🎛️ 4-Tab Interactive Controller Cockpit

The Streamlit cockpit organizes complex financial telemetry into four specialized workbenches:

| Tab | Name | Purpose & Key Metrics |
|---|---|---|
| **Tab 1** | **📈 CFO Liquidity & Cash Flow** | Real-time liquidity overview: Gross GMV, Net Expected Settlement, MDR Fee Leakage, 18% GST, 10% Reserve Holdbacks, and Bank Settled Cash. Tracks cash float in transit. |
| **Tab 2** | **⚖️ Leg 1: Commercial Recon** | Order-level 1:1 join between OMS orders and Gateway payment captures. Audits contract MDR rates by payment method (UPI, Debit, Credit, Netbanking) and flags status discrepancies (`OMS COMPLETED` vs `Gateway FAILED`). |
| **Tab 3** | **🎯 Leg 2: Cash Settlement Matrix** | Bank statement matching cockpit against ground truth. Displays the **99.3% measured accuracy card**, 4-archetype segmented accuracy breakdown, confusion matrix, and BPO manual ops labor benchmark. |
| **Tab 4** | **🔍 Auditor Exception Workbench** | Human-in-the-Loop review queue for exceptions (<0.85 confidence or adversarial traps). Includes tamper-proof locks preventing unauthorized overrides on already-verified matches. |

---

## 📊 Ground-Truth Evaluation Benchmark

ReconAgent is validated against a rigorous 150-record ground truth dataset featuring 4 distinct transaction archetypes and adversarial edge cases:

```
=================================================================
             RECONAGENT: BENCHMARK & EVALUATION REPORT
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

### Segmented Archetype Accuracy

| Archetype | Evaluation Focus | Ground-Truth Records | Passed | Measured Accuracy |
|---|---|---|---|---|
| **Clean 1:1 UTR** | Deterministic SQL netting + UTR token match | 105 | 105 | **100.0%** |
| **Truncated UTR / Typo** | AI fuzzy string alignment & bank narration parsing | 19 | 19 | **100.0%** |
| **Fee / Refund Netting** | Multi-component variance explanation ($\Delta = \text{MDR} + \text{Refund}$) | 19 | 18 | **94.7%** |
| **Adversarial Traps** | Phantom credits, duplicate twins, circular routing (held in review queue) | 7 | 7 | **100.0%** |

---

## ☁️ Streamlit Cloud Deployment & Instant Boot

ReconAgent is optimized for zero cold-start latency when deployed to **Streamlit Community Cloud**:

1. **Golden Baseline Database (`data/golden_recon_agent.duckdb`)**:
   - The verified 6.8MB reference database is tracked in Git.
   - On cold start in a fresh container, the app automatically clones the golden database to `data/recon_agent.duckdb` in milliseconds, eliminating the 3–5 minute wait time of running a live pipeline from scratch.
2. **Public Demo Protection (`IS_PUBLIC_DEPLOY`)**:
   - In Streamlit Cloud **App Settings → Secrets**, optionally configure:
     ```toml
     IS_PUBLIC_DEPLOY = true
     ```
   - This safely locks mutation buttons (Pipeline Run / Regenerate Synthetic Data) to protect evaluation quotas and guarantee consistent evaluator metrics.

---

## 📁 Repository Structure

```
ReconAgent/
├── .env                              # Silent API key configuration (GEMINI_API_KEY)
├── .gitignore                        # Tracks golden DB (!data/golden_recon_agent.duckdb)
├── requirements.txt                  # duckdb, streamlit, pydantic, google-genai, pandas, pytest
├── README.md                         # Project documentation & blueprint
├── data/
│   ├── generator.py                  # Synthetic data generator (OMS, Gateway, Bank feeds)
│   ├── ground_truth.json             # Ground truth registry for Leg 1 and Leg 2 validation
│   ├── golden_recon_agent.duckdb     # Committed reference database (150 records, 99.3% accuracy)
│   └── recon_agent.duckdb            # Live working DuckDB database (auto-bootstrapped)
├── db/
│   ├── duckdb_client.py              # Persistent DuckDB session, OLAP cloning & queries
│   └── schema.sql                    # DuckDB DDL schema (DECIMAL(18,2) precision tables)
├── engine/
│   ├── tier1_sql.py                  # Leg 1 commercial recon & Leg 2 deterministic SQL engine
│   ├── tier2_ai.py                   # Live Gemini 2.5 Flash GenAI & Tier 1.5 rule fallback
│   └── controller.py                 # Pipeline orchestrator, telemetry & golden restore logic
├── app/
│   ├── streamlit_app.py              # Main application entry point & 4-tab controller cockpit
│   └── pages/
│       └── 0_🏠_Home.py              # Executive landing page & governance overview
├── eval/
│   └── benchmark.py                  # Confusion matrix, segmented accuracy & BPO evaluator
├── scripts/
│   └── restore_golden.py             # CLI utility to restore live database from golden baseline
└── tests/
    ├── test_reconciliation.py        # Pipeline consistency, precision & conservation laws
    ├── test_tab3_display.py          # Ground-truth accuracy and segmented display tests
    ├── test_override_guard.py        # Auditor override guardrail & tamper-proof lock tests
    └── test_ui_polish.py             # Landing page layout, button position & AppTest suite
```

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
