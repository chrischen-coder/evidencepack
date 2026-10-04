"""Immutable evidence values and the ports used by the application service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol

MediaType = Literal["text", "json"]


class EvidenceError(Exception):
    """Base failure that callers may handle without catching programming errors."""


class NotFound(EvidenceError):
    """The requested evidence is unavailable in the caller's scope."""


class Deleted(EvidenceError):
    """An explicit deletion left a tombstone at this reference."""


class IntegrityError(EvidenceError):
    """Stored content no longer matches its captured digest."""


class Pinned(EvidenceError):
    """An active receipt still depends on the requested artifact."""


class BudgetTooSmall(EvidenceError):
    """The complete requested representation cannot fit the supplied allowance."""

    def __init__(self, budget: int, required: int) -> None:
        self.budget = budget
        self.required = required
        super().__init__(f"Budget {budget} is too small; at least {required} units are required")


@dataclass(frozen=True, slots=True)
class Scope:
    """Host-supplied tenant and session labels; these are not authentication."""

    tenant: str
    session: str

    def __post_init__(self) -> None:
        for label in (self.tenant, self.session):
            if not isinstance(label, str) or not label.strip() or len(label) > 256:
                raise ValueError("Scope labels must be nonblank strings of at most 256 characters")


@dataclass(frozen=True, slots=True)
class Artifact:
    """One tool invocation's original text and immutable capture identity."""

    id: str
    source: str
    text: str
    media_type: MediaType
    sha256: str
    created_at: float


@dataclass(frozen=True, slots=True)
class Excerpt:
    """A complete displayed unit tied to one artifact and a recoverable locator."""

    citation: str
    artifact_id: str
    source: str
    locator: str
    text: str
    sha256: str
    ordinal: int

    def as_dict(self) -> dict[str, str]:
        """Return only the fields that the model needs to read and cite a unit."""
        return {
            "citation": self.citation,
            "artifact": self.artifact_id,
            "source": self.source,
            "locator": self.locator,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class Pack:
    """A serialized model projection backed by a committed exposure receipt."""

    receipt: str
    excerpts: tuple[Excerpt, ...]
    omitted: int
    counter: str

    def to_json(self) -> str:
        """Serialize the complete budgeted representation, including metadata."""
        return json.dumps(
            {
                "v": 1,
                "receipt": self.receipt,
                "counter": self.counter,
                "excerpts": [unit.as_dict() for unit in self.excerpts],
                "omitted": self.omitted,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class Verdict:
    """Quote provenance result; validity does not establish semantic entailment."""

    valid: bool
    reason: str


class Counter(Protocol):
    """Measure the final string in one explicitly named budget unit."""

    @property
    def name(self) -> str: ...

    def count(self, text: str) -> int: ...


class Ranker(Protocol):
    """Assign query relevance without changing the original evidence units."""

    def rank(self, query: str, units: tuple[Excerpt, ...]) -> list[tuple[Excerpt, float]]: ...


class Repository(Protocol):
    """Persist evidence and exposure atomically within a host-bound scope."""

    def put(self, scope: Scope, source: str, text: str, media_type: MediaType) -> Artifact: ...

    def get(self, scope: Scope, artifact_id: str) -> Artifact: ...

    def units(self, scope: Scope, artifact_ids: tuple[str, ...]) -> tuple[Excerpt, ...]: ...

    def resolve(self, scope: Scope, artifact_id: str, locator: str) -> Excerpt: ...

    def record(self, scope: Scope, pack: Pack) -> None: ...

    def verify(self, scope: Scope, receipt: str, citation: str, quote: str) -> Verdict: ...

    def release(self, scope: Scope, receipt: str) -> None: ...

    def delete(self, scope: Scope, artifact_id: str, *, force: bool = False) -> None: ...

    def collect(self, scope: Scope, before: float) -> int: ...
