"""Show the library's inputs and outputs without an LLM, GPU or external service."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from evidencepack import EvidenceService, Scope, SQLiteRepository


def main() -> None:
    """Pack generated tool outputs, print their model payload and check two preset quotes."""
    query = "Diagnose checkout HTTP 502. Compare upstream_port to backend bound_port."
    noise = "INFO checkout /ping status=200\n" * 900
    outputs = {
        "application-log": noise
        + "ERROR checkout upstream connection refused status=502\n"
        + noise,
        "configuration": "CONFIG upstream_port=8080 health_path=/health\n",
        "backend-runtime": "LISTENER bound_port=8081 health_path=/health\n",
    }
    with TemporaryDirectory(prefix="evidencepack-quickstart-") as directory:
        service = EvidenceService(
            SQLiteRepository(Path(directory) / "vault.sqlite"), Scope("demo", "incident-1")
        )
        artifacts = [service.capture(source, text) for source, text in outputs.items()]
        pack = service.pack(query, [artifact.id for artifact in artifacts], budget=2000)
        print("INPUT: question + three generated tool outputs + 2,000-byte allowance")
        print("Question:", query)
        print("Raw tool text bytes:", sum(len(text.encode()) for text in outputs.values()))
        print("OUTPUT 1: evidence JSON for your existing model")
        print(pack.to_json())
        print("Serialized evidence bytes:", len(pack.to_json().encode()))
        configuration = next(unit for unit in pack.excerpts if unit.source == "configuration")
        print("OUTPUT 2: exact-quote verification results")
        for quote in ("upstream_port=8080", "upstream_port=9999"):
            verdict = service.verify(pack.receipt, configuration.citation, quote)
            print(json.dumps({"quote": quote, **asdict(verdict)}))
        print("No model was called. These preset quotes demonstrate verification only.")
        service.release(pack.receipt)


if __name__ == "__main__":
    main()
