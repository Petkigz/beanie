"""Human interface to the loop — REPL and one-shot.

Traceability: ARCHITECTURE §4.2 (owner input trigger) and §8 Stage 0 (owner
input/output). The interface is a window into the mind, not the mind itself
(VISION §1) — this CLI exists so the skeleton can be talked to and demoed,
and will be superseded by richer windows (voice, UI) without touching the
loop.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .mind import Mind


def build_mind(state_dir: Path, authority: str = "ask") -> Mind:
    """A mind with the real model tier when BEANIE_MODEL_URL is set (§2).

    The CLI and the WebUI construct their minds through this one seam so both
    windows answer with the same substrate: HTTP when the owner configured an
    endpoint, the documented stub double otherwise.
    """
    substrate = None
    if os.environ.get("BEANIE_MODEL_URL"):
        from .substrate_http import HTTPSubstrate

        try:
            substrate = HTTPSubstrate()
        except RuntimeError as error:
            print(f"◉ model tier not used ({error}) — falling back to the deterministic stub")
    return Mind(substrate=substrate, state_dir=state_dir, authority=authority)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Talk to Beanie (Stage 0 skeleton).")
    parser.add_argument("--state-dir", default=".beanie_state", help="where this mind lives (default: .beanie_state)")
    parser.add_argument("--say", default=None, help="one-shot: send a single message and print the reply")
    parser.add_argument("--label", action="store_true", help="prefix replies with the communicated confidence label (T8)")
    parser.add_argument("--tick", type=int, default=0,
                        help="run N background-cognition passes (idle budget) and print what they did")
    parser.add_argument("--check-model", action="store_true",
                        help="ping the configured model tier (BEANIE_MODEL_URL) and exit")
    parser.add_argument("--status", action="store_true",
                        help="show which organs are seated (model tier, bodies, voice) and how to seat each")
    parser.add_argument("--audit-explanations", action="store_true",
                        help="run the §9.9 faithfulness audit over every recorded decision and exit")
    args = parser.parse_args(argv)

    if args.check_model:
        return _check_model()

    mind = build_mind(Path(args.state_dir))

    if args.status:
        pending = mind.pending_permission_requests()
        print("◉ organ status:")
        for name, organ in mind.organ_status().items():
            mark = "●" if organ["on"] else "○"
            line = f"  {mark} {name:<13} {'ON' if organ['on'] else 'off'}  — {organ['detail']}"
            if not organ["on"]:
                line += f"\n      seat it: {organ['switch']}"
            print(line)
        pending_line = ", ".join(p["capability"] for p in pending) or "none"
        print(f"  permission asks pending: {pending_line}")
        return 0

    if args.audit_explanations:
        return _audit_explanations(mind)

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


def _audit_explanations(mind: Mind) -> int:
    """§9.9: prove each explanation cites the actual reasons, not plausible ones."""
    from .faithfulness import audit_mind

    reports, summary = audit_mind(mind)
    if not reports:
        print("explanation audit: no decisions on record yet — talk to the mind first.")
        return 0
    for report in reports:
        print(report.to_text() if not report.faithful else f"turn {report.turn_id}: faithful")
    print(
        f"explanation audit: {summary['turns']} turn(s), {summary['faithful']} faithful, "
        f"{summary['violations']} violation(s), {summary['claims']} claim(s) checked"
        + (f", {summary['unaudited']} turn(s) with no decision trace" if summary.get("unaudited") else "")
    )
    return 1 if summary["violations"] else 0


def _check_model() -> int:
    """Report whether the configured model tier answers (§2 seam, owner-run check)."""
    import os

    from .substrate import FailureTaxonomy
    from .substrate_http import HTTPSubstrate

    endpoint = os.environ.get("BEANIE_MODEL_URL", "")
    model_name = os.environ.get("BEANIE_MODEL_NAME", "")
    try:
        substrate = HTTPSubstrate()
    except RuntimeError as error:
        print(f"Model tier not configured: {error}")
        print("Set BEANIE_MODEL_URL, BEANIE_MODEL_NAME and BEANIE_API_KEY, then retry.")
        return 2
    print(f"Endpoint: {substrate.base_url}  ·  model: {substrate.model}")
    candidate = substrate.fast({"user_text": "ping"}, [])
    if candidate.startswith("fast: low-confidence"):
        print("Fast tier: unreachable or unsure of the ping.")
    else:
        print(f"Fast tier: ok — {candidate[:120]}")
    outcome = substrate.deep({"user_text": "Reply with the single word: pong"}, [], candidate)
    if outcome.failure is FailureTaxonomy.TOOL_EXECUTION_ERROR:
        print("Deep tier: unreachable — the loop would report this honestly and not guess.")
        return 1
    print(f"Deep tier: ok — {outcome.text[:160]}")
    print("The whole loop and the longitudinal suite can now run against this tier:")
    print("  .venv/bin/python -m beanie.measure --suite-dir suites --substrate http")
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
