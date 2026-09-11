"""The resume ritual's safety-critical branches (rollback hygiene playbook).

The sandbox has reset the working branch mid-project six times; scripts/resume.sh
now owns the recovery. These tests build disposable git worlds proving the two
branches that must NEVER misfire: (1) local strictly behind origin = the
rollback signature → the script synchronises forward; (2) true divergence =
local commits origin lacks → the script REFUSES, because a blind hard reset
would burn real work. Neither test touches the project repo.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)


def _mk_world(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A bare origin, a seed commit, and a working clone with resume.sh copied in."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    origin.mkdir()
    seed.mkdir()
    _git(["init", "--bare", str(origin)], tmp_path)
    _git(["init", str(seed)], tmp_path)
    _git(["-C", str(seed).replace(str(tmp_path), str(tmp_path)), "config", "user.email", "t@t"], tmp_path) if False else None
    subprocess.run(["git", "-C", str(seed), "config", "user.email", "ritual@test"], check=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.name", "Ritual"], check=True)
    (seed / "file.txt").write_text("v1\n")
    _git(["add", "-A"], seed)
    _git(["commit", "-m", "seed"], seed)
    _git(["branch", "-M", "arena"], seed)
    _git(["remote", "add", "origin", str(origin)], seed)
    _git(["push", "-q", "-u", "origin", "arena"], seed)

    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.email", "ritual@test"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "Ritual"], check=True)
    subprocess.run(["git", "-C", str(work), "checkout", "-q", "arena"], check=True)
    (work / "scripts").mkdir()
    shutil.copy(REPO_ROOT / "scripts" / "resume.sh", work / "scripts" / "resume.sh")
    return origin, seed, work


def _run_script(work: Path) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "RESUME_SKIP_VERIFY": "1", "LC_ALL": "C"}
    return subprocess.run(["bash", "scripts/resume.sh"], cwd=work, env=env,
                          capture_output=True, text=True)


def test_rollback_signature_syncs_forward_and_clears_phantoms(tmp_path):
    origin, seed, work = _mk_world(tmp_path)
    # origin moves ahead (the sandbox pushed more work), local stays behind
    (seed / "file.txt").write_text("v2\n")
    _git(["commit", "-qam", "origin work"], seed)
    _git(["push", "-q"], seed)
    # and the phantom signature: a dirty working tree behind HEAD
    (work / "file.txt").write_text("phantom modification\n")
    base = _git(["rev-parse", "HEAD"], work).stdout.strip()
    ahead = _git(["rev-parse", "origin/HEAD"] if False else ["ls-remote", "origin", "arena"], seed)

    result = _run_script(work)
    assert result.returncode == 0, result.stderr
    assert "strictly behind" in result.stdout
    assert _git(["rev-parse", "HEAD"], work).stdout.strip() != base
    assert (work / "file.txt").read_text() == "v2\n"          # phantoms cleared
    assert "skipped" in result.stdout


def test_true_divergence_refuses_and_preserves_local_work(tmp_path):
    origin, seed, work = _mk_world(tmp_path)
    (work / "local.txt").write_text("real uncommitted-in-origin work\n")
    _git(["add", "local.txt"], work)
    _git(["commit", "-qm", "local ahead"], work)

    result = _run_script(work)
    assert result.returncode == 3
    assert "true divergence" in result.stderr.lower()
    assert (work / "local.txt").exists()                      # nothing burned
    assert _git(["log", "--oneline", "-1"], work).stdout.startswith(
        _git(["rev-parse", "--short", "HEAD"], work).stdout.strip())
