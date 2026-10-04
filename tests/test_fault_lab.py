import pytest

from benchmarks.fault_lab import incident
from evidencepack import EvidenceService, Scope


@pytest.mark.parametrize("family", ["port_mismatch", "path_mismatch", "token_mismatch"])
def test_live_fault_and_repair_are_observed_over_http(repository, family):
    with incident(family, 3, traffic_requests=12) as live:
        assert live.before_status == 502
        assert family not in live.case.query
        service = EvidenceService(repository, Scope("lab", family))
        artifacts = [service.capture(output.source, output.text) for output in live.case.outputs]
        pack = service.pack(live.case.query, [artifact.id for artifact in artifacts], budget=3000)
        repair = live.try_repair("\n".join(unit.text for unit in pack.excerpts))
        assert repair["diagnosis"] == family
        assert repair["after"] == 200
        assert repair["repaired"]
        assert live.try_repair("")["after"] == 502
