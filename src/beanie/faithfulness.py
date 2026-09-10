"""Explanation faithfulness audit — the §9.9 protocol (T10).

Traceability: ARCHITECTURE §9.9 (*"the audit protocol proving the explanation
service cites the actual reasons a decision was made, not plausible ones"*) and
VISION property 9. This module is the mechanism that answers §9.9.

The check is mechanical, not editorial. For every explanation:

1. **Every citation resolves.** A claim that names `record:<id>` or
   `turn:<id>:decision.<key>` must point at something that actually exists in
   the trace/stores. An invented citation is a violation
   (`unknown_citation`) — this is what catches a *plausible* explanation.
2. **Every claim is what the source says.** The values a sentence asserts must
   equal the values in the store/trace (`asserted_mismatch`), and the values the
   builder recorded as read must equal what re-resolution finds (`misread`), so
   a claim cannot be written first and cited afterwards.
3. **Nothing material is silent.** Inputs that demonstrably shaped the decision —
   the question answered, the effort depth, an escalation, each pre-flight
   concern, the calibration weights that moved the number, the residual — must
   each have a claim. An omitted deciding factor is a violation
   (`silent_material_input`), which is the failure mode of an explanation that
   reads well and leaves out the real reason.
4. **The summary is backed.** The rendered summary must be the text of a
   `summary` claim (`unbacked_summary`), so no free-floating sentence can be
   added to an explanation.

**Boundary of the claim.** This proves the explanation matches the recorded
trace. It cannot prove the trace captured everything the substrate did
internally; that remains open in §9.9 and is stated in the register rather than
papered over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .explain import CALIBRATION_WEIGHTS, Explanation, age_days, reply_snippet, snippet
from .stores import Memory
from .trace import Trace, TraceEvent


# Values rendered as a phrase instead of verbatim. One documented exception
# beats a per-claim escape hatch: every other scalar a claim asserts must appear
# in the sentence it renders, so text and citation cannot drift apart.
PHRASED_KEYS = {
    "age_days": "rendered as a freshness phrase ('today' / 'N days old')",
}


def _turn_decision(trace: Trace, turn_id: str) -> Optional[TraceEvent]:
    return next((e for e in trace.events_for(turn_id) if e.kind == "decision"), None)


def resolve_ref(ref: str, *, trace: Trace, memory: Memory) -> Optional[dict[str, Any]]:
    """Re-resolve a claim's citation against the live trace/stores.

    Returns the actual values at the reference, or None when nothing is there —
    which is exactly what an invented citation looks like.
    """
    if ref == "record:none":
        return {}
    if ref.startswith("record:"):
        entry = memory.find(ref.split(":", 1)[1])
        if entry is None:
            return None
        return {
            "confidence": entry.confidence,
            "source": entry.source.value,
            "text": snippet(entry),
            "age_days": age_days(entry),
            "reply": reply_snippet(entry.content.get("reply", "")),
            "created_at": entry.created_at,
            "label": entry.content.get("label", "n/a"),
            "content": dict(entry.content),  # so claims can assert what they read
        }
    if not ref.startswith("turn:"):
        return None
    _, turn_id, rest = ref.split(":", 2) if ref.count(":") >= 2 else ("", "", "")
    if not turn_id:
        return None

    if rest == "perception.user_text":
        for event in trace.events_for(turn_id):
            if event.kind == "perception" and event.payload.get("user_text"):
                return {"user_text": str(event.payload["user_text"])}
        return None

    if "[" in rest and rest.endswith("]"):
        kind, _, raw = rest.partition("[")
        try:
            index = int(raw[:-1])
        except ValueError:
            return None
        events = [e for e in trace.events_for(turn_id) if e.kind == kind]
        if not (0 <= index < len(events)):
            return None
        return dict(events[index].payload)

    if rest == "decision" or rest.startswith("decision."):
        decision = _turn_decision(trace, turn_id)
        if decision is None:
            return None
        tail = rest.split(".", 1)[1] if "." in rest else ""
        if not tail:
            return dict(decision.payload)
        index = None
        if "[" in tail and tail.endswith("]"):
            key, _, raw = tail.partition("[")
            try:
                index = int(raw[:-1])
            except ValueError:
                return None
            tail = key
        value = decision.payload.get(tail)
        if index is not None:
            if not isinstance(value, list) or not (0 <= index < len(value)):
                return None
            value = value[index]
            if not isinstance(value, dict):
                return None
            return dict(value)
        if tail not in decision.payload:
            return None
        if tail == "reply":
            value = reply_snippet(value)
        return {tail: value}
    return None


def material_refs(trace: Trace, memory: Memory, turn_id: str) -> dict[str, str]:
    """The inputs that demonstrably shaped this turn's decision, and why each
    one is material. Every entry must be cited or the audit fails."""
    required: dict[str, str] = {}
    for event in trace.events_for(turn_id):
        if event.kind == "perception" and event.payload.get("user_text"):
            required[f"turn:{turn_id}:perception.user_text"] = "the question the answer belongs to"
            break
    decision = _turn_decision(trace, turn_id)
    if decision is None:
        return required
    depth = decision.payload.get("depth")
    if depth == "deterministic" and decision.payload.get("handler"):
        required[f"turn:{turn_id}:decision.handler"] = "which organ answered without a model tier"
    elif depth:
        required[f"turn:{turn_id}:decision.depth"] = "which tier answered"
    if decision.payload.get("escalated_from"):
        required[f"turn:{turn_id}:decision.escalated_from"] = "why effort was raised"
    for index, concern in enumerate(decision.payload.get("concerns") or []):
        if concern.get("kind") != "none":
            required[f"turn:{turn_id}:decision.concerns[{index}]"] = "a concern raised before answering"
    calibration = decision.payload.get("calibration") or {}
    if any(calibration.get(key) for key in CALIBRATION_WEIGHTS):
        required[f"turn:{turn_id}:decision.calibration"] = "what moved the confidence"
    if decision.payload.get("residual"):
        required[f"turn:{turn_id}:decision.residual"] = "the residual uncertainty"
    outcome = next((e for e in trace.events_for(turn_id) if e.kind == "outcome"), None)
    record_id = outcome.payload.get("record_id") if outcome else None
    if record_id and memory.find(record_id) is not None:
        required[f"record:{record_id}"] = "the record this turn created"
    # action turns: what ran, and what the authority gate allowed (§7)
    for index, event in enumerate(e for e in trace.events_for(turn_id) if e.kind == "outcome"):
        if "goal" in event.payload or "skill_id" in event.payload:
            required[f"turn:{turn_id}:outcome[{index}]"] = "what the action actually did"
            skill_id = event.payload.get("skill_id")
            if skill_id and memory.find(str(skill_id)) is not None:
                required[f"record:{skill_id}"] = "the learned skill that ran"
    for index, event in enumerate(e for e in trace.events_for(turn_id) if e.kind == "authority"):
        required[f"turn:{turn_id}:authority[{index}]"] = "the permission state that governed it"
    return required


@dataclass
class FaithfulnessReport:
    turn_id: str
    record_id: Optional[str]
    claims: int
    required: int
    violations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def faithful(self) -> bool:
        return not self.violations

    def to_text(self) -> str:
        head = f"turn {self.turn_id}: " + ("faithful" if self.faithful else "UNFAITHFUL")
        head += f" — {self.claims} claim(s) checked against {self.required} material input(s)"
        for violation in self.violations:
            head += f"\n  [{violation['kind']}] {violation['detail']}"
        return head


def audit_explanation(explanation: Explanation, *, trace: Trace, memory: Memory) -> FaithfulnessReport:
    """Run the four §9.9 checks over one explanation."""
    turn_id = explanation.turn_id
    required = material_refs(trace, memory, turn_id) if turn_id else {}
    violations: list[dict[str, Any]] = []
    refs = explanation.refs()

    # 4. the summary must be a claim, not a free-floating sentence
    summary_claims = [c for c in explanation.claims if c.section == "summary"]
    if not summary_claims:
        violations.append({"kind": "unbacked_summary", "ref": "", "detail": "no summary claim: the conclusion is not rendered from a citation"})
    elif summary_claims[0].text != explanation.summary:
        violations.append({"kind": "unbacked_summary", "ref": summary_claims[0].ref,
                           "detail": "the rendered summary is not the text of its claim"})

    for claim in explanation.claims:
        resolved = resolve_ref(claim.ref, trace=trace, memory=memory)
        if resolved is None:
            violations.append({"kind": "unknown_citation", "ref": claim.ref,
                               "detail": f"'{claim.ref}' does not exist in the trace or stores (claimed: {claim.asserted})"})
            continue
        # 2. what the sentence asserts must be what the source says
        for key, value in claim.asserted.items():
            if key not in resolved or resolved[key] != value:
                violations.append({"kind": "asserted_mismatch", "ref": claim.ref,
                                   "detail": f"{key}: explanation says {value!r}, source says {resolved.get(key, '<absent>')!r}"})
        for key, value in claim.actual.items():
            if key not in resolved or resolved[key] != value:
                violations.append({"kind": "misread", "ref": claim.ref,
                                   "detail": f"{key}: claim recorded {value!r}, re-resolution found {resolved.get(key, '<absent>')!r}"})
        # 2b. the sentence must show the values it cites (composite values are
        # checked for equality instead of rendering)
        for key, value in claim.asserted.items():
            if isinstance(value, (dict, list)) or key in PHRASED_KEYS:
                continue
            shown = str(value)
            variants = [shown]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                variants.append(f"{value:g}")  # the display precision the claim declares
            if any(v in claim.text for v in variants):
                continue
            if len(shown) > 40 and shown[:40] in claim.text:
                continue
            violations.append({"kind": "unrendered_value", "ref": claim.ref,
                               "detail": f"the sentence never shows {key}={shown!r}"})

    # 3. nothing material may be silent
    for ref, why in required.items():
        if ref not in refs:
            violations.append({"kind": "silent_material_input", "ref": ref,
                               "detail": f"the explanation never mentions {why}"})

    return FaithfulnessReport(
        turn_id=turn_id,
        record_id=explanation.record_id,
        claims=len(explanation.claims),
        required=len(required),
        violations=violations,
    )


def audit_mind(mind: Any, *, limit: int = 0) -> tuple[list[FaithfulnessReport], dict[str, int]]:
    """Audit every turn in a mind's trace that has a decision event."""
    reports: list[FaithfulnessReport] = []
    turn_ids: list[str] = []
    for event in mind.trace.events:
        if event.kind == "decision" and event.turn_id not in turn_ids:
            turn_ids.append(event.turn_id)
    if limit:
        turn_ids = turn_ids[-limit:]
    for turn_id in turn_ids:
        explanation = mind.explainer.explain_turn(turn_id)
        if explanation is None:
            continue
        reports.append(audit_explanation(explanation, trace=mind.trace, memory=mind.memory))
    audited = set(turn_ids)
    unaudited = sorted({
        event.turn_id for event in mind.trace.events
        if event.kind == "outcome" and event.turn_id not in audited
    })
    summary = {
        "turns": len(reports),
        "faithful": sum(1 for r in reports if r.faithful),
        "violations": sum(len(r.violations) for r in reports),
        "claims": sum(r.claims for r in reports),
        "unaudited": len(unaudited),
    }
    for turn_id in unaudited:
        reports.append(FaithfulnessReport(
            turn_id=turn_id, record_id=None, claims=0, required=0,
            violations=[{"kind": "no_decision_trace", "ref": f"turn:{turn_id}",
                         "detail": "this turn has an outcome but recorded no decision — it cannot be audited"}],
        ))
    return reports, summary
