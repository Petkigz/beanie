"""Stores — the mind's persistent long-term memory, all kinds.

Traceability: ARCHITECTURE §3 (all stores share one record envelope) and
§3.1–§3.7 (episodic, semantic/world, procedural, self, owner/social with its
theory-of-mind belief layer, and intentions/prospective memory). §3.7's
intention entries live in the intention store; authority rules (ARCHITECTURE
§5) live in the owner store as content type "rule".

Every store is a JSONL file of record-envelope entries (§3); mutation goes
through Entry.revise() (records.py) so nothing is ever silently overwritten.
Stage 0's EpisodicStore name is kept for compatibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from .records import Entry


class JsonlStore:
    """A JSONL-backed store of envelope entries (§3)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[Entry] = []
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        self._entries.append(Entry.from_json(line))
        # revisions per entry id as of the last write, so a mutated entry is
        # never lost: append() rewrites the file only when something was revised
        self._written_revisions: dict[str, int] = {
            entry.id: len(entry.revision_history) for entry in self._entries
        }

    def append(self, entry: Entry) -> Entry:
        """Append a new entry; the entry must not already be present.

        Append is the hot path of a mind that runs for a long time (every turn,
        every observation), so it is O(1) when nothing was revised: the new
        entry is written as one line. If any stored entry has been revised since
        the last write, the file is rewritten so those changes persist exactly
        as they did when every append rewrote the store (ARCHITECTURE §9: the
        storage substrate has to hold at human-scale history).
        """
        self._entries.append(entry)
        if self._has_pending_revisions():
            self._flush()
        else:
            self._append_line(entry)
        self._written_revisions[entry.id] = len(entry.revision_history)
        return entry

    def _has_pending_revisions(self) -> bool:
        for entry in self._entries:
            if self._written_revisions.get(entry.id, 0) != len(entry.revision_history):
                return True
        return False

    def _append_line(self, entry: Entry) -> None:
        if not self.path.exists():
            self._flush()
            return
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(entry.to_json() + "\n")

    def all(self) -> list[Entry]:
        return list(self._entries)

    def latest(self, n: int) -> list[Entry]:
        return list(self._entries[-n:]) if n > 0 else []

    def find(self, record_id: str) -> Optional[Entry]:
        for entry in reversed(self._entries):
            if entry.id == record_id:
                return entry
        return None

    def count(self) -> int:
        return len(self._entries)

    def _flush(self) -> None:
        """Rewrite the whole file atomically (entries are mutable via revise())."""
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for entry in self._entries:
                fh.write(entry.to_json() + "\n")
        tmp.replace(self.path)
        self._written_revisions = {entry.id: len(entry.revision_history) for entry in self._entries}

    def save_all(self) -> None:
        """Explicit full rewrite (after revisions, deletions, bulk edits)."""
        self._flush()

    def __iter__(self) -> Iterator[Entry]:
        return iter(self._entries)


class EpisodicStore(JsonlStore):
    """Episodic memory store (ARCHITECTURE §3.1) — legacy Stage 0 name."""


KIND_FILES: dict[str, str] = {
    "episode": "episodes.jsonl",
    "semantic": "semantic.jsonl",
    "procedural": "procedural.jsonl",
    "self": "self_model.jsonl",
    "owner_model": "owner_model.jsonl",
    "intention": "intentions.jsonl",
}


class Memory:
    """All of Beanie's stores behind one facade (§3).

    Each kind has its own JSONL backing under a state directory. Ids are
    allocated from one persistent counter so no two records ever collide and
    continuity survives restarts (VISION property 1).
    """

    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._stores: dict[str, JsonlStore] = {
            kind: JsonlStore(self.dir / name) for kind, name in KIND_FILES.items()
        }
        self._seq_file = self.dir / "memory_seq.json"
        self._next = 1
        if self._seq_file.exists():
            self._next = int(json.loads(self._seq_file.read_text(encoding="utf-8"))["next"])

    # -- identity/ids ------------------------------------------------------

    def allocate_id(self) -> str:
        record_id = f"rec-{self._next:05d}"
        self._next += 1
        self._seq_file.write_text(json.dumps({"next": self._next}), encoding="utf-8")
        return record_id

    # -- access ------------------------------------------------------------

    def store(self, kind: str) -> JsonlStore:
        return self._stores[kind]

    @property
    def episodes(self) -> JsonlStore:
        return self._stores["episode"]

    @property
    def semantic(self) -> JsonlStore:
        return self._stores["semantic"]

    @property
    def skills(self) -> JsonlStore:
        return self._stores["procedural"]

    @property
    def self_model(self) -> JsonlStore:
        return self._stores["self"]

    @property
    def owner_model(self) -> JsonlStore:
        return self._stores["owner_model"]

    @property
    def intentions(self) -> JsonlStore:
        return self._stores["intention"]

    def entries_of(self, kind: str) -> list[Entry]:
        return self._stores[kind].all()

    def find(self, record_id: str) -> Optional[Entry]:
        for store in self._stores.values():
            found = store.find(record_id)
            if found is not None:
                return found
        return None

    def query(self, *, kind: str | None = None, ctype: str | None = None, **fields: object) -> list[Entry]:
        """Query entries by kind, content type, and content field values."""
        stores = self._stores.values() if kind is None else [self._stores[kind]]
        out: list[Entry] = []
        for store in stores:
            for entry in store.all():
                content = entry.content
                if ctype is not None and content.get("type") != ctype:
                    continue
                if all(content.get(key) == value for key, value in fields.items()):
                    out.append(entry)
        return out

    def subjects_matching(self, tokens: set[str]) -> list[Entry]:
        """Semantic/owner entries whose subject token overlaps `tokens`."""
        out: list[Entry] = []
        for kind in ("semantic", "owner_model"):
            for entry in self._stores[kind].all():
                subject = str(entry.content.get("subject", ""))
                if subject and subject in tokens:
                    out.append(entry)
        return out
