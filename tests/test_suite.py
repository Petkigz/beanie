"""Longitudinal-suite scaffold tests (ARCHITECTURE §8 measurement protocol)."""

import json

from beanie import Mind
from beanie.measure import Scenario, run_scenario, run_suite


def test_bundled_stage0_scenario_passes(tmp_path):
    scenario = Scenario.from_file(__import__("pathlib").Path("suites/stage0_skeleton.json"))
    result = run_scenario(scenario, tmp_path / "run")
    assert result.passed, result.failures
    assert result.passed_turns == 3
    # the ambiguity turn must have been tagged in the trace
    assert result.trace_failures.get("prompt_ambiguity") == 1


def test_scenario_failure_is_reported(tmp_path):
    scenario = Scenario(id="failing", description="", turns=[
        {"user": "hello", "expect": "zzzz-this-will-never-match"},
    ])
    result = run_scenario(scenario, tmp_path / "run")
    assert not result.passed
    assert result.failed_turns == 1
    assert result.failures[0]["expected"] == "zzzz-this-will-never-match"


def test_run_suite_tracks_delta_between_runs(tmp_path, capsys):
    """Measurement protocol (Q31): archived runs print the delta vs previous."""
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "one.json").write_text(json.dumps({
        "id": "one",
        "description": "passes",
        "turns": [{"user": "hello", "expect": "received"}],
    }), encoding="utf-8")
    track = tmp_path / "track"
    assert run_suite(suite_dir, tmp_path / "state1", track_dir=track) == 0
    assert run_suite(suite_dir, tmp_path / "state2", track_dir=track) == 0
    out = capsys.readouterr().out
    assert "Delta vs previous run:" in out
    assert "one: 1 → 1 passed turns" in out
    assert len(list(track.glob("*.json"))) == 2  # both runs archived


def test_run_suite_writes_outcome_json(tmp_path):
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "one.json").write_text(json.dumps({
        "id": "one",
        "description": "passes",
        "turns": [{"user": "hello", "expect": "received"}],
    }), encoding="utf-8")
    (suite_dir / "two.json").write_text(json.dumps({
        "id": "two",
        "description": "fails",
        "turns": [{"user": "hello", "expect": "impossible-match"}],
    }), encoding="utf-8")
    out = tmp_path / "out.json"
    code = run_suite(suite_dir, tmp_path / "state", out)
    assert code == 1  # one failed scenario
    data = json.loads(out.read_text(encoding="utf-8"))
    by_id = {row["scenario_id"]: row for row in data}
    assert by_id["one"]["passed"] is True
    assert by_id["two"]["passed"] is False
