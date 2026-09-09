"""T-test battery: T4 — preference learning & implicit discovery (VISION §5)."""

import pytest

from beanie import Mind


@pytest.fixture
def mind(tmp_path):
    return Mind(state_dir=tmp_path / "mind")


def test_t4_explicit_preference_learned_and_restated(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    reply = mind.step("i prefer dark mode over light mode")
    assert reply.success
    assert "dark mode" in reply.text
    entry = mind.memory.query(kind="owner_model", type="preference", context="general")[0]
    assert entry.content["choice"] == "dark mode"
    assert entry.content["status"] == "active"
    assert entry.content["rejected"] == "light mode"
    assert entry.confidence == pytest.approx(0.9)

    # restating corroborates: confidence rises, bounded
    mind.step("i prefer dark mode over light mode")
    assert entry.confidence == pytest.approx(0.95)


def test_t4_changed_preference_supersedes_not_deletes(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("i prefer dark mode over light mode")
    reply = mind.step("i like light mode more than dark mode")
    assert reply.success
    assert "light mode" in reply.text
    assert "replaces" in reply.text  # the owner is told the old belief changed

    entries = mind.memory.query(kind="owner_model", type="preference", context="general")
    by_choice = {e.content["choice"]: e for e in entries}
    assert by_choice["light mode"].content["status"] == "active"
    assert by_choice["dark mode"].content["status"] == "superseded"
    assert by_choice["dark mode"].confidence == pytest.approx(0.9 * 0.3)
    assert any("superseded" in r.reason for r in by_choice["dark mode"].revision_history)


def test_t4_when_uncertain_preference_phrase(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    reply = mind.step("when uncertain, ask rather than guess")
    assert reply.success
    entry = mind.memory.query(kind="owner_model", type="preference", context="uncertain")[0]
    assert entry.content["status"] == "active"
    assert "ask" in entry.content["choice"]


def test_t4_implicit_discovery_from_history_requires_confirmation(tmp_path):
    """From history alone → proposed; only an explicit statement activates."""
    mind = Mind(state_dir=tmp_path / "mind")
    # two corrections in the same topic category (asking/guessing)
    mind.step("no, always ask me before you guess")
    mind.step("no, ask first when unsure")

    proposals = mind.preferences.mine_implicit(mind.episodes.all())
    assert len(proposals) == 1
    proposed = proposals[0]
    assert proposed.content["context"] == "uncertain"
    assert proposed.content["status"] == "proposed"
    assert proposed.content["choice"] == "<awaiting owner confirmation>"
    assert proposed.confidence == pytest.approx(0.4)
    # nothing active yet — no silent adoption
    active = mind.memory.query(kind="owner_model", type="preference", context="uncertain", status="active")
    assert active == []

    # the owner confirms with an explicit statement → the proposal is promoted
    reply = mind.step("when uncertain, ask rather than guess")
    assert reply.success
    promoted = mind.memory.query(kind="owner_model", type="preference", context="uncertain")[0]
    assert promoted.content["status"] == "active"
    assert promoted.content["choice"] != "<awaiting owner confirmation>"
    assert "confirmed by explicit" in promoted.revision_history[-1].reason


def test_t4_single_correction_does_not_propose(tmp_path):
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("no, ask me first next time")
    assert mind.preferences.mine_implicit(mind.episodes.all()) == []
