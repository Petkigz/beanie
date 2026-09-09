"""Introspection (row 35), low-confidence fallback (Q13), effort-policy
adaptation (T13), knowledge transfer (Q15), meta-learning (row 24)."""

from beanie import Mind
from beanie.learning import DemoAction


def _teach(mind, title, goal_class, action) -> None:
    mind.body.run("mkdir", {"dir": "docs"})
    mind.body.run("write_file", {"path": "downloads/a.pdf", "text": "x"})
    proposal = mind.demonstrate(title=title, goal_class=goal_class, actions=[action])
    mind.confirm_skill(proposal.skill_id)


# -- introspection (row 35) --------------------------------------------------

def test_introspection_open_questions_and_lessons(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    unsure = mind.step("what are you unsure about?")
    assert unsure.success
    assert "unresolved questions" in unsure.text  # honest empty state

    mind.step("the context is missing here")  # leaves an open question
    reply = mind.step("what are you unsure about?")
    assert "missing" in reply.text or "unresolved" in reply.text

    mind.step("wait, that's wrong about the thing")
    mind.reflector.reflect(mind.episodes.all())  # distill a lesson
    learned = mind.step("what have you learned recently?")
    assert learned.success
    assert "learned" in learned.text.lower()


def test_introspection_capabilities_and_identity(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    can = mind.step("what can you do?")
    assert can.success
    assert "write_file" in can.text and "list_files" in can.text  # from the body
    _teach(mind, "pdfs to docs", "organize files",
           DemoAction("move_file", {"src": "downloads/a.pdf", "dst": "docs"}))
    can2 = mind.step("what can you do?")
    assert "organize files" in can2.text  # learned skill surfaced

    me = mind.step("tell me about yourself")
    assert me.success
    assert "Beanie" in me.text
    assert "episodes" in me.text
    assert "not by a script" in me.text  # identity from history, not a prompt


# -- low-confidence fallback (Q13 panic button) ------------------------------

def test_low_confidence_success_gets_honest_caveat(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("the report status is missing")  # → open question about report
    for _ in range(3):
        mind.step("wait, that's wrong about the report")  # corrections pile up
    reply = mind.step("tell me about the report status")
    assert reply.success
    assert reply.confidence < 0.55
    assert "not fully confident" in reply.text  # the honest caveat is shown
    # and the residual gap is recorded (not left as a silent confident answer)
    assert mind.memory.query(kind="self", type="question", status="open")


# -- effort policy adaptation (T13 loop) --------------------------------------

def test_effort_policy_tightens_after_reflex_class_failures(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    assert mind.policy.word_limit == 6
    # generate reflex-class failures: short utterances that flag and fail
    short_failures = ["make it ambiguous", "that contradicts", "tool-error now"]
    for i in range(10):
        mind.step(short_failures[i % len(short_failures)])  # ≤4 words each
    change = mind.policy.adapt(mind.trace.events)
    assert change  # the reflex budget was tightened
    assert "tightened" in change
    assert mind.policy.word_limit < 6
    # the change is recorded with a reason (audit trail)
    stored = mind.memory.query(kind="self", type="effort_policy")[-1]
    assert stored.content["word_limit"] == mind.policy.word_limit
    assert stored.content["history"]


def test_effort_policy_widens_after_clean_reflex_runs(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.policy.word_limit = 3  # artificially tight
    for i in range(10):
        mind.step("hi there")  # 2 words, always succeeds reflexively
    change = mind.policy.adapt(mind.trace.events)
    assert change and "widened" in change
    assert mind.policy.word_limit == 4


def test_policy_survives_restart(tmp_path):
    state_dir = tmp_path / "mind"
    mind = Mind(state_dir=state_dir)
    mind.policy.word_limit = 4
    mind.policy._store("manual test adjustment")
    reopened = Mind(state_dir=state_dir)
    assert reopened.policy.word_limit == 4


# -- knowledge transfer between minds (Q15) -----------------------------------

def test_knowledge_transfer_teaches_another_mind(tmp_path):
    a = Mind(state_dir=tmp_path / "a", authority="allow")
    _teach(a, "pdfs to docs", "organize files",
           DemoAction("move_file", {"src": "downloads/a.pdf", "dst": "docs"}))
    a.step("remember that client_omega uses postgres")

    bundle = a.export_knowledge()
    assert len(bundle["skills"]) == 1
    assert any(f["subject"] == "client_omega" for f in bundle["facts"])

    b = Mind(state_dir=tmp_path / "b", authority="allow")  # a fresh, empty mind
    assert b.learner.active_skills() == []
    counts = b.import_knowledge(bundle)
    assert counts == {"skills": 1, "facts": 1, "preferences": 0}

    # B can now perform the skill it never saw demonstrated (know-how travels)
    b.body.run("mkdir", {"dir": "docs"})
    b.body.run("write_file", {"path": "downloads/x.pdf", "text": "x"})
    result = b.perform_goal("organize files", base_dir="downloads")
    assert result.outcome == "success"
    assert "docs/x.pdf" in b.body.run("snapshot")["tree"]
    # and it knows the fact (semantic knowledge travels)
    assert b.memory.query(kind="semantic", type="fact", subject="client_omega")


def test_transfer_marks_learned_via_transfer(tmp_path):
    a = Mind(state_dir=tmp_path / "a", authority="allow")
    _teach(a, "pdfs to docs", "organize files",
           DemoAction("move_file", {"src": "downloads/a.pdf", "dst": "docs"}))
    b = Mind(state_dir=tmp_path / "b")
    b.import_knowledge(a.export_knowledge())
    skill = b.learner.active_skills()[0]
    assert skill.content["learned_via"] == "transfer"
    assert any(e.kind == "learning" for e in b.trace.events)


# -- meta-learning (row 24) ----------------------------------------------------

def test_meta_learning_family_boosts_later_proposals(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind", authority="allow")
    _teach(mind, "pdfs to docs", "organize files",
           DemoAction("move_file", {"src": "downloads/a.pdf", "dst": "docs"}))
    # second skill in the same family
    _teach(mind, "texts to texts", "organize files",
           DemoAction("move_file", {"src": "downloads/b.txt", "dst": "texts"}))
    # third proposal in the family arrives with a meta boost
    mind.body.run("write_file", {"path": "downloads/c.csv", "text": "c"})
    proposal = mind.demonstrate(
        title="csvs to data", goal_class="organize files",
        actions=[DemoAction("move_file", {"src": "downloads/c.csv", "dst": "data"})],
    )
    assert proposal.entry.confidence == 0.6  # boosted by prior family skills
    assert "similar task" in proposal.confirm_question
    # the meta-lesson is recorded once (learning how it learns, row 24)
    meta_lessons = [
        l for l in mind.memory.query(kind="self", type="lesson")
        if str(l.content.get("text", "")).startswith("meta:")
    ]
    assert len(meta_lessons) == 1
    assert "organize files" in meta_lessons[0].content["text"]
