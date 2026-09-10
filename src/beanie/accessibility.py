"""Accessibility eyes — the desktop UI tree as real screen text (§11.3, row 47).

Traceability: ARCHITECTURE §11.3 (screen text is the navigator's input) and
the owner's brief ("know where to click"). Pixels need a vision model; the
desktop's *accessibility tree* does not. Windows (UI Automation), macOS
(AXUIElement) and Linux (AT-SPI) all publish the same thing to assistive
technology: every visible control with a **name, a role and a bounding box**.
That is text with coordinates — the honest way to click "the Login button"
without guessing a pixel.

Structure: a `backend` enumerates `UIElement`s; `read_screen` formats them as
bounded text for the navigator's propose action; `ATGUIDriver` resolves a
named target to the element's center *at click time* (the tree is re-read —
screens move). `ScriptBackend` is the deterministic double tests use; the real
backends (`atspi`, `pywinauto`/UIA) are imported lazily and their absence is
an `unavailable_reason`, never a crash. Actions that find no element are
`target_not_found` — nothing is ever clicked blindly.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Optional, Protocol

from .body import BodyError

#: the screen digest never drowns the loop (§4.2 boundedness)
MAX_SCREEN_ELEMENTS = 80


@dataclass
class UIElement:
    name: str
    role: str
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def line(self) -> str:
        cx, cy = self.center
        return f"{self.role} '{self.name}' at ({cx}, {cy})"


class AccessibilityBackend(Protocol):
    """One way of enumerating the current screen's elements."""

    def elements(self) -> list[UIElement]: ...


class ScriptBackend:
    """Deterministic double: the 'tree' is a staged list (tests, demos)."""

    def __init__(self, elements: list[UIElement]) -> None:
        self._elements = list(elements)

    def elements(self) -> list[UIElement]:
        return list(self._elements)


class ATSPIBackend:
    """Linux AT-SPI: the real tree, when the library and a session exist."""

    def __init__(self) -> None:
        import pyatspi  # type: ignore  # noqa: F401 — presence is the gate

        self._atspi = pyatspi

    def elements(self) -> list[UIElement]:
        from pyatspi import Registry  # type: ignore

        found: list[UIElement] = []
        registry = getattr(self._atspi, "Registry", Registry)
        desktop = registry.getDesktop(0)
        walker = getattr(self._atspi, "utils", None)
        for app_index in range(desktop.childCount):
            app = desktop.getChildAtIndex(app_index)
            stack = [app]
            while stack and len(found) < 500:
                node = stack.pop()
                try:
                    name = node.name or ""
                    role = node.getRoleName() or ""
                    extents = node.queryComponent().getExtents(1) if node.queryComponent() else None
                    if name and extents and extents.width > 0 and extents.height > 0:
                        found.append(UIElement(name=name, role=role, x=extents.x, y=extents.y,
                                               width=extents.width, height=extents.height))
                    for child_index in range(node.childCount):
                        stack.append(node.getChildAtIndex(child_index))
                except Exception:
                    continue
        return found


class UIABackend:
    """Windows UI Automation through pywinauto, lazily imported."""

    def __init__(self) -> None:
        from pywinauto import Desktop  # type: ignore  # noqa: F401

        self._desktop_cls = Desktop

    def elements(self) -> list[UIElement]:
        found: list[UIElement] = []
        desktop = self._desktop_cls(backend="uia")
        for window in desktop.windows():
            try:
                for control in window.descendants():
                    try:
                        name = control.window_text() or ""
                        rect = control.rectangle()
                        width = rect.right - rect.left
                        height = rect.bottom - rect.top
                        if name and width > 0 and height > 0:
                            found.append(UIElement(
                                name=name, role=str(control.friendly_class_name()).lower(),
                                x=rect.left, y=rect.top, width=width, height=height,
                            ))
                    except Exception:
                        continue
            except Exception:
                continue
            if len(found) >= 500:
                break
        return found


