"""Planning & execution — goal → skill → plan → act → verify → repair.

Traceability: ARCHITECTURE §7 (mind discovers capability by need and verifies
the result), §6/T1 (a demonstrated skill performed in a new context), T3
(self-correction after failure: identify the cause, repair, retry, consolidate
the lesson), T12 (proactive re-check of stale state before acting on it), and
§4.8 (incubation queue: problems parked with partial state and revisited on a
later budget when new evidence has arrived — never silently abandoned).

Plans are built from the active skill library by goal class, instantiated
against the current body state (sandbox tree), executed step by step through
the authority gate, and verified by observing the resulting state. Failures
carry a taxonomy tag (Q28), get a repair from the skill's recorded failure
modes or the built-in repair table, and are retried — bounded. When no repair
exists the failure is parked in the incubator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .body import AuthorityGate, BodyError, SandboxBody
from .learning import DemonstrationLearner
from .records import Entry, RecordKind, Source, utcnow_iso
from .stores import Memory


@dataclass
class PlanStep:
    capability: str
    args: dict[str, Any]
    description: str = ""


@dataclass
class PlanResult:
    skill_id: Optional[str]
    steps: list[PlanStep]        # instantiated, concrete steps
    mapping: dict[str, str] = field(default_factory=dict)  # ext -> destination
    outcome: str = "not_run"     # success | failed | needs_permission
    permission_phrase: Optional[str] = None
    failure_taxonomy: Optional[str] = None
    repairs: int = 0
    last_result: Optional[dict[str, Any]] = None


#: deterministic repairs for known failure modes — scaffolding until skills
#: record their own failure modes (T3 consolidation replaces this table)
_REPAIRS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "missing_destination": [("mkdir", {"dir": ""})],
}


class Planner:
    """Goal → template plan using active skills; questions when none match."""

    def __init__(self, memory: Memory, learner: DemonstrationLearner) -> None:
        self.memory = memory
        self.learner = learner

    def plan_for_goal(self, goal: str, base_dir: str = "downloads") -> tuple[Optional[PlanResult], list[str]]:
        """Build a template plan for `goal`; returns (plan, questions) — T5.

        When no active skill covers the goal class, no plan is produced and
        the mind says what it needs instead of guessing.
        """
        skill = self.learner.find_skill_for_goal(goal)
        if skill is None:
            return None, ["I don't yet have a skill for that kind of task — demonstrate it once and I'll learn it."]
        mapping = dict(skill.content.get("mapping", {}))
        steps: list[PlanStep] = [
            PlanStep("list_files", {"dir": base_dir}, "sense what is in the folder"),
            PlanStep("snapshot", {}, "verify the result"),
        ]
        return PlanResult(skill_id=skill.id, steps=steps, mapping=mapping), []


class PlanExecutor:
    """Instantiate and execute plans through body + authority gate."""

    def __init__(self, body: SandboxBody, gate: AuthorityGate, learner: DemonstrationLearner, memory: Memory) -> None:
        self.body = body
        self.gate = gate
        self.learner = learner
        self.memory = memory

    def execute(self, plan: PlanResult, max_repairs: int = 2) -> PlanResult:
        steps = self._instantiate(plan)
        plan.steps = steps
        repairs = 0
        for step in steps:
            # authority first: the four states (§5)
            permission = self.gate.check(step.capability)
            if not permission.allowed:
                plan.outcome = "needs_permission"
                plan.permission_phrase = permission.phrase
                plan.last_result = {"capability": step.capability}
                return plan
            for attempt in range(2):
                try:
                    plan.last_result = self.body.run(step.capability, dict(step.args))
                    break
                except BodyError as exc:
                    plan.failure_taxonomy = exc.kind or exc.taxonomy  # what failed (Q28)
                    if attempt == 0 and repairs < max_repairs:
                        if self._repair(exc, step, plan):
                            repairs += 1
                            continue
                    plan.outcome = "failed"
                    return plan
        plan.outcome = "success"
        plan.repairs = repairs
        if repairs and plan.skill_id:
            self.learner.record_failure(plan.skill_id, plan.failure_taxonomy or "tool_execution_error", "auto-repaired")
        return plan

    # -- internals ----------------------------------------------------------

    def _instantiate(self, plan: PlanResult) -> list[PlanStep]:
        """Bind the mapping to the concrete files found *at execution time*.

        Listing happens here, not when the goal was phrased — the plan acts on
        current state (T12: never act on a cached view). Each file goes to the
        destination its extension maps to; unmapped files are left untouched
        (honesty: do only what was demonstrated).
        """
        listing: dict[str, Any] = {}
        concrete: list[PlanStep] = []
        base_dir = ""
        for step in plan.steps:
            if step.capability == "list_files":
                base_dir = str(step.args.get("dir", ""))
                listing = self.body.run("list_files", dict(step.args))
                concrete.append(step)
        for name in listing.get("files", []):
            extension = Path(name).suffix.lower().lstrip(".")
            destination = plan.mapping.get(extension)
            if destination is not None:
                concrete.append(
                    PlanStep(
                        "move_file",
                        {"src": f"{base_dir}/{name}", "dst": destination},
                        f".{extension} files belong in {destination}",
                    )
                )
        for step in plan.steps:
            if step.capability not in ("list_files", "move_file"):
                concrete.append(step)
        return concrete

    def _repair(self, exc: BodyError, step: PlanStep, plan: PlanResult) -> bool:
        """Apply a skill-recorded or built-in repair; True if one was used."""
        fixes: list[tuple[str, dict[str, Any]]] = []
        if plan.skill_id:
            skill = self.memory.find(plan.skill_id)
            if skill is not None:
                for mode in skill.content.get("failure_modes", []):
                    if mode.get("taxonomy") in (exc.kind, exc.taxonomy) and mode.get("fix"):
                        fixes.append(("recorded_fix", {"of": mode["fix"]}))
        if not fixes:
            fixes = _REPAIRS.get(exc.kind, []) or _REPAIRS.get(exc.taxonomy, [])
        for capability, template in fixes:
            if capability == "mkdir":
                args = dict(template)
                if args.get("dir") == "":
                    args["dir"] = str(step.args.get("dst", ""))
                if not args.get("dir"):
                    continue
                self.body.run("mkdir", args)
                return True
            if capability == "recorded_fix":
                # a recorded fix names a capability+args to run before retry
                recorded = template.get("of")
                if isinstance(recorded, dict) and recorded.get("capability"):
                    self.body.run(recorded["capability"], dict(recorded.get("args", {})))
                    return True
        return False


class Incubator:
    """Park unresolved problems; revisit when evidence has moved (§4.8)."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def park(self, problem: str, detail: dict[str, Any]) -> Entry:
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.SELF,
            content={
                "type": "open_problem",
                "problem": problem,
                "detail": detail,
                "parked_at": utcnow_iso(),
                "evidence_version_at_park": 0,
                "revisits": 0,
                "status": "parked",
            },
            source=Source.SELF_REFLECTION,
            confidence=0.5,
        )
        self.memory.self_model.append(entry)
        # baseline taken *after* parking: only later evidence counts (§4.8)
        entry.content["evidence_version_at_park"] = self.memory.self_model.count()
        entry.revise("parked with evidence baseline", observe=False)
        self.memory.self_model.save_all()
        return entry

    def due_for_revisit(self) -> list[Entry]:
        """Parked problems that have new evidence since parking (§4.8)."""
        version = self.memory.self_model.count()
        return [
            entry
            for entry in self.memory.query(kind="self", type="open_problem", status="parked")
            if int(entry.content.get("evidence_version_at_park", 0)) < version
        ]

    def revisit(self, entry: Entry, note: str) -> Entry:
        entry.content["revisits"] = int(entry.content.get("revisits", 0)) + 1
        entry.revise(note, confidence=min(0.7, entry.confidence + 0.05))
        self.memory.self_model.save_all()
        return entry

    def mark_resolved(self, entry_id: str, note: str) -> None:
        entry = self.memory.find(entry_id)
        if entry is not None:
            entry.content["status"] = "resolved"
            entry.revise(note, confidence=0.7)
            self.memory.self_model.save_all()
