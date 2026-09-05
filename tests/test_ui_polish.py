"""
Test suite to verify UI polish changes:
1. '→ Open Dashboard' button placed ABOVE the description card.
2. Button has custom cyan-emerald styling and increased font size in CSS.
3. Pitch card description box uses full container width (width: 100%).
4. Redundant '🏠 Back to Home' button removed from sidebar.
5. Landing page transitions cleanly to Dashboard mode upon clicking button.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def test_landing_page_source_structure():
    app_path = os.path.join(PROJECT_ROOT, "app", "streamlit_app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Verify button is above pitch card box in streamlit_app.py
    btn_pos = content.find('st.button("→ Open Dashboard"')
    pitch_card_pos = content.find('<div class="pitch-card-box">')
    assert btn_pos != -1, "Open Dashboard button not found in streamlit_app.py"
    assert pitch_card_pos != -1, "Pitch card box not found in streamlit_app.py"
    assert btn_pos < pitch_card_pos, (
        f"Expected Open Dashboard button (pos {btn_pos}) to be ABOVE pitch card box (pos {pitch_card_pos})"
    )

    # 2. Verify increased font size and color scheme styling
    assert "1.25rem" in content, "Font size 1.25rem not found in button styles"
    assert "linear-gradient(135deg, #00C9FF 0%, #92FE9D 100%)" in content, "Cyan/emerald gradient not found in button styles"
    assert "div[data-testid=\"stButton\"] > button[kind=\"primary\"]" in content, "Primary button CSS override not found"

    # 3. Verify full-width description card (no wasted space)
    assert "width: 100%;" in content, "width: 100% not found in pitch-card-box"
    assert "max-width: 100%;" in content, "max-width: 100% not found in pitch-card-box"
    assert "max-width: 880px;" not in content, "Outdated max-width: 880px constraint still present in pitch-card-box"

    # 4. Verify duplicate Back to Home button is REMOVED from sidebar
    assert "sidebar_back_to_home" not in content, "Duplicate sidebar_back_to_home button still found in sidebar"
    assert 'st.button("🏠 Back to Home"' not in content, "Duplicate '🏠 Back to Home' button still found in sidebar"

    print("[OK] All checks for app/streamlit_app.py PASSED!")

def test_multipage_home_structure():
    home_path = os.path.join(PROJECT_ROOT, "app", "pages", "0_🏠_Home.py")
    with open(home_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Verify button is above pitch card box in 0_🏠_Home.py
    btn_pos = content.find('st.button("→ Open Dashboard"')
    pitch_card_pos = content.find('<div class="pitch-card-box">')
    assert btn_pos != -1, "Open Dashboard button not found in 0_🏠_Home.py"
    assert pitch_card_pos != -1, "Pitch card box not found in 0_🏠_Home.py"
    assert btn_pos < pitch_card_pos, (
        f"Expected Open Dashboard button (pos {btn_pos}) to be ABOVE pitch card box (pos {pitch_card_pos})"
    )

    # 2. Verify styling
    assert "1.25rem" in content, "Font size 1.25rem not found in 0_🏠_Home.py"
    assert "linear-gradient(135deg, #00C9FF 0%, #92FE9D 100%)" in content, "Cyan/emerald gradient not found in 0_🏠_Home.py"

    # 3. Verify full width card
    assert "width: 100%;" in content, "width: 100% not found in pitch-card-box in 0_🏠_Home.py"
    assert "max-width: 880px;" not in content, "Outdated max-width: 880px constraint still present in 0_🏠_Home.py"

    # 4. Verify initial sidebar state is expanded
    assert 'initial_sidebar_state="expanded"' in content, "initial_sidebar_state should be expanded"

    print("[OK] All checks for app/pages/0_Home.py PASSED!")

def test_apptest_interaction():
    from streamlit.testing.v1 import AppTest

    # Launch app in default landing mode
    at = AppTest.from_file(os.path.join(PROJECT_ROOT, "app", "streamlit_app.py"), default_timeout=30)
    at.session_state["app_view"] = "Home"
    at.run()
    assert not at.exception, f"AppTest raised exception: {at.exception}"

    # On landing page, verify button exists
    assert len(at.button) >= 1, "Expected at least 1 button on page"
    cta_btn = at.button(key="landing_open_dash_btn")
    assert cta_btn.label == "→ Open Dashboard", f"Unexpected button label: {cta_btn.label}"

    # Click CTA button to open dashboard
    cta_btn.click().run()
    assert not at.exception, f"AppTest raised exception after click: {at.exception}"
    assert at.session_state["app_view"] == "Dashboard", f"App view not updated to Dashboard: {at.session_state.get('app_view')}"

    # In Dashboard view, verify sidebar controls exist
    sidebar_runs = [b for b in at.sidebar.button if "Run Full Reconciliation" in b.label]
    assert len(sidebar_runs) == 1, "Run reconciliation button should be present in sidebar"

    # Verify NO 'Back to Home' button in sidebar
    back_home_btns = [b for b in at.sidebar.button if "Back to Home" in b.label]
    assert len(back_home_btns) == 0, "Redundant Back to Home button should NOT be in sidebar"

    print("[OK] AppTest interaction & transition to Dashboard PASSED!")

if __name__ == "__main__":
    test_landing_page_source_structure()
    test_multipage_home_structure()
    test_apptest_interaction()
    print("\nALL UI POLISH CHECKS VERIFIED SUCCESSFULLY!")
