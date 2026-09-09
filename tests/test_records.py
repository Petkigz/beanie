"""Record envelope tests: serialization, revision history, decay (ARCHITECTURE §3)."""

from beanie.records import (
    DecayProfile,
    Entry,
    EvidenceRef,
    RecordKind,
    Revision,
    Source,
    Volatility,
    confidence_label,
)


def make_entry(confidence=0.9) -> Entry:
    return Entry(
        id="rec-00001",
        kind=RecordKind.EPISODE,
        content={"user_text": "hello"},
        source=Source.OWNER,
        confidence=confidence,
        created_at="2026-09-09T10:00:00+00:00",
        updated_at="2026-09-09T10:00:00+00:00",
        last_observed_at="2026-09-09T10:00:00+00:00",
        evidence_refs=[EvidenceRef(record_id="rec-00000", role="context")],
    )


def test_json_roundtrip_preserves_envelope():
    entry = make_entry()
    restored = Entry.from_json(entry.to_json())
    assert restored.id == entry.id
    assert restored.kind == RecordKind.EPISODE
    assert restored.source == Source.OWNER
    assert restored.confidence == entry.confidence
    assert restored.evidence_refs[0].record_id == "rec-00000"
    assert restored.decay_profile.volatility == Volatility.MEDIUM


def test_revise_records_history_and_never_silently_overwrites():
    entry = make_entry(confidence=0.9)
    entry.revise("new evidence conflicts", confidence=0.4)
    assert entry.confidence == 0.4
    assert len(entry.revision_history) == 1
    rev: Revision = entry.revision_history[0]
    assert rev.confidence_before == 0.9
    assert rev.confidence_after == 0.4
    assert "new evidence conflicts" in rev.reason
    # id and created_at are immutable anchors
    assert entry.id == "rec-00001"
    assert entry.created_at == entry.created_at


def test_confidence_is_clamped_to_unit_interval():
    entry = make_entry(confidence=0.5)
    entry.revise("overclaim", confidence=1.7)
    assert entry.confidence == 1.0
    entry.revise("underclaim", confidence=-0.2)
    assert entry.confidence == 0.0


def test_effective_confidence_decays_along_profile():
    profile = DecayProfile(volatility=Volatility.HIGH, half_life_hours=1.0)
    entry = make_entry(confidence=0.8)
    entry.decay_profile = profile
    # two hours unobserved → one half-life elapsed twice → 0.8 * 0.5^2
    later = "2026-09-09T12:00:00+00:00"
    assert abs(entry.effective_confidence(now=later) - 0.8 * 0.25) < 1e-3
    # observing again restores full confidence (last_observed_at bumps)
    entry.revise("observed again")
    assert entry.effective_confidence() == entry.confidence


def test_confidence_label_thresholds():
    assert confidence_label(0.95) == "highly confident"
    assert confidence_label(0.8) == "highly confident"
    assert confidence_label(0.6) == "moderate"
    assert confidence_label(0.25) == "speculative"
