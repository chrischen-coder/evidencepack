"""A thin CLI adapter; JSON projections have the same contract as the Python API."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import cast

from .counters import ByteCounter, TiktokenCounter
from .domain import Counter, EvidenceError, MediaType, Scope
from .repository import SQLiteRepository
from .service import EvidenceService


def parser() -> argparse.ArgumentParser:
    """Describe host-owned scope once rather than accepting it inside individual tools."""
    root = argparse.ArgumentParser(prog="evidencepack")
    root.add_argument("--vault", default=".evidencepack/vault.sqlite")
    root.add_argument("--tenant", required=True)
    root.add_argument("--session", required=True)
    root.add_argument("--encoding", help="Optional tiktoken encoding; default budgets use bytes")
    commands = root.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture", help="Archive a UTF-8 file or stdin ('-')")
    capture.add_argument("file")
    capture.add_argument("--source", required=True)
    capture.add_argument("--type", choices=("text", "json"), default="text")
    pack = commands.add_parser("pack", help="Return a task-specific bounded projection")
    pack.add_argument("artifacts", nargs="+")
    pack.add_argument("--query", required=True)
    pack.add_argument("--budget", type=int, default=4096)
    read = commands.add_parser("read", help="Reread L1-L3 or J:/records/0 with a new receipt")
    read.add_argument("artifact")
    read.add_argument("locator")
    read.add_argument("--budget", type=int, default=4096)
    raw = commands.add_parser("raw", help="Export exact input without a model budget")
    raw.add_argument("artifact")
    verify = commands.add_parser("verify", help="Validate a quotation against its exposure receipt")
    verify.add_argument("receipt")
    verify.add_argument("citation")
    verify.add_argument("quote")
    release = commands.add_parser("release", help="Remove one receipt's retention pin")
    release.add_argument("receipt")
    delete = commands.add_parser("delete", help="Tombstone an artifact and its payload")
    delete.add_argument("artifact")
    delete.add_argument("--force", action="store_true")
    collect = commands.add_parser(
        "collect", help="Tombstone unpinned captures older than a Unix time"
    )
    collect.add_argument("--before", type=float, required=True)
    serve = commands.add_parser("serve", help="Run the optional MCP stdio adapter")
    serve.add_argument("--max-budget", type=int, default=8192)
    return root


def main(argv: list[str] | None = None) -> int:
    """Run one operation; rejected provenance exits 1 and typed operational failures exit 2."""
    args = parser().parse_args(argv)
    try:
        counter: Counter = TiktokenCounter(args.encoding) if args.encoding else ByteCounter()
        repository = SQLiteRepository(args.vault)
        service = EvidenceService(repository, Scope(args.tenant, args.session), counter=counter)
        result: object
        if args.command == "capture":
            if args.file == "-":
                payload = sys.stdin.buffer.read(repository.max_capture_bytes + 1)
            else:
                with Path(args.file).open("rb") as file:
                    payload = file.read(repository.max_capture_bytes + 1)
            if len(payload) > repository.max_capture_bytes:
                raise ValueError("Input exceeds the configured capture limit")
            artifact = service.capture(
                args.source, payload.decode("utf-8"), media_type=cast(MediaType, args.type)
            )
            result = {
                "artifact": artifact.id,
                "source": artifact.source,
                "sha256": artifact.sha256,
                "bytes": len(payload),
            }
        elif args.command == "pack":
            print(service.pack(args.query, args.artifacts, budget=args.budget).to_json())
            return 0
        elif args.command == "read":
            print(service.read(args.artifact, args.locator, budget=args.budget).to_json())
            return 0
        elif args.command == "raw":
            sys.stdout.buffer.write(service.raw(args.artifact).text.encode("utf-8"))
            return 0
        elif args.command == "verify":
            verdict = service.verify(args.receipt, args.citation, args.quote)
            print(json.dumps(asdict(verdict)))
            return 0 if verdict.valid else 1
        elif args.command == "release":
            service.release(args.receipt)
            result = {"released": args.receipt}
        elif args.command == "delete":
            service.delete(args.artifact, force=args.force)
            result = {"deleted": args.artifact}
        elif args.command == "collect":
            result = {"collected": service.collect(before=args.before)}
        else:
            from .mcp_server import create_server

            create_server(service, max_budget=args.max_budget).run(transport="stdio")
            return 0
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (EvidenceError, ValueError, TypeError, OSError, ImportError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
