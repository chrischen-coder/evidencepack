"""Seeded stress tasks with grading labels kept out of retrieval inputs."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from typing import Any

from evidencepack.domain import MediaType


@dataclass(frozen=True)
class Output:
    source: str
    text: str
    media_type: MediaType = "text"


@dataclass(frozen=True)
class Case:
    id: str
    family: str
    query: str
    outputs: tuple[Output, ...]
    required_quotes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Export inputs and separately named grading targets for reproducible evaluation."""
        return asdict(self)


def generated_cases(seed: int = 20261004, count: int = 20) -> tuple[Case, ...]:
    """Exercise positions, complete JSON records, multiple sources and deliberate misses."""
    rng = random.Random(seed)
    result: list[Case] = []
    for i in range(count):
        request = f"target-{i:04d}"
        text = [
            f"INFO request=noise-{j:04d} status=200 elapsed_ms={rng.randrange(50)}\n"
            for j in range(700)
        ]
        position = rng.randrange(70, 630)
        failure = f"ERROR request={request} upstream=checkout code=ECONNREFUSED port={7500 + i}\n"
        text[position] = failure
        result.append(
            Case(
                f"text-{i}",
                "middle-log",
                f"Find the failed checkout upstream request {request}.",
                (Output("requests", "".join(text)),),
                (failure.strip(),),
            )
        )
        records = [{"request": f"noise-{j}", "status": "healthy", "code": 200} for j in range(220)]
        record = {"request": request, "status": "failed", "code": "EPIPE", "attempt": i + 2}
        records[rng.randrange(30, 190)] = record
        result.append(
            Case(
                f"json-{i}",
                "json-record",
                f"Find the failed request {request} and its retry attempt.",
                (Output("records", json.dumps(records), "json"),),
                (json.dumps(record, sort_keys=True, separators=(",", ":")),),
            )
        )
        noise = [
            f"ERROR checkout upstream connection refused request={request} attempt={j}\n"
            for j in range(200)
        ]
        config = f"CONFIG checkout upstream_port={7600 + i}\n"
        listener = f"LISTENER checkout bound_port={7700 + i}\n"
        result.append(
            Case(
                f"chain-{i}",
                "cross-source",
                f"Why is checkout upstream connection refused for request {request}? "
                "Compare configuration "
                "and listener before proposing a repair.",
                (
                    Output("traffic", "".join(noise)),
                    Output("config", config),
                    Output("runtime", listener),
                ),
                (config.strip(), listener.strip(), noise[0].strip()),
            )
        )
    for i in range(5):
        opaque = {"payload": "z" * 20000, "signal": "critical", "id": f"oversized-{i}"}
        result.append(
            Case(
                f"oversized-{i}",
                "oversized-record",
                f"Find the critical signal for oversized-{i}.",
                (Output("large-record", json.dumps([opaque]), "json"),),
                ('"signal":"critical"',),
            )
        )
    return tuple(result)
