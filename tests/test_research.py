"""Learning from the outside world (§11.9, row 51): research with sources.

The user requirement: when Beanie doesn't know how, it recognizes that, finds
a video worth learning from, reads what can honestly be read (the transcript —
pixels need the vision tier), and verifies whether the source is complete —
most videos aren't, so gaps are named, not papered over.

The mechanics are deterministic and testable offline: URL parsing, caption
extraction, step extraction, source labelling. The tier does only the parts a
human does with understanding: condensing and gap-checking — and when no tier
is wired, the honest output is the raw step lines plus an unverified-rubric.
"""

from __future__ import annotations

import json

from beanie import Mind
from beanie.research import (
    Researcher,
    caption_tracks,
    extract_step_lines,
    parse_timedtext,
    video_id_from,
)
from beanie.substrate import Outcome, StubSubstrate

WATCH_PAGE = """
<html><head><title>How to edit videos in OpenShot for beginners - YouTube</title></head>
<body>
<script>var ytInitialPlayerResponse = {"captions":{"playerCaptionsTracklistRenderer":
{"captionTracks":[{"baseUrl":"https://www.youtube.com/api/timedtext?v=abc123xyz&lang=en",
"name":{"simpleText":"English"},"languageCode":"en","kind":""},
{"baseUrl":"https://www.youtube.com/api/timedtext?v=abc123xyz&lang=sw",
"name":{"simpleText":"Swahili"},"languageCode":"sw"}]}},
"title":{"simpleText":"How to edit videos in OpenShot for beginners"}};
</script></body></html>
"""

TIMEDTEXT = """<?xml version="1.0" encoding="utf-8"?>
<transcript>
<text start="0.0" dur="2.4">So, welcome back guys. Let&apos;s begin.</text>
<text start="2.4" dur="4.0">First you import your clips into the Project Files panel.</text>
<text start="6.4" dur="3.5">Then drag the clip onto the timeline to start cutting.</text>
<text start="9.9" dur="4.1">Next, use the razor tool to split where you want the cut.</text>
<text start="14.0" dur="3.2">After that, arrange the pieces and add transitions.</text>
<text start="17.2" dur="5.8">Finally, export the project to an mp4 file. &amp; that is it.</text>
</transcript>
"""


def _fixture_fetcher(url: str) -> str:
    if "youtube.com/results" in url:
        return '{"videoId": "abc123xyz"}'
    if "watch?v=abc123xyz" in url:
        return WATCH_PAGE
    if "timedtext" in url:
        return TIMEDTEXT
    raise ValueError(f"fixture has no page for {url}")


def test_video_id_parsing():
    assert video_id_from("https://www.youtube.com/watch?v=abc123xyz&list=1") == "abc123xyz"
    assert video_id_from("https://youtu.be/abc123xyz") == "abc123xyz"
    assert video_id_from("https://www.youtube.com/watch?v=abc123xyz") == "abc123xyz"
    assert video_id_from("https://example.com/page") is None


def test_caption_tracks_prefer_english():
    tracks = caption_tracks(WATCH_PAGE)
    assert len(tracks) == 2
    assert tracks[0].language == "en"         # English ordered first
    assert "lang=en" in tracks[0].base_url
    assert caption_tracks("<html><body>no video here</body></html>") == []


def test_timedtext_parsing_decodes_entities_and_keeps_timing():
    transcript = parse_timedtext(TIMEDTEXT)
    assert transcript.lines[0][0] == 0.0
    assert "Let's begin." in transcript.text
    assert "&" in transcript.text            # &amp; decoded
    assert "<text" not in transcript.text    # markup stripped


def test_step_extraction_is_cue_based_not_guessed():
    transcript = parse_timedtext(TIMEDTEXT)
    steps = extract_step_lines(transcript.text)
    assert any("import your clips" in s for s in steps)
    assert any("razor tool" in s for s in steps)
    assert any("export the project" in s for s in steps)
    assert not any("welcome back" in s.lower() for s in steps)   # chatter isn't a step
    assert extract_step_lines("") == []


