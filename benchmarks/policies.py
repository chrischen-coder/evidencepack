"""Equal-schema baselines; these are selection policies, not complete agents."""

from __future__ import annotations

from uuid import uuid4

from evidencepack import BudgetTooSmall, LexicalRanker, Pack
from evidencepack.domain import Counter, Excerpt

POLICIES = ("prefix", "head_tail", "bm25", "evidencepack")


def baseline_pack(
    policy: str, query: str, units: tuple[Excerpt, ...], counter: Counter, budget: int
) -> Pack:
    """Give baselines the same complete units, citation metadata and serialized allowance."""
    receipt = "p_" + uuid4().hex
    selected: list[Excerpt] = []
    seen: set[tuple[str, str]] = set()

    def projection() -> Pack:
        return Pack(receipt, tuple(selected), len(units) - len(selected), counter.name)

    minimum = counter.count(projection().to_json())
    if minimum > budget:
        raise BudgetTooSmall(budget, minimum)
    if policy == "prefix":
        order = list(units)
    elif policy == "head_tail":
        order = []
        left, right = 0, len(units) - 1
        while left <= right:
            order.append(units[left])
            if left != right:
                order.append(units[right])
            left += 1
            right -= 1
    elif policy == "bm25":
        ranked = LexicalRanker().rank(query, units)
        ranked.sort(
            key=lambda pair: (
                -pair[1] / max(1, counter.count(pair[0].text)),
                pair[0].source,
                pair[0].ordinal,
            )
        )
        order = [unit for unit, _score in ranked]
    else:
        raise ValueError(f"Unknown baseline: {policy}")
    for unit in order:
        key = (unit.artifact_id, unit.sha256)
        if key in seen:
            continue
        seen.add(key)
        selected.append(unit)
        if counter.count(projection().to_json()) > budget:
            selected.pop()
            if policy == "prefix":
                break
    return projection()
