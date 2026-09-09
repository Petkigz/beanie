"""Restart continuity: closing is sleep, not death (VISION property 1)."""

from beanie import Mind
from beanie.substrate import StubSubstrate


def test_mind_continues_across_instances_over_same_state_dir(tmp_path):
    state_dir = tmp_path / "mind"

    # "session" one: two turns
    mind1 = Mind(substrate=StubSubstrate(), state_dir=state_dir)
    r1 = mind1.step("first message")
    r2 = mind1.step("second message")
    assert r1.turn_id == "turn-00001" and r1.record_id == "rec-00001"
    assert r2.turn_id == "turn-00002" and r2.record_id == "rec-00002"
    assert mind1.episodes.count() == 2

    # "session" two: a new process over the same directory
    mind2 = Mind(substrate=StubSubstrate(), state_dir=state_dir)
    assert mind2.episodes.count() == 2, "prior episodes must be remembered"
    assert len(mind2.recall(limit=8)) == 2
    r3 = mind2.step("third message")
    # ids continue — no collisions, no reset to factory defaults
    assert r3.turn_id == "turn-00003"
    assert r3.record_id == "rec-00003"
    assert mind2.episodes.count() == 3
    # and the first mind's view, reopened, still sees everything
    mind3 = Mind.open(state_dir)
    assert mind3.episodes.count() == 3


def test_each_mind_state_dir_is_independent(tmp_path):
    a = Mind(state_dir=tmp_path / "a")
    b = Mind(state_dir=tmp_path / "b")
    a.step("only a hears this")
    assert a.episodes.count() == 1
    assert b.episodes.count() == 0
