"""Cognitive behaviors: devil's advocate, curiosity gaps.

Traceability: ARCHITECTURE §4.7 (bounded pre-flight adversarial check before
high-stakes outputs ship: findings downgrade confidence or become rejected
alternatives for the explanation service), §4.2 / T5 (curiosity: gaps become
questions or investigations, never silent guesses), and §4.6 (effort
allocation decides which behaviors pay their cost).

These behaviors are deliberately *bounded* — Beanie doubts itself on purpose,
never on every token; only high-stakes or high-confidence outputs pay the
adversarial cost (§4.7).
"""

from __future__ import annotations

import re
from typing import Optional

from .records import Entry, RecordKind, Source
from .stores import Memory


def stakes_of(text: str) -> int:
    """Effort-allocation signal: how much a request looks like it matters (§4.6)."""
    high = re.findall(
        r"\b(delete|remove|permanent|send|pay|buy|sell|overwrite|irreversible|contract|money|final|never)\b",
        text.lower(),
    )
    return len(high)


class Devil:
    """Bounded pre-flight adversarial check (§4.7): try to disprove."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def check(self, user_text: str, confidence: float) -> list[dict]:
        """Return concerns: contradiction history, open questions, gaps.

        Deterministic over the stores: subjects the reply relies on are
        checked for (a) entries with conflict/supersession/invalidation in
        their revision history and (b) open questions about the same subject.
        Each concern carries its entry id so the explanation service can cite
        it honestly (T10).
        """
        tokens = {t for t in re.findall(r"[a-z]{4,}", user_text.lower())}
        concerns: list[dict] = []
        for entry in self.memory.subjects_matching(tokens):
            for revision in reversed(entry.revision_history[-3:]):
                reason = revision.reason.lower()
                if any(word in reason for word in ("conflict", "superseded", "invalidated")):
                    concerns.append(
                        {
                            "entry_id": entry.id,
                            "kind": "contradiction_history",
                            "detail": revision.reason,
                            "confidence_now": entry.confidence,
                        }
                    )
                    break
        for question in self.memory.query(kind="self", type="question", status="open"):
            qtext = str(question.content.get("text", ""))
            if any(t in qtext for t in tokens):
                concerns.append({"entry_id": question.id, "kind": "open_question", "detail": qtext})
        if confidence >= 0.95 and not concerns:
            concerns.append({"kind": "none", "detail": "no contradicting evidence found in stores"})
        return concerns[:3]  # bounded (§4.7)


class Curiosity:
    """Gap detection → open questions driving future behavior (T5)."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def open_question(self, subject: str, detail: str) -> Optional[Entry]:
        """Persist a known gap as an open question; skips duplicates (T5)."""
        for existing in self.memory.query(kind="self", type="question", status="open"):
            if str(existing.content.get("text", "")) == detail:
                return None
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.SELF,
            content={"type": "question", "status": "open", "subject": subject.lower(), "text": detail},
            source=Source.SELF_REFLECTION,
            confidence=0.5,
        )
        self.memory.self_model.append(entry)
        return entry

    def resolve_open_questions(self, subject: str, evidence_id: str, note: str) -> list[str]:
        """Close open questions about `subject` when evidence has arrived.

        The knowledge loop must close: a question stays open only while no
        evidence exists; when a fact about its subject is stored, matching
        questions are resolved with a reference to the evidence (T5 → the
        curiosity drive is satisfied by learning, not left dangling forever).
        """
        tokens = {t for t in re.findall(r"[a-z0-9]{3,}", subject.lower()) if not t.isdigit()}
        resolved: list[str] = []
        for question in self.memory.query(kind="self", type="question", status="open"):
            qtext = f"{question.content.get('subject', '')} {question.content.get('text', '')}".lower()
            if tokens & {t for t in re.findall(r"[a-z0-9]{3,}", qtext) if not t.isdigit()}:
                question.content["status"] = "resolved"
                question.content["resolved_by"] = evidence_id
                question.revise(f"resolved by evidence {evidence_id}: {note}", confidence=0.9)
                resolved.append(question.id)
        if resolved:
            self.memory.self_model.save_all()
        return resolved
