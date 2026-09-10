"""Owner-model affect *observations* — tone read from what the owner actually says.

Traceability: ARCHITECTURE §3.5 (owner model — what the owner wants, prefers and
is like, stored with provenance), §4.4 (correction channel: how the owner says
something is signal) and §6 (the owner's state shapes how the mind responds, not
what it claims to feel).

The excluded-capability table in CAPABILITY_REGISTER.md rules out "persistent
mood / affective state coloring cognition" — simulating feelings on top of a
model that has none — and names its behavioral proxy in scope: *owner-model
affect observations*. That is what this module is: the mind reads tone markers
in the owner's messages, records them as observations with the evidence that
produced them, and lets them shape its *behavior toward the owner* (slow down,
ask what is wrong, offer to change tack). It never claims to be feeling
anything, and it never diagnoses: it records what was said.

Honesty rules encoded here:
  * observations are evidence-backed (the markers are kept in the record);
  * tone is recent-window, so a bad moment does not become a permanent label;
  * nothing is inferred from content the owner did not express as tone.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .records import Entry, RecordKind, Source

#: conservative frustration markers — tone the owner expresses, not topics
_FRUSTRATION = (
    "frustrat", "annoying", "annoyed", "irritat", "angry", "fed up",
    "not working", "doesn't work", "does not work", "still not", "still wrong",
    "again and again", "keep getting", "why won't", "why wont", "ugh", "ffs",
    "i give up", "this is broken", "makes no sense", "waste of time",
)
#: urgency / time pressure
_URGENCY = (
    "asap", "urgent", "right now", "immediately", "hurry", "quickly",
    "deadline", "running out of time", "today", "before the meeting",
)
#: satisfaction / approval
_SATISFACTION = (
    "thank", "thanks", "perfect", "exactly", "brilliant", "nice", "great",
    "well done", "that works", "works now", "solved", "appreciate",
)
_SHOUT_RE = re.compile(r"\b[A-Z]{4,}\b")
_EMPHASIS_RE = re.compile(r"[!?]{2,}")

TONE_WINDOW = 6  # owner turns considered "recent" for the current read


class AffectObserver:
    """Reads tone from owner messages; stores observations, never feelings."""

    def __init__(self, memory) -> None:
        self.memory = memory

    # -- reading -------------------------------------------------------------
    def read(self, text: str) -> Optional[dict[str, Any]]:
        """Classify one message's tone; None when nothing about tone is expressed."""
        lowered = text.lower()
        markers: list[str] = []
        tone = ""
        for tone_name, phrases in (("frustration", _FRUSTRATION), ("urgency", _URGENCY),
                                   ("satisfaction", _SATISFACTION)):
            hits = [phrase for phrase in phrases if phrase in lowered]
            if hits:
                tone = tone_name
                markers.extend(hits)
                break  # first match wins: frustration > urgency > satisfaction
        if tone != "satisfaction":
            if _EMPHASIS_RE.search(text):
                markers.append("emphatic-punctuation")
                tone = tone or "urgency"
            elif _SHOUT_RE.search(text):
                markers.append("shouting")
                tone = tone or "frustration"
        if not tone or not markers:
            return None
        return {"tone": tone, "markers": sorted(set(markers))[:4], "text": text[:200]}

    def observe(self, turn_id: str, text: str) -> Optional[Entry]:
        """Record a tone observation for this turn, if the owner expressed one."""
        reading = self.read(text)
        if reading is None:
            return None
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.OWNER_MODEL,
            content={"type": "affect_observation", "status": "active",
                     "subject": "owner", **reading},
            source=Source.OWNER,
            confidence=0.6,  # an observation of what was said, not a diagnosis
        )
        self.memory.owner_model.append(entry)
        return entry

    # -- reading back --------------------------------------------------------
    def recent(self, window: int = TONE_WINDOW) -> list[Entry]:
        entries = self.memory.query(kind="owner_model", type="affect_observation")
        return entries[-window:]

    def current_tone(self, window: int = TONE_WINDOW) -> str:
        """The most recent expressed tone in the window ('neutral' if none)."""
        entries = self.recent(window)
        return str(entries[-1].content.get("tone", "neutral")) if entries else "neutral"

    def frustration_streak(self, window: int = TONE_WINDOW) -> int:
        """How many of the recent tone observations were frustration."""
        return sum(1 for e in self.recent(window) if e.content.get("tone") == "frustration")

    def summary(self) -> str:
        """Plain-language read-back for the owner (row 33: their model, cited)."""
        entries = self.recent()
        if not entries:
            return ("I haven't noted anything about how you sound — I only record tone when "
                    "you express it, and I don't guess at feelings.")
        lines = []
        for entry in entries[-4:]:
            markers = ", ".join(entry.content.get("markers", []))
            lines.append(f"  - {entry.content.get('tone')} (you said: \"{entry.content.get('text', '')[:60]}\""
                         f"{f'; markers: {markers}' if markers else ''})")
        return ("What I've noted about how you sound lately (observations, not guesses):\n"
                + "\n".join(lines))
