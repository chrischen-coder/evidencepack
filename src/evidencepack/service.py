"""Application facade that binds trusted scope to storage and selection policy."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from .counters import ByteCounter
from .domain import (
    Artifact,
    BudgetTooSmall,
    Counter,
    MediaType,
    Pack,
    Ranker,
    Repository,
    Scope,
    Verdict,
)
from .selection import BudgetPacker, LexicalRanker


class EvidenceService:
    """Compose replaceable ports once, keeping scope out of model-supplied arguments."""

    def __init__(
        self,
        repository: Repository,
        scope: Scope,
        *,
        counter: Counter | None = None,
        ranker: Ranker | None = None,
    ) -> None:
        self.repository = repository
        self.scope = scope
        self.counter = counter or ByteCounter()
        self.packer = BudgetPacker(self.counter, ranker or LexicalRanker())

    def capture(self, source: str, text: str, *, media_type: MediaType = "text") -> Artifact:
        """Persist original textual output before building any model projection."""
        return self.repository.put(self.scope, source, text, media_type)

    def pack(self, query: str, artifact_ids: Sequence[str], *, budget: int = 4096) -> Pack:
        """Select complete evidence, enforce the allowance, then commit its receipt."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be nonblank")
        if not artifact_ids:
            raise ValueError("At least one artifact ID is required")
        units = self.repository.units(self.scope, tuple(artifact_ids))
        pack = self.packer.build(query, units, budget)
        self.repository.record(self.scope, pack)
        return pack

    def read(self, artifact_id: str, locator: str, *, budget: int = 4096) -> Pack:
        """Expose an exact line range or JSON record through a fresh bounded receipt."""
        if type(budget) is not int or budget < 1:
            raise ValueError("budget must be a positive integer")
        unit = self.repository.resolve(self.scope, artifact_id, locator)
        pack = Pack("p_" + uuid4().hex, (unit,), 0, self.counter.name)
        required = self.counter.count(pack.to_json())
        if required > budget:
            raise BudgetTooSmall(budget, required)
        self.repository.record(self.scope, pack)
        return pack

    def raw(self, artifact_id: str) -> Artifact:
        """Recover original output for the trusted host; this is deliberately unbudgeted."""
        return self.repository.get(self.scope, artifact_id)

    def verify(self, receipt: str, citation: str, quote: str) -> Verdict:
        """Check exact exposure provenance, leaving claim interpretation to the caller."""
        return self.repository.verify(self.scope, receipt, citation, quote)

    def release(self, receipt: str) -> None:
        """End the retention pin once the host no longer needs this receipt."""
        self.repository.release(self.scope, receipt)

    def delete(self, artifact_id: str, *, force: bool = False) -> None:
        """Delete scoped evidence, respecting live references unless explicitly forced."""
        self.repository.delete(self.scope, artifact_id, force=force)

    def collect(self, *, before: float) -> int:
        """Collect old unpinned artifacts while preserving explicit deletion history."""
        return self.repository.collect(self.scope, before)
