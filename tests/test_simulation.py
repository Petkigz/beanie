"""Simulation & counterfactual tests (rows 10–11, ARCHITECTURE §7)."""

from beanie import Mind
from beanie.learning import DemoAction


def _seed(body, files: dict[str, str]) -> None:
    for path, text in files.items():
        body.run("write_file", {"path": path, "text": text})


def _teach_pdf_skill(mind) -> None:
    _seed(mind.body, {"downloads/seed.pdf": "s"})
    mind.body.run("mkdir", {"dir": "docs"})
    proposal = mind.demonstrate(
        title="pdfs to docs",
        goal_class="organize files",
        actions=[DemoAction("move_file", {"src": "downloads/seed.pdf", "dst": "docs"})],
    )
    mind.confirm_skill(proposal.skill_id)


def test_predict_goal_reports_outcome_without_touching_body(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _teach_pdf_skill(mind)
    _seed(mind.body, {"downloads/report.pdf": "r"})

    prediction = mind.predict_goal("organize files", base_dir="downloads")
    assert prediction["known"] is True
    assert prediction["ok"] is True
    assert any("report.pdf" in p for p in prediction["moved"])

    # the body was never modified by prediction
    tree = mind.body.run("snapshot")["tree"]
    assert "downloads/report.pdf" in tree  # still there


def test_predict_goal_missing_folder_would_be_created_first(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    # teach with docs existing, then delete docs so the world changed
    _seed(mind.body, {"downloads/seed.pdf": "s"})
    mind.body.run("mkdir", {"dir": "docs"})
    proposal = mind.demonstrate(
        title="pdfs to docs", goal_class="organize files",
        actions=[DemoAction("move_file", {"src": "downloads/seed.pdf", "dst": "docs"})],
    )
    mind.confirm_skill(proposal.skill_id)
    import shutil
    shutil.rmtree(mind.state_dir / "sandbox" / "docs")

    _seed(mind.body, {"downloads/a.pdf": "a"})
    prediction = mind.predict_goal("organize files", base_dir="downloads")
    assert prediction["ok"] is True
    assert any("docs" in d for d in prediction["created_dirs"])
    assert prediction["summary"]  # says a folder would be created first
    # still nothing executed
    assert "docs/a.pdf" not in mind.body.run("snapshot")["tree"]


def test_what_if_directive_predicts_move_and_leaves_body_alone(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _seed(mind.body, {"downloads/invoice.pdf": "x"})
    mind.body.run("mkdir", {"dir": "docs"})

    reply = mind.step("what if i moved invoice.pdf to docs")
    assert reply.success
    assert "would move" in reply.text
    assert "docs" in reply.text
    # nothing actually moved
    tree = mind.body.run("snapshot")["tree"]
    assert "downloads/invoice.pdf" in tree
    assert "docs/invoice.pdf" not in tree


def test_what_if_missing_folder_reports_would_not_move(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _seed(mind.body, {"downloads/invoice.pdf": "x"})
    reply = mind.step("what if i moved invoice.pdf to videos")
    assert not reply.success
    assert "does not exist" in reply.text
    # and the nonexistent-file case is honest too
    reply2 = mind.step("what if i moved nope.png to docs")
    assert not reply2.success
    assert "no file named" in reply2.text
