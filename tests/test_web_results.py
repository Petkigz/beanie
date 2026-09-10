"""The web actually answers (§11.2/§11.7, rows 46/51): live results, dated and labelled.

"google X" must not be a passive tab-open anymore: Beanie reads the result titles
and snippets (text — the modality it honestly owns), and with a live tier it
summarizes what the web says *today*, always labelled as live lookup with its
date — never confused with internal knowledge. Without a tier the raw top
results are shown plainly, and a network failure is a failure, not prose.
"""

from __future__ import annotations

import pytest

from beanie import Mind
from beanie.research import WebResult, web_search
from beanie.substrate import Outcome, StubSubstrate

DDG_PAGE = """
<html><body>
<table>
 <tr><td><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FPortal%252FOuter%2520space" class="result-link">Portal: Outer space - Wikipedia</a></td></tr>
 <tr><td class='result-snippet'>A portal coordinated by editors covering outer space, the physical universe beyond Earth's atmosphere.</td></tr>
 <tr><td><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnasa.gov%2Fbiosphere" class="result-link">The Biosphere — NASA</a></td></tr>
 <tr><td class='result-snippet'>NASA science covering Earth's atmosphere and biosphere boundaries.</td></tr>
 <tr><td><a href="//duckduckgo.com/ad/sponsored" class="result-link">Buy planets now</a></td></tr>
</table>
</body></html>
"""


def _fetch(url: str) -> str:
    if "duckduckgo.com/lite" in url:
        return DDG_PAGE
    raise ValueError(f"no fixture page for {url}")


def test_web_search_parses_titles_links_and_snippets():
    results = web_search("where does earth's atmosphere end", fetch=_fetch)
    assert len(results) == 2                              # the sponsored row is not a result
    first = results[0]
    assert "Wikipedia" in first.title
    assert first.url == "https://en.wikipedia.org/wiki/Portal%2FOuter%20space"
    assert "atmosphere" in first.snippet.lower()
    second = results[1]
    assert second.url.startswith("https://nasa.gov")


def test_web_search_failure_is_a_honest_empty_never_a_lie():
    assert web_search("anything", fetch=lambda url: (_ for _ in ()).throw(ValueError("net down"))) == []


class _Tier(StubSubstrate):
    name = "fixture-tier"

    def deep(self, observation, context, candidate=None):
        text = observation.get("user_text", "")
        if "live web results" in text.lower():
            return Outcome(success=True, text=(
                "The atmosphere fades gradually into space; the Kármán line at 100 km is the "
                "usual working boundary.\nBEST: the Wikipedia portal — broadest neutral overview."))
        return Outcome(success=True, text="Acknowledged.")


def test_web_need_with_tier_summarizes_and_labels_the_lookup(tmp_path):
    mind = Mind(substrate=_Tier(), state_dir=tmp_path / "state")
    mind.web_fetcher = _fetch
    reply = mind.step("google where does earth's atmosphere end")
    assert "Kármán" in reply.text
    assert "live" in reply.text.lower() and "2026-09-10" in reply.text  # dated, labelled lookup
    assert "BEST" in reply.text or "Wikipedia" in reply.text
    assert "inner knowledge" not in reply.text  # explicitly separated from memory

    episode = mind.episodes.all()[-1]
    assert episode.content["directive"] == "web"
    assert episode.content.get("web_results")                                # the audit trail keeps the sources
    assert any("wikipedia" in r["url"] for r in episode.content["web_results"])


def test_web_need_without_tier_shows_the_raw_top_results_plainly(tmp_path):
    mind = Mind(state_dir=tmp_path / "state")
    mind.web_fetcher = _fetch
    reply = mind.step("search the web for outlandish deep sea creatures")
    assert "Wikipedia" in reply.text or "NASA" in reply.text
    assert "live lookup" in reply.text.lower()
    assert "can't weigh them yet" in reply.text or "stub" not in reply.text.lower()


def test_web_need_network_down_is_reported_as_network_down(tmp_path):
    mind = Mind(substrate=_Tier(), state_dir=tmp_path / "state")
    mind.web_fetcher = lambda url: (_ for _ in ()).throw(ValueError("net down"))
    reply = mind.step("google the price of maize this week")
    assert "couldn't reach" in reply.text.lower() or "no usable results" in reply.text.lower()
    assert "google.com/search" in reply.text            # the plain route is still offered
