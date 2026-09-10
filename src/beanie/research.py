"""Learning from the outside world — sources, transcripts, gaps (§11.1 learn).

Traceability: ARCHITECTURE §4.3 (dormant learning is woken by declared needs,
not pretending), §9 (a researched answer names its source and what the source
did *not* cover — most instructional videos are incomplete; a verified-against-
second-source claim is worth more than a fluent summary), and the owner's brief
("when I don't know, search the internet — mostly videos — analyze them like a
human would, and handle partial information honestly").

What this module can honestly do today, and what it refuses to fake:

* find the top YouTube result for a topic (`streaming.youtube_top_result`);
* read the **transcript** (caption tracks are text — the mind reads text);
* extract step-shaped lines deterministically from the transcript;
* hand the transcript to the model tier for a checklist + an explicit GAPS
  pass ("what does this source not explain?") when a tier is wired.

It does **not** claim to watch pixels. A video without captions is a video
Beanie cannot yet understand — the reply says so, names the vision tier as
the blocker, and still hands the owner the source.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Callable, Optional

from .streaming import ResultsFetcher, youtube_top_result

# --------------------------------------------------------------- primitives

_VIDEO_ID_RE = re.compile(r"(?:youtube\.com/watch\?[^\"']*?v=|youtu\.be/)([\w-]{6,20})")
_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_SIMPLE_TITLE_RE = re.compile(r'"title"\s*:\s*\{\s*"simpleText"\s*:\s*"([^"]+)"')
_TEXT_ELEM_RE = re.compile(r'<text start="([\d.]+)"(?:[^>]*)>(.*?)</text>', re.DOTALL)
_STEP_CUE_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))(?:"
    r"step\s+(?:one|two|three|four|five|six|\d+)[,:]?\s+|"
    r"first(?:ly)?(?:\s+of all)?[,.]?\s+|to start[,.]?\s+|second(?:ly)?[,.]?\s+|"
    r"third(?:ly)?[,.]?\s+|next[,.]?\s+|then[,.]?\s+|after that[,.]?\s+|"
    r"once (?:you|we|the)[,.]?\s+|now (?:you|we|just)[,.]?\s+|"
    r"finally[,.]?\s+|lastly[,.]?\s+"
    r")([^.!?\n]{10,160})",
    re.IGNORECASE,
)


def video_id_from(url: str) -> Optional[str]:
    """Parse a YouTube video id out of watch/youtu.be URLs; None otherwise."""
    match = _VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


@dataclass
class CaptionTrack:
    base_url: str
    language: str
    name: str = ""


def _json_array_at(page: str, marker: str) -> Optional[str]:
    """Bracket-depth scan for the JSON array starting right after `marker` —
    a regex `\\[.*?\\]` breaks on string contents; this does not."""
    idx = page.find(marker)
    if idx < 0:
        return None
    start = page.find("[", idx)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(page)):
        char = page[pos]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return page[start:pos + 1]
    return None


def caption_tracks(page_html: str) -> list[CaptionTrack]:
    """Caption tracks from a watch page, English first (the mind reads text)."""
    raw = _json_array_at(page_html, '"captionTracks"')
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    tracks: list[CaptionTrack] = []
    for item in data:
        base_url = item.get("baseUrl")
        if not base_url:
            continue
        name = item.get("name", {})
        label = name.get("simpleText") if isinstance(name, dict) else str(name)
        tracks.append(CaptionTrack(
            base_url=base_url,
            language=str(item.get("languageCode", "")),
            name=str(label or ""),
        ))
    tracks.sort(key=lambda track: 0 if track.language.startswith("en") else 1)
    return tracks


def page_title(page_html: str) -> str:
    """The video's title: ytInitialPlayerResponse first, <title> as fallback."""
    match = _SIMPLE_TITLE_RE.search(page_html)
    if match:
        return unescape(match.group(1)).strip()
    match = _TITLE_TAG_RE.search(page_html)
    if match:
        title = unescape(match.group(1)).strip()
        return re.sub(r"\s*-\s*YouTube\s*$", "", title).strip()
    return ""


@dataclass
class Transcript:
    lines: list[tuple[float, str]]

    @property
    def text(self) -> str:
        return " ".join(line for _, line in self.lines)

    def excerpt(self, max_chars: int = 2400) -> str:
        text = self.text
        return text if len(text) <= max_chars else text[:max_chars].rsplit(" ", 1)[0] + " …"


def parse_timedtext(xml_text: str) -> Transcript:
    """YouTube timedtext XML → ordered (start, text) lines, entities decoded."""
    lines: list[tuple[float, str]] = []
    for match in _TEXT_ELEM_RE.finditer(xml_text):
        body = unescape(match.group(2))
        body = re.sub(r"<[^>]+>", "", body)  # inner <i>/<font> markup is not text
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            lines.append((float(match.group(1)), body))
    return Transcript(lines=lines)


def extract_step_lines(text: str, limit: int = 8) -> list[str]:
    """Step-shaped sentences — cue words only, so a line is never invented.
    Video narration that teaches in order talks in ordinal cues; anything else
    in the transcript is context, and context is not a checklist."""
    seen: set[str] = set()
    steps: list[str] = []
    for match in _STEP_CUE_RE.finditer(text):
        clause = re.sub(r"\s+", " ", match.group(1)).strip(" ,.;")
        if not clause:
            continue
        key = clause.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        steps.append(clause)  # kept in the narrator's own words — no rewriting
        if len(steps) >= limit:
            break
    return steps


# ----------------------------------------------------------------- researcher

@dataclass
class ResearchPacket:
    """One researched source packet — labelled, gap-aware, replayable."""
    topic: str
    video_url: str
    title: str
    transcript: Optional[Transcript] = None
    steps: list[str] = field(default_factory=list)
    no_captions: bool = False

    @property
    def source_label(self) -> str:
        return f"video transcript: '{self.title}' ({self.video_url})"


class Researcher:
    """Find → read → extract; the tier verifies. Offline-injectable (§9)."""

    def __init__(self, fetch: Optional[ResultsFetcher] = None) -> None:
        from .streaming import default_fetcher

        self.fetch = fetch or default_fetcher

    def research_video(self, topic: str) -> Optional[ResearchPacket]:
        """Assemble the best video source packet for a topic.

        None when no specific video resolves — the caller then honestly falls
        back (opening the search page is the stream from §11.2, not research).
        """
        url, specific = youtube_top_result(topic, fetch=self.fetch)
        if not specific:
            return None
        try:
            page = self.fetch(url)
        except Exception:  # network/HTML errors are honest "no research happened"
            return None
        packet = ResearchPacket(topic=topic, video_url=url, title=page_title(page) or topic)
        tracks = caption_tracks(page)
        if not tracks:
            packet.no_captions = True
            return packet
        try:
            xml = self.fetch(tracks[0].base_url)
            packet.transcript = parse_timedtext(xml)
        except Exception:
            packet.no_captions = True
            return packet
        if packet.transcript is not None and packet.transcript.lines:
            packet.steps = extract_step_lines(packet.transcript.text)
        else:
            packet.no_captions = True
            packet.transcript = None
        return packet
