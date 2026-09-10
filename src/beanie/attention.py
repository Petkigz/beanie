"""Attention — novelty over observed streams (continuous cognition, §4.2).

Traceability: ARCHITECTURE §4.2 (novelty in an observed stream → attention,
optional episode — there is no "exist → think" idle loop; continuous
cognition is event-driven) and Stage 4 (attention/novelty over observed
streams). The detector diffs snapshots of the body's tree and reports
add/change/remove events so Mind.observe() can record perception episodes
(source PERCEPTION) and check intentions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


class NoveltyDetector:
    """Diff-based attention over a watched body state (§4.2)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._last: Optional[dict[str, str]] = None

    def snapshot(self) -> dict[str, str]:
        tree: dict[str, str] = {}
        if self.root.exists():
            for path in sorted(self.root.rglob("*")):
                if path.is_file():
                    rel = str(path.relative_to(self.root))
                    try:
                        tree[rel] = path.read_text(encoding="utf-8", errors="replace")[:200]
                    except OSError:
                        tree[rel] = "<unreadable>"
        return tree

    def reset(self) -> None:
        self._last = self.snapshot()

    def diff(self) -> list[dict[str, Any]]:
        """Events since the last diff: add | change | remove."""
        current = self.snapshot()
        events: list[dict[str, Any]] = []
        if self._last is None:  # first observation establishes the baseline
            self._last = current
            return events
        for path, text in current.items():
            if path not in self._last:
                events.append({"path": path, "kind": "add"})
            elif self._last[path] != text:
                events.append({"path": path, "kind": "change"})
        for path in self._last:
            if path not in current:
                events.append({"path": path, "kind": "remove"})
        self._last = current
        return events
