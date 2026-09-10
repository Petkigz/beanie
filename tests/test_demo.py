"""The end-to-end demo is a deliverable: it must run clean and show the mechanisms."""

import subprocess
import sys


def test_demo_runs_and_shows_the_mechanisms():
    proc = subprocess.run(
        [sys.executable, "examples/demo_mind.py"],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    markers = [
        "=== demonstration (T1) ===",          # teach once, transfer
        "unmapped untouched: True",             # honesty: only what was taught
        "=== introspection (row 35) ===",       # self-model answers
        "not fully confident",                  # Q13 caveat
        "=== usefulness feedback (T13) ===",    # explicit rating
        "idle budget:",                         # row 21 investigation
        "candidate evidence:",                  # findings with content
        "reflex word budget after:",            # T13 policy adaptation
        "=== owner tone (§3.5 affect observations) ===",
        "You sound frustrated",                 # observation acted on
        "observations, not guesses",            # cited read-back
        "fresh mind performed the taught goal: success",  # Q15 transfer
        "unmapped .txt untouched: True",
    ]
    for marker in markers:
        assert marker in out, f"demo output lost: {marker}"
