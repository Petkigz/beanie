"""Event trace with failure-taxonomy tagging.

Traceability: ARCHITECTURE §8 Measurement protocol — every turn records the
decision trace and, when the outcome was wrong, a root-cause taxonomy tag, so
we know *which organ* failed rather than only that one did (Q28). The trace is
for the machine; the user-facing explanation service (§4.5, Stage 1+) reads
this same record.

Taxonomy categories (Q28): prompt ambiguity / missing context / evidence
misweighting / causal mis-modeling / tool execution error.
"""

from __future__ import annotations

import datetime as _dt
import enum
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

UTC = _dt.timezone.utc


class FailureTaxonomy(str, enum.Enum):
    """Root-cause categories for wrong outcomes (Q28 / ARCHITECTURE §8)."""

    PROMPT_AMBIGUITY = "prompt_ambiguity"
    MISSING_CONTEXT = "missing_context"
    EVIDENCE_MISWEIGHTING = "evidence_misweighting"
    CAUSAL_MIS_MODELING = "causal_mis_modeling"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    NONE = "none"


@dataclass
class TraceEvent:
    """One trace line: what the mind did, saw, or decided on a turn."""

    turn_id: str
    kind: str  # perception | decision | outcome | revision
    at: str
    payload: dict[str, Any] = field(default_factory=dict)
    failure: Optional[FailureTaxonomy] = None

    def to_json(self) -> str:
        data = asdict(self)
        data["failure"] = self.failure.value if self.failure else None
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "TraceEvent":
        data = json.loads(line)
        failure = data.get("failure")
        return cls(
            turn_id=data["turn_id"],
            kind=data["kind"],
            at=data["at"],
            payload=data.get("payload", {}),
            failure=FailureTaxonomy(failure) if failure else None,
        )


class Trace:
    """Append-only trace of cognitive-loop events (ARCHITECTURE §8)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._events: list[TraceEvent] = []
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                # Restore prior events so in-memory history spans restarts.
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            self._events.append(TraceEvent.from_json(line))

    def append(
        self,
        turn_id: str,
        kind: str,
        payload: dict[str, Any],
        failure: Optional[FailureTaxonomy] = None,
    ) -> TraceEvent:
        event = TraceEvent(
            turn_id=turn_id,
            kind=kind,
            at=_dt.datetime.now(UTC).isoformat(timespec="seconds"),
            payload=payload,
            failure=failure,
        )
        self._events.append(event)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(event.to_json() + "\n")
        return event

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)

    def events_for(self, turn_id: str) -> list[TraceEvent]:
        return [e for e in self._events if e.turn_id == turn_id]

    def failures_by_kind(self) -> dict[str, int]:
        """Count of failure events per taxonomy tag (Q28 → metrics)."""
        counts: dict[str, int] = {}
        for e in self._events:
            if e.kind == "outcome" and e.failure is not None and e.failure != FailureTaxonomy.NONE:
                counts[e.failure.value] = counts.get(e.failure.value, 0) + 1
        return counts


