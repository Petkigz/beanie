"""The decision gate — owner directive §D9: *how* a task gets done, and with what.

Spec: ARCHITECTURE §11 (owner directives), §4.1 (the loop's decision point),
§5 (authority) and §7 (embodiment — capabilities are probed, never assumed).


The owner's assessment, recorded in OWNER_DIRECTIVES.md: this gate is what makes Beanie
as strong as it should be "or just another generic AI". So it is a mechanism with
provenance, not a chain of ``if`` statements.

Division of labour, stated because three modules could otherwise each claim this job:

=================  ==========================================================
``cognition.py``   **how much effort** a turn deserves (reflex / deep / verified)
``gate.py``        **which route** a task takes, and why that one over the others
``planning.py``    **executes** the chosen route (goal → skill → plan → verify)
=================  ==========================================================

The gate does five things, in order:

1. **Enumerate** the candidate approaches for the goal (local index, local app, web,
   sandbox, container, ask the owner), each declaring the capabilities it needs.
2. **Filter** by what this machine can actually do *right now* — capabilities are probed,
   never assumed. A route whose condition does not hold is not silently dropped: it is
   reported as rejected **with the reason**, so "why didn't you just play the local file?"
   has an answer.
3. **Score** by capability fit, cost, risk, and — decisively — **what has worked before**
   (``RouteLedger``). The last term is why the gate improves with use instead of staying
   static: a route that failed last time starts lower next time.
4. **Choose**, recording the choice *and* the alternatives with their scores, so
   "why did you do it that way?" is auditable under §9.9 like any other claim.
5. **Re-decide on failure**: ``record_outcome`` demotes what failed, and the caller runs
   the next-best route.

Risk and permission follow §D8 exactly: the owner is the decider, Beanie carries no moral
veto of its own. Autonomous by default; ``needs_permission`` is set for the operations the
owner named as dangerous or irreversible (destructive file work, install/uninstall, system
settings, acting on someone else's account or data), and those go through the four-state
authority gate (§5) — which persists the owner's answer so the same question is never asked
twice. Reading the web is *not* in that set: the owner asked for the YouTube fallback to
just happen.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from .index import PLAYABLE

# --------------------------------------------------------------------- intents (§D4)

@dataclass(slots=True)
class Intent:
    """What an ambiguous request actually asks for, and how we know.

    ``why`` is not decoration: an intent guess that cannot name the pattern it matched is
    a guess the owner cannot check (§D6/§9.9 — the same rule as everywhere else).
    """

    action: str                     # play | open | find | where | install | uninstall | delete | web | learn
    object_phrase: str              # "kaba"
    kinds: tuple[str, ...] = ()     # index kinds the object may be
    preferred_kind: str = ""        # tie-break when two candidates score the same
    raw: str = ""
    why: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        kinds = f", looking among {', '.join(self.kinds)}" if self.kinds else ""
        return f"{self.action} '{self.object_phrase}'{kinds} — {'; '.join(self.why)}"


#: verb patterns → (action, kinds, preferred kind). Ordered: first match wins, and the
#: order is part of the mechanism, so it lives here where it can be read.
_PATTERNS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (r"\bplay\s+(?:me\s+|us\s+|the\s+song\s+|some\s+)?(?P<obj>.+)$", "play", PLAYABLE, "audio"),
    (r"\bput\s+on\s+(?P<obj>.+)$", "play", PLAYABLE, "audio"),
    (r"\blisten\s+to\s+(?P<obj>.+)$", "play", ("audio",), "audio"),
    (r"\bwatch\s+(?P<obj>.+)$", "play", ("video",), "video"),
    (r"\bopen\s+(?P<obj>.+)$", "open", (), ""),
    (r"\blaunch\s+(?P<obj>.+)$", "open", (), ""),
    (r"\bwhere\s+(?:is|are)\s+(?P<obj>.+)$", "where", (), ""),
    (r"\bfind\s+(?:me\s+)?(?P<obj>.+)$", "find", (), ""),
    (r"\blocate\s+(?P<obj>.+)$", "find", (), ""),
    (r"\blook\s+(?:for|through)\s+(?P<obj>.+)$", "find", (), ""),
    (r"\bsearch\s+(?:for\s+|my\s+|the\s+)?(?P<obj>.+)$", "find", (), ""),
    (r"\binstall\s+(?P<obj>.+)$", "install", (), ""),
    (r"\buninstall\s+(?:or\s+)?remove\s+(?P<obj>.+)$", "uninstall", (), ""),
    (r"\bdelete\s+(?P<obj>.+)$", "delete", (), ""),
    (r"\blook\s+up\s+(?:how\s+to\s+)?(?P<obj>.+)$", "learn", (), ""),
    (r"\bhow\s+(?:do|can)\s+(?:i|you)\s+(?P<obj>.+)$", "learn", (), ""),
)

#: trailing/leading words that decorate a request without changing what it asks for
_TAIL = re.compile(
    r"[\s.,!?]*(?:"
    r"please|pls|for me|right now|now|asap|"
    r"the song|the video|the audio|the music|the track|the movie|the file|song|video|audio|music|track|movie"
    r")[\s.,!?]*$", re.IGNORECASE)
_LEAD = re.compile(r"^(?:the|my|a|an|some)\s+", re.IGNORECASE)


def classify_intent(text: str) -> Optional[Intent]:
    """Parse a human-shaped request into an action + object, or return None honestly.

    Returning None is a real outcome: it means "this is not a task pattern I recognise",
    and the caller must then fall back to the conversation path rather than guess.
    """
    stripped = text.strip().lower()
    for pattern, action, kinds, preferred in _PATTERNS:
        match = re.search(pattern, stripped)
        if not match:
            continue
        raw_object = match.group("obj").strip()
        why = [f"matched the '{action}' pattern {pattern.split('(')[0].strip()!r}"]

        cleaned = raw_object
        previous = None
        while previous != cleaned:            # "play the song kaba please now"
            previous = cleaned
            cleaned = _TAIL.sub("", cleaned).strip()
            cleaned = _LEAD.sub("", cleaned).strip()
        if cleaned != raw_object:
            why.append(f"dropped decoration: {raw_object!r} → {cleaned!r}")
        if not cleaned:
            continue
        if action in ("play", "find", "open", "where") and not kinds:
            kinds = ()                        # any kind — the owner did not say
        return Intent(action=action, object_phrase=cleaned, kinds=tuple(kinds),
                      preferred_kind=preferred, raw=text.strip(), why=why)
    return None


# ------------------------------------------------------------------ approaches (§D9)

RISK_PENALTY: dict[str, float] = {"none": 0.0, "reversible": 0.15, "external": 0.30, "destructive": 0.75}

#: §D8 — the operations that always go through the authority gate. Everything else is
#: autonomous, including reading the web (the owner asked for the fallback to just work).
PERMISSION_REQUIRED_RISKS: frozenset[str] = frozenset({"destructive"})


@dataclass(frozen=True, slots=True)
class Approach:
    """One way a task could be done, with what it needs and what it costs."""

    id: str
    summary: str
    requires: tuple[str, ...] = ()
    cost: float = 0.30
    risk: str = "none"
    condition: str = "always"
    needs_permission: bool = False
    #: a fallback is the floor, not a competitor: it is chosen only when nothing else
    #: is eligible. Without that, "say what is missing" outranks "do the thing".
    fallback: bool = False

    @property
    def permission_gated(self) -> bool:
        return self.needs_permission or self.risk in PERMISSION_REQUIRED_RISKS


#: The condition vocabulary. Named conditions (not lambdas) so a decision can state, in
#: words and in the trace, exactly why a route was or was not eligible.
CONDITIONS: dict[str, tuple[str, Callable[[dict[str, Any]], bool]]] = {
    "always": ("it is always eligible", lambda facts: True),
    "local_hit": ("the whole-machine index found a match on this PC (§D6)",
                  lambda facts: bool(facts.get("local_hits"))),
    "play_clear": ("the owner asked to play something, and the best local match is playable",
                   lambda facts: facts.get("action") == "play" and bool(facts.get("playable_hit"))
                   and not facts.get("ambiguous")),
    "open_clear": ("the owner asked to open something and there is one clearly-best local match",
                   lambda facts: facts.get("action") == "open" and bool(facts.get("local_hits"))
                   and not facts.get("ambiguous")),
    "locate_clear": ("the owner asked where something is / to find it, and the index has a match",
                     lambda facts: facts.get("action") in ("find", "where")
                     and bool(facts.get("local_hits"))),
    "kind_mismatch": ("a file matched, but not in a kind this request can use",
                      lambda facts: bool(facts.get("kind_mismatch"))),
    "play_missing": ("the owner asked to play something and nothing on this PC matches at all",
                     lambda facts: facts.get("action") == "play" and facts.get("searched")
                     and not facts.get("local_hits") and not facts.get("kind_mismatch")),
    "no_local_hit": ("the index searched the whole PC and found nothing good enough (§D6)",
                     lambda facts: facts.get("searched") and not facts.get("local_hits")),
    "ambiguous": ("two or more local candidates scored the same, so choosing would be a guess",
                  lambda facts: bool(facts.get("ambiguous"))),
    "needs_isolation": ("the task asks for isolation or a different OS than this host (§D2c)",
                        lambda facts: bool(facts.get("needs_isolation"))),
    "knowledge_gap": ("Beanie has no skill for this yet and says so (§D5)",
                      lambda facts: bool(facts.get("knowledge_gap"))),
}


#: The route table. Adding a capability to Beanie means adding a row here — which is the
#: point: the gate's whole space of choices is readable in one place.
APPROACHES: tuple[Approach, ...] = (
    Approach("local_play", "play the file already on this PC with a local player",
             requires=("play_media",), cost=0.05, risk="none", condition="play_clear"),
    Approach("local_open", "open the file with the OS's own handler for its type",
             requires=("open_path",), cost=0.08, risk="none", condition="open_clear"),
    Approach("report_found", "tell the owner where the file is, and why that file matched",
             requires=(), cost=0.10, risk="none", condition="locate_clear"),
    Approach("clarify_kind", "say what was actually found and that it cannot be played",
             requires=(), cost=0.15, risk="none", condition="kind_mismatch"),
    Approach("ask_which", "ask the owner which of the tied candidates they meant",
             requires=(), cost=0.20, risk="none", condition="ambiguous"),
    Approach("web_play", "play it from the web (e.g. YouTube) because it is not on this PC",
             requires=("open_url",), cost=0.45, risk="external", condition="play_missing"),
    Approach("web_search", "search the web for the thing itself (§D5)",
             requires=("web_search",), cost=0.50, risk="external", condition="knowledge_gap"),
    Approach("sandbox_run", "run it in a sandbox/container instead of on the host (§D2c)",
             requires=("container_run",), cost=0.60, risk="reversible", condition="needs_isolation"),
    Approach("install_tool", "install the software the task needs (§D2b)",
             requires=("install_app",), cost=0.70, risk="destructive", condition="knowledge_gap",
             needs_permission=True),
    Approach("report_gap", "say plainly what is missing and what would fix it — never fake success",
             requires=(), cost=0.95, risk="none", condition="always", fallback=True),
)


@dataclass(slots=True)
class Route:
    """A scored candidate: eligible or rejected, and why."""

    approach: Approach
    eligible: bool
    score: float
    prior: float
    missing: tuple[str, ...] = ()
    why: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.approach.id

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.approach.id,
            "summary": self.approach.summary,
            "eligible": self.eligible,
            "score": round(self.score, 4),
            "prior": round(self.prior, 4),
            "cost": self.approach.cost,
            "risk": self.approach.risk,
            "condition": self.approach.condition,
            "missing_capabilities": list(self.missing),
            "needs_permission": self.approach.permission_gated,
            "why": list(self.why),
        }


@dataclass(slots=True)
class Decision:
    """The gate's output — chosen route, every alternative, and the reason."""

    goal: str
    intent: Optional[Intent]
    routes: list[Route]
    chosen: Optional[Route]
    facts: dict[str, Any]
    needs_permission: bool = False

    @property
    def rejected(self) -> list[Route]:
        return [r for r in self.routes if r is not self.chosen]

    @property
    def eligible(self) -> list[Route]:
        return [r for r in self.routes if r.eligible]

    def route(self, approach_id: str) -> Optional[Route]:
        return next((r for r in self.routes if r.id == approach_id), None)

    def to_text(self) -> str:
        head = f"decision gate: goal '{self.goal}'"
        if self.intent is not None:
            head += f" read as {self.intent.action} '{self.intent.object_phrase}'"
        if self.chosen is None:
            return head + " — no route is available on this machine (that is the honest answer)"
        lines = [head + f" → {self.chosen.id} ({self.chosen.score:.2f}): {self.chosen.approach.summary}"]
        for route in sorted(self.rejected, key=lambda r: -r.score)[:4]:
            reason = "; ".join(route.why) or "eligible but scored lower"
            lines.append(f"  not {route.id} ({route.score:.2f}) — {reason}")
        if self.needs_permission:
            lines.append("  this route needs the owner's permission first (§D8)")
        return "\n".join(lines)

    def to_trace_payload(self) -> dict[str, Any]:
        """The shape recorded in the trace, so §9.9 can audit the choice itself."""
        return {
            "goal": self.goal,
            "intent": ({"action": self.intent.action, "object": self.intent.object_phrase,
                        "kinds": list(self.intent.kinds), "why": list(self.intent.why)}
                       if self.intent is not None else None),
            "routes": [r.to_dict() for r in self.routes],
            "chosen": self.chosen.id if self.chosen else None,
            "needs_permission": self.needs_permission,
            "facts": {k: v for k, v in self.facts.items() if isinstance(v, (str, int, float, bool, type(None)))},
        }


