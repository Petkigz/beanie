"""Record envelope shared by all stores.

Traceability: ARCHITECTURE §3 — every stored entry carries id, kind, content,
source, timestamps (created/updated/last_observed), confidence, decay_profile
(freshness erosion, T12), evidence_refs, revision_history, and access_scope.

Stage 0 implements the envelope plus JSON serialization and the confidence
decay helper; full stores arrive in Stage 1. The envelope is the contract that
keeps every future store corrigible (VISION property 3).
"""

from __future__ import annotations

import datetime as _dt
import enum
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

UTC = _dt.timezone.utc


def utcnow_iso() -> str:
    """Current UTC time as ISO-8601 with seconds precision."""
    return _dt.datetime.now(UTC).isoformat(timespec="seconds")


class Source(str, enum.Enum):
    """Where an entry came from (ARCHITECTURE §3 envelope)."""

    PERCEPTION = "perception"
    OWNER = "owner"
    WEB = "web"
    INFERENCE = "inference"
    SELF_REFLECTION = "self-reflection"


class RecordKind(str, enum.Enum):
    """Entry kinds across the mind's stores (§3.1–§3.7).

    Stage 0 persists EPISODE entries only; the other kinds are declared now so
    schemas stay stable when their stores arrive in Stage 1.
    """

    EPISODE = "episode"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    SELF = "self"
    OWNER_MODEL = "owner_model"
    INTENTION = "intention"


class Volatility(str, enum.Enum):
    """Volatility class used to pick a decay profile (T12, ARCHITECTURE §3.6)."""

    LOW = "low"          # e.g. a file's existence
    MEDIUM = "medium"    # default
    HIGH = "high"        # e.g. a process's `running` flag


@dataclass(frozen=True)
class DecayProfile:
    """How confidence erodes while an entry goes unobserved (ARCHITECTURE §3).

    Deterministic exponential decay by half-life; empirical constants per
    volatility class are open question ARCHITECTURE §9.8.
    """

    volatility: Volatility = Volatility.MEDIUM
    half_life_hours: float = 72.0

    def decayed(self, confidence: float, age_hours: float) -> float:
        """Confidence after `age_hours` of non-observation."""
        if self.half_life_hours <= 0:
            return confidence
        return round(confidence * (0.5 ** (age_hours / self.half_life_hours)), 4)


@dataclass(frozen=True)
class EvidenceRef:
    """Pointer to another entry that supports/conflicts with this one."""

    record_id: str
    role: str = "supports"  # supports | conflicts | source | context


@dataclass(frozen=True)
class Revision:
    """One entry in revision_history: every change and why (VISION property 3)."""

    at: str
    reason: str
    confidence_before: float
    confidence_after: float


@dataclass
class Entry:
    """One corrigible record in the mind's long-term stores (ARCHITECTURE §3)."""

    id: str
    kind: RecordKind
    content: dict[str, Any]
    source: Source
    confidence: float
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)
    last_observed_at: str = field(default_factory=utcnow_iso)
    decay_profile: DecayProfile = field(default_factory=DecayProfile)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    revision_history: list[Revision] = field(default_factory=list)
    access_scope: str = "owner"  # enforcement model: open question §9.5

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def revise(
        self,
        reason: str,
        *,
        confidence: Optional[float] = None,
        content: Optional[dict[str, Any]] = None,
        observe: bool = True,
    ) -> "Entry":
        """Update the entry in place, recording why (VISION property 3, T2).

        Every change goes through here — never mutate fields directly — so
        revision_history stays complete and the contradiction engine (§3.6) has
        an audit trail to reason over.
        """
        before = self.confidence
        now = utcnow_iso()
        if confidence is not None:
            self.confidence = self._clamp(confidence)
        if content is not None:
            self.content = content
        if observe:
            self.last_observed_at = now
        self.updated_at = now
        self.revision_history.append(
            Revision(at=now, reason=reason, confidence_before=before, confidence_after=self.confidence)
        )
        return self

    def effective_confidence(self, now: Optional[str] = None) -> float:
        """Confidence decayed by time since last observation (T12)."""
        now = now or utcnow_iso()
        try:
            age = (_dt.datetime.fromisoformat(now) - _dt.datetime.fromisoformat(self.last_observed_at)).total_seconds()
        except ValueError:
            age = 0.0
        return self.decay_profile.decayed(self.confidence, age / 3600.0)

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "content": self.content,
            "source": self.source.value,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_observed_at": self.last_observed_at,
            "decay_profile": {
                "volatility": self.decay_profile.volatility.value,
                "half_life_hours": self.decay_profile.half_life_hours,
            },
            "evidence_refs": [asdict(r) for r in self.evidence_refs],
            "revision_history": [asdict(r) for r in self.revision_history],
            "access_scope": self.access_scope,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entry":
        dp = data.get("decay_profile") or {}
        return cls(
            id=data["id"],
            kind=RecordKind(data["kind"]),
            content=data["content"],
            source=Source(data["source"]),
            confidence=float(data["confidence"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            last_observed_at=data["last_observed_at"],
            decay_profile=DecayProfile(
                volatility=Volatility(dp.get("volatility", Volatility.MEDIUM.value)),
                half_life_hours=float(dp.get("half_life_hours", 72.0)),
            ),
            evidence_refs=[EvidenceRef(**r) for r in data.get("evidence_refs", [])],
            revision_history=[Revision(**r) for r in data.get("revision_history", [])],
            access_scope=data.get("access_scope", "owner"),
        )

    @classmethod
    def from_json(cls, line: str) -> "Entry":
        return cls.from_dict(json.loads(line))


def confidence_label(confidence: float) -> str:
    """Map an evidence-state confidence to a communicated label (T8).

    Thresholds are provisional; the mapping itself and its calibration are
    open question ARCHITECTURE §9.7. The label is always surfaced on replies
    (VISION property 7).
    """
    if confidence >= 0.80:
        return "highly confident"
    if confidence >= 0.55:
        return "moderate"
    return "speculative"
