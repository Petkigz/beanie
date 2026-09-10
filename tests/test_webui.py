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
