"""The CLI is a window into the loop (§8 Stage 0) — including the idle budget."""

from beanie.cli import main


def test_cli_say_and_tick(tmp_path, capsys):
    state = tmp_path / "mind"
    assert main(["--state-dir", str(state), "--say", "hello there"]) == 0
    assert "Received: hello there." in capsys.readouterr().out

    # an unresolved request opens a gap; the idle budget investigates it
    assert main(["--state-dir", str(state), "--say", "the context is missing here"]) == 0
    capsys.readouterr()
    assert main(["--state-dir", str(state), "--tick", "1"]) == 0
    out = capsys.readouterr().out
    assert "curiosity:" in out
    assert "no evidence in the sandbox" in out


def test_cli_rating_flows_through(tmp_path, capsys):
    state = tmp_path / "mind"
    main(["--state-dir", str(state), "--say", "hello there"])
    capsys.readouterr()
    assert main(["--state-dir", str(state), "--say", "that was useful"]) == 0
    assert "rated 5/5" in capsys.readouterr().out


def test_repl_speak_flag_is_honest_when_the_speaker_is_not_seated(tmp_path, capsys, monkeypatch):
    """§11.6: --speak says so when no engine exists, and replies continue as text."""
    monkeypatch.delenv("BEANIE_VOICE", raising=False)
    monkeypatch.setattr("shutil.which", lambda _name: None)  # no espeak/spd-say anywhere
    state = tmp_path / "mind"

    prompts = iter(["hello there"])

    def fake_input(_prompt=""):
        try:
            return next(prompts)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)
    rc = main(["--state-dir", str(state), "--speak"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "speaker not seated" in out          # the honest line, once, at seating time
    assert "Received: hello there." in out      # and text output was never muted


def test_say_and_speak_speaks_once_or_says_so_honestly(tmp_path, capsys, monkeypatch):
    """§11.6: one-shot mode honours --speak too — silence would be a broken
    promise at the flag level (the silent dev-null is the REPL asymmetrically
    superset problem)."""
    monkeypatch.delenv("BEANIE_VOICE", raising=False)
    monkeypatch.setattr("shutil.which", lambda _name: None)  # engine absent on this box
    state = tmp_path / "mind"
    assert main(["--state-dir", str(state), "--say", "hello there", "--speak"]) == 0
    out = capsys.readouterr().out
    assert "Received: hello there." in out
    assert "speaker not seated" in out      # the honest line, one time, not silent, not spammed


def test_check_model_reports_reachable_and_ok_against_a_stub_server(tmp_path, capsys, monkeypatch):
    """The owner's second onboarding instrument (after --status): --check-model
    must prove both tiers against a REAL endpoint, with exit 0 only when both answer."""
    import json as _json
    import threading as _threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Chat(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            body = _json.dumps({"choices": [{"message": {"content": "pong"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Chat)
    _threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("BEANIE_MODEL_URL", f"http://127.0.0.1:{server.server_address[1]}")
        from beanie.cli import main as cli_main
        rc = cli_main(["--state-dir", str(tmp_path / "s1"), "--check-model"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Fast tier: ok" in out and "Deep tier: ok" in out

        monkeypatch.setenv("BEANIE_MODEL_URL", "http://127.0.0.1:9")   # nothing lives there
        rc = cli_main(["--state-dir", str(tmp_path / "s2"), "--check-model"])
        assert rc == 1                                                   # down is a red, not a crash
        out = capsys.readouterr().out
        assert "unreachable" in out.lower()
    finally:
        server.shutdown()
        server.server_close()


def test_transcribe_flag_is_honest_without_an_engine_and_speaks_with_one(tmp_path, capsys, monkeypatch):
    """§11.6: the ear-check must never fake a transcript. No engine → red +
    the seat-it line naming the checked engines. With an engine (mocked at the
    Voice seam, as no real model ships in this sandbox) → the transcript."""
    state = tmp_path / "mind"
    (tmp_path / "clip.wav").write_bytes(b"fake-audio")

    import beanie.voice as voice_mod
    monkeypatch.setattr(voice_mod.Voice, "transcription_engine", lambda self: None)
    rc = main(["--state-dir", str(state), "--transcribe", str(tmp_path / "clip.wav")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "no transcription engine" in out and "faster-whisper" in out and "ears are unseated" in out

    monkeypatch.setattr(voice_mod.Voice, "transcription_engine", lambda self: "faster_whisper")
    from beanie.voice import VoiceResult
    monkeypatch.setattr(voice_mod.Voice, "transcribe",
                        lambda self, path: VoiceResult(True, "transcribed", "hello computer"))
    rc = main(["--state-dir", str(state), "--transcribe", str(tmp_path / "clip.wav")])
    assert rc == 0
    assert "hello computer" in capsys.readouterr().out

    rc = main(["--state-dir", str(state), "--transcribe", str(tmp_path / "missing.wav")])
    assert rc == 1
    assert "no such audio file" in capsys.readouterr().out


def test_label_and_audit_explanations_flags_pin_their_cli_surfaces(tmp_path, capsys):
    """§9.8/§9.9 at the shell edge: the last two flag surfaces without a CLI
    test. --label must prefix the one-shot reply with the communicated
    confidence label; --audit-explanations must be honest about an empty
    record and then actually audit once the mind has turned (internals of
    faithfulness live in their own suite; this pins entry + rc)."""
    state = tmp_path / "mind"

    rc = main(["--state-dir", str(state), "--audit-explanations"])
    assert rc == 0
    assert "no decisions on record yet" in capsys.readouterr().out

    rc = main(["--state-dir", str(state), "--say", "hello", "--label"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("[") and "] " in out.splitlines()[0]   # label prefix present

    rc = main(["--state-dir", str(state), "--audit-explanations"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "explanation audit:" in out and "turn(s)" in out and "violation(s)" in out
