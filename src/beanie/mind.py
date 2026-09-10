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

import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .affect import AffectObserver
from .analogy import CATEGORY_LABEL, demonstrated_categories
from .attention import NoveltyDetector
from .belief import ContradictionEngine, DecayMonitor
from .automation import Navigator, VirtualGUIDriver, default_driver
from .body import AuthorityGate, BodyError, OSBody, SandboxBody, parse_authority_statement
from .calibration import Calibrator
from .cognition import Curiosity, Devil, stakes_of
from .decision import DecisionGate, Need
from .explain import ExplanationService

from .intention import IntentionKeeper, parse as parse_intention
from .learning import DemonstrationLearner, DemoAction, SkillProposal
from .planning import Incubator, PlanExecutor, PlanResult, Planner
from .policy import EffortPolicy
from .preferences import PreferenceMiner
from .records import Entry, EvidenceRef, RecordKind, Source, confidence_label, utcnow_iso
from .reflection import ConsolidationAdapter, NoopConsolidationAdapter, Reflector, StubReflector
from .research import Researcher, web_search
from .searchindex import FileIndex
from .state import MindState
from .streaming import google_search_url, youtube_search_url, youtube_top_result
from .voice import Voice
from .stores import Memory
from .substrate import Outcome, StubSubstrate, Substrate
from .simulate import Simulator, parse_what_if
from .trace import FailureTaxonomy, Trace

#: owner statements that start a preference (VISION T4)
_PREF_RE = re.compile(
    r"^\s*(?:i\s+prefer\b|i\s+like\b|when\s+(?:i'?m\s+|i\s+am\s+|i\s+)?(?:uncertain|unsure|in\s+doubt|not\s+sure)\b)",
    re.IGNORECASE,
)
#: owner-tone read-back (row 33 proxy: the owner model, cited)
_AFFECT_QUERY_RE = re.compile(
    r"^\s*(?:"
    r"how\s+(?:do\s+you\s+think\s+)?(?:am\s+i|i\s+am|i'?m)\s+(?:feeling|doing|sounding|coming\s+across)|"
    r"what\s+(?:have\s+you\s+noticed\s+about|do\s+you\s+think\s+of)\s+(?:me|my\s+(?:tone|mood))"
    r")\s*\??\s*$",
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
# supervised GUI takeover: "log me in to github", "sign in to whatsapp", "automate this"
_GUI_TASK_RE = re.compile(
    r"^\s*(?:please\s+)?(log\s+me\s+in\s+to|log\s+in\s+to|sign\s+me\s+in\s+to|sign\s+in\s+to|"
    r"automate(?:\s+this)?|take\s+over\s+and\s+do|navigate\s+to\s+and)\s+(?P<goal>.{3,}?)"
    r"(?:\s+for\s+me)?\s*[.!?]*\s*$",
    re.IGNORECASE,
)

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

#: media follow-ups: walk the ranked trail from the last media ask (§11.2)
_MEDIA_FOLLOW_RE = re.compile(
    r"^\s*(?:no|nah|nope)?\s*[,!.]?\s*(?:"
    r"the\s+other\s+one|another\s+one|not\s+that\s+one|the\s+next\s+one|a\s+different\s+one|"
    r"try\s+(?:the\s+|another\s+)?(?:next|other)(?:\s+one)?|"
    r"next|another|different\s+one)\s*\.?\s*$",
    re.IGNORECASE,
)


_SIGNAL_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "it", "is", "was",
    "be", "for", "with", "that", "this", "you", "i", "me", "my", "your", "please",
    "do", "did", "does", "can", "could", "would", "should", "now", "then", "about",
    "here", "there", "what", "why", "how", "when", "so", "if", "not", "no", "yes",
})


