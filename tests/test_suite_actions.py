"""Suite action-turn kinds and the trailing-window bookkeeping (Q31/§8)."""

import json

from beanie.measure import Scenario, run_scenario, run_suite, window_report


def test_scenario_action_turns_and_env_setup(tmp_path):
    """demo/perform/body/observe turns execute real loop paths, not just chat."""
    scenario = Scenario(
        id="actions",
        description="",
        authority="allow",
        setup={"dirs": ["downloads", "docs"], "files": {"downloads/a.pdf": "x"}},
        turns=[
            {"observe": True},
            {"demo": {"title": "pdfs to docs", "goal_class": "organize files",
                      "actions": [{"capability": "move_file",
                                   "args": {"src": "downloads/a.pdf", "dst": "docs"}}]},
             "expect": "pdf"},
            {"files": {"downloads/b.pdf": "y"},
             "perform": {"goal": "organize files", "base_dir": "downloads"}, "expect": "success"},
            {"body": {"capability": "read_file", "args": {"path": "docs/b.pdf"}}, "expect": "b.pdf"},
            {"query": {"kind": "procedural", "ctype": "skill"}, "expect": "organize files"},
        ],
    )
    result = run_scenario(scenario, tmp_path / "run")
    assert result.passed, result.failures
    assert result.passed_turns == 5


def test_expect_absent_is_the_honesty_assertion(tmp_path):
    """A scenario can assert the mind did NOT invent an answer."""
    scenario = Scenario(
        id="honest",
        description="",
        turns=[{"user": "where is unicorn.xyz?", "expect_absent": "is at"}],
    )
    assert run_scenario(scenario, tmp_path / "run").passed

    dishonest = Scenario(
        id="dishonest",
        description="",
        turns=[{"user": "where is unicorn.xyz?", "expect_absent": "received"}],
    )
    result = run_scenario(dishonest, tmp_path / "run2")
    assert not result.passed
    assert result.failures[0]["expected"] == "ABSENT: received"


def test_expect_same_as_flags_inconsistency(tmp_path):
    """Row 40 in the suite: identical input must produce identical surfaced text."""
    stable = Scenario(id="stable", description="", turns=[
        {"user": "hello there", "expect": "received"},
        {"user": "hello there", "expect_same_as": 0},
    ])
    assert run_scenario(stable, tmp_path / "run").passed

    unstable = Scenario(id="unstable", description="", turns=[
        {"user": "hello there", "expect": "received"},
        {"user": "goodbye", "expect_same_as": 0},  # different input → different text
    ])
    result = run_scenario(unstable, tmp_path / "run2")
    assert not result.passed
    assert result.failures[0]["expected"] == "SAME AS TURN 0"


def test_body_turn_failure_is_reported_not_crashed(tmp_path):
    """A body check on a missing file is a scenario failure, not an exception."""
    scenario = Scenario(id="body", description="", authority="allow", turns=[
        # a successful read returns {"path": …, "text": …}; the error payload does not
        {"body": {"capability": "read_file", "args": {"path": "nope.txt"}}, "expect": '"path"'},
    ])
    result = run_scenario(scenario, tmp_path / "run")
    assert not result.passed
    assert result.failed_turns == 1
    assert "body_error" in result.failures[0]["actual"]


def test_window_report_aggregates_tracked_runs(tmp_path):
    """Q31: the tracked number is movement over the trailing window, not one run."""
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "one.json").write_text(json.dumps({
        "id": "one", "description": "",
        "turns": [{"user": "hello", "expect": "received"}],
    }), encoding="utf-8")
    track = tmp_path / "track"
    run_suite(suite_dir, tmp_path / "s1", track_dir=track)
    run_suite(suite_dir, tmp_path / "s2", track_dir=track)

    report = window_report(track, days=30)
    assert report["runs"] == 2
    assert report["runs_archived"] == 2
    assert report["pass_rate"] == 1.0
    assert report["per_scenario"]["one"]["passed_runs"] == 2
    assert report["per_scenario"]["one"]["turn_delta"] == 0  # flat is flat, honestly
    assert report["calibration"]["highly confident"]["n"] == 2  # two outcome events

    empty = window_report(tmp_path / "nothing", days=30)
    assert empty["runs"] == 0


