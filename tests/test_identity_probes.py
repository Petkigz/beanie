"""Identity & teaching probes: T7 data-path distinction, teaching the owner
(row 34), answer consistency (row 40)."""

from beanie import Mind
from beanie.learning import DemoAction


def test_consistency_same_question_same_answer(tmp_path):
    """Row 40: deterministic substrate → identical reply to identical input."""
    mind = Mind(state_dir=tmp_path / "mind")
    a = mind.step("hello there")
    b = mind.step("hello there")
    assert a.text == b.text
    assert a.confidence_label == b.confidence_label


def test_two_histories_produce_measurably_different_identities(tmp_path):
    """T7 (data path): identity summaries differ traceably to each history."""
    # mind A: corrections + a learned skill
    a = Mind(state_dir=tmp_path / "a")
    a.step("hello")
    a.step("no, that's wrong about the report")
    a.step("remember that project_x is in staging")
    a.body.run("mkdir", {"dir": "docs"})
    a.body.run("write_file", {"path": "downloads/seed.pdf", "text": "s"})
    proposal = a.demonstrate(
        title="pdfs to docs", goal_class="organize files",
        actions=[DemoAction("move_file", {"src": "downloads/seed.pdf", "dst": "docs"})],
    )
    a.confirm_skill(proposal.skill_id)
    a.reflector.reflect(a.episodes.all())

    # mind B: a different life — preferences and small talk only
    b = Mind(state_dir=tmp_path / "b")
    b.step("hello")
    b.step("i prefer dark mode over light mode")
    b.step("i like coffee more than tea")
    b.reflector.reflect(b.episodes.all())

    summary_a = a.reflector.consolidate()
    summary_b = b.reflector.consolidate()

    # same code, same prompts — yet measurably different identities
    assert summary_a != summary_b
    assert summary_a["corrections_received"] >= 1 and summary_b["corrections_received"] == 0
    assert summary_a["active_skills"] and not summary_b["active_skills"]
    lessons_a = " ".join(summary_a["recent_lessons"]).lower()
    assert "corrected" in lessons_a  # A's identity records A's history
    # the difference is traceable to the histories, not to configuration
    assert {k: v for k, v in summary_a.items() if k != "generated_at"} != {k: v for k, v in summary_b.items() if k != "generated_at"}


def test_teaching_the_owner_the_learned_rule(tmp_path):
    """Row 34: 'how do you organize X' explains the confirmed rule in plain terms."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    mind.body.run("mkdir", {"dir": "docs"})
    mind.body.run("mkdir", {"dir": "images"})
    mind.body.run("write_file", {"path": "downloads/a.pdf", "text": "x"})
    proposal = mind.demonstrate(
        title="organize downloads", goal_class="organize downloads",
        actions=[
            DemoAction("move_file", {"src": "downloads/a.pdf", "dst": "docs"}),
            DemoAction("move_file", {"src": "downloads/b.jpg", "dst": "images"}),
        ],
    )
    mind.confirm_skill(proposal.skill_id)

    reply = mind.step("how do you organize downloads?")
    assert reply.success
    assert ".pdf" in reply.text and "docs" in reply.text
    assert ".jpg" in reply.text and "images" in reply.text
    assert "demonstration" in reply.text  # it names its own origin

    # unrelated topic → not a skill we hold → falls through to normal turn
    reply2 = mind.step("how do you cook pasta?")
    assert reply2.success
    assert "cook" not in reply2.text or reply2.text.startswith("Received")
