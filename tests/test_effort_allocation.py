"""Effort allocation (§4.6) + budgeted idle exploration (R3.24 / register row 21)."""

from beanie import Mind
from beanie.substrate import StubSubstrate


def test_reflex_turns_never_wake_the_deep_tier(tmp_path):
    """Trivial low-stakes input is answered by the fast tier alone (§4.6)."""
    substrate = StubSubstrate()
    mind = Mind(substrate=substrate, state_dir=tmp_path / "mind")
    reply = mind.step("hello there")
    assert reply.success
    assert substrate.fast_calls == 1
    assert substrate.deep_calls == 0  # the deep tier was never woken
    assert reply.confidence_label == "highly confident"
    episode = mind.episodes.find(reply.record_id)
    assert episode.content["candidate"] == reply.text  # reflex answer is the fast reply


def test_short_trigger_escalates_from_reflex_to_deep(tmp_path):
    """A fast-tier low-confidence flag must escalate to the deep tier (§2)."""
    substrate = StubSubstrate()
    mind = Mind(substrate=substrate, state_dir=tmp_path / "mind")
    reply = mind.step("make it ambiguous")  # 3 words, stakes 0 → reflex first
    assert not reply.success
    assert reply.confidence_label == "speculative"
    assert substrate.fast_calls == 2  # reflex attempt + pre-deep candidate
    assert substrate.deep_calls == 1  # escalation happened
    decisions = [e for e in mind.trace.events if e.kind == "decision"]
    assert decisions[-1].payload["depth"] == "deep"


def test_high_stakes_uses_deep_verified(tmp_path):
    """High-stakes phrasing selects deep_verified (deep + pre-flight, §4.7)."""
    substrate = StubSubstrate()
    mind = Mind(substrate=substrate, state_dir=tmp_path / "mind")
    reply = mind.step("please delete the permanent folder forever")
    assert reply.success
    assert substrate.deep_calls == 1
    decisions = [e for e in mind.trace.events if e.kind == "decision"]
    assert decisions[-1].payload["depth"] == "deep_verified"
    assert "concerns" in decisions[-1].payload  # the devil's advocate ran


def test_long_routine_questions_use_deep_not_reflex(tmp_path):
    substrate = StubSubstrate()
    mind = Mind(substrate=substrate, state_dir=tmp_path / "mind")
    mind.step("what is the best way to structure a long term project like this one")
    assert substrate.deep_calls == 1
    decisions = [e for e in mind.trace.events if e.kind == "decision"]
    assert decisions[-1].payload["depth"] == "deep"


def test_idle_exploration_revisits_open_questions_once(tmp_path):
    """Row 21: budgeted idle cognition picks an open question, once each."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("the context is missing here")  # records an open question (T5)
    open_questions = mind.memory.query(kind="self", type="question", status="open")
    assert len(open_questions) == 1

    notes = mind.tick()
    assert notes["curiosity"]  # idle pass found something to explore
    assert open_questions[0].content.get("explored_at")  # marked explored

    # a second idle pass does not re-explore the same question
    notes2 = mind.tick()
    assert notes2["curiosity"] == []

    # a new question becomes explorable again
    mind.step("please do something ambiguous with the reports")
    notes3 = mind.tick()
    assert notes3["curiosity"]
    trace = mind.trace.events
    assert any(e.kind == "curiosity" for e in trace)
