import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from evidencepack import (
    BudgetTooSmall,
    Deleted,
    EvidenceService,
    IntegrityError,
    NotFound,
    Pinned,
    Scope,
    SQLiteRepository,
)


def test_capture_recovers_exact_unicode_newlines_and_invocation_identity(evidence):
    text = "日志\r\nαβ\ntrailing newline\n"
    first = evidence.capture("probe", text)
    second = evidence.capture("probe", text)
    assert first.id != second.id
    assert first.sha256 == second.sha256
    assert evidence.raw(first.id).text.encode() == text.encode()


def test_concurrent_same_source_outputs_do_not_overwrite(evidence):
    with ThreadPoolExecutor(max_workers=8) as pool:
        artifacts = list(pool.map(lambda i: evidence.capture("same", f"invocation={i}"), range(32)))
    assert len({artifact.id for artifact in artifacts}) == 32
    assert {evidence.raw(artifact.id).text for artifact in artifacts} == {
        f"invocation={i}" for i in range(32)
    }


@pytest.mark.parametrize("scope", [Scope("tenant-b", "session-a"), Scope("tenant-a", "session-b")])
def test_every_reference_operation_is_scope_bound(repository, evidence, scope):
    artifact = evidence.capture("probe", "ERROR endpoint refused\n")
    pack = evidence.pack("endpoint refused", [artifact.id], budget=1800)
    outsider = EvidenceService(repository, scope)
    with pytest.raises(NotFound):
        outsider.raw(artifact.id)
    with pytest.raises(NotFound):
        outsider.pack("endpoint", [artifact.id])
    with pytest.raises(NotFound):
        outsider.read(artifact.id, "L1-L1")
    with pytest.raises(NotFound):
        outsider.delete(artifact.id, force=True)
    with pytest.raises(NotFound):
        outsider.release(pack.receipt)
    assert outsider.collect(before=artifact.created_at + 1) == 0
    assert outsider.verify(pack.receipt, pack.excerpts[0].citation, "endpoint refused").reason == (
        "unknown_receipt"
    )


def test_archived_but_unexposed_quote_is_rejected(evidence, repository):
    artifact = evidence.capture("logs", "ERROR target broken\nnormal\nnormal\nSECRET unexposed\n")
    receipt = evidence.read(artifact.id, "L1-L1", budget=1200)
    unseen = repository.resolve(evidence.scope, artifact.id, "L4-L4")
    assert not evidence.verify(receipt.receipt, unseen.citation, "SECRET unexposed").valid
    assert (
        evidence.verify(receipt.receipt, unseen.citation, "SECRET unexposed").reason
        == "not_exposed"
    )
    exposed = receipt.excerpts[0]
    assert evidence.verify(receipt.receipt, exposed.citation, "target broken").valid
    assert evidence.verify(receipt.receipt, exposed.citation, "target repaired").reason == (
        "quote_mismatch"
    )
    assert evidence.verify(receipt.receipt, exposed.citation, "  ").reason == "empty_quote"


def test_receipts_survive_process_restart(tmp_path):
    vault = tmp_path / "evidence.sqlite"
    first = EvidenceService(SQLiteRepository(vault), Scope("t", "s"))
    artifact = first.capture("test", "ERROR restart failed\n")
    pack = first.pack("restart", [artifact.id], budget=1600)
    second = EvidenceService(SQLiteRepository(vault), Scope("t", "s"))
    assert second.verify(pack.receipt, pack.excerpts[0].citation, "restart failed").valid
    assert second.raw(artifact.id).text == artifact.text


def test_live_receipt_blocks_collection_and_explicit_deletion(evidence):
    artifact = evidence.capture("probe", "ERROR healthy endpoint unavailable")
    pack = evidence.pack("endpoint", [artifact.id], budget=1800)
    assert evidence.collect(before=artifact.created_at + 1) == 0
    with pytest.raises(Pinned):
        evidence.delete(artifact.id)
    evidence.release(pack.receipt)
    assert evidence.verify(pack.receipt, pack.excerpts[0].citation, "unavailable").valid
    assert evidence.collect(before=artifact.created_at + 1) == 1
    with pytest.raises(Deleted):
        evidence.raw(artifact.id)
    assert evidence.verify(pack.receipt, pack.excerpts[0].citation, "unavailable").reason == (
        "artifact_deleted"
    )


