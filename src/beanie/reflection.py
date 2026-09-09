"""Reflection & consolidation — the learning engine (§4.3) and identity data.

Traceability: ARCHITECTURE §4.3 (periodic reflection pass: what happened, what
I learned, what belief changed, what I should do differently — outputs land in
the correct stores and change future behavior) and Stage 5's consolidation
data path (lessons and statistics distilled into self-model summaries so "who
Beanie is" is a computation over history, T7). The consolidation adapter
interface is where a fine-tune would plug in — one mechanism among many,
never "the personality" (VISION property 5).

StubReflector is deterministic: it only distills what genuinely happened in
the records (corrections, confirmations, failures) into lessons. PromptedReflector
delegates deeper distillation to a substrate when a real model tier is
present; without one it returns no invented lessons (honesty rule, VISION §4).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

from .records import Entry, RecordKind, Source, utcnow_iso
from .stores import Memory
from .substrate import Substrate


class Reflector(ABC):
    """Reflection pass over recent experience (§4.3)."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    @abstractmethod
    def reflect(self, episodes: list[Entry]) -> list[str]:
        """Distill episodes into store updates; returns notes."""

    def consolidate(self) -> dict[str, Any]:
        """Build/refresh the identity summary from accumulated history (T7).

        The bundle is also the input a ConsolidationAdapter would fine-tune
        on — identity data, not personality prompts.
        """
        lessons = [e for e in self.memory.query(kind="self", type="lesson")]
        corrections = sum(1 for e in self.memory.episodes.all() if e.content.get("was_correction"))
        skills = [s for s in self.memory.query(kind="procedural", type="skill", status="active")]
        summary = {
            "type": "identity_summary",
            "generated_at": utcnow_iso(),
            "episodes_lived": self.memory.episodes.count(),
            "lessons_learned": len(lessons),
            "corrections_received": corrections,
            "active_skills": [{"title": s.content.get("title"), "id": s.id} for s in skills],
            "recent_lessons": [l.content.get("text", "")[:300] for l in lessons[-5:]],
        }
        existing = self.memory.query(kind="self", type="identity_summary")
        if existing:
            entry = existing[-1]
            entry.revise("consolidation refresh", confidence=0.95)
            entry.content = summary
            self.memory.self_model.save_all()
            return summary
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.SELF,
            content=summary,
            source=Source.SELF_REFLECTION,
            confidence=0.95,
        )
        self.memory.self_model.append(entry)
        return summary


class StubReflector(Reflector):
    """Deterministic distillation (no model tier): only real record events."""

    def reflect(self, episodes: list[Entry]) -> list[str]:
        notes: list[str] = []
        for episode in episodes:
            content = episode.content
            if content.get("was_correction"):
                notes.append(self._lesson(f"Owner corrected: {content.get('user_text', '')[:200]}"))
            if content.get("plan_failed"):
                notes.append(self._lesson(f"Plan failure on {content.get('goal', '?')}: {content.get('failure', 'unknown')}"))
            if content.get("skill_confirmed"):
                rule_text = content.get("rule", "")
                if not isinstance(rule_text, str):
                    rule_text = str(rule_text)[:200]
                notes.append(self._lesson(f"Owner confirmed a learned rule: {rule_text[:200]}"))
        if not notes:
            notes.append("reflection: nothing beyond routine episodes to distill")
        # every reflection ends with the identity summary refresh (T7 data path)
        self.consolidate()
        return notes

    def _lesson(self, text: str) -> str:
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.SELF,
            content={"type": "lesson", "text": text, "at": utcnow_iso()},
            source=Source.SELF_REFLECTION,
            confidence=0.8,
        )
        self.memory.self_model.append(entry)
        return text


class PromptedReflector(Reflector):
    """Substrate-assisted distillation for when a real model tier is wired."""

    PROMPT = (
        "You are Beanie's reflection pass. From these episodes, extract at most three "
        "durable lessons as a JSON list of strings. Only include lessons that the episodes "
        "actually support. If nothing durable happened, return []."
    )

    def __init__(self, memory: Memory, substrate: Substrate) -> None:
        super().__init__(memory)
        self.substrate = substrate

    def reflect(self, episodes: list[Entry]) -> list[str]:
        notes: list[str] = []
        recent = episodes[-20:]
        if not recent:
            return notes
        transcript = "\n".join(
            f"{e.content.get('user_text', '')} → {e.content.get('reply', '')[:120]}" for e in recent
        )
        try:
            outcome = self.substrate.deep(
                {"user_text": "", "task": "reflection", "transcript": transcript[:6000]},
                [],
                candidate="reflect",
            )
            lessons = json.loads(outcome.text)
            for lesson in lessons if isinstance(lessons, list) else []:
                notes.append(self._lesson(str(lesson)[:300]))
        except (json.JSONDecodeError, ValueError, AttributeError):
            notes.append("reflection: substrate output was not parseable; nothing invented")
        self.consolidate()
        return notes

    def _lesson(self, text: str) -> str:
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.SELF,
            content={"type": "lesson", "text": text, "at": utcnow_iso()},
            source=Source.SELF_REFLECTION,
            confidence=0.7,
        )
        self.memory.self_model.append(entry)
        return text


class ConsolidationAdapter(ABC):
    """Where a fine-tune would plug in (Stage 5) — one mechanism, not identity."""

    @abstractmethod
    def consolidate(self, bundle: dict[str, Any]) -> None: ...


class NoopConsolidationAdapter(ConsolidationAdapter):
    """No adapter configured: identity stays in the stores (default)."""

    def consolidate(self, bundle: dict[str, Any]) -> None:  # noqa: D102
        return None
