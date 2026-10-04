"""Complete-unit projections and deterministic, coverage-aware budget selection."""

from __future__ import annotations

import json
import math
import re
from collections import Counter as Frequencies
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .domain import BudgetTooSmall, Counter, Excerpt, MediaType, Pack, Ranker

_WORDS = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)
_DIAGNOSTIC = re.compile(
    r"\b(error|failed|failure|exception|refused|denied|mismatch|timeout|unhealthy)\b",
    re.IGNORECASE,
)
_STOP = frozenset("a an and are as at be by for from in is it of on or the to was with".split())


@dataclass(frozen=True, slots=True)
class Segment:
    """An atomic display unit before it receives its artifact identity."""

    locator: str
    text: str


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate keys whose pointers would otherwise be ambiguous."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def parse_json(text: str) -> Any:
    """Parse strict JSON so every record pointer has an unambiguous meaning."""

    def reject_constant(value: str) -> Any:
        raise ValueError(f"Non-JSON constant: {value}")

    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=reject_constant)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def segments(text: str, media_type: MediaType, *, window: int = 3) -> tuple[Segment, ...]:
    """Build complete text windows or complete JSON records without slicing values."""
    if media_type == "text":
        lines = text.splitlines(keepends=True) or [""]
        return tuple(
            Segment(f"L{i + 1}-L{min(i + window, len(lines))}", "".join(lines[i : i + window]))
            for i in range(0, len(lines), window)
        )
    if media_type != "json":
        raise ValueError("media_type must be 'text' or 'json'")
    data = parse_json(text)
    result: list[Segment] = []

    def emit(value: Any, pointer: str) -> None:
        if isinstance(value, list) and value:
            for index, record in enumerate(value):
                result.append(Segment(f"J:{pointer}/{index}", _json_text(record)))
        else:
            result.append(Segment(f"J:{pointer}", _json_text(value)))

    if isinstance(data, dict) and data:
        for key, value in data.items():
            emit(value, "/" + key.replace("~", "~0").replace("/", "~1"))
    else:
        emit(data, "")
    return tuple(result)


def extract(text: str, media_type: MediaType, locator: str) -> str:
    """Resolve a strict line range or RFC 6901 pointer against the captured input."""
    if media_type == "text":
        match = re.fullmatch(r"L([1-9][0-9]*)-L([1-9][0-9]*)", locator)
        if match is None:
            raise ValueError("Text locators use L1-L3 syntax")
        start, end = map(int, match.groups())
        lines = text.splitlines(keepends=True) or [""]
        if start > end or end > len(lines):
            raise ValueError("Line range is outside the captured text")
        return "".join(lines[start - 1 : end])
    if not locator.startswith("J:"):
        raise ValueError("JSON locators use J:/records/0 syntax")
    pointer = locator[2:]
    value = parse_json(text)
    if pointer:
        if not pointer.startswith("/"):
            raise ValueError("A nonempty JSON pointer starts with '/'")
        for encoded in pointer[1:].split("/"):
            if re.search(r"~(?![01])", encoded):
                raise ValueError("Invalid JSON pointer escape")
            key = encoded.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", key):
                    raise ValueError("JSON array pointers need canonical nonnegative indices")
                index = int(key)
                if index >= len(value):
                    raise ValueError("JSON array index is outside the captured value")
                value = value[index]
            elif isinstance(value, dict) and key in value:
                value = value[key]
            else:
                raise ValueError("JSON pointer does not resolve")
    return _json_text(value)


def words(text: str) -> tuple[str, ...]:
    """Tokenize identifiers and individual CJK characters for transparent retrieval."""
    return tuple(term for term in _WORDS.findall(text.lower()) if term not in _STOP)


