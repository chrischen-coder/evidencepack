"""Run one actual loopback fault and show the evidence behind a measured repair."""

from pathlib import Path
from tempfile import TemporaryDirectory

from benchmarks.fault_lab import incident
from evidencepack import EvidenceService, Scope, SQLiteRepository


def main() -> None:
    """Use the rule-based lab to demonstrate evidence transport without requiring a model."""
    with TemporaryDirectory() as directory, incident("port_mismatch", 0) as live:
        service = EvidenceService(
            SQLiteRepository(Path(directory) / "vault.sqlite"), Scope("demo", "incident")
        )
        artifacts = [service.capture(o.source, o.text) for o in live.case.outputs]
        pack = service.pack(live.case.query, [a.id for a in artifacts], budget=2400)
        print(pack.to_json())
        print(live.try_repair("\n".join(unit.text for unit in pack.excerpts)))
        unit = next(unit for unit in pack.excerpts if unit.source == "configuration")
        print("captured quotation:", service.verify(pack.receipt, unit.citation, unit.text))
        print("invented quotation:", service.verify(pack.receipt, unit.citation, "port=99999"))
        service.release(pack.receipt)


if __name__ == "__main__":
    main()
