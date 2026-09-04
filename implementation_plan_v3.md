# Razorpay ReconAgent: 3-Way Bounded AI Financial Controller

## System Goal
Build an enterprise-grade autonomous financial reconciliation and settlement controller that verifies cash liquidity, matches multi-source records (OMS $\leftrightarrow$ Gateway $\leftrightarrow$ Bank), detects fee/refund variances, and resolves cryptic banking narrations using a bounded, cost-aware two-tier engine (DuckDB SQL + Gemini LLM).

---

## Open Questions (do not skip — answer before building)

> [!NOTE]
> 1. **Tie-breaking**: If two or more Tier-1 candidates both satisfy amount + date + narration conditions for one settlement, do we guess or escalate? **Decision: escalate.** Tier 1 never auto-picks between tied candidates — it routes the record into the Tier 2 pool instead. A wrong deterministic match is worse than an honest escalation.
> 2. **Leg 1 exception path**: OMS↔Gateway (`order_id`, 1:1) currently has no exception branch in the architecture. **Decision for this build: scope-cut.** Leg 1 is assumed clean 1:1 and out of scope; only Leg 2 (Gateway↔Bank) gets the full two-tier treatment. State this explicitly to judges rather than let the diagram imply otherwise.
> 3. **Multi-batch refund netting**: can one refund span multiple settlement batches? For v1, assume one refund nets against exactly one settlement batch. Flag as a known simplification.
> 4. **Confidence threshold justification**: 0.85 is currently asserted, not derived. Plan to report it as a tunable routing heuristic, not a calibrated probability — see Section 2.

---

## User Review Required

> [!IMPORTANT]
> **Key Architectural Enhancements & Adjustments:**
> 1. **Correct Pathing**: All components structured under the repository root (use a real git-trackable path, not an editor scratch/cache directory — this matters for how the repo looks when judges clone it).
> 2. **Financial Precision**: All SQL schemas and DuckDB calculations strictly enforce `DECIMAL(18,2)` on every monetary field, to prevent floating-point rounding discrepancies on fee calculations ($2\%$ MDR $+ 18\%$ GST) and tolerance matching ($\pm ₹1.00$).
> 3. **Structured GenAI SDK Integration**: Tier 2 Gemini calls explicitly enforce `google-genai` SDK with `response_mime_type="application/json"` and Pydantic schema validation (`ReconDecisionSchema`) to guarantee structured outputs and prevent hallucinations.
> 4. **Configurable Settlement Window**: DuckDB matching supports $T+0$ to $T+3$ clearing windows by default, configurable up to $T+5$ for extended holiday/weekend stacking (e.g. Friday capture + Monday public holiday).

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
│  - OUT OF SCOPE v1        │                     ┌───────────┴───────────┐
│    (assumed clean)        │                     ▼                       ▼
└───────────────────────────┘          ┌────────────────────┐   ┌───────────────────┐
                                       │ Tier 1: SQL Engine │   │ Unmatched Queue   │
                                       │ - Exact UTR token  │   └─────────┬─────────┘
                                       │ - Net Amount ±₹1   │             │
                                       │ - T+0 to T+5 Dates │             ▼
                                       │ - Ties -> escalate │   ┌───────────────────┐
                                       └─────────┬──────────┘   │ Candidate Filter  │
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

* **MDR Fee**: Standard $2.00\%$ of Gross Captured, computed as `DECIMAL(18,2)`.
* **GST on MDR**: $18.00\%$ applied to the fee ($0.36\%$ effective deduction), computed as `DECIMAL(18,2)`.
* **Cross-Cycle Deductions**: Refunds initiated for past orders are netted against current settlement batches (`rfnd_xxx`). A netted variance is only treated as explained if a documented `refund_id`/amount actually exists against that settlement — matching magnitude alone is not sufficient evidence (this is what separates the "Netting Variance" archetype from the "Unnotified Bank Fee" adversarial trap; see Section 3).