def test_two_receipts_have_independent_retention_pins(evidence):
    artifact = evidence.capture("probe", "ERROR service failure")
    first = evidence.pack("service", [artifact.id], budget=1800)
    second = evidence.read(artifact.id, "L1-L1", budget=1800)
    evidence.release(first.receipt)
    assert evidence.collect(before=artifact.created_at + 1) == 0
    evidence.release(second.receipt)
    assert evidence.collect(before=artifact.created_at + 1) == 1


def test_forced_deletion_invalidates_dependent_receipts(evidence, repository):
    artifact = evidence.capture("probe", "private payload")
    pack = evidence.read(artifact.id, "L1-L1", budget=1800)
    evidence.delete(artifact.id, force=True)
    assert evidence.verify(pack.receipt, pack.excerpts[0].citation, "private").reason == (
        "artifact_deleted"
    )
    with sqlite3.connect(repository.path) as db:
        assert db.execute("SELECT text FROM artifacts").fetchone()[0] == ""
        assert db.execute("SELECT text FROM units").fetchone()[0] == ""


@pytest.mark.parametrize("table", ["artifacts", "units"])
def test_digest_tampering_fails_closed(evidence, repository, table):
    artifact = evidence.capture("probe", "ERROR authentic")
    pack = evidence.pack("authentic", [artifact.id], budget=1800)
    with sqlite3.connect(repository.path) as db:
        db.execute(f"UPDATE {table} SET text='forged'")
    assert evidence.verify(pack.receipt, pack.excerpts[0].citation, "forged").reason == (
        "integrity_error"
    )
    with pytest.raises(IntegrityError):
        evidence.pack("forged", [artifact.id])


def test_forged_projection_cannot_be_committed(evidence, repository):
    artifact = evidence.capture("probe", "ERROR authentic")
    pack = evidence.pack("authentic", [artifact.id], budget=1800)
    altered = replace(pack.excerpts[0], text="forged")
    with pytest.raises(IntegrityError):
        repository.record(evidence.scope, replace(pack, receipt="p_forged", excerpts=(altered,)))


def test_gc_between_selection_and_receipt_commit_never_returns_stale_pack(evidence, repository):
    artifact = evidence.capture("probe", "ERROR fail")
    units = repository.units(evidence.scope, (artifact.id,))
    pack = evidence.packer.build("fail", units, 1800)
    evidence.collect(before=artifact.created_at + 1)
    with pytest.raises(Deleted):
        repository.record(evidence.scope, pack)


def test_json_recovers_raw_and_escaped_pointers(evidence):
    raw = '{ "records": [{"name":"正常"}, {"a/b":{"~key":7}}], "empty": [] }\n'
    artifact = evidence.capture("json", raw, media_type="json")
    assert evidence.raw(artifact.id).text == raw
    pack = evidence.read(artifact.id, "J:/records/1/a~1b/~0key", budget=1800)
    assert json.loads(pack.excerpts[0].text) == 7
    assert evidence.verify(pack.receipt, pack.excerpts[0].citation, "7").valid


@pytest.mark.parametrize("payload", ['{"key":1,"key":2}', "[NaN]", "[Infinity]", "{broken"])
def test_ambiguous_or_invalid_json_capture_is_atomic(evidence, repository, payload):
    with pytest.raises(ValueError):
        evidence.capture("json", payload, media_type="json")
    with sqlite3.connect(repository.path) as db:
        assert db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0


@pytest.mark.parametrize("locator", ["L0-L1", "L2-L1", "L1-L4", "../../secret", "L1-2"])
def test_invalid_text_locators_do_not_read_other_material(evidence, locator):
    artifact = evidence.capture("probe", "one\ntwo\nthree")
    with pytest.raises(ValueError):
        evidence.read(artifact.id, locator)


@pytest.mark.parametrize("locator", ["J:/a/01", "J:/a/-1", "J:/a/99", "J:/a/~2", "J:a"])
def test_invalid_json_locators_are_rejected(evidence, locator):
    artifact = evidence.capture("json", '{"a":[1,2]}', media_type="json")
    with pytest.raises(ValueError):
        evidence.read(artifact.id, locator)


def test_explicit_large_reread_errors_instead_of_slicing(evidence):
    artifact = evidence.capture("single", "x" * 3000)
    with pytest.raises(BudgetTooSmall) as error:
        evidence.read(artifact.id, "L1-L1", budget=1000)
    assert error.value.required > error.value.budget
