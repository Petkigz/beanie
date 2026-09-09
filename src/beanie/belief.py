"""Belief maintenance: contradiction, contamination, stale-truth decay.

Traceability: ARCHITECTURE §3.6 (contradiction & confidence engine incl.
contamination propagation — T2/T11) and the stale-truth handling rule (T12,
decay profiles from records.py). This module is the machinery that keeps the
stores corrigible: evidence agrees → confidence rises (bounded); evidence
conflicts → confidence falls, owner-derived rules ask first; invalidation
walks evidence_refs in reverse so everything a false fact touched is doubted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .records import Entry, RecordKind, Source, Volatility, utcnow_iso
from .stores import Memory


@dataclass
class IngestReport:
    """What an ingestion did to the stores."""

    updated: list[str] = field(default_factory=list)
    demoted: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    ask_owner: bool = False
    note: Optional[str] = None


class ContradictionEngine:
    """Evidence-state maintenance over the mind's stores (§3.6)."""

    #: how much corroboration raises confidence (bounded)
    CONFIRM_BOOST = 0.06
    #: factor applied to the losing side of an owner-vs-owner conflict
    SUPERSEDED_FACTOR = 0.3
    MAX_CONFIRM = 0.97

    def _conflict_key(self, entry: Entry) -> Optional[tuple[str, str]]:
        content = entry.content
        if content.get("type") == "fact" and content.get("subject") and content.get("predicate"):
            return (str(content["subject"]), str(content["predicate"]))
        return None

    def ingest(self, memory: Memory, entry: Entry) -> IngestReport:
        """Bring one new entry into the stores, resolving contradictions."""
        report = IngestReport()
        report.created.append(entry.id)
        key = self._conflict_key(entry)
        if key is None:
            return report

        for other in memory.query(kind="semantic", type="fact", subject=key[0], predicate=key[1]):
            if other.id == entry.id or other.confidence <= 0.05:
                continue
            if other.content.get("object") == entry.content.get("object"):
                # corroboration: raise both, bounded
                if entry.confidence < self.MAX_CONFIRM:
                    entry.revise(f"corroborated by {other.id}", confidence=min(entry.confidence + self.CONFIRM_BOOST, self.MAX_CONFIRM))
                if other.confidence < self.MAX_CONFIRM:
                    other.revise(f"corroborated by {entry.id}", confidence=min(other.confidence + self.CONFIRM_BOOST, self.MAX_CONFIRM))
                report.updated.extend([entry.id, other.id])
                memory.semantic.save_all()
                return report
            # conflict
            if entry.source == Source.OWNER and other.source == Source.OWNER:
                # newest owner statement wins; the old one is superseded, kept, flagged
                other.revise(
                    f"superseded by newer owner statement {entry.id}",
                    confidence=other.confidence * self.SUPERSEDED_FACTOR,
                )
                report.demoted.append(other.id)
                report.ask_owner = True
                report.note = (
                    "That contradicts what I had on record — I've updated it to the newer statement. "
                    "The older belief is kept but flagged superseded."
                )
            elif entry.source == Source.OWNER:
                other.revise(f"corrected by owner statement {entry.id}", confidence=other.confidence * 0.4)
                report.demoted.append(other.id)
            elif other.source == Source.OWNER:
                # evidence vs owner rule: never silently overwrite the owner
                report.ask_owner = True
                report.note = f"I have an owner-stated fact that conflicts with this ({other.id}). Not overwriting without your word."
            else:
                # two non-owner sources conflict: doubt both, keep both (T2)
                other.revise(f"conflicts with {entry.id}", confidence=other.confidence * 0.5)
                entry.revise(f"conflicts with {other.id}", confidence=entry.confidence * 0.5)
                report.demoted.extend([entry.id, other.id])
                report.note = f"Conflicting evidence ({other.id} vs new). Confidence lowered on both; unresolved for now."
            memory.semantic.save_all()
            break  # one conflict handled per pass; later passes revisit
        return report

    def contamination(self, memory: Memory, source_id: str, reason: str, factor: float = 0.5) -> list[str]:
        """Invalidate `source_id` and everything that depended on it (T11).

        Walks evidence_refs in reverse, depth-limited, demoting dependents and
        tagging them needs_recheck. Returns the ids of all demoted entries.
        """
        demoted: list[str] = []
        visited: set[str] = set()

        def walk(record_id: str, level: int) -> None:
            if level > 3 or record_id in visited:
                return
            visited.add(record_id)
            for store in (memory.semantic, memory.owner_model, memory.skills, memory.self_model):
                for entry in store.all():
                    refs = [r.record_id for r in entry.evidence_refs if r.role in ("supports", "source")]
                    if entry.id != record_id and record_id in refs:
                        entry.revise(
                            f"depends on invalidated {record_id}: {reason}",
                            confidence=entry.confidence * factor,
                            observe=False,
                        )
                        entry.content.setdefault("needs_recheck", True)
                        demoted.append(entry.id)
                        walk(entry.id, level + 1)
                store.save_all()

        source = memory.find(source_id)
        if source is not None and source.confidence > 0.05:
            source.revise(reason, confidence=0.05, observe=False)
        walk(source_id, 0)
        return demoted


class DecayMonitor:
    """Stale-truth handling (T12): decay sweeps + stale-state flags."""

    def __init__(self, stale_below: float = 0.35) -> None:
        self.stale_below = stale_below

    def sweep(self, memory: Memory, now: Optional[str] = None) -> list[Entry]:
        """Mark entries whose unobserved confidence fell under the threshold.

        Returns the stale entries so callers can decide (re-check before
        acting on high-stakes state, ask, or drop).
        """
        stale: list[Entry] = []
        for kind in ("semantic", "owner_model", "procedural"):
            store = memory.store(kind)
            for entry in store.all():
                if entry.decay_profile.volatility == Volatility.LOW:
                    continue
                effective = entry.effective_confidence(now)
                if effective < entry.confidence - 0.02:
                    entry.revise(
                        f"auto-decay while unobserved ({entry.confidence:.2f} → {effective:.2f})",
                        confidence=effective,
                        observe=False,
                    )
                    if effective < self.stale_below and not entry.content.get("stale"):
                        entry.content["stale"] = True
                        stale.append(entry)
            store.save_all()
        return stale

    def stale_related(self, memory: Memory, subjects: set[str]) -> list[Entry]:
        """High-stakes state the mind plans to act on that has gone stale (T12)."""
        stale: list[Entry] = []
        for entry in memory.query(kind="semantic", type="fact"):
            if str(entry.content.get("subject", "")) in subjects and entry.content.get("stale"):
                stale.append(entry)
        return stale