### B. Settlement Timing & Date Drift
* **Normal Cycle**: $T+1$ business days.
* **Weekend/Holiday Window**: Orders captured Friday–Sunday settle on Monday or Tuesday; if a public holiday stacks on top of a weekend, extend the window to $T+5$ rather than hard-coding $T+3$.
* **Matching Rule**: Bank credit date must satisfy `bank_date BETWEEN expected_credit_date AND expected_credit_date + INTERVAL '5 DAYS'` (configurable, default window $T+0$ to $T+3$).

---

## 2. Two-Tier Reconciliation Engine

### Tier 1: Deterministic Engine (DuckDB SQL)
Processes bulk volume at ₹0 token cost:
1. **Pre-aggregation**: Groups Gateway transactions by `settlement_id`, calculates `net_amount` using `DECIMAL(18,2)`, and extracts candidate `utr`.
2. **Deterministic Match Condition** (all three must hold):
   - `bank.credit_amount` matches `gateway.net_amount` within $\pm ₹1.00$ tolerance.
   - Bank `credit_date` falls within the $[T+0, T+5]$ clearing window.
   - Bank `raw_narration` contains the `utr` substring or settlement-linking token.
   - Flagged as `MATCHED_DETERMINISTIC`.
3. **Ties are never guessed**: if 2+ bank rows satisfy all three conditions for one settlement, route to Tier 2 instead of picking one.

### Tier 2: Bounded AI Investigator (Gemini via Structured JSON)
Activated only for records failing Tier 1:
1. **Candidate Retrieval**: SQL retrieves the top 3 closest Gateway settlement candidates based on net amount proximity and date proximity.
2. **Context Enrichment**: Includes any cross-cycle refund IDs, MDR adjustments, or dispute holds associated with each candidate — critically, whether a variance has a *documented* refund backing it, not just a plausible magnitude.
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
4. **Safety Guardrail**: If `confidence < 0.85`, or if multiple candidates are indistinguishable (score gap < threshold), the AI MUST output `"decision": "UNRESOLVED"`, routing the record to `EXCEPTION_HUMAN`. Report this confidence value to judges as a *routing heuristic*, not a calibrated probability — it's the model's self-report, not a statistically validated accuracy figure. The real accuracy number comes from `benchmark.py`'s measured confusion matrix, not from averaging confidence scores.

---

## 3. Synthetic Dataset & Programmatic Ground Truth

The synthetic generator produces 150 orders across 4 explicit archetypes with embedded ground-truth metadata. **The generator is written and frozen before any matching logic is tuned, and is not edited again to make downstream accuracy numbers look better** — this is what makes the eventual match-rate claims defensible rather than circular.

| Archetype | Share | Description | Ground Truth Label | Expected Engine |
| :--- | :--- | :--- | :--- | :--- |
| **Type 1: Clean Flow** | 70% (105 txns) | Clean UTR in narration, exact net settlement amount, T+1 credit date. | `MATCHED_DETERMINISTIC` | Tier 1 (SQL) |
| **Type 2: Cryptic Narration** | 15% (23 txns) | UTR truncated or nested in bank noise (`CMS-RZP-SETL-xxx`, `HDFC CMP RZP`), amount exact, date drifts to T+2/T+3. | `MATCHED_AI` | Tier 2 (AI) |
| **Type 3: Netting Variance** | 10% (15 txns) | Amount off by ₹500–₹3,000 due to a *documented* past refund or dispute hold; narration has partial (not full) reference. | `MATCHED_AI` | Tier 2 (AI) |
| **Type 4: Adversarial Traps** | 5% (7 txns) | Three concrete sub-traps: (a) twin duplicate amount+date with generic narration — genuinely ambiguous; (b) phantom bank credit with no gateway batch at all; (c) unnotified bank fee — a plausible-looking variance with *no* documented refund backing it, which must NOT be waved through just because the magnitude looks similar to Type 3. | `EXCEPTION_HUMAN` | Tier 2 $\to$ Unresolved |

