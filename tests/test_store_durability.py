"""Store durability + the append fast path (ARCHITECTURE §3, §9 storage scale).

A mind that runs for a long time appends constantly (every turn, every
observation). Appending used to rewrite the whole file, so a session cost grew
quadratically with history. The fast path must not weaken the contract: what is
in memory is on disk, and a revision is never lost — even when the only thing
that would have persisted it was a later append.
"""

import json
import time

from beanie.records import Entry, RecordKind, Source
from beanie.stores import Memory


def _entry(memory: Memory, subject: str) -> Entry:
    return Entry(
        id=memory.allocate_id(),
        kind=RecordKind.SEMANTIC,
        content={"type": "fact", "subject": subject, "predicate": "is", "object": "somewhere"},
        source=Source.OWNER,
        confidence=0.9,
    )


def _on_disk(path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_appends_are_durable_and_match_memory(tmp_path):
    memory = Memory(tmp_path)
    for n in range(20):
        memory.semantic.append(_entry(memory, f"subject_{n}"))
    disk = _on_disk(tmp_path / "semantic.jsonl")
    assert disk == [json.loads(e.to_json()) for e in memory.semantic.all()]
    assert len(disk) == 20


def test_revision_is_not_lost_when_a_later_append_persists_it(tmp_path):
    """The old behavior persisted revisions incidentally on the next append.

    Callers are still expected to call save_all(), but the fast path must not
    silently drop a revision that a subsequent append used to flush.
    """
    memory = Memory(tmp_path)
    first = memory.semantic.append(_entry(memory, "alpha"))
    first.revise("owner corrected the object", confidence=0.7, content={
        "type": "fact", "subject": "alpha", "predicate": "is", "object": "corrected",
    })
    memory.semantic.append(_entry(memory, "beta"))  # no explicit save_all

    disk = _on_disk(tmp_path / "semantic.jsonl")
    assert [row["content"]["object"] for row in disk] == ["corrected", "somewhere"]
    assert disk[0]["revision_history"], "the revision reason must survive"


def test_explicit_save_all_after_revision(tmp_path):
    memory = Memory(tmp_path)
    entry = memory.semantic.append(_entry(memory, "gamma"))
    entry.revise("superseded by a newer statement", confidence=0.6)
    memory.semantic.save_all()
    disk = _on_disk(tmp_path / "semantic.jsonl")
    assert disk[0]["confidence"] == 0.6
    assert disk[0]["revision_history"][0]["reason"] == "superseded by a newer statement"

    # appends after a full flush keep working and stay consistent
    memory.semantic.append(_entry(memory, "delta"))
    assert len(_on_disk(tmp_path / "semantic.jsonl")) == 2


def test_reload_reproduces_the_store(tmp_path):
    memory = Memory(tmp_path)
    for n in range(5):
        memory.semantic.append(_entry(memory, f"subject_{n}"))
    refreshed = Memory(tmp_path)
    assert [e.id for e in refreshed.semantic.all()] == [e.id for e in memory.semantic.all()]
    assert [e.content for e in refreshed.semantic.all()] == [e.content for e in memory.semantic.all()]


def test_append_cost_does_not_grow_with_history(tmp_path):
    """Appends must be flat-rate: the file is not rewritten per append (§9)."""
    memory = Memory(tmp_path)
    for n in range(2000):
        memory.semantic.append(_entry(memory, f"old_{n}"))

    start = time.perf_counter()
    for n in range(300):
        memory.semantic.append(_entry(memory, f"new_{n}"))
    elapsed = time.perf_counter() - start
    # the old implementation rewrote 2000+ entries per append (~2s for this loop);
    # the bound is loose so it cannot flake, but tight enough to catch a regression
    assert elapsed < 0.5, f"300 appends over a 2000-entry store took {elapsed:.2f}s"
    assert len(_on_disk(tmp_path / "semantic.jsonl")) == 2300
