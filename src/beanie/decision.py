"""The decision gate — how a task is understood before anything is used.

Traceability: ARCHITECTURE §11.1 (the decision gate: every owner request is
classified into a *need* before any capability is chosen — needs first, tools
second, §7), §5 (danger classification feeds the four authority states: a
dangerous need is always a permission question, everything else is answered
autonomously), and §2 (ambiguous routing is substrate-assisted: the deep tier
classifies what the deterministic rules cannot, into the same need vocabulary
— never into a free-form action).

This is the organ the owner identified as the difference between a strong
system and a generic one. Its discipline:

1. **Deterministic first.** Ordinary action phrases (play, find, open,
   install, run, on my phone, go to, learn) are resolved by rules — cheap,
   stable, testable, and their decision trail is exactly citable (§9.9).
2. **Model-assisted for the ambiguous.** When no rule accepts, and a real
   model tier is present, the deep tier classifies into the *same* bounded
   need vocabulary (it chooses a kind, it does not invent actions). Without a
   model tier the gate honestly says "I don't know how yet" and records the
   gap (T5) — it never guesses an executable.
3. **Danger is classified, not felt.** `danger=True` needs (install,
   uninstall, delete, shell, docker run, payments/messages, locking the
   screen…) always go through the authority gate; the rest are answered from
   autonomy. The owner is at the top of the permission chain — a rule the
   owner sets decides, always (§5).

The gate decides *what* and *how dangerous*; the mind decides *whether it may
proceed* (AuthorityGate) and the body decides *how it happens* (§7).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .substrate import Substrate

#: bounded need vocabulary — the deep tier may only choose among these
NEED_KINDS = (
    "play_media",    # play a song/video: index the PC, fall back to streaming
    "search_file",   # find a file and report it
    "open_app",      # launch an application / open a file with its app
    "install_app",   # install software (danger)
    "uninstall_app",  # remove software (danger)
    "shell",         # run an arbitrary command (danger)
    "docker_run",    # run a task in a container sandbox (danger)
    "phone",         # act on the connected Android phone (danger depends on action)
    "web",           # open a URL / search the web
    "learn",         # the task needs new knowledge first (research/watch a video)
    "conversation",  # ordinary talk: no body action implied
    "unknown",       # genuinely cannot classify — the gate says so
)

#: needs that are always dangerous — they change the system or reach out of it
DANGEROUS_NEEDS = {"install_app", "uninstall_app", "shell", "docker_run"}

_OPEN_APP_HINT = re.compile(
    r"^\s*(?:open|launch|start|run|bring up|switch to)\s+(?:the\s+)?(?:app\s+|application\s+)?(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_PLAY_RE = re.compile(
    r"^\s*(?:play|put on|listen to|queue)\s+(?:me\s+|us\s+)?(?:the\s+|a\s+|some\s+)?(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_FIND_RE = re.compile(
    r"^\s*(?:find|search for|search|look for|locate)\s+(?:me\s+)?(?:the\s+|my\s+|a\s+)?(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_INSTALL_RE = re.compile(
    r"^\s*(uninstall|install|remove|get|download|set up)\s+(?:the\s+)?(?:app\s+|application\s+|program\s+)?(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_SHELL_RE = re.compile(
    r"^\s*(?:run|execute)\s+(?:the\s+)?(?:command|shell|terminal)\s*[:\-]?\s+(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_DOCKER_RE = re.compile(
    r"^\s*(?:run|use|spin up|launch)\s+(?:a\s+)?docker(?:\s+container|image)?[\s:]+(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"^\s*(?:on my phone|on the phone|from my phone)\s*[,\-:]?\s*(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_WEB_URL_RE = re.compile(
    r"^\s*(?:go to|open|visit|take me to)\s+((?:https?://)?[\w.-]+\.(?:com|org|net|io|ug|co|tv|app|dev)(?:/\S*)?)\s*\.?\s*$",
    re.IGNORECASE,
)
_WEB_SEARCH_RE = re.compile(
    r"^\s*(?:search (?:the )?(?:web|internet|online)|google|look up online|search online)\s*(?:for)?\s+(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_LEARN_RE = re.compile(
    r"^\s*(?:learn|teach yourself|figure out|study|research|watch videos about|watch a video about|find out how to)\s*(?:how to|about)?\s+(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)

#: words that make even a phone action dangerous (wipe, send money, delete…)
_DANGER_WORDS = {
    "delete", "remove", "wipe", "format", "erase", "uninstall", "install", "send",
    "pay", "buy", "purchase", "transfer", "post", "publish", "share", "factory",
    "reset", "lock", "encrypt", "shutdown", "reboot", "kill",
}


@dataclass
class Need:
    """The gate's verdict for one owner request."""

    kind: str
    target: str = ""                # the thing the task is about ("kaba", "firefox", "https://…")
    danger: bool = False
    needs_learning: bool = False    # true when the mind does not know how — it must learn first
    assisted: bool = False          # true when a model tier did the classification
    reason: str = ""                # one clause: why this kind was chosen (the citable trail)

    @property
    def actionable(self) -> bool:
        """Whether the need implies body action beyond conversation."""
        return self.kind not in ("conversation", "unknown", "learn")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "target": self.target, "danger": self.danger,
            "needs_learning": self.needs_learning, "assisted": self.assisted, "reason": self.reason,
        }


