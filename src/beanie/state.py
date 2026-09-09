"""Mind state: counters and continuity metadata.

Traceability: ARCHITECTURE §8 Stage 0 — restart continuity is an exit
criterion: closing the process is sleep, not death (VISION property 1). The
state file persists the id counters that keep records and turns unique across
restarts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .records import utcnow_iso


class MindState:
    """Persistent counters for one mind instance (identity over time)."""

    def __init__(self, *, next_turn: int = 1, next_record: int = 1) -> None:
        self.next_turn = next_turn
        self.next_record = next_record
        self.created_at = utcnow_iso()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "next_turn": self.next_turn,
            "next_record": self.next_record,
            "created_at": self.created_at,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic-ish replace: no torn state files

    @classmethod
    def load(cls, path: Path) -> "MindState":
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            state = cls(
                next_turn=int(data.get("next_turn", 1)),
                next_record=int(data.get("next_record", 1)),
            )
            state.created_at = data.get("created_at", state.created_at)
            return state
        return cls()

    @classmethod
    def from_dir(cls, directory: Path) -> "MindState":
        return cls.load(directory / "mind_state.json")
