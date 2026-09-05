"""
Acceptance Test for Tab 3 Ground Truth & Segmented Accuracy Display.
Verifies:
1. Sidebar security & governance caption is present.
2. Ground-Truth Accuracy metric is computed and displayed.
3. Measured Accuracy vs Ground Truth alert/info card contains exact wording and metrics.
4. Segmented Accuracy by Transaction Archetype table contains all 4 archetypes.
5. BPO manual ops text includes "(illustrative industry range)".
"""
import os
import sys
sys.path.insert(0, os.path.abspath("."))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from streamlit.testing.v1 import AppTest

def test_tab3_ground_truth_and_segmented_accuracy():
    app_path = os.path.abspath("app/streamlit_app.py")
    at = AppTest.from_file(app_path, default_timeout=120)
    at.run()

    # 1. Verify Sidebar Governance Caption
    captions = [c.value for c in at.sidebar.caption]
    print("Sidebar captions:", captions)
    gov_caption_present = any("No PII sent to Gemini" in c and "AI proposes, never posts" in c for c in captions)
    assert gov_caption_present, "Expected security & governance caption in sidebar"

    # 2. Verify Ground-Truth Accuracy Metric
    metrics = {m.label: (m.value, m.delta) for m in at.metric}
    print("Metrics detected:", list(metrics.keys()))
    assert "Ground-Truth Accuracy" in metrics, "Expected 'Ground-Truth Accuracy' metric"
    gt_val, gt_delta = metrics["Ground-Truth Accuracy"]
    print(f"Ground-Truth Accuracy: {gt_val} (Delta: {gt_delta})")
    assert "%" in gt_val, f"Value {gt_val} should contain percentage"
    assert "Verified Matches" in gt_delta, f"Delta {gt_delta} should indicate verified matches"

    # 3. Verify Explicit Measured Accuracy vs Ground Truth Card
    info_boxes = [info.value for info in at.info]
    print("Info callout cards:", info_boxes)
    match_card = [msg for msg in info_boxes if "Measured Accuracy vs. Ground Truth" in msg]
    assert len(match_card) > 0, "Expected 'Measured Accuracy vs. Ground Truth' card"
    assert "matched verified ground truth" in match_card[0], "Card must contain verified ground truth match statement"
    assert "True Positives" in match_card[0]
    assert "True Negatives" in match_card[0]
    assert "0 False Positives" in match_card[0]

    # 4. Verify Segmented Accuracy Table Dataframe
    dataframes = [df.value for df in at.dataframe]
    # Find dataframe with Archetype column
    archetype_df = None
    for df in dataframes:
        if "Archetype" in df.columns:
            archetype_df = df
            break
    assert archetype_df is not None, "Expected Segmented Accuracy DataFrame in Tab 3"
    print("Segmented Accuracy Table:\n", archetype_df[["Archetype", "Volume", "Measured Accuracy"]])
    assert len(archetype_df) == 4, f"Expected 4 archetypes, found {len(archetype_df)}"
    assert any("Type 1: Clean Flow" in arch for arch in archetype_df["Archetype"])
    assert any("Type 2: Cryptic Narration" in arch for arch in archetype_df["Archetype"])
    assert any("Type 3: Netting Variance" in arch for arch in archetype_df["Archetype"])
    assert any("Type 4: Adversarial Traps" in arch for arch in archetype_df["Archetype"])

    # 5. Verify BPO Labeling
    text_elements = [t.value for t in at.markdown]
    all_text = " ".join(text_elements)
    assert "Estimated Manual Ops Equivalent (illustrative industry range)" in all_text, \
        "Expected updated BPO manual ops wording with illustrative industry range"

    print("\n--- ALL TAB 3 & GOVERNANCE CHECKS PASSED SUCCESSFULLY ---")

if __name__ == "__main__":
    test_tab3_ground_truth_and_segmented_accuracy()
