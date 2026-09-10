"""The cognitive loop — the integrated mind (ARCHITECTURE §4).

Traceability: ARCHITECTURE §4.1 (trigger → perceive → understand → reason →
decide → act → experience → reflect → mind changed), §4.2 (triggers; no idle
loop), §4.4 (correction handler), §4.5 (explanation service), §4.6 (effort
allocation), §5 (authority), §7 (body), and the Stage-0 exit criteria the
original skeleton proved (persistence, restart continuity, failure tags).

Every module-level behavior has its own module (belief, learning, planning,
intention, reflection, explain, cognition, attention); this file wires them
into one loop with one public face — Mind.step() for owner input, Mind.tick()
for scheduled background cognition, Mind.observe() for perception events, and
Mind.demonstrate()/Mind.perform_goal() for teach-then-act (T1).

Honesty boundary (VISION §4): plain conversation never silently triggers body
actions; acting requires either an explicit demonstrated/confirmed skill via
perform_goal, an allow rule, or a permission answer — the four states of §5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .attention import NoveltyDetector
from .belief import ContradictionEngine, DecayMonitor
from .body import AuthorityGate, BodyError, SandboxBody, parse_authority_statement
from .calibration import Calibrator
from .cognition import Curiosity, Devil, stakes_of
from .explain import ExplanationService

from .intention import IntentionKeeper, parse as parse_intention
from .learning import DemonstrationLearner, DemoAction, SkillProposal
from .planning import Incubator, PlanExecutor, PlanResult, Planner
from .policy import EffortPolicy
from .preferences import PreferenceMiner
from .records import Entry, EvidenceRef, RecordKind, Source, confidence_label, utcnow_iso
from .reflection import ConsolidationAdapter, NoopConsolidationAdapter, Reflector, StubReflector
from .state import MindState
from .stores import Memory
from .substrate import Outcome, StubSubstrate, Substrate
from .simulate import Simulator, parse_what_if
from .trace import FailureTaxonomy, Trace

#: owner statements that start a preference (VISION T4)
_PREF_RE = re.compile(
    r"^\s*(?:i\s+prefer\b|i\s+like\b|when\s+(?:i'?m\s+|i\s+am\s+|i\s+)?(?:uncertain|unsure|in\s+doubt|not\s+sure)\b)",
    re.IGNORECASE,
)
#: introspection — the self-model answers about itself (row 35)
_INTROSPECT_RE = re.compile(
    r"^\s*(?:what\s+are\s+you\s+(?:unsure|uncertain|confused|wondering)\s+about\s*\??|"
    r"what\s+(?:have|did)\s+you\s+learn(?:ed)?\s*(?:recently|so\s+far|today)?\s*\??|"
    r"what\s+can\s+you\s+do\s*\??|"
    r"(?:tell\s+me\s+about\s+yourself|what\s+do\s+you\s+know\s+about\s+yourself)\s*\??)\s*$",
    re.IGNORECASE,
)
#: owner belief statements → owner-model belief layer (§3.5, row 33)
_BELIEF_RE = re.compile(
    r"^\s*(?:i\s+|my\s+)?(?:think|thought|believe|believed|assume|assumed|suspect|suspected)\s+(?:that\s+)?(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
#: owner statements that start a correction (ARCHITECTURE §4.4)
_CORRECTION_RE = re.compile(
    r"^\s*(?:no|nope|wait|stop|wrong|not that|that'?s not right|that'?s wrong|that is wrong|that is not right)"
    r"(?:[,\-:]\s*|\s+)(.*)$",
    re.IGNORECASE,
)
#: explicit usefulness feedback about the previous answer (§8/T13): the owner
#: says a cheap answer was or wasn't useful, and the effort policy hears it
_RATING_OPENER_RE = re.compile(
    r"^\s*(?:that|this|it|thanks|thank you|well done|good job|nice work|"
    r"perfect|great|excellent|useful|helpful|useless|unhelpful)\b",
    re.IGNORECASE,
)
_RATING_END_RE = re.compile(
    r"(?:useful|helpful|great|perfect|excellent|correct|right|helped|"
    r"thanks|done|job|work|useless|unhelpful|wrong)\W*$",
    re.IGNORECASE,
)
_RATING_POSITIVE = ("useful", "helpful", "great", "perfect", "excellent",
                    "good job", "well done", "nice work", "correct", "right",
                    "helped", "thanks", "thank you")
_RATING_NEGATIVE = ("useless", "unhelpful", "not useful", "not helpful",
                    "wasn't useful", "wasn't helpful", "isn't useful", "isn't helpful",
                    "wrong", "not right", "didn't help", "did not help")


_SIGNAL_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "it", "is", "was",
    "be", "for", "with", "that", "this", "you", "i", "me", "my", "your", "please",
    "do", "did", "does", "can", "could", "would", "should", "now", "then", "about",
    "here", "there", "what", "why", "how", "when", "so", "if", "not", "no", "yes",
})


def _signal_tokens(text: str) -> set[str]:
    """Content words used to judge whether a turn follows up on the last one."""
    return {w for w in re.findall(r"[a-z0-9_\.]+", text.lower()) if w not in _SIGNAL_STOPWORDS and len(w) > 2}


def parse_usefulness_rating(text: str) -> Optional[int]:
    """Return 1–5 for an explicit usefulness remark about the last answer, else None.

    Deliberately conservative: short, sentiment-final messages only, so ordinary
    conversation ("great, now move the files") never registers as feedback.
    """
    lowered = text.lower().strip()
    if not lowered or len(lowered.split()) > 8:
        return None
    if not _RATING_OPENER_RE.match(lowered) or not _RATING_END_RE.search(lowered):
        return None
    if any(phrase in lowered for phrase in _RATING_NEGATIVE):
        return 1
    if any(phrase in lowered for phrase in _RATING_POSITIVE):
        return 5
    return None


#: owner statements that command memory ("remember that X is Y")
_REMEMBER_RE = re.compile(r"^\s*(?:remember|note|keep in mind)(?:\s+that)?\s*:?\s*(.+)$", re.IGNORECASE)
_FACT_RE = re.compile(
    r"^(.+?)\s+(is|are|was|were|has|have|uses|runs? on|prefers|likes|belongs? to|located at|costs?)"
    r"\s+(?:in|at|on|under|near|with)?\s*(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_EXPLAIN_RE = re.compile(r"^\s*(?:explain|why did you|why do you think|walk me through)\b", re.IGNORECASE)
#: "where is X?" → world-model location lookup (Domain A object permanence)
_WHERE_RE = re.compile(r"^\s*where(?:'s|\s+is|\s+are)\s+(.+?)\s*\??\s*$", re.IGNORECASE)
#: "how do you organize …?" → teaching the owner the learned rule (row 34)
_HOW_RE = re.compile(r"^\s*how\s+do\s+you\s+(?:organize|sort|handle|do)\s+(?:it|this|that)?\s*(.*?)\s*\??\s*$", re.IGNORECASE)
_CANCEL_REMARK_RE = re.compile(r"^\s*(?:cancel|forget|never mind)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Reply:
    """A turn's public response: text + communicated confidence (T8) + extras."""

    text: str
    confidence: float
    confidence_label: str
    turn_id: str
    success: bool
    failure: Optional[FailureTaxonomy] = None
    record_id: Optional[str] = None
    reminders: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "turn_id": self.turn_id,
            "success": self.success,
            "failure": self.failure.value if self.failure else None,
            "record_id": self.record_id,
            "reminders": list(self.reminders),
            "questions": list(self.questions),
        }


