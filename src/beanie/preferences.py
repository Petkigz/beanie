"""Preference learning & discovery — VISION T4 (owner model, ARCHITECTURE §6).

Traceability: VISION §5 T4 — from statements *or history alone* Beanie
infers a stable preference of its owner ("you prefer X over Y when …") and
either adopts it or asks for confirmation — and ARCHITECTURE §6
(preference/social learning → owner model).

Explicit statements are learned immediately (the owner is the highest
authority, VISION §4): a repeated preference corroborates (confidence rises,
bounded), a changed preference supersedes the old one (flagged, never
deleted — T2 applies). Implicit discovery — T4's "from history alone" —
mines repeated owner corrections that share a topic category and records a
*proposed* preference, which requires an explicit owner statement in the
same context before it becomes active. Nothing is adopted from guesses.
"""

from __future__ import annotations

import re
from typing import Optional

from .records import Entry, RecordKind, Source
from .stores import Memory

_WITH_VS = re.compile(
    r"^\s*i\s+prefer\s+(?:to\s+)?(?P<choice>.+?)\s+(?:over|rather\s+than)\s+(?P<rejected>.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_WITH_BARE = re.compile(r"^\s*i\s+prefer\s+(?:to\s+)?(?P<choice>.+?)\s*\.?\s*$", re.IGNORECASE)
_LIKE_VS = re.compile(
    r"^\s*i\s+like\s+(?P<choice>.+?)\s+more\s+than\s+(?P<rejected>.+?)\s*\.?\s*$", re.IGNORECASE
)
_WHEN_UNCERTAIN = re.compile(
    r"^\s*when\s+(?:(?:i\s+am|i'?m|i)\s+)?(?P<ctx>uncertain|unsure|in\s+doubt|not\s+sure)\s*[,.]?\s+"
    r"(?P<choice>ask\s+(?:me\s+)?(?:rather\s+than\s+(?:guess|guessing)|first)|ask\s+rather\s+than\s+guess(?:ing)?)\s*\.?\s*$",
    re.IGNORECASE,
)

#: correction-topic categories for implicit mining (ctx → topic keywords)
_CATEGORIES: list[tuple[str, set[str]]] = [
    ("uncertain", {"ask", "guess", "permission", "approve", "confirm"}),
    ("files", {"move", "folder", "directory", "downloads", "files"}),
    ("style", {"format", "style", "wording", "tone"}),
]

_NORMALIZED_CTX = {
    "unsure": "uncertain",
    "in doubt": "uncertain",
    "not sure": "uncertain",
    "i'm uncertain": "uncertain",
}


class PreferenceMiner:
    """Learn explicit preferences; discover implicit ones from history (T4)."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    # -- explicit statements -------------------------------------------------

    def learn(self, text: str) -> Optional[Entry]:
        """Learn an explicit preference statement; returns the stored entry.

        Corroborates an identical active preference (confidence +0.05,
        bounded) and supersedes a conflicting one (demoted + flagged, T2).
        A proposed implicit preference in the same context is promoted.
        """
        parsed = self._parse(text)
        if parsed is None:
            return None
        ctx, choice, rejected = parsed
        superseded_choice = ""

        existing = self._entries(ctx)
        for entry in existing:
            if entry.content.get("status") != "active":
                continue
            if str(entry.content.get("choice")) == choice:
                entry.revise("preference restated by owner", confidence=min(0.97, entry.confidence + 0.05))
                self.memory.owner_model.save_all()
                return entry
            # conflicting active preference: newest owner statement wins
            superseded_choice = str(entry.content.get("choice"))
            entry.content["status"] = "superseded"
            entry.content["superseded_choice"] = superseded_choice
            entry.revise(
                f"superseded by newer owner preference: {choice} (was {superseded_choice})",
                confidence=entry.confidence * 0.3,
            )
            self.memory.owner_model.save_all()

        # promote a proposed implicit preference in the same context (T4)
        for entry in existing:
            if entry.content.get("status") == "proposed":
                entry.content["status"] = "active"
                entry.content["choice"] = choice
                entry.revise(f"confirmed by explicit owner statement: {choice}", confidence=0.85)
                self.memory.owner_model.save_all()
                return entry

        new_entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.OWNER_MODEL,
            content={
                "type": "preference",
                "context": ctx,
                "choice": choice,
                "rejected": rejected or "",
                "status": "active",
                "superseded_choice": superseded_choice,
            },
            source=Source.OWNER,
            confidence=0.9,
        )
        self.memory.owner_model.append(new_entry)
        return new_entry

    def _parse(self, text: str) -> Optional[tuple[str, str, str]]:
        match = _WHEN_UNCERTAIN.match(text)
        if match:
            ctx = _NORMALIZED_CTX.get(match.group("ctx").lower().strip(), match.group("ctx").lower().strip())
            return ctx, self._clean(match.group("choice")), ""
        match = _WITH_VS.match(text)
        if match:
            return "general", self._clean(match.group("choice")), self._clean(match.group("rejected"))
        match = _LIKE_VS.match(text)
        if match:
            return "general", self._clean(match.group("choice")), self._clean(match.group("rejected"))
        match = _WITH_BARE.match(text)
        if match:
            return "general", self._clean(match.group("choice")), ""
        return None

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().strip(".,")).lower()

    # -- implicit discovery from history (T4 "from history alone") -----------

    def mine_implicit(self, episodes: list[Entry], min_repeats: int = 2) -> list[Entry]:
        """Propose preferences from repeated corrections in one topic category.

        Returns newly proposed entries (owner model, status "proposed",
        confidence 0.4). They become active only when the owner states the
        preference explicitly (learn() promotes them).
        """
        proposals: list[Entry] = []
        for ctx, keywords in _CATEGORIES:
            count = 0
            for episode in episodes:
                if not episode.content.get("was_correction"):
                    continue
                remainder = str(episode.content.get("user_text", ""))
                # 3+ letters so short words like "ask" can match topic keywords
                tokens = {t for t in re.findall(r"[a-z]{3,}", remainder.lower())}
                if tokens & keywords:
                    count += 1
            if count < min_repeats:
                continue
            if self._entries(ctx):
                continue  # already known (active, proposed, or superseded)
            entry = Entry(
                id=self.memory.allocate_id(),
                kind=RecordKind.OWNER_MODEL,
                content={
                    "type": "preference",
                    "context": ctx,
                    "choice": "<awaiting owner confirmation>",
                    "rejected": "",
                    "status": "proposed",
                    "proposed_from": "corrections",
                    "repeat_count": count,
                },
                source=Source.INFERENCE,
                confidence=0.4,
            )
            self.memory.owner_model.append(entry)
            proposals.append(entry)
        return proposals

    def _entries(self, ctx: str) -> list[Entry]:
        return self.memory.query(kind="owner_model", type="preference", context=ctx)
