"""Human interface to the loop — REPL and one-shot.

Traceability: ARCHITECTURE §4.2 (owner input trigger) and §8 Stage 0 (owner
input/output). The interface is a window into the mind, not the mind itself
(VISION §1) — this CLI exists so the skeleton can be talked to and demoed,
and will be superseded by richer windows (voice, UI) without touching the
loop.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .mind import Mind


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Talk to Beanie (Stage 0 skeleton).")
    parser.add_argument("--state-dir", default=".beanie_state", help="where this mind lives (default: .beanie_state)")
    parser.add_argument("--say", default=None, help="one-shot: send a single message and print the reply")
    parser.add_argument("--label", action="store_true", help="prefix replies with the communicated confidence label (T8)")
    parser.add_argument("--tick", type=int, default=0,
                        help="run N background-cognition passes (idle budget) and print what they did")
    args = parser.parse_args(argv)

    mind = Mind(state_dir=Path(args.state_dir))

    if args.tick:
        for _ in range(args.tick):
            _print_tick(mind.tick())
        if args.say is None:
            return 0

    if args.say is not None:
        reply = mind.step(args.say)
        _print_reply(reply, show_label=args.label)
        return 0

    print("Beanie — artificial mind skeleton. Type 'exit' or Ctrl-D to leave; 'tick [N]' runs the "
          "background budget. (State persists in this state dir.)")
    try:
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            text = line.strip()
            if not text:
                continue
            if text.lower() in {"exit", "quit"}:
                break
            if text.lower().startswith("tick"):
                parts = text.split()
                count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                for _ in range(count):
                    _print_tick(mind.tick())
                continue
            reply = mind.step(text)
            _print_reply(reply, show_label=args.label)
    except KeyboardInterrupt:
        print()
    return 0


def _print_tick(notes: dict) -> None:
    """Show what a background-cognition pass actually did (§4.2, row 21)."""
    lines: list[str] = []
    for reminder in notes.get("reminders", []):
        lines.append(f"reminder: {reminder}")
    for subject in notes.get("curiosity", []):
        lines.append(f"curiosity: {subject}")
    for gist_id in notes.get("gists", []):
        lines.append(f"gist: {gist_id}")
    for context in notes.get("preferences", []):
        lines.append(f"preference proposal: {context}")
    for entry_id in notes.get("stale", []):
        lines.append(f"stale flagged: {entry_id}")
    for entry_id in notes.get("incubation_revisits", []):
        lines.append(f"incubation revisit: {entry_id}")
    for lesson in notes.get("reflection", []):
        lines.append(f"lesson: {lesson}")
    if notes.get("policy"):
        lines.append(f"policy: {notes['policy']}")
    print("\n".join(lines) if lines else "(background pass: nothing needed attention)")


def _print_reply(reply, *, show_label: bool) -> None:
    prefix = f"[{reply.confidence_label}] " if show_label else ""
    print(f"{prefix}{reply.text}")
    for reminder in reply.reminders:
        print(f"  🔔 Reminder: {reminder}")
    for question in reply.questions:
        print(f"  ? {question}")


def main_entry() -> None:
    """Console-script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