class Mind:
    """One continuous mind: loop, stores, behaviors, body, persistence."""

    def __init__(
        self,
        substrate: Optional[Substrate] = None,
        state_dir: str | Path = ".beanie_state",
        authority: str = "ask",  # ask | allow | deny (allow is demo/test policy)
        reflect_every: int = 25,
        consolidation_adapter: Optional[ConsolidationAdapter] = None,
    ) -> None:
        if substrate is None:
            substrate = StubSubstrate()
        self.substrate = substrate
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.state = MindState.from_dir(self.state_dir)
        self.memory = Memory(self.state_dir)
        self.trace = Trace(self.state_dir / "trace.jsonl")
        self.episodes = self.memory.episodes  # Stage-0 compatible handle

        # behaviors & stores are assembled here; every component is swappable
        self.engine = ContradictionEngine()
        self.decay = DecayMonitor()
        self.calibrator = Calibrator(self.memory, self.trace)
        self.devil = Devil(self.memory)
        self.curiosity = Curiosity(self.memory)
        self.learner = DemonstrationLearner(self.memory)
        self.preferences = PreferenceMiner(self.memory)
        self.planner = Planner(self.memory, self.learner)
        self.intentions = IntentionKeeper(self.memory)
        self.explainer = ExplanationService(self.memory, self.trace)
        self.incubator = Incubator(self.memory)
        self.reflector: Reflector = StubReflector(self.memory)
        self.adapter = consolidation_adapter or NoopConsolidationAdapter()

        self.body = SandboxBody(self.state_dir / "sandbox")
        self.gate = AuthorityGate(self.memory, default=authority)
        self.executor = PlanExecutor(self.body, self.gate, self.learner, self.memory)
        self.simulator = Simulator(self.body)
        self.attention = NoveltyDetector(self.state_dir / "sandbox")
        self.policy = EffortPolicy(self.memory)
        self.last_observed_reminders: list[str] = []

        self.reflect_every = reflect_every
        self._last_turn_record: Optional[str] = None
        self._current_turn_id: str = ""
        self._previous_turn_id: str = ""
        self._previous_user_text: str = ""

    # ======================================================================
    # Owner input
    # ======================================================================

    def step(self, user_text: str) -> Reply:
        """One cognitive-loop turn for one owner utterance (§4.1)."""
        turn_id = self._new_turn_id()
        text = user_text.strip()
        self._previous_turn_id = self._current_turn_id
        self._current_turn_id = turn_id
        self._record_implicit_usefulness(turn_id, text)
        self._previous_user_text = text  # for the next turn's signal judgement

        # 1) prospective memory: set or cancel an intention (§3.7)
        if _CANCEL_REMARK_RE.match(text):
            cancelled = self.intentions.cancel_matching(text)
            if cancelled is not None:
                return self._directive_reply(turn_id, "Reminder cancelled.", success=True)
        parsed_intention = parse_intention(text)
        if parsed_intention is not None:
            entry = self.intentions.add(parsed_intention, origin_turn=turn_id)
            self.trace.append(turn_id, "intention", {"intention_id": entry.id, "action": parsed_intention.action})
            return self._directive_reply(
                turn_id,
                f"Understood — I'll remind you to {parsed_intention.action}.",
                success=True,
                record_id=entry.id,
            )

        # 2) preference statements → owner model (T4)
        if _PREF_RE.match(text):
            return self._learn_preference(turn_id, text)

        # 3) authority statements → durable rules (§5)
        authority_rule = parse_authority_statement(text)
        if authority_rule is not None:
            capability, action = authority_rule
            rule = self.gate.grant(capability, action)
            self.trace.append(turn_id, "authority", {"capability": capability, "action": action, "rule_id": rule.id})
            phrase = {
                "allow": "I may do that now.",
                "deny": "I won't do that.",
                "ask": "I'll ask before doing that.",
            }[action]
            return self._directive_reply(turn_id, f"Understood. {phrase} ({capability} → {action})", success=True, record_id=rule.id)

        # 4) what-if questions → simulated prediction, body untouched (rows 10–11)
        what_if = parse_what_if(text)
        if what_if is not None:
            return self._what_if(turn_id, text, what_if)

        # 5) "where is X?" → world-model location lookup (row 11)
        where = _WHERE_RE.match(text)
        if where:
            handled = self._where_is(turn_id, text, where.group(1).strip())
            if handled is not None:
                return handled

        # 6) "how do you organize …?" → teach the owner the learned rule (row 34)
        how = _HOW_RE.match(text)
        if how:
            handled = self._teach_rule(turn_id, text, how.group(1).strip())
            if handled is not None:
                return handled

        # 7) introspection — the self-model answers about itself (row 35)
        if _INTROSPECT_RE.match(text):
            return self._introspect(turn_id, text)

        # 8) belief statements ("i think that X is Y") → owner belief layer (§3.5)
        if _BELIEF_RE.match(text):
            return self._note_belief(turn_id, text)

        # 9) commanded memory ("remember that …") → semantic store via §3.6
        remember = _REMEMBER_RE.match(text)
        if remember:
            return self._remember(turn_id, remember.group(1).strip())

        # 10) explanation on demand (§4.5 / T10)
        if _EXPLAIN_RE.match(text):
            return self._explain_last(turn_id, text)

        # 11) corrections — the continuous "no, that's wrong" channel (§4.4)
        correction = _CORRECTION_RE.match(text)
        if correction:
            return self._handle_correction(turn_id, text, correction.group(1).strip())

        # 12) explicit usefulness feedback about the last answer (§8/T13)
        rating = parse_usefulness_rating(text)
        if rating is not None:
            return self._rate_last(turn_id, text, rating)

        # 13) default cognition path (§4.1)
        return self._default_turn(turn_id, text)

    def _introspect(self, turn_id: str, text: str) -> Reply:
        """The self-model speaks: gaps, lessons, capabilities, identity.

        Every branch is answered from the stores — open questions (T5),
        distilled lessons (§4.3), body capabilities + active skills (§7), and
        the consolidated identity summary (T7 data path) — so introspection
        is a read over real state, never canned text (row 35).
        """
        lowered = text.lower()
        if "unsure" in lowered or "uncertain" in lowered or "confused" in lowered or "wondering" in lowered:
            open_questions = self.memory.query(kind="self", type="question", status="open")
            if not open_questions:
                reply_text = "I don't have unresolved questions right now — nothing I'm actively unsure about is on record."
            else:
                items = "\n".join(f"  - {q.content.get('text', q.content.get('subject', ''))}" for q in open_questions[:6])
                reply_text = f"Open questions I'm holding:\n{items}"
        elif "learn" in lowered:
            lessons = self.memory.query(kind="self", type="lesson")
            if not lessons:
                reply_text = "I haven't distilled any durable lessons yet."
            else:
                items = "\n".join(f"  - {l.content.get('text', '')}" for l in lessons[-6:])
                reply_text = f"What I've learned so far:\n{items}"
        elif "can you do" in lowered or "do you know" in lowered:
            capabilities = ", ".join(sorted(self.body.capabilities)) or "none"
            skill_lines = "\n".join(
                f"  - {s.content.get('goal_class', s.content.get('title', ''))} "
                f"(learned via {s.content.get('learned_via', '?')})"
                for s in self.learner.active_skills()
            )
            reply_text = f"Things I can do in my environment: {capabilities}."
            if skill_lines:
                reply_text += f"\nSkills I've learned:\n{skill_lines}"
        else:  # about yourself / identity
            summary = self.reflector.consolidate()
            outcomes = [e for e in self.trace.events if e.kind == "outcome"][-20:]
            calibration_line = ""
            if outcomes:
                accurate = sum(1 for e in outcomes if e.payload.get("success"))
                calibration_line = (
                    f" Recently my answers were right {accurate} of the last {len(outcomes)} "
                    f"times I answered — calibration like that is on record, not promised."
                )
            reply_text = (
                f"I am Beanie — a continuous mind, not an agent. So far I have lived "
                f"{summary['episodes_lived']} episodes, learned {summary['lessons_learned']} lesson(s), "
                f"received {summary['corrections_received']} correction(s), and hold "
                f"{len(self.learner.active_skills())} active skill(s)."
                f"{calibration_line} "
                f"My identity is written by this history, not by a script."
            )
        episode = self._record_episode(
            turn_id, reply_text, 0.95, True, None,
            extra={"user_text": text, "directive": "introspection", "reply": reply_text},
        )
        return Reply(text=reply_text, confidence=0.95, confidence_label=confidence_label(0.95),
                     turn_id=turn_id, success=True, record_id=episode.id)

    def export_knowledge(self) -> dict:
        """Serialize the mind's learnable knowledge for another instance (Q15).

        Active skills, stored facts, and active preferences travel as plain
        content bundles; episodes and raw history stay behind (each mind keeps
        its own identity — what transfers is *know-how*, not memories).
        """
        return {
            "format": 1,
            "skills": [dict(s.content) for s in self.learner.active_skills()],
            "facts": [
                dict(e.content)
                for e in self.memory.query(kind="semantic", type="fact")
                if e.content.get("predicate") != "located_at"
            ],
            "preferences": [
                dict(e.content)
                for e in self.memory.query(kind="owner_model", type="preference", status="active")
            ],
        }

    def import_knowledge(self, bundle: dict) -> dict:
        """Learn from another mind's exported know-how (Q15 cooperation)."""
        counts = {"skills": 0, "facts": 0, "preferences": 0}
        for skill_content in bundle.get("skills", []):
            entry = Entry(
                id=self.memory.allocate_id(),
                kind=RecordKind.PROCEDURAL,
                content={**skill_content, "status": "active", "learned_via": "transfer"},
                source=Source.INFERENCE,
                confidence=0.75,
            )
            self.memory.skills.append(entry)
            counts["skills"] += 1
        for fact_content in bundle.get("facts", []):
            entry = Entry(
                id=self.memory.allocate_id(),
                kind=RecordKind.SEMANTIC,
                content=dict(fact_content),
                source=Source.INFERENCE,
                confidence=0.75,
            )
            self.engine.ingest(self.memory, entry)
            self.memory.semantic.append(entry)
            counts["facts"] += 1
        for pref_content in bundle.get("preferences", []):
            entry = Entry(
                id=self.memory.allocate_id(),
                kind=RecordKind.OWNER_MODEL,
                content={**pref_content, "status": "active", "origin": "transfer"},
                source=Source.INFERENCE,
                confidence=0.7,
            )
            self.memory.owner_model.append(entry)
            counts["preferences"] += 1
        self.trace.append("transfer", "learning", {"imported": counts})
        return counts

    def _where_is(self, turn_id: str, text: str, target: str) -> Optional[Reply]:
        """Answer from the world model; verify when the record is doubtful.

        Object permanence (Domain A): objects the mind has seen or moved keep
        existing in its world model even when out of the current view — and a
        stale/doubtful record triggers a fresh look (proactive re-check, T12)
        instead of a confident lie. Returns None when the target is not a
        known thing (falls through to normal cognition).
        """
        name = target.strip().lower()
        facts = self.memory.query(kind="semantic", type="fact", subject=name, predicate="located_at")
        if not facts:
            # maybe it exists in the sandbox even though never recorded
            found = self._find_in_body(name)
            if found is None:
                return None
            self._record_location(name, found, Source.PERCEPTION, 0.6, "found during a where-is question")
            reply_text = f"{name} is at {found} (I found it in my environment)."
        else:
            fact = facts[-1]
            obj = str(fact.content.get("object", ""))
            if fact.confidence >= 0.8 and not fact.content.get("stale") and fact.effective_confidence() >= 0.6:
                reply_text = f"According to my records, {name} is at {obj}."
            else:
                found = self._find_in_body(name)
                if found is not None:
                    self._record_location(name, found, Source.PERCEPTION, 0.7, "re-checked: still present")
                    reply_text = f"I checked — {name} is at {found}."
                else:
                    self._forget_location(name, "not found during re-check")
                    reply_text = f"I last knew {name} as being at {obj}, but I couldn't find it on a fresh look — it may have moved or been removed."
        episode = self._record_episode(
            turn_id, reply_text, 0.9, True, None,
            extra={"user_text": text, "directive": "where_is", "target": name, "reply": reply_text},
        )
        self.trace.append(turn_id, "world", {"target": name, "reply": reply_text})
        return Reply(text=reply_text, confidence=0.9, confidence_label=confidence_label(0.9),
                     turn_id=turn_id, success=True, record_id=episode.id)

    def _find_in_body(self, name: str) -> Optional[str]:
        for path in self.body.root.rglob("*"):
            if path.is_file() and path.name.lower() == name:
                return str(path.relative_to(self.body.root))
        return None

    def _teach_rule(self, turn_id: str, text: str, rest: str) -> Optional[Reply]:
        """Teaching: explain the learned rule for the topic asked about (row 34)."""
        skills = self.learner.active_skills()
        if not skills:
            return None
        topic = rest.strip().lower()
        skill = None
        if topic:
            for candidate in reversed(skills):
                if topic in str(candidate.content.get("goal_class", "")).lower() or topic in str(candidate.content.get("title", "")).lower():
                    skill = candidate
                    break
            if skill is None:
                return None  # not about a skill we hold
        else:
            skill = skills[-1]
        mapping = dict(skill.content.get("mapping", {}))
        parts = [f"{'.' + ext if '.' not in ext else ext} files → {dst}" for ext, dst in mapping.items()]
        body = "; ".join(parts) if parts else "I don't have a fixed mapping yet"
        reply_text = (f"Here's how I {skill.content.get('goal_class', 'do it')}: {body}. "
                      f"I learned this from your demonstration and you confirmed it.")
        episode = self._record_episode(
            turn_id, reply_text, 0.9, True, None,
            extra={"user_text": text, "directive": "teach", "skill_id": skill.id, "reply": reply_text},
        )
        return Reply(text=reply_text, confidence=0.9, confidence_label=confidence_label(0.9),
                     turn_id=turn_id, success=True, record_id=episode.id)

    def _record_location(self, name: str, path_value: str, source: Source, confidence: float, reason: str) -> Entry:
        """Upsert the world fact '<name> is located at <path_value>' (row 11)."""
        name = name.lower()
        facts = self.memory.query(kind="semantic", type="fact", subject=name, predicate="located_at")
        if facts:
            entry = facts[-1]
            entry.content["object"] = path_value
            entry.content.pop("stale", None)
            entry.revise(reason, confidence=confidence)
            self.memory.semantic.save_all()
            return entry
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.SEMANTIC,
            content={"type": "fact", "subject": name, "predicate": "located_at", "object": path_value},
            source=source,
            confidence=confidence,
        )
        self.memory.semantic.append(entry)
        return entry

    def _forget_location(self, name: str, reason: str) -> None:
        """The object is gone from the world model (observed removal)."""
        name = name.lower()
        for entry in self.memory.query(kind="semantic", type="fact", subject=name, predicate="located_at"):
            entry.revise(reason, confidence=0.05, observe=False)
            entry.content["stale"] = True
        self.memory.semantic.save_all()

    def _what_if(self, turn_id: str, text: str, what_if: tuple[str, str]) -> Reply:
        """Answer a counterfactual about the body with a simulation (§7, row 10)."""
        file_name, dst = what_if
        prediction = self.simulator.predict_move(file_name, dst)
        # the counterfactual itself becomes a learning episode (why: outcome)
        episode = self._record_episode(
            turn_id, prediction.summary, 0.9, prediction.ok, None,
            extra={"user_text": text, "simulated": True, "file": file_name, "dst": dst,
                   "prediction": prediction.summary, "reply": prediction.summary},
        )
        self.trace.append(turn_id, "simulation", {"file": file_name, "dst": dst, "ok": prediction.ok,
                                                  "summary": prediction.summary})
        return Reply(text=prediction.summary, confidence=0.9, confidence_label=confidence_label(0.9),
                     turn_id=turn_id, success=prediction.ok, record_id=episode.id)

    def _note_belief(self, turn_id: str, text: str) -> Reply:
        """Record an owner belief separately from facts; surface conflicts (§3.5)."""
        statement = _BELIEF_RE.match(text).group(1).strip()
        fact = _FACT_RE.match(statement)
        subject = fact.group(1).strip().lower() if fact else statement.lower()[:60]
        obj = fact.group(3).strip() if fact else ""
        # if the owner's belief contradicts a fact on record, say so gently —
        # never overwrite the fact; ask whether it changed (T2 discipline)
        conflict_note = ""
        for entry in self.memory.query(kind="semantic", type="fact", subject=subject):
            if entry.content.get("predicate", "") != (fact.group(2).lower() if fact else "described_by"):
                continue
            if obj and entry.content.get("object") != obj:
                conflict_note = (f" My records currently say {subject} is {entry.content.get('object')} — "
                                 f"has that changed? I've kept my fact as-is.")
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.OWNER_MODEL,
            content={"type": "belief", "subject": subject, "predicate": fact.group(2).lower() if fact else "described_by",
                     "object": obj, "raw": statement, "status": "active"},
            source=Source.OWNER,
            confidence=0.7,
        )
        self.memory.owner_model.append(entry)
        reply_text = f"Noted as your belief: {statement}.{conflict_note}"
        episode = self._record_episode(
            turn_id, reply_text, 0.9, True, None,
            extra={"user_text": text, "belief_id": entry.id, "subject": subject, "reply": reply_text},
        )
        self.trace.append(turn_id, "belief", {"belief_id": entry.id, "subject": subject, "conflict": bool(conflict_note)})
        return Reply(text=reply_text, confidence=0.9, confidence_label=confidence_label(0.9),
                     turn_id=turn_id, success=True, record_id=episode.id)

    def _learn_preference(self, turn_id: str, text: str) -> Reply:
        """Learn an explicit preference statement (T4)."""
        entry = self.preferences.learn(text)
        if entry is None:
            # the statement started with a preference word but did not parse:
            # keep it as raw context rather than guessing a structure (§4 honesty)
            entry = self.preferences.learn(f"i prefer {text.lower()}")
        choice = str(entry.content.get("choice", ""))
        note = ""
        superseded = str(entry.content.get("superseded_choice", ""))
        if superseded:
            note = f" This replaces your earlier preference for {superseded}."
        for revision in reversed(entry.revision_history):
            if "confirmed by explicit" in revision.reason:
                note = f" I had noticed this from your corrections and will apply it."
                break
        reply_text = f"Understood — I'll remember that you prefer {choice}.{note}"
        episode = self._record_episode(
            turn_id, reply_text, entry.confidence, True, None,
            extra={"directive": "preference", "user_text": text, "preference_id": entry.id},
        )
        self.trace.append(turn_id, "memory", {"preference_id": entry.id, "choice": choice})
        return Reply(text=reply_text, confidence=entry.confidence, confidence_label=confidence_label(entry.confidence),
                     turn_id=turn_id, success=True, record_id=episode.id)

    def tick(self) -> dict[str, Any]:
        """Scheduled background cognition — no owner input needed (§4.2).

        Runs the deterministic maintenance loop on a budget: wall-clock
        reminders, stale-state decay sweep, incubation revisits, and the
        reflection pass when enough episodes have accumulated.
        """
        notes: dict[str, Any] = {
            "reminders": [], "stale": [], "incubation_revisits": [],
            "reflection": [], "preferences": [], "curiosity": [], "gists": [],
            "policy": "",
        }

        # usefulness → effort policy (T13): audit reflex-class outcomes
        policy_change = self.policy.adapt(self.trace.events)
        if policy_change:
            notes["policy"] = policy_change
            self.trace.append("bg", "policy", {"change": policy_change})

        # episodic compression (Domain B / R1.3): routine detail folds away
        gist_id = self.reflector.gist()
        if gist_id is not None:
            notes["gists"].append(gist_id)
            self.trace.append("bg", "gist", {"gist_id": gist_id})

        # T4 implicit discovery: repeated corrections may propose a preference
        for proposal in self.preferences.mine_implicit(self.episodes.all()):
            notes["preferences"].append(proposal.content.get("context", ""))
            self.trace.append(
                "bg", "preference",
                {"proposed": proposal.id, "context": proposal.content.get("context")},
            )

        for entry in self.intentions.due_wallclock():
            notes["reminders"].append(self.intentions.fire(entry))
            self.trace.append("bg", "intention", {"fired": entry.id, "action": entry.content.get("action")})

        notes["stale"] = [e.id for e in self.decay.sweep(self.memory)]
        if notes["stale"]:
            self.trace.append("bg", "decay", {"stale": notes["stale"]})

        for entry in self.incubator.due_for_revisit():
            self.incubator.revisit(entry, "revisited on background budget (new evidence present)")
            notes["incubation_revisits"].append(entry.id)

        # idle exploration (R3.24 / register row 21): budgeted self-directed
        # attention — surface the oldest unexplored open question and mark it,
        # so every idle budget does real cognitive work but never loops (§4.2)
        for question in self.memory.query(kind="self", type="question", status="open"):
            if not question.content.get("explored_at"):
                subject = str(question.content.get("subject", "?"))
                question.content["explored_at"] = utcnow_iso()
                question.revise("idle exploration pass", observe=False)
                self.memory.self_model.save_all()
                notes["curiosity"].append(subject)
                self.trace.append("bg", "curiosity", {"question_id": question.id, "subject": subject})
                break
        else:
            # no open questions left: idle cognition still senses the world —
            # inspect one environment directory not yet explored this session
            # (self-initiated perception content, not just bookkeeping)
            for directory in sorted((p for p in self.body.root.iterdir() if p.is_dir() and not p.name.startswith(".")),
                                    key=lambda p: p.name):
                if self.memory.query(kind="self", type="explored_dir", subject=directory.name.lower()):
                    continue
                try:
                    listing = self.body.run("list_files", {"dir": directory.name})
                except BodyError:
                    continue
                entry = Entry(
                    id=self.memory.allocate_id(),
                    kind=RecordKind.EPISODE,
                    content={"type": "observation", "event": {"kind": "inspect", "dir": directory.name,
                                                             "files": listing.get("files", [])},
                             "user_text": f"idle inspection of {directory.name}"},
                    source=Source.PERCEPTION,
                    confidence=0.6,
                )
                self.episodes.append(entry)
                mark = Entry(
                    id=self.memory.allocate_id(),
                    kind=RecordKind.SELF,
                    content={"type": "explored_dir", "subject": directory.name.lower()},
                    source=Source.SELF_REFLECTION,
                    confidence=1.0,
                )
                self.memory.self_model.append(mark)
                notes["curiosity"].append(f"inspected {directory.name}")
                self.trace.append("bg", "curiosity", {"inspected_dir": directory.name})
                break

        cursor = self._reflect_cursor()
        new_episodes = self.episodes.all()[cursor:]
        if len(new_episodes) >= self.reflect_every:
            notes["reflection"] = self.reflector.reflect(new_episodes)
            self._set_reflect_cursor(self.episodes.count())
            self.trace.append("bg", "reflection", {"notes": notes["reflection"][:3]})
            # Stage 5: consolidation input — the identity bundle, refreshed
            self.adapter.consolidate(self.reflector.consolidate())
        return notes

    def observe(self) -> list[dict[str, Any]]:
        """Perception over an observed stream: record what changed (§4.2)."""
        events = self.attention.diff()
        for event in events:
            entry = Entry(
                id=self.memory.allocate_id(),
                kind=RecordKind.EPISODE,
                content={"type": "observation", "event": event, "user_text": f"observed {event['kind']} {event['path']}"},
                source=Source.PERCEPTION,
                confidence=0.6,
            )
            self.episodes.append(entry)
            # world model: objects persist; track where they are (row 11)
            name = Path(event["path"]).name
            if event["kind"] == "add":
                self._record_location(name, event["path"], Source.PERCEPTION, 0.6,
                                      f"observed new file {event['path']}")
            elif event["kind"] == "remove":
                self._forget_location(name, f"observed {event['path']} disappear")
            self.trace.append("perception", "perception", {"event": event})
        # conditional intentions: "remind me when X appears" (Domain B/§3.7)
        self.last_observed_reminders = self.intentions.check_conditional(events)
        for reminder in self.last_observed_reminders:
            self.trace.append("perception", "intention", {"conditional_fired": reminder})
        return events

    # ======================================================================
    # Teaching & acting (T1) — the demonstration interaction model (§6)
    # ======================================================================

    def demonstrate(self, *, title: str, goal_class: str, actions: list[DemoAction]) -> SkillProposal:
        """Watch a demonstration and propose the general rule as a question."""
        proposal = self.learner.learn(title=title, goal_class=goal_class, actions=actions)
        self.trace.append(
            "demo",
            "learning",
            {"kind": "proposal", "skill_id": proposal.skill_id, "question": proposal.confirm_question},
        )
        return proposal

    def confirm_skill(self, skill_id: str) -> Entry:
        """Owner says yes — the proposed rule is ratified (§6 interaction)."""
        entry = self.learner.confirm(skill_id)
        # loop closure: an unknown-goal question is resolved by the new skill
        resolved = self.curiosity.resolve_open_questions(
            str(entry.content.get("goal_class", "")), entry.id, "a skill now covers this goal class"
        )
        if resolved:
            self.trace.append("demo", "learning", {"skill_id": skill_id, "resolved_questions": resolved})
        self._log_learning_episode(
            user_text=f"confirmed skill {entry.content.get('title', skill_id)}",
            content={"skill_confirmed": True, "rule": entry.content.get("mapping", {}), "skill_id": entry.id},
        )
        return entry

    def reject_skill(self, skill_id: str, reason: str = "owner rejected the proposed rule") -> None:
        self.learner.reject(skill_id, reason)

    def perform_goal(self, goal: str, base_dir: str | None = None) -> PlanResult:
        """Perform a goal in the body using learned skills (T1 end-to-end).

        The target directory is inferred from the goal itself when not given
        ("organize the library folder" → library) — the mind understands which
        part of its world the goal is about instead of requiring a parameter
        (ARCHITECTURE §7: needs first, parameters second).
        """
        if base_dir is None:
            base_dir = self._infer_target_dir(goal)
        plan, questions = self.planner.plan_for_goal(goal, base_dir=base_dir)
        if plan is None:
            # T5: an unknown goal class is a recorded gap, not a silent shrug
            self.curiosity.open_question(goal[:60], f"no skill found for goal: {goal}")
            self.trace.append("act", "plan", {"goal": goal, "questions": questions})
            return PlanResult(skill_id=None, steps=[], outcome="needs_information")
        result = self.executor.execute(plan)
        # world model update from own actions: moved files are now at their
        # new locations (object permanence — row 11, Domain A)
        for action in result.actions_done:
            if action["capability"] == "move_file":
                src = str(action["args"]["src"])
                dst = str(action["args"]["dst"])
                name = Path(src).name
                self._record_location(name, f"{dst.rstrip('/')}/{name}", Source.SELF_REFLECTION, 0.9,
                                      f"I moved {src} → {dst}")
        self.trace.append(
            "act",
            "outcome",
            {
                "goal": goal,
                "skill_id": result.skill_id,
                "outcome": result.outcome,
                "failure": result.failure_taxonomy,
                "repairs": result.repairs,
            },
            failure=FailureTaxonomy(result.failure_taxonomy) if result.failure_taxonomy and result.failure_taxonomy in FailureTaxonomy._value2member_map_ else None,
        )
        if result.outcome == "failed" or result.outcome == "needs_information":
            self._log_learning_episode(
                user_text=goal,
                content={"plan_failed": True, "goal": goal, "failure": result.failure_taxonomy, "outcome": result.outcome},
            )
        elif result.outcome == "success" and result.repairs == 0:
            self._log_learning_episode(user_text=goal, content={"plan_succeeded": True, "goal": goal})
        return result

    # ======================================================================
    # Feedback & explanation
    # ======================================================================

    def rate(self, turn_id: str, score: int, note: str = "") -> None:
        """Explicit usefulness rating for a past turn (T13)."""
        from .calibration import UsefulnessTracker

        UsefulnessTracker().rate(self.trace, turn_id, score, note)

    def _record_implicit_usefulness(self, turn_id: str, text: str) -> Optional[str]:
        """Record follow-up / abandonment as usefulness signals (§8 implicit side).

        Deterministic and conservative: a turn that shares content words with
        the previous owner turn is a *follow-up* (engagement); a turn that
        walks away from a previous turn left unresolved (open question or
        failed outcome) without touching its words is *abandonment* — the
        owner gave up on that thread. Pure statements with nothing unresolved
        about the previous turn record nothing.
        """
        if not self._previous_turn_id or not self._previous_user_text:
            return None
        previous_tokens = _signal_tokens(self._previous_user_text)
        overlap = previous_tokens & _signal_tokens(text)
        if overlap:
            signal = "follow_up"
        else:
            previous_failed = any(
                e.kind == "outcome" and e.turn_id == self._previous_turn_id
                and e.failure is not None and e.failure.value != "none"
                for e in self.trace.events
            )
            if not previous_failed:
                return None
            signal = "abandonment"
        self.trace.append(turn_id, "usefulness", {"signal": signal, "about_turn": self._previous_turn_id})
        return signal

    def _rate_last(self, turn_id: str, text: str, score: int) -> Reply:
        """Attach the owner's usefulness verdict to the answer it is about.

        The rating lands in the trace against the *previous* turn's id, so the
        per-label usefulness summary (T13) and the effort-policy audit both
        read it; the loop then answers normally (no rating is ever fabricated
        for a turn that did not happen).
        """
        target = self._previous_turn_id
        if not target:
            return self._directive_reply(
                turn_id, "I don't have an answer to rate yet — say it after a turn you're judging.",
                success=True,
            )
        self.rate(target, score, note=text)  # one feedback event per rating, against the judged turn
        judgement = "useful" if score >= 4 else "not useful"
        reply_text = f"Noted — I'll treat that answer as {judgement} (rated {score}/5)."
        return self._directive_reply(turn_id, reply_text, success=True)

    def explain(self, *, turn_id: str = "", record_id: str = "") -> Optional[str]:
        """User-facing explanation on demand (§4.5 / T10)."""
        explanation = None
        if record_id:
            explanation = self.explainer.explain_record(record_id)
        elif turn_id:
            explanation = self.explainer.explain_turn(turn_id)
        elif self._last_turn_record:
            explanation = self.explainer.explain_record(self._last_turn_record)
        return explanation.to_text() if explanation is not None else None

    # ======================================================================
    # Directive handlers
    # ======================================================================

    def _remember(self, turn_id: str, statement: str) -> Reply:
        fact = _FACT_RE.match(statement)
        if fact:
            subject, predicate, obj = fact.group(1).strip(), fact.group(2).lower(), fact.group(3).strip()
            content = {"type": "fact", "subject": subject.lower(), "predicate": predicate, "object": obj}
        else:
            subject = statement.lower()[:80]
            content = {"type": "fact", "subject": subject, "predicate": "described_by", "object": statement}
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.SEMANTIC,
            content=content,
            source=Source.OWNER,
            confidence=0.9,
        )
        report = self.engine.ingest(self.memory, entry)
        self.memory.semantic.append(entry)
        # loop closure: evidence arriving can resolve open questions (T5)
        resolved = self.curiosity.resolve_open_questions(subject, entry.id, "a fact is now on record")
        questions: tuple[str, ...] = ()
        text = "Remembered."
        if report.note:
            text = f"Remembered. {report.note}"
        if report.ask_owner:
            questions = ("I've updated my record to the newer statement — is that right?",)
        if resolved:
            self.trace.append(turn_id, "memory", {"entry_id": entry.id, "resolved_questions": resolved})
        self.trace.append(turn_id, "memory", {"entry_id": entry.id, "report": report.__dict__})
        episode = self._record_episode(
            turn_id, text, entry.confidence, True, None,
            extra={"directive": "remember", "user_text": statement, "memory_entry_id": entry.id},
        )
        return Reply(
            text=text, confidence=entry.confidence, confidence_label=confidence_label(entry.confidence),
            turn_id=turn_id, success=True, record_id=episode.id, questions=questions,
        )

    def _handle_correction(self, turn_id: str, full_text: str, remainder: str) -> Reply:
        """§4.4: classify, update, revise strategy, log learning episode."""
        # strategy revision first: mapping corrections adjust the skill (T9)
        revised = self.learner.apply_correction(remainder or full_text)
        if revised is not None:
            skill = self.memory.find(revised)
            mapping = dict(skill.content.get("mapping", {})) if skill else {}
            text = "Got it — I've corrected my rule" + (f": {', '.join(f'.{k} → {v}' for k, v in mapping.items())}" if mapping else ".")
            episode = self._record_episode(
                turn_id, text, 0.9, True, None,
                extra={"was_correction": True, "user_text": full_text, "strategy_revision": revised},
            )
            self.trace.append(turn_id, "correction", {"kind": "strategy_revision", "skill_id": revised})
            return Reply(text=text, confidence=0.9, confidence_label=confidence_label(0.9), turn_id=turn_id,
                         success=True, record_id=episode.id)
        # generic correction: demote the last claim; if the claim was a
        # remembered fact, propagate the invalidation (T11 contamination)
        if self._last_turn_record:
            last = self.memory.find(self._last_turn_record)
            if last is not None:
                last.revise(f"corrected by owner: {remainder or full_text}", confidence=last.confidence * 0.3)
                fact_id = last.content.get("memory_entry_id")
                if fact_id:
                    demoted = self.engine.contamination(
                        self.memory, fact_id, f"owner said the statement was wrong: {remainder or full_text}"
                    )
                    self.trace.append(turn_id, "correction", {"kind": "contamination", "source": fact_id, "demoted": demoted})
                self.episodes.save_all()
        text = "Understood — I was wrong. I've noted the correction and will handle this kind of case differently next time."
        episode = self._record_episode(
            turn_id, text, 0.9, True, None,
            extra={"was_correction": True, "user_text": full_text},
        )
        self.trace.append(turn_id, "correction", {"kind": "generic"})
        return Reply(text=text, confidence=0.9, confidence_label=confidence_label(0.9), turn_id=turn_id,
                     success=True, record_id=episode.id)

    def _explain_last(self, turn_id: str, text: str) -> Reply:
        explanation = self.explain()
        if explanation is None:
            reply_text = "I have no recent decision to explain yet."
            episode = self._record_episode(turn_id, reply_text, 0.9, True, None, extra={"user_text": text})
            return Reply(text=reply_text, confidence=0.9, confidence_label=confidence_label(0.9),
                         turn_id=turn_id, success=True, record_id=episode.id)
        episode = self._record_episode(turn_id, explanation, 0.9, True, None, extra={"user_text": text, "explanation_of": self._last_turn_record})
        return Reply(text=explanation, confidence=0.9, confidence_label=confidence_label(0.9),
                     turn_id=turn_id, success=True, record_id=episode.id)

    def _directive_reply(self, turn_id: str, text: str, *, success: bool, record_id: Optional[str] = None) -> Reply:
        episode = self._record_episode(turn_id, text, 0.95, success, None, extra={})
        return Reply(text=text, confidence=0.95, confidence_label="highly confident", turn_id=turn_id,
                     success=success, record_id=record_id or episode.id)

    # ======================================================================
    # Default cognition path
    # ======================================================================

    def _default_turn(self, turn_id: str, text: str) -> Reply:
        context = self.recall(text, limit=8)
        self.trace.append(turn_id, "perception", {"user_text": text[:200]})

        # effort allocation (§4.6): choose a processing depth first
        planned_depth = self._effort_depth(text)
        depth = planned_depth
        observation = {"user_text": text, "turn_id": turn_id}
        outcome: Optional[Outcome] = None
        candidate = ""
        escalated_from: Optional[str] = None

        if depth == "reflex":
            # trivial, low-stakes input → the fast tier answers alone; the
            # deep tier is never woken (§4.6: don't burn deep compute on 2+2)
            candidate = self.substrate.fast(observation, context)
            if candidate.startswith("fast: low-confidence"):
                depth = "deep"  # fast tier flagged; escalate (§2 contract)
                escalated_from = "reflex"  # recorded for the effort-policy audit (T13)
        if depth != "reflex":
            # dual-process: System-1 candidate, System-2 verdict (§2)
            candidate = self.substrate.fast(observation, context)
            outcome = self.substrate.deep(observation, context, candidate)
        else:
            outcome = Outcome(
                text=candidate,
                confidence=float(getattr(self.substrate, "FAST_CONFIDENCE", 0.9)),
                success=True,
                failure=FailureTaxonomy.NONE,
                fast_candidate=candidate,
                slow_candidate="",
                meta={"depth": "reflex"},
            )
        assert outcome is not None

        # T5: gaps noticed by the loop become open questions (no silent guesses)
        if outcome.failure in (FailureTaxonomy.MISSING_CONTEXT, FailureTaxonomy.PROMPT_AMBIGUITY):
            self.curiosity.open_question(text[:60], f"owner request left unresolved: {text[:160]}")

        # adversarial pre-flight only when the stakes justify it (§4.7 via §4.6)
        concerns: list[dict] = []
        stakes = stakes_of(text)
        if depth in ("deep", "deep_verified") and stakes and not outcome.failure and outcome.success:
            concerns = self.devil.check(text, outcome.confidence)

        # calibration (T8): evidence state adjusts the substrate's confidence
        confidence, reasons = self.calibrator.assess(text, outcome.confidence)
        if concerns:
            real_concerns = [c for c in concerns if c.get("kind") != "none"]
            if real_concerns:
                confidence = max(0.05, confidence - 0.1 * len(real_concerns))
            residual = "; ".join(c["detail"] for c in concerns[:2]) or "none"
            reasons["concerns"] = len(concerns)
        else:
            residual = ""
        label = confidence_label(confidence)

        # low-confidence "panic button" (Q13): a successful answer that the
        # evidence state does not back gets an honest caveat + a recorded gap
        reply_text = outcome.text
        failure_free = outcome.failure in (None, FailureTaxonomy.NONE)
        if outcome.success and failure_free and confidence < 0.55:
            reply_text = (
                f"{outcome.text} (I'm not fully confident about this — my records on "
                f"related subjects are uncertain or recently corrected. I can dig deeper if you want.)"
            )
            self.curiosity.open_question(text[:60], f"low confidence left unresolved: {text[:160]}")

        self.trace.append(
            turn_id, "decision",
            {"candidate": candidate, "reply": reply_text[:200], "label": label, "depth": depth,
             "escalated_from": escalated_from,
             "concerns": concerns, "residual": residual, "calibration": reasons},
        )

        episode = self._record_episode(turn_id, reply_text, confidence, outcome.success, outcome.failure,
                                       extra={"user_text": text, "candidate": candidate, "reply": reply_text,
                                              "label": label, "success": outcome.success})
        self.trace.append(
            turn_id, "outcome",
            {"record_id": episode.id, "success": outcome.success, "label": label},
            failure=outcome.failure,
        )

        # prospective memory: turn-count intentions advance after each turn (§3.7)
        reminders: list[str] = []
        for due in self.intentions.advance_turns():
            reminders.append(self.intentions.fire(due))
            self.trace.append(turn_id, "intention", {"fired": due.id, "action": due.content.get("action")})

        self._last_turn_record = episode.id
        self.state.save(self.state_dir / "mind_state.json")
        return Reply(
            text=reply_text,
            confidence=confidence,
            confidence_label=label,
            turn_id=turn_id,
            success=outcome.success,
            failure=outcome.failure,
            record_id=episode.id,
            reminders=tuple(reminders),
        )

    # ======================================================================
    # Records & helpers
    # ======================================================================

    def predict_goal(self, goal: str, base_dir: str | None = None) -> dict:
        """Simulate a goal before executing it; the body is never touched.

        Counterfactual replay over the current world state (row 10): the
        reply says what *would* happen — files that would move, folders that
        would be created first, or the failure that would occur.
        """
        if base_dir is None:
            base_dir = self._infer_target_dir(goal)
        plan, questions = self.planner.plan_for_goal(goal, base_dir=base_dir)
        if plan is None:
            return {"known": False, "questions": questions, "summary": "I don't yet know how to do that — teach me once and I'll learn it."}
        prediction = self.simulator.predict_goal(dict(plan.mapping), base_dir)
        self.trace.append("act", "simulation", {"goal": goal, "ok": prediction.ok, "summary": prediction.summary})
        return {"known": True, "ok": prediction.ok, "summary": prediction.summary,
                "moved": prediction.moved, "created_dirs": prediction.created_dirs,
                "failure": prediction.failure}

    def _infer_target_dir(self, goal: str) -> str:
        """Pick which existing folder a goal is about, from its own words."""
        tokens = set(re.findall(r"[a-z0-9]+", goal.lower()))
        # token that names an actual directory wins (longest match)
        if self.body.root.exists():
            for directory in sorted((p for p in self.body.root.iterdir() if p.is_dir()), key=lambda p: len(p.name), reverse=True):
                name = directory.name.lower()
                if name in tokens or any(name.startswith(t) or t.startswith(name) for t in tokens if len(t) >= 4):
                    return directory.name
        phrase = re.search(r"\b(?:in|into|inside|for)\s+(?:the\s+)?([A-Za-z0-9_./-]+?)(?:\s+folder)?\b", goal)
        if phrase:
            return phrase.group(1).strip("/")
        return "downloads"

    def _effort_depth(self, text: str) -> str:
        """Choose a processing depth by perceived stakes and size (§4.6).

        reflex          → trivial/low-stakes, fast tier only
        deep            → full dual-process turn
        deep_verified   → high stakes: deep tier + pre-flight check (§4.7)

        The reflex word budget comes from the adaptive effort policy, so
        usefulness feedback (T13) can widen or tighten what counts as
        "trivial" over time.
        """
        stakes = stakes_of(text)
        if stakes == 0 and len(text.split()) <= self.policy.word_limit:
            return "reflex"
        return "deep_verified" if stakes >= self.policy.verify_stakes else "deep"

    def _record_episode(
        self,
        turn_id: str,
        reply_text: str,
        confidence: float,
        success: bool,
        failure: Optional[FailureTaxonomy],
        *,
        extra: dict[str, Any],
    ) -> Entry:
        now = utcnow_iso()
        record_id = self.memory.allocate_id()
        prior = self.episodes.latest(1)
        refs = [EvidenceRef(record_id=prior[0].id, role="context")] if prior else []
        content = {
            "reply": reply_text,
            "success": success,
            "failure": failure.value if failure else None,
            **extra,
        }
        entry = Entry(
            id=record_id,
            kind=RecordKind.EPISODE,
            content=content,
            source=Source.OWNER if "user_text" in extra else Source.SELF_REFLECTION,
            confidence=confidence,
            created_at=now,
            updated_at=now,
            last_observed_at=now,
            evidence_refs=refs,
        )
        self.episodes.append(entry)
        self._last_turn_record = record_id
        return entry

    def _log_learning_episode(self, *, user_text: str, content: dict[str, Any]) -> Entry:
        return self._record_episode(
            "act", reply_text="", confidence=0.8, success=True, failure=None,
            extra={"user_text": user_text, **content},
        )

    def _new_turn_id(self) -> str:
        turn_id = f"turn-{self.state.next_turn:05d}"
        self.state.next_turn += 1
        return turn_id

    def _reflect_cursor(self) -> int:
        cursors = self.memory.query(kind="self", type="reflection_cursor")
        if cursors:
            return int(cursors[-1].content.get("index", 0))
        return 0

    def _set_reflect_cursor(self, index: int) -> None:
        cursors = self.memory.query(kind="self", type="reflection_cursor")
        if cursors:
            cursor = cursors[-1]
            cursor.content["index"] = index
            cursor.revise("reflection cursor advanced", confidence=1.0)
            self.memory.self_model.save_all()
            return
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.SELF,
            content={"type": "reflection_cursor", "index": index},
            source=Source.SELF_REFLECTION,
            confidence=1.0,
        )
        self.memory.self_model.append(entry)

    def recall(self, text: str | None = None, limit: int = 8) -> list[dict[str, str]]:
        """Memory retrieval: what is relevant now, not just what is recent.

        With `text`, related stored knowledge about the same subjects (facts,
        beliefs, preferences — the stores of §3.2/§3.5) and related episodes
        are surfaced first, then recent episodes fill the window (Domain B /
        register row 7: retrieval is triggered by what the situation is
        about). Without `text` this keeps the original recency behavior.

        The returned shape stays a list of role/text dicts so every consumer
        (substrate context, explanations) is unchanged.
        """
        if not text:
            return [
                {"role": "user", "text": e.content.get("user_text", "") or e.content.get("reply", ""), "record_id": e.id}
                for e in self.episodes.latest(limit)
            ]
        tokens = {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if not t.isdigit()}
        context: list[dict[str, str]] = []
        seen: set[str] = set()

        def push(record_id: str, entry_text: str) -> None:
            if record_id in seen:
                return
            seen.add(record_id)
            context.append({"role": "user", "text": entry_text, "record_id": record_id})

        # 1) stored knowledge about the same subjects (facts/beliefs/preferences)
        for entry in self.memory.subjects_matching(tokens):
            content = entry.content
            if content.get("type") not in ("fact", "belief", "preference"):
                continue
            if content.get("status") == "superseded":
                continue
            subject, predicate, obj = (str(content.get("subject", "")), str(content.get("predicate", "")),
                                       str(content.get("object", content.get("choice", ""))))
            push(entry.id, f"on record: {subject} {predicate} {obj}".strip())
        # 2) episodes about the same subjects
        for entry in self.episodes.all()[-60:]:
            words = {w for w in re.findall(r"[a-z0-9]{3,}", str(entry.content.get("user_text", "")).lower())}
            if tokens & words:
                push(entry.id, entry.content.get("user_text", "") or entry.content.get("reply", ""))
        # 3) recent episodes fill the window (recency still matters)
        for entry in self.episodes.latest(limit):
            push(entry.id, entry.content.get("user_text", "") or entry.content.get("reply", ""))
        return context[:limit]

    @classmethod
    def open(cls, state_dir: str | Path, substrate: Optional[Substrate] = None, **kwargs: Any) -> "Mind":
        """Continue the mind living in `state_dir` (restart continuity)."""
        return cls(substrate=substrate, state_dir=state_dir, **kwargs)
