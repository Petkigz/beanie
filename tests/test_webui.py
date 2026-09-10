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
