"""The web window (§11.7, row 50): a real conversation over HTTP.

The page is served, dialogue goes through the same Mind.step the CLI uses,
ticks tick, and the state panel reports the mind's real counters — the window
is a second face on one mind, never a parallel fake.
"""

from __future__ import annotations

import http.client
import json
import threading

from beanie import Mind
from beanie.webui import make_server


def _get(client: http.client.HTTPConnection, path: str) -> tuple[int, bytes]:
    client.request("GET", path)
    response = client.getresponse()
    return response.status, response.read()


def _post(client: http.client.HTTPConnection, path: str, payload: dict) -> tuple[int, dict]:
    client.request("POST", path, body=json.dumps(payload),
                   headers={"Content-Type": "application/json"})
    response = client.getresponse()
    return response.status, json.loads(response.read() or b"{}")


def test_the_window_serves_and_converses(tmp_path):
    mind = Mind(state_dir=tmp_path / "state")
    server = make_server(mind, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.address
        client = http.client.HTTPConnection(host, port, timeout=10)

        status, body = _get(client, "/")
        assert status == 200
        page = body.decode()
        assert "Beanie" in page and "speechSynthesis" in page and "mic" in page  # voice both ways is in the glass

        status, reply = _post(client, "/api/step", {"text": "play me kaba"})
        assert status == 200
        assert "kaba" in reply["text"]            # the media path answers genuinely
        assert reply["confidence_label"]          # labels travel to the window
        assert reply["turn_id"].startswith("turn-")

        status, reply = _post(client, "/api/step", {"text": "install obs studio"})
        # system-changing work is classified even with the body off, and honesty
        # (nothing ran, and why) travels over the wire
        assert "permission" in reply["text"]
        assert "Nothing ran" in reply["text"]

        status, state_body = _get(client, "/api/state")
        assert status == 200
        state = json.loads(state_body)
        assert state["episodes"] >= 2
        assert state["pending_permissions"] == 0   # body off → no dangling asks: exactly the truth
        assert "backend" in state

        status, tick = _post(client, "/api/tick", {})
        assert status == 200 and "notes" in tick

        status, explain = _post(client, "/api/explain", {})
        assert status == 200 and explain["explanation"]  # §9 validation over the wire

        status, _ = _get(client, "/definitely-not-a-route")
        assert status == 404
        client.close()
    finally:
        server.shutdown()
        server.server_close()


def test_pending_permission_is_answerable_from_the_window(tmp_path):
    """Dangerous asks are one tap in the window (§11.7/§5): the state payload
    names the capability, and sending the grant sentence through the same mind
    clears it — which is exactly what the page's Allow button does."""
    mind = Mind(state_dir=tmp_path / "state")
    server = make_server(mind, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.address
        client = http.client.HTTPConnection(host, port, timeout=10)

        _post(client, "/api/step", {"text": "You may gui_control"})  # pre-existing rule, keeps churn low
        status, state_body = _get(client, "/api/state")
        pending_before = json.loads(state_body)["pending_permissions"]

        _post(client, "/api/step", {"text": "on my phone, open whatsapp"})  # phone ask (device off): no new ask
        status, state_body = _get(client, "/api/state")
        assert json.loads(state_body)["pending_permissions"] == pending_before

        # a plan wall DOES create a pending ask the window can see and answer
        from beanie.planning import PlanResult
        from beanie.body import BodyError
        result = PlanResult(skill_id="sk", steps=[], outcome="needs_permission")
        result.last_result = {"capability": "open_url"}
        question = mind._note_permission_need("open the dashboard", result)
        assert question
        status, state_body = _get(client, "/api/state")
        state = json.loads(state_body)
        assert any(p["capability"] == "open_url" for p in state["pending"])

        status, reply = _post(client, "/api/step", {"text": "you may open_url"})  # the Allow button's payload
        assert status == 200
        status, state_body = _get(client, "/api/state")
        assert all(p["capability"] != "open_url" for p in json.loads(state_body)["pending"])
        client.close()
    finally:
        server.shutdown()
        server.server_close()


def test_organ_status_is_a_honest_seating_chart(tmp_path, monkeypatch):
    """§11/row 35: what is seated, what is not, and the exact switch for each —
    never a brochure."""
    for var in ("BEANIE_BODY_OS", "BEANIE_AUTOMATION", "BEANIE_ANDROID", "BEANIE_VOICE"):
        monkeypatch.delenv(var, raising=False)
    mind = Mind(state_dir=tmp_path / "state")
    status = mind.organ_status()
    assert set(status) == {"model_tier", "os_body", "gui_control", "android",
                           "voice_speaker", "voice_ears"}
    assert status["model_tier"]["on"] is False
    assert "BEANIE_MODEL_URL" in status["model_tier"]["switch"]
    assert status["os_body"]["on"] is False

    monkeypatch.setenv("BEANIE_BODY_OS", "1")
    mind2 = Mind(state_dir=tmp_path / "state2")
    assert mind2.organ_status()["os_body"]["on"] is True


def test_organ_status_marks_a_configured_but_dead_model_tier_unreachable(tmp_path, monkeypatch):
    """Row 35: seated-but-down is a different problem than not-configured —
    the chart must distinguish them (a staged LM Studio that isn't running is
    the most common first-run trap on the owner's machine)."""
    from beanie.substrate_http import HTTPSubstrate

    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    monkeypatch.delenv("BEANIE_AUTOMATION", raising=False)
    substrate = HTTPSubstrate(base_url="http://127.0.0.1:9")   # nothing can listen there
    mind = Mind(substrate=substrate, state_dir=tmp_path / "state")
    status = mind.organ_status()["model_tier"]
    assert status["on"] is False
    assert "UNREACHABLE" in status["detail"]
    assert "LM Studio" in status["switch"]


def test_organ_status_marks_a_live_model_tier_reachable(tmp_path, monkeypatch):
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from beanie.substrate_http import HTTPSubstrate

    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    monkeypatch.delenv("BEANIE_AUTOMATION", raising=False)

    class _Models(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = _json.dumps({"data": [{"id": "local-model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Models)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        substrate = HTTPSubstrate(base_url=f"http://127.0.0.1:{server.server_address[1]}")
        mind = Mind(substrate=substrate, state_dir=tmp_path / "state")
        status = mind.organ_status()["model_tier"]
        assert status["on"] is True
        assert "reachable" in status["detail"]
    finally:
        server.shutdown()
        server.server_close()


def test_state_endpoint_carries_the_day_digest_and_live_queue(tmp_path, monkeypatch):
    """§11.7/§5: the window shows the overseer the same record the
    conversation answers from — today counted from the trace, the live queue
    itemised (asks with grant sentences, paused/parked work)."""
    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    mind = Mind(state_dir=tmp_path / "state")
    server = make_server(mind, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.address
        client = http.client.HTTPConnection(host, port, timeout=10)
        _post(client, "/api/step", {"text": "hello there"})       # produce a day
        from beanie.planning import PlanResult
        result = PlanResult(skill_id="sk", steps=[], outcome="needs_permission")
        result.last_result = {"capability": "open_url"}
        assert mind._note_permission_need("open the dashboard", result)

        status, state_body = _get(client, "/api/state")
        state = json.loads(state_body)
        assert state["today"]["events"] >= 1
        assert state["today"]["date"][:4].isdigit() and "-" in state["today"]["date"]
        asks = [item for item in state["queue"] if item["kind"] == "permission_ask"]
        assert any(item["capability"] == "open_url" and "you may open_url" in " ".join(
            [item.get("grant", "")]) for item in asks)
        client.close()
    finally:
        server.shutdown()
        server.server_close()


def test_probe_timeout_is_env_configurable_and_slow_but_live_is_not_dead(tmp_path, monkeypatch):
    """Row 35 honesty extends to LAN latency: a slow-but-live server reported
    as dead would be a lie dressed as diagnostics, so the timeout is a
    documented switch (BEANIE_MODEL_PROBE_TIMEOUT)."""
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from beanie.substrate_http import HTTPSubstrate
    from beanie.mind import _probe_model_endpoint

    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    monkeypatch.delenv("BEANIE_AUTOMATION", raising=False)

    class _SlowModels(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            time.sleep(0.35)
            body = b'{"data": []}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowModels)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        assert _probe_model_endpoint(url, timeout=0.05) is False      # too-tight: times out
        assert _probe_model_endpoint(url, timeout=2.0) is True        # enough budget: live
        monkeypatch.setenv("BEANIE_MODEL_PROBE_TIMEOUT", "2.0")
        mind = Mind(substrate=HTTPSubstrate(base_url=url), state_dir=tmp_path / "state")
        assert mind.organ_status()["model_tier"]["on"] is True        # env respected
    finally:
        server.shutdown()
        server.server_close()


def test_step_error_is_an_honest_500_and_the_window_survives(tmp_path, monkeypatch):
    """§11.7: a mind that throws must not kill the phone's window — the answer
    is a JSON failure carrying the real exception, and the server answers the
    very next request."""
    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)

    class _Exploding(Mind):
        def step(self, text):  # only this utterance explodes
            if "boom" in text:
                raise RuntimeError("planted failure for the honest-500 test")
            return super().step(text)

    mind = _Exploding(state_dir=tmp_path / "state")
    server = make_server(mind, host="127.0.0.1", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        host, port = server.address
        client = http.client.HTTPConnection(host, port, timeout=10)
        client.request("POST", "/api/step", body=json.dumps({"text": "make it boom"}),
                       headers={"Content-Type": "application/json"})
        response = client.getresponse()
        raw = response.read().decode()
        assert response.status == 500
        payload = json.loads(raw)
        assert "RuntimeError" in payload["text"] and "planted failure" in payload["text"]
        status, body2 = _post(client, "/api/step", {"text": "hello there"})   # window survives
        assert status == 200
        assert "Received: hello there." in json.dumps(body2) if not isinstance(body2, str)             else "Received: hello there." in body2
        status, state = _get(client, "/api/state")
        assert status == 200
        client.close()
    finally:
        server.shutdown()
        server.server_close()


def test_busy_port_is_a_guided_exit_not_a_traceback(tmp_path, capfd, monkeypatch):
    """§11.7 first-run hygiene: port-in-use says 'close the old window or pass
    --port', exits non-zero, and never dumps a stack at the owner."""
    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    import socket as _socket

    holder = _socket.socket()
    holder.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    taken = holder.getsockname()[1]
    try:
        import pytest

        with pytest.raises(SystemExit) as exit_info:
            from beanie.webui import main as webui_main
            webui_main(["--state-dir", str(tmp_path / "state"),
                        "--host", "127.0.0.1", "--port", str(taken)])
        assert exit_info.value.code == 3
        out = capfd.readouterr().out
        assert "cannot open the window" in out
        assert "--port" in out
        assert "Traceback" not in (out + capfd.readouterr().err)
    finally:
        holder.close()
