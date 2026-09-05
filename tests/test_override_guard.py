"""
Acceptance Test for Human Override Guard:
1. Select stmt_101 (MATCHED_DETERMINISTIC) -> override panel hidden, locked info message displayed.
2. Select stmt_102 (EXCEPTION_HUMAN) -> override panel visible, verdict is 'Select an Action...', notes textarea is empty.
3. Switch between different EXCEPTION_HUMAN records -> verify widgets reset cleanly.
"""
import os
import sys
sys.path.insert(0, os.path.abspath("."))
from streamlit.testing.v1 import AppTest
from db.duckdb_client import DuckDBClient, DEFAULT_DB_PATH

def test_human_override_guard():
    app_path = os.path.abspath("app/streamlit_app.py")
    at = AppTest.from_file(app_path, default_timeout=15)
    at.run()

    # Find the bank stmt selectbox
    sb = [s for s in at.selectbox if "Select Bank Stmt ID" in s.label][0]

    # TEST 1: stmt_101 (MATCHED_DETERMINISTIC)
    sb.select("stmt_101").run()

    info_msgs = [info.value for info in at.info]
    has_lock_info = any("Human override is locked" in msg for msg in info_msgs)
    commit_btns = [b for b in at.button if "Commit Auditor Decision" in b.label]

    print("\n--- TEST 1: stmt_101 (MATCHED_DETERMINISTIC) ---")
    print("Lock info displayed:", has_lock_info)
    print("Commit button present:", len(commit_btns) > 0)
    assert has_lock_info, "Expected lock info message for resolved record stmt_101"
    assert len(commit_btns) == 0, "Commit button should be hidden for resolved record stmt_101"

    # TEST 2: stmt_102 (EXCEPTION_HUMAN)
    sb.select("stmt_102").run()

    commit_btns = [b for b in at.button if "Commit Auditor Decision" in b.label]
    verdict_sbs = [s for s in at.selectbox if "Auditor Verdict Action" in s.label]
    notes_ta = [t for t in at.text_area if "Auditor Verification Rationale" in t.label]

    print("\n--- TEST 2: stmt_102 (EXCEPTION_HUMAN) ---")
    print("Commit button present for stmt_102:", len(commit_btns) > 0)
    print("Verdict dropdown value:", verdict_sbs[0].value if verdict_sbs else None)
    print("Rationale textarea value (should be empty):", repr(notes_ta[0].value) if notes_ta else None)

    assert len(commit_btns) == 1, "Commit button should be visible for EXCEPTION_HUMAN record"
    assert verdict_sbs[0].value == "Select an Action...", "Verdict should default to neutral 'Select an Action...'"
    assert notes_ta[0].value == "", "Rationale textarea should be clean/empty initially"

    # TEST 3: Switch between two different EXCEPTION_HUMAN records
    db = DuckDBClient(DEFAULT_DB_PATH)
    exceptions = [r[0] for r in db.conn.execute("SELECT bank_stmt_id FROM recon_ledger WHERE recon_status = 'EXCEPTION_HUMAN';").fetchall()]
    db.close()
    print("\n--- TEST 3: Switch between EXCEPTION_HUMAN records ---")
    print("Available EXCEPTION_HUMAN records:", exceptions[:3])

    rec1, rec2 = exceptions[0], exceptions[1]
    sb.select(rec1).run()
    ta1 = [t for t in at.text_area if "Auditor Verification Rationale" in t.label][0]
    vd1 = [s for s in at.selectbox if "Auditor Verdict Action" in s.label][0]
    print(f"Initial {rec1} -> Verdict: {vd1.value} | Rationale: {repr(ta1.value)}")
    
    # Enter custom text and verdict in rec1
    ta1.input("Custom notes entered for rec1")
    vd1.select("Confirm Disputed Exception / Fraud Trap").run()

    # Now switch to rec2
    sb.select(rec2).run()
    ta2 = [t for t in at.text_area if "Auditor Verification Rationale" in t.label][0]
    vd2 = [s for s in at.selectbox if "Auditor Verdict Action" in s.label][0]
    print(f"Switched to {rec2} -> Verdict: {vd2.value} | Rationale: {repr(ta2.value)}")

    assert vd2.value == "Select an Action...", f"rec2 verdict should reset to default, got {vd2.value}"
    assert ta2.value == "", f"rec2 rationale should reset to blank, got {repr(ta2.value)}"

    print("\n>>> ALL ACCEPTANCE TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    test_human_override_guard()
