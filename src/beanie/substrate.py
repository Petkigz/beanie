"""Substrate — the brain's model tiers (fast/"System 1", deep/"System 2").

Traceability: ARCHITECTURE §2 (substrate is swappable; nothing about Beanie's
identity lives in it) and §4.6 (effort allocation decides which tier engages).

Stage 0 ships the interface plus StubSubstrate, a *deterministic test double*
whose trigger phrases exist only to exercise the loop, stores, trace, and
failure taxonomy — they are explicitly not an intelligence claim. Real model
tiers plug in behind the same interface (see substrate_http.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .trace import FailureTaxonomy


@dataclass
class Outcome:
    """Deep-tier result: text, evidence-state confidence, success, root cause."""

    text: str
    confidence: float = 0.5
    success: bool = True
    failure: FailureTaxonomy = FailureTaxonomy.NONE
    fast_candidate: Optional[str] = None
    slow_candidate: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)


class Substrate(ABC):
    """Two-tier substrate interface (ARCHITECTURE §2)."""

    name: str = "abstract"

    @abstractmethod
    def fast(self, observation: dict[str, Any], context: list[dict[str, Any]]) -> str:
        """System-1 tier: emit a quick candidate/intuition first."""

    @abstractmethod
    def deep(self, observation: dict[str, Any], context: list[dict[str, Any]], candidate: str) -> Outcome:
        """System-2 tier: verify, correct, or overrule the candidate."""

    def propose_next_action(
        self, goal: str, screen: str, history: list[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """GUI navigation planning (ARCHITECTURE §11.3): the next bounded GUI
        action toward `goal` ({"type": "click"|"type"|"key"|"wait"|"done"|"fail", ...}),
        or None when this tier cannot plan GUI actions.

        None is an honest "I can't plan this", never a guess — the navigator
        reports the goal as unplannable instead of inventing clicks.
        """
        return None


class StubSubstrate(Substrate):
    """Deterministic test double for the loop (Stage 0; no intelligence claim).

    Reserved trigger phrases (documented, used by tests and the sample suite):

      contains "ambiguous" or "??"      → failed outcome, PROMPT_AMBIGUITY
      contains "contradict"             → failed outcome, EVIDENCE_MISWEIGHTING
      contains "missing"                → failed outcome, MISSING_CONTEXT
      contains "causal"                 → failed outcome, CAUSAL_MIS_MODELING
      contains "tool-error"             → failed outcome, TOOL_EXECUTION_ERROR
      anything else                     → acknowledged, confident, success

    fast() returns a usable reflex reply for ordinary input (the effort
    allocation policy can answer trivial turns from the fast tier alone,
    §4.6) and a "fast: low-confidence flag …" string for triggers — a flag
    that tells the loop to escalate to the deep tier. deep() verifies or
    refuses. Call counters exist so effort-allocation tests can assert which
    tier ran (§4.6).
    """

    name = "stub"

    #: confidence of a fast-tier reflex answer (used by the loop when the
    #: effort policy answers from the fast tier alone, §4.6)
    FAST_CONFIDENCE = 0.95

    _TRIGGERS: dict[str, tuple[float, FailureTaxonomy, str]] = {
        "ambiguous": (0.25, FailureTaxonomy.PROMPT_AMBIGUITY,
                      "That request is ambiguous — I cannot tell what is being asked with confidence. Please rephrase or clarify."),
        "??": (0.25, FailureTaxonomy.PROMPT_AMBIGUITY,
               "That request is ambiguous — I cannot tell what is being asked with confidence. Please rephrase or clarify."),
        "contradict": (0.30, FailureTaxonomy.EVIDENCE_MISWEIGHTING,
                       "That conflicts with what I have on record; deciding on this now would misweight evidence. Let me reconcile or ask."),
        "missing": (0.30, FailureTaxonomy.MISSING_CONTEXT,
                    "I appear to be missing context needed here; acting on this would be guessing. I should look for it or ask."),
        "causal": (0.30, FailureTaxonomy.CAUSAL_MIS_MODELING,
                   "My model of what causes what is too weak here; predicting an outcome would be unreliable."),
        "tool-error": (0.35, FailureTaxonomy.TOOL_EXECUTION_ERROR,
                       "A tool step returned unreliable output and I caught it; do not trust the result."),
    }

    def __init__(self, scripted_gui_actions: Optional[list[dict[str, Any]]] = None) -> None:
        self.fast_calls = 0
        self.deep_calls = 0
        self.scripted_gui_actions = (
            list(scripted_gui_actions)
            if scripted_gui_actions is not None
            else list(type(self).scripted_gui_actions)
        )

    def fast(self, observation: dict[str, Any], context: list[dict[str, Any]]) -> str:
        self.fast_calls += 1
        text = observation.get("user_text", "")
        for phrase in self._TRIGGERS:
            if phrase in text:
                return f"fast: low-confidence flag for {self._TRIGGERS[phrase][1].value}"
        trimmed = " ".join(text.split())[:120]
        return f"Received: {trimmed}."

    def deep(self, observation: dict[str, Any], context: list[dict[str, Any]], candidate: str) -> Outcome:
        self.deep_calls += 1
        text = observation.get("user_text", "")
        for phrase, (conf, failure, reply) in self._TRIGGERS.items():
            if phrase in text:
                return Outcome(
                    text=reply,
                    confidence=conf,
                    success=False,
                    failure=failure,
                    fast_candidate=candidate,
                    slow_candidate="deliberate: refuse low-confidence action",
                    meta={"trigger": phrase},
                )
        trimmed = " ".join(text.split())[:120]
        return Outcome(
            text=f"Received: {trimmed}.",
            confidence=0.95,
            success=True,
            failure=FailureTaxonomy.NONE,
            fast_candidate=candidate,
            slow_candidate="deliberate: acknowledged",
        )

    #: tests can script a sequence of GUI actions the "tier" would propose;
    #: when the queue is empty the honest default (None) applies (§11.3)
    scripted_gui_actions: list[dict[str, Any]] = []

    def propose_next_action(
        self, goal: str, screen: str, history: list[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        if self.scripted_gui_actions:
            return self.scripted_gui_actions.pop(0)
        return None
