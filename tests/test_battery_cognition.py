"""T-test battery: T10, prospective memory, authority, attention, incubation,
usefulness, reflection/consolidation."""

import json

import pytest

from beanie import Mind
from beanie.calibration import UsefulnessTracker
from beanie.learning import DemoAction


@pytest.fixture
def mind(tmp_path):
    return Mind(state_dir=tmp_path / "mind")


def test_t10_explanation_on_demand_is_auditable(tmp_path):
    """T10: explanation cites the actual record; available on demand."""
    mind = Mind(state_dir=tmp_path / "mind")
    r1 = mind.step("hello there")
    r2 = mind.step("please do something ambiguous here")

    text = mind.explain(record_id=r2.record_id)
    assert text is not None
    assert r2.record_id in text
    assert "ambiguous" in text
    assert "confidence" in text

    # conversational path: "explain …" returns the explanation
    reply = mind.step("explain your last answer")
    assert reply.success
    assert "I answered" in reply.text

    # unknown id → honest nothing
    assert mind.explain(record_id="rec-99999") is None


def test_prospective_memory_turn_count_reminders(tmp_path):
    """§3.7: hold an intent in the background while the topic changes."""
    mind = Mind(state_dir=tmp_path / "mind")
    ack = mind.step("remind me in 2 turns to stretch")
    assert ack.success and "remind" in ack.text
    r1 = mind.step("hello")   # 1 remaining
    assert r1.reminders == ()
    r2 = mind.step("hello again")  # 0 remaining → fires
    assert "stretch" in r2.reminders
    assert mind.intentions.pending() == []


def test_prospective_memory_wallclock_and_cancel(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("remind me in 30 minutes to hydrate")
    pending = mind.intentions.pending()
    assert len(pending) == 1
    # backdate so it is due, then tick fires it
    entry = pending[0]
    entry.content["due_at"] = "2000-01-01T00:00+00:00"
    mind.memory.intentions.save_all()
    notes = mind.tick()
    assert notes["reminders"] == ["hydrate"]
    assert mind.intentions.pending() == []

    mind.step("remind me in 3 turns to call mom")
    cancel = mind.step("cancel the reminder about call mom")
    assert cancel.success and "cancel" in cancel.text.lower()
    assert mind.intentions.pending() == []
    # cancellation is logged as a revision, not a ghost
    cancelled = [e for e in mind.memory.intentions.all() if e.content.get("status") == "cancelled"]
    assert len(cancelled) == 1
    assert any("cancelled" in r.reason for r in cancelled[0].revision_history)


def test_authority_gate_four_states_and_growth(tmp_path):
    """§5: unknown → ask; granted → act; denied → not allowed."""
    mind = Mind(state_dir=tmp_path / "mind", authority="ask")
    _teach(mind)

    result = mind.perform_goal("organize downloads", base_dir="downloads")
    assert result.outcome == "needs_permission"
    assert "don't know whether" in result.permission_phrase  # the honest fourth state

    for capability in ("list_files", "move_file", "snapshot"):
        ack = mind.step(f"you may {capability}")
        assert ack.success
    result = mind.perform_goal("organize downloads", base_dir="downloads")
    assert result.outcome == "success", result

    mind.step("never list_files")
    denied = mind.perform_goal("organize downloads", base_dir="downloads")
    assert denied.outcome == "needs_permission"
    assert "not allowed" in denied.permission_phrase
    # rules persist with provenance
    rules = mind.gate.rules()
    assert any(r.content["capability"] == "list_files" and r.content["action"] == "deny" for r in rules)


def test_attention_novelty_over_observed_stream(tmp_path):
    """§4.2: file appears → perception episode, no owner input needed."""
    mind = Mind(state_dir=tmp_path / "mind")
    assert mind.observe() == []  # baseline
    mind.body.run("write_file", {"path": "incoming.txt", "text": "hi"})
    events = mind.observe()
    assert any(e["kind"] == "add" and e["path"] == "incoming.txt" for e in events)
    observation_episodes = [e for e in mind.episodes.all() if e.content.get("type") == "observation"]
    assert len(observation_episodes) == 1
    assert observation_episodes[0].source.value == "perception"


def test_incubation_parked_until_new_evidence(tmp_path):
    """§4.8: unsolved problems are revisited only when evidence has moved."""
    mind = Mind(state_dir=tmp_path / "mind")
    parked = mind.incubator.park("why does the migration keep failing", {"attempts": 2})
    assert mind.incubator.due_for_revisit() == []  # no new evidence yet
    # new evidence arrives (an open question enters the self store)
    mind.curiosity.open_question("migration", "does the migration conflict with the schema?")
    due = mind.incubator.due_for_revisit()
    assert any(e.id == parked.id for e in due)
    mind.incubator.revisit(parked, "revisited: schema question may explain it")
    assert parked.content["revisits"] == 1
    mind.incubator.mark_resolved(parked.id, "resolved: schema was the cause")
    assert mind.incubator.due_for_revisit() == []


def test_usefulness_tracking_t13(tmp_path):
    """T13: explicit ratings bucket by label; failures counted per label."""
    mind = Mind(state_dir=tmp_path / "mind")
    r1 = mind.step("hello")
    mind.rate(r1.turn_id, 5, "clear")
    r2 = mind.step("ambiguous thing here")
    mind.rate(r2.turn_id, 1, "confusing")
    summary = UsefulnessTracker.summary(mind.trace)
    assert summary["mean_rating_by_label"]["highly confident"] == 5.0
    assert summary["mean_rating_by_label"]["speculative"] == 1.0
    assert summary["failures_by_label"]["speculative"] == 1


def test_reflection_distills_and_consolidates_identity(tmp_path):
    """§4.3/Stage 5: corrections become lessons; identity summary refreshes."""
    mind = Mind(state_dir=tmp_path / "mind", reflect_every=1)
    mind.step("hello")  # a routine turn first
    mind.step("wait, that's wrong about the report")
    notes = mind.tick()
    assert any("Owner corrected" in note for note in notes["reflection"])
    lessons = mind.memory.query(kind="self", type="lesson")
    assert len(lessons) >= 1
    summary = mind.reflector.consolidate()
    assert summary["episodes_lived"] >= 2
    assert summary["corrections_received"] >= 1
    assert summary["lessons_learned"] >= 1
    # identity lives in the stores, queryable — T7 data path
    stored = mind.memory.query(kind="self", type="identity_summary")[-1]
    assert stored.content["episodes_lived"] == summary["episodes_lived"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _teach(mind):
    for path, text in {"downloads/a.pdf": "x", "downloads/b.jpg": "y"}.items():
        mind.body.run("write_file", {"path": path, "text": text})
    for directory in ("docs", "images"):
        mind.body.run("mkdir", {"dir": directory})
    proposal = mind.demonstrate(
        title="organize downloads",
        goal_class="organize downloads",
        actions=[
            DemoAction("move_file", {"src": "downloads/a.pdf", "dst": "docs"}),
            DemoAction("move_file", {"src": "downloads/b.jpg", "dst": "images"}),
        ],
    )
    mind.confirm_skill(proposal.skill_id)
