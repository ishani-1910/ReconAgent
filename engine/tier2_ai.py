"""
Tier 2 Bounded AI Investigator (Gemini 2.5 Flash GenAI SDK) & Tier 1.5 Rule Engine.
Invoked only for unmatched records failing Tier 1 SQL.

Features:
  - Genuine Gemini 2.5 Flash calls when GEMINI_API_KEY is configured in .env or environment.
  - Live token tracking (prompt_tokens, candidates_tokens, total_tokens).
  - Live latency tracking (milliseconds).
  - Transparent Tier 1.5 Rule Fallback when offline (strictly labeled as rule-based, 0 tokens, no fake confidence).
"""

import os
import json
import time
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Automatically load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class ReconDecisionSchema(BaseModel):
    decision: str = Field(..., description="Decision enum: 'MATCH' or 'UNRESOLVED'")
    selected_settlement_id: Optional[str] = Field(None, description="The matched gateway settlement_id, or null if unresolved")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")
    variance_explained: float = Field(0.0, description="Exact amount explained by refunds/fees/disputes")
    reason: str = Field(..., description="Step-by-step audit explanation supporting the decision")
    recon_tier: str = Field("TIER_2_AI", description="TIER_2_AI or TIER_1_5_RULE")
    tokens_used: int = Field(0, description="Total tokens consumed by LLM")
    latency_ms: int = Field(0, description="Execution latency in milliseconds")

