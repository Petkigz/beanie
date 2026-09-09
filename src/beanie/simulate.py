"""Simulation — a working model of the body to test actions before acting.

Traceability: Domain A / register rows 10–11 (counterfactual replay: mentally
re-run a sequence with a changed variable and predict the outcome without a
simulator *for text* — but for the sandbox body we build the simulator), and
ARCHITECTURE §7 (verify before act) + §2.10 grounding. The mind does not need
to touch its body to know what *would* happen: it replays the plan against a
virtual tree loaded from the real one, and the real body is never modified by
prediction.

What-if questions ("what if I moved X to Y") and goal prediction
("predict_goal") both run here. Predictions mirror the executor's repair
semantics (a missing destination is reported as "would be created first"),
so predicted outcomes and real outcomes agree by construction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .body import BodyError, SandboxBody
from .stores import Memory

_MOVE_RE = re.compile(
    r"^\s*what\s+(?:would\s+happen\s+)?if\s+i\s+(?:moved|move|were to move)\s+"
    r"(?P<name>[\w.\- ]+?)\s+(?:from\s+[\w./\-]+\s+)?(?:to|into)\s+(?P<dst>[\w.\-]+?)\s*\??\s*$",
    re.IGNORECASE,
)


@dataclass
class Prediction:
    ok: bool
    summary: str
    moved: list[str] = None  # type: ignore[assignment]
    failure: Optional[str] = None
    created_dirs: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.moved is None:
            self.moved = []
        if self.created_dirs is None:
            self.created_dirs = []


class Simulator:
    """Virtual replay of body operations over a loaded tree model."""

    def __init__(self, body: SandboxBody) -> None:
        self.body = body

    # -- model loading ------------------------------------------------------

    def _load_tree(self) -> dict[str, str]:
        """A virtual copy of the body's current tree: files with content and
        every real directory (empty dirs carry no file in the snapshot, so
        they must be seeded for existence checks to match reality)."""
        tree = dict(self.body.run("snapshot").get("tree", {}))
        root = self.body.root
        for path in root.rglob("*"):
            if path.is_dir():
                rel = str(path.relative_to(root))
                tree.setdefault(rel, "")
        return tree

    @staticmethod
    def _simulate_move(tree: dict[str, str], src: str, dst: str) -> tuple[bool, Optional[str]]:
        if src not in tree:
            return False, "missing_source"
        if dst not in tree:
            return False, "missing_destination"
        name = Path(src).name
        target = f"{dst.rstrip('/')}/{name}"
        if dst + "/" in src or target == src:
            return False, "self_move"
        tree[target] = tree.pop(src)
        return True, None

    # -- goal prediction ----------------------------------------------------

    def predict_goal(self, mapping: dict[str, str], base_dir: str, ) -> Prediction:
        """Replay a skill's mapping against the current tree; body untouched.

        Mirrors the executor's repair rule: a missing destination folder would
        be created before the move, so the prediction reports it as such.
        """
        tree = self._load_tree()
        moved: list[str] = []
        created: list[str] = []
        try:
            listing = self.body.run("list_files", {"dir": base_dir})
        except BodyError as exc:
            return Prediction(ok=False, summary=f"cannot predict: {exc.kind}", failure=exc.kind)
        for name in listing.get("files", []):
            ext = Path(name).suffix.lower().lstrip(".")
            dst = mapping.get(ext)
            if dst is None:
                continue
            src = f"{base_dir}/{name}"
            if src not in tree:
                continue
            if dst.rstrip("/") not in tree:
                created.append(dst.rstrip("/"))
                tree[dst.rstrip("/")] = ""  # folder would be created first
            ok, failure = self._simulate_move(tree, src, dst)
            if not ok:
                return Prediction(ok=False, summary=f"predicted failure: {failure} on {name}", failure=failure)
            moved.append(f"{dst.rstrip('/')}/{name}")
        summary = f"{len(moved)} file(s) would be moved" + (f"; {len(created)} folder(s) created first" if created else "")
        return Prediction(ok=True, summary=summary, moved=moved, created_dirs=created)

    # -- what-if ------------------------------------------------------------

    def predict_move(self, file_name: str, dst: str) -> Prediction:
        """What would happen if `file_name` were moved into directory `dst`."""
        tree = self._load_tree()
        src = next((path for path in tree if Path(path).name == file_name), None)
        if src is None:
            return Prediction(ok=False, summary=f"no file named '{file_name}' exists in my sandbox right now.",
                              failure="missing_source")
        if dst.rstrip("/") not in tree:
            return Prediction(
                ok=False,
                summary=f"'{file_name}' would not move there — folder '{dst}' does not exist yet (I could create it first).",
                failure="missing_destination",
            )
        ok, failure = self._simulate_move(tree, src, dst)
        if not ok:
            return Prediction(ok=False, summary=f"that move would fail ({failure}).", failure=failure)
        return Prediction(
            ok=True,
            summary=f"'{file_name}' would move from {src} to {dst}/ — nothing else would change.",
            moved=[f"{dst.rstrip('/')}/{file_name}"],
        )


def parse_what_if(text: str) -> Optional[tuple[str, str]]:
    """Parse a "what if I moved X to Y" question into (file, destination)."""
    match = _MOVE_RE.match(text)
    if not match:
        return None
    return match.group("name").strip(), match.group("dst").strip()