---

## 4. Streamlit Controller Cockpit

Three specialized tabs:
1. **Executive Cash & Liquidity Dashboard**: Gross Captured Volume vs. Settled Bank Cash; Total MDR Fees & GST paid; Float/In-Transit Cash pending clearing.
2. **Programmatic Verification Matrix**: Total Processed, Deterministic Match Rate, AI Escalate Count, AI Match Rate, False Match Rate (report the *measured* value here — do not assert 0.00% as a target; see Verification Plan). Cost & Latency Benchmark: Pure LLM Cost vs. Two-Tier Cost Savings.
3. **Auditor Exception Workbench**: Categorized exception buckets (*Timing Differences*, *Fee/TDS Discrepancies*, *Phantom Credits*, *Low-Confidence Ambiguities*); AI Chain-of-Thought & evidence view; one-click manual approval/resolution with notes.

---

## Proposed Project Structure

```
<repo-root>/ReconAgent/
├── data/
│   ├── generator.py            # Generates synthetic OMS, Gateway, Bank CSVs with ground truth (frozen after first run)
│   └── ground_truth.json       # Ground truth registry for programmatic validation
├── db/
│   ├── duckdb_client.py        # Embedded DuckDB session, staging, FACT_STAGE aggregation
│   └── schema.sql              # RAW, FACT, and RECON tables — DECIMAL(18,2) throughout
├── engine/
│   ├── tier1_sql.py            # Deterministic join, tie-detection, Top-3 candidate retriever
│   ├── tier2_ai.py             # Bounded Gemini investigator, Pydantic JSON schema, confidence floor
│   └── controller.py           # Orchestrator: Leg 2 Tier 1 -> Tier 2 -> RECON_LEDGER
├── app/
│   └── streamlit_app.py        # Interactive 3-tab controller cockpit
├── eval/
│   └── benchmark.py            # Confusion matrix, per-archetype accuracy, honest exception list
├── tests/
│   └── test_reconciliation.py  # Fee precision, netting formula, date windows, no-false-positive invariant
├── README.md                   # Architecture doc + honest status + judge Q&A prep
└── requirements.txt            # duckdb, streamlit, pydantic, google-genai, pandas, pytest
```

---

## Verification Plan

### Automated Tests
- `pytest tests/`: deterministic matching, netting formula, date window logic, and the hard invariant that Tier 1 never auto-matches a ground-truth exception.
- `python eval/benchmark.py`: full end-to-end evaluation against ground truth, producing a per-archetype confusion matrix — this table *is* the "honest exception list" artifact for judges, not just an aggregate percentage.
  - **Tier 1 Match Rate**: report both order-level and batch-level percentages (they differ — batch composition varies by archetype).
  - **Tier 2 Precision**: measured, not asserted. If the stub scorer is used for pipeline testing before real Gemini access is available, label it explicitly as a stub result and re-run with live Gemini before presenting a Tier-2 accuracy number to judges.
  - **False Positive / Hallucination Rate**: report the measured value, whatever it is — a suspiciously perfect 0.0% target reads as unbelievable to judges reviewing a hackathon plan; an honest 2-5% (or a true 0% backed by the invariant test) is more credible either way.

### Manual Verification
- Launch Streamlit UI: `streamlit run app/streamlit_app.py`.
- Verify live execution of Leg 2 reconciliation runs.
- Inspect AI reasoning modals and test human-in-the-loop override actions.

---

## Build Order (time-boxed priority)
1. Generator + ground truth (frozen once correct)
2. Schema + DuckDB client + FACT_STAGE
3. Tier 1 SQL matcher — get a real measured match rate
4. `benchmark.py` with per-archetype confusion matrix
5. Tier 2 AI layer (real Gemini call)
6. Streamlit cockpit (polish — only after the numbers are real)
