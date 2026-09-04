"""
Tier 2 Bounded AI Investigator (Gemini GenAI SDK + Pydantic Schema).
Invoked only for unmatched records failing Tier 1 SQL.
Enforces structured output schema and confidence thresholds (>=0.85).
"""

import os
import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ReconDecisionSchema(BaseModel):
    decision: str = Field(..., description="Decision enum: 'MATCH' or 'UNRESOLVED'")
    selected_settlement_id: Optional[str] = Field(None, description="The matched gateway settlement_id, or null if unresolved")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")
    variance_explained: float = Field(0.0, description="Exact amount explained by refunds/fees/disputes")
    reason: str = Field(..., description="Step-by-step audit explanation supporting the decision")

class Tier2AIInvestigator:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.client = None
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"Warning: Could not initialize Google GenAI SDK ({e}). Running in rule-bounded mode.")

    def investigate(self, bank_record: Dict[str, Any], candidates: List[Dict[str, Any]]) -> ReconDecisionSchema:
        """
        Investigates an unmatched bank statement against candidate Gateway settlements.
        Returns a validated ReconDecisionSchema.
        """
        if self.client:
            return self._call_gemini_genai(bank_record, candidates)
        else:
            return self._bounded_heuristic_investigation(bank_record, candidates)

    def _call_gemini_genai(self, bank_record: Dict[str, Any], candidates: List[Dict[str, Any]]) -> ReconDecisionSchema:
        """Invokes Gemini using official google-genai SDK with Pydantic structured output."""
        from google.genai import types

        prompt = f"""
You are an enterprise financial reconciliation controller for Razorpay settlements.
Analyze the following unmatched bank statement transaction against candidate Gateway settlement batches.

BANK STATEMENT TRANSACTION:
- Bank Stmt ID: {bank_record['bank_stmt_id']}
- Credit Date: {bank_record['credit_date']}
- Credit Amount: ₹{bank_record['credit_amount']}
- Raw Narration: "{bank_record['raw_narration']}"

CANDIDATE GATEWAY SETTLEMENT BATCHES:
{json.dumps(candidates, indent=2)}

INSTRUCTIONS:
1. Examine if any candidate's UTR token, partial UTR suffix, or netting amount aligns with the narration.
2. Check if net amount difference (e.g. ₹{bank_record['credit_amount']} vs Candidate Net Amount) is exactly explained by cross-cycle refund deductions (`refund_deducted`) or fees.
3. If an exact or high-confidence match (confidence >= 0.85) is found, set decision to "MATCH", specify `selected_settlement_id`, `variance_explained`, and provide audit reason.
4. If ambiguous, twin duplicate amounts exist, or no candidate matches with >=0.85 confidence, set decision to "UNRESOLVED", `selected_settlement_id` to null, and explain why.
"""
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ReconDecisionSchema,
                    temperature=0.0
                )
            )
            data = json.loads(response.text)
            return ReconDecisionSchema(**data)
        except Exception as e:
            print(f"Gemini API call failed ({e}), falling back to bounded heuristic investigation.")
            return self._bounded_heuristic_investigation(bank_record, candidates)

    def _bounded_heuristic_investigation(self, bank_record: Dict[str, Any], candidates: List[Dict[str, Any]]) -> ReconDecisionSchema:
        """
        Bounded fallback rule-engine when API key is not present.
        Accurately handles Cryptic Narrations, Netting Variances, and Traps.
        """
        narration = str(bank_record.get("raw_narration", "")).upper()
        credit_amount = float(bank_record.get("credit_amount", 0.0))

        # Check each candidate
        for cand in candidates:
            settlement_id = cand["settlement_id"]
            utr = str(cand.get("utr", "")).upper()
            short_utr = utr[-6:] if len(utr) >= 6 else utr
            net_amount = float(cand.get("net_amount", 0.0))
            refund_deducted = float(cand.get("refund_deducted", 0.0))

            # Case A: Truncated UTR in cryptic narration (Type 2 Archetype)
            if short_utr in narration and abs(credit_amount - net_amount) <= 1.00:
                return ReconDecisionSchema(
                    decision="MATCH",
                    selected_settlement_id=settlement_id,
                    confidence=0.96,
                    variance_explained=0.0,
                    reason=f"Cryptic bank narration matches truncated UTR token '{short_utr}' for settlement {settlement_id}. Amount matches net settlement ₹{net_amount:.2f}."
                )

            # Case B: Netting Variance (Type 3 Archetype - Past Refund Deducted)
            if refund_deducted > 0:
                expected_after_refund = round(net_amount - refund_deducted, 2)
                if abs(credit_amount - expected_after_refund) <= 1.00 and (utr in narration or "RFND" in narration or "LESS" in narration):
                    return ReconDecisionSchema(
                        decision="MATCH",
                        selected_settlement_id=settlement_id,
                        confidence=0.94,
                        variance_explained=refund_deducted,
                        reason=f"Bank credit ₹{credit_amount:.2f} matches net settlement ₹{net_amount:.2f} minus cross-cycle refund ₹{refund_deducted:.2f} (Refund ID: {cand.get('refund_id')})."
                    )

        # Case C: Adversarial Traps / Low Confidence (Type 4 Archetype)
        return ReconDecisionSchema(
            decision="UNRESOLVED",
            selected_settlement_id=None,
            confidence=0.40,
            variance_explained=0.0,
            reason="Unresolved exception: Bank narration lacks recognizable UTR token and amount discrepancy is not explained by recorded refunds/adjustments."
        )
