"""Longitudinal measurement scaffold.

Traceability: ARCHITECTURE §8 Measurement protocol — failure taxonomy from
every run, and a longitudinal suite of multi-turn tasks whose *delta* is the
tracked number (Q31); VISION §5 scoring (0–3, nothing earns 3 without
longitudinal evidence).

Stage 0 ships the scaffold: scenario format, runner, and per-run summary.
Weekly delta bookkeeping and the 20–30-task canonical suite are populated as
stages land (each stage adds its exit criteria as scenarios here, so the
suite grows with the mind instead of drifting from it).

Scenario format (each turn is one of the kinds below, plus optional `expect`
and `expect_absent` substring checks against everything the turn surfaced):

    {"user": "..."}                        conversation turn (Mind.step)
    {"observe": true}                      perception pass (Mind.observe)
    {"tick": 2}                            background cognition (Mind.tick)
    {"demo": {"title":…, "goal_class":…,
              "actions": [{"capability":…, "args": {…}}]}}   teach + confirm
    {"perform": {"goal":…, "base_dir":…}}  goal execution (Mind.perform_goal)
    {"body": {"capability":…, "args": {…}}}  direct sandbox check (read/list/…)
    {"query": {"kind":…, "type":…}}        assertion over a store
    {"trace": {"kind": "feedback"}}        assertion over trace events

Any turn may carry `"dirs": [...]` / `"files": {path: text}` to stage the
environment before the turn; a top-level `"setup"` does the same once up
front. `expect_absent` is how a scenario asserts honesty (e.g. no fabricated
location, no confident answer without evidence) — the assertion side of the
"never fake a capability" rule.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .learning import DemoAction
from .mind import Mind
from .substrate import StubSubstrate
from .trace import FailureTaxonomy


@dataclass(frozen=True)
class Scenario:
    """One multi-turn task from the longitudinal suite (ARCHITECTURE §8)."""

    id: str
    description: str
    turns: list[dict[str, Any]]  # conversation/tool turns — see module docstring
    setup: dict[str, Any] = field(default_factory=dict)
    authority: str = "ask"  # authority policy the scenario runs under (§5)
    reflect_every: int = 25  # reflection cadence for the run (§4.3)

    @classmethod
    def from_file(cls, path: Path) -> "Scenario":
        data = json.loads(path.read_text(encoding="utf-8"))
        turns = data.get("turns")
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"scenario {path}: 'turns' must be a non-empty list")
        for turn in turns:
            if not any(k in turn for k in ("user", "observe", "tick", "demo", "perform", "body", "query", "trace")):
                raise ValueError(f"scenario {path}: each turn needs 'user' or an action key")
            turn.setdefault("expect", "")
        return cls(
            id=data.get("id", path.stem),
            description=data.get("description", ""),
            turns=turns,
            setup=data.get("setup", {}),
            authority=str(data.get("authority", "ask")),
            reflect_every=int(data.get("reflect_every", 25)),
        )


def _apply_env(mind: Mind, spec: dict[str, Any]) -> None:
    """Stage the sandbox before a turn: `dirs` then `files` (deterministic)."""
    for directory in spec.get("dirs", []):
        mind.body.run("mkdir", {"dir": directory})
    for path, text in spec.get("files", {}).items():
        mind.body.run("write_file", {"path": path, "text": str(text)})



def calibration_report(events: list) -> dict[str, dict]:
    """T8 self-audit: how well did each confidence label predict success?

    Reads trace outcome events (each carries a label and a success/failure
    verdict) and buckets them: per label — count, failures, and accuracy.
    This is the executable half of VISION T8: labels must *predict* outcomes
    better than an unlabeled baseline; the report surfaces when "highly
    confident" stops beating "speculative" (miscalibration to act on).
    """
    from collections import defaultdict

    buckets: dict[str, dict] = {}
    counts: dict[str, list[bool]] = defaultdict(list)
    for event in events:
        kind = getattr(event, "kind", event.get("kind") if isinstance(event, dict) else None)
        if kind != "outcome":
            continue
        payload = event.payload if not isinstance(event, dict) else event
        label = str(payload.get("label", "")) or "unlabeled"
        success = bool(payload.get("success", False))
        counts[label].append(success)
    for label, outcomes in counts.items():
        failures = sum(1 for ok in outcomes if not ok)
        buckets[label] = {
            "n": len(outcomes),
            "failures": failures,
            "accuracy": round((len(outcomes) - failures) / len(outcomes), 3),
        }
    return dict(sorted(buckets.items(), key=lambda kv: kv[1]["n"], reverse=True))


def usefulness_report(events: list) -> dict[str, dict]:
    """T13/A4: explicit owner ratings per confidence label.

    Reads trace feedback events (the owner's 1–5 usefulness verdicts, whether
    spoken in the loop or set via Mind.rate) and buckets them under the label
    of the turn they judged. A label whose answers get rated poorly is exactly
    the signal the effort policy and the owner should see.
    """
    labels: dict[str, str] = {}
    scores: dict[str, list[int]] = {}
    signals: dict[str, int] = {}
    for event in events:
        kind = getattr(event, "kind", None)
        payload = getattr(event, "payload", {})
        if kind == "outcome":
            labels[event.turn_id] = str(payload.get("label", "")) or "unlabeled"
        elif kind == "feedback":
            label = labels.get(event.turn_id, "unlabeled")
            scores.setdefault(label, []).append(int(payload.get("score", 0)))
        elif kind == "usefulness":
            signal = str(payload.get("signal", ""))
            signals[signal] = signals.get(signal, 0) + 1
    return {
        "ratings_by_label": {
            label: {"n": len(values), "sum": sum(values), "mean": round(sum(values) / len(values), 2)}
            for label, values in sorted(scores.items())
        },
        "signals": dict(sorted(signals.items())),
    }


@dataclass
class ScenarioResult:
    scenario_id: str
    passed_turns: int = 0
    failed_turns: int = 0
    failures: list[dict] = field(default_factory=list)
    trace_failures: dict[str, int] = field(default_factory=dict)
    calibration: dict[str, dict] = field(default_factory=dict)
    usefulness: dict[str, dict] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.failed_turns == 0

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "passed_turns": self.passed_turns,
            "failed_turns": self.failed_turns,
            "failures": self.failures,
            "trace_failures": self.trace_failures,
            "calibration": self.calibration,
            "usefulness": self.usefulness,
        }


def run_scenario(scenario: Scenario, state_dir: Path) -> ScenarioResult:
    """Run one scenario against a fresh mind; check expected reply substrings.

    Every turn kind produces a haystack of everything it surfaced (reply text,
    reminders, questions, events, tick notes, plan steps) and the scenario's
    `expect` / `expect_absent` substrings are checked against it. Checks are
    deliberately weak (substring) — the scaffold's job is the loop, not the
    oracle; the T-tests are the oracle. Scenario expectations tighten as the
    T-tests land (T1–T13 map onto scenario turns).
    """
    mind = Mind(substrate=StubSubstrate(), state_dir=state_dir, authority=scenario.authority,
                reflect_every=scenario.reflect_every)
    _apply_env(mind, scenario.setup)
    result = ScenarioResult(scenario_id=scenario.id)
    turn_haystacks: list[str] = []
    for turn in scenario.turns:
        _apply_env(mind, turn)
        haystacks: list[str] = []
        if turn.get("observe"):
            events = mind.observe()
            haystacks.append(json.dumps(events))
            haystacks.extend(mind.last_observed_reminders)
        elif "tick" in turn:
            haystacks.append(json.dumps([mind.tick() for _ in range(int(turn["tick"]))]))
        elif "demo" in turn:
            demo = turn["demo"]
            proposal = mind.demonstrate(
                title=demo.get("title", ""),
                goal_class=demo.get("goal_class", ""),
                actions=[
                    DemoAction(a.get("capability", ""), dict(a.get("args", {})), a.get("effect_note", ""))
                    for a in demo.get("actions", [])
                ],
            )
            entry = mind.confirm_skill(proposal.skill_id)
            haystacks.extend([proposal.confirm_question, json.dumps(entry.content)])
        elif "perform" in turn:
            performed = mind.perform_goal(
                str(turn["perform"].get("goal", "")),
                base_dir=turn["perform"].get("base_dir"),
            )
            haystacks.append(json.dumps(
                {"outcome": performed.outcome, "steps": performed.actions_done,
                 "permission": performed.permission_phrase,
                 "permission_question": performed.permission_question,
                 "inferred": performed.inferred, "unmapped": performed.unmapped}
            ))
        elif "body" in turn:
            body_call = turn["body"]
            try:
                outcome = mind.body.run(str(body_call.get("capability", "")), dict(body_call.get("args", {})))
            except Exception as exc:  # a body check that fails is a scenario failure, not a crash
                outcome = {"body_error": f"{type(exc).__name__}: {exc}"}
            haystacks.append(json.dumps(outcome))
        elif "query" in turn:
            spec = {k: v for k, v in turn["query"].items() if k not in ("text",)}
            entries = mind.memory.query(**spec)
            haystacks.append(json.dumps([e.content for e in entries]))
        elif "trace" in turn:
            wanted = str(turn["trace"].get("kind", ""))
            haystacks.append(json.dumps([
                {"kind": e.kind, "turn_id": e.turn_id, "payload": e.payload}
                for e in mind.trace.events
                if not wanted or e.kind == wanted
            ]))
        else:
            reply = mind.step(turn["user"])
            haystacks.extend([reply.text, " ".join(reply.reminders), " ".join(reply.questions)])
        haystack = " ".join(haystacks).lower()
        message = " ".join(haystacks)[:200] or "(nothing surfaced)"
        expected = turn.get("expect", "").lower()
        forbidden = turn.get("expect_absent", "").lower()
        same_as = turn.get("expect_same_as")
        if same_as is not None and haystack != turn_haystacks[int(same_as)]:
            result.failed_turns += 1
            result.failures.append(
                {
                    "turn": (turn.get("user") or json.dumps(turn))[:120],
                    "expected": f"SAME AS TURN {same_as}",
                    "actual": message,
                    "label": "",
                }
            )
        elif expected and expected not in haystack:
            result.failed_turns += 1
            result.failures.append(
                {
                    "turn": (turn.get("user") or json.dumps(turn))[:120],
                    "expected": expected,
                    "actual": message,
                    "label": getattr(mind, "_last_label", ""),
                }
            )
        elif forbidden and forbidden in haystack:
            result.failed_turns += 1
            result.failures.append(
                {
                    "turn": (turn.get("user") or json.dumps(turn))[:120],
                    "expected": f"ABSENT: {forbidden}",
                    "actual": message,
                    "label": "",
                }
            )
        else:
            result.passed_turns += 1
        turn_haystacks.append(haystack)
    result.trace_failures = mind.trace.failures_by_kind()
    result.calibration = calibration_report(mind.trace.events)
    result.usefulness = usefulness_report(mind.trace.events)
    return result


def scorecard_snapshot(register_path: Path) -> dict[str, str]:
    """Read the mechanism scorecard into `{row: verdict}` (ARCHITECTURE §8).

    §8 fixes the tracked number as suite score *and* register movement over
    the trailing window, so the register has to be machine-readable. The
    consolidated scorecard table is: first column = register row(s) (numbers,
    ranges, or T/Q ids), second = verdict for the current state.
    """
    if not register_path.exists():
        return {}
    text = register_path.read_text(encoding="utf-8")
    _, _, scorecard = text.partition("## Mechanism scorecard")
    snapshot: dict[str, str] = {}
    for line in scorecard.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].startswith("Row") or set(cells[0]) <= {"-", " "}:
            continue
        for part in cells[0].split(","):
            key = part.strip().lstrip("#")
            if not key:
                continue
            if "–" not in key:
                leading = re.match(r"(\d+)", key)
                if leading:  # "43 (T6 analogy)" is row 43
                    key = leading.group(1)
            snapshot[key] = cells[1]
    return snapshot


def register_scores(register_path: Path) -> dict[int, int]:
    """Read the capability table's Score column: {row number -> achieved level}.

    The register's headline metric is how many rows move up a VISION §5 level
    between reviews, so the Score column has to be machine-readable — otherwise
    the metric exists only in prose (it was empty until 2026-09-10).
    """
    if not register_path.exists():
        return {}
    scores: dict[int, int] = {}
    for line in register_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 6 or not cells[0].isdigit() or not cells[5].isdigit():
            continue
        scores[int(cells[0])] = int(cells[5])
    return scores


def score_movement(previous: dict[int, int], current: dict[int, int]) -> list[dict[str, int]]:
    """Rows whose VISION §5 score changed between two register readings."""
    return [
        {"row": row, "from": previous[row], "to": level}
        for row, level in sorted(current.items())
        if row in previous and previous[row] != level
    ]


def print_score_composition(scores: dict[int, int]) -> None:
    """The register's headline number: how many rows sit at each level today."""
    if not scores:
        print("  capability scores: register not readable")
        return
    total = len(scores)
    by_level: dict[int, int] = {}
    for level in scores.values():
        by_level[level] = by_level.get(level, 0) + 1
    parts = ", ".join(f"{count} at level {level}" for level, count in sorted(by_level.items(), reverse=True))
    print(f"  capability scores: {parts} (of {total} rows) "
          f"— levels 2–3 require longitudinal evidence (VISION §5)")


