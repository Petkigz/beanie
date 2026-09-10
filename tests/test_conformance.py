"""Drift guard: every module must cite the spec section it implements.

Traceability: ARCHITECTURE.md closes with the rule — "every file, module, and
prompt added to this repository must be traceable to a store, a behavior, or
a tested property in this document — or it must change this document first."
This test is the mechanical enforcement of that rule: code that appears
without a spec citation fails the build, so the implementation cannot quietly
grow into something different from the founding documents.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "beanie"


def test_every_module_cites_its_spec_section():
    missing = []
    for path in sorted({p for p in PKG.rglob("*.py")}):
        text = path.read_text(encoding="utf-8")
        # docstring is the first triple-quoted block
        start = text.find('"""')
        if start == -1:
            missing.append((str(path.relative_to(ROOT)), "no docstring"))
            continue
        end = text.find('"""', start + 3)
        docstring = text[start + 3 : end] if end != -1 else ""
        if "ARCHITECTURE §" not in docstring:
            missing.append((str(path.relative_to(ROOT)), "no 'ARCHITECTURE §' citation in docstring"))
    assert not missing, "\n".join(f"{p}: {why}" for p, why in missing)


def test_docs_reference_each_other():
    """The three founding docs must stay linked (no orphaned canon)."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for doc in ("VISION.md", "ARCHITECTURE.md", "CAPABILITY_REGISTER.md"):
        assert doc in readme, f"README.md no longer links {doc}"
    for doc in ("VISION.md", "ARCHITECTURE.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert "CAPABILITY_REGISTER.md" in text, f"{doc} lost its link to the register"


def _scorecard_rows() -> list[tuple[str, str]]:
    """(row-spec, verdict) pairs from the mechanism scorecard table."""
    text = (ROOT / "CAPABILITY_REGISTER.md").read_text(encoding="utf-8")
    _, _, scorecard = text.partition("## Mechanism scorecard")
    rows: list[tuple[str, str]] = []
    for line in scorecard.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].startswith("Row") or set(cells[0]) <= {"-", " "}:
            continue
        rows.append((cells[0], cells[1]))
    return rows


def _covered_numbers(rows) -> set[int]:
    """Capability rows 1–42 covered by the scorecard's row specs."""
    covered: set[int] = set()
    for spec, _ in rows:
        for part in spec.split(","):
            part = part.strip().lstrip("#")
            if "–" in part:
                low, high = (int(piece.strip()) for piece in part.split("–"))
                covered.update(range(low, high + 1))
            elif part.isdigit():
                covered.add(int(part))
    return covered


def test_scorecard_has_no_contradictory_duplicates():
    """The scorecard must state each register row exactly once (no stale lines)."""
    rows = _scorecard_rows()
    seen: set[str] = set()
    for spec, verdict in rows:
        for part in spec.split(","):
            key = part.strip().lstrip("#")
            assert key not in seen, f"scorecard repeats {part}: also stated as {verdict!r}"
            seen.add(key)
    missing = sorted(set(range(1, 43)) - _covered_numbers(rows))
    assert not missing, f"scorecard is missing rows: {', '.join(map(str, missing))}"


def test_scorecard_suite_count_matches_reality():
    """If the scorecard names a suite size, it must equal the shipped tasks."""
    text = (ROOT / "CAPABILITY_REGISTER.md").read_text(encoding="utf-8")
    match = re.search(r"(\d+) multi-turn tasks", text)
    if match is None:
        return  # wording changed; the size claim simply is not present
    actual = len(list((ROOT / "suites").glob("*.json")))
    assert int(match.group(1)) == actual, (
        f"scorecard says {match.group(1)} tasks, suites/ holds {actual}"
    )
