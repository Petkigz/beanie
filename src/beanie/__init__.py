"""Beanie — an artificial mind, not an agent.

Traceability: ARCHITECTURE §8 Stage 0 (skeleton) — substrate wiring, loop entry
point, one minimal store (episodic), owner input/output, trace with
failure-taxonomy tagging. The vision this code must not drift from is fixed in
VISION.md (filter §2, properties §3, tests §5) and ARCHITECTURE.md.

Nothing in this package claims intelligence: the default substrate is a
deterministic test double so the loop, stores, trace, and measurement protocol
are honest and testable before any real model tier is wired in.
"""

from .mind import Mind, Reply
from .records import (
    DecayProfile,
    Entry,
    EvidenceRef,
    RecordKind,
    Revision,
    Source,
    Volatility,
    confidence_label,
)
from .stores import EpisodicStore
from .substrate import Outcome, StubSubstrate, Substrate
from .trace import FailureTaxonomy

__version__ = "0.1.0"
__all__ = [
    "Mind",
    "Reply",
    "Entry",
    "RecordKind",
    "Source",
    "EvidenceRef",
    "Revision",
    "DecayProfile",
    "Volatility",
    "confidence_label",
    "EpisodicStore",
    "Substrate",
    "StubSubstrate",
    "Outcome",
    "FailureTaxonomy",
    "__version__",
]