def register_movement(previous: dict[str, str], current: dict[str, str]) -> list[dict[str, str]]:
    """Rows whose verdict changed between two scorecard snapshots."""
    moved: list[dict[str, str]] = []
    for row, verdict in current.items():
        before = previous.get(row)
        if before is not None and before != verdict:
            moved.append({"row": row, "from": before, "to": verdict})
    return moved


def _print_register_movement(movement: list[dict[str, str]]) -> None:
    if not movement:
        print("  register movement: none — no scorecard row changed")
        return
    print(f"  register movement: {len(movement)} row(s) changed")
    for change in movement:
        print(f"    row {change['row']}: {change['from']} → {change['to']}")


def run_files(track_dir: Path) -> list[Path]:
    """Archived run files (results), excluding the register/score sidecars."""
    return sorted(
        path for path in track_dir.glob("*.json")
        if not path.name.endswith((".register.json", ".scores.json")) and _parse_run_id(path.stem)
    )


def sidecar_files(track_dir: Path, suffix: str) -> list[Path]:
    """Companion snapshots written beside runs, in run order."""
    return sorted(
        path for path in track_dir.glob(f"*{suffix}")
        if _parse_run_id(path.name[: -len(suffix)])
    )


def _parse_run_id(stem: str) -> "_dt.datetime | None":
    """Archived run ids are `%Y%m%d_%H%M%S_%f` timestamps."""
    try:
        return _dt.datetime.strptime(stem, "%Y%m%d_%H%M%S_%f")
    except ValueError:
        return None


