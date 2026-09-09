"""Prospective memory — intentions held in the background while focusing (§3.7).

Traceability: ARCHITECTURE §3.7 (intentions & commitments store: trigger
condition, deadline or turn-count, priority, origin episode; the loop checks
the store against every perception and turn — Domain B prospective memory).
Intentions that die silently (owner said "never mind") are logged as
revisions, not ghosts.

Two trigger kinds: turn-count ("remind me in 3 turns/messages to …") and
wall-clock ("remind me tomorrow at 09:00 / in 30 minutes to …"). Firing is
checked by Mind.tick() and after every step.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from typing import Optional

from .records import Entry, RecordKind, Source, Volatility
from .stores import Memory

UTC = _dt.timezone.utc

_TURN_RE = re.compile(r"^\s*remind\s+me\s+in\s+(\d+)\s+(?:turns?|messages?|steps?)\s+to\s+(.+?)\s*\.?\s*$", re.IGNORECASE)
_MINUTE_RE = re.compile(r"^\s*remind\s+me\s+in\s+(\d+)\s+minutes?\s+to\s+(.+?)\s*\.?\s*$", re.IGNORECASE)
_HOUR_RE = re.compile(r"^\s*remind\s+me\s+in\s+(\d+)\s+hours?\s+to\s+(.+?)\s*\.?\s*$", re.IGNORECASE)
_TOMORROW_RE = re.compile(r"^\s*remind\s+me\s+tomorrow\s+at\s+(\d{1,2}):(\d{2})\s+to\s+(.+?)\s*\.?\s*$", re.IGNORECASE)
_CANCEL_RE = re.compile(r"^\s*(?:cancel|forget|never\s+mind(?:\s+the)?)\s+(?:the\s+)?(?:reminder|intention)?\s*(?:about\s+)?(.+?)\s*\.?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedIntention:
    action: str
    in_turns: Optional[int] = None
    due_at: Optional[str] = None  # ISO-8601


def parse(text: str, now: Optional[str] = None) -> Optional[ParsedIntention]:
    """Parse owner "remind me …" statements into an intention (§3.7)."""
    match = _TURN_RE.match(text)
    if match:
        return ParsedIntention(action=match.group(2).strip(), in_turns=int(match.group(1)))
    now = now or _dt.datetime.now(UTC)
    if isinstance(now, str):
        now = _dt.datetime.fromisoformat(now)
    match = _MINUTE_RE.match(text)
    if match:
        due = now + _dt.timedelta(minutes=int(match.group(1)))
        return ParsedIntention(action=match.group(2).strip(), due_at=due.isoformat(timespec="minutes"))
    match = _HOUR_RE.match(text)
    if match:
        due = now + _dt.timedelta(hours=int(match.group(1)))
        return ParsedIntention(action=match.group(2).strip(), due_at=due.isoformat(timespec="minutes"))
    match = _TOMORROW_RE.match(text)
    if match:
        due = (now + _dt.timedelta(days=1)).replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)
        return ParsedIntention(action=match.group(3).strip(), due_at=due.isoformat(timespec="minutes"))
    return None


class IntentionKeeper:
    """The intention store + due-checking (prospective memory, §3.7)."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def add(self, parsed: ParsedIntention, origin_turn: Optional[str] = None) -> Entry:
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.INTENTION,
            content={
                "type": "intention",
                "action": parsed.action,
                "status": "pending",
                "in_turns": parsed.in_turns,
                "due_at": parsed.due_at,
                "origin_turn": origin_turn,
            },
            source=Source.OWNER,
            confidence=0.95,
        )
        self.memory.intentions.append(entry)
        return entry

    def pending(self) -> list[Entry]:
        return self.memory.query(kind="intention", type="intention", status="pending")

    def advance_turns(self, n: int = 1) -> list[Entry]:
        """Decrement turn-count intentions; return ones due right now."""
        due: list[Entry] = []
        for entry in self.pending():
            remaining = entry.content.get("in_turns")
            if remaining is None:
                continue
            remaining = int(remaining) - n
            entry.content["in_turns"] = max(remaining, 0)
            entry.revise(f"advanced {n} turn(s); {remaining} left" if remaining else "turn count reached")
            if remaining <= 0:
                due.append(entry)
        self.memory.intentions.save_all()
        return due

    def due_wallclock(self, now: Optional[str] = None) -> list[Entry]:
        now = now or _dt.datetime.now(UTC).isoformat(timespec="minutes")
        due: list[Entry] = []
        for entry in self.pending():
            due_at = entry.content.get("due_at")
            if due_at and due_at <= now:
                due.append(entry)
        return due

    def fire(self, entry: Entry) -> str:
        """Mark fired; returns the reminder text to surface to the owner."""
        action = str(entry.content.get("action"))
        entry.content["status"] = "fired"
        entry.revise(f"reminder fired: {action}", confidence=1.0)
        self.memory.intentions.save_all()
        return action

    def cancel_matching(self, text: str) -> Optional[Entry]:
        """Owner says never mind → cancel with a revision, not a ghost (§3.7)."""
        match = _CANCEL_RE.match(text)
        if not match:
            return None
        needle = match.group(1).strip().lower()
        for entry in self.pending():
            if needle in str(entry.content.get("action", "")).lower() or needle == "reminder":
                entry.content["status"] = "cancelled"
                entry.revise("cancelled by owner")
                self.memory.intentions.save_all()
                return entry
        return None
