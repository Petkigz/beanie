"""General learning — procedural skills from demonstration & correction.

Traceability: ARCHITECTURE §6 (procedural learning from demonstration: watch
episodes → infer goal, state changes, conditions, what can vary → propose the
general rule as a question, not a form) and §3.3 (procedural store). Also
T1 (one-demonstration learning with transfer), T3 (self-correction after
failure via failure modes + repairs), T9 (correction → strategy revision:
"no, that's wrong" adjusts the skill, not just the fact).

The demonstration pipeline is generic over body actions
({capability, args, observed effect}); file-organizing demonstrations are the
first concrete kind (extension→directory mapping). Skills are stored as
envelope entries in the procedural store; failures and corrections write
revision reasons so the skill's history explains itself (T10).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .records import Entry, EvidenceRef, RecordKind, Source
from .stores import Memory


@dataclass(frozen=True)
class DemoAction:
    """One step of a live demonstration (owner's body trace)."""

    capability: str
    args: dict[str, Any]
    effect_note: str = ""


@dataclass
class SkillProposal:
    """A skill inferred from demonstration, awaiting owner confirmation."""

    entry: Entry
    confirm_question: str

    @property
    def skill_id(self) -> str:
        return self.entry.id


class DemonstrationLearner:
    """Turn demonstrated actions into a parameterized skill (T1)."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def learn(
        self,
        *,
        goal_class: str,
        title: str,
        actions: list[DemoAction],
        owner_note: str = "",
    ) -> SkillProposal:
        """Infer a skill from one demonstration and propose it for confirmation.

        The inference that is genuinely general (transferable) here: file
        moves observed in the demo are parameterized as
        "files whose extension is E belong in directory D", so the skill can
        be performed later on a folder with different files (T1 transfer).
        """
        content: dict[str, Any] = {
            "type": "skill",
            "title": title,
            "goal_class": goal_class.lower(),
            "status": "proposed",  # -> "active" on owner confirmation
            "learned_via": "demonstration",
            "mapping": {},         # extension -> destination dir
            "steps": [{"capability": a.capability, "args": a.args, "note": a.effect_note} for a in actions],
            "failure_modes": [],   # filled in by T3 self-correction
            "owner_note": owner_note,
        }
        for action in actions:
            if action.capability == "move_file":
                src = str(action.args.get("src", ""))
                dst = str(action.args.get("dst", ""))
                extension = Path(src).suffix.lower().lstrip(".")
                if extension and dst:
                    content["mapping"][extension] = dst
        now_entry = self._store(content, confidence=0.5)
        mapping_text = ", ".join(f".{ext} → {dst}" for ext, dst in sorted(content["mapping"].items())) or "no file moves observed"
        return SkillProposal(
            entry=now_entry,
            confirm_question=f"Rule I learned: {mapping_text}. Is that the rule you want me to remember?",
        )

    def confirm(self, skill_id: str) -> Entry:
        """Owner said yes: activate the skill (source becomes OWNER-ratified)."""
        entry = self._find_skill(skill_id)
        entry.revise("owner confirmed the proposed rule", confidence=0.9)
        entry.content["status"] = "active"
        self.memory.skills.save_all()
        return entry

    def reject(self, skill_id: str, reason: str = "owner rejected the proposed rule") -> None:
        entry = self._find_skill(skill_id)
        entry.revise(reason, confidence=0.05)
        entry.content["status"] = "rejected"
        self.memory.skills.save_all()

    # -- strategy revision (T9) -------------------------------------------

    #: "no, X files go into Y" / "screenshots go into assets/" etc.
    _MAPPING_CORRECTION = re.compile(r"^\s*([\w\-. ]+?)\s+(?:files?\s+)?(?:go|belong|should go|should be moved|move)\s+(?:in|into|to)\s+([\w\-./]+)\s*\.?\s*$", re.IGNORECASE)

    def apply_correction(self, correction_text: str) -> Optional[str]:
        """Revise the latest active skill's mapping from an owner correction.

        Returns the skill id if one was revised (T9: strategy revision, not
        just a fact update).
        """
        match = self._MAPPING_CORRECTION.match(correction_text)
        if not match:
            return None
        raw_kind, destination = match.group(1).strip().lower(), match.group(2)
        extension = raw_kind.lstrip(".") if "." in raw_kind else raw_kind
        skill = self._latest_active_skill()
        if skill is None:
            return None
        old = dict(skill.content["mapping"])
        skill.content["mapping"][extension] = destination
        skill.revise(
            f"owner correction: {extension} → {destination} (was {old.get(extension, 'unset')})",
            confidence=min(0.95, skill.confidence + 0.05),
        )
        self.memory.skills.save_all()
        return skill.id

    # -- T3 self-correction after failure ----------------------------------

    def record_failure(self, skill_id: str, taxonomy: str, fix: str) -> Entry:
        """Log a failure mode + the fix that worked (T3 consolidation)."""
        skill = self._find_skill(skill_id)
        modes = skill.content.setdefault("failure_modes", [])
        if taxonomy not in [m.get("taxonomy") for m in modes]:
            modes.append({"taxonomy": taxonomy, "fix": fix, "count": 1})
        else:
            for mode in modes:
                if mode.get("taxonomy") == taxonomy:
                    mode["count"] = int(mode.get("count", 0)) + 1
                    mode["fix"] = fix
        skill.revise(f"recorded failure mode '{taxonomy}' with fix", confidence=max(0.05, skill.confidence - 0.05))
        self.memory.skills.save_all()
        return skill

    # -- lookup helpers -----------------------------------------------------

    def active_skills(self) -> list[Entry]:
        return self.memory.query(kind="procedural", type="skill", status="active")

    def find_skill_for_goal(self, goal: str) -> Optional[Entry]:
        goal_tokens = set(re.findall(r"[a-z]{3,}", goal.lower()))
        best, best_score = None, 0
        for skill in self.active_skills():
            goal_class = set(str(skill.content.get("goal_class", "")).split())
            score = len(goal_class & goal_tokens)
            if score > best_score:
                best, best_score = skill, score
        return best if best_score > 0 else None

    def _store(self, content: dict[str, Any], confidence: float) -> Entry:
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.PROCEDURAL,
            content=content,
            source=Source.INFERENCE,
            confidence=confidence,
        )
        self.memory.skills.append(entry)
        return entry

    def _find_skill(self, skill_id: str) -> Entry:
        entry = self.memory.find(skill_id)
        if entry is None:
            raise KeyError(f"no such skill record: {skill_id}")
        return entry

    def _latest_active_skill(self) -> Optional[Entry]:
        skills = self.memory.query(kind="procedural", type="skill", status="active")
        return skills[-1] if skills else None