def _ordinal(number: int) -> str:
    """2 → '2nd', 3 → '3rd' — small honest wording, not '2th'."""
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


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
        self.affect = AffectObserver(self.memory)
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

        # The decision gate (§11.1): every action-flavored request is classified
        # into a bounded need before any tool is touched. Ambiguous requests are
        # assisted by a real model tier only — the deterministic stub's canned
        # replies are not classifications, which keeps ambiguity honest.
        self.decision_gate = DecisionGate(
            self.substrate if self.substrate.name != "stub" else None
        )
        self.search_roots: Optional[list[Path]] = None
        self._fileindex: Optional[FileIndex] = None
        self._osbody: Optional[OSBody] = None
        self._osbody_probed = False
        self.youtube_fetcher = None  # injectable ResultsFetcher (tests never touch a network)
        self.web_fetcher = None      # injectable web ResultsFetcher (tests never touch a network)
        # the media trail (§11.2): last ranked matches + how far the owner has walked
        self._media_trail: Optional[tuple[list[Any], int]] = None
        self._media_trail_target = ""
        self._gui_driver_override: Any = None      # tests/demos inject scripted limbs
        self._gui_driver_cached: Any = None

        self.reflect_every = reflect_every
        self._last_turn_record: Optional[str] = None
        self._last_episode_turn = ""
        self._current_turn_id: str = ""
        self._previous_turn_id: str = ""
        self._previous_user_text: str = ""

    # ======================================================================
    # Owner input
    # ======================================================================

    def step(self, user_text: str) -> Reply:
        """One cognitive-loop turn for one owner utterance (§4.1).

        The turn first reads the owner's *tone* (§3.5 owner model; the register's
        behavioral proxy for the excluded "mood" capability) and, when the owner
        expresses frustration, the reply acknowledges it and offers to change
        tack — observation shaping behavior, never a claim of feeling.
        """
        turn_id = self._new_turn_id()
        text = user_text.strip()
        self._organ_hint = None  # each routing branch declares itself as it runs
        self._last_episode_turn = ""  # which turn last created an episode
        self._previous_turn_id = self._current_turn_id
        self._current_turn_id = turn_id
        self._record_implicit_usefulness(turn_id, text)
        self._previous_user_text = text  # for the next turn's signal judgement

        observation = self.affect.observe(turn_id, text)
        if observation is not None:
            self.trace.append(turn_id, "affect",
                              {"tone": observation.content["tone"], "markers": observation.content["markers"]})
        reply = self._dispatch(turn_id, text)
        if observation is not None and observation.content["tone"] == "frustration":
            return self._acknowledge_frustration(turn_id, reply)
        return reply

    def _dispatch(self, turn_id: str, text: str) -> Reply:
        """Route one utterance, then make sure every turn has a recorded reason.

        Directive turns are answered by deterministic organs, not by a model
        tier, so they used to record no decision event at all — and an answer
        with no recorded reason cannot be explained or audited (§4.5, §9.9).
        The wrapper records which organ actually produced the reply, inferred
        from the events the turn itself left behind (never invented).
        """
        reply = self._route(turn_id, text)
        events = self.trace.events_for(turn_id)
        if not any(event.kind == "decision" for event in events):
            self.trace.append(
                turn_id, "decision",
                {"candidate": "", "reply": reply.text[:200], "label": reply.confidence_label,
                 "depth": "deterministic", "escalated_from": None,
                 "handler": self._turn_organ(turn_id),
                 "concerns": [], "residual": "", "calibration": {}},
            )
        # a turn that created an episode links it here: an unlinked record
        # cannot be cited by the explanation service, and an answer whose
        # record is invisible is an answer that cannot be audited (§4.5, §9.9)
        if self._last_episode_turn == turn_id and not any(event.kind == "outcome" for event in events):
            self.trace.append(
                turn_id, "outcome",
                {"record_id": self._last_turn_record, "success": reply.success,
                 "label": reply.confidence_label},
                failure=None,
            )
        return reply

    # Which organ answered a deterministic turn. Each routing branch *declares*
    # it as it runs (never inferred after the fact), so the explanation names
    # the code path that actually produced the reply (§9.9). A forgotten
    # declaration degrades to an honest generic phrase, never to a wrong organ.
    _ORGAN_FALLBACK = "the direct reply handler — a rule in the conversation layer, not a model tier"

    def _turn_organ(self, turn_id: str) -> str:
        return self._organ_hint or self._ORGAN_FALLBACK

    def _route(self, turn_id: str, text: str) -> Reply:
        """Route one stripped utterance to its directive or to default cognition."""
        # 1) prospective memory: set or cancel an intention (§3.7)
        if _CANCEL_REMARK_RE.match(text):
            cancelled = self.intentions.cancel_matching(text)
            if cancelled is not None:
                self._organ_hint = "prospective memory (§3.7) — a pending reminder was cancelled"
                return self._directive_reply(turn_id, "Reminder cancelled.", success=True)
        parsed_intention = parse_intention(text)
        if parsed_intention is not None:
            self._organ_hint = "prospective memory (§3.7) — an intention was set for a later turn"
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
            self._organ_hint = "the preference store (§3.4) — a stated preference was learned"
            return self._learn_preference(turn_id, text)

        # 3) authority statements → durable rules (§5)
        authority_rule = parse_authority_statement(text)
        if authority_rule is not None:
            capability, action = authority_rule
            self._organ_hint = "the authority gate (§5) — a permission rule changed"
            rule = self.gate.grant(capability, action)
            resolved = self._resolve_permission_requests(turn_id, capability, action)
            self.trace.append(turn_id, "authority",
                              {"capability": capability, "action": action, "rule_id": rule.id,
                               "resolved_requests": resolved})
            phrase = {
                "allow": "I may do that now.",
                "deny": "I won't do that.",
                "ask": "I'll ask before doing that.",
            }[action]
            return self._directive_reply(turn_id, f"Understood. {phrase} ({capability} → {action})", success=True, record_id=rule.id)

        # 4) what-if questions → simulated prediction, body untouched (rows 10–11)
        what_if = parse_what_if(text)
        if what_if is not None:
            self._organ_hint = "the simulator (§3.3) — a prediction; nothing was executed"
            return self._what_if(turn_id, text, what_if)

        # 5) "where is X?" → world-model location lookup (row 11)
        where = _WHERE_RE.match(text)
        if where:
            handled = self._where_is(turn_id, text, where.group(1).strip())
            if handled is not None:
                self._organ_hint = "world state (§3.2) — a location fact was looked up"
                return handled

        # 6) "how do you organize …?" → teach the owner the learned rule (row 34)
        how = _HOW_RE.match(text)
        if how:
            handled = self._teach_rule(turn_id, text, how.group(1).strip())
            if handled is not None:
                self._organ_hint = "the planner's learned-skill store (§4.1) — the confirmed rule was explained"
                return handled

        # 7) owner-tone read-back → owner model, cited (row 33 proxy)
        if _AFFECT_QUERY_RE.match(text):
            self._organ_hint = "the affect read-back (§3.5) — an observation, not a claim of feeling"
            return self._read_back_owner_tone(turn_id, text)

        # 8) introspection — the self-model answers about itself (row 35)
        if _INTROSPECT_RE.match(text):
            self._organ_hint = "the self-model (§3.8) — an introspective report about my own state"
            return self._introspect(turn_id, text)

        # 9) belief statements ("i think that X is Y") → owner belief layer (§3.5)
        if _BELIEF_RE.match(text):
            self._organ_hint = "the belief layer (§3.5) — stored as your belief, apart from facts"
            return self._note_belief(turn_id, text)

        # 10) commanded memory ("remember that …") → semantic store via §3.6
        remember = _REMEMBER_RE.match(text)
        if remember:
            self._organ_hint = "the memory store (§3.1) — a fact was retained with its evidence"
            return self._remember(turn_id, remember.group(1).strip())

        # 11) explanation on demand (§4.5 / T10)
        if _EXPLAIN_RE.match(text):
            self._organ_hint = "the explanation service (§4.5) — this reply is itself an explanation"
            return self._explain_last(turn_id, text)

        # 11b) media follow-ups: "no, the other one" walks the trail (§11.2) —
        # it IS a correction, but one with a walkable answer: before the
        # general correction channel, and only while a trail exists to walk
        if _MEDIA_FOLLOW_RE.match(text) and self._media_trail is not None:
            self._organ_hint = "the media trail (§11.2) — the owner chose the next ranked match"
            return self._media_follow(turn_id)

        # 11b.5) supervised GUI takeover: a spoken imperative becomes the
        # navigator loop itself — eyes from the accessibility tree, one
        # action per authority check, budgeted, outcome narrated honestly
        gui_match = _GUI_TASK_RE.match(text)
        if gui_match:
            self._organ_hint = ("the supervised navigator (§11.3) — the request asked for a "
                                "GUI takeover; the limb drove, the authority gate supervised")
            return self._gui_takeover(turn_id, text, gui_match.group("goal").strip())

        # 12) corrections — the continuous "no, that's wrong" channel (§4.4)
        correction = _CORRECTION_RE.match(text)
        if correction:
            self._organ_hint = "the correction channel (§4.4) — records were revised, not overwritten"
            return self._handle_correction(turn_id, text, correction.group(1).strip())

        # 13) explicit usefulness feedback about the last answer (§8/T13)
        rating = parse_usefulness_rating(text)
        if rating is not None:
            self._organ_hint = "the usefulness tracker (§8) — your explicit rating was applied"
            return self._rate_last(turn_id, text, rating)

        # 14) the decision gate (§11.1) — action-flavored requests are classified
        # into bounded needs before any tool is touched; the reason travels with
        # the need (citable), and whatever cannot be classified falls through to
        # the default conversation path unchanged
        need_replied = self._route_need(turn_id, text)
        if need_replied is not None:
            return need_replied

        # 15) default cognition path (§4.1)
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
        lifted = demonstrated_categories(mapping)
        analogy_note = ""
        if lifted:
            kinds = " and ".join(sorted(CATEGORY_LABEL.get(c, c) for c in lifted))
            analogy_note = (f" I also apply the same idea to other {kinds} files you never showed me, "
                            f"because your demonstration placed that kind of thing there.")
        reply_text = (f"Here's how I {skill.content.get('goal_class', 'do it')}: {body}. "
                      f"I learned this from your demonstration and you confirmed it.{analogy_note}")
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
                note = " I had noticed this from your corrections and will apply it."
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
        # attention — take the oldest unexplored open question and *investigate*
        # it against the environment (search by its own words), so the idle
        # budget does real cognitive work but never loops (§4.2)
        for question in self.memory.query(kind="self", type="question", status="open"):
            if not question.content.get("explored_at"):
                found = self._investigate(question)
                notes["curiosity"].append(found["note"])
                self.trace.append("bg", "curiosity", {"question_id": question.id, **found["trace"]})
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
            gap = PlanResult(skill_id=None, steps=[], outcome="needs_information")
            self._record_action_decision(goal, gap)
            return gap
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
        if result.inferred:
            self.trace.append("act", "analogy", {"goal": goal, "inferred": result.inferred})
        if result.unmapped:
            # honesty (T5/T6): a kind the demonstration never covered is a gap,
            # not a licence to guess where the owner's files go
            kinds = ", ".join(sorted({f".{entry['extension']}" for entry in result.unmapped}))
            self.curiosity.open_question(
                goal[:60], f"I don't know where {kinds} files belong — demonstrate once and I'll learn it"
            )
            self.trace.append("act", "analogy", {"goal": goal, "unmapped": result.unmapped})
        if result.outcome == "needs_permission":
            question = self._note_permission_need(goal, result)
            if question:
                result.permission_question = question
        if result.outcome == "failed":
            # §4.8: a failed plan is incubated, not dropped — the tick budget
            # revisits it when evidence has moved (audit continuation note)
            self.incubator.park(goal[:80], {
                "failure": result.failure_taxonomy, "base_dir": base_dir,
                "parked_from": "perform_goal", "skill_id": result.skill_id,
            })
        if result.outcome == "failed" or result.outcome == "needs_information":
            self._log_learning_episode(
                user_text=goal,
                content={"plan_failed": True, "goal": goal, "failure": result.failure_taxonomy, "outcome": result.outcome},
            )
        elif result.outcome == "success" and result.repairs == 0:
            self._log_learning_episode(user_text=goal, content={"plan_succeeded": True, "goal": goal})
        self._record_action_decision(goal, result)
        return result

    def _record_action_decision(self, goal: str, result: "PlanResult") -> None:
        """Action turns record the same decision event owner turns do.

        A goal execution is a decision the mind made (§7) — which skill ran, and
        what the authority gate allowed — so it must be explainable and
        auditable like any other turn (T10, §9.9), not an untraceable side effect.
        """
        if result.skill_id:
            reply = f"executed skill {result.skill_id} for '{goal}' — {result.outcome}"
            handler = "the action layer (§7) — a learned skill executed in the sandbox"
        else:
            reply = f"no skill matched '{goal}' — nothing was executed"
            handler = "the action layer (§7) — no skill matched this goal, so the body was untouched"
        confidence = 0.9 if result.outcome in ("success", "needs_permission") else 0.4
        self.trace.append(
            "act", "decision",
            {"candidate": "", "reply": reply[:200], "label": confidence_label(confidence),
             "depth": "deterministic", "escalated_from": None, "handler": handler,
             "concerns": [], "residual": "", "calibration": {}},
        )

    # ======================================================================
    # Feedback & explanation
    # ======================================================================

    def rate(self, turn_id: str, score: int, note: str = "") -> None:
        """Explicit usefulness rating for a past turn (T13)."""
        from .calibration import UsefulnessTracker

        UsefulnessTracker().rate(self.trace, turn_id, score, note)

    def _resolve_permission_requests(self, turn_id: str, capability: str, action: str) -> list[str]:
        """An authority statement answers any standing request for it (§5)."""
        resolved: list[str] = []
        for entry in self.memory.query(kind="owner_model", type="permission_request", capability=capability):
            if entry.content.get("status") != "pending":
                continue
            entry.content["status"] = "answered"
            entry.content["answer"] = action
            entry.revise(f"owner answered: {capability} → {action}", confidence=0.95)
            resolved.append(entry.id)
        if resolved:
            self.memory.owner_model.save_all()
            self.trace.append(turn_id, "authority", {"requests_answered": resolved, "action": action})
        return resolved

    def _read_back_owner_tone(self, turn_id: str, text: str) -> Reply:
        """Answer 'how am I doing?' from recorded observations, never from guesses (row 33)."""
        reply_text = self.affect.summary()
        episode = self._record_episode(
            turn_id, reply_text, 0.9, True, None,
            extra={"user_text": text, "directive": "owner_model_readback", "reply": reply_text},
        )
        self.trace.append(turn_id, "affect", {"read_back": self.affect.current_tone()})
        return Reply(text=reply_text, confidence=0.9, confidence_label=confidence_label(0.9),
                     turn_id=turn_id, success=True, record_id=episode.id)

    def _acknowledge_frustration(self, turn_id: str, reply: Reply) -> Reply:
        """Attach a short, non-patronising acknowledgement to a frustrated turn (§3.5).

        The mind says what it noticed (the owner's own words), asks what to do
        differently, and otherwise leaves the answer intact. No diagnosis, no
        apology theatre — the observation is cited, and the owner decides.
        """
        streak = self.affect.frustration_streak()
        note = (" You sound frustrated — tell me what to change and I'll take a different "
                "approach.")
        if streak >= 2:
            note = (f" That's {streak} frustrated messages in a row — I'll stop guessing. "
                    f"Tell me the outcome you want and I'll work backwards from it.")
        self.trace.append(turn_id, "affect", {"acknowledged": True, "streak": streak})
        from dataclasses import replace as _replace  # dataclass with tuples: copy safely

        return _replace(
            reply,
            text=reply.text + note,
            questions=tuple(reply.questions) + ("Should I change how I'm approaching this?",),
        )

    def _note_permission_need(self, goal: str, result: PlanResult) -> str:
        """Turn a permission wall into an explicit, counted, non-nagging ask (§5).

        Row 29 (growing autonomy): when a plan stops because the mind does not
        know whether it is allowed, that is a question for the owner, not a
        silent failure. The need is recorded with a count so repeated walls
        become one standing request instead of repeated asks — and an explicit
        deny is respected: nothing is proposed again for that capability.
        """
        capability = str((result.last_result or {}).get("capability", "")) or "?"
        permission = self.gate.check(capability)
        if permission.state == "not_allowed":
            # the owner already decided; ask nothing, just log the wall
            self.trace.append("act", "authority",
                              {"blocked": capability, "goal": goal, "state": permission.state})
            return ""
        existing = [
            e for e in self.memory.query(kind="owner_model", type="permission_request", capability=capability)
            if e.content.get("status") == "pending"
        ]
        if existing:
            entry = existing[-1]
            entry.content["count"] = int(entry.content.get("count", 1)) + 1
            entry.content["last_goal"] = goal
            entry.revise(f"asked again about {capability} ({entry.content['count']}x)", confidence=0.8)
            self.memory.owner_model.save_all()
            count = entry.content["count"]
        else:
            entry = Entry(
                id=self.memory.allocate_id(),
                kind=RecordKind.OWNER_MODEL,
                content={"type": "permission_request", "capability": capability, "status": "pending",
                         "count": 1, "first_goal": goal, "last_goal": goal},
                source=Source.SELF_REFLECTION,
                confidence=0.8,
            )
            self.memory.owner_model.append(entry)
            count = 1
        self.trace.append("act", "authority",
                          {"permission_request": capability, "count": count, "goal": goal})
        if count == 1:
            return (f"To do this I'd need permission for {capability} — say 'you may {capability}' "
                    f"to allow it, or 'never use {capability}' to rule it out.")
        return (f"This is the {_ordinal(count)} time I've needed {capability}. If you like, a standing rule "
                f"('you may {capability}') would save you the trip — otherwise I'll keep asking.")

    def organ_status(self) -> dict[str, dict[str, Any]]:
        """Each organ's state and the exact switch that seats it (§11, row 35) —
        the honest onboarding answer to "what can you actually do right now?"."""
        voice = Voice()
        gui_on = os.environ.get("BEANIE_AUTOMATION") == "1"
        try:
            import pyautogui  # noqa: F401

            gui_lib = True
        except ImportError:
            gui_lib = False
        adb_ready = bool(os.environ.get("BEANIE_ANDROID") == "1" and shutil.which("adb"))
        return {
            "model_tier": {
                "on": self.substrate.name != "stub",
                "detail": self.substrate.name,
                "switch": "export BEANIE_MODEL_URL=http://localhost:1234/v1   (LM Studio's server)",
            },
            "os_body": {
                "on": self._os_body() is not None,
                "detail": "real machine actions (open/play/install/shell/docker, dry-run previews)",
                "switch": "export BEANIE_BODY_OS=1",
            },
            "gui_control": {
                "on": gui_on and gui_lib,
                "detail": "screen eyes+hands navigation loop" if gui_on else "screens stay read-only",
                "switch": "export BEANIE_AUTOMATION=1 && .venv/bin/pip install pyautogui",
            },
            "android": {
                "on": adb_ready,
                "detail": "phone as a limb over adb",
                "switch": "export BEANIE_ANDROID=1 (and install platform-tools + enable USB debugging)",
            },
            "voice_speaker": {
                "on": os.environ.get("BEANIE_VOICE") == "1" and voice.speaker() is not None,
                "detail": f"platform engine: {voice.speaker() or 'none found'}",
                "switch": "export BEANIE_VOICE=1",
            },
            "voice_ears": {
                "on": voice.transcription_engine() is not None,
                "detail": voice.transcription_engine() or "no engine — browser speech recognition in the WebUI covers this",
                "switch": ".venv/bin/pip install faster-whisper",
            },
        }

    def pending_permission_requests(self) -> list[dict[str, Any]]:
        """Standing permission questions the owner has not answered yet (§5)."""
        return [
            {"capability": e.content.get("capability"), "count": e.content.get("count"),
             "request_id": e.id}
            for e in self.memory.query(kind="owner_model", type="permission_request", status="pending")
        ]

    def _surface_permission_request(self, turn_id: str) -> str:
        """Ask an unanswered standing request once, on the next ordinary turn (§5)."""
        for entry in self.memory.query(kind="owner_model", type="permission_request", status="pending"):
            if entry.content.get("surfaced_at"):
                continue
            entry.content["surfaced_at"] = utcnow_iso()
            entry.revise("standing request surfaced to the owner", observe=False)
            self.memory.owner_model.save_all()
            capability = str(entry.content.get("capability", "?"))
            count = int(entry.content.get("count", 1))
            self.trace.append(turn_id, "authority", {"surfaced_request": capability, "count": count})
            if count == 1:
                return (f"I still need permission for {capability} — 'you may {capability}' allows it, "
                        f"'never use {capability}' rules it out.")
            return (f"I've needed {capability} {_ordinal(count)} times now; a standing rule would help — "
                    f"'you may {capability}' or 'never use {capability}'.")
        return ""

    def _surface_idle_finding(self, turn_id: str) -> str:
        """Bring an idle investigation's finding to the owner once (row 20/21).

        Active sensing is not supposed to end in a private note: when the idle
        budget found candidate evidence for an open question, the next ordinary
        turn says so and asks whether it is the right thing — the owner still
        decides (the gap stays open until real evidence arrives, T5).
        """
        for question in self.memory.query(kind="self", type="question", status="open"):
            investigation = question.content.get("investigation") or {}
            matches = investigation.get("matches") or []
            if not matches or investigation.get("surfaced_at"):
                continue
            investigation["surfaced_at"] = utcnow_iso()
            question.revise("finding surfaced to the owner", observe=False)
            self.memory.self_model.save_all()
            subject = str(question.content.get("subject", ""))[:60]
            paths = ", ".join(str(m.get("path", "")) for m in matches[:2])
            self.trace.append(turn_id, "curiosity", {"surfaced_finding": paths, "question_id": question.id})
            return f"While idle I looked into '{subject}' and found {paths} — is that what you meant?"
        return ""

    def _investigate(self, question: Entry) -> dict[str, Any]:
        """Idle curiosity with content (row 21): search the environment for evidence.

        The question's own words pick the search terms; the sandbox is searched
        by filename and content; findings are recorded as a perception episode
        and attached to the question. A keyword match never silently closes the
        gap — the question stays open with what was found, and only real
        evidence (a stored fact, owner confirmation) resolves it through the
        normal paths (T5 honesty, §4.2).
        """
        subject = str(question.content.get("subject", "")) or "?"
        terms = _signal_tokens(f"{subject} {question.content.get('text', '')}")
        matches: list[dict[str, Any]] = []
        searched = 0
        if self.body.root.exists():
            for path in sorted(p for p in self.body.root.rglob("*") if p.is_file()):
                searched += 1
                relative = str(path.relative_to(self.body.root))
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")[:4000]
                except OSError:
                    content = ""
                overlap = (_signal_tokens(path.name) | _signal_tokens(content)) & terms
                if overlap:
                    matches.append({"path": relative, "matched_terms": sorted(overlap)[:4]})
        investigation = {
            "at": utcnow_iso(),
            "terms": sorted(terms)[:8],
            "files_searched": searched,
            "matches": matches[:5],
        }
        if searched or matches:  # record the search itself as lived experience
            episode = Entry(
                id=self.memory.allocate_id(),
                kind=RecordKind.EPISODE,
                content={"type": "observation",
                         "event": {"kind": "investigation", "question_id": question.id, **investigation},
                         "user_text": f"idle investigation of {subject[:60]}"},
                source=Source.PERCEPTION,
                confidence=0.6,
            )
            self.episodes.append(episode)
            investigation["episode_id"] = episode.id
        question.content["explored_at"] = utcnow_iso()
        question.content["investigation"] = investigation
        if matches:
            note = (f"{subject[:60]} (searched {searched} file(s); "
                    f"candidate evidence: {', '.join(m['path'] for m in matches[:3])})")
        else:
            note = f"{subject[:60]} (searched {searched} file(s); no evidence in the sandbox)"
        question.revise("idle investigation pass", observe=False)
        self.memory.self_model.save_all()
        return {
            "note": note,
            "trace": {"searched": searched, "matches": [m["path"] for m in matches[:5]],
                      "terms": investigation["terms"]},
        }

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
            # a fresh process has no in-memory previous turn: fall back to the
            # last answered turn in the persisted trace, so the owner can rate
            # yesterday's answer after restarting the mind
            for event in reversed(self.trace.events):
                if event.kind == "outcome":
                    target = event.turn_id
                    break
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

    def _gui_driver(self) -> Any:
        if self._gui_driver_override is not None:
            return self._gui_driver_override
        if self._gui_driver_cached is None:
            self._gui_driver_cached = default_driver()
        return self._gui_driver_cached

    def _gui_takeover(self, turn_id: str, text: str, goal: str) -> Reply:
        """'log me in to github' → the supervised navigator, right now (§11.3).

        The sentence IS the task intake: eyes from the driver's screen text,
        one action per authority check (Navigator runs every action through
        the same capability gate), a bounded budget, and the outcome narrated
        in the outcome's own words — never "done" when the loop merely stopped.
        """
        turn_goal = goal.strip()
        driver = self._gui_driver()
        if self._gui_driver_override is None and isinstance(driver, VirtualGUIDriver):
            # no override: the default is virtual only because nothing real is seeded
            reply = Reply(
                text=(f"GUI control is not seated on this machine — right now my limb is the "
                      f"test double, and the test double touches nothing real. Seat it: "
                      f"BEANIE_AUTOMATION=1 plus pyautogui (pointer) and pyatspi/pywinauto "
                      f"(named-target eyes), then say it again."),
                confidence=0.85, confidence_label=confidence_label(0.85),
                turn_id=turn_id, success=False)
            self.trace.append(turn_id, "gui_takeover", {"goal": turn_goal[:80], "outcome": "unseated"})
            self._record_episode(turn_id, reply.text, 0.85, False, None,
                                 extra={"user_text": text, "goal": turn_goal[:120],
                                        "outcome": "unseated"})
            return reply
        try:
            screen = driver.read_screen()
        except BodyError as exc:
            reply = Reply(
                text=(f"I can move a pointer here but I have no eyes: {exc}. Named-target "
                      f"seeing needs the platform accessibility backend (pyatspi on Linux, "
                      f"pywinauto on Windows) — I do not click blindly."),
                confidence=0.8, confidence_label=confidence_label(0.8),
                turn_id=turn_id, success=False)
            self.trace.append(turn_id, "gui_takeover",
                              {"goal": turn_goal[:80], "outcome": "no_eyes", "reason": str(exc)})
            self._record_episode(turn_id, reply.text, 0.8, False, None,
                                 extra={"user_text": text, "goal": turn_goal[:120],
                                        "outcome": "no_eyes"})
            return reply

        gate = AuthorityGate(self.memory)
        navigator = Navigator(driver, self.substrate, gate)
        report = navigator.run(turn_goal)
        action_count = len(report.steps)
        outcome = report.outcome
        if outcome == "needs_permission":
            text_out = report.permission_question
            confidence, ok = 0.9, False
        elif outcome == "completed":
            text_out, confidence, ok = (f"Done — '{turn_goal}' completed under supervision: "
                                        f"{action_count} action{'s' if action_count != 1 else ''} "
                                        f"({report.note}), every one logged in the trace."), 0.9, True
        elif outcome == "budget":
            text_out, confidence, ok = (f"'{turn_goal}' is not finished — the loop hit its budget "
                                        f"after {action_count} action{'s' if action_count != 1 else ''} "
                                        f"({report.note}). A paused task is not a done task; say "
                                        f"'continue' to give it another budget."), 0.8, False
        else:  # failed / unplannable
            text_out, confidence, ok = (f"I could not complete '{turn_goal}' — {report.note}. "
                                        f"The trace keeps exactly what was tried and what the "
                                        f"screen said; nothing was guessed."), 0.8, False
        self.trace.append(turn_id, "gui_takeover",
                          {"goal": turn_goal[:80], "outcome": outcome, "actions": action_count,
                           "note": report.note[:200]})
        self._record_episode(turn_id, text_out, confidence, ok, None,
                             extra={"user_text": text, "goal": turn_goal[:120],
                                    "outcome": outcome, "actions": action_count})
        return Reply(text=text_out, confidence=confidence,
                     confidence_label=confidence_label(confidence), turn_id=turn_id, success=ok)

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


    # ======================================================================
    # Decision-gated body flows (§11) — classified needs become real actions
    # ======================================================================

    def _route_need(self, turn_id: str, text: str) -> Optional[Reply]:
        need = self.decision_gate.classify(text)
        if need.kind == "play_media":
            self._organ_hint = ("the decision gate + file index (\u00a711.1/\u00a711.2) — "
                                "a media request routed to a real place")
            return self._play_media(turn_id, text, need)
        if need.kind == "search_file":
            self._organ_hint = ("the decision gate + file index (\u00a711.1/\u00a711.2) — "
                                "a find the machine actually searched")
            return self._find_files(turn_id, text, need)
        if need.kind == "open_app":
            self._organ_hint = ("the decision gate + OS body (\u00a711.1/\u00a711.8) — "
                                "an app to launch for real")
            return self._open_app(turn_id, text, need)
        if need.kind == "web":
            self._organ_hint = ("the decision gate + OS body (\u00a711.1/\u00a711.8) — "
                                "the web reached for openly")
            return self._open_web(turn_id, text, need)
        if need.kind in ("install_app", "uninstall_app", "shell", "docker_run"):
            self._organ_hint = ("the decision gate + authority (\u00a711.1/\u00a75) — "
                                "a system-changing need, permission first")
            return self._execute_system_need(turn_id, text, need)
        if need.kind == "phone":
            self._organ_hint = ("the decision gate + android body (\u00a711.1/\u00a711.5) — "
                                "the phone as a limb")
            return self._handle_phone(turn_id, text, need)
        if need.kind == "learn":
            self._organ_hint = ("the decision gate + curiosity (\u00a711.1/\u00a74.3) — "
                                "a declared learning task")
            return self._learn_flow(turn_id, text, need)
        return None

    def _os_body(self) -> Optional[OSBody]:
        """The real body — opt-in only, probed once (BEANIE_BODY_OS=1, §11.8)."""
        if not self._osbody_probed:
            self._osbody_probed = True
            if os.environ.get("BEANIE_BODY_OS") == "1":
                try:
                    self._osbody = OSBody()
                except RuntimeError:
                    self._osbody = None
        return self._osbody

    def _file_index(self) -> FileIndex:
        """The whole-PC index when the OS body is live, the sandbox otherwise (§11.2)."""
        if self._fileindex is None:
            roots = self.search_roots
            if roots is None:
                if self._os_body() is not None:
                    home = Path.home()
                    roots = [home / name for name in
                             ("Documents", "Downloads", "Desktop", "Music", "Videos", "Pictures")
                             if (home / name).is_dir()]
                    if not roots:
                        roots = [home]
                else:
                    roots = [self.body.root]
            self._fileindex = FileIndex(roots=roots, state_file=self.state_dir / ".fileindex.json")
        return self._fileindex

    def _capability_permission(self, turn_id: str, capability: str, goal: str) -> tuple[str, str]:
        """Four-state verdict for one capability the decision gate routed (§5):
        returns ("act" | "ask" | "deny", owner-facing text)."""
        permission = self.gate.check(capability)
        if permission.allowed:
            return "act", ""
        if permission.state == "not_allowed":
            self.trace.append(turn_id, "authority",
                              {"blocked": capability, "goal": goal, "state": permission.state})
            return "deny", f"You ruled {capability} out, so I won't do it."
        existing = [e for e in self.memory.query(kind="owner_model", type="permission_request",
                                                 capability=capability)
                    if e.content.get("status") == "pending"]
        if existing:
            entry = existing[-1]
            entry.content["count"] = int(entry.content.get("count", 1)) + 1
            entry.content["last_goal"] = goal
            entry.revise(f"asked again about {capability} ({entry.content['count']}x)", confidence=0.8)
            count = int(entry.content["count"])
        else:
            entry = Entry(
                id=self.memory.allocate_id(), kind=RecordKind.OWNER_MODEL,
                content={"type": "permission_request", "capability": capability, "status": "pending",
                         "count": 1, "first_goal": goal, "last_goal": goal},
                source=Source.SELF_REFLECTION, confidence=0.8,
            )
            self.memory.owner_model.append(entry)
            count = 1
        self.memory.owner_model.save_all()
        self.trace.append(turn_id, "authority",
                          {"permission_request": capability, "count": count, "goal": goal})
        if count == 1:
            return ("ask", f"I can do this, but {capability} needs your permission first — "
                           f"say 'you may {capability}' to allow it, or 'never use {capability}' to rule it out.")
        return ("ask", f"This is the {_ordinal(count)} time {capability} has come up. A standing rule "
                       f"('you may {capability}') would settle it for good.")

    def _play_media(self, turn_id: str, text: str, need: Need) -> Reply:
        """Local-first playback (§11.2, row 45): the PC's own copy always wins; a
        song the machine does not have streams — and the reply says which happened."""
        target = need.target.strip()
        index = self._file_index()
        index.build()
        matches = index.search(target, limit=5)
        body = self._os_body()
        if matches:
            top = matches[0]
            self._media_trail = (matches, 0)
            self._media_trail_target = target
            reply_text = self._media_serve_text(turn_id, target, top, 1, len(matches))
            confidence = 0.9
        else:
            self._media_trail = None
            self._media_trail_target = ""
            url, specific = youtube_top_result(target, fetch=self.youtube_fetcher)
            what = "the top result" if specific else "the search results"
            if body is None:
                reply_text = (f"Nothing like '{target}' exists anywhere this machine lets me see. "
                              f"YouTube fallback: {url} — set BEANIE_BODY_OS=1 and I'll open it for you.")
                confidence = 0.65
            else:
                verdict, question = self._capability_permission(turn_id, "open_url", target)
                if verdict == "act":
                    body.run("open_url", {"url": url})
                    reply_text = f"'{target}' isn't on this machine, so I opened {what} for it on YouTube ({url})."
                    confidence = 0.85
                elif verdict == "deny":
                    reply_text = question
                    confidence = 0.9
                else:
                    reply_text = f"'{target}' isn't on this machine. I could open {what} on YouTube ({url}) — {question}"
                    confidence = 0.7
        self.trace.append(turn_id, "media", {
            "target": target, "matched": matches[0].path if matches else None,
            "alternatives": [m.path for m in matches[1:]], "decision": need.to_dict()})
        episode = self._record_episode(
            turn_id, reply_text, confidence, True, None,
            extra={"user_text": text, "directive": "play_media", "decision": need.to_dict(),
                   "matched": matches[0].path if matches else None, "reply": reply_text})
        return Reply(text=reply_text, confidence=confidence,
                     confidence_label=confidence_label(confidence), turn_id=turn_id,
                     success=True, record_id=episode.id)

    def _media_serve_text(self, turn_id: str, target: str, match: Any,
                          position: int, total: int) -> str:
        """One ranked match presented honestly — with its position in the trail (§11.2)."""
        body = self._os_body()
        name = Path(match.path).name
        where = f" ({position} of {total})" if total > 1 else ""
        if body is None:
            return (f"I found '{name}' at {match.path} ({match.why}){where}. My OS body is opt-in and "
                    f"off — set BEANIE_BODY_OS=1 and I can play it in your default player.")
        verdict, question = self._capability_permission(turn_id, "play_media", target)
        if verdict == "act":
            body.run("play_media", {"path": match.path})
            return (f"Playing '{name}' in your default player{where} — closest match on this machine "
                    f"({match.why}). If that's not the one, tell me and I'll try the next.")
        if verdict == "deny":
            return question + f" I had '{name}' ready at {match.path}."
        return f"I found '{name}' at {match.path}{where}. {question}"

    def _media_follow(self, turn_id: str) -> Reply:
        """'No, the other one' (§11.2): walk the last ranked trail, one step at a
        time, and say so when the trail is exhausted — silence-wrapping to the
        first match again would be a lie."""
        assert self._media_trail is not None
        matches, served = self._media_trail
        target = self._media_trail_target
        nxt = served + 1
        if nxt >= len(matches):
            url = youtube_search_url(target)
            last_name = Path(matches[-1].path).name
            reply_text = (f"'{last_name}' was the last local match ({len(matches)} of {len(matches)}) "
                          f"— no untouched alternatives remain on this machine for '{target}'. "
                          f"Your outside door stays open: {url}")
            confidence = 0.75
        else:
            self._media_trail = (matches, nxt)
            reply_text = ("Next match, then: "
                          + self._media_serve_text(turn_id, target, matches[nxt], nxt + 1, len(matches)))
            confidence = 0.9
        self.trace.append(turn_id, "media", {"followed": True, "target": target,
                                             "served_index": self._media_trail[1],
                                             "total": len(matches)})
        episode = self._record_episode(
            turn_id, reply_text, confidence, True, None,
            extra={"user_text": "media follow-up", "directive": "media_follow",
                   "trail_position": self._media_trail[1] + 1, "trail_total": len(matches)})
        return Reply(text=reply_text, confidence=confidence,
                     confidence_label=confidence_label(confidence), turn_id=turn_id,
                     success=True, record_id=episode.id)

    def _find_files(self, turn_id: str, text: str, need: Need) -> Reply:
        """Whole-machine search the owner can audit (§11.2, row 44)."""
        target = need.target.strip()
        index = self._file_index()
        index.build()
        matches = index.search(target, limit=5)
        if matches:
            listing = "\n".join(f"  • {Path(m.path).name} — {m.path} ({m.why})" for m in matches)
            reply_text = f"Found {len(matches)} match(es) for '{target}':\n{listing}"
            confidence = 0.9
        else:
            reply_text = (f"I searched everywhere I can see and found nothing like '{target}' — "
                          f"an honest zero, not a hidden miss.")
            confidence = 0.65
        self.trace.append(turn_id, "media", {
            "target": target, "matches": [m.path for m in matches], "decision": need.to_dict()})
        episode = self._record_episode(
            turn_id, reply_text, confidence, True, None,
            extra={"user_text": text, "directive": "search_file", "decision": need.to_dict(),
                   "matches": [m.path for m in matches]})
        return Reply(text=reply_text, confidence=confidence,
                     confidence_label=confidence_label(confidence), turn_id=turn_id,
                     success=True, record_id=episode.id)

    def _open_app(self, turn_id: str, text: str, need: Need) -> Reply:
        """Launch applications for real — or say plainly that the body is off (§11.8)."""
        target = need.target.strip()
        body = self._os_body()
        if body is None:
            reply_text = (f"Understood: open '{target}'. My OS body is opt-in and off "
                          f"(BEANIE_BODY_OS=1); nothing was launched and I'm saying so plainly.")
            confidence = 0.85
        else:
            verdict, question = self._capability_permission(turn_id, "open_app", target)
            if verdict == "act":
                body.run("open_app", {"app": target})
                reply_text = f"Launching '{target}' now."
            else:
                reply_text = question
            confidence = 0.9
        self.trace.append(turn_id, "body", {"op": "open_app", "target": target,
                                            "decision": need.to_dict()})
        episode = self._record_episode(
            turn_id, reply_text, confidence, True, None,
            extra={"user_text": text, "directive": "open_app", "decision": need.to_dict()})
        return Reply(text=reply_text, confidence=confidence,
                     confidence_label=confidence_label(confidence), turn_id=turn_id,
                     success=True, record_id=episode.id)

    def _open_web(self, turn_id: str, text: str, need: Need) -> Reply:
        """Open a page for real — a URL, or the honest top search result (§11.8)."""
        target = need.target.strip()
        is_url = need.reason == "an explicit site to open"
        url = target if is_url else google_search_url(target)
        episode_extra: dict[str, Any] = {}
        body = self._os_body()
        if body is None:
            reply_text = (f"Understood: {url}. My OS body is opt-in and off — open it yourself, "
                          f"or set BEANIE_BODY_OS=1 and I'll open pages for you.")
            confidence = 0.85
        else:
            verdict, question = self._capability_permission(turn_id, "open_url", target)
            if verdict == "act":
                body.run("open_url", {"url": url})
                reply_text = f"Opening {url}."
            elif verdict == "deny":
                reply_text = question
            else:
                reply_text = f"The page waiting on your word is {url}. {question}"
            confidence = 0.9
        if need.needs_learning:
            self.curiosity.open_question(target[:60], "declared research need from a web request")
            research_note = self._web_research(turn_id, target, episode_extra)
            if research_note:
                reply_text = research_note + "\n\n" + reply_text
        self.trace.append(turn_id, "body", {"op": "open_url", "url": url, "decision": need.to_dict(),
                                            "web_results": [r.get("url") for r in episode_extra.get("web_results", [])]})
        extra: dict[str, Any] = {"user_text": text, "directive": "web", "decision": need.to_dict(), "url": url}
        extra.update(episode_extra)
        episode = self._record_episode(
            turn_id, reply_text, confidence, True, None, extra=extra)
        return Reply(text=reply_text, confidence=confidence,
                     confidence_label=confidence_label(confidence), turn_id=turn_id,
                     success=True, record_id=episode.id)

    def _web_research(self, turn_id: str, target: str, extra: dict[str, Any]) -> str:
        """The web actually answers (rows 46/51): fetch live results, and with a
        live tier weigh them — always labelled as a dated live lookup, kept
        strictly apart from memory. Network failure is reported as failure."""
        results = web_search(target, fetch=self.web_fetcher)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.trace.append(turn_id, "web_research",
                          {"target": target, "result_count": len(results),
                           "urls": [r.url for r in results]})
        extra["web_results"] = [r.to_dict() for r in results]
        if not results:
            return (f"I couldn't reach the web for a usable answer (DuckDuckGo, {today}) — the "
                    f"network is down, blocked, or empty on this one. I'm reporting that plainly; "
                    f"the manual route is below.")
        numbered = "\n".join(f"  {i+1}. {r.title} — {r.url}\n     {r.snippet}"
                             for i, r in enumerate(results[:4]))
        if self.substrate.name != "stub":
            outcome = self.substrate.deep(
                {"user_text": (
                    f"These are LIVE web results fetched today ({today}) for the question: {target}\n"
                    f"{numbered}\n"
                    "Answer in at most 60 words what the web says, then a line 'BEST:' naming the "
                    "source to open first (write 'IRRELEVANT:' instead if the results miss the question)."
                )}, [], candidate="web-verify",
            )
            if outcome.success and outcome.text.strip():
                return (outcome.text.strip()[:520]
                        + f"\n\n— a live lookup from DuckDuckGo ({today}), kept apart from my memory; "
                        "a lookup replaces a stale guess, it does not become memory itself.")
        return (f"Live lookup results (DuckDuckGo, {today}) — top {min(4, len(results))}, raw below; "
                f"I can't weigh them yet without the model tier wired:\n{numbered}")

    def _execute_system_need(self, turn_id: str, text: str, need: Need) -> Reply:
        """System-changing needs: command preview first, authority always (§5, §11.4)."""
        target = need.target.strip()
        resolved_note = ""
        alternatives: list[str] = []
        resolution_failed = False
        body_for_search = self._os_body()
        if need.kind in ("install_app", "uninstall_app") and body_for_search is not None:
            # §11.4: a wording is a lookup, not a command — resolve the real id
            # first; the ask and the run name the id the machine will act on
            search = getattr(body_for_search, "search_package", None)
            candidates: list[dict[str, str]] = []
            search_probe = False
            if callable(search):
                search_probe = True
                candidates = search(target)
            if candidates:
                resolved = candidates[0]
                alternatives = [c["id"] for c in candidates[1:4]]
                if resolved["id"].lower() != target.lower():
                    resolved_note = (f"Resolved '{target}' → {resolved['id']} ({resolved['label']})"
                                     + (f"; also matching: {', '.join(alternatives)}."
                                        if alternatives else "."))
                target = resolved["id"]
            elif search_probe:
                # zero candidates FROM A REAL SEARCH blocks auto-execution
                # (nothing to aim at) — but a body that cannot search cannot
                # disprove an id, so only actual search misses flag failure
                resolution_failed = True
                resolved_note = (f"Note: no exact package id matched '{target}' in the manager's "
                                 f"search results.")
        if need.kind in ("install_app", "uninstall_app"):
            args: dict[str, Any] = {"package": target}
        elif need.kind == "shell":
            args = {"command": target}
        else:  # docker_run: "image command…"
            parts = target.split(None, 1)
            args = {"image": parts[0], "command": parts[1] if len(parts) > 1 else ""}
        body = self._os_body()
        if body is None:
            reply_text = (f"Understood: {need.kind} '{target}'. That changes the system, so even "
                          f"with permission it needs my OS body — opt-in and off (BEANIE_BODY_OS=1). "
                          f"Nothing ran.")
            confidence = 0.85
        else:
            preview = OSBody(dry_run=True).run(need.kind, args)["would_run"]
            verdict, question = self._capability_permission(turn_id, need.kind, target)
            if verdict == "act" and resolution_failed:
                reply_text = (f"No package matched '{target}' in this machine's package manager — "
                              f"nothing was installed, nothing was guessed. Give me the exact id "
                              f"and I'll ask with the exact command.")
                confidence = 0.85
                self.trace.append(turn_id, "body", {"op": need.kind, "target": target,
                                                    "resolved": None, "decision": need.to_dict()})
                episode = self._record_episode(
                    turn_id, reply_text, confidence, True, None,
                    extra={"user_text": text, "directive": need.kind, "decision": need.to_dict(),
                           "resolved": None})
                return Reply(text=reply_text, confidence=confidence,
                             confidence_label=confidence_label(confidence), turn_id=turn_id,
                             success=True, record_id=episode.id)
            elif verdict == "act":
                try:
                    result = body.run(need.kind, args)
                except BodyError as exc:
                    reply_text = f"I tried '{preview}' and the body reported: {exc}"
                    confidence = 0.8
                else:
                    if "ran" in result or result.get("returncode", 0) == 0:
                        tail = (result.get("stdout") or "").strip().splitlines()
                        summary = (" — last line: " + tail[-1][:200]) if tail else ""
                        reply_text = f"Done: {preview}{summary}"
                    else:
                        stderr = (result.get("stderr") or "").strip().splitlines()
                        summary = (": " + stderr[-1][:200]) if stderr else ""
                        reply_text = (f"It ran and failed (exit {result.get('returncode')}){summary} "
                                      f"— that's the honest result, not a retry in disguise.")
                    confidence = 0.9
            elif verdict == "deny":
                reply_text = question + f" The planned command was: {preview}"
                confidence = 0.9
            else:
                reply_text = f"This would run: {preview}. {question}"
                confidence = 0.85
        if resolved_note:
            reply_text = resolved_note + " " + reply_text
        self.trace.append(turn_id, "body", {"op": need.kind, "target": target,
                                            "decision": need.to_dict(),
                                            "resolved_alternatives": alternatives})
        episode = self._record_episode(
            turn_id, reply_text, confidence, True, None,
            extra={"user_text": text, "directive": need.kind, "decision": need.to_dict(),
                   "resolved": target, "resolved_alternatives": alternatives})
        return Reply(text=reply_text, confidence=confidence,
                     confidence_label=confidence_label(confidence), turn_id=turn_id,
                     success=True, record_id=episode.id)

    def _handle_phone(self, turn_id: str, text: str, need: Need) -> Reply:
        """The phone as a limb — discovered, never asserted (§11.5, row 48)."""
        from .android import ADBDriver, VirtualAndroidDriver, default_android_driver

        driver = default_android_driver()
        real_phone = isinstance(driver, ADBDriver) and driver.available()
        if not real_phone:
            reply_text = ("Your phone isn't connected (no adb device answering, or BEANIE_ANDROID "
                          "isn't enabled). Plug it in with USB debugging on and ask again — "
                          "nothing was attempted.")
            confidence = 0.85
        else:
            verdict, question = self._capability_permission(turn_id, "phone", need.target)
            if verdict == "act":
                open_match = re.match(r"(?:open|launch|start)\s+(.+)", need.target.strip(), re.IGNORECASE)
                if open_match:
                    app = open_match.group(1).strip()
                    try:
                        driver.execute({"type": "open_app", "package": app})
                        reply_text = f"Opening '{app}' on your phone."
                    except BodyError as exc:
                        reply_text = f"The phone rejected the open: {exc}"
                elif self.substrate.name != "stub":
                    reply_text = ("Connected. Phone navigation beyond opening apps uses the model "
                                  "tier over the screen — the tier is set; describe the target screen "
                                  "and I'll navigate to it when that loop ships with the phone driver.")
                else:
                    reply_text = ("Connected. I can open apps on it right now; navigating inside them "
                                  "needs the model tier (my current one is the Stage-0 stub, and it "
                                  "cannot read a screen).")
            elif verdict == "deny":
                reply_text = question
            else:
                reply_text = f"Your phone is connected. {question}"
            confidence = 0.9
        self.trace.append(turn_id, "phone", {"connected": real_phone, "decision": need.to_dict()})
        episode = self._record_episode(
            turn_id, reply_text, confidence, True, None,
            extra={"user_text": text, "directive": "phone", "decision": need.to_dict()})
        return Reply(text=reply_text, confidence=confidence,
                     confidence_label=confidence_label(confidence), turn_id=turn_id,
                     success=True, record_id=episode.id)

    def _learn_flow(self, turn_id: str, text: str, need: Need) -> Reply:
        """'I need to learn this first' is a first-class answer (§11.1, row 51) — and
        with a live tier the learning starts immediately: find a source, read what can
        honestly be read (its transcript), have the tier condense and gap-check it
        ("what does this source NOT cover?" — most videos are incomplete), and name the
        gaps as new open questions. Practice remains the next step either way."""
        target = need.target.strip()
        self.curiosity.open_question(target[:60], "declared learning task from the decision gate")
        research: dict[str, Any] = {}
        reply_text: Optional[str] = None
        confidence = 0.6
        if self.substrate.name != "stub":
            packet = Researcher(fetch=self.youtube_fetcher).research_video(target)
            if packet is not None and packet.transcript is not None:
                outcome = self.substrate.deep(
                    {"user_text": (
                        "You are verifying a how-to video an agent uses to learn a skill.\n"
                        f"TOPIC: {target}\n"
                        f"TRANSCRIPT (excerpt):\n{packet.transcript.excerpt()}\n"
                        "Write (1) a compact checklist of at most 8 numbered steps for the topic, "
                        "using only what the transcript supports; then (2) a line starting 'GAPS:' "
                        "naming what this source does NOT explain or covers poorly, so a second "
                        "source can finish the job. Under 150 words."
                    )},
                    [], candidate="learn-verify",
                )
                if outcome.success and outcome.text.strip():
                    gaps_line = next(
                        (line.strip() for line in outcome.text.splitlines()
                         if line.strip().upper().startswith("GAPS")), "",
                    )
                    if ":" in gaps_line:
                        gap_detail = gaps_line.split(":", 1)[1].strip()
                        if gap_detail:
                            self.curiosity.open_question(
                                target[:44] + " — second source needed",
                                f"first source incomplete (gap-check): {gap_detail[:160]}",
                            )
                    reply_text = (
                        outcome.text.strip()[:700]
                        + "\n\n— condensed and gap-checked by my model tier from "
                        + packet.source_label
                        + "; transcript text, not visual understanding. It stays unverified until "
                        "I practice it — logged as the next step."
                    )
                    confidence = 0.8
                    research = {"kind": "transcript", "video_url": packet.video_url,
                                "title": packet.title, "steps": packet.steps}
            elif packet is not None and packet.no_captions:
                reply_text = (
                    f"I found a relevant video — '{packet.title}' ({packet.video_url}) — but it has "
                    f"no transcript I can read: it teaches in pictures, and my vision tier isn't "
                    f"wired yet, so I can't (yet) analyze it like you would. Open it yourself — or, "
                    f"with my OS body on, say 'you may open_url' and I'll put it on screen for you. "
                    f"The learning task stays logged either way."
                )
                confidence = 0.6
                research = {"kind": "video-no-captions", "video_url": packet.video_url,
                            "title": packet.title}
            if reply_text is None:
                # no source resolved — teach from the tier's own knowledge, labelled as such
                outcome = self.substrate.deep(
                    {"user_text": f"Explain concisely, in under 120 words, how to: {target}"},
                    [], candidate="teach",
                )
                if outcome.success and outcome.text.strip():
                    reply_text = (
                        outcome.text.strip()[:700]
                        + "\n\n— from my model tier's general knowledge (no source was resolved); "
                        "I treat that as a draft until I've practiced it. The learning task is "
                        "logged: research, then sandbox practice, then it becomes a real skill."
                    )
                    confidence = 0.75
                else:
                    reply_text = (f"I don't know how to '{target}' yet and my tier couldn't teach it "
                                  f"either — saying so instead of improvising. The learning task is "
                                  f"logged.")
        else:
            reply_text = (
                f"I don't know how to '{target}' yet — saying so instead of improvising. My plan: "
                f"research it online (text and videos the way you find them), verify each source "
                f"for what it leaves out, then practice in my sandbox until the "
                f"demonstration learner turns it into a skill. Those research senses need the model "
                f"tier, so for now the gap is logged as an open question, not faked."
            )
        self.trace.append(turn_id, "learning_task",
                          {"topic": target, "decision": need.to_dict(), "research": research})
        extra: dict[str, Any] = {"user_text": text, "directive": "learn", "decision": need.to_dict()}
        if research:
            extra["research"] = research
        episode = self._record_episode(
            turn_id, reply_text, confidence, True, None, extra=extra)
        return Reply(text=reply_text, confidence=confidence,
                     confidence_label=confidence_label(confidence), turn_id=turn_id,
                     success=True, record_id=episode.id)

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
            # dual-process: System-1 candidate, System-2 verdict (§2); the
            # candidate is reused when the fast tier already ran — the same
            # intuition is never paid for twice (a real tier costs money and time)
            if not candidate:
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
        # NOTE: FailureTaxonomy.NONE is a truthy enum member, so the "no failure"
        # guard must compare against NONE explicitly — `not outcome.failure` is
        # False even on success and silently disabled the whole check.
        concerns: list[dict] = []
        stakes = stakes_of(text)
        failure_free = outcome.failure in (None, FailureTaxonomy.NONE)
        if depth in ("deep", "deep_verified") and stakes and failure_free and outcome.success:
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
        surfaced = self._surface_idle_finding(turn_id) or self._surface_permission_request(turn_id)
        return Reply(
            text=reply_text,
            confidence=confidence,
            confidence_label=label,
            turn_id=turn_id,
            success=outcome.success,
            failure=outcome.failure,
            record_id=episode.id,
            reminders=tuple(reminders),
            questions=(surfaced,) if surfaced else (),
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
        "trivial" over time. A frustrated owner is never answered reflexively:
        the recorded tone (§3.5 observation) raises the floor to deep processing,
        because a cheap answer is the last thing that helps then.
        """
        stakes = stakes_of(text)
        if stakes == 0 and len(text.split()) <= self.policy.word_limit:
            if self.affect.current_tone() == "frustration":
                return "deep"  # affect observation raises the effort floor, never lowers it
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
            "turn_id": turn_id,  # lets an explanation cite the decision trace (§9.9)
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
        self._last_episode_turn = turn_id
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
