"""T-test battery: T2, T8, T11, T12 — contradiction, calibration, contamination, stale truth."""

import datetime as dt

import pytest

from beanie import Mind
from beanie.records import DecayProfile, Entry, EvidenceRef, RecordKind, Source, Volatility
from beanie.belief import DecayMonitor


@pytest.fixture
def mind(tmp_path):
    return Mind(state_dir=tmp_path / "mind")


def test_t2_owner_contradiction_demotes_and_asks(tmp_path):
    """T2: conflicting owner statement → old belief demoted, never silent."""
    mind = Mind(state_dir=tmp_path / "mind")
    first = mind.step("remember that server_a is in london")
    assert first.success
    second = mind.step("remember that server_a is in berlin")
    assert "contradicts" in second.text
    assert second.questions  # surfaced, not silent

    facts = mind.memory.query(kind="semantic", type="fact", subject="server_a")
    by_object = {f.content["object"]: f for f in facts}
    assert set(by_object) == {"london", "berlin"}  # nothing deleted
    assert by_object["london"].confidence == pytest.approx(0.9 * 0.3)  # superseded
    assert any("superseded" in r.reason for r in by_object["london"].revision_history)
    assert by_object["berlin"].confidence == pytest.approx(0.9)  # newest wins


def test_t8_labels_track_evidence_state(tmp_path):
    """T8: corroboration raises the label's underlying confidence."""
    mind = Mind(state_dir=tmp_path / "mind")
    r1 = mind.step("remember that client_x uses linux")
    r2 = mind.step("remember that client_x uses linux")  # corroboration
    assert r2.confidence > r1.confidence
    fact = mind.memory.query(kind="semantic", type="fact", subject="client_x")[-1]
    assert fact.confidence == pytest.approx(min(0.9 + 0.06, 0.97), abs=1e-3)


def test_t8_recent_corrections_lower_calibrated_confidence(tmp_path):
    """T8: repeated corrections about the same subject push the label down."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("wait, that's wrong about the report")
    r2 = mind.step("hello")  # unrelated → no penalty
    assert r2.confidence_label == "highly confident"
    mind.step("wait, the report thing is wrong")
    r3 = mind.step("what about the report status?")
    assert r3.confidence < 0.95 - 0.2  # penalized twice
    assert r3.confidence_label == "moderate"


def test_t11_contamination_propagates_to_dependents(tmp_path):
    """T11: invalidating a fact doubts everything that depended on it."""
    mind = Mind(state_dir=tmp_path / "mind")
    r1 = mind.step("remember that my_name is alice")
    remember_episode = [e for e in mind.episodes.all() if e.content.get("directive") == "remember"][-1]
    fact_id = remember_episode.content["memory_entry_id"]

    # a derived entry that *depends* on the fact
    derived = Entry(
        id=mind.memory.allocate_id(),
        kind=RecordKind.SEMANTIC,
        content={"type": "fact", "subject": "profile", "predicate": "named", "object": "alice"},
        source=Source.WEB,
        confidence=0.85,
        evidence_refs=[EvidenceRef(record_id=fact_id, role="supports")],
    )
    mind.memory.semantic.append(derived)

    reply = mind.step("no, that's wrong")
    assert reply.success and "wrong" in reply.text

    fact = mind.memory.find(fact_id)
    assert fact.confidence <= 0.05  # the source is dead
    dependent = mind.memory.find(derived.id)
    assert dependent.confidence == pytest.approx(0.85 * 0.5)  # halved by propagation
    assert dependent.content.get("needs_recheck") is True
    assert any("invalidated" in r.reason for r in dependent.revision_history)
    assert any(e.kind == "correction" and e.payload.get("kind") == "contamination" for e in mind.trace.events)


def test_t12_stale_truth_decays_and_is_flagged(tmp_path):
    """T12: unobserved high-volatility state decays deterministically and flags."""
    mind = Mind(state_dir=tmp_path / "mind")
    mind.step("remember that render_service is running")
    episode = [e for e in mind.episodes.all() if e.content.get("directive") == "remember"][-1]
    entry = mind.memory.find(episode.content["memory_entry_id"])
    entry.decay_profile = DecayProfile(volatility=Volatility.HIGH, half_life_hours=1.0)
    back = dt.datetime.fromisoformat(entry.last_observed_at) - dt.timedelta(hours=4)
    entry.last_observed_at = back.isoformat(timespec="seconds")
    mind.memory.semantic.save_all()

    stale = DecayMonitor(stale_below=0.35).sweep(mind.memory)
    ids = [e.id for e in stale]
    assert entry.id in ids
    assert entry.content.get("stale") is True
    related = DecayMonitor().stale_related(mind.memory, {"render_service"})
    assert any(e.id == entry.id for e in related)
    assert entry.confidence < 0.1  # 0.9 * 0.5^4