def window_report(track_dir: Path, days: int = 30) -> dict[str, Any]:
    """The tracked number of the protocol: movement over the trailing window.

    ARCHITECTURE §8 / Q31 fixes the number as suite score *and* register
    movement over the trailing 30 days — not any single run. This reads the
    archived runs inside the window and returns: run count, per-scenario
    pass-rate and passed-turn delta (first → last run in window), overall
    pass rate, and the aggregated T8 calibration buckets. A system that
    shuffles code but never improves on the *same* tasks shows as a flat or
    negative delta here.
    """
    runs: list[tuple[_dt.datetime, list[dict]]] = []
    registers: list[tuple[_dt.datetime, dict[str, str]]] = []
    score_snapshots: list[tuple[_dt.datetime, dict]] = []
    for path in sidecar_files(track_dir, ".register.json"):
        stamp = _parse_run_id(path.name[: -len(".register.json")])
        try:
            registers.append((stamp, json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError):
            pass
    for path in sidecar_files(track_dir, ".scores.json"):
        stamp = _parse_run_id(path.name[: -len(".scores.json")])
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            score_snapshots.append((stamp, {int(k): int(v) for k, v in raw.items()}))
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    for path in run_files(track_dir):
        stamp = _parse_run_id(path.stem)
        try:
            runs.append((stamp, json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError):
            continue
    if not runs:
        return {"runs": 0, "days": days}
    latest_stamp = runs[-1][0]
    cutoff = latest_stamp - _dt.timedelta(days=days)
    window = [(stamp, rows) for stamp, rows in runs if stamp >= cutoff]
    per_scenario: dict[str, dict[str, Any]] = {}
    calibration: dict[str, dict[str, int]] = {}
    runs_fully_passed = 0
    for _, rows in window:
        all_passed = bool(rows)
        for row in rows:
            entry = per_scenario.setdefault(
                row["scenario_id"],
                {"runs": 0, "passed_runs": 0, "first_passed_turns": row["passed_turns"],
                 "last_passed_turns": row["passed_turns"], "turn_delta": 0},
            )
            entry["runs"] += 1
            entry["passed_runs"] += 1 if row.get("passed") else 0
            entry["last_passed_turns"] = row["passed_turns"]
            entry["turn_delta"] = entry["last_passed_turns"] - entry["first_passed_turns"]
            all_passed = all_passed and bool(row.get("passed"))
            for label, stats in (row.get("calibration") or {}).items():
                bucket = calibration.setdefault(label, {"n": 0, "failures": 0})
                bucket["n"] += stats.get("n", 0)
                bucket["failures"] += stats.get("failures", 0)
        runs_fully_passed += 1 if all_passed else 0
    for label, stats in calibration.items():
        stats["accuracy"] = round((stats["n"] - stats["failures"]) / stats["n"], 3) if stats["n"] else None
    window_start = window[0][0] if window else None
    register_window = [(stamp, snap) for stamp, snap in registers if window_start is not None and stamp >= window_start]
    movement = register_movement(register_window[0][1], register_window[-1][1]) if len(register_window) >= 2 else []
    score_window = [(stamp, snap) for stamp, snap in score_snapshots if window_start is not None and stamp >= window_start]
    levels = score_movement(score_window[0][1], score_window[-1][1]) if len(score_window) >= 2 else []
    return {
        "runs": len(window),
        "runs_archived": len(runs),
        "days": days,
        "window_start": window[0][0].isoformat(),
        "window_end": latest_stamp.isoformat(),
        "runs_fully_passed": runs_fully_passed,
        "pass_rate": round(runs_fully_passed / len(window), 3) if window else None,
        "per_scenario": per_scenario,
        "calibration": calibration,
        "register_movement": movement,
        "score_movement": levels,
    }


def print_window_report(track_dir: Path, days: int = 30) -> dict[str, Any]:
    """Print and return the trailing-window report (Q31 tracked number)."""
    report = window_report(track_dir, days=days)
    print(f"\nTrailing-{days}-day window (Q31 tracked number):")
    if not report["runs"]:
        print("  no archived runs in the window yet — the delta appears from the second run on")
        return report
    print(f"  runs in window: {report['runs']} (of {report['runs_archived']} archived) · "
          f"fully-passing runs: {report['runs_fully_passed']} ({report['pass_rate']})")
    print(f"  window: {report['window_start'][:19]} → {report['window_end'][:19]}")
    for scenario_id, entry in sorted(report["per_scenario"].items()):
        delta = entry["turn_delta"]
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
        print(f"  {scenario_id}: pass {entry['passed_runs']}/{entry['runs']} runs · "
              f"passed turns {entry['first_passed_turns']} → {entry['last_passed_turns']} {arrow}")
    print("  register movement in window:")
    _print_register_movement(report.get("register_movement", []))
    levels = report.get("score_movement", [])
    if levels:
        print("  register score movement (VISION §5 levels):")
        for change in levels:
            print(f"    row {change['row']}: level {change['from']} → {change['to']} ▲")
    else:
        print("  register score movement: none")
    if report["calibration"]:
        print("  calibration in window:")
        for label, stats in sorted(report["calibration"].items(), key=lambda kv: -kv[1]["n"]):
            print(f"    {label:<18} n={stats['n']:<4} failures={stats['failures']:<4} accuracy={stats['accuracy']}")
    return report


def run_suite(suite_dir: Path, state_dir: Path, out_path: Path | None = None, track_dir: Path | None = None,
              register_path: Path | None = None) -> int:
    """Run every scenario file in `suite_dir`; returns number of failed scenarios.

    With `track_dir`, the run's results are archived under a timestamped file
    and the *delta* against the previous run is printed — suite score movement
    being half of the tracked number (Q31 / ARCHITECTURE §8). With
    `register_path`, the scorecard is snapshotted beside the run so the other
    half — capability-register movement — is tracked too.
    """
    paths = sorted(p for p in suite_dir.glob("*.json") if p.is_file())
    if not paths:
        print(f"No scenario files (*.json) found in {suite_dir}")
        return 1
    results: list[ScenarioResult] = []
    for path in paths:
        scenario = Scenario.from_file(path)
        run_dir = state_dir / scenario.id
        run_dir.mkdir(parents=True, exist_ok=True)
        results.append(run_scenario(scenario, run_dir))
    failed = sum(1 for r in results if not r.passed)
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"[{mark}] {result.scenario_id}: {result.passed_turns} passed, {result.failed_turns} failed "
              f"(trace failures: {result.trace_failures or 'none'})")
        for failure in result.failures:
            print(f"      expected '{failure['expected']}' in reply, got: {failure['actual']!r} [{failure['label']}]")
    print(f"\nSuite summary: {len(results) - failed}/{len(results)} scenarios passed.")
    payload = [r.to_dict() for r in results]
    # T8 self-audit: aggregated label calibration across the run
    merged: dict[str, dict] = {}
    for row in payload:
        for label, stats in row.get("calibration", {}).items():
            bucket = merged.setdefault(label, {"n": 0, "failures": 0})
            bucket["n"] += stats["n"]
            bucket["failures"] += stats["failures"]
    if merged:
        print("\nCalibration (labels vs outcomes, T8):")
        for label, stats in sorted(merged.items(), key=lambda kv: -kv[1]["n"]):
            accuracy = round((stats["n"] - stats["failures"]) / stats["n"], 3)
            print(f"  {label:<18} n={stats['n']:<3} failures={stats['failures']:<3} accuracy={accuracy}")
    ratings: dict[str, dict[str, int]] = {}
    signal_counts: dict[str, int] = {}
    for row in payload:
        usefulness = row.get("usefulness") or {}
        for label, stats in (usefulness.get("ratings_by_label") or {}).items():
            bucket = ratings.setdefault(label, {"n": 0, "sum": 0})
            bucket["n"] += stats["n"]
            bucket["sum"] += stats.get("sum", 0)
        for signal, count in (usefulness.get("signals") or {}).items():
            signal_counts[signal] = signal_counts.get(signal, 0) + count
    if ratings:
        print("\nUsefulness (explicit owner ratings, T13):")
        for label, stats in sorted(ratings.items(), key=lambda kv: -kv[1]["n"]):
            mean = round(stats["sum"] / stats["n"], 2) if stats["n"] else 0
            print(f"  {label:<18} n={stats['n']:<3} mean_rating={mean}")
    if signal_counts:
        print("  implicit signals (§8): " + ", ".join(f"{k}={v}" for k, v in sorted(signal_counts.items())))
    if out_path is not None:
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if track_dir is not None:
        track_dir.mkdir(parents=True, exist_ok=True)
        run_id = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        (track_dir / f"{run_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        snapshot = scorecard_snapshot(register_path) if register_path is not None else {}
        if snapshot:
            (track_dir / f"{run_id}.register.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        scores = register_scores(register_path) if register_path is not None else {}
        if scores:
            (track_dir / f"{run_id}.scores.json").write_text(json.dumps(scores, indent=2), encoding="utf-8")
            print_score_composition(scores)
        previous = run_files(track_dir)
        if len(previous) >= 2:  # newest is this run
            with previous[-2].open(encoding="utf-8") as fh:
                last = {row["scenario_id"]: row for row in json.load(fh)}
            print("\nDelta vs previous run:")
            for row in payload:
                prev = last.get(row["scenario_id"])
                if prev is None:
                    print(f"  {row['scenario_id']}: new scenario")
                    continue
                shift = row["passed_turns"] - prev["passed_turns"]
                arrow = "▲" if shift > 0 else ("▼" if shift < 0 else "—")
                print(f"  {row['scenario_id']}: {prev['passed_turns']} → {row['passed_turns']} passed turns {arrow}")
            if snapshot:
                previous_registers = sidecar_files(track_dir, ".register.json")
                if len(previous_registers) >= 2:
                    with previous_registers[-2].open(encoding="utf-8") as fh:
                        previous_snapshot = json.load(fh)
                    _print_register_movement(register_movement(previous_snapshot, snapshot))
        # the protocol's tracked number is the trailing-window delta (Q31)
        print_window_report(track_dir)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Beanie longitudinal suite runner (ARCHITECTURE §8).")
    parser.add_argument("--suite-dir", default="suites", help="directory of scenario *.json files")
    parser.add_argument("--state-dir", default=None, help="state directory (default: fresh temp dir)")
    parser.add_argument("--out", default=None, help="optional path for a JSON results file")
    parser.add_argument("--track-dir", default=None, help="archive runs here and print the delta vs the previous run (Q31)")
    args = parser.parse_args(argv)
    suite_dir = Path(args.suite_dir)
    state_dir = Path(args.state_dir) if args.state_dir else Path(tempfile.mkdtemp(prefix="beanie-suite-"))
    register_path = Path("CAPABILITY_REGISTER.md")
    return run_suite(
        suite_dir,
        state_dir,
        Path(args.out) if args.out else None,
        Path(args.track_dir) if args.track_dir else None,
        register_path if register_path.exists() else None,
    )


if __name__ == "__main__":
    sys.exit(main())