class DecisionGate:
    """Classify owner requests into bounded needs (§11.1)."""

    def __init__(self, substrate: Optional[Substrate] = None) -> None:
        self.substrate = substrate

    # ---------------------------------------------------------------- rules
    def classify(self, text: str) -> Need:
        """Resolve one owner utterance to a need. Deterministic first (§11.1)."""
        stripped = text.strip()

        match = _PLAY_RE.match(stripped)
        if match and _looks_media(stripped):
            return Need("play_media", target=match.group(1),
                        reason="the play verb targets something to hear or watch")

        match = _INSTALL_RE.match(stripped)
        if match:
            verb, target = match.group(1).lower(), match.group(2)
            kind = "uninstall_app" if verb in ("uninstall", "remove") else "install_app"
            return Need(kind, target=target, danger=True,
                        reason=f"'{verb}' changes the system itself — that is always dangerous")

        match = _SHELL_RE.match(stripped)
        if match:
            return Need("shell", target=match.group(1), danger=True,
                        reason="an explicit shell command can do anything — always dangerous")

        match = _DOCKER_RE.match(stripped)
        if match:
            return Need("docker_run", target=match.group(1), danger=True,
                        reason="a container run isolates the task but still executes code")

        match = _PHONE_RE.match(stripped)
        if match:
            action = match.group(1)
            dangerous = bool({t for t in re.findall(r"[a-z]+", action.lower())} & _DANGER_WORDS)
            return Need("phone", target=action, danger=dangerous,
                        reason="the request explicitly targets the connected phone")

        match = _WEB_URL_RE.match(stripped)
        if match:
            return Need("web", target=match.group(1), reason="an explicit site to open")

        match = _WEB_SEARCH_RE.match(stripped)
        if match:
            return Need("web", target=match.group(1),
                        needs_learning=True, reason="an explicit search of the outside world")

        match = _LEARN_RE.match(stripped)
        if match:
            return Need("learn", target=match.group(1), needs_learning=True,
                        reason="the owner asked for something that must be learned first")

        # app-opening only matches when nothing stronger fired and the phrase
        # looks like a bare application command — not conversation words
        match = _OPEN_APP_HINT.match(stripped)
        if match and not _looks_conversational(stripped):
            return Need("open_app", target=match.group(1),
                        reason="an open/launch command aimed at an application")

        match = _FIND_RE.match(stripped)
        if match and _looks_fileish(match.group(1)):
            return Need("search_file", target=match.group(1),
                        reason="a find/search command about something stored on the machine")

        # ordinary talk never pays for a classification (§4.6 — effort is spent
        # where the request is action-shaped, not on greetings and questions)
        if _looks_chatter(stripped):
            return Need("conversation", target=stripped, reason="ordinary conversation, not an action request")

        return self._assist_or_answer(stripped)

    # ------------------------------------------------------------- assisted
    def _assist_or_answer(self, text: str) -> Need:
        """Ambiguous input: let a real model tier classify into the same
        vocabulary, or answer honestly that there is no classification (§11.1)."""
        if self.substrate is None:
            return Need("unknown", target=text, reason="no deterministic rule and no model tier to consult")
        outcome = self.substrate.deep(
            {"user_text": (
                "Classify this owner request into exactly one need kind from: "
                + ", ".join(NEED_KINDS)
                + '. Reply with ONLY JSON: {"kind": "…", "target": "…", "needs_learning": false}. '
                "The target is the thing the task is about, in the owner's words."
                + f"\nREQUEST: {text}"
            )},
            [],
            candidate="classify",
        )
        if not outcome.success:
            return Need("unknown", target=text, reason="the model tier could not classify it either")
        parsed = _parse_json_need(outcome.text)
        if parsed is None or parsed.get("kind") not in NEED_KINDS:
            return Need("unknown", target=text,
                        reason="the model tier's answer was not a valid classification — not guessing")
        need = Need(
            kind=parsed["kind"],
            target=str(parsed.get("target") or text),
            needs_learning=bool(parsed.get("needs_learning")),
            assisted=True,
            reason="the model tier classified the ambiguous request",
        )
        if need.kind in DANGEROUS_NEEDS:
            need.danger = True
        elif need.kind == "phone":
            need.danger = bool({t for t in re.findall(r"[a-z]+", need.target.lower())} & _DANGER_WORDS)
        return need


def _parse_json_need(text: str) -> Optional[dict[str, Any]]:
    """Extract one JSON object from a tier reply; None when it is not a need."""
    try:
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None


_CHATTER_RE = re.compile(
    r"^(?:hi|hii+|hello|hey|yo|good\s+(?:morning|afternoon|evening|night|day)|"
    r"thanks|thank\s+you|okay|ok\b|yes|yeah|no\b|nope|bye|goodbye|see\s+you|"
    r"who|what(?:'s)?|why|how|when|where|which|whose|whom|is|are|am|do|does|did|"
    r"can|could|should|shall|will|would|may|might|tell\s+me|have\s+you)\b",
    re.IGNORECASE,
)


def _looks_chatter(text: str) -> bool:
    """Greetings, questions and small talk are conversation, not action requests."""
    stripped = text.strip()
    if stripped.endswith("?"):
        return True
    return bool(_CHATTER_RE.match(stripped))


def _looks_media(text: str) -> bool:
    """Play+something is media unless the target is clearly an app or URL."""
    lowered = text.lower()
    return not re.search(r"(?:https?://|\.com\b|\.exe\b|chrome|firefox)", lowered)


def _looks_conversational(text: str) -> bool:
    """An 'open' sentence is not an app command when it is clearly speech."""
    return bool(re.search(r"\b(open up|open about|open to me|open the conversation)\b", text.lower()))


def _looks_fileish(target: str) -> bool:
    """'find the protocol' vs 'find my invoice' — file search needs a stored-thing
    reading: an extension, a folder word, or "file" explicitly in the request."""
    tokens = set(re.findall(r"[a-z0-9]+", target.lower()))
    if tokens & {"file", "files", "folder", "document", "song", "video", "photo",
                 "picture", "music", "invoice", "report", "spreadsheet"}:
        return True
    return bool(re.search(r"\.[a-z0-9]{2,5}\b", target.lower()))
