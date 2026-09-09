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
from .body import AuthorityGate, SandboxBody, parse_authority_statement
from .calibration import Calibrator
from .cognition import Curiosity, Devil, stakes_of
from .explain import ExplanationService

#: reflex tier budget: at most this many words per trivial utterance (§4.6)
_REFLEX_MAX_WORDS = 6
from .intention import IntentionKeeper, parse as parse_intention
from .learning import DemonstrationLearner, DemoAction, SkillProposal
from .planning import Incubator, PlanExecutor, PlanResult, Planner
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
#: owner statements that command memory ("remember that X is Y")
_REMEMBER_RE = re.compile(r"^\s*(?:remember|note|keep in mind)(?:\s+that)?\s*:?\s*(.+)$", re.IGNORECASE)
_FACT_RE = re.compile(
    r"^(.+?)\s+(is|are|was|were|has|have|uses|runs? on|prefers|likes|belongs? to|located at|costs?)"
    r"\s+(?:in|at|on|under|near|with)?\s*(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_EXPLAIN_RE = re.compile(r"^\s*(?:explain|why did you|why do you think|walk me through)\b", re.IGNORECASE)
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

        self.reflect_every = reflect_every
        self._last_turn_record: Optional[str] = None

    # ======================================================================
    # Owner input
    # ======================================================================

    def step(self, user_text: str) -> Reply:
        """One cognitive-loop turn for one owner utterance (§4.1)."""
        turn_id = self._new_turn_id()
        text = user_text.strip()

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

        # 5) belief statements ("i think that X is Y") → owner belief layer (§3.5)
        if _BELIEF_RE.match(text):
            return self._note_belief(turn_id, text)

        # 6) commanded memory ("remember that …") → semantic store via §3.6
        remember = _REMEMBER_RE.match(text)
        if remember:
            return self._remember(turn_id, remember.group(1).strip())

        # 7) explanation on demand (§4.5 / T10)
        if _EXPLAIN_RE.match(text):
            return self._explain_last(turn_id, text)

        # 8) corrections — the continuous "no, that's wrong" channel (§4.4)
        correction = _CORRECTION_RE.match(text)
        if correction:
            return self._handle_correction(turn_id, text, correction.group(1).strip())

        # 9) default cognition path (§4.1)
        return self._default_turn(turn_id, text)

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
            "reflection": [], "preferences": [], "curiosity": [],
        }

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
            self.trace.append("perception", "perception", {"event": event})
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
            content = {"type": "fact", "subject": statement.lower()[:80], "predicate": "described_by", "object": statement}
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.SEMANTIC,
            content=content,
            source=Source.OWNER,
            confidence=0.9,
        )
        report = self.engine.ingest(self.memory, entry)
        self.memory.semantic.append(entry)
        questions: tuple[str, ...] = ()
        text = "Remembered."
        if report.note:
            text = f"Remembered. {report.note}"
        if report.ask_owner:
            questions = ("I've updated my record to the newer statement — is that right?",)
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
        depth = self._effort_depth(text)
        observation = {"user_text": text, "turn_id": turn_id}
        outcome: Optional[Outcome] = None
        candidate = ""

        if depth == "reflex":
            # trivial, low-stakes input → the fast tier answers alone; the
            # deep tier is never woken (§4.6: don't burn deep compute on 2+2)
            candidate = self.substrate.fast(observation, context)
            if candidate.startswith("fast: low-confidence"):
                depth = "deep"  # fast tier flagged; escalate (§2 contract)
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

        self.trace.append(
            turn_id, "decision",
            {"candidate": candidate, "reply": outcome.text[:200], "label": label, "depth": depth,
             "concerns": concerns, "residual": residual, "calibration": reasons},
        )

        episode = self._record_episode(turn_id, outcome.text, confidence, outcome.success, outcome.failure,
                                       extra={"user_text": text, "candidate": candidate, "reply": outcome.text,
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
            text=outcome.text,
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

    @staticmethod
    def _effort_depth(text: str) -> str:
        """Choose a processing depth by perceived stakes and size (§4.6).

        reflex          → trivial/low-stakes, fast tier only
        deep            → full dual-process turn
        deep_verified   → high stakes: deep tier + pre-flight check (§4.7)
        """
        stakes = stakes_of(text)
        if stakes == 0 and len(text.split()) <= _REFLEX_MAX_WORDS:
            return "reflex"
        return "deep_verified" if stakes >= 2 else "deep"

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
