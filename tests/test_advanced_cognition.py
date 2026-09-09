"""Prospective-memory conditional triggers + open-question resolution + calibration + gisting."""

from beanie import Mind
from beanie.cognition import Curiosity
from beanie.intention import ParsedIntention, parse
from beanie.measure import calibration_report
from beanie.records import Entry, RecordKind, Source, utcnow_iso
from beanie.trace import Trace, FailureTaxonomy


# -- conditional prospective memory (Domain B / §3.7) ----------------------

def test_parse_conditional_reminder():
    parsed = parse("remind me when report.pdf appears in downloads to send it to the team")
    assert parsed is not None
    assert parsed.trigger_file == "report.pdf"
    assert parsed.trigger_dir == "downloads"
    assert "send it" in parsed.action


def test_conditional_reminder_fires_on_observation(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("remind me when report.pdf appears in downloads")
    pending = mind.intentions.pending()
    assert len(pending) == 1 and pending[0].content["trigger_file"] == "report.pdf"

    # baseline observation, then the file arrives
    assert mind.observe() == []
    mind.body.run("mkdir", {"dir": "downloads"})
    mind.body.run("write_file", {"path": "downloads/report.pdf", "text": "r"})
    events = mind.observe()
    assert any(e["path"] == "downloads/report.pdf" for e in events)

    # the conditional fired
    assert mind.last_observed_reminders  # surfaced by the observation pass
    assert mind.intentions.pending() == []
    fired = [e for e in mind.memory.intentions.all() if e.content.get("status") == "fired"]
    assert len(fired) == 1
    assert any(e.kind == "intention" for e in mind.trace.events)


def test_conditional_does_not_fire_for_other_files(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("remind me when invoice.pdf appears in downloads")
    mind.body.run("mkdir", {"dir": "downloads"})
    mind.body.run("write_file", {"path": "downloads/other.txt", "text": "x"})
    mind.observe()
    assert mind.intentions.pending()  # still pending — the trigger did not match
    assert mind.last_observed_reminders == []


# -- open-question resolution on evidence (T5 loop closure) -----------------

def test_open_question_resolves_when_fact_arrives(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("the context is missing here")  # leaves an open question
    assert len(mind.memory.query(kind="self", type="question", status="open")) == 1
    mind.step("remember that the context is stored in the config file")
    open_questions = mind.memory.query(kind="self", type="question", status="open")
    resolved = mind.memory.query(kind="self", type="question", status="resolved")
    assert len(resolved) == 1
    assert resolved[0].content.get("resolved_by")
    assert any("resolved by evidence" in r.reason for r in resolved[0].revision_history)


def test_open_goal_question_resolves_when_skill_confirmed(tmp_path):
    from beanie.learning import DemoAction

    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    result = mind.perform_goal("organize the archive folder")  # no skill → gap
    assert result.outcome == "needs_information"
    assert len(mind.memory.query(kind="self", type="question", status="open")) == 1
    # teach + confirm a matching skill → the gap closes
    mind.body.run("mkdir", {"dir": "docs"})
    mind.body.run("write_file", {"path": "downloads/a.pdf", "text": "x"})
    proposal = mind.demonstrate(
        title="sort pdfs", goal_class="organize files",
        actions=[DemoAction("move_file", {"src": "downloads/a.pdf", "dst": "docs"})],
    )
    mind.confirm_skill(proposal.skill_id)
    assert mind.memory.query(kind="self", type="question", status="open") == []
    assert len(mind.memory.query(kind="self", type="question", status="resolved")) >= 1


# -- calibration report (T8 measurement) ------------------------------------

def test_calibration_report_buckets_by_label():
    trace = Trace()  # in-memory trace
    for turn in range(6):
        trace.append(f"turn-{turn}", "outcome", {"success": True, "label": "highly confident"})
    for turn in range(2):
        trace.append(f"turn-{turn}", "outcome", {"success": False, "label": "speculative"})
    report = calibration_report(trace.events)
    assert report["highly confident"]["accuracy"] == 1.0
    assert report["speculative"]["accuracy"] == 0.0
    assert report["speculative"]["failures"] == 2
    # unlabeled events are ignored, not crashed on
    trace.append("turn-x", "decision", {"label": "highly confident"})
    assert calibration_report(trace.events)["highly confident"]["n"] == 6


# -- gisting (Domain B / R1.3) ----------------------------------------------

def test_gist_folds_routine_episodes(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    for i in range(30):  # 30 routine reflex turns
        mind.step("hello there")
    # all are routine; fold all but the recent window (20) — 10 older
    gist_id = mind.reflector.gist(keep_recent=20, threshold=8)
    assert gist_id is not None
    gist_entry = mind.memory.episodes.find(gist_id)
    assert gist_entry.content["type"] == "gist"
    assert len(gist_entry.content["compressed_episodes"]) >= 8
    compressed = [e for e in mind.memory.episodes.all() if e.content.get("compressed") == gist_id]
    assert len(compressed) >= 8
    # recent episodes are untouched
    recent = [e for e in mind.memory.episodes.all() if not e.content.get("compressed") and e.content.get("type") != "gist"]
    assert len(recent) <= 21  # 20 recent + the gist entry itself


def test_gist_runs_on_background_tick_when_due(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    for i in range(50):  # beyond keep_recent(20) + threshold(25)
        mind.step("hello there")
    notes = mind.tick()
    assert notes["gists"]  # the budget folded routine detail
    assert any(e.kind == "gist" for e in mind.trace.events)
    compressed = [e for e in mind.memory.episodes.all() if e.content.get("compressed")]
    assert len(compressed) >= 25
