"""Cognitive-loop tests: labels, failure taxonomy, episodes, trace (§4.1, §8)."""

from beanie import Mind
from beanie.substrate import StubSubstrate
from beanie.trace import FailureTaxonomy


def make_mind(tmp_path):
    return Mind(substrate=StubSubstrate(), state_dir=tmp_path / "mind")


def test_confident_turn_is_labeled_and_recorded(tmp_path):
    mind = make_mind(tmp_path)
    reply = mind.step("hello there")
    assert reply.success is True
    assert reply.confidence_label == "highly confident"
    assert reply.text.startswith("Received:")
    assert mind.episodes.count() == 1
    episode = mind.episodes.all()[0]
    assert episode.content["user_text"] == "hello there"
    assert episode.content["success"] is True
    assert episode.id == reply.record_id


def test_ambiguous_turn_carries_root_cause_tag_everywhere(tmp_path):
    mind = make_mind(tmp_path)
    reply = mind.step("please do something ambiguous here")
    assert reply.success is False
    assert reply.failure == FailureTaxonomy.PROMPT_AMBIGUITY
    assert reply.confidence_label == "speculative"
    # tag lands in the trace (measurement protocol, ARCHITECTURE §8)
    outcome = [e for e in mind.trace.events_for(reply.turn_id) if e.kind == "outcome"][0]
    assert outcome.failure == FailureTaxonomy.PROMPT_AMBIGUITY
    # and in the episode content (store keeps outcome detail)
    episode = mind.episodes.find(reply.record_id)
    assert episode.content["failure"] == "prompt_ambiguity"
    assert mind.trace.failures_by_kind() == {"prompt_ambiguity": 1}


def test_each_failure_taxonomy_category_is_mapped(tmp_path):
    mind = make_mind(tmp_path)
    cases = {
        "contradict what I said": FailureTaxonomy.EVIDENCE_MISWEIGHTING,
        "the context is missing here": FailureTaxonomy.MISSING_CONTEXT,
        "the causal link is unknown": FailureTaxonomy.CAUSAL_MIS_MODELING,
        "tool-error happened": FailureTaxonomy.TOOL_EXECUTION_ERROR,
        "??": FailureTaxonomy.PROMPT_AMBIGUITY,
    }
    for text, expected in cases.items():
        reply = mind.step(text)
        assert reply.failure == expected, f"{text!r} should tag {expected.value}, got {reply.failure}"
    counts = mind.trace.failures_by_kind()
    assert counts == {failure.value: 1 for failure in cases.values()}
    # every failure reply is honest about low confidence (VISION property 7)
    assert all(e.failure != FailureTaxonomy.NONE for e in mind.trace.events if e.kind == "outcome")


def test_effort_depth_is_recorded_per_turn(tmp_path):
    """Effort allocation (§4.6): every decision records which depth ran."""
    mind = make_mind(tmp_path)
    mind.step("hello")  # reflex
    mind.step("please do something ambiguous here")  # reflex → deep (flag)
    mind.step("delete the permanent file right now please")  # stakes ≥ 2 → deep_verified
    decisions = [e for e in mind.trace.events if e.kind == "decision"]
    assert decisions[0].payload["depth"] == "reflex"
    assert decisions[1].payload["depth"] == "deep"
    assert decisions[2].payload["depth"] == "deep_verified"


def test_trace_and_episodes_persist_to_disk(tmp_path):
    state_dir = tmp_path / "mind"
    mind = Mind(state_dir=state_dir)
    mind.step("first")
    mind.step("ambiguous request here")
    assert (state_dir / "trace.jsonl").exists()
    assert (state_dir / "episodes.jsonl").exists()
    assert (state_dir / "mind_state.json").exists()
    lines = (state_dir / "trace.jsonl").read_text(encoding="utf-8").strip().splitlines()
    # 3 events per turn: perception, decision, outcome
    assert len(lines) == 6
