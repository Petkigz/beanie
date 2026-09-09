"""Curiosity loop wiring (T5): gaps become open questions, no silent guesses."""

from beanie import Mind


def test_t5_unresolved_request_records_open_question(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    reply = mind.step("the context is missing here")
    assert not reply.success
    questions = mind.memory.query(kind="self", type="question", status="open")
    assert len(questions) == 1
    assert "missing" in questions[0].content["text"]


def test_t5_open_questions_are_deduplicated(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("the context is missing here")
    mind.step("the context is missing here")
    questions = mind.memory.query(kind="self", type="question", status="open")
    assert len(questions) == 1


def test_t5_unknown_goal_records_gap(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    result = mind.perform_goal("defragment the database", base_dir="downloads")
    assert result.outcome == "needs_information"
    questions = mind.memory.query(kind="self", type="question", status="open")
    assert any("defragment the database" in q.content["text"] for q in questions)
