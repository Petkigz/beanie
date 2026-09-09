"""End-to-end demo of the built mind (stages 0–4 mechanisms, T1/T2/T9/T10).

Run:  .venv/bin/python examples/demo_mind.py
State lives in a temp dir that is printed; rerun to watch continuity.
Uses authority="allow" so the demo can act in its own sandbox body — the
default policy for a real owner is "ask" (ARCHITECTURE §5).
"""

from __future__ import annotations

import pathlib
import tempfile

from beanie import Mind
from beanie.learning import DemoAction

STATE = pathlib.Path(tempfile.mkdtemp(prefix="beanie-demo-"))
mind = Mind(state_dir=STATE, authority="allow")


def say(text: str) -> None:
    reply = mind.step(text)
    print(f"  you: {text}")
    for reminder in reply.reminders:
        print(f"   🔔 reminder: {reminder}")
    print(f"  [{reply.confidence_label}] beanie: {reply.text}")
    if reply.questions:
        for question in reply.questions:
            print(f"   ? {question}")


print("=== Beanie mind demo ===")
print(f"state dir: {STATE}\n")

# 1. conversation + honesty contract (labels, ambiguity refusal)
say("hello beanie, good morning")
say("make a decision that is ambiguous")
say("explain your last answer")  # T10

# 2. commanded memory + contradiction handling (T2)
say("remember that server_a is in london")
say("remember that server_a is in berlin")

# 3. prospective memory (§3.7)
say("remind me in 3 turns to stretch")
say("what is the weather like")
say("tell me a fun fact")

# 4. teach by demonstration → propose rule → confirm (T1)
files = {"downloads/invoice.pdf": "x", "downloads/photo.jpg": "y", "downloads/notes.txt": "z"}
for path, text in files.items():
    mind.body.run("write_file", {"path": path, "text": text})
for directory in ("docs", "images"):
    mind.body.run("mkdir", {"dir": directory})

print("\n=== demonstration (T1) ===")
print("  you demonstrate: move invoice.pdf → docs/, photo.jpg → images/")
proposal = mind.demonstrate(
    title="organize downloads by type",
    goal_class="organize downloads",
    actions=[
        DemoAction("move_file", {"src": "downloads/invoice.pdf", "dst": "docs"}),
        DemoAction("move_file", {"src": "downloads/photo.jpg", "dst": "images"}),
    ],
)
print(f"  beanie asks: {proposal.confirm_question}")
mind.confirm_skill(proposal.skill_id)
print("  you: yes")

# 5. perform in a NEW context — transfer
new_files = {"new/report.pdf": "r", "new/pic.jpg": "p", "new/meme.png": "m"}
for path, text in new_files.items():
    mind.body.run("write_file", {"path": path, "text": text})
for directory in ("docs", "images"):
    mind.body.run("mkdir", {"dir": directory})
print("\n  you: organize the 'new' folder too")
result = mind.perform_goal("organize downloads", base_dir="new")
print(f"  plan outcome: {result.outcome} (repairs: {result.repairs})")
tree = mind.body.run("snapshot")["tree"]
print(f"  docs/   has: {sorted(k for k in tree if k.startswith('docs/'))}")
print(f"  images/ has: {sorted(k for k in tree if k.startswith('images/'))}")
print(f"  unmapped untouched: {'new/meme.png' in tree}")

# 6. correction → strategy revision (T9)
print("\n=== correction (T9) ===")
say("no, jpg files go into photos/")

# 7. prospective memory fires
print("\n=== reminders fire ===")
say("ok back to work")

print("\ndemo complete — the mind persists at:", STATE)
