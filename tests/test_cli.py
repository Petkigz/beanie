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
