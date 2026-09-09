"""Calibration & usefulness — evidence-state confidence for replies.

Traceability: VISION property 7 and test T8 (calibrated communication:
labels must be derived from the evidence state, not from phrasing) and
ARCHITECTURE §4.6 (effort allocation) + VISION property 13/T13 (usefulness).

The calibrator starts from the substrate's own reported confidence (the
model's internal signal) and adjusts it with the mind's evidence state:
recent corrections about the same subject lower it, corroborating stored
facts raise it, open questions lower it. The mapping confidence → label is
records.confidence_label (thresholds are open question ARCHITECTURE §9.7).

Usefulness tracking (T13): explicit ratings land in the trace as feedback
events; implicit signals (corrections) are counted per label bucket so the
effort policy can later be driven by the correlation.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from .records import Entry, confidence_label
from .stores import Memory
from .trace import Trace


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", text.lower()) if not t.isdigit()}


class Calibrator:
    """Adjust substrate confidence by the evidence state (T8)."""

    CORRECTION_PENALTY = 0.15
    CONFIRM_BOOST = 0.05
    OPEN_QUESTION_PENALTY = 0.1
    PENALTY_CAP = 0.35
    BOOST_CAP = 0.15

    def __init__(self, memory: Memory, trace: Trace) -> None:
        self.memory = memory
        self.trace = trace

    def assess(self, user_text: str, base: float) -> tuple[float, dict]:
        """Return (adjusted_confidence, reasons) for a reply about `user_text`."""
        tokens = _tokens(user_text)
        supporting = [e for e in self.memory.subjects_matching(tokens) if e.content.get("type") == "fact"]
        open_questions = [
            e for e in self.memory.query(kind="self", type="question")
            if any(t in str(e.content.get("text", "")) for t in tokens)
        ]
        corrections = self._recent_corrections(tokens)

        confidence = base
        reasons: dict[str, int | float] = {"base": round(base, 3)}
        if supporting:
            boost = min(self.BOOST_CAP, self.CONFIRM_BOOST * len(supporting))
            confidence = min(0.97, confidence + boost)
            reasons["corroborated"] = len(supporting)
        if corrections:
            penalty = min(self.PENALTY_CAP, self.CORRECTION_PENALTY * len(corrections))
            confidence = max(0.05, confidence - penalty)
            reasons["recent_corrections"] = len(corrections)
        if open_questions:
            confidence = max(0.05, confidence - self.OPEN_QUESTION_PENALTY)
            reasons["open_questions"] = len(open_questions)
        reasons["label"] = confidence_label(confidence)
        return round(confidence, 3), reasons

    def _recent_corrections(self, tokens: set[str]) -> list[Entry]:
        out: list[Entry] = []
        for episode in self.memory.episodes.latest(20):
            if episode.content.get("was_correction") and _tokens(str(episode.content.get("user_text", ""))) & tokens:
                out.append(episode)
        return out


class UsefulnessTracker:
    """Explicit + implicit usefulness per answer (T13, ARCHITECTURE §8)."""

    def rate(self, trace: Trace, turn_id: str, score: int, note: str = "") -> None:
        """Explicit user rating for a turn (1–5)."""
        trace.append(turn_id, "feedback", {"score": int(score), "note": note})

    @staticmethod
    def summary(trace: Trace) -> dict:
        """Mean explicit rating and correction count per confidence label."""
        buckets: dict[str, list[int]] = {}
        corrections_by_label: dict[str, int] = {}
        outcome_labels: dict[str, str] = {}
        for event in trace.events:
            if event.kind == "outcome":
                outcome_labels[event.turn_id] = str(event.payload.get("label", ""))
            elif event.kind == "feedback":
                label = outcome_labels.get(event.turn_id, "")
                buckets.setdefault(label, []).append(int(event.payload.get("score", 0)))
        for event in trace.events:
            if event.kind == "outcome" and event.failure is not None and event.failure.value != "none":
                label = outcome_labels.get(event.turn_id, "")
                corrections_by_label[label] = corrections_by_label.get(label, 0) + 1
        return {
            "mean_rating_by_label": {label: round(sum(v) / len(v), 2) for label, v in sorted(buckets.items()) if v},
            "failures_by_label": corrections_by_label,
        }
