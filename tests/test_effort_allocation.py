"""Effort allocation (§4.6) + budgeted idle exploration (R3.24 / register row 21)
+ the bounded pre-flight adversarial pass (§4.7 / register row 14)."""

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
    assert substrate.fast_calls == 1  # the flagged candidate is reused, not re-bought
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
    # the pre-flight pass really ran: on a clean, confident turn it reports
    # finding no contradicting evidence — a mere "key exists" assertion let the
    # check die silently once before (FailureTaxonomy.NONE is truthy)
    concerns = decisions[-1].payload["concerns"]
    assert concerns and all(c.get("kind") == "none" for c in concerns)


def test_pre_flight_finds_contradiction_history_about_the_subject(tmp_path):
    """§4.7 regression: the adversarial pass must see the stored contradiction.

    Row 14 wired but inert (a truthiness bug) until 2026-09-10: with a
    supersession on record, a high-stakes turn about that subject must surface
    a named concern, lose confidence, and cite the losing alternative in its
    explanation (§4.5/T10).
    """
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("remember that london is lovely")
    mind.step("remember that london is rainy")  # newer statement supersedes (T2)
    reply = mind.step("please delete the permanent london folder forever")
    assert reply.success

    decisions = [e for e in mind.trace.events if e.kind == "decision"]
    concerns = decisions[-1].payload["concerns"]
    assert any(c.get("kind") == "contradiction_history" for c in concerns), concerns
    assert decisions[-1].payload["residual"]  # the concern is on the record
    # a real concern costs real confidence (bounded §4.7): below the unflagged 0.95→0.97
    assert decisions[-1].payload["calibration"].get("concerns")

    explanation = mind.explain(turn_id=reply.turn_id)
    assert "Alternatives I considered and set aside" in explanation
    assert "contradiction_history" in explanation


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
