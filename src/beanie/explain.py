"""Explanation service — user-facing reasoning, on demand (§4.5, T10, §9.9).

Traceability: ARCHITECTURE §4.5 (a summarization layer over the trace: the
conclusion, the evidence it rested on — named with freshness/quality — the
alternatives considered and why they lost, and residual uncertainty; plain
language; never raw chain-of-thought), VISION property 9, and ARCHITECTURE §9.9
(the audit protocol proving an explanation cites the *actual* reasons a decision
was made, not plausible ones).

**Provenance-first.** An explanation is a list of :class:`Claim` objects. Each
claim carries the sentence it renders, the reference it was read from
(`record:<id>`, `turn:<id>:decision.<key>`, `turn:<id>:decision.concerns[i]`,
…), what the sentence asserts, and what was actually read. The text is rendered
*from* the claims, so the sentence and its citation cannot drift apart — and
`beanie.faithfulness` can re-resolve every reference against the trace and the
stores and prove the explanation said what was really there (§9.9).

What this does **not** claim: the audit proves the explanation matches the
recorded trace. It cannot prove the trace captured everything the substrate did
internally — that boundary is stated in §9.9 and left open.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Optional

from .records import Entry
from .stores import Memory
from .trace import Trace

UTC = _dt.timezone.utc

# Section order in the rendered explanation (§4.5)
CLAIM_SECTIONS = ("context", "effort", "evidence", "alternative", "confidence", "residual")

# calibration keys that mean "the evidence state moved the number" — their
# presence makes the confidence reasoning a material input (§9.9)
CALIBRATION_WEIGHTS = {
    "corroborated": "supporting record(s) counted for",
    "recent_corrections": "recent correction(s) counted against",
    "open_questions": "open question(s) counted against",
    "concerns": "pre-flight concern(s) counted against",
}


def reply_snippet(text: Any) -> str:
    """The quoted reply — shared by the builder and the auditor, so truncation
    can never make an honest claim look false."""
    return str(text)[:160]


def snippet(entry: Entry) -> str:
    """The quoted text for an evidence line — one derivation, used by the
    builder and by the auditor, so a fabricated quote cannot survive."""
    return str(entry.content.get("user_text", entry.id))[:100]


def _parse(at: str) -> Optional[_dt.datetime]:
    try:
        parsed = _dt.datetime.fromisoformat(at)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def age_days(entry: Entry, *, now: Optional[_dt.datetime] = None) -> Optional[int]:
    """Whole days since the entry was last observed/updated (§4.5 freshness)."""
    reference = entry.last_observed_at or entry.updated_at or entry.created_at
    parsed = _parse(reference)
    if parsed is None:
        return None
    return max(0, ((now or _dt.datetime.now(UTC)) - parsed).days)


def age_phrase(days: Optional[int]) -> str:
    if days is None:
        return "freshness unknown"
    if days == 0:
        return "today"
    if days == 1:
        return "1 day old"
    return f"{days} days old"


@dataclass
class Claim:
    """One auditable sentence: what it says, where it was read from, and what
    was actually there (§9.9)."""

    section: str
    text: str
    ref: str
    asserted: dict[str, Any] = field(default_factory=dict)
    actual: dict[str, Any] = field(default_factory=dict)


@dataclass
class Explanation:
    turn_id: str
    record_id: Optional[str]
    summary: str
    claims: list[Claim] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    residual_uncertainty: str = ""

    def claims_for(self, section: str) -> list[Claim]:
        return [c for c in self.claims if c.section == section]

    def to_text(self) -> str:
        """Render the claims. Every line below comes from a citation."""
        lines = [self.summary]
        blocks = {
            "context": "What I was answering:",
            "effort": "How much effort it took:",
            "evidence": "Evidence I used:",
            "alternative": "Alternatives I considered and set aside:",
            "confidence": "How the confidence was reached:",
        }
        for section in CLAIM_SECTIONS:
            claims = self.claims_for(section)
            if not claims:
                continue
            if section == "residual":
                continue
            lines.append(blocks[section] if section != "context" else blocks["context"])
            lines.extend(f"  - {claim.text}" for claim in claims)
        residual = self.claims_for("residual")
        if residual:
            lines.append(f"Residual uncertainty: {residual[0].text}")
        return "\n".join(lines)

    def refs(self) -> set[str]:
        return {claim.ref for claim in self.claims}


class ExplanationService:
    """Compose auditable explanations from the trace + stores (§4.5, §9.9)."""

    def __init__(self, memory: Memory, trace: Trace) -> None:
        self.memory = memory
        self.trace = trace

    # ----------------------------------------------------------------- API
    def explain_record(self, record_id: str) -> Optional[Explanation]:
        entry = self.memory.find(record_id)
        if entry is None:
            return None
        turn_id = str(entry.content.get("turn_id", "") or "")
        return self._build(turn_id=turn_id, record_id=record_id, entry=entry)

    def explain_turn(self, turn_id: str) -> Optional[Explanation]:
        events = self.trace.events_for(turn_id)
        if not events:
            return None
        outcome = next((e for e in events if e.kind == "outcome"), None)
        record_id = outcome.payload.get("record_id") if outcome else None
        entry = self.memory.find(record_id) if record_id else None
        return self._build(turn_id=turn_id, record_id=record_id, entry=entry)

    # ------------------------------------------------------------- builder
    def _decision(self, turn_id: str) -> Optional[Any]:
        return next((e for e in self.trace.events_for(turn_id) if e.kind == "decision"), None)

    def _events_of(self, turn_id: str, kind: str) -> list[Any]:
        return [e for e in self.trace.events_for(turn_id) if e.kind == kind]

    def _perception_text(self, turn_id: str) -> Optional[str]:
        for event in self.trace.events_for(turn_id):
            if event.kind == "perception" and event.payload.get("user_text"):
                return str(event.payload["user_text"])
        return None

    def _build(
        self,
        *,
        turn_id: str = "",
        record_id: Optional[str] = None,
        entry: Optional[Entry],
    ) -> Explanation:
        claims: list[Claim] = []
        decision = self._decision(turn_id) if turn_id else None

        # --- context: the question this answer belongs to -------------------
        question = self._perception_text(turn_id) if turn_id else None
        if question:
            claims.append(
                Claim(
                    section="context",
                    text=f"'{question[:120]}'",
                    ref=f"turn:{turn_id}:perception.user_text",
                    asserted={"user_text": question},
                    actual={"user_text": question},
                )
            )

        # --- effort: which tier ran, and whether it escalated (§4.6) --------
        if decision is not None:
            depth = decision.payload.get("depth", "")
            escalated = decision.payload.get("escalated_from") or None
            handler = decision.payload.get("handler")
            if depth:
                if str(depth) == "deterministic" and handler:
                    # a rule-governed answer: say which organ answered, so the
                    # explanation never implies a model tier reasoned (§9.9)
                    claims.append(
                        Claim(
                            section="effort",
                            text=f"answered by {handler}; no model tier was used",
                            ref=f"turn:{turn_id}:decision.handler",
                            asserted={"handler": handler},
                            actual={"handler": handler},
                        )
                    )
                else:
                    phrase = {
                        "reflex": "the fast tier answered alone at reflex depth (trivial, low-stakes input)",
                        "deep": "the deep tier reviewed a fast-tier candidate at deep depth",
                        "deep_verified": "the deep tier answered at deep_verified depth after the "
                                         "adversarial pre-flight check",
                    }.get(str(depth), f"depth '{depth}'")
                    claims.append(
                        Claim(
                            section="effort",
                            text=phrase,
                            ref=f"turn:{turn_id}:decision.depth",
                            asserted={"depth": depth},
                            actual={"depth": depth},
                        )
                    )
            if escalated:
                claims.append(
                    Claim(
                        section="effort",
                        text=f"escalated from '{escalated}' — the fast tier flagged low confidence "
                             "instead of answering (§2 contract)",
                        ref=f"turn:{turn_id}:decision.escalated_from",
                        asserted={"escalated_from": escalated},
                        actual={"escalated_from": escalated},
                    )
                )

        # --- evidence: the records actually attached to this one ------------
        if entry is not None:
            for ref in entry.evidence_refs:
                ref_entry = self.memory.find(ref.record_id)
                if ref_entry is None:
                    continue
                days = age_days(ref_entry)
                quote = snippet(ref_entry)
                claims.append(
                    Claim(
                        section="evidence",
                        text=f"{ref.role}: '{quote}' (confidence {ref_entry.confidence:g}, "
                             f"{ref_entry.source.value}, {age_phrase(days)})",
                        ref=f"record:{ref_entry.id}",
                        asserted={
                            "confidence": ref_entry.confidence,
                            "source": ref_entry.source.value,
                            "text": quote,
                            "age_days": days,
                        },
                        actual={
                            "confidence": ref_entry.confidence,
                            "source": ref_entry.source.value,
                            "text": quote,
                            "age_days": days,
                        },
                    )
                )

        # --- alternatives: the pre-flight concerns, and why they lost (§4.7) -
        for index, concern in enumerate(decision.payload.get("concerns") or [] if decision else []):
            if concern.get("kind") == "none":
                continue
            detail = str(concern.get("detail", "a concern was noted"))
            cited = f" (raised against record {concern['entry_id']})" if concern.get("entry_id") else ""
            claims.append(
                Claim(
                    section="alternative",
                    text=f"{concern.get('kind', 'concern')}: {detail}{cited} — noted, not decisive",
                    ref=f"turn:{turn_id}:decision.concerns[{index}]",
                    asserted={
                        "kind": concern.get("kind"),
                        "detail": concern.get("detail"),
                        "entry_id": concern.get("entry_id"),
                    },
                    actual=dict(concern),
                )
            )

        # --- confidence: what the evidence state did to the number (T8) -----
        if decision is not None:
            calibration = decision.payload.get("calibration") or {}
            weighted = {k: v for k, v in calibration.items() if k in CALIBRATION_WEIGHTS and v}
            if weighted:
                parts = [f"base {calibration.get('base', 'n/a')}"]
                for key, value in weighted.items():
                    parts.append(f"{value} {CALIBRATION_WEIGHTS[key]} it")
                parts.append(f"label '{calibration.get('label', 'n/a')}'")
                claims.append(
                    Claim(
                        section="confidence",
                        text="; ".join(parts),
                        ref=f"turn:{turn_id}:decision.calibration",
                        asserted={"calibration": dict(calibration)},
                        actual={"calibration": dict(calibration)},
                    )
                )

        # --- actions: what ran in the world, and what the gate allowed (§7) --
        if turn_id:
            for index, event in enumerate(self._events_of(turn_id, "outcome")):
                payload = event.payload
                if "goal" not in payload and "skill_id" not in payload:
                    continue  # a reply outcome, already covered above
                outcome = str(payload.get("outcome", ""))
                if payload.get("skill_id"):
                    text = (f"ran '{payload.get('goal', '')}' using learned skill {payload['skill_id']} "
                            f"→ {outcome}")
                    if payload.get("repairs"):
                        text += f" (after {payload['repairs']} repair(s))"
                else:
                    text = (f"no skill matched '{payload.get('goal', '')}' — the body was not touched "
                            "(recorded as an open question)")
                asserted = {k: payload.get(k) for k in ("goal", "skill_id", "outcome") if k in payload}
                claims.append(
                    Claim(
                        section="evidence",
                        text=text,
                        ref=f"turn:{turn_id}:outcome[{index}]",
                        asserted=asserted,
                        actual=asserted,
                    )
                )
                skill = self.memory.find(str(payload["skill_id"])) if payload.get("skill_id") else None
                if skill is not None:
                    title = str(skill.content.get("title", skill.id))
                    goal_class = skill.content.get("goal_class", "unclassified")
                    learned_via = skill.content.get("learned_via", "unknown")
                    claims.append(
                        Claim(
                            section="evidence",
                            text=f"the learned skill '{title}' ({goal_class}, learned via {learned_via})",
                            ref=f"record:{skill.id}",
                            asserted={"content": dict(skill.content)},
                            actual={"content": dict(skill.content)},
                        )
                    )
            for index, event in enumerate(self._events_of(turn_id, "authority")):
                payload = event.payload
                if "blocked" in payload:
                    text = f"the authority gate refused '{payload['blocked']}' — you ruled it out"
                elif "permission_request" in payload:
                    text = (f"the authority gate stopped me: '{payload['permission_request']}' needs your "
                            f"permission (asked {payload.get('count', 1)}x)")
                elif "capability" in payload and "action" in payload:
                    text = f"authority rule applied: {payload['capability']} → {payload['action']}"
                elif "requests_answered" in payload:
                    text = (f"a standing rule ('{payload.get('action', 'allow')}') resolved {len(payload['requests_answered'])} "
                            "earlier permission request(s)")
                elif "surfaced_request" in payload:
                    text = (f"I also asked for permission for '{payload['surfaced_request']}' "
                            f"(request #{payload.get('count', 1)})")
                else:
                    continue
                asserted = {k: payload.get(k) for k in ("blocked", "permission_request", "count",
                                                        "capability", "action", "requests_answered",
                                                        "surfaced_request") if k in payload}
                claims.append(
                    Claim(
                        section="evidence",
                        text=text,
                        ref=f"turn:{turn_id}:authority[{index}]",
                        asserted=asserted,
                        actual=asserted,
                    )
                )

        # --- residual uncertainty -------------------------------------------
        residual = ""
        if decision is not None:
            residual = str(decision.payload.get("residual", "") or "")
        if residual:
            claims.append(
                Claim(
                    section="residual",
                    text=residual,
                    ref=f"turn:{turn_id}:decision.residual",
                    asserted={"residual": residual},
                    actual={"residual": residual},
                )
            )
        elif entry is not None:
            label = entry.content.get("label", "n/a")
            residual = f"answer carries label '{label}' at confidence {entry.confidence:g}"
            claims.append(
                Claim(
                    section="residual",
                    text=residual,
                    ref=f"record:{entry.id}",
                    asserted={"label": label, "confidence": entry.confidence},
                    actual={"label": label, "confidence": entry.confidence},
                )
            )
        else:
            residual = "no separate uncertainty assessment was recorded for this turn"
            claims.append(
                Claim(
                    section="residual",
                    text=residual,
                    ref=f"turn:{turn_id}:decision" if decision else "record:none",
                    asserted={},
                    actual={},
                )
            )

        # --- the plain-language conclusion (cites the record, never raw CoT) -
        if entry is not None:
            reply = reply_snippet(entry.content.get("reply", ""))
            summary = (
                f"I answered: '{reply}'. This record ({entry.id}) was created at "
                f"{entry.created_at} from a {entry.source.value}."
            )
            claims.insert(
                0,
                Claim(
                    section="summary",
                    text=summary,
                    ref=f"record:{entry.id}",
                    asserted={
                        "reply": reply,
                        "created_at": entry.created_at,
                        "source": entry.source.value,
                    },
                    actual={
                        "reply": reply,
                        "created_at": entry.created_at,
                        "source": entry.source.value,
                    },
                ),
            )
        elif decision is not None:
            reply = reply_snippet(decision.payload.get("reply", ""))
            summary = f"Turn {turn_id} decided: '{reply}' — no episode record was linked to it."
            claims.insert(
                0,
                Claim(
                    section="summary",
                    text=summary,
                    ref=f"turn:{turn_id}:decision.reply",
                    asserted={"reply": reply},
                    actual={"reply": reply},
                ),
            )
        else:
            summary = f"Turn {turn_id} has no linked record."

        return Explanation(
            turn_id=turn_id,
            record_id=record_id,
            summary=summary,
            claims=claims,
            evidence=[c.text for c in claims if c.section == "evidence"],
            alternatives=[c.text for c in claims if c.section == "alternative"],
            residual_uncertainty=residual,
        )
