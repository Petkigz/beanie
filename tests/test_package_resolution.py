"""Install precisely (§11.4, row 46): resolve the real package id before asking.

"install obs studio" is not a command — it is a lookup. The body searches the
platform's package manager, presents what actually exists, and the permission
ask names the exact id the command will install. Parsers are exercised against
real manager output formats; the flow runs on a recording fake body.
"""

from __future__ import annotations

import pytest

from beanie.body import OSBody, parse_apt_results, parse_brew_results, parse_winget_results

WINGET_OUT = """Name                Id                      Version     Match        Source
-----------------------------------------------------------------------------
OBS Studio          OBSProject.OBSStudio    31.0.2                  winget
OBS Virtual Camera  OBSProject.OBSVirtualcam 2.0.5                 winget
"""

APT_OUT = """obs-studio/x11 29.0.2 amd64
  recorder and streamer for live video content

kamoso/jammy 21.12.3 amd64
  tool to take pictures and videos from your webcam
"""

BREW_BLOCK = """obs
obs-virtualcam
obsidian
"""


def test_winget_parser_takes_the_id_column():
    found = parse_winget_results(WINGET_OUT)
    assert found[0]["id"] == "OBSProject.OBSStudio"
    assert "OBS Studio" in found[0]["label"]
    assert len(found) == 2


def test_apt_parser_prefers_binary_family_lines():
    found = parse_apt_results(APT_OUT)
    assert found[0]["id"] == "obs-studio"
    assert any("recorder" in entry["label"].lower() for entry in found)


def test_brew_parser_lists_formulae():
    found = parse_brew_results(BREW_BLOCK)
    assert [entry["id"] for entry in found] == ["obs", "obs-virtualcam", "obsidian"]


def test_search_package_dispatches_per_platform(monkeypatch):
    monkeypatch.setenv("BEANIE_BODY_OS", "1")
    body = OSBody(dry_run=True)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(body, "_probe_output",
                        lambda cmd: APT_OUT if "apt-cache" in " ".join(cmd) else "")
    found = body.search_package("obs studio")
    assert found[0]["id"] == "obs-studio"


class _SearchableBody:
    """Recording fake: the search answers, the install is recorded."""

    def __init__(self, results):
        self.results = results
        self.calls: list[tuple[str, dict]] = []

    def search_package(self, target: str):
        return self.results

    def run(self, capability: str, args=None):
        self.calls.append((capability, dict(args or {})))
        return {"returncode": 0, "stdout": "installed", "stderr": ""}


def test_install_flow_resolves_the_id_and_names_alternatives(tmp_path, monkeypatch):
    from beanie import Mind

    monkeypatch.setenv("BEANIE_BODY_OS", "1")
    mind = Mind(state_dir=tmp_path / "state", authority="allow")
    fake = _SearchableBody([
        {"id": "OBSProject.OBSStudio", "label": "OBS Studio"},
        {"id": "OBSProject.OBSVirtualcam", "label": "OBS Virtual Camera"},
    ])
    mind._osbody, mind._osbody_probed = fake, True

    reply = mind.step("install obs studio")
    assert fake.calls and fake.calls[0][0] == "install_app"
    assert fake.calls[0][1]["package"] == "OBSProject.OBSStudio"   # the resolved id, not the wording
    assert "OBSProject.OBSVirtualcam" in reply.text                # alternatives are surfaced, not hidden


def test_install_flow_with_no_match_says_so_never_installs_anything(tmp_path, monkeypatch):
    from beanie import Mind

    monkeypatch.setenv("BEANIE_BODY_OS", "1")
    mind = Mind(state_dir=tmp_path / "state", authority="allow")
    fake = _SearchableBody([])                       # manager answers nothing
    mind._osbody, mind._osbody_probed = fake, True

    reply = mind.step("install zzz blorple")
    assert "no package matched" in reply.text.lower() or "nothing matched" in reply.text.lower()
    assert fake.calls == []   # nothing invented, nothing installed
