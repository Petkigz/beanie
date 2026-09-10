"""Explicit usefulness feedback (T13/§8): owner verdicts reach the trace and the
effort policy — cheap answers that never fail by construction can still be wrong."""

from beanie import Mind
from beanie.measure import usefulness_report


def _feedback(mind):
    return [e for e in mind.trace.events if e.kind == "feedback"]


def test_rating_attaches_to_the_judged_turn(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    first = mind.step("hello there")
    rated = mind.step("that was useful")
    assert "useful" in rated.text and "5/5" in rated.text
    events = _feedback(mind)
    assert len(events) == 1
    assert events[0].turn_id == first.turn_id  # the verdict is about that answer
    assert events[0].payload["score"] == 5


def test_negative_verdict_and_non_ratings(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("hello there")
    mind.step("that wasn't helpful")
    assert _feedback(mind)[-1].payload["score"] == 1

    before = len(_feedback(mind))
    # a task continuation that merely starts with "great" is not a rating
    mind.step("great, now do something ambiguous")
    assert len(_feedback(mind)) == before


def test_rating_with_nothing_to_rate_is_honest(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    reply = mind.step("that was useful")
    assert "don't have an answer to rate yet" in reply.text
    assert _feedback(mind) == []  # never invents a turn to attach the verdict to


def test_low_ratings_tighten_the_reflex_budget(tmp_path):
    """The policy hears ratings, not just failures (reflex answers don't fail)."""
    mind = Mind(state_dir=tmp_path / "mind")
    assert mind.policy.word_limit == 6
    for _ in range(6):
        mind.step("hi there")
        mind.step("that wasn't helpful")
    change = mind.policy.adapt(mind.trace.events)
    assert "tightened" in change
    assert mind.policy.word_limit == 5


def test_high_ratings_let_the_budget_widen(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.policy.word_limit = 3
    for _ in range(6):
        mind.step("hi there")
        mind.step("that was useful")
    change = mind.policy.adapt(mind.trace.events)
    assert "widened" in change
    assert mind.policy.word_limit == 4


def test_usefulness_report_buckets_ratings_by_label(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("hello there")
    mind.step("that was useful")
    report = usefulness_report(mind.trace.events)
    assert report["highly confident"] == {"n": 1, "sum": 5, "mean": 5.0}