# ------------------------------------------------------------------- route history

class RouteLedger:
    """What has worked before — the term that makes the gate learn (§D9 step 3).

    Deliberately a counter table, not a memory record: it answers "how often did this
    route succeed?" and nothing else. One JSONL line per outcome, appended, never
    rewritten, so a corrupt last line cannot lose the history before it.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.successes: dict[str, int] = {}
        self.failures: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue                      # a torn last line costs one event, not the ledger
            key = str(row.get("route", ""))
            if not key:
                continue
            if row.get("success"):
                self.successes[key] = self.successes.get(key, 0) + 1
            else:
                self.failures[key] = self.failures.get(key, 0) + 1

    def record(self, route_id: str, success: bool, note: str = "") -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"route": route_id, "success": bool(success),
                                     "note": note[:200], "at": time.time()}) + "\n")
        if success:
            self.successes[route_id] = self.successes.get(route_id, 0) + 1
        else:
            self.failures[route_id] = self.failures.get(route_id, 0) + 1

    def prior_for(self, route_id: str, neutral: float = 0.5) -> float:
        """Success rate, shrunk toward neutral when there is little history.

        The shrinkage matters: one success must not make a route look certain. With
        ``prior = (successes + 2*neutral) / (total + 2)`` a single win gives 0.625, ten
        wins give 0.92 — evidence accumulates instead of being decided by the first try.
        """
        wins = self.successes.get(route_id, 0)
        losses = self.failures.get(route_id, 0)
        total = wins + losses
        if total == 0:
            return neutral
        return (wins + 2 * neutral) / (total + 2)

    def stats(self) -> dict[str, Any]:
        return {route: {"success": self.successes.get(route, 0),
                        "failure": self.failures.get(route, 0),
                        "prior": round(self.prior_for(route), 4)}
                for route in sorted(set(self.successes) | set(self.failures))}


# ------------------------------------------------------------------------- the gate

SCORE_WEIGHTS: dict[str, float] = {"fit": 0.50, "prior": 0.20, "cost": 0.20, "risk": 0.10}


class DecisionGate:
    """Chooses the route, and can always say why (§D9).

    ``capabilities`` is the *probed* capability table of the body currently in use, so the
    gate can never propose something this machine cannot do. That is the difference
    between a plan and a wish.
    """

    def __init__(self, capabilities: dict[str, str] | Callable[[], dict[str, str]],
                 ledger: Optional[RouteLedger] = None,
                 approaches: Sequence[Approach] = APPROACHES) -> None:
        self._capabilities = capabilities
        self.approaches: tuple[Approach, ...] = tuple(approaches)
        self.ledger = ledger

    @property
    def capabilities(self) -> dict[str, str]:
        return self._capabilities() if callable(self._capabilities) else dict(self._capabilities)

    def set_capabilities(self, capabilities: dict[str, str]) -> None:
        self._capabilities = capabilities

    def prior_for(self, route_id: str) -> float:
        return self.ledger.prior_for(route_id) if self.ledger else 0.5

    def decide(self, goal: str, facts: Optional[dict[str, Any]] = None,
               intent: Optional[Intent] = None) -> Decision:
        """Enumerate → filter → score → choose, recording every rejection reason."""
        facts = dict(facts or {})
        capabilities = self.capabilities
        routes: list[Route] = []

        for approach in self.approaches:
            missing = tuple(cap for cap in approach.requires if cap not in capabilities)
            condition_text, condition = CONDITIONS[approach.condition]
            holds = condition(facts)
            prior = self.prior_for(approach.id)
            why: list[str] = []

            if missing:
                why.append(f"this machine has no {', '.join(missing)} capability")
                routes.append(Route(approach, False, 0.0, prior, missing, why))
                continue
            if not holds:
                why.append(f"not eligible: {approach.condition} — {condition_text}")
                routes.append(Route(approach, False, 0.0, prior, (), why))
                continue

            why.append(f"eligible: {approach.condition} — {condition_text}")
            fit = SCORE_WEIGHTS["fit"]
            prior_term = SCORE_WEIGHTS["prior"] * prior
            if self.ledger is not None and (self.ledger.successes.get(approach.id)
                                            or self.ledger.failures.get(approach.id)):
                stats = self.ledger.stats()[approach.id]
                why.append(f"history: {stats['success']} success / {stats['failure']} failure "
                           f"→ prior {prior:.3f}")
            else:
                why.append(f"no history for this route yet → neutral prior {prior:.3f}")
            cost_term = SCORE_WEIGHTS["cost"] * (1.0 - approach.cost)
            why.append(f"cost {approach.cost:.2f} → +{cost_term:.3f}")
            risk_term = SCORE_WEIGHTS["risk"] * (1.0 - RISK_PENALTY[approach.risk])
            why.append(f"risk '{approach.risk}' → +{risk_term:.3f}")
            score = fit + prior_term + cost_term + risk_term
            routes.append(Route(approach, True, round(score, 4), prior, (), why))

        eligible = [r for r in routes if r.eligible]
        # A fallback route is always eligible, so `chosen` is never None while a mind
        # exists — the gate always has something true to do. But it competes only
        # against other fallbacks: honesty is the floor, not a preference.
        real = [r for r in eligible if not r.approach.fallback]
        pool = real or eligible
        chosen = max(pool, key=lambda r: r.score) if pool else None
        needs_permission = bool(chosen and chosen.approach.permission_gated)
        return Decision(goal=goal, intent=intent, routes=routes, chosen=chosen,
                        facts=facts, needs_permission=needs_permission)

    def next_best(self, decision: Decision, exclude: Sequence[str] = ()) -> Optional[Route]:
        """§D9 step 5: after a failure, the next eligible route that has not been tried."""
        tried = set(exclude)
        candidates = [r for r in decision.eligible if r.id not in tried and r is not decision.chosen]
        return max(candidates, key=lambda r: r.score) if candidates else None
