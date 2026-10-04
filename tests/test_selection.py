import json
import random

import pytest

from evidencepack import (
    BudgetTooSmall,
    ByteCounter,
    EvidenceService,
    LexicalRanker,
    Scope,
    TiktokenCounter,
)


def test_mid_log_failure_is_retained_without_changing_lines(evidence):
    lines = [f"INFO request={i} healthy\n" for i in range(900)]
    lines[450] = "ERROR checkout upstream connection refused request=critical\n"
    artifact = evidence.capture("service-log", "".join(lines))
    pack = evidence.pack(
        "checkout upstream connection refused critical", [artifact.id], budget=2000
    )
    assert any(lines[450] in unit.text for unit in pack.excerpts)
    for unit in pack.excerpts:
        assert unit.text in artifact.text
        assert unit.text.endswith("\n")
    assert len(pack.to_json().encode()) <= 2000
    assert pack.omitted > 0


def test_source_coverage_survives_one_very_noisy_source(evidence):
    noisy = evidence.capture("requests", "ERROR checkout request failed upstream\n" * 150)
    cause = evidence.capture("configuration", "checkout upstream_port=7412 expected_port=7413\n")
    pack = evidence.pack("checkout upstream port", [noisy.id, cause.id], budget=1600)
    assert {unit.artifact_id for unit in pack.excerpts} == {noisy.id, cause.id}


def test_primary_evidence_precedes_alphabetically_earlier_background(evidence):
    background = evidence.capture("aaa-background", "ERROR checkout worker paused\n")
    configuration = evidence.capture(
        "zzz-configuration", "checkout upstream listener port mismatch expected=8101 actual=8102\n"
    )
    pack = evidence.pack(
        "checkout upstream listener port mismatch", [background.id, configuration.id], budget=1200
    )
    assert {unit.artifact_id for unit in pack.excerpts} == {background.id, configuration.id}
    assert pack.excerpts[0].artifact_id == configuration.id


def test_json_units_stay_parseable_and_huge_records_are_explicitly_omitted(evidence):
    records = [{"request": f"q-{i}", "status": "ok", "payload": "x" * 20} for i in range(70)]
    records[32] = {"request": "needle", "status": "failed", "code": 503}
    records[33] = {"request": "needle", "status": "failed", "payload": "x" * 20000}
    artifact = evidence.capture("records", json.dumps(records), media_type="json")
    pack = evidence.pack("needle failed 503", [artifact.id], budget=1800)
    assert any(json.loads(unit.text).get("code") == 503 for unit in pack.excerpts)
    for unit in pack.excerpts:
        assert isinstance(json.loads(unit.text), dict)
    assert pack.omitted > 0
    assert len(pack.to_json().encode()) <= 1800
    assert evidence.raw(artifact.id).text == json.dumps(records)


@pytest.mark.parametrize("budget", [100, 180, 400, 900, 1800, 4096])
def test_random_multilingual_inputs_obey_whole_pack_byte_budget(evidence, budget):
    generator = random.Random(42)
    text = "\n".join(
        "ERROR 服务 unavailable " + "".join(generator.choices("αβ汉字éabc012", k=i % 90))
        for i in range(130)
    )
    artifact = evidence.capture("unicode", text)
    try:
        pack = evidence.pack("服务 unavailable", [artifact.id], budget=budget)
    except BudgetTooSmall as error:
        assert error.required > budget
    else:
        assert ByteCounter().count(pack.to_json()) <= budget
        assert json.loads(pack.to_json())["omitted"] == pack.omitted


@pytest.mark.parametrize("budget", [40, 100, 220, 500, 1000])
def test_actual_tiktoken_budget_includes_identifiers_and_json_escaping(repository, budget):
    pytest.importorskip("tiktoken")
    counter = TiktokenCounter()
    evidence = EvidenceService(repository, Scope("t", "s"), counter=counter)
    artifact = evidence.capture("tokens", 'ERROR 引用 "quoted" \\path <|endoftext|>\n' * 100)
    try:
        pack = evidence.pack("引用 ERROR", [artifact.id], budget=budget)
    except BudgetTooSmall as error:
        assert error.required > budget
    else:
        assert counter.count(pack.to_json()) <= budget
        assert pack.counter == "tokens:cl100k_base"


def test_query_without_overlap_returns_explicit_empty_pack(repository):
    evidence = EvidenceService(
        repository, Scope("t", "s"), ranker=LexicalRanker(diagnostic_bonus=0)
    )
    artifact = evidence.capture("plain", "the quick brown fox")
    pack = evidence.pack("unrelated database", [artifact.id], budget=1000)
    assert pack.excerpts == ()
    assert pack.omitted == 1


def test_empty_input_is_recoverable(evidence):
    artifact = evidence.capture("empty", "")
    assert evidence.raw(artifact.id).text == ""
    read = evidence.read(artifact.id, "L1-L1", budget=1800)
    assert read.excerpts[0].text == ""


@pytest.mark.parametrize("budget", [True, False, 0, -10, 2.5, "2000"])
def test_invalid_budget_values_fail_before_returning_a_pack(evidence, budget):
    artifact = evidence.capture("probe", "ERROR failure")
    with pytest.raises(ValueError):
        evidence.pack("failure", [artifact.id], budget=budget)
    with pytest.raises(ValueError):
        evidence.read(artifact.id, "L1-L1", budget=budget)


def test_duplicate_units_do_not_consume_the_entire_projection(evidence):
    noisy = evidence.capture("noise", "ERROR checkout upstream\n" * 3000)
    cause = evidence.capture("cause", "checkout upstream points to an absent listener\n")
    pack = evidence.pack("checkout upstream listener", [noisy.id, cause.id], budget=1800)
    noisy_units = [unit for unit in pack.excerpts if unit.artifact_id == noisy.id]
    assert len(noisy_units) <= 1
    assert any(unit.artifact_id == cause.id for unit in pack.excerpts)
