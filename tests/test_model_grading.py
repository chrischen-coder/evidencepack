import json

import pytest

from benchmarks.cases import Case, Output
from benchmarks.model_eval import grade, parse_answer
from evidencepack import EvidenceService, Scope


def observation_case():
    config = 'CONFIG {"upstream_port":7000,"health_path":"/health","auth_token":"demo"}\n'
    runtime = 'LISTENER {"bound_port":7001,"health_path":"/health","auth_token":"demo"}\n'
    return Case(
        "grading",
        "port_mismatch",
        "diagnose checkout health",
        (
            Output("traffic", "ERROR health failed\n"),
            Output("configuration", config),
            Output("backend-runtime", runtime),
        ),
        (),
    )


def test_model_grade_requires_correct_patch_and_relevant_exposed_quotes(repository):
    case = observation_case()
    service = EvidenceService(repository, Scope("eval", "case"))
    artifacts = [service.capture(o.source, o.text) for o in case.outputs]
    pack = service.pack(case.query, [a.id for a in artifacts], budget=4000)
    answer = {
        "diagnosis": "port_mismatch",
        "patch": {"upstream_port": 7001},
        "evidence": [
            {"citation": u.citation, "quote": u.text}
            for u in pack.excerpts
            if u.source in ("configuration", "backend-runtime")
        ],
    }
    assert grade(case, answer, service, pack)["grounded_success"]
    answer["patch"] = {"upstream_port": 7999}
    assert not grade(case, answer, service, pack)["grounded_success"]
    answer["patch"] = {"upstream_port": 7001}
    answer["evidence"] = []
    assert not grade(case, answer, service, pack)["grounded_success"]


def test_correct_patch_with_archived_unexposed_quote_cannot_pass(repository):
    case = observation_case()
    service = EvidenceService(repository, Scope("eval", "case"))
    artifacts = [service.capture(o.source, o.text) for o in case.outputs]
    pack = service.read(artifacts[1].id, "L1-L1", budget=1800)
    unseen = repository.resolve(service.scope, artifacts[2].id, "L1-L1")
    answer = {
        "diagnosis": "port_mismatch",
        "patch": {"upstream_port": 7001},
        "evidence": [
            {"citation": pack.excerpts[0].citation, "quote": pack.excerpts[0].text},
            {"citation": unseen.citation, "quote": unseen.text},
        ],
    }
    result = grade(case, answer, service, pack)
    assert result["correct_patch"]
    assert not result["grounded_success"]
    assert result["valid_quotes"] == 1


def test_exact_but_irrelevant_quote_does_not_support_a_patch(repository):
    case = observation_case()
    service = EvidenceService(repository, Scope("eval", "case"))
    artifacts = [service.capture(o.source, o.text) for o in case.outputs]
    pack = service.pack(case.query, [a.id for a in artifacts], budget=4000)
    answer = {
        "diagnosis": "port_mismatch",
        "patch": {"upstream_port": 7001},
        "evidence": [
            {"citation": u.citation, "quote": "health_path"}
            for u in pack.excerpts
            if u.source in ("configuration", "backend-runtime")
        ],
    }
    result = grade(case, answer, service, pack)
    assert result["all_quotes_valid"]
    assert not result["grounded_success"]


def test_answer_parser_does_not_repair_invalid_json():
    assert parse_answer('<think>reasoning</think>```json\n{"diagnosis":"unknown"}\n```') == {
        "diagnosis": "unknown"
    }
    with pytest.raises(json.JSONDecodeError):
        parse_answer('{"diagnosis": unknown}')
