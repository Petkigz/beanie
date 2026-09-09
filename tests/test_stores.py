"""Episodic store tests: append, reload across instances (ARCHITECTURE §3.1)."""

from beanie.records import Entry, RecordKind, Source
from beanie.stores import EpisodicStore


def _entry(record_id: str, text: str) -> Entry:
    return Entry(
        id=record_id,
        kind=RecordKind.EPISODE,
        content={"user_text": text},
        source=Source.OWNER,
        confidence=0.9,
        created_at="2026-09-09T10:00:00+00:00",
        updated_at="2026-09-09T10:00:00+00:00",
        last_observed_at="2026-09-09T10:00:00+00:00",
    )


def test_append_and_reopen_persists_episodes(tmp_path):
    path = tmp_path / "episodes.jsonl"
    store = EpisodicStore(path)
    store.append(_entry("rec-00001", "first"))
    store.append(_entry("rec-00002", "second"))
    assert store.count() == 2

    reopened = EpisodicStore(path)  # a new process, same file
    assert reopened.count() == 2
    assert [e.content["user_text"] for e in reopened] == ["first", "second"]


def test_latest_returns_most_recent_oldest_first(tmp_path):
    store = EpisodicStore(tmp_path / "episodes.jsonl")
    for i in range(5):
        store.append(_entry(f"rec-{i:05d}", f"turn {i}"))
    latest = store.latest(3)
    assert [e.content["user_text"] for e in latest] == ["turn 2", "turn 3", "turn 4"]


def test_find_returns_entry_or_none(tmp_path):
    store = EpisodicStore(tmp_path / "episodes.jsonl")
    store.append(_entry("rec-00001", "first"))
    assert store.find("rec-00001") is not None
    assert store.find("rec-99999") is None
