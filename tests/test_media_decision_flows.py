"""End-to-end decision-gate flows (§11.1/§11.2/§5, rows 44–46).

The owner's acceptance case drives these: "play me kaba" must find the song on
the machine no matter how it is named, a song the machine does not have falls
back to streaming honestly, dangerous work always asks first, and everything
reported as done really was done (or the reply says why not).
"""

from __future__ import annotations

import pathlib

import pytest

from beanie import Mind


class FakeBody:
    """Records every action a flow attempted — the audit seed for these runs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, capability: str, args: dict | None = None) -> dict:
        self.calls.append((capability, dict(args or {})))
        return {"returncode": 0, "stdout": "ok-body-ran", "stderr": "", "ran": capability}


@pytest.fixture()
def pc(tmp_path):
    """A small staged 'PC': songs with awkward names, plus some decoys."""
    music = tmp_path / "Music"
    music.mkdir()
    (music / "kaba.mp3").write_text("x")
    (music / "Kaba by Kapeke.m4a").write_text("x")
    (tmp_path / "Downloads").mkdir()
    (tmp_path / "Downloads" / "ka_bba live.mpg").write_text("x")
    return tmp_path


def _mind(tmp_path, roots, authority="ask", monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setenv("BEANIE_BODY_OS", "1")  # the dry-run preview builder needs the opt-in
    mind = Mind(state_dir=tmp_path / "state", authority=authority)
    mind.search_roots = [roots]
    mind.youtube_fetcher = lambda url: '"videoId": "abc123xyz"'  # deterministic, no network
    return mind


def test_play_finds_the_song_regardless_of_how_it_is_named(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    reply = mind.step("play me kaba")
    assert "kaba.mp3" in reply.text
    assert "Playing" not in reply.text          # body off: found, but no false claim of playback
    assert "BEANIE_BODY_OS=1" in reply.text     # and the path to real playback is stated
    episode = mind.episodes.all()[-1]
    assert episode.content["directive"] == "play_media"
    assert episode.content["decision"]["kind"] == "play_media"
    assert episode.content["matched"].endswith("kaba.mp3")
    assert mind._turn_organ("").startswith("the decision gate")


def test_play_ranks_video_for_video_requests(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    reply = mind.step("play the kabba video")   # near-spelling, video kind
    assert "ka_bba live.mpg" in reply.text
    assert "kaba.mp3" not in reply.text


def test_missing_song_falls_back_to_streaming_honestly(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    reply = mind.step("play me zzz neverheard")
    assert "watch?v=abc123xyz" in reply.text    # specific link resolved by the (stubbed) fetcher
    assert "isn't on this machine" in reply.text or "Nothing like" in reply.text
    assert "Playing" not in reply.text          # nothing played, nothing claimed


def test_streaming_fallback_opens_itself_when_body_and_permission_allow(tmp_path, pc, monkeypatch):
    mind = _mind(tmp_path, pc, authority="allow", monkeypatch=monkeypatch)
    fake = FakeBody()
    mind._osbody, mind._osbody_probed = fake, True
    reply = mind.step("play me zzz neverheard")
    assert ("open_url", {"url": "https://www.youtube.com/watch?v=abc123xyz"}) in fake.calls
    assert "opened the top result" in reply.text


def test_play_found_launches_the_player_with_allow(tmp_path, pc, monkeypatch):
    mind = _mind(tmp_path, pc, authority="allow", monkeypatch=monkeypatch)
    fake = FakeBody()
    mind._osbody, mind._osbody_probed = fake, True
    reply = mind.step("play me kaba")
    assert any(cap == "play_media" for cap, _ in fake.calls)
    assert reply.text.startswith("Playing 'kaba.mp3'")


def test_dangerous_work_always_asks_first_and_previews_the_command(tmp_path, pc, monkeypatch):
    mind = _mind(tmp_path, pc, monkeypatch=monkeypatch)  # default policy: ask
    fake = FakeBody()
    mind._osbody, mind._osbody_probed = fake, True
    reply = mind.step("install obs studio")
    assert "you may install_app" in reply.text
    assert "would run" in reply.text.lower() or "winget install" in reply.text or "apt-get" in reply.text or "brew" in reply.text
    assert fake.calls == []                     # nothing executed while asking
    assert mind.pending_permission_requests()   # the ask is on record, counted
    # a second ask of the same kind escalates politely instead of repeating verbatim
    reply2 = mind.step("install obs studio")
    assert "2nd time" in reply2.text
    assert fake.calls == []
    # the owner grants it — then the same request executes
    mind.step("you may install_app")
    reply3 = mind.step("install obs studio")
    assert fake.calls and fake.calls[0][0] == "install_app"
    assert "Done" in reply3.text or "winget" in reply3.text or "apt-get" in reply3.text


def test_denied_capability_is_refused_with_the_rule_cited(tmp_path, pc, monkeypatch):
    mind = _mind(tmp_path, pc, monkeypatch=monkeypatch)
    mind._osbody, mind._osbody_probed = FakeBody(), True
    mind.step("never use install_app")
    reply = mind.step("install obs studio")
    assert "ruled install_app out" in reply.text


def test_open_and_web_without_body_are_plain_honest_reports(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    reply = mind.step("open firefox")
    assert "nothing was launched" in reply.text
    reply = mind.step("go to youtube.com")
    assert "youtube.com" in reply.text and "BEANIE_BODY_OS=1" in reply.text
    reply = mind.step("google how the nether portal works")
    assert "google.com/search" in reply.text
    assert "open question" in reply.text.lower() or "learn" in reply.text.lower()
    assert mind.memory.query(kind="self", type="question", status="open")


def test_phone_not_connected_is_reported_never_pretended(tmp_path, pc, monkeypatch):
    monkeypatch.delenv("BEANIE_ANDROID", raising=False)
    mind = _mind(tmp_path, pc)
    reply = mind.step("on my phone, open whatsapp")
    assert "isn't connected" in reply.text
    assert "nothing was attempted" in reply.text


def test_learning_tasks_are_declared_not_improvised(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    reply = mind.step("learn how to edit videos in openshot")
    assert "don't know how" in reply.text
    assert "open question" in reply.text
    assert any("openshot" in e.content.get("subject", "")
               for e in mind.memory.query(kind="self", type="question", status="open"))


def test_everyday_conversation_stays_conversation(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    reply = mind.step("hi there, how are you doing today?")
    assert reply.text                            # answered
    assert all(e.content.get("directive") not in ("play_media", "shell", "install_app")
               for e in mind.episodes)


def test_find_files_reports_all_matches_with_places(tmp_path, pc):
    mind = _mind(tmp_path, pc)
    reply = mind.step("find the kaba file")
    assert "kaba.mp3" in reply.text and "Kaba by Kapeke.m4a" in reply.text
    reply = mind.step("find the blorple file")
    assert "found nothing" in reply.text.lower()