def platform_backend() -> tuple[Optional[AccessibilityBackend], str]:
    """The real backend for this platform, or (None, honest reason)."""
    try:
        if sys.platform.startswith("linux"):
            return ATSPIBackend(), ""
        if sys.platform.startswith("win"):
            return UIABackend(), ""
        return None, (f"no accessibility backend implemented for {sys.platform} "
                      "(macOS AX is the declared gap)")
    except ImportError as exc:
        missing = str(exc).split("named")[-1].strip().strip("'") or str(exc)
        return None, f"accessibility library missing ({missing}) — see the switch to seat it"


class PlatformATDriver:
    """Read the screen as named, coordinate text for the navigator."""

    name = "accessibility"

    def __init__(
        self,
        backend: Optional[AccessibilityBackend] = None,
        unavailable_reason: str = "",
    ) -> None:
        if backend is None and not unavailable_reason:
            backend, unavailable_reason = platform_backend()
        self.backend = backend
        self.unavailable_reason = unavailable_reason

    @property
    def available(self) -> bool:
        return self.backend is not None

    def read_screen(self, limit: int = MAX_SCREEN_ELEMENTS) -> str:
        if self.backend is None:
            raise BodyError(f"screen reading not available ({self.unavailable_reason})",
                            kind="no_screen_reader")
        lines = [element.line() for element in self.backend.elements() if element.name.strip()]
        lines = [line for line in lines if line]
        if len(lines) > limit:
            lines = lines[:limit] + [f"… (+{len(lines) - limit} more elements — the loop stays bounded)"]
        return "\n".join(lines) or "(screen tree is empty)"

    def find(self, name: str) -> Optional[UIElement]:
        """Resolve a *named* target to its element. Misses are honest None."""
        if self.backend is None:
            return None
        wanted = name.strip().lower()
        if not wanted:
            return None
        best: tuple[float, Optional[UIElement]] = (0.0, None)
        for element in self.backend.elements():
            candidate = element.name.strip().lower()
            if not candidate:
                continue
            if wanted in candidate or candidate in wanted:
                score = 0.9 + min(len(wanted), len(candidate)) / 100.0
            else:
                score = SequenceMatcher(None, wanted, candidate).ratio() * 0.85
            if score > best[0]:
                best = (score, element)
        return best[1] if best[0] >= 0.6 else None


class ATGUIDriver:
    """A navigator-ready limb that clicks *named* targets at real coordinates."""

    name = "accessibility+pointer"
    action_types = ("click", "type", "key", "wait", "done", "fail")

    def __init__(
        self,
        backend: Optional[AccessibilityBackend] = None,
        motion: Optional[Any] = None,
    ) -> None:
        self.eyes = PlatformATDriver(backend=backend)
        if motion is None:
            from .automation import PyAutoGUIDriver

            motion = PyAutoGUIDriver()  # real pointer (opt-in), or see default_driver below
        self.motion = motion
        self.backend = backend or self.eyes.backend

    def read_screen(self) -> str:
        return self.eyes.read_screen()

    def _require_element(self, target: str) -> UIElement:
        element = self.eyes.find(target)
        if element is None:
            raise BodyError(f"no on-screen element named like '{target}'",
                            kind="target_not_found")
        return element

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        kind = action.get("type")
        if kind == "click" and action.get("target"):
            element = self._require_element(str(action["target"]))
            x, y = element.center
            self.motion.click(x, y)
            return {"performed": "click", "target": element.name, "at": [x, y]}
        if kind == "type":
            if action.get("target"):
                element = self._require_element(str(action["target"]))
                x, y = element.center
                self.motion.click(x, y)  # focus the field first, like a person would
            self.motion.typewrite(str(action.get("text", "")))
            return {"performed": "type"}
        if kind == "key":
            self.motion.press(str(action.get("key", "")))
            return {"performed": "key"}
        if kind == "wait":
            import time

            time.sleep(min(float(action.get("ms", 500)) / 1000.0, 5.0))
            return {"performed": "wait"}
        raise BodyError(f"cannot execute GUI action of type {kind!r}", kind="bad_action")
