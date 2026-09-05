"""
Restores live data/recon_agent.duckdb from the verified data/golden_recon_agent.duckdb reference.
Guarantees clean baseline state before demos, submission, or CI tests.
"""
import os
import sys
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
GOLDEN_PATH = os.path.join(DATA_DIR, "golden_recon_agent.duckdb")
LIVE_PATH = os.path.join(DATA_DIR, "recon_agent.duckdb")

def restore():
    if not os.path.exists(GOLDEN_PATH):
        print(f"Error: Golden reference file not found at {GOLDEN_PATH}")
        sys.exit(1)

    shutil.copyfile(GOLDEN_PATH, LIVE_PATH)
    print(f"Success: Restored live database from golden baseline.")
    print(f"  Source: {GOLDEN_PATH} ({os.path.getsize(GOLDEN_PATH):,} bytes)")
    print(f"  Target: {LIVE_PATH} ({os.path.getsize(LIVE_PATH):,} bytes)")

if __name__ == "__main__":
    restore()
