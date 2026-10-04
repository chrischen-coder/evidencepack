"""Reproducible retention, provenance and live-repair measurements."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from evidencepack import ByteCounter, EvidenceService, Scope, SQLiteRepository, TiktokenCounter
from evidencepack.domain import Counter

from .cases import Case, generated_cases
from .fault_lab import Incident, incident
from .policies import POLICIES, baseline_pack
from .provenance import source_digest


def evaluate(
    case: Case,
    repository: SQLiteRepository,
    counter: Counter,
    budget: int,
    live: Incident | None = None,
) -> list[dict[str, Any]]:
    """Keep labels outside the policies and give every arm the same captures and allowance."""
    service = EvidenceService(repository, Scope("benchmark", case.id), counter=counter)
    capture_start = time.perf_counter()
    artifacts = [
        service.capture(output.source, output.text, media_type=output.media_type)
        for output in case.outputs
    ]
    capture_ms = (time.perf_counter() - capture_start) * 1000
    ids = [artifact.id for artifact in artifacts]
    units = repository.units(service.scope, tuple(ids))
    raw_cost = counter.count(
        json.dumps([{"source": o.source, "text": o.text} for o in case.outputs], ensure_ascii=False)
    )
    rows = []
    for policy in POLICIES:
        started = time.perf_counter()
        if policy == "evidencepack":
            pack = service.pack(case.query, ids, budget=budget)
        else:
            pack = baseline_pack(policy, case.query, units, counter, budget)
            repository.record(service.scope, pack)
        elapsed = (time.perf_counter() - started) * 1000
        text = "\n".join(unit.text for unit in pack.excerpts)
        retained = [quote in text for quote in case.required_quotes]
        exact_valid = all(
            service.verify(pack.receipt, unit.citation, unit.text).valid
            for unit in pack.excerpts
            if unit.text.strip()
        )
        fabricated_rejected = all(
            not service.verify(pack.receipt, unit.citation, "THIS QUOTE DOES NOT EXIST 8bc91").valid
            for unit in pack.excerpts
        )
        used = counter.count(pack.to_json())
        if used > budget:
            raise AssertionError(f"{policy} exceeded the common allowance")
        row = {
            "case": case.id,
            "family": case.family,
            "policy": policy,
            "budget": budget,
            "used": used,
            "raw_cost": raw_cost,
            "required": len(retained),
            "retained": sum(retained),
            "complete": all(retained),
            "latency_ms": round(elapsed, 3),
            "capture_ms": round(capture_ms, 3),
            "sources": len({unit.artifact_id for unit in pack.excerpts}),
            "quote_checks_pass": exact_valid and fabricated_rejected,
            "positive_quote_checks": sum(bool(u.text.strip()) for u in pack.excerpts),
            "fabricated_quote_checks": len(pack.excerpts),
            "pack": json.loads(pack.to_json()),
        }
        if live:
            row["repair"] = live.try_repair(text)
        rows.append(row)
        service.release(pack.receipt)
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Report denominators, complete-chain retention and measured selection costs."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["policy"]].append(row)
    result: dict[str, Any] = {}
    for policy, group in grouped.items():
        latencies = sorted(row["latency_ms"] for row in group)
        summary = {
            "cases": len(group),
            "complete": sum(row["complete"] for row in group),
            "complete_rate": round(sum(row["complete"] for row in group) / len(group), 4),
            "retained_quotes": sum(row["retained"] for row in group),
            "required_quotes": sum(row["required"] for row in group),
            "mean_used": round(statistics.mean(row["used"] for row in group), 1),
            "mean_raw_cost": round(statistics.mean(row["raw_cost"] for row in group), 1),
            "median_ms": round(statistics.median(latencies), 3),
            "p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
            "budget_violations": sum(row["used"] > row["budget"] for row in group),
            "quote_check_failures": sum(not row["quote_checks_pass"] for row in group),
            "positive_quote_checks": sum(row["positive_quote_checks"] for row in group),
            "fabricated_quote_checks": sum(row["fabricated_quote_checks"] for row in group),
        }
        if "repair" in group[0]:
            summary["repairs"] = sum(row["repair"]["repaired"] for row in group)
        result[policy] = summary
    return result


def main() -> None:
    """Run seeded stress and real loopback faults, persisting all evidence projections."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("benchmark-runs/local"))
    parser.add_argument("--budget", type=int, default=2000)
    parser.add_argument("--encoding")
    parser.add_argument("--stress-count", type=int, default=20)
    parser.add_argument("--real-per-family", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    counter: Counter = TiktokenCounter(args.encoding) if args.encoding else ByteCounter()
    stress_rows: list[dict[str, Any]] = []
    real_rows: list[dict[str, Any]] = []
    cases: list[Case] = []
    with TemporaryDirectory(prefix="evidencepack-benchmark-") as directory:
        repository = SQLiteRepository(Path(directory) / "evidence.sqlite")
        for case in generated_cases(count=args.stress_count):
            cases.append(case)
            stress_rows.extend(evaluate(case, repository, counter, args.budget))
        for family in ("port_mismatch", "path_mismatch", "token_mismatch"):
            for index in range(args.real_per_family):
                with incident(family, index) as live:
                    cases.append(live.case)
                    real_rows.extend(evaluate(live.case, repository, counter, args.budget, live))
                print(f"captured {family} {index + 1}/{args.real_per_family}", flush=True)
    report = {
        "date": "2026-10-04",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "counter": counter.name,
        "budget": args.budget,
        "seed": 20261004,
        "stress": summarize(stress_rows),
        "real_faults": summarize(real_rows),
        "model_evaluation": "not run by this script",
        "source_sha256": source_digest(),
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    with (args.output / "cases.jsonl").open("w") as file:
        for case in cases:
            file.write(json.dumps(case.as_dict(), ensure_ascii=False) + "\n")
    with (args.output / "rows.jsonl").open("w") as file:
        for row in [*stress_rows, *real_rows]:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
