# Razorpay ReconAgent: 3-Way Bounded AI Financial Controller

## System Goal
Build an enterprise-grade autonomous financial reconciliation and settlement controller that verifies cash liquidity, matches multi-source records (OMS $\leftrightarrow$ Gateway $\leftrightarrow$ Bank), detects fee/refund variances, and resolves cryptic banking narrations using a bounded, cost-aware two-tier engine (DuckDB SQL + Gemini LLM).

---

## User Review Required

> [!IMPORTANT]
> **Key Architectural Enhancements & Adjustments:**
> 1. **Correct Pathing**: All components are structured directly under the repository root `c:\Users\Oscar\Documents\GitHub\ReconAgent\`.
> 2. **Financial Precision**: All SQL schemas and DuckDB calculations strictly enforce `DECIMAL(18,2)` data types to prevent floating-point rounding discrepancies on fee calculations ($2\%$ MDR $+ 18\%$ GST) and tolerance matching ($\pm ₹1.00$).
> 3. **Structured GenAI SDK Integration**: Tier 2 Gemini calls explicitly enforce `google-genai` SDK with `response_mime_type="application/json"` and Pydantic schema validation (`ReconDecisionSchema`) to guarantee structured outputs and prevent hallucinations.
> 4. **Configurable Settlement Window**: DuckDB matching supports $T+0$ to $T+3$ clearing windows, configurable up to $T+5$ for extended holiday/weekend windows.

---

## Open Questions

> [!NOTE]
> None at this stage. All domain formulas, netting rules, and two-tier boundary conditions are fully specified.

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

## 1. Domain Modeling: The Indian Netting & Settlement Reality

### A. Net Settlement Formula
Razorpay does not settle gross order sums. Bank statements reflect net payouts calculated as:

$$\text{Net Settlement} = \sum(\text{Gross Captured}) - \sum(\text{MDR Fee}) - \sum(\text{GST on MDR at 18\%}) - \sum(\text{Refunds Deducted}) - \sum(\text{Dispute Reserves}) \pm \text{Adjustments}$$

* **MDR Fee**: Standard $2.00\%$ of Gross Captured.
* **GST on MDR**: $18.00\%$ applied to the fee ($0.36\%$ effective deduction).
* **Cross-Cycle Deductions**: Refunds initiated for past orders are netted against current settlement batches (`rfnd_xxx`).

### B. Settlement Timing & Date Drift
* **Normal Cycle**: $T+1$ business days.
* **Weekend/Holiday Window**: Orders captured Friday–Sunday settle on Monday or Tuesday.
* **Matching Rule**: Bank credit date must satisfy `bank_date BETWEEN expected_credit_date AND expected_credit_date + INTERVAL '5 DAYS'`.

---

## 2. Two-Tier Reconciliation Engine

### Tier 1: Deterministic Engine (DuckDB SQL)
Processes bulk volume at ₹0 token cost:
1. **Pre-aggregation**: Groups Gateway transactions by `settlement_id`, calculates `net_amount` using `DECIMAL(18,2)`, and extracts candidate `utr`.
2. **Deterministic Match Condition**:
   - `bank.credit_amount` matches `gateway.net_amount` within $\pm ₹1.00$ tolerance.
   - Bank `credit_date` falls within the $[T+0, T+5]$ clearing window.
   - Bank `raw_narration` contains the `utr` substring.
   - Flagged as `MATCHED_DETERMINISTIC`.

### Tier 2: Bounded AI Investigator (Gemini via Structured JSON)
Activated only for records failing Tier 1:
1. **Candidate Retrieval**: SQL retrieves the top 3 closest Gateway settlement candidates based on net amount proximity and date proximity.
2. **Context Enrichment**: Includes any cross-cycle refund IDs, MDR adjustments, or dispute holds associated with each candidate.
3. **Structured Pydantic Contract**:
   ```json
   {
     "decision": "MATCH",
     "selected_settlement_id": "setl_9182374",
     "confidence": 0.96,
     "variance_explained": 1500.00,
     "reason": "Bank narration references 'CMS RZP 2374' matching settlement suffix. Amount discrepancy of ₹1,500 corresponds to cross-cycle refund rfnd_4810293."
   }
   ```
4. **Safety Guardrail**: If `confidence < 0.85` or if multiple candidates are indistinguishable, the AI MUST output `"decision": "UNRESOLVED"`, routing the record to `EXCEPTION_HUMAN`.

---

## Proposed Changes

### Data & Ground Truth Layer

#### [NEW] [generator.py](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/data/generator.py)
* Generates 150 synthetic records across 4 archetypes (Clean Flow, Cryptic Narration, Netting Variance, Adversarial Traps).
* Produces OMS Orders CSV, Razorpay Gateway Batches CSV, and Bank Statements CSV.

#### [NEW] [ground_truth.json](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/data/ground_truth.json)
* Canonical registry mapping transaction IDs to ground truth labels (`MATCHED_DETERMINISTIC`, `MATCHED_AI`, `EXCEPTION_HUMAN`) for eval benchmarking.

---

### Database & Storage Layer

#### [NEW] [schema.sql](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/db/schema.sql)
* SQL script creating `RAW_STAGE`, `FACT_STAGE`, and `RECON_LEDGER` with exact `DECIMAL(18,2)` types for all monetary fields.

#### [NEW] [duckdb_client.py](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/db/duckdb_client.py)
* DuckDB session manager, staging CSV ingestion, and fee metric views.

---

### Reconciliation Engine Layer

#### [NEW] [tier1_sql.py](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/engine/tier1_sql.py)
* Deterministic SQL reconciliation engine (Leg 1 & Leg 2) and Top-3 candidate retriever for unmatched records.

#### [NEW] [tier2_ai.py](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/engine/tier2_ai.py)
* Bounded Gemini LLM investigator using `google-genai` SDK with Pydantic JSON schema (`ReconDecisionSchema`).

#### [NEW] [controller.py](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/engine/controller.py)
* Master pipeline orchestrator tying together data ingestion, Tier 1 SQL, candidate retrieval, Tier 2 Gemini calls, and database updates.

---

### Web Dashboard & Evaluation Layer

#### [NEW] [streamlit_app.py](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/app/streamlit_app.py)
* 3-Tab Streamlit Cockpit:
  1. CFO Executive Cash & Liquidity Dashboard.
  2. Ground-Truth Accuracy & Cost Savings Matrix.
  3. Auditor Exception Workbench with manual override capabilities.

#### [NEW] [benchmark.py](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/eval/benchmark.py)
* Programmatic confusion matrix, match accuracy reporter, and hallucination rate benchmark.

#### [NEW] [test_reconciliation.py](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/tests/test_reconciliation.py)
* Automated pytest suite covering deterministic matching, netting formulas, and date window logic.

#### [NEW] [requirements.txt](file:///c:/Users/Oscar/Documents/GitHub/ReconAgent/requirements.txt)
* Project dependencies: `duckdb`, `streamlit`, `pydantic`, `google-genai`, `pandas`, `pytest`.

---

## Verification Plan

### Automated Tests
- Run pytest suite: `pytest tests/`
- Run evaluation script against ground truth dataset: `python eval/benchmark.py`
  - **Tier 1 Match Rate**: Target $70\% \pm 3\%$
  - **Tier 2 Precision**: Target $> 90\%$ on Type 2 & Type 3 archetypes
  - **False Positive / Hallucination Rate**: $0.0\%$ (Safety Trap verification)

### Manual Verification
- Launch Streamlit UI: `streamlit run app/streamlit_app.py`
- Verify live execution of Leg 1 and Leg 2 reconciliation runs.
- Inspect AI chain-of-thought reasoning modals and test human-in-the-loop override actions.
