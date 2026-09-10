"""The real-machine body (§7/§11.8, row 44/51): opt-in, honest, plan-first.

Tests run in dry-run mode: they verify *what the body would do* on each
platform without touching any real machine state — the same way the body
answers a permission ask with a preview (§5).
"""

from __future__ import annotations

import pytest

from beanie.body import BodyError, OSBody


@pytest.fixture()
def osbody(monkeypatch):
    monkeypatch.setenv("BEANIE_BODY_OS", "1")
    return OSBody(dry_run=True)


def test_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    with pytest.raises(RuntimeError):
        OSBody(dry_run=True)


def test_openers_per_platform(osbody, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert osbody.run("open_file", {"path": r"C:\songs\kaba.mp3"})["would_run"] \
        == 'cmd /c start \'""\' \'C:\\songs\\kaba.mp3\''
    monkeypatch.setattr("sys.platform", "darwin")
    assert osbody.run("play_media", {"path": "/music/kaba.m4a"})["would_run"] == "open /music/kaba.m4a"
    monkeypatch.setattr("sys.platform", "linux")
    assert osbody.run("play_media", {"path": "/music/kaba.m4a"})["would_run"] == "xdg-open /music/kaba.m4a"


def test_url_gets_a_scheme_and_opener(osbody, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    out = osbody.run("open_url", {"url": "youtube.com/results?search_query=kaba"})
    assert out["would_run"] == "xdg-open 'https://youtube.com/results?search_query=kaba'"


def test_package_managers_per_platform(osbody, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert osbody.run("install_app", {"package": "VideoLAN.VLC"})["would_run"] == \
        "winget install --id VideoLAN.VLC -e"
    monkeypatch.setattr("sys.platform", "darwin")
    assert osbody.run("uninstall_app", {"package": "vlc"})["would_run"] == "brew uninstall vlc"
    monkeypatch.setattr("sys.platform", "linux")
    assert osbody.run("install_app", {"package": "vlc"})["would_run"] == "sudo apt-get install -y vlc"


def test_docker_sandbox_for_os_specific_tasks(osbody, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    out = osbody.run("docker_run", {"image": "python:3.12", "command": "bash -lc 'pytest -q'"})
    assert out["would_run"] == "docker run --rm python:3.12 bash -lc 'pytest -q'"
    plain = osbody.run("docker_run", {"image": "ubuntu:24.04"})
    assert plain["would_run"] == "docker run --rm ubuntu:24.04"


def test_missing_docker_is_an_honest_error_not_a_crash(monkeypatch):
    monkeypatch.setenv("BEANIE_BODY_OS", "1")
    monkeypatch.setattr("shutil.which", lambda name: None)
    body = OSBody(dry_run=False)  # a real run without docker must say so
    with pytest.raises(BodyError) as error:
        body.run("docker_run", {"image": "ubuntu"})
    assert error.value.kind == "missing_tool"
    assert "docker" in str(error.value).lower()


def test_real_local_execution_still_works(monkeypatch):
    """The non-dry path is for real: a harmless echo proves execution passes through."""
    monkeypatch.setenv("BEANIE_BODY_OS", "1")
    body = OSBody(dry_run=False)
    out = body.run("shell", {"command": "echo beanie-os-body"})
    assert out["returncode"] == 0 and "beanie-os-body" in out["stdout"]
