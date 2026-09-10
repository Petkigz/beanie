"""Growing autonomy (row 29/§5): permission walls become counted asks, denies are respected."""

from beanie import Mind
from beanie.learning import DemoAction


def _teach(mind: Mind) -> None:
    mind.body.run("mkdir", {"dir": "downloads"})
    mind.body.run("mkdir", {"dir": "docs"})
    mind.body.run("write_file", {"path": "downloads/a.pdf", "text": "x"})
    proposal = mind.demonstrate(
        title="pdfs to docs", goal_class="organize files",
        actions=[DemoAction("move_file", {"src": "downloads/a.pdf", "dst": "docs"})],
    )
    mind.confirm_skill(proposal.skill_id)


def test_permission_wall_becomes_a_counted_ask(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="ask")  # undecided: the fourth state
    _teach(mind)
    first = mind.perform_goal("organize files", base_dir="downloads")
    assert first.outcome == "needs_permission"
    assert first.permission_question is not None
    assert "you may list_files" in first.permission_question  # actionable, not vague

    second = mind.perform_goal("organize files", base_dir="downloads")
    assert "2nd time" in second.permission_question  # autonomy pressure is counted
    assert len(mind.pending_permission_requests()) == 1  # one standing request, not two

    # it is surfaced to the owner on the next ordinary turn, once
    turn = mind.step("hello there")
    assert any("standing rule" in q for q in turn.questions)
    assert mind.step("hello again").questions == ()


def test_owner_answer_resolves_the_standing_request(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="ask")
    _teach(mind)
    mind.perform_goal("organize files", base_dir="downloads")
    assert mind.pending_permission_requests()

    grant = mind.step("you may list_files")
    assert "I may do that now" in grant.text
    assert mind.pending_permission_requests() == []
    answered = mind.memory.query(kind="owner_model", type="permission_request", status="answered")
    assert answered and answered[0].content["answer"] == "allow"


def test_explicit_deny_is_respected_without_nagging(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="ask")
    _teach(mind)
    mind.step("never use list_files")
    blocked = mind.perform_goal("organize files", base_dir="downloads")
    assert blocked.outcome == "needs_permission"
    assert blocked.permission_question is None       # the owner already decided
    assert mind.pending_permission_requests() == []  # nothing proposed again
    assert mind.step("hello there").questions == ()


def test_granting_then_running_the_plan(tmp_path):
    """The point of asking: once the owner answers, the work actually happens."""
    mind = Mind(state_dir=tmp_path / "mind", authority="ask")
    _teach(mind)
    mind.perform_goal("organize files", base_dir="downloads")
    for statement in ("you may list_files", "you may mkdir", "you may move_file", "you may snapshot"):
        mind.step(statement)
    result = mind.perform_goal("organize files", base_dir="downloads")
    assert result.outcome == "success"
    assert "docs/a.pdf" in mind.body.run("snapshot")["tree"]
