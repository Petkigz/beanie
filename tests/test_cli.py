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
