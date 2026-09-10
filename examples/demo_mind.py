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
new_files = {"new/report.pdf": "r", "new/pic.jpg": "p", "new/meme.png": "m", "new/theme.mp3": "s"}
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
print(f"  .png never demonstrated, inferred by analogy: {'images/meme.png' in tree}")
print(f"  unmapped category untouched: {'new/theme.mp3' in tree}")

# 6. correction → strategy revision (T9)
print("\n=== correction (T9) ===")
say("no, jpg files go into photos/")

# 7. prospective memory fires
print("\n=== reminders fire ===")
say("ok back to work")

# 8. world model + conditional prospective memory (§3.7 / row 11)
print("\n=== world model & conditional reminders (§3.7 / row 11) ===")
mind.body.run("write_file", {"path": "downloads/contract.pdf", "text": "signed copy"})
mind.observe()  # baseline: the mind notes where things are
say("remind me when budget.xlsx appears in downloads to flag it for review")
mind.body.run("write_file", {"path": "downloads/budget.xlsx", "text": "q3 numbers"})
observed = mind.observe()
print(f"  observe saw: {[event['path'] for event in observed]}")
print(f"  conditional reminder fired: {list(mind.last_observed_reminders)}")
say("where is contract.pdf?")

# 9. self-model introspection (row 35)
print("\n=== introspection (row 35) ===")
say("what are you unsure about?")
say("what can you do?")
say("tell me about yourself")

# 10. honest low confidence (Q13)
print("\n=== honest low confidence (Q13) ===")
say("the deployment status is missing")
say("wait, that's wrong about the deployment")
say("no, that's wrong about the deployment")
say("that's not right about the deployment")
say("tell me about the deployment status")

# 11. explicit usefulness feedback (T13)
print("\n=== usefulness feedback (T13) ===")
say("that was useful")

# 12. idle curiosity investigates the environment (row 21)
print("\n=== idle curiosity (row 21) ===")
mind.body.run("write_file", {"path": "notes/deployment.md", "text": "the deployment pipeline is green"})
for _ in range(6):  # one gap per budget, oldest first, until the budget is drained
    curiosity = mind.tick()["curiosity"]
    for item in curiosity:
        print(f"  idle budget: {item}")
    if not curiosity:
        break
say("remember that the deployment status is green")  # real evidence resolves the gap
print("  open questions left:",
      len(mind.memory.query(kind="self", type="question", status="open")))

# 13. effort policy adapts to outcomes (T13 / §4.6)
print("\n=== effort policy (T13 / §4.6) ===")
print(f"  reflex word budget before: {mind.policy.word_limit}")
for phrase in ["make it ambiguous", "that contradicts", "tool-error now"] * 3:
    mind.step(phrase)  # short, failing reflex-class turns
notes = mind.tick()
print(f"  policy note: {notes['policy'] or 'no adjustment due'}")
print(f"  reflex word budget after:  {mind.policy.word_limit}")

# 13b. owner tone observed, cited, acted on (excluded-capability proxy)
print("\n=== owner tone (§3.5 affect observations) ===")
say("this is broken, it keeps failing!")   # read from the owner's words, not guessed
say("how am I doing?")                      # read-back, citing what was noticed

# 14. knowledge transfer to a fresh mind (Q15)
print("\n=== knowledge transfer (Q15) ===")
child = Mind(state_dir=STATE.parent / f"{STATE.name}-child", authority="allow")
counts = child.import_knowledge(mind.export_knowledge())
print(f"  fresh mind imported: {counts}")
child.body.run("mkdir", {"dir": "docs"})
child.body.run("mkdir", {"dir": "images"})
child.body.run("mkdir", {"dir": "handoff"})
child.body.run("write_file", {"path": "handoff/quarterly.pdf", "text": "q"})
child.body.run("write_file", {"path": "handoff/clip.mov", "text": "v"})
outcome = child.perform_goal("organize downloads", base_dir="handoff")
print(f"  fresh mind performed the taught goal: {outcome.outcome}")
moved = child.body.run("snapshot")["tree"]
print(f"  pdf went to docs/: {'docs/quarterly.pdf' in moved}")
print(f"  never-demonstrated category untouched: {'handoff/clip.mov' in moved}")

print("\ndemo complete — the mind persists at:", STATE)
