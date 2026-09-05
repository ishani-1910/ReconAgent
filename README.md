# Razorpay ReconAgent: 3-Way Bounded Financial Controller & Settlement Engine

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/OLAP-DuckDB-yellow.svg)](https://duckdb.org/)
[![Gemini GenAI](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-green.svg)](https://ai.google.dev/)
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A bounded, cost-aware financial reconciliation controller that verifies cash liquidity and matches multi-source records (OMS ↔ Gateway ↔ Bank) using a two-tier engine — free deterministic SQL first, a confidence-gated Gemini investigator only for genuine exceptions. It detects fee and refund variances automatically, and for cryptic banking narrations it resolves what it can and honestly escalates what it can't to a human auditor

OPEN THE PROJECT HERE : https://reconagent-ai.streamlit.app/

---

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

---
FOR DETAILED INFORMATION ABOUT THE ARCHITECTURAL DESGIN PLEASE READ THE DOCUMENTATION

