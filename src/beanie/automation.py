"""GUI automation — seeing the screen and acting on it (§11.3, row 47).

Traceability: ARCHITECTURE §11.3 (eyes-and-hands: the screen is sensed, one
bounded action is proposed by the navigation tier, executed through the
authority gate, and the result is sensed again — a bounded loop, never a
runaway), §5 (every action passes the four-state gate; unknown permission is
an ask, not a click), §7 (drivers are interchangeable limbs: the navigator
logic never changes, the limb underneath does).

Two drivers ship:

* ``VirtualGUIDriver`` — a deterministic test double: the "screen" is scripted
  lines of text, actions are recorded, and nothing on a real machine moves.
  This is what tests and demos run against.
* ``PyAutoGUIDriver`` — real screen control (opt-in ``BEANIE_AUTOMATION=1``,
  needs ``pyautogui``). Screen *reading* is separate from clicking: pixels go
  to the model tier (§11.3) via ``import pyautogui`` screenshots when a
  vision-capable substrate is configured.

The navigator's honesty rules, which protect the owner's machine:
  * one proposed action per step, named by its visible target;
  * a tier that gives no action means "unplannable" — reported, never guessed;
  * a budget caps every navigation (default 8 actions) — bounded cognition (§4.2);
  * each action is gated (§5): "I don't know if I'm allowed" stops the loop
    with the permission question attached.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .body import AuthorityGate, BodyError

#: bounded action vocabulary (mirrors Substrate.propose_next_action)
ACTION_TYPES = ("click", "type", "key", "wait", "done", "fail")


@dataclass
class NavStep:
    action: dict[str, Any]
    note: str = ""


@dataclass
class NavReport:
    outcome: str            # completed | failed | unplannable | budget | needs_permission
    goal: str
    steps: list[NavStep] = field(default_factory=list)
    note: str = ""
    permission_question: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "goal": self.goal,
            "steps": [{"action": s.action, "note": s.note} for s in self.steps],
            "note": self.note,
            "permission_question": self.permission_question,
        }


class VirtualGUIDriver:
    """Deterministic screen double for tests (no machine is ever touched)."""

    name = "virtual"
    has_screen = True

    def __init__(self, screens: Optional[list[str]] = None) -> None:
        self.screens = list(screens or [""])
        self.executed: list[dict[str, Any]] = []
        self._screen_index = 0

    def read_screen(self) -> str:
        screen = self.screens[min(self._screen_index, len(self.screens) - 1)]
        if self._screen_index < len(self.screens) - 1:
            self._screen_index += 1
        return screen

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        self.executed.append(action)
        return {"performed": action.get("type"), "on": action.get("target", "")}


class PyAutoGUIDriver:
    """Real screen control through pyautogui — opt-in only (§11.3)."""

    name = "pyautogui"
    has_screen = False  # pixel sensing needs the vision tier (§2), not OCR claims

    def __init__(self) -> None:
        if os.environ.get("BEANIE_AUTOMATION") != "1":
            raise RuntimeError("PyAutoGUIDriver requires BEANIE_AUTOMATION=1 (screen control is opt-in)")
        try:
            import pyautogui  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("PyAutoGUIDriver needs 'pyautogui' installed in the environment") from exc
        self._gui = pyautogui

    def read_screen(self) -> str:
        """Honest: pixels are not text — the vision tier reads screenshots."""
        raise BodyError(
            "no accessibility/screen reader configured — use the model tier with screenshots",
            kind="no_screen_reader",
        )

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        kind = action.get("type")
        if kind == "click":
            x, y = int(action.get("x", 0)), int(action.get("y", 0))
            self._gui.click(x, y)
            return {"performed": "click", "at": [x, y]}
        if kind == "type":
            self._gui.typewrite(str(action.get("text", "")), interval=0.02)
            return {"performed": "type"}
        if kind == "key":
            self._gui.press(str(action.get("key", "")))
            return {"performed": "key"}
        if kind == "wait":
            import time

            time.sleep(min(float(action.get("ms", 500)) / 1000.0, 5.0))
            return {"performed": "wait"}
        raise BodyError(f"cannot execute GUI action of type {kind!r}", kind="bad_action")


class Navigator:
    """The bounded navigation loop: sense → propose → gate → act → sense (§11.3)."""

    def __init__(
        self,
        driver: Any,
        substrate: Any,
        gate: Optional[AuthorityGate] = None,
        *,
        max_actions: int = 8,
    ) -> None:
        self.driver = driver
        self.substrate = substrate
        self.gate = gate
        self.max_actions = max_actions

    def run(self, goal: str) -> NavReport:
        history: list[dict[str, Any]] = []
        report = NavReport(outcome="failed", goal=goal)
        for _ in range(self.max_actions):
            try:
                screen = self.driver.read_screen()
            except BodyError as exc:
                report.outcome = "unplannable"
                report.note = f"cannot read the screen: {exc}"
                return report
            if self.gate is not None:
                permission = self.gate.check("gui_control")
                if not permission.allowed:
                    report.outcome = "needs_permission"
                    report.note = permission.phrase
                    report.permission_question = (
                        f"To operate the screen I need permission for gui_control — say "
                        f"'you may gui_control' to allow it, or 'never use gui_control' to rule it out."
                    )
                    return report
            action = self.substrate.propose_next_action(goal, screen, history)
            if action is None:
                report.outcome = "unplannable"
                report.note = ("the navigation tier proposed no action — I say so instead of "
                               "guessing where to click")
                return report
            kind = action.get("type")
            if kind == "done":
                report.outcome = "completed"
                report.note = str(action.get("reason", "goal reached"))
                return report
            if kind == "fail":
                report.outcome = "failed"
                report.note = str(action.get("reason", "the tier reported this screen cannot reach the goal"))
                return report
            vocabulary = getattr(self.driver, "action_types", ACTION_TYPES)
            if kind not in vocabulary:
                report.outcome = "unplannable"
                report.note = f"the tier proposed an out-of-vocabulary action {kind!r} — refused"
                return report
            try:
                result = self.driver.execute(action)
            except BodyError as exc:
                report.outcome = "failed"
                report.note = f"the limb failed: {exc}"
                return report
            note = str(action.get("reason", ""))
            history.append({"type": kind, "target": action.get("target", ""), "note": note})
            report.steps.append(NavStep(action=action, note=str(result)))
        report.outcome = "budget"
        report.note = f"out of budget after {self.max_actions} actions — paused, not abandoned"
        return report


def default_driver() -> Any:
    """The driver's sensible default: the real limb when the owner opts in,
    the virtual limb otherwise — same interface either way."""
    if os.environ.get("BEANIE_AUTOMATION") == "1":
        try:
            return PyAutoGUIDriver()
        except RuntimeError:
            return VirtualGUIDriver()
    return VirtualGUIDriver()
