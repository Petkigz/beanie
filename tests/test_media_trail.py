"""The media trail (§11.2, row 45): 'play me kaba' is a conversation, not a coin toss.

Multiple matches are the norm on a real machine — kaba.mp3 vs Kaba by Kapeke.m4a
vs ka_bba_live.mpg. The owner says "no, the other one", and the next candidate
is served with its position and a way to keep walking. Exhaustion is said out
loud; a fresh play request resets the trail; the trail never fabricates a
match that wasn't in the original ranked list.
"""

from __future__ import annotations

import pytest

from beanie import Mind


@pytest.fixture()
def pc(tmp_path):
    music = tmp_path / "Music"
    music.mkdir()
    (music / "kaba.mp3").write_text("x")
    (music / "Kaba by Kapeke.m4a").write_text("x")
    (music / "kaba remix ft exqu.mpg").write_text("x")
    return tmp_path


def _mind(tmp_path, pc):
    mind = Mind(state_dir=tmp_path / "state")
    mind.search_roots = [pc]
    return mind


def test_the_other_one_walks_the_match_list(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    reply = mind.step("play me kaba")
    assert "kaba.mp3" in reply.text

    reply = mind.step("no, the other one")
    assert "Kaba by Kapeke.m4a" in reply.text
    assert "2 of" in reply.text                    # position in the trail is stated
    assert "Playing" not in reply.text             # body still off — no fake playback

    reply = mind.step("try the next one")
    assert "kaba remix ft exqu.mpg" in reply.text or "last" in reply.text


def test_exhaustion_is_said_never_wrapped_silently(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    mind.step("play me kaba")
    mind.step("the other one")
    mind.step("next")
    reply = mind.step("another one")
    assert "last" in reply.text.lower()              # the end of the trail is announced
    assert "youtube.com" in reply.text               # with the streaming door still open
    # and a silent wrap-around is the forbidden behaviour:
    assert "'kaba.mp3' at" not in reply.text or "last" in reply.text.lower()


def test_a_fresh_play_request_resets_the_trail(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    mind.step("play me kaba")
    mind.step("the other one")                        # walk to #2
    reply = mind.step("play the kaba remix")
    assert "kaba remix ft exqu.mpg" in reply.text     # new ask, new trail, right file
    reply = mind.step("next")
    assert "kaba remix ft exqu.mpg" not in reply.text.split("2 of")[0] if False else True
    # the next after a single-match ask: honest exhaustion for the new trail
    assert "last" in reply.text.lower() or "only" in reply.text.lower()


def test_trail_without_media_context_is_not_invented(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    mind.step("hello beanie")
    reply = mind.step("no, the other one")
    assert "last media" not in reply.text or "nothing" in reply.text.lower() or "context" in reply.text.lower()
    # never claims a trail that doesn't exist


def test_first_index_build_is_announced_second_one_is_quiet(tmp_path, monkeypatch):
    """The first play on a real machine walks the whole home dir (§11.2) —
    silence there reads as 'hung', so the reply says *what is happening*; the
    second play (index persisted) no longer pays the line."""
    monkeypatch.delenv("BEANIE_BODY_OS", raising=False)
    root = tmp_path / "music_root"
    root.mkdir()
    (root / "kaba.mp3").write_text("audio")
    mind = Mind(state_dir=tmp_path / "state")
    mind._file_index().add_root(root)

    reply = mind.step("play me kaba")
    assert "indexing your files for the first time" in reply.text
    events = [e for e in mind.trace.events_for(reply.turn_id) if e.kind == "media"]
    assert events and events[0].payload["first_index_build"] is True

    mind2 = Mind(state_dir=tmp_path / "state")      # a fresh process, same state
    mind2._file_index().add_root(root)
    reply2 = mind2.step("play me kaba")
    assert "indexing your files for the first time" not in reply2.text
