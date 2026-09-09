"""Longitudinal measurement scaffold.

Traceability: ARCHITECTURE §8 Measurement protocol — failure taxonomy from
every run, and a longitudinal suite of multi-turn tasks whose *delta* is the
tracked number (Q31); VISION §5 scoring (0–3, nothing earns 3 without
longitudinal evidence).

Stage 0 ships the scaffold: scenario format, runner, and per-run summary.
Weekly delta bookkeeping and the 20–30-task canonical suite are populated as
stages land (each stage adds its exit criteria as scenarios here, so the
suite grows with the mind instead of drifting from it).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .mind import Mind
from .substrate import StubSubstrate
from .trace import FailureTaxonomy


@dataclass(frozen=True)
class Scenario:
    """One multi-turn task from the longitudinal suite (ARCHITECTURE §8)."""

    id: str
    description: str
    turns: list[dict[str, str]]  # [{"user": ..., "expect": ...}, ...]

    @classmethod
    def from_file(cls, path: Path) -> "Scenario":
        data = json.loads(path.read_text(encoding="utf-8"))
        turns = data.get("turns")
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"scenario {path}: 'turns' must be a non-empty list")
        for turn in turns:
            if "user" not in turn:
                raise ValueError(f"scenario {path}: each turn needs 'user'")
            turn.setdefault("expect", "")
        return cls(id=data.get("id", path.stem), description=data.get("description", ""), turns=turns)


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


@dataclass
class ScenarioResult:
    scenario_id: str
    passed_turns: int = 0
    failed_turns: int = 0
    failures: list[dict] = field(default_factory=list)
    trace_failures: dict[str, int] = field(default_factory=dict)
    calibration: dict[str, dict] = field(default_factory=dict)

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
        }


def run_scenario(scenario: Scenario, state_dir: Path) -> ScenarioResult:
    """Run one scenario against a fresh mind; check expected reply substrings.

    Stage 0 checks are deliberately weak (substring match on the reply) — the
    scaffold's job is the loop, not the oracle. Scenario expectations tighten
    as the T-tests land (T1–T13 map onto scenario turns in later stages).
    """
    mind = Mind(substrate=StubSubstrate(), state_dir=state_dir)
    result = ScenarioResult(scenario_id=scenario.id)
    for turn in scenario.turns:
        reply = mind.step(turn["user"])
        expected = turn.get("expect", "").lower()
        # the haystack includes the reply text AND surfaced reminders and
        # questions, so scenarios can assert background intents firing (§3.7)
        haystack = " ".join(
            [reply.text, " ".join(reply.reminders), " ".join(reply.questions)]
        ).lower()
        if expected and expected not in haystack:
            result.failed_turns += 1
            result.failures.append(
                {
                    "turn": turn["user"][:120],
                    "expected": expected,
                    "actual": reply.text[:200],
                    "reminders": list(reply.reminders)[:3],
                    "label": reply.confidence_label,
                }
            )
        else:
            result.passed_turns += 1
    result.trace_failures = mind.trace.failures_by_kind()
    result.calibration = calibration_report(mind.trace.events)
    return result


def run_suite(suite_dir: Path, state_dir: Path, out_path: Path | None = None, track_dir: Path | None = None) -> int:
    """Run every scenario file in `suite_dir`; returns number of failed scenarios.

    With `track_dir`, the run's results are archived under a timestamped file
    and the *delta* against the previous run is printed — the tracked number
    of the measurement protocol (Q31 / ARCHITECTURE §8).
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
    if out_path is not None:
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if track_dir is not None:
        track_dir.mkdir(parents=True, exist_ok=True)
        run_id = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        (track_dir / f"{run_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        previous = sorted(track_dir.glob("*.json"))
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
    return run_suite(
        suite_dir,
        state_dir,
        Path(args.out) if args.out else None,
        Path(args.track_dir) if args.track_dir else None,
    )


if __name__ == "__main__":
    sys.exit(main())
