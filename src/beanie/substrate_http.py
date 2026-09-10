"""HTTP substrate — pluggable real-model tiers (OpenAI-compatible endpoint).

Traceability: ARCHITECTURE §2 — the substrate is swappable and identity never
lives in it. This adapter exists so a real model can be wired in behind the
same interface once model access exists.

Configuration (environment): BEANIE_MODEL_URL (e.g. https://api.openai.com/v1),
BEANIE_MODEL_NAME (e.g. gpt-4o-mini), BEANIE_API_KEY. If unset, constructing
the adapter raises RuntimeError with a clear message. `--substrate http` on the
suite runner and `--check-model` on the CLI both use this adapter, so the
moment an endpoint is configured the whole loop and the longitudinal suite run
against it.

Tests never touch an external endpoint: `tests/test_substrate_http.py` starts a
local OpenAI-compatible mock server on 127.0.0.1 and exercises the adapter
through it, which is what keeps this seam working without model access.

Honesty notes (VISION §4):
  * the confidence returned by ``deep`` is a placeholder until T8 calibration
    (the loop's calibrator still adjusts it from evidence state);
  * ``FAST_CONFIDENCE`` is deliberately *moderate*, not stub-high: a real
    model's gut answer is not a calibrated "highly confident";
  * when the tier is unreachable the loop is told via the escalation flag, and
    a reflex turn escalates to the deep tier instead of answering with an
    error string.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .records import confidence_label
from .substrate import Outcome, Substrate
from .trace import FailureTaxonomy


#: confidence of a fast-tier answer from a real model (moderate, not stub-high)
FAST_CONFIDENCE = 0.6

#: returned by fast() when the endpoint cannot answer — the loop's documented
#: escalation contract: a "fast: low-confidence" candidate promotes the turn
#: to the deep tier rather than being returned as an answer
_UNREACHABLE_FLAG = "fast: low-confidence flag for tool_execution_error"

#: hedging language in a fast answer: doubt the fast tier itself expressed
_HEDGE_RE = re.compile(r"\b(ambiguous|not sure|unclear|unsure|missing context|can'?t tell|don'?t know)\b",
                       re.IGNORECASE)


def _chat(base_url: str, api_key: str, model: str, messages: list[dict[str, str]], max_tokens: int) -> str:
    body = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (configurable endpoint)
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


class HTTPSubstrate(Substrate):
    """Two-tier substrate over an OpenAI-compatible chat endpoint."""

    name = "http"
    FAST_CONFIDENCE = FAST_CONFIDENCE

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        fast_model: str | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("BEANIE_MODEL_URL")
        self.model = model or os.environ.get("BEANIE_MODEL_NAME")
        self.api_key = api_key or os.environ.get("BEANIE_API_KEY")
        self.fast_model = fast_model or self.model
        missing = [name for name, value in (("BEANIE_MODEL_URL", self.base_url), ("BEANIE_MODEL_NAME", self.model), ("BEANIE_API_KEY", self.api_key)) if not value]
        if missing:
            raise RuntimeError(f"HTTPSubstrate requires {', '.join(missing)} to be configured.")

    def fast(self, observation: dict[str, Any], context: list[dict[str, Any]]) -> str:
        try:
            text = _chat(
                self.base_url, self.api_key, self.fast_model,
                [{"role": "system", "content": "You are Beanie's System-1 tier: reply with a terse intuitive candidate (under 20 words)."},
                 {"role": "user", "content": observation.get("user_text", "")}],
                max_tokens=32,
            ).strip()
            if _HEDGE_RE.search(text):
                # the gut answer itself flags doubt: surface it through the loop's
                # escalation contract so the deep tier decides, not the fast tier
                return _UNREACHABLE_FLAG.replace("tool_execution_error", "prompt_ambiguity")
            return text
        except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError):
            # honest failure: flag low confidence so the loop escalates instead
            # of answering the owner with an error string at high confidence
            return _UNREACHABLE_FLAG

    def deep(self, observation: dict[str, Any], context: list[dict[str, Any]], candidate: str) -> Outcome:
        system = (
            "You are Beanie's System-2 tier. Think before answering. If the request is "
            "ambiguous, missing context, or conflicts with prior statements, say so plainly. "
            "Keep the answer concise."
        )
        turns: list[dict[str, str]] = [{"role": "system", "content": system}]
        for item in context[-8:]:
            turns.append({"role": item.get("role", "user"), "content": item.get("text", "")})
        if candidate and not candidate.startswith("fast: low-confidence"):
            # dual-process contract (§2): the deep tier verifies or overrules the
            # System-1 candidate, so it must be able to see it
            turns.append({"role": "system", "content": f"System-1 candidate: {candidate}"})
        turns.append({"role": "user", "content": observation.get("user_text", "")})
        try:
            text = _chat(self.base_url, self.api_key, self.model, turns, max_tokens=400).strip()
        except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError) as exc:
            return Outcome(
                text="My model tier is unreachable right now — I cannot respond with confidence.",
                confidence=0.1, success=False, failure=FailureTaxonomy.TOOL_EXECUTION_ERROR,
                fast_candidate=candidate, meta={"error": str(exc)},
            )
        low = any(token in text.lower() for token in ("ambiguous", "not sure", "unclear", "missing context"))
        confidence = 0.4 if low else 0.8  # placeholder until T8 calibration (Stage 1)
        return Outcome(
            text=text,
            confidence=confidence,
            success=not low,
            failure=FailureTaxonomy.PROMPT_AMBIGUITY if low else FailureTaxonomy.NONE,
            fast_candidate=candidate,
            slow_candidate=text,
            meta={"label": confidence_label(confidence)},
        )