def test_window_report_window_excludes_old_runs(tmp_path):
    """Runs older than the window do not count toward the tracked number."""
    track = tmp_path / "track"
    track.mkdir()
    rows = [{"scenario_id": "one", "passed": True, "passed_turns": 1, "failed_turns": 0,
             "calibration": {"highly confident": {"n": 1, "failures": 0}}}]
    (track / "20200101_000000_000000.json").write_text(json.dumps(rows), encoding="utf-8")
    (track / "20260910_000000_000000.json").write_text(json.dumps(rows), encoding="utf-8")
    report = window_report(track, days=30)
    assert report["runs"] == 1
    assert report["runs_archived"] == 2


def test_bundled_suite_meets_the_20_to_30_task_protocol(tmp_path):
    """ARCHITECTURE §8: the longitudinal suite carries 20–30 multi-turn tasks."""
    from pathlib import Path

    paths = sorted(Path("suites").glob("*.json"))
    assert 20 <= len(paths) <= 30, f"protocol wants 20–30 tasks, found {len(paths)}"
    scenarios = [Scenario.from_file(path) for path in paths]
    for scenario in scenarios:
        assert len(scenario.turns) >= 2, f"{scenario.id}: a task is multi-turn"
    ids = [s.id for s in scenarios]
    assert len(ids) == len(set(ids)), "scenario ids must be unique"


def test_bundled_suite_passes_end_to_end(tmp_path):
    """Every shipped task passes on the deterministic substrate (no regressions)."""
    from pathlib import Path

    assert run_suite(Path("suites"), tmp_path / "state") == 0


def test_scorecard_snapshot_parses_the_real_register(tmp_path):
    """§8: register movement is half the tracked number — so it must be readable."""
    from pathlib import Path

    from beanie.measure import scorecard_snapshot

    snapshot = scorecard_snapshot(Path("CAPABILITY_REGISTER.md"))
    assert snapshot["35"] == "1"          # introspection, implemented
    assert snapshot["17"] == "0→P"        # Stage-5 property, honestly gated
    assert snapshot["5"] == "1"           # range "1–3, 5" expands to its parts
    assert snapshot["Q31 / §8"] == "1"
    assert len(snapshot) >= 30


def test_register_movement_is_tracked_between_runs(tmp_path):
    """The other half of Q31: scorecard movement over the window is reported."""
    import json

    from beanie.measure import register_movement, window_report

    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "one.json").write_text(json.dumps({
        "id": "one", "description": "", "turns": [{"user": "hello", "expect": "received"}],
    }), encoding="utf-8")
    register = tmp_path / "CAPABILITY_REGISTER.md"
    register.write_text(
        "## Mechanism scorecard\n\n| Row(s) | Verdict | Evidence |\n|---|---|---|\n"
        "| 17 | 0→P | Stage-5 property |\n| 35 | 1 | introspection |\n",
        encoding="utf-8",
    )
    track = tmp_path / "track"
    assert run_suite(suite_dir, tmp_path / "s1", track_dir=track, register_path=register) == 0

    register.write_text(
        "## Mechanism scorecard\n\n| Row(s) | Verdict | Evidence |\n|---|---|---|\n"
        "| 17 | 1 (data path) | proposal path landed |\n| 35 | 1 | introspection |\n",
        encoding="utf-8",
    )
    assert run_suite(suite_dir, tmp_path / "s2", track_dir=track, register_path=register) == 0

    sidecars = sorted(track.glob("*.register.json"))
    assert len(sidecars) == 2  # one snapshot per run
    first = json.loads(sidecars[0].read_text(encoding="utf-8"))
    second = json.loads(sidecars[1].read_text(encoding="utf-8"))
    assert register_movement(first, second) == [{"row": "17", "from": "0→P", "to": "1 (data path)"}]

    report = window_report(track, days=30)
    assert report["register_movement"] == [{"row": "17", "from": "0→P", "to": "1 (data path)"}]
