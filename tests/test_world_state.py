"""World-model tests: object permanence & location tracking (row 11 / Domain A),
world-factored answers, proactive re-check, idle sensing content (row 21)."""

from beanie import Mind
from beanie.learning import DemoAction


def _seed(body, files: dict[str, str]) -> None:
    for path, text in files.items():
        body.run("write_file", {"path": path, "text": text})


def _teach(mind):
    _seed(mind.body, {"downloads/seed.pdf": "s"})
    mind.body.run("mkdir", {"dir": "docs"})
    proposal = mind.demonstrate(
        title="pdfs to docs", goal_class="organize files",
        actions=[DemoAction("move_file", {"src": "downloads/seed.pdf", "dst": "docs"})],
    )
    mind.confirm_skill(proposal.skill_id)


def test_object_permanence_after_own_action(tmp_path):
    """After moving a file, the mind knows where it is without re-listing."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _teach(mind)
    _seed(mind.body, {"downloads/report.pdf": "r"})
    result = mind.perform_goal("organize files", base_dir="downloads")
    assert result.outcome == "success"

    reply = mind.step("where is report.pdf?")
    assert reply.success
    assert "docs/report.pdf" in reply.text  # from the world model, not a scan
    # and a located_at fact exists on record
    facts = mind.memory.query(kind="semantic", type="fact", subject="report.pdf", predicate="located_at")
    assert facts and facts[0].content["object"] == "docs/report.pdf"


def test_simulation_never_moves_objects_in_world_model(tmp_path):
    """A what-if must not change where the mind thinks things are."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _seed(mind.body, {"downloads/invoice.pdf": "x"})
    mind.body.run("mkdir", {"dir": "docs"})
    reply = mind.step("what if i moved invoice.pdf to docs")
    assert reply.success and "would move" in reply.text
    facts = mind.memory.query(kind="semantic", type="fact", subject="invoice.pdf", predicate="located_at")
    # the fact may exist from seeding observation — but if it does, it must
    # still point at the original location, never the simulated one
    if facts:
        assert facts[0].content["object"] != "docs/invoice.pdf"
    # and the physical file is still in downloads
    assert "downloads/invoice.pdf" in mind.body.run("snapshot")["tree"]


def test_observed_add_then_where_is(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    assert mind.observe() == []  # baseline
    mind.body.run("write_file", {"path": "inbox/letter.txt", "text": "hi"})
    mind.body.run("mkdir", {"dir": "inbox"})  # ensure dir exists for snapshot
    events = mind.observe()
    assert any(e["kind"] == "add" for e in events)
    reply = mind.step("where is letter.txt?")
    assert reply.success
    assert "inbox/letter.txt" in reply.text


def test_observed_removal_is_honest_afterwards(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.body.run("mkdir", {"dir": "inbox"})
    mind.body.run("write_file", {"path": "inbox/letter.txt", "text": "hi"})
    mind.observe()  # sees the add
    assert "letter.txt" in mind.step("where is letter.txt?").text

    import shutil
    shutil.rmtree(mind.body.root / "inbox")  # external removal, unobserved...
    mind.body.run("write_file", {"path": "other.txt", "text": "trigger"})
    mind.observe()  # ...but the next observation pass sees it disappear
    reply = mind.step("where is letter.txt?")
    assert "couldn't find it" in reply.text or "no longer" in reply.text
    fact = mind.memory.query(kind="semantic", type="fact", subject="letter.txt", predicate="located_at")[-1]
    assert fact.content.get("stale") or fact.confidence <= 0.1


def test_where_is_unknown_thing_falls_through_to_normal_turn(tmp_path):
    """'where is the meaning of life' is not a world query — normal cognition."""
    mind = Mind(state_dir=tmp_path / "mind")
    reply = mind.step("where is the best sushi place")
    # falls through to the default substrate (no location fact, not in body)
    assert reply.success
    assert "sushi" not in reply.text or reply.text.startswith("Received")
    assert not mind.memory.query(kind="semantic", type="fact", subject="the best sushi place")


def test_idle_tick_inspects_environment_directories(tmp_path):
    """Row 21: idle cognition senses the world when no question is pending."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.body.run("mkdir", {"dir": "downloads"})
    mind.body.run("write_file", {"path": "downloads/a.pdf", "text": "x"})
    notes = mind.tick()
    assert notes["curiosity"]  # something was explored
    assert any("inspected" in item for item in notes["curiosity"])
    # a perception episode was recorded (real sensing content)
    inspections = [e for e in mind.episodes.all() if e.content.get("event", {}).get("kind") == "inspect"]
    assert inspections and inspections[0].content["event"]["dir"] == "downloads"
    # second tick explores nothing new (no loop)
    assert mind.tick()["curiosity"] == []
