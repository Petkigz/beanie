"""Drift guard: every module must cite the spec section it implements.

Traceability: ARCHITECTURE.md closes with the rule — "every file, module, and
prompt added to this repository must be traceable to a store, a behavior, or
a tested property in this document — or it must change this document first."
This test is the mechanical enforcement of that rule: code that appears
without a spec citation fails the build, so the implementation cannot quietly
grow into something different from the founding documents.
"""

import pathlib

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
