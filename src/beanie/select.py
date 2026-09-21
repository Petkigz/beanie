"""ARCHITECTURE §13.5: the RSI selector — advisory by architecture.

Choosing WHAT to improve is a different organ from improving it. This module
scans the mind's evidence signals (pending skill proposals, failure receipts,
incubated questions, calibration buckets) and emits ranked Proposal objects.
It can propose; it can never execute, approve itself, or mutate anything:
real change still goes through the permission organ, a test battery, and the
owner where the risk asks for it. That asymmetry is the constitution, not a
phase we grow out of.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# action classes the selector is allowed to speak in; "execute" is not on it
ALLOWED_ACTION_CLASSES = ("promote", "probe", "tune", "patch")
_RISK_WEIGHT = {"low": 1.0, "medium": 2.0}   # selector never proposes 'high' — those live in the gate


@dataclass
class ImprovementProposal:
    lane: str               # skill | curiosity | calibration
    action_class: str       # one of ALLOWED_ACTION_CLASSES
    title: str
    evidence: dict[str, Any] = field(default_factory=dict)
    risk: str = "low"
    score: float = 0.0

    def to_line(self) -> str:
        return f"[{self.lane}/{self.action_class}, risk={self.risk}] {self.title} (score {self.score:.2f})"


class ImprovementSelector:
    """Rank what to improve next from live evidence — advice only, no hands (§13.5)."""

    def __init__(self, mind) -> None:
        self.mind = mind

    def _proposals(self) -> list[ImprovementProposal]:
        out: list[ImprovementProposal] = []

        # 1) SKILL lane: pending proposals want promotion; failure receipts want repair
        skills = self.mind.learner.active_skills()
        pending = self.mind.memory.query(kind="procedural", type="skill", status="proposed")
        for entry in pending:
            title = str(entry.content.get("title", entry.id))
            out.append(ImprovementProposal(
                lane="skill", action_class="promote",
                title=f"skill awaiting your confirmation: '{title}' — confirm or reject",
                evidence={"skill_id": entry.id, "goal_class": entry.content.get("goal_class", "")},
                risk="low",
                score=1.0 / _RISK_WEIGHT["low"],
            ))
        for entry in skills:
            failures = entry.content.get("failure_modes") or []
            if failures:
                title = str(entry.content.get("title", entry.id))
                out.append(ImprovementProposal(
                    lane="skill", action_class="patch",
                    title=f"repair skill '{title}': {len(failures)} recorded failure mode(s) want a fix",
                    evidence={"skill_id": entry.id, "failures": len(failures)},
                    risk="medium",
                    score=min(3.0, float(len(failures))) / _RISK_WEIGHT["medium"],
                ))

        # 2) CURIOSITY lane: incubated questions whose evidence may have arrived
        due = self.mind.incubator.due_for_revisit()
        if due:
            out.append(ImprovementProposal(
                lane="curiosity", action_class="probe",
                title=f"{len(due)} incubated question(s) due for revisit — check whether new evidence answers them",
                evidence={"due": len(due)},
                risk="low",
                score=min(3.0, float(len(due))) / _RISK_WEIGHT["low"],
            ))

        # 3) CALIBRATION lane: correction pressure on a confidence label
        from .calibration import UsefulnessTracker
        summary = UsefulnessTracker.summary(self.mind.trace)
        failures_by_label = summary.get("failures_by_label", {})
        failures_total = sum(failures_by_label.values())
        if failures_total:
            hottest = max(failures_by_label, key=failures_by_label.get)
            out.append(ImprovementProposal(
                lane="calibration", action_class="tune",
                title=f"confidence label '{hottest}' keeps drawing corrections — re-audit its honesty buckets",
                evidence={"failures_by_label": failures_by_label,
                          "mean_rating_by_label": summary.get("mean_rating_by_label", {})},
                risk="medium",
                score=min(2.5, failures_total / 2.0) / _RISK_WEIGHT["medium"],
            ))

        out.sort(key=lambda p: p.score, reverse=True)
        return out

    def proposals(self, limit: int = 6) -> list[ImprovementProposal]:
        return self._proposals()[:limit]

    def report(self, limit: int = 6) -> str:
        header = ("improvement proposals — advisory only (choosing what to improve ≠ "
                  "improving it; execution stays behind your permissions and receipts):")
        proposals = self.proposals(limit)
        if not proposals:
            return header + "\n  no improvement signals on record yet — a few real turns of use " \
                          "seed the selector (failures, confirmations, corrections, ratings)."
        return header + "\n" + "\n".join(f"  {p.to_line()}" for p in proposals)