class LexicalRanker:
    """BM25 relevance plus a small diagnostic bonus, without an LLM call."""

    def __init__(self, *, diagnostic_bonus: float = 0.15) -> None:
        self.diagnostic_bonus = diagnostic_bonus

    def rank(self, query: str, units: tuple[Excerpt, ...]) -> list[tuple[Excerpt, float]]:
        """Rank complete units; diagnostic signals cannot outweigh strong query matches."""
        terms = set(words(query))
        bags = [Frequencies(words(unit.text)) for unit in units]
        lengths = [sum(bag.values()) for bag in bags]
        average = sum(lengths) / max(1, len(lengths)) or 1.0
        frequencies = Frequencies(term for bag in bags for term in terms if term in bag)
        ranked: list[tuple[Excerpt, float]] = []
        for unit, bag, length in zip(units, bags, lengths, strict=True):
            score = 0.0
            for term in terms.intersection(bag):
                idf = math.log(
                    1 + (len(units) - frequencies[term] + 0.5) / (frequencies[term] + 0.5)
                )
                tf = bag[term]
                score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / average))
            if _DIAGNOSTIC.search(unit.text):
                score += self.diagnostic_bonus
            if score > 0:
                ranked.append((unit, score))
        return sorted(
            ranked,
            key=lambda item: (-item[1], item[0].source, item[0].ordinal, item[0].artifact_id),
        )


class BudgetPacker:
    """Select complete units and count every byte or token of the resulting pack."""

    def __init__(self, counter: Counter, ranker: Ranker, *, candidate_limit: int = 512) -> None:
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be positive")
        self.counter = counter
        self.ranker = ranker
        self.candidate_limit = candidate_limit

    def build(self, query: str, units: tuple[Excerpt, ...], budget: int) -> Pack:
        """Allocate one fair-share unit per source, then fill by relevance density."""
        if type(budget) is not int or budget < 1:
            raise ValueError("budget must be a positive integer")
        receipt = "p_" + uuid4().hex
        selected: list[Excerpt] = []
        selected_ids: set[str] = set()

        def projection(items: list[Excerpt]) -> Pack:
            return Pack(receipt, tuple(items), len(units) - len(items), self.counter.name)

        minimum = self.counter.count(projection([]).to_json())
        if minimum > budget:
            raise BudgetTooSmall(budget, minimum)
        ranked: list[tuple[Excerpt, float]] = []
        seen_content: set[tuple[str, str]] = set()
        for unit, score in self.ranker.rank(query, units):
            key = (unit.artifact_id, unit.sha256)
            if key not in seen_content:
                ranked.append((unit, score))
                seen_content.add(key)
        sources: dict[str, list[tuple[Excerpt, float]]] = defaultdict(list)
        for unit, score in ranked:
            sources[unit.artifact_id].append((unit, score))
        share = max(0, (budget - minimum) // max(1, len(sources)))

        def include(unit: Excerpt, allowance: int | None = None) -> bool:
            if unit.citation in selected_ids:
                return False
            previous = self.counter.count(projection(selected).to_json())
            cost = self.counter.count(projection([*selected, unit]).to_json())
            if cost > budget or (allowance is not None and cost - previous > allowance):
                return False
            selected.append(unit)
            selected_ids.add(unit.citation)
            return True

        for candidates in sources.values():
            for unit, _score in candidates:
                if include(unit, share):
                    break
        scores = {unit.citation: score for unit, score in ranked}
        ranked = ranked[: self.candidate_limit]
        ranked.sort(
            key=lambda item: (
                -item[1] / max(1, self.counter.count(item[0].text)),
                item[0].source,
                item[0].ordinal,
            )
        )
        for unit, _score in ranked:
            include(unit)
        selected.sort(
            key=lambda unit: (
                -scores[unit.citation] / max(1, self.counter.count(unit.text)),
                unit.source,
                unit.ordinal,
                unit.artifact_id,
            )
        )
        pack = projection(selected)
        final_cost = self.counter.count(pack.to_json())
        while final_cost > budget and selected:
            selected.pop()
            pack = projection(selected)
            final_cost = self.counter.count(pack.to_json())
        if final_cost > budget:
            raise BudgetTooSmall(budget, final_cost)
        return pack
