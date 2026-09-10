"""Streaming fallback — when the PC does not have the media (§11.2 / row 45).

Traceability: ARCHITECTURE §11.2 (the media sense answers "do we have it?"
from the file index first — the PC's own copy wins — and falls back to the
owner's streaming destination with the *same* query) and §5 (opening the
fallback is still an action through the authority gate and the OS body —
never a silent side effect).

`youtube_top_result` resolves a query to a specific watch URL by reading the
YouTube results page; when the network or the page disagrees, the honest
fallback is the search-results URL itself — the owner lands exactly where
they would have typed the query, and the reply says which of the two
happened. The fetcher is injectable so tests never touch a network.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
from typing import Callable, Optional
from urllib.error import URLError

ResultsFetcher = Callable[[str], str]

_YOUTUBE_SEARCH = "https://www.youtube.com/results?search_query={query}"
_GOOGLE_SEARCH = "https://www.google.com/search?q={query}"
_VIDEO_ID_RE = re.compile(r'"videoId"\s*:\s*"([\w-]{6,20})"')


def youtube_search_url(query: str) -> str:
    return _YOUTUBE_SEARCH.format(query=urllib.parse.quote_plus(query))


def google_search_url(query: str) -> str:
    return _GOOGLE_SEARCH.format(query=urllib.parse.quote_plus(query))


def default_fetcher(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (beanie-mind)"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 — fixed URL built here
        return response.read().decode("utf-8", errors="replace")


def youtube_top_result(query: str, *, fetch: Optional[ResultsFetcher] = None) -> tuple[str, bool]:
    """Best-effort deep link to the top YouTube result for `query`.

    Returns (url, is_specific): ``(…/watch?v=…, True)`` when a specific video
    was resolved, or ``(…/results?search_query=…, False)`` when only the
    search page itself is known. The boolean is what keeps the reply honest —
    "I opened the top result" vs "I opened the search for it".
    """
    fetch = fetch or default_fetcher
    try:
        page = fetch(youtube_search_url(query))
    except (URLError, OSError, ValueError):
        return youtube_search_url(query), False
    match = _VIDEO_ID_RE.search(page)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}", True
    return youtube_search_url(query), False
