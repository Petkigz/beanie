"""Idle curiosity with content (row 21): the idle budget investigates an open
question against the environment — and never closes a gap on a keyword match."""

from beanie import Mind


def test_idle_investigation_searches_the_environment(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.body.run("mkdir", {"dir": "notes"})
    mind.body.run("write_file", {"path": "notes/context.txt", "text": "the context is in the config file"})
    mind.step("the context is missing here")  # leaves an open question (T5)

    notes = mind.tick()
    assert any("candidate evidence" in item and "notes/context.txt" in item for item in notes["curiosity"])

    question = mind.memory.query(kind="self", type="question")[0]
    investigation = question.content["investigation"]
    assert investigation["files_searched"] >= 1
    assert "notes/context.txt" in [m["path"] for m in investigation["matches"]]
    assert "context" in investigation["terms"]

    # the search is lived experience (a perception episode), not bookkeeping
    episodes = [e for e in mind.episodes.all()
                if isinstance(e.content.get("event"), dict) and e.content["event"].get("kind") == "investigation"]
    assert episodes
    assert episodes[0].source.value == "perception"
    assert episodes[0].content["event"]["question_id"] == question.id

    # a keyword match is not proof: the gap stays open for real evidence (T5)
    assert question.content["status"] == "open"
    assert not mind.memory.query(kind="semantic", type="fact", subject="context")


def test_idle_investigation_without_evidence_is_honest(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("the context is missing here")
    notes = mind.tick()
    assert any("no evidence in the sandbox" in item for item in notes["curiosity"])

    question = mind.memory.query(kind="self", type="question")[0]
    assert question.content["investigation"]["matches"] == []
    assert question.content["status"] == "open"
    assert mind.tick()["curiosity"] == []  # explored once; the budget moves on


def test_real_evidence_still_resolves_the_question(tmp_path):
    """Investigation does not replace the closure paths — real evidence does."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.body.run("mkdir", {"dir": "notes"})
    mind.body.run("write_file", {"path": "notes/context.txt", "text": "the context lives here"})
    mind.step("the context is missing here")
    mind.tick()  # investigate: candidate only
    assert mind.memory.query(kind="self", type="question", status="open")

    mind.step("remember that the context is in the config file")  # real evidence (T5)
    assert mind.memory.query(kind="self", type="question", status="open") == []
    resolved = mind.memory.query(kind="self", type="question", status="resolved")[0]
    assert resolved.content.get("resolved_by")
