# ReconAgent: 3-Way Bounded Financial Controller & Settlement Engine

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/OLAP-DuckDB-yellow.svg)](https://duckdb.org/)
[![Gemini GenAI](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-green.svg)](https://ai.google.dev/)
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A bounded, cost-aware financial reconciliation controller that verifies cash liquidity and matches multi-source records (OMS ↔ Gateway ↔ Bank) using a two-tier engine — free deterministic SQL first, a confidence-gated Gemini investigator only for genuine exceptions. It detects fee and refund variances automatically, and for cryptic banking narrations it resolves what it can and honestly escalates what it can't to a human auditor.

**OPEN THE PROJECT HERE:** https://reconagent-ai.streamlit.app/

---

## Key Highlights & Innovations

**1. True Commercial Recon (Leg 1: OMS ↔ Gateway)**
- Performs a true 1:1 join between OMS orders and Gateway payment captures on `order_id`.
- Recomputes contract MDR fees dynamically:
  - UPI: 0.00%
  - Debit Card: 0.90%
  - Credit Card: 2.00%
  - Netbanking: 1.80%
  - GST: 18.00% on MDR
  - High-Risk Reserve Holdback: 10.00% dispute reserve
- Flags payment status discrepancies (`OMS COMPLETED` vs `Gateway FAILED/REFUNDED`) and overcharged fee leakages.

**2. Domain Precision (Indian Net Settlement Formula)**
- Accurately models real-world payment gateway netting: `Net Settlement = Σ(Gross) − MDR − GST − Holdback − Refunds ± Adjustments`
- Enforces exact `DECIMAL(18,2)` arithmetic across all DuckDB tables, preventing floating-point rounding errors.

**3. Estimated 85%+ Token Cost Reduction (Multi-Tier Architecture)**
- Tier 1 (DuckDB SQL) processes clean records at ₹0 token cost.
- Tier 2 (Gemini 2.5 Flash GenAI) is only invoked for cryptic narrations, truncated UTRs, and fee/refund variances.
- Tier 1.5 (Deterministic Rule Engine) provides a transparent fallback whenever live inference is unavailable — no API key configured, a network failure, or an exhausted quota — so the pipeline always completes and clearly labels which engine resolved each record.
- The 85%+ figure is an estimate versus routing every record through the LLM directly; it has not been benchmarked against a full-LLM baseline run.

**4. Confidence-Gated Guardrail & Audit Trail (0 False Positives in Testing)**
- Enforces structured Pydantic schema validation (`response_mime_type="application/json"`).
- If AI confidence is `< 0.85` or duplicate ambiguity exists (e.g. twin amounts, phantom bank credits), the engine sets `"decision": "UNRESOLVED"` and routes to `EXCEPTION_HUMAN`.
- Stores real tokens consumed and execution latency in `recon_ledger` for every decision, AI or rule-based.
- In our most recent benchmark run: 0 false positives across 150 records.

**5. Security & Persistence**
- All DuckDB queries use strictly parameterized queries (`?` placeholders) — no raw string interpolation.
- Database is persistent on disk (`data/recon_agent.duckdb`), with a version-controlled golden reference snapshot (`data/golden_recon_agent.duckdb`) ensuring reproducible, instant-load state on fresh deployments.

---

## Known Limitations

- Tier 2 investigates only the top-3 SQL-ranked candidates per record — this is a deliberate bound for cost and latency predictability, not open-ended agentic search.
- Reported accuracy may vary by ±1–2 records on a fresh live run due to normal LLM sampling variance, even at `temperature=0.0`.
- Free-tier Gemini rate limits (15 RPM) mean a full live Tier 2 escalation batch (~45 records) takes roughly 3–4 minutes end-to-end.

---

## Quick Start

**1. Installation**
```bash
pip install -r requirements.txt
```

**2. Configure Gemini API Key (optional, for live GenAI)**

Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_gemini_api_key_here
```
If no key is configured, the system automatically and transparently operates in Tier 1.5 Rule Fallback mode.

**3. (Optional) Generate a fresh synthetic dataset**
```bash
python -u data/generator.py
```
⚠️ This overwrites the sample data and regenerates a new random dataset — the golden benchmark results referenced in this README were computed on the committed dataset. Skip this step if you just want to explore the existing verified results.

**4. Run automated tests**
```bash
pytest tests/ -v
```

**5. Run accuracy & telemetry benchmark**
```bash
python -u eval/benchmark.py
```
⚠️ If a `GEMINI_API_KEY` is configured, this triggers live Tier 2 calls and takes ~3–4 minutes on the free tier, consuming API quota.

**6. Launch the Streamlit Controller Cockpit**
```bash
streamlit run app/streamlit_app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser. The app loads instantly from the committed golden dataset — no live run required to see results.

---

**For detailed architectural design, schema definitions, and test methodology, see [DOCUMENTATION.md](./DOCUMENTATION.md).**
