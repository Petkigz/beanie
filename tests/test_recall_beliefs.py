"""Relevance-aware retrieval (row 7) & owner-belief layer (row 33) tests."""

from beanie import Mind


def test_recall_surfaces_related_knowledge_before_recency(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    # several unrelated episodes fill the window
    for i in range(6):
        mind.step(f"chatting about topic number {i}")
    # a fact about apollo is on record
    mind.step("remember that apollo is the staging server")

    context = mind.recall("where is apollo running?", limit=8)
    first = context[0]
    assert "apollo" in first["text"].lower()
    assert first["text"].startswith("on record:")
    assert first["record_id"] is not None
    # and the fact itself sits in the semantic store
    facts = mind.memory.query(kind="semantic", type="fact", subject="apollo")
    assert facts and facts[0].id == first["record_id"]


def test_recall_without_text_keeps_recency_behavior(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("first thing")
    mind.step("second thing")
    context = mind.recall(limit=8)
    assert len(context) == 2
    assert all(item["role"] == "user" for item in context)


def test_default_turn_uses_relevant_context(tmp_path):
    """The loop feeds the substrate what the turn is about, not just recency."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("remember that zeta_db runs on port 5433")
    for i in range(5):
        mind.step(f"irrelevant small talk number {i}")
    context = mind.recall("is zeta_db still on port 5433?", limit=8)
    assert any("zeta_db" in c["text"] for c in context)


def test_owner_belief_is_stored_separately_from_facts(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    reply = mind.step("i think server_a is in london")
    assert reply.success
    assert "london" in reply.text
    beliefs = mind.memory.query(kind="owner_model", type="belief", subject="server_a")
    assert len(beliefs) == 1
    assert beliefs[0].content["status"] == "active"
    # it is a belief, not a fact: the semantic store is untouched
    assert mind.memory.query(kind="semantic", type="fact", subject="server_a") == []


def test_owner_belief_conflicting_with_fact_surfaces_gently(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("remember that server_a is in berlin")
    reply = mind.step("i think server_a is in london")
    assert reply.success
    assert "london" in reply.text  # belief acknowledged
    assert "record" in reply.text  # the conflict is surfaced
    # the fact is not overwritten by an opinion (T2 discipline)
    fact = mind.memory.query(kind="semantic", type="fact", subject="server_a")[0]
    assert fact.content["object"] == "berlin"
