"""The decision gate (§11.1, row 46): every request classified before any tool.

The gate decides *what* the need is and *how dangerous* it is. Deterministic
rules handle ordinary phrases; a model tier classifies ambiguous requests into
the same bounded vocabulary; danger words always end up at the authority gate.
"""

from __future__ import annotations

from beanie.decision import DecisionGate
from beanie.substrate import Outcome, StubSubstrate


class _ClassifyingSubstrate(StubSubstrate):
    """A stub that answers the gate's classification prompt with JSON."""

    def __init__(self, reply: str, success: bool = True) -> None:
        super().__init__()
        self.reply = reply
        self.reply_success = success

    def deep(self, observation, context, candidate):
        return Outcome(text=self.reply, success=self.reply_success)


def test_media_play_requests(tmp_path):
    gate = DecisionGate()
    need = gate.classify("play me kaba")
    assert need.kind == "play_media" and need.target == "kaba" and not need.danger
    need = gate.classify("play the Ssebo video")
    assert need.kind == "play_media" and need.target == "Ssebo video"
    need = gate.classify("put on some music")
    assert need.kind == "play_media"


def test_danger_is_classified_never_guessed(tmp_path):
    gate = DecisionGate()
    assert gate.classify("install obs studio").danger is True
    assert gate.classify("install obs studio").kind == "install_app"
    need = gate.classify("uninstall whatsapp from my pc")
    assert need.kind == "uninstall_app" and need.danger is True
    need = gate.classify("run command: rm -rf /tmp/x")
    assert need.kind == "shell" and need.danger is True
    need = gate.classify("run a docker container python:3.12 bash -lc 'pytest'")
    assert need.kind == "docker_run" and need.danger is True
    # phone: benign reading vs dangerous action
    assert gate.classify("on my phone, open whatsapp").danger is False
    assert gate.classify("on my phone, delete my photos").danger is True


def test_open_find_web_needs(tmp_path):
    gate = DecisionGate()
    need = gate.classify("open firefox")
    assert need.kind == "open_app" and need.target == "firefox" and not need.danger
    need = gate.classify("find my invoice file")
    assert need.kind == "search_file" and "invoice" in need.target
    need = gate.classify("find the report named final.pdf")
    assert need.kind == "search_file"
    need = gate.classify("go to youtube.com")
    assert need.kind == "web" and not need.needs_learning
    need = gate.classify("google how minecraft nether portals work")
    assert need.kind == "web" and need.needs_learning  # research: knowledge first
    need = gate.classify("learn how to edit videos in openshot")
    assert need.kind == "learn" and need.needs_learning


def test_conversation_is_not_routed_to_the_body(tmp_path):
    gate = DecisionGate()
    assert gate.classify("hello beanie, good morning").kind != "open_app"
    assert gate.classify("open up about your day").kind != "open_app"


def test_ambiguous_request_falls_to_the_model_tier(tmp_path):
    """Assisting is the whole point (row 46): the tier picks a *kind*, never an action."""
    json_reply = '{"kind": "play_media", "target": "kaba by kapeke"}'
    gate = DecisionGate(substrate=_ClassifyingSubstrate(json_reply))
    need = gate.classify("I really want to hear that new kapeke single right now")
    assert need.kind == "play_media" and need.target == "kaba by kapeke" and need.assisted

    # contradictory fabric: a JSON kind the vocabulary does not contain → honest unknown
    gate = DecisionGate(substrate=_ClassifyingSubstrate('{"kind": "conjure_fire", "target": "x"}'))
    need = gate.classify("something something")
    assert need.kind == "unknown"

    # an unreachable/broken tier must not be disguised as a classification
    gate = DecisionGate(substrate=_ClassifyingSubstrate("error", success=False))
    assert gate.classify("unparseable words here").kind == "unknown"


def test_without_any_tier_ambiguity_is_honest_unknown():
    gate = DecisionGate()
    need = gate.classify("◉ the quick brown misphrased frobnicate")
    assert need.kind == "unknown" and not need.actionable
