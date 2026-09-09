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
    args = parser.parse_args(argv)

    mind = Mind(state_dir=Path(args.state_dir))

    if args.say is not None:
        reply = mind.step(args.say)
        _print_reply(reply, show_label=args.label)
        return 0

    print("Beanie — artificial mind skeleton. Type 'exit' or Ctrl-D to leave. (State persists in this state dir.)")
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
            reply = mind.step(text)
            _print_reply(reply, show_label=args.label)
    except KeyboardInterrupt:
        print()
    return 0


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
