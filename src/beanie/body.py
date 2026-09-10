"""Embodiment — capabilities (the body) and authority (permission gate).

Traceability: ARCHITECTURE §7 (tools are the body: capability interface with
senses and effects; the mind discovers capabilities by need) and §5 (the
four authority states: I can / I am allowed / I need permission / I don't
know — agency with authority, never fake-crippled intelligence).

SandboxBody is a real, safe body over a virtual file tree rooted in the mind's
state directory — it is the environment demonstrations and plans act on in
tests and demos. OSBody (real process execution) exists behind the same
capability interface and is only constructed when BEANIE_BODY_OS=1 and the
permission gate allows — never by default, never in tests.

Authority rules persist in the owner model store (content type "rule":
capability glob → allow | ask | deny), each with provenance and confidence
(§5 bullet 1). The gate's check() returns one of the four states so the mind
can phrase exactly what it needs.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .records import DecayProfile, Entry, EvidenceRef, RecordKind, Source, Volatility
from .stores import Memory


class BodyError(Exception):
    """A capability failed; taxonomy tags the failure (Q28 tool execution)."""

    def __init__(self, message: str, taxonomy: str = "tool_execution_error", kind: str = "") -> None:
        super().__init__(message)
        self.taxonomy = taxonomy
        self.kind = kind


# --------------------------------------------------------------------------
# Sandbox body
# --------------------------------------------------------------------------

def _safe(root: Path, target: str) -> Path:
    """Resolve a path inside the sandbox root; refuse escapes (no jailbreak)."""
    candidate = (root / target).resolve()
    root_resolved = root.resolve()
    if not (candidate == root_resolved or root_resolved in candidate.parents):
        raise BodyError(f"path escapes sandbox: {target}", kind="path_escape")
    return candidate


class SandboxBody:
    """A safe virtual file body for demonstrations and plans (§7)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def capabilities(self) -> dict[str, str]:
        return {
            "list_files": "senses the files in a directory",
            "read_file": "senses a file's text content",
            "write_file": "creates/overwrites a text file",
            "mkdir": "creates a directory",
            "move_file": "moves a file into a directory",
            "delete_file": "deletes a file",
            "snapshot": "senses the whole tree (state for verify)",
        }

    def run(self, capability: str, args: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        handler: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = getattr(self, f"_op_{capability}", None)
        if handler is None:
            raise BodyError(f"unknown capability: {capability}", kind="unknown_capability")
        try:
            return handler(args or {})
        except BodyError:
            raise
        except OSError as exc:
            raise BodyError(f"{capability} failed: {exc}", kind="os_error") from exc

    def _op_list_files(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _safe(self.root, str(args.get("dir", ".")))
        if not path.exists():
            raise BodyError(f"no such directory: {args.get('dir')}", kind="missing_source")
        files = sorted(p.name for p in path.iterdir())
        return {"dir": str(args.get("dir")), "files": files}

    def _op_read_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _safe(self.root, str(args["path"]))
        if not path.is_file():
            raise BodyError(f"no such file: {args['path']}", kind="missing_source")
        return {"path": str(args["path"]), "text": path.read_text(encoding="utf-8", errors="replace")}

    def _op_write_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _safe(self.root, str(args["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(args.get("text", "")), encoding="utf-8")
        return {"path": str(args["path"]), "wrote": True}

    def _op_mkdir(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _safe(self.root, str(args["dir"]))
        path.mkdir(parents=True, exist_ok=True)
        return {"dir": str(args["dir"]), "created": True}

    def _op_move_file(self, args: dict[str, Any]) -> dict[str, Any]:
        src = _safe(self.root, str(args["src"]))
        dst = _safe(self.root, str(args["dst"]))
        if not src.is_file():
            raise BodyError(f"no such file: {args['src']}", kind="missing_source")
        if not dst.exists():
            raise BodyError(f"destination missing: {args['dst']}", kind="missing_destination")
        if not dst.is_dir():
            raise BodyError(f"destination not a directory: {args['dst']}", kind="bad_destination")
        shutil.move(str(src), str(dst / src.name))
        return {"src": str(args["src"]), "dst": str(args["dst"])}

    def _op_delete_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _safe(self.root, str(args["path"]))
        if path.is_file():
            path.unlink()
            return {"path": str(args["path"]), "deleted": True}
        raise BodyError(f"no such file: {args['path']}", kind="missing_source")

    def _op_snapshot(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        tree: dict[str, Any] = {}
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                rel = str(path.relative_to(self.root))
                tree[rel] = path.read_text(encoding="utf-8", errors="replace")[:200]
        return {"tree": tree}


# --------------------------------------------------------------------------
# Real OS body (opt-in only)
# --------------------------------------------------------------------------

def parse_winget_results(output: str) -> list[dict[str, str]]:
    """winget search output → [{id, label}] — the machine id, not the wording."""
    found: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip() or line.lstrip().startswith(("-", "Name")):
            continue
        parts = line.split()
        if len(parts) >= 3 and "." in parts[-3] if False else False:
            pass
        # heuristics: the id is a token containing a dot; the label is what precedes it
        tokens = line.split()
        for index, token in enumerate(tokens):
            if "." in token and not token.startswith(".") and any(ch.isalpha() for ch in token):
                if index == 0:
                    continue
                label = " ".join(tokens[:index])
                if label:
                    found.append({"id": token, "label": label})
                break
    return found


def parse_apt_results(output: str) -> list[dict[str, str]]:
    """apt-cache search output: 'pkg/suite version arch' + indented description."""
    found: list[dict[str, str]] = []
    pending: dict[str, str] = {}
    for line in output.splitlines():
        if line and not line[0].isspace() and "/" in line:
            if pending:
                found.append(pending)
            package = line.split("/", 1)[0].strip()
            pending = {"id": package, "label": package}
        elif pending and line.strip():
            pending["label"] = f"{pending['id']} — {line.strip()}"
        elif not line.strip() and pending:
            found.append(pending)
            pending = {}
    if pending:
        found.append(pending)
    return found


def parse_brew_results(output: str) -> list[dict[str, str]]:
    """brew search: plain name-per-line."""
    return [{"id": name.strip(), "label": name.strip()}
            for name in output.splitlines() if name.strip()]


class OSBody:
    """Real-machine body — constructed only when BEANIE_BODY_OS=1 (§7, §9.5, §11.4).

    The capability surface of a real PC: shell, plus the §11.4 senses and hands —
    open files/apps with their default application, open URLs in the default
    browser, play media, install/uninstall software, and run tasks inside a
    Docker sandbox when a job wants another OS or an isolated room.

    `dry_run=True` (or BEANIE_BODY_DRYRUN=1) turns every action into the honest
    plan for it ("would run: …") — used by previews, permission asks and tests.
    """

    def __init__(self, cwd: Optional[str] = None, dry_run: Optional[bool] = None) -> None:
        if os.environ.get("BEANIE_BODY_OS") != "1":
            raise RuntimeError("OSBody requires BEANIE_BODY_OS=1 (real OS actions are opt-in by design)")
        self.cwd = Path(cwd or os.getcwd())
        self.dry_run = (
            dry_run if dry_run is not None else os.environ.get("BEANIE_BODY_DRYRUN") == "1"
        )

    @property
    def capabilities(self) -> dict[str, str]:
        return {
            "shell": "runs a shell command in the owner's environment",
            "open_file": "opens a file with the system's default application",
            "open_url": "opens a URL in the default browser",
            "play_media": "plays a media file with the system's default player",
            "open_app": "launches an application by name",
            "install_app": "installs software with the OS package manager (dangerous)",
            "uninstall_app": "removes software with the OS package manager (dangerous)",
            "docker_run": "runs a task inside a docker container sandbox (dangerous)",
        }

    # -- command builders (pure: testable without touching the machine) ----

    def _platform(self) -> str:
        name = sys.platform.lower()
        if name.startswith("win"):
            return "windows"
        if name == "darwin":
            return "macos"
        return "linux"

    def _package_manager(self, action: str, package: str) -> list[str]:
        """Install/uninstall command for the current platform (§11.4)."""
        if action == "install":
            return {
                "windows": ["winget", "install", "--id", package, "-e"],
                "macos": ["brew", "install", package],
                "linux": ["sudo", "apt-get", "install", "-y", package],
            }[self._platform()]
        return {
            "windows": ["winget", "uninstall", "--id", package, "-e"],
            "macos": ["brew", "uninstall", package],
            "linux": ["sudo", "apt-get", "remove", "-y", package],
        }[self._platform()]

    def _probe_output(self, command: list[str]) -> str:
        """Read-only probe (package search): never in dry-run output, never mutating."""
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)  # noqa: S603
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout if result.returncode == 0 else ""

    def search_package(self, query: str) -> list[dict[str, str]]:
        """Resolve a wording to real package ids before anything installs (§11.4).

        Read-only: searches are how the owner sees what WOULD be installed —
        winget/brew/apt-cache output parsed to [{id, label}], first [0..5].
        A manager that answers nothing yields an honest empty list.
        """
        platform = self._platform()
        if platform == "windows":
            raw = self._probe_output(["winget", "search", "--accept-source-agreements", query])
            return parse_winget_results(raw)[:6]
        if platform == "macos":
            raw = self._probe_output(["brew", "search", f"/{query.split()[0]}/i"])
            return parse_brew_results(raw)[:6]
        raw = self._probe_output(["apt-cache", "search", "--names-only", query.split()[0]])
        if not raw:
            # names-only narrows too hard with spaces; plain search is the fallback
            raw = self._probe_output(["apt-cache", "search", query])
        return parse_apt_results(raw)[:6]

    def _open_command(self, target: str, *, url: bool = False) -> list[str]:
        """Open a file/URL with the system default handler (the OS picks the app)."""
        if self._platform() == "windows":
            return ["cmd", "/c", "start", '""', target]
        if self._platform() == "macos":
            return ["open", target]
        return ["xdg-open", target]

    def _docker_command(self, image: str, command: str = "") -> list[str]:
        cmd = ["docker", "run", "--rm"]
        if command:
            cmd += [image] + shlex.split(command)
        else:
            cmd += [image]
        return cmd

    # -- execution --------------------------------------------------------

    def _execute(self, command: list[str], *, detach: bool, timeout: int) -> dict[str, Any]:
        """Run one action, or return the honest plan for it in dry-run."""
        pretty = shlex.join(command)
        if self.dry_run:
            return {"dry_run": True, "would_run": pretty}
        if detach:
            subprocess.Popen(command, cwd=self.cwd,  # noqa: S603 — explicit opt-in body
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"detached": True, "ran": pretty}
        result = subprocess.run(  # noqa: S603 — explicit opt-in body
            command, cwd=self.cwd, capture_output=True, text=True, timeout=timeout
        )
        return {"returncode": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-2000:]}

    def run(self, capability: str, args: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        handler: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = getattr(self, f"_op_{capability}", None)
        if handler is None:
            raise BodyError(f"unknown capability: {capability}", kind="unknown_capability")
        try:
            return handler(args or {})
        except BodyError:
            raise
        except OSError as exc:
            raise BodyError(f"{capability} failed: {exc}", kind="os_error") from exc

    def _op_shell(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._execute(shlex.split(str(args["command"])), detach=False,
                             timeout=int(args.get("timeout", 30)))

    def _op_open_file(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._execute(self._open_command(str(args["path"])), detach=True,
                             timeout=int(args.get("timeout", 30)))

    def _op_open_url(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args["url"])
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return self._execute(self._open_command(url, url=True), detach=True,
                             timeout=int(args.get("timeout", 30)))

    def _op_play_media(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._execute(self._open_command(str(args["path"])), detach=True,
                             timeout=int(args.get("timeout", 30)))

    def _op_install_app(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._execute(self._package_manager("install", str(args["package"])), detach=False,
                             timeout=int(args.get("timeout", 600)))

    def _op_uninstall_app(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._execute(self._package_manager("uninstall", str(args["package"])), detach=False,
                             timeout=int(args.get("timeout", 600)))

    def _op_open_app(self, args: dict[str, Any]) -> dict[str, Any]:
        """Launch an application by name, platform-natively (§11.8)."""
        app = str(args["app"])
        if self._platform() == "windows":
            command = ["cmd", "/c", "start", '""', app]
        elif self._platform() == "macos":
            command = ["open", "-a", app]
        else:
            command = [app]
        return self._execute(command, detach=True, timeout=int(args.get("timeout", 30)))

    def _op_docker_run(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.dry_run and shutil.which("docker") is None:
            raise BodyError("docker is not installed or not on PATH", kind="missing_tool")
        return self._execute(
            self._docker_command(str(args["image"]), str(args.get("command", ""))),
            detach=False, timeout=int(args.get("timeout", 300)),
        )


# --------------------------------------------------------------------------
# Authority gate (§5)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Permission:
    state: str          # act | need_permission | not_allowed | unknown
    phrase: str         # which of the four states the mind can communicate
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.state == "act"


class AuthorityGate:
    """Four-state permission gate over capabilities (§5)."""

    def __init__(self, memory: Memory, default: str = "ask") -> None:
        self.memory = memory
        self.default = default  # ask | allow (auto, demo/test only) | deny

    def rules(self) -> list[Entry]:
        return self.memory.query(kind="owner_model", type="rule")

    def check(self, capability: str) -> Permission:
        rule = self._matching_rule(capability)
        if rule is not None:
            action = str(rule.content.get("action"))
            if action == "allow":
                return Permission("act", "I can do this.", f"rule {rule.id}")
            if action == "deny":
                return Permission("not_allowed", "I am not allowed to do this.", f"rule {rule.id}")
            return Permission("need_permission", "I need your permission before doing this.", f"rule {rule.id}")
        if self.default == "allow":
            return Permission("act", "I can do this.", "default allow (demo/test policy)")
        if self.default == "deny":
            return Permission("not_allowed", "I am not allowed to do this.", "default deny")
        return Permission("unknown", "I don't know whether I'm allowed to do this.", "no rule on record")

    def grant(self, capability: str, action: str = "allow", note: str = "owner granted") -> Entry:
        """Persist an authority rule with provenance (§5)."""
        existing = self._matching_rule(capability)
        if existing is not None:
            existing.revise(f"{note}: {capability} → {action}", confidence=0.95)
            existing.content["action"] = action
            self.memory.owner_model.save_all()
            return existing
        entry = Entry(
            id=self.memory.allocate_id(),
            kind=RecordKind.OWNER_MODEL,
            content={"type": "rule", "capability": capability, "action": action, "note": note},
            source=Source.OWNER,
            confidence=0.95,
            decay_profile=DecayProfile(volatility=Volatility.LOW),
        )
        self.memory.owner_model.append(entry)
        return entry

    def _matching_rule(self, capability: str) -> Optional[Entry]:
        for rule in reversed(self.rules()):
            pattern = str(rule.content.get("capability", "*"))
            if pattern == "*" or pattern == capability:
                return rule
        return None


#: owner statement patterns → authority rules ("you may …", "never …")
_RULE_PATTERNS = [
    (re.compile(r"^\s*you\s+may\s+(?:always\s+)?(?:use\s+)?([a-z_]+)\s*\.?\s*$", re.IGNORECASE), "allow"),
    (re.compile(r"^\s*never\s+(?:use\s+)?([a-z_]+)\s*\.?\s*$", re.IGNORECASE), "deny"),
    (re.compile(r"^\s*you\s+(?:may|can)\s+([a-z_]+)\s+if\s+I\s+approve\s*\.?\s*$", re.IGNORECASE), "ask"),
]


def parse_authority_statement(text: str) -> Optional[tuple[str, str]]:
    """Return (capability, action) for an owner authority statement, if any."""
    for pattern, action in _RULE_PATTERNS:
        match = pattern.match(text)
        if match:
            return match.group(1).lower(), action
    return None
