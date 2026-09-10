"""T6 — abstraction / analogy (VISION §5, register row 43).

"A concept learned in one domain is correctly applied in a structurally similar
domain it has never seen (e.g. 'grouping by type' learned on downloads, applied
to a photo library)."  These tests pin the lift from demonstrated *extensions*
to *categories*, and the honesty boundary around it.
"""

from beanie import Mind
from beanie.analogy import category_of, demonstrated_categories, infer_destination
from beanie.learning import DemoAction


def _demonstrate_grouping(mind: Mind) -> None:
    for folder in ("downloads", "docs", "images"):
        mind.body.run("mkdir", {"dir": folder})
    mind.body.run("write_file", {"path": "downloads/invoice.pdf", "text": "x"})
    mind.body.run("write_file", {"path": "downloads/photo.jpg", "text": "y"})
    proposal = mind.demonstrate(
        title="group by type", goal_class="organize files",
        actions=[
            DemoAction("move_file", {"src": "downloads/invoice.pdf", "dst": "docs"}),
            DemoAction("move_file", {"src": "downloads/photo.jpg", "dst": "images"}),
        ],
    )
    mind.confirm_skill(proposal.skill_id)


def test_categories_are_structural_not_destinations():
    assert category_of("png") == "images"
    assert category_of(".PNG") == "images"
    assert category_of("docx") == "documents"
    assert category_of("mp3") == "audio"
    assert category_of("weirdkind") is None
    assert demonstrated_categories({"pdf": "docs", "jpg": "images"}) == {
        "documents": "docs", "images": "images",
    }


def test_inference_requires_the_category_to_have_been_demonstrated():
    mapping = {"pdf": "docs", "jpg": "images"}
    destination, reason = infer_destination(mapping, "png")
    assert destination == "images"
    assert "inferred by analogy" in reason and ".jpg" in reason
    assert infer_destination(mapping, "pdf") == ("docs", "demonstrated directly")

    destination, reason = infer_destination(mapping, "mp3")   # audio: never shown
    assert destination is None
    assert "never placed" in reason
    assert infer_destination(mapping, "weirdkind")[0] is None  # unknown kind: no guess


def test_t6_rule_carries_to_a_library_it_has_never_seen(tmp_path):
    """The VISION example: grouping by type learned on downloads, applied to a library."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _demonstrate_grouping(mind)

    for folder in ("library", "docs", "images"):
        mind.body.run("mkdir", {"dir": folder})
    for name in ("sunset.png", "scanned.tiff", "report.docx", "notes.md", "song.mp3", "clip.mov"):
        mind.body.run("write_file", {"path": f"library/{name}", "text": "z"})

    result = mind.perform_goal("organize files", base_dir="library")
    assert result.outcome == "success"
    tree = mind.body.run("snapshot")["tree"]
    # kinds never demonstrated, of demonstrated categories → placed by analogy
    for moved in ("images/sunset.png", "images/scanned.tiff", "docs/report.docx", "docs/notes.md"):
        assert moved in tree, f"{moved} missing: {sorted(tree)}"
    # categories the demonstration never covered stay put, and are asked about
    assert "library/song.mp3" in tree and "library/clip.mov" in tree
    assert sorted(u["extension"] for u in result.unmapped) == ["mov", "mp3"]
    gaps = [q.content["text"] for q in mind.memory.query(kind="self", type="question", status="open")]
    assert any(".mp3" in text and ".mov" in text for text in gaps)


def test_inferred_moves_are_labelled_with_their_reason(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _demonstrate_grouping(mind)
    for folder in ("inbox", "docs", "images"):
        mind.body.run("mkdir", {"dir": folder})
    mind.body.run("write_file", {"path": "inbox/scan.png", "text": "z"})
    result = mind.perform_goal("organize files", base_dir="inbox")
    assert result.inferred and result.inferred[0]["reason"].startswith("inferred by analogy")
    # the plan's own steps carry the reason (visible before execution, §4.1)
    assert any("inferred by analogy" in step.description for step in result.steps)
    assert any(e.kind == "analogy" for e in mind.trace.events)  # auditable in the trace


def test_stored_rule_is_not_polluted_by_inference(tmp_path):
    """Analogy is applied at plan time; the confirmed skill keeps only what was shown."""
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _demonstrate_grouping(mind)
    for folder in ("inbox", "docs", "images"):
        mind.body.run("mkdir", {"dir": folder})
    mind.body.run("write_file", {"path": "inbox/scan.png", "text": "z"})
    mind.perform_goal("organize files", base_dir="inbox")
    skill = mind.learner.active_skills()[0]
    assert set(skill.content["mapping"]) == {"pdf", "jpg"}  # owner-shown facts only


def test_teaching_names_the_generalization(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _demonstrate_grouping(mind)
    reply = mind.step("how do you organize files?")
    assert "document and image files you never showed me" in reply.text
