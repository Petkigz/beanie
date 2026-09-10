"""Effort policy — usefulness feedback closes the loop into depth routing.

Traceability: ARCHITECTURE §4.6 (effort allocation: "good enough" vs deep,
stakes-aware; the policy is itself learned from outcomes — T13: if low-effort
answers correlate with corrections, the stakes estimator recalibrates) and
VISION T13 (the correlation demonstrably informs effort allocation).

The policy owns the reflex word-limit and the deep-verification stakes
threshold. Every background tick it audits the trace: reflex turns that
failed (corrected/refused) shrink the reflex budget; long stretches of clean
reflex turns grow it back (bounded). Adjustments persist as a self-model
entry (type "effort_policy") so the policy survives restarts and the audit
trail says why the mind became more or less conservative.
"""

from __future__ import annotations

from typing import Any, Optional

from .records import Entry, RecordKind, Source
from .stores import Memory
from .trace import FailureTaxonomy

DEFAULT_WORD_LIMIT = 6
DEFAULT_VERIFY_STAKES = 2
MIN_WORD_LIMIT = 3
MAX_WORD_LIMIT = 10


class EffortPolicy:
    """Adaptive depth-routing parameters, learned from outcomes (T13)."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        entry = self._stored()
        if entry is not None:
            self.word_limit = int(entry.content.get("word_limit", DEFAULT_WORD_LIMIT))
            self.verify_stakes = int(entry.content.get("verify_stakes", DEFAULT_VERIFY_STAKES))
        else:
            self.word_limit = DEFAULT_WORD_LIMIT
            self.verify_stakes = DEFAULT_VERIFY_STAKES

    def adapt(self, events: list) -> str:
        """Audit the trace and adjust; returns a note about the change ('' if none).

        Reflex-class turns are (a) clean reflex answers (depth 'reflex', which
        never fail by construction) and (b) turns the fast tier flagged and
        the loop escalated to the deep tier (decision payload
        'escalated_from': 'reflex'). A reflex-class turn counts as a failure
        when its outcome failed *or* the owner rated it poorly afterwards
        (explicit usefulness feedback, ARCHITECTURE §8/T13 — cheap answers
        that never fail by construction can still be wrong for the owner).
        Enough failures tighten the reflex budget; long clean stretches widen
        it again (bounded).
        """
        meta_by_turn: dict[str, dict] = {}
        outcomes: dict[str, bool] = {}  # turn_id -> outcome succeeded
        low_ratings: set[str] = set()  # turns the owner rated 1–2
        for event in events:
            kind = getattr(event, "kind", None)
            payload = getattr(event, "payload", {})
            if kind == "decision":
                meta_by_turn[event.turn_id] = {
                    "depth": str(payload.get("depth", "")),
                    "escalated_from": payload.get("escalated_from"),
                }
            elif kind == "outcome":
                outcomes[event.turn_id] = not (event.failure and event.failure != FailureTaxonomy.NONE)
            elif kind == "feedback":
                if int(payload.get("score", 5)) <= 2:
                    low_ratings.add(event.turn_id)
            elif kind == "usefulness" and payload.get("signal") == "abandonment":
                # implicit verdict: the owner walked away from what that turn left open
                low_ratings.add(str(payload.get("about_turn", "")))
        reflex_class: list[tuple[str, bool]] = []
        for turn_id, succeeded in outcomes.items():
            meta = meta_by_turn.get(turn_id)
            if not meta:
                continue
            if meta["depth"] == "reflex" or meta.get("escalated_from") == "reflex":
                reflex_class.append((turn_id, succeeded and turn_id not in low_ratings))
        if len(reflex_class) < 6:
            return ""
        failures = sum(1 for _, ok in reflex_class if not ok)
        failure_rate = failures / len(reflex_class)
        change = ""
        if failure_rate >= 0.25 and self.word_limit > MIN_WORD_LIMIT:
            self.word_limit -= 1
            change = f"reflex budget tightened ({self.word_limit + 1} → {self.word_limit} words): {failure_rate:.0%} of reflex-class turns failed"
        elif failure_rate == 0.0 and self.word_limit < MAX_WORD_LIMIT:
            self.word_limit += 1
            change = f"reflex budget widened ({self.word_limit - 1} → {self.word_limit} words): no reflex-class failures recently"
        if change:
            self._store(change)
        return change

    def _stored(self) -> Optional[Entry]:
        entries = self.memory.query(kind="self", type="effort_policy")
        return entries[-1] if entries else None

    def _store(self, change: str) -> None:
        entry = self._stored()
        if entry is None:
            entry = Entry(
                id=self.memory.allocate_id(),
                kind=RecordKind.SELF,
                content={"type": "effort_policy",
                         "word_limit": self.word_limit,
                         "verify_stakes": self.verify_stakes,
                         "history": [change]},
                source=Source.SELF_REFLECTION,
                confidence=0.9,
            )
            self.memory.self_model.append(entry)
            return
        entry.content["word_limit"] = self.word_limit
        entry.content["verify_stakes"] = self.verify_stakes
        entry.content.setdefault("history", []).append(change)
        entry.revise(change, confidence=0.9)
        self.memory.self_model.save_all()
