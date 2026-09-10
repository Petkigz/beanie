"""The real-model seam (§2): HTTPSubstrate exercised against a local mock.

No external calls: a tiny OpenAI-compatible server runs on 127.0.0.1 so the
adapter's request shape, error handling and the loop's behavior on top of a
real tier are all covered before an endpoint is ever configured.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from beanie import Mind
from beanie.substrate_http import FAST_CONFIDENCE, HTTPSubstrate

REPLY = "Here is a considered answer."


class _MockModel(BaseHTTPRequestHandler):
    """Minimal /chat/completions endpoint that records what it received."""

    requests: list[dict] = []
    fail_next = False
    reply_text = REPLY

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if type(self).fail_next:
            type(self).fail_next = False
            self.send_response(502)
            self.end_headers()
            self.wfile.write(b"upstream broke")
            return
        payload = json.dumps({"choices": [{"message": {"content": type(self).reply_text}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:  # keep test output clean
        pass


@pytest.fixture()
def mock_model():
    class _Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True
        block_on_close = False  # serve_forever's poll interval must not slow teardown

    server = _Server(("127.0.0.1", 0), _MockModel)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    _MockModel.requests = []
    _MockModel.fail_next = False
    _MockModel.reply_text = REPLY
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", _MockModel
    finally:
        server.shutdown()
        server.server_close()


def test_requires_configuration(monkeypatch):
    for name in ("BEANIE_MODEL_URL", "BEANIE_MODEL_NAME", "BEANIE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError) as error:
        HTTPSubstrate()
    assert "BEANIE_MODEL_URL" in str(error.value)  # says exactly what is missing

    monkeypatch.setenv("BEANIE_MODEL_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("BEANIE_MODEL_NAME", "mock-model")
    monkeypatch.setenv("BEANIE_API_KEY", "test-key")
    substrate = HTTPSubstrate()  # environment configuration works
    assert substrate.model == "mock-model" and substrate.fast_model == "mock-model"


def test_reads_configuration_from_the_environment(monkeypatch, mock_model):
    base_url, mock = mock_model
    monkeypatch.setenv("BEANIE_MODEL_URL", base_url)
    monkeypatch.setenv("BEANIE_MODEL_NAME", "mock-model")
    monkeypatch.setenv("BEANIE_API_KEY", "secret-key")
    substrate = HTTPSubstrate()
    assert substrate.fast({"user_text": "hello"}, []) == REPLY
    sent = mock.requests[-1]
    assert sent["path"] == "/v1/chat/completions"   # OpenAI-compatible path
    assert sent["auth"] == "Bearer secret-key"
    assert sent["body"]["model"] == "mock-model"
    assert sent["body"]["messages"][-1]["content"] == "hello"


def test_deep_tier_sees_the_system_1_candidate(mock_model):
    """Dual-process contract (§2): the deep tier verifies or overrules the candidate."""
    base_url, mock = mock_model
    substrate = HTTPSubstrate(base_url=base_url, model="m", api_key="k")
    outcome = substrate.deep({"user_text": "do the thing"}, [], candidate="gut says yes")
    assert outcome.success and outcome.text == REPLY
    contents = [message["content"] for message in mock.requests[-1]["body"]["messages"]]
    assert any("gut says yes" in content for content in contents)


def test_context_is_included_and_bounded(mock_model):
    base_url, mock = mock_model
    substrate = HTTPSubstrate(base_url=base_url, model="m", api_key="k")
    context = [{"role": "user", "text": f"turn {n}"} for n in range(20)]
    substrate.deep({"user_text": "now"}, context, candidate="")
    messages = mock.requests[-1]["body"]["messages"]
    assert any("turn 19" in m["content"] for m in messages)   # recent context kept
    assert not any("turn 0" in m["content"] for m in messages)  # window bounded (§3.1)
    assert messages[-1]["content"] == "now"


def test_low_confidence_wording_maps_to_an_honest_outcome(mock_model):
    base_url, mock = mock_model
    substrate = HTTPSubstrate(base_url=base_url, model="m", api_key="k")
    mock.reply_text = "That request is ambiguous — please clarify."
    outcome = substrate.deep({"user_text": "vague"}, [], candidate="")
    assert not outcome.success
    assert outcome.failure.value == "prompt_ambiguity"
    assert outcome.confidence < 0.5

    mock.reply_text = REPLY
    assert substrate.deep({"user_text": "clear"}, [], candidate="").failure.value == "none"


def test_unreachable_endpoint_is_reported_honestly(mock_model):
    base_url, mock = mock_model
    substrate = HTTPSubstrate(base_url=base_url, model="m", api_key="k")

    # fast tier: flags low confidence so the loop escalates instead of answering
    mock.fail_next = True
    flagged = substrate.fast({"user_text": "hello"}, [])
    assert flagged.startswith("fast: low-confidence")

    # deep tier: a failure outcome with the root cause and no invented answer
    mock.fail_next = True
    outcome = substrate.deep({"user_text": "hello"}, [], candidate="")
    assert not outcome.success
    assert outcome.failure.value == "tool_execution_error"
    assert outcome.confidence <= 0.1
    assert "unreachable" in outcome.text

    unreachable = HTTPSubstrate(base_url="http://127.0.0.1:9/v1", model="m", api_key="k")
    assert unreachable.fast({"user_text": "hi"}, []).startswith("fast: low-confidence")


def test_loop_runs_on_a_real_tier(mock_model, tmp_path):
    """A configured endpoint drives the whole loop: reflex turns use the fast tier
    alone, and a hedged fast answer escalates without paying for it twice."""
    base_url, mock = mock_model
    substrate = HTTPSubstrate(base_url=base_url, model="m", api_key="k")
    mind = Mind(substrate=substrate, state_dir=tmp_path / "mind")

    reply = mind.step("hi there")                 # reflex: fast tier alone
    assert reply.text == REPLY
    assert reply.confidence_label == "moderate"   # FAST_CONFIDENCE is honestly moderate
    assert len(mock.requests) == 1                # one call, no deep wake-up

    mock.reply_text = "That is unclear to me."    # the gut answer hedges
    escalated = mind.step("ok")
    assert escalated.confidence < 0.5             # the deep verdict governs the label
    assert not escalated.success
    # exactly three calls: reflex, flagged reflex, deep — the flag is not re-bought
    assert len(mock.requests) == 3
    assert "System-2" in mock.requests[-1]["body"]["messages"][0]["content"]
    decisions = [e for e in mind.trace.events if e.kind == "decision"]
    assert decisions[-1].payload["depth"] == "deep"
    assert decisions[-1].payload["escalated_from"] == "reflex"


def test_suite_runs_against_a_real_tier_and_is_attributed(mock_model, tmp_path):
    """--substrate http drives the suite, and the run records which tier produced it."""
    import json

    from beanie.measure import run_suite

    base_url, mock = mock_model
    monkeypatch_substrate = HTTPSubstrate(base_url=base_url, model="m", api_key="k")
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "one.json").write_text(json.dumps({
        "id": "one", "description": "",
        # the mock answers "Here is a considered answer."; the stub answers "Received: hello."
        "turns": [{"user": "hello", "expect": "considered"}],
    }), encoding="utf-8")
    track = tmp_path / "track"

    # run_suite builds its own substrate per scenario; point it at the mock
    import beanie.measure as measure
    original = measure.make_substrate
    measure.make_substrate = lambda kind: (HTTPSubstrate(base_url=base_url, model="m", api_key="k")
                                           if kind == "http" else original(kind))
    try:
        assert run_suite(suite_dir, tmp_path / "s1", track_dir=track, substrate_kind="http") == 0
        assert run_suite(suite_dir, tmp_path / "s2", track_dir=track, substrate_kind="stub") == 1
    finally:
        measure.make_substrate = original

    archived = sorted(p for p in track.glob("*.json") if not p.name.endswith(("register.json", "scores.json")))
    first = json.loads(archived[0].read_text(encoding="utf-8"))
    second = json.loads(archived[1].read_text(encoding="utf-8"))
    assert first[0]["substrate"] == "http"
    assert second[0]["substrate"] == "stub"


def test_local_server_needs_no_api_key_and_model_defaults(monkeypatch, mock_model):
    """LM Studio style: no key, one loaded model — the adapter must just work."""
    base_url, mock = mock_model
    for name in ("BEANIE_MODEL_NAME", "BEANIE_API_KEY", "BEANIE_MODEL_FAST_NAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BEANIE_MODEL_URL", base_url)
    substrate = HTTPSubstrate()  # no key configured at all
    assert substrate.model == "local-model"
    assert substrate.fast({"user_text": "hello"}, []) == REPLY
    assert mock.requests[-1]["auth"] is None  # no header sent when no key is set


def test_fast_model_env_selects_the_system_1_model(monkeypatch, mock_model):
    base_url, mock = mock_model
    monkeypatch.setenv("BEANIE_MODEL_URL", base_url)
    monkeypatch.setenv("BEANIE_MODEL_NAME", "deep-model")
    monkeypatch.setenv("BEANIE_MODEL_FAST_NAME", "fast-model")
    substrate = HTTPSubstrate()
    assert substrate.fast_model == "fast-model"
    substrate.fast({"user_text": "hello"}, [])
    assert mock.requests[-1]["body"]["model"] == "fast-model"
    substrate.deep({"user_text": "hello"}, [], "candidate")
    assert mock.requests[-1]["body"]["model"] == "deep-model"


def test_gui_action_proposal_parses_one_bounded_action(monkeypatch, mock_model):
    """§11.3: the vision/navigation proposal must be one JSON action or an
    honest None — never a half-parsed guess the navigator would execute."""
    base_url, mock = mock_model
    monkeypatch.setenv("BEANIE_MODEL_URL", base_url)
    substrate = HTTPSubstrate()

    mock.reply_text = '{"type": "click", "target": "Files", "reason": "open the file manager"}'
    action = substrate.propose_next_action("open the file manager", "Desktop: [Files] [Trash]", [])
    assert action == {"type": "click", "target": "Files", "reason": "open the file manager"}

    mock.reply_text = "I would probably click somewhere near the top left."
    assert substrate.propose_next_action("open the file manager", "Desktop", []) is None

    mock.reply_text = REPLY
