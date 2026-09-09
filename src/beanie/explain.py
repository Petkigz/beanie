"""Explanation service — user-facing reasoning, on demand (§4.5, T10).

Traceability: ARCHITECTURE §4.5 (a summarization layer over the trace: the
conclusion, the evidence it rested on — named with freshness/quality — the
alternatives considered and why they lost, and residual uncertainty; plain
language; never raw chain-of-thought) and VISION property 9.

Every explanation is *auditable*: it names the actual record ids, trace
events, and revision reasons behind a reply, so the owner can verify the
explanation against the record (T10). It reads the same trace the evaluation
pipeline reads — but it is for the person, not the machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .records import Entry
from .stores import Memory
from .trace import Trace


@dataclass
class Explanation:
    turn_id: str
    record_id: Optional[str]
    summary: str
    evidence: list[dict] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    residual_uncertainty: str = ""

    def to_text(self) -> str:
        lines = [self.summary]
        if self.evidence:
            lines.append("Evidence I used:")
            for item in self.evidence:
                lines.append(f"  - {item['description']} (confidence {item['confidence']:.2f}, {item['source']})")
        if self.alternatives:
            lines.append("Alternatives I considered and set aside:")
            for alt in self.alternatives:
                lines.append(f"  - {alt}")
        if self.residual_uncertainty:
            lines.append(f"Residual uncertainty: {self.residual_uncertainty}")
        return "\n".join(lines)


class ExplanationService:
    """Compose auditable explanations from the trace + stores (§4.5)."""

    def __init__(self, memory: Memory, trace: Trace) -> None:
        self.memory = memory
        self.trace = trace

    def explain_record(self, record_id: str) -> Optional[Explanation]:
        entry = self.memory.find(record_id)
        if entry is None:
            return None
        return self._build(record_id=record_id, entry=entry)

    def explain_turn(self, turn_id: str) -> Optional[Explanation]:
        events = self.trace.events_for(turn_id)
        if not events:
            return None
        outcome = next((e for e in events if e.kind == "outcome"), None)
        record_id = outcome.payload.get("record_id") if outcome else None
        entry = self.memory.find(record_id) if record_id else None
        return self._build(turn_id=turn_id, record_id=record_id, entry=entry)

    def _build(self, *, turn_id: str = "", record_id: Optional[str] = None, entry: Optional[Entry]) -> Explanation:
        evidence: list[dict] = []
        alternatives: list[str] = []
        residual = ""

        if entry is not None:
            for ref in entry.evidence_refs:
                ref_entry = self.memory.find(ref.record_id)
                if ref_entry is not None:
                    evidence.append(
                        {
                            "description": f"{ref.role}: {ref_entry.content.get('user_text', ref.record_id)[:100]}",
                            "confidence": ref_entry.confidence,
                            "source": ref_entry.source.value,
                        }
                    )
        # concern payloads recorded by the pre-flight check become the
        # "alternatives considered and why they lost" section (T10)
        for event in self.trace.events_for(turn_id):
            concerns = event.payload.get("concerns") or []
            for concern in concerns:
                if concern.get("kind") != "none":
                    alternatives.append(concern.get("detail", "a concern was noted"))
            residual = str(event.payload.get("residual", "") or "")
        if entry is not None and not residual:
            residual = f"answer carries label '{entry.content.get('label', 'n/a')}' at confidence {entry.confidence:.2f}"
        if not residual:
            residual = "no separate uncertainty assessment was recorded for this turn"

        # plain-language summary — cites the record, never raw chain-of-thought
        if entry is not None and entry.content.get("reply"):
            summary = (
                f"I answered: '{str(entry.content['reply'])[:160]}'. "
                f"This record ({entry.id}) was created at {entry.created_at} from a {entry.source.value}."
            )
        elif entry is not None:
            summary = f"Record {entry.id} ({entry.kind.value}), source {entry.source.value}, confidence {entry.confidence:.2f}."
        else:
            summary = f"Turn {turn_id} has no linked record."
        return Explanation(
            turn_id=turn_id,
            record_id=record_id,
            summary=summary,
            evidence=evidence,
            alternatives=alternatives,
            residual_uncertainty=residual,
        )