def test_researcher_assembles_a_labelled_source_packet():
    researcher = Researcher(fetch=_fixture_fetcher)
    packet = researcher.research_video("how to edit videos in openshot")
    assert packet is not None
    assert packet.video_url == "https://www.youtube.com/watch?v=abc123xyz"
    assert "OpenShot" in packet.title
    assert packet.transcript and "razor" in packet.transcript.text
    assert packet.steps and len(packet.steps) >= 3
    assert packet.source_label == (
        "video transcript: 'How to edit videos in OpenShot for beginners' "
        "(https://www.youtube.com/watch?v=abc123xyz)"
    )


def test_researcher_without_captions_says_so_instead_of_watching():
    def no_caption_fetch(url: str) -> str:
        if "youtube.com/results" in url:
            return '{"videoId": "vidxyz123"}'
        if "timedtext" in url:
            raise ValueError("no captions")
        return "<html><head><title>A Tutorial - YouTube</title></head><body></body></html>"

    packet = Researcher(fetch=no_caption_fetch).research_video("cook sushi")
    assert packet is not None and packet.transcript is None
    assert packet.no_captions is True
    assert packet.steps == []


def test_researcher_unresolvable_is_honest_none():
    def empty_fetch(url: str) -> str:
        return "{}"  # no videoId on the results page

    assert Researcher(fetch=empty_fetch).research_video("anything") is None


class _Tier(StubSubstrate):
    """A standing model tier for the learn flow: teach + verify prompts answered."""

    name = "fixture-tier"

    def deep(self, observation, context, candidate=None):
        text = observation.get("user_text", "")
        if "gaps" in text.lower() and "checklist" in text.lower():
            return Outcome(
                success=True,
                text=("1 Import clips. 2 Drag to timeline. 3 Split with razor. 4 Arrange and "
                      "transition. 5 Export mp4.\nGAPS: the video never explains audio levels or "
                      "title overlays — find a second source for those."),
            )
        return Outcome(success=True, text="Acknowledged.", confidence=0.5)


def test_learn_flow_does_real_research_and_names_gaps(tmp_path):
    mind = Mind(substrate=_Tier(), state_dir=tmp_path / "state")
    mind.youtube_fetcher = _fixture_fetcher
    reply = mind.step("learn how to edit videos in openshot")
    assert "Import clips" in reply.text
    assert "GAPS" in reply.text or "never explains audio" in reply.text   # partial source named
    assert "transcript" in reply.text.lower()                              # labelled honestly
    assert "unverified" in reply.text.lower()                              # until practiced
    # the gap lands as a recorded open question, not lost in prose
    open_texts = [e.content.get("text", "") for e in mind.memory.query(kind="self", type="question", status="open")]
    assert any("audio" in t.lower() or "subtitle" in t.lower() or "overlay" in t.lower() for t in open_texts)
    episode = mind.episodes.all()[-1]
    assert episode.content["directive"] == "learn"
    assert episode.content.get("research", {}).get("video_url", "").endswith("abc123xyz")


def test_learn_flow_without_captions_admits_the_vision_gap(tmp_path):
    def no_caption_fetch(url: str) -> str:
        if "youtube.com/results" in url:
            return '{"videoId": "vidxyz123"}'
        if "timedtext" in url:
            raise ValueError("none")
        return "<html><head><title>Only Video - YouTube</title></head><body></body></html>"

    mind = Mind(substrate=_Tier(), state_dir=tmp_path / "state")
    mind.youtube_fetcher = no_caption_fetch
    reply = mind.step("learn how to cook sushi")
    assert "transcript" in reply.text.lower() or "captions" in reply.text.lower()
    assert "can't (yet)" in reply.text or "vision" in reply.text.lower() or "cannot read the pictures" in reply.text.lower()
    assert "youtube.com/watch" in reply.text   # the owner still gets the source itself


def test_learn_flow_still_declares_honestly_without_any_tier(tmp_path):
    mind = Mind(state_dir=tmp_path / "state")     # stub tier: no research pretended
    reply = mind.step("learn quantum entanglement")
    assert "don't know how" in reply.text
    assert "transcript" not in reply.text.lower()  # nothing fabricated about sources
