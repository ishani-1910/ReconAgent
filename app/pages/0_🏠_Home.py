"""
ReconAgent | Executive Landing Page & Governance Overview.
Sets business context, introduces the 3-way reconciliation problem, 
and highlights the architectural governance guardrails before entering the live cockpit.
"""

import os
import sys
import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

st.set_page_config(
    page_title="Home | ReconAgent",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "app_view" not in st.session_state:
    st.session_state.app_view = "Home"

# Custom Styling (Fintech Dark Theme & Glassmorphism, Sidebar Hidden on Home)
st.markdown("""
<style>
    /* Hide sidebar on home landing page */
    [data-testid="stSidebar"] {
        display: none !important;
    }
    [data-testid="collapsedControl"] {
        display: none !important;
    }

    .hero-title {
        font-size: 3.4rem;
        font-weight: 850;
        background: linear-gradient(135deg, #00C9FF 0%, #92FE9D 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.3rem;
        letter-spacing: -0.02em;
    }
    .pitch-card-box {
        width: 100%;
        max-width: 100%;
        margin: 1.8rem 0 2.2rem 0;
        background: linear-gradient(180deg, rgba(26, 32, 44, 0.9) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid rgba(0, 201, 255, 0.35);
        border-radius: 14px;
        padding: 2.2rem 2.8rem;
        box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }
    .gov-card-box {
        background: rgba(30, 41, 59, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1.4rem;
        height: 100%;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .gov-card-box:hover {
        border-color: rgba(0, 201, 255, 0.4);
        transform: translateY(-2px);
    }

    /* High-Impact Cyan/Emerald Fintech CTA Button */
    div[data-testid="stButton"] > button[kind="primary"],
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #00C9FF 0%, #92FE9D 100%) !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.75rem 2.5rem !important;
        box-shadow: 0 4px 20px rgba(0, 201, 255, 0.45) !important;
        transition: all 0.25s ease-in-out !important;
    }
    div[data-testid="stButton"] > button[kind="primary"] *,
    div.stButton > button[kind="primary"] * {
        color: #0A192F !important;
        font-size: 1.25rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.01em !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover,
    div.stButton > button[kind="primary"]:hover {
        transform: translateY(-2px) scale(1.02) !important;
        box-shadow: 0 8px 25px rgba(0, 201, 255, 0.65), 0 0 18px rgba(146, 254, 157, 0.55) !important;
        background: linear-gradient(135deg, #38BDF8 0%, #68D391 100%) !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover * {
        color: #06101E !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:active,
    div.stButton > button[kind="primary"]:active {
        transform: translateY(1px) scale(0.99) !important;
    }
</style>
""", unsafe_allow_html=True)

# Hero Header & Subtitle
st.markdown("""
<div style="text-align: center; max-width: 1050px; margin: 0 auto; padding-top: 0.5rem;">
    <div style="display: inline-block; padding: 4px 16px; background: rgba(0, 201, 255, 0.12); border: 1px solid rgba(0, 201, 255, 0.35); border-radius: 20px; color: #00C9FF; font-size: 0.8rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.9rem;">
        Autonomous Financial Controller
    </div>
    <div class="hero-title">ReconAgent</div>
    <p style="color: #94A3B8; font-size: 1.2rem; font-weight: 500; margin-bottom: 1.4rem;">
        3-Way Bounded Financial Controller (OMS ↔ Gateway ↔ Bank OLAP)
    </p>
    <div style="display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; margin-bottom: 1.8rem;">
        <span style="background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(99, 179, 237, 0.3); padding: 5px 14px; border-radius: 16px; font-size: 0.85rem; color: #63B3ED; font-weight: 500;">🔒 Zero PII Transmitted</span>
        <span style="background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(104, 211, 145, 0.3); padding: 5px 14px; border-radius: 16px; font-size: 0.85rem; color: #68D391; font-weight: 500;">⚡ Live Gemini 2.5 Flash</span>
        <span style="background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(246, 173, 85, 0.3); padding: 5px 14px; border-radius: 16px; font-size: 0.85rem; color: #F6AD55; font-weight: 500;">📐 DECIMAL(18,2) Exact Math</span>
        <span style="background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(183, 148, 244, 0.3); padding: 5px 14px; border-radius: 16px; font-size: 0.85rem; color: #B794F4; font-weight: 500;">🎯 99.3% Ground-Truth Accuracy</span>
        <span style="background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(226, 232, 240, 0.2); padding: 5px 14px; border-radius: 16px; font-size: 0.85rem; color: #E2E8F0; font-weight: 500;">🛡️ Propose, Never Post</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Prominent Centered Call-to-Action Button (Placed ABOVE description box)
col_l, col_m, col_r = st.columns([1.1, 1.8, 1.1])
with col_m:
    if st.button("→ Open Dashboard", type="primary", use_container_width=True, key="home_page_center_btn"):
        st.session_state.app_view = "Dashboard"
        try:
            st.switch_page("streamlit_app.py")
        except Exception:
            try:
                st.switch_page("app/streamlit_app.py")
            except Exception:
                st.info("Please navigate to the dashboard from the menu.")

# Pitch Box with exact user text (Full container width)
st.markdown("""
<div class="pitch-card-box">
    <p style="font-size: 1.25rem; font-weight: 700; color: #F8FAFC; line-height: 1.55; margin-bottom: 1.1rem; border-left: 4px solid #00C9FF; padding-left: 1rem;">
        A 3-way bounded financial controller that closes the reconciliation loop — and tells you exactly what it couldn't.
    </p>
    <p style="color: #CBD5E1; font-size: 1.02rem; line-height: 1.75; margin-bottom: 0.9rem;">
        Every day, a high-growth D2C merchant's money moves through three systems that don't talk to each other: 
        the <strong>order management system (OMS)</strong>, the <strong>payment gateway (Razorpay)</strong>, and the <strong>bank statement (Cash OLAP)</strong>. 
        Someone on a finance team spends hours manually tracing each rupee across all three — matching UTRs, chasing refund netting, 
        and explaining why a settlement batch is short.
    </p>
    <p style="color: #CBD5E1; font-size: 1.02rem; line-height: 1.75; margin-bottom: 0;">
        ReconAgent automates that loop end-to-end, and — <em>this is the part most reconciliation demos skip</em> — 
        <strong style="color: #38BDF8;">it never pretends to be more certain than it is</strong>.
    </p>
</div>
""", unsafe_allow_html=True)

# Section Divider & Governance Note
st.markdown("---")
st.markdown("""
<div style="text-align: center; margin: 2.2rem 0 1.6rem 0;">
    <h3 style="font-size: 1.55rem; font-weight: 700; color: #F8FAFC; margin-bottom: 0.35rem;">
        🛡️ Why Trust External AI in Finance? (Security & Governance)
    </h3>
    <p style="color: #94A3B8; font-size: 0.95rem;">
        How ReconAgent eliminates financial hallucinations and guarantees mathematical ledger integrity.
    </p>
</div>
""", unsafe_allow_html=True)

# 6 Governance Cards (Row 1)
g1, g2, g3 = st.columns(3)
with g1:
    st.markdown("""
    <div class="gov-card-box">
        <h4 style="color: #63B3ED; margin-bottom: 0.5rem;">🔒 1. Zero PII Ingestion</h4>
        <p style="color: #94A3B8; font-size: 0.92rem; line-height: 1.6; margin: 0;">
            No customer names, phone numbers, email addresses, or card PANs are ever sent to Gemini. 
            Only internal pseudo-identifiers, batch settlement amounts, and sanitized bank narration strings enter inference prompts.
        </p>
    </div>
    """, unsafe_allow_html=True)

with g2:
    st.markdown("""
    <div class="gov-card-box">
        <h4 style="color: #68D391; margin-bottom: 0.5rem;">🤖 2. Propose, Never Post</h4>
        <p style="color: #94A3B8; font-size: 0.92rem; line-height: 1.6; margin: 0;">
            The LLM acts strictly as an investigative intelligence layer. It proposes matches with structured rationales, 
            but cannot unilaterally alter account balances or commit transactions to general ledger without mathematical validation.
        </p>
    </div>
    """, unsafe_allow_html=True)

with g3:
    st.markdown("""
    <div class="gov-card-box">
        <h4 style="color: #F6AD55; margin-bottom: 0.5rem;">⚡ 3. Strict Confidence Gating (&lt;0.85)</h4>
        <p style="color: #94A3B8; font-size: 0.92rem; line-height: 1.6; margin: 0;">
            Every AI match must achieve a decision confidence score ≥ 0.85. 
            Any ambiguous narration, conflicting delta, or adversarial trap automatically bypasses auto-match and halts in the <strong>Human Auditor Review Queue</strong>.
        </p>
    </div>
    """, unsafe_allow_html=True)

st.write("")
# 6 Governance Cards (Row 2)
g4, g5, g6 = st.columns(3)
with g4:
    st.markdown("""
    <div class="gov-card-box">
        <h4 style="color: #B794F4; margin-bottom: 0.5rem;">📐 4. Exact DECIMAL(18,2) Math</h4>
        <p style="color: #94A3B8; font-size: 0.92rem; line-height: 1.6; margin: 0;">
            All commercial fee calculations (UPI 0%, Debit 0.9%, Credit 2.0%, Netbanking 1.8%), 18% GST, and 10% risk dispute holdbacks 
            are computed using DuckDB fixed-point math — eliminating IEEE-754 floating-point rounding discrepancies.
        </p>
    </div>
    """, unsafe_allow_html=True)

with g5:
    st.markdown("""
    <div class="gov-card-box">
        <h4 style="color: #FC8181; margin-bottom: 0.5rem;">🛡️ 5. Deterministic Rule Fallback</h4>
        <p style="color: #94A3B8; font-size: 0.92rem; line-height: 1.6; margin: 0;">
            If external Gemini API quotas are exhausted or network access is severed, the system gracefully operates in 
            100% deterministic Tier 1.5 rule mode with continuous uptime and zero financial disruption.
        </p>
    </div>
    """, unsafe_allow_html=True)

with g6:
    st.markdown("""
    <div class="gov-card-box">
        <h4 style="color: #E2E8F0; margin-bottom: 0.5rem;">⚖️ 6. 3-Way Closed Loop</h4>
        <p style="color: #94A3B8; font-size: 0.92rem; line-height: 1.6; margin: 0;">
            Links OMS orders ↔ Gateway settlements ↔ Bank statement credits. 
            Commercial fee leakages and cash float in transit are continuously bounded and audited under double-entry conservation laws.
        </p>
    </div>
    """, unsafe_allow_html=True)