class Tier2AIInvestigator:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.client = None
        self.total_tokens_spent = 0
        self.total_api_calls = 0
        self.quota_exhausted = False

        if self.api_key and self.api_key.strip():
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key.strip())
            except Exception as e:
                print(f"Warning: Could not initialize Google GenAI SDK ({e}). Running in transparent Rule Engine mode.")

    @property
    def is_live_ai_active(self) -> bool:
        return self.total_api_calls > 0 and self.total_tokens_spent > 0

    def investigate(self, bank_record: Dict[str, Any], candidates: List[Dict[str, Any]]) -> ReconDecisionSchema:
        """
        Investigates an unmatched bank statement against candidate Gateway settlements.
        Calls live Gemini if API key is configured and quota available, otherwise invokes transparent Tier 1.5 Rule Engine.
        """
        if self.client and not self.quota_exhausted:
            return self._call_gemini_genai(bank_record, candidates)
        else:
            reason = "Free Tier API Quota Limit Reached" if self.quota_exhausted else None
            return self._tier1_5_rule_investigation(bank_record, candidates, fallback_reason=reason)

    def _call_gemini_genai(self, bank_record: Dict[str, Any], candidates: List[Dict[str, Any]]) -> ReconDecisionSchema:
        """Invokes Gemini using official google-genai SDK with structured Pydantic schema validation."""
        from google.genai import types

        start_time = time.perf_counter()

        prompt = f"""
You are an enterprise financial reconciliation controller for Razorpay settlements.
Analyze the following unmatched bank statement transaction against candidate Gateway settlement batches.

BANK STATEMENT TRANSACTION:
- Bank Stmt ID: {bank_record['bank_stmt_id']}
- Credit Date: {bank_record['credit_date']}
- Credit Amount: ₹{bank_record['credit_amount']}
- Raw Narration: "{bank_record['raw_narration']}"

CANDIDATE GATEWAY SETTLEMENT BATCHES:
{json.dumps(candidates, indent=2, default=str)}

INSTRUCTIONS:
1. Check if any candidate's UTR token, partial UTR suffix, or netting amount aligns with the bank narration.
2. Check if net amount difference (₹{bank_record['credit_amount']} vs Candidate Net Amount) is exactly explained by cross-cycle refund deductions (`refund_deducted`) or fees.
3. If an exact or high-confidence match (confidence >= 0.85) is found:
   - set `decision` to "MATCH"
   - specify `selected_settlement_id`
   - set `variance_explained` (e.g. refund amount if deducted)
   - provide step-by-step audit reasoning
4. If ambiguous, twin duplicate amounts exist, or no candidate matches with >=0.85 confidence:
   - set `decision` to "UNRESOLVED"
   - set `selected_settlement_id` to null
   - set `confidence` to actual estimated score (< 0.85)
   - explain why it requires human escalation
"""
        models_to_try = ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
        last_error = None

        for model_name in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ReconDecisionSchema,
                        temperature=0.0
                    )
                )
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                tokens = 0
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    tokens = response.usage_metadata.total_token_count or 0

                self.total_tokens_spent += tokens
                self.total_api_calls += 1

                data = json.loads(response.text)
                decision = ReconDecisionSchema(**data)
                decision.recon_tier = "TIER_2_AI"
                decision.tokens_used = tokens
                decision.latency_ms = elapsed_ms
                resp_str = response.text.strip().encode("ascii", errors="backslashreplace").decode("ascii")
                print(f"\n[Gemini Live Response - Model: {model_name}] Bank Stmt: {bank_record.get('bank_stmt_id')} | Tokens: {tokens} | Latency: {elapsed_ms}ms")
                print(f"Decoded Response: {resp_str}\n")
                return decision

            except Exception as e:
                logger.error(f"Gemini API call failed for model {model_name}: {type(e).__name__}: {e}", exc_info=True)
                last_error = e
                # Try next model if model unavailable (404/503) or rate-limited
                continue

        if last_error and ("429" in str(last_error) or "quota" in str(last_error).lower() or "resource_exhausted" in str(last_error).lower()):
            self.quota_exhausted = True
            print("Notice: Gemini API Free Tier quota limit reached. Automatically transitioning batch to Tier 1.5 Rule Engine.")
            return self._tier1_5_rule_investigation(bank_record, candidates, fallback_reason="Free Tier Daily Quota Limit Reached")

        print(f"Gemini API call failed ({last_error}). Falling back to transparent Tier 1.5 Rule Engine.")
        return self._tier1_5_rule_investigation(bank_record, candidates, fallback_reason=str(last_error))

    def _tier1_5_rule_investigation(
        self,
        bank_record: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        fallback_reason: Optional[str] = None
    ) -> ReconDecisionSchema:
        """
        Transparent Tier 1.5 Deterministic Rule Fallback.
        No fake AI confidence; clearly records rule execution, 0 tokens spent.
        """
        narration = str(bank_record.get("raw_narration", "")).upper()
        credit_amount = float(bank_record.get("credit_amount", 0.0))

        env_note = " [Offline Mode: No GEMINI_API_KEY configured in .env]" if not fallback_reason else f" [Fallback: API Error ({fallback_reason})]"

        for cand in candidates:
            settlement_id = cand["settlement_id"]
            utr = str(cand.get("utr", "")).upper()
            short_utr = utr[-6:] if len(utr) >= 6 else utr
            net_amount = float(cand.get("net_amount", 0.0))
            refund_deducted = float(cand.get("refund_deducted", 0.0))

            # Case A: Truncated UTR substring pattern
            if short_utr in narration and abs(credit_amount - net_amount) <= 1.00:
                return ReconDecisionSchema(
                    decision="MATCH",
                    selected_settlement_id=settlement_id,
                    confidence=1.0,
                    variance_explained=0.0,
                    reason=f"Matched via Tier 1.5 Rule: Truncated UTR suffix '{short_utr}' found in narration. Amount ₹{net_amount:.2f} matches net settlement.{env_note}",
                    recon_tier="TIER_1_5_RULE",
                    tokens_used=0,
                    latency_ms=0
                )

            # Case B: Documented refund netting variance
            if refund_deducted > 0:
                expected_after_refund = round(net_amount - refund_deducted, 2)
                if abs(credit_amount - expected_after_refund) <= 1.00 and (utr in narration or "RFND" in narration or "LESS" in narration):
                    return ReconDecisionSchema(
                        decision="MATCH",
                        selected_settlement_id=settlement_id,
                        confidence=1.0,
                        variance_explained=refund_deducted,
                        reason=f"Matched via Tier 1.5 Rule: Bank credit ₹{credit_amount:.2f} equals settlement ₹{net_amount:.2f} minus verified refund ₹{refund_deducted:.2f} (Refund ID: {cand.get('refund_id')}).{env_note}",
                        recon_tier="TIER_1_5_RULE",
                        tokens_used=0,
                        latency_ms=0
                    )

        # Case C: Unresolved Exception
        return ReconDecisionSchema(
            decision="UNRESOLVED",
            selected_settlement_id=None,
            confidence=0.0,
            variance_explained=0.0,
            reason=f"Unresolved exception: No candidate matches UTR token or verified refund adjustments.{env_note}",
            recon_tier="TIER_1_5_RULE",
            tokens_used=0,
            latency_ms=0
        )
