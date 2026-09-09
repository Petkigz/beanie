"""T-test battery: T1, T3, T9 — demonstration learning, self-correction, strategy revision."""

import pytest

from beanie import Mind
from beanie.learning import DemoAction


@pytest.fixture
def mind(tmp_path):
    return Mind(substrate=None, state_dir=tmp_path / "mind", authority="allow")


def _seed(body, files: dict[str, str]) -> None:
    for path, text in files.items():
        body.run("write_file", {"path": path, "text": text})


def _teach_organize(mind, files, actions, goal_class="organize downloads", title="organize downloads by type"):
    _seed(mind.body, files)
    proposal = mind.demonstrate(
        title=title,
        goal_class=goal_class,
        actions=[DemoAction(capability=a["capability"], args=a["args"]) for a in actions],
    )
    assert "?" in proposal.confirm_question  # a question, not a form
    mind.confirm_skill(proposal.skill_id)
    return proposal


def test_t1_learns_from_one_demonstration_and_transfers(tmp_path):
    """T1: one demonstration → performed later in a new context."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    # demonstration folder
    _seed(mind.body, {
        "downloads/invoice.pdf": "invoice",
        "downloads/photo.jpg": "photo",
        "downloads/notes.txt": "notes",
    })
    mind.body.run("mkdir", {"dir": "docs"})
    mind.body.run("mkdir", {"dir": "images"})
    proposal = mind.demonstrate(
        title="organize downloads by type",
        goal_class="organize downloads",
        actions=[
            DemoAction("move_file", {"src": "downloads/invoice.pdf", "dst": "docs"}),
            DemoAction("move_file", {"src": "downloads/photo.jpg", "dst": "images"}),
        ],
    )
    assert ".pdf → docs" in proposal.confirm_question
    assert ".jpg → images" in proposal.confirm_question
    mind.confirm_skill(proposal.skill_id)

    # NEW folder, different files, including an unmapped extension (transfer)
    _seed(mind.body, {"downloads2/report.pdf": "r", "downloads2/pic.jpg": "p", "downloads2/meme.png": "m"})
    mind.body.run("mkdir", {"dir": "docs"})
    mind.body.run("mkdir", {"dir": "images"})

    result = mind.perform_goal("organize downloads", base_dir="downloads2")
    assert result.outcome == "success", result
    tree = mind.body.run("snapshot")["tree"]
    assert "docs/report.pdf" in tree
    assert "images/pic.jpg" in tree
    assert "downloads2/meme.png" in tree  # unmapped → untouched, honest
    # the skill learned nothing it did not see in the demo
    skill = mind.memory.find(result.skill_id)
    assert set(skill.content["mapping"]) == {"pdf", "jpg"}


def test_t3_self_corrects_after_failure_and_records_lesson(tmp_path):
    """T3: failed move (missing destination) → repair → retry → consolidated."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    proposal = mind.demonstrate(
        title="file pdfs",
        goal_class="organize downloads",
        actions=[DemoAction("move_file", {"src": "downloads/a.pdf", "dst": "docs"})],
    )
    mind.confirm_skill(proposal.skill_id)
    # docs/ does NOT exist — the plan will fail on the first attempt
    _seed(mind.body, {"downloads/only.pdf": "x"})

    result = mind.perform_goal("organize downloads", base_dir="downloads")
    assert result.outcome == "success", result
    assert result.repairs == 1
    assert "docs/only.pdf" in mind.body.run("snapshot")["tree"]
    # the failure mode + fix was recorded on the skill (T3 consolidation)
    skill = mind.memory.find(result.skill_id)
    modes = skill.content.get("failure_modes", [])
    assert any(mode.get("taxonomy") == "missing_destination" for mode in modes)
    # a second run now needs no repair: the lesson changed future behavior
    _seed(mind.body, {"downloads/b.pdf": "y"})
    second = mind.perform_goal("organize downloads", base_dir="downloads")
    assert second.outcome == "success"
    assert second.repairs == 0


def test_t9_correction_revises_strategy_not_just_the_fact(tmp_path):
    """T9: "no, X goes into Y" changes the skill → future similar cases differ."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    proposal = mind.demonstrate(
        title="sort images",
        goal_class="organize downloads",
        actions=[DemoAction("move_file", {"src": "downloads/a.jpg", "dst": "images"})],
    )
    mind.confirm_skill(proposal.skill_id)

    # owner corrects the rule
    reply = mind.step("no, jpg files go into photos/")
    assert reply.success
    assert "photos" in reply.text

    skill = mind.memory.query(kind="procedural", type="skill", status="active")[-1]
    assert skill.content["mapping"].get("jpg") == "photos/"
    assert any("owner correction" in r.reason for r in skill.revision_history)

    # perform in a NEW context → the corrected strategy is used
    _seed(mind.body, {"new/pic.jpg": "p"})
    mind.body.run("mkdir", {"dir": "photos"})
    mind.body.run("mkdir", {"dir": "images"})
    result = mind.perform_goal("organize downloads", base_dir="new")
    assert result.outcome == "success"
    tree = mind.body.run("snapshot")["tree"]
    assert "photos/pic.jpg" in tree
    assert "images/pic.jpg" not in tree
    # correction is recorded as a learning event
    assert any(e.content.get("was_correction") and e.content.get("strategy_revision") for e in mind.episodes.all())


def test_demonstration_proposal_can_be_rejected(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    proposal = mind.demonstrate(
        title="noisy demo",
        goal_class="organize downloads",
        actions=[DemoAction("move_file", {"src": "downloads/a.txt", "dst": "texts"})],
    )
    mind.reject_skill(proposal.skill_id, "not the rule I want")
    skill = mind.memory.find(proposal.skill_id)
    assert skill.content["status"] == "rejected"
    assert mind.learner.active_skills() == []  # nothing silently kept
