"""Transactional evidence storage with scoped references and explicit lifetimes."""

from __future__ import annotations

import hashlib
import math
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4

from .domain import (
    Artifact,
    Deleted,
    Excerpt,
    IntegrityError,
    MediaType,
    NotFound,
    Pack,
    Pinned,
    Scope,
    Verdict,
)
from .selection import extract, segments

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, session TEXT NOT NULL,
    source TEXT NOT NULL, text TEXT NOT NULL, media_type TEXT NOT NULL,
    sha256 TEXT NOT NULL, created_at REAL NOT NULL, deleted_at REAL
);
CREATE INDEX IF NOT EXISTS artifact_scope ON artifacts(tenant, session);
CREATE TABLE IF NOT EXISTS units (
    citation TEXT PRIMARY KEY, artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    locator TEXT NOT NULL, text TEXT NOT NULL, sha256 TEXT NOT NULL, ordinal INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS unit_artifact ON units(artifact_id);
CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, session TEXT NOT NULL,
    created_at REAL NOT NULL, active INTEGER NOT NULL DEFAULT 1, invalid_reason TEXT
);
CREATE TABLE IF NOT EXISTS exposure (
    receipt TEXT NOT NULL REFERENCES receipts(id),
    citation TEXT NOT NULL REFERENCES units(citation),
    PRIMARY KEY(receipt, citation)
);
CREATE INDEX IF NOT EXISTS exposure_citation ON exposure(citation);
"""


def digest(text: str) -> str:
    """Hash exact UTF-8 bytes, including whitespace and trailing newlines."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SQLiteRepository:
    """A host-owned local vault; every public operation requires an explicit scope."""

    def __init__(self, path: str | Path, *, max_capture_bytes: int = 32 * 1024 * 1024) -> None:
        self.path = Path(path)
        if str(path) == ":memory:":
            raise ValueError("Use a filesystem vault; operations have independent connections")
        if max_capture_bytes < 1:
            raise ValueError("max_capture_bytes must be positive")
        self.max_capture_bytes = max_capture_bytes
        parent_exists = self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not parent_exists:
            self.path.parent.chmod(0o700)
        with sqlite3.connect(self.path, timeout=30) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError(f"Unsupported vault schema version: {version}")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(_SCHEMA)
            db.execute("PRAGMA user_version=1")
        self.path.chmod(0o600)

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _get(self, db: sqlite3.Connection, scope: Scope, artifact_id: str) -> Artifact:
        row = db.execute(
            "SELECT * FROM artifacts WHERE id=? AND tenant=? AND session=?",
            (artifact_id, scope.tenant, scope.session),
        ).fetchone()
        if row is None:
            raise NotFound("Artifact is unavailable in this scope")
        if row["deleted_at"] is not None:
            raise Deleted("Artifact was explicitly deleted")
        if digest(row["text"]) != row["sha256"]:
            raise IntegrityError("Artifact digest mismatch")
        return Artifact(
            row["id"],
            row["source"],
            row["text"],
            cast(MediaType, row["media_type"]),
            row["sha256"],
            row["created_at"],
        )

    @staticmethod
    def _unit(row: sqlite3.Row) -> Excerpt:
        if digest(row["text"]) != row["sha256"]:
            raise IntegrityError("Excerpt digest mismatch")
        return Excerpt(
            row["citation"],
            row["artifact_id"],
            row["source"],
            row["locator"],
            row["text"],
            row["sha256"],
            row["ordinal"],
        )

    def _insert_unit(
        self, db: sqlite3.Connection, artifact: Artifact, locator: str, text: str, ordinal: int
    ) -> Excerpt:
        sha = digest(text)
        citation = "e_" + digest(f"{artifact.id}\0{locator}\0{sha}")[:24]
        db.execute(
            "INSERT OR IGNORE INTO units VALUES(?,?,?,?,?,?)",
            (citation, artifact.id, locator, text, sha, ordinal),
        )
        row = db.execute(
            "SELECT u.*, a.source FROM units u JOIN artifacts a ON a.id=u.artifact_id "
            "WHERE citation=?",
            (citation,),
        ).fetchone()
        assert row is not None
        if (row["artifact_id"], row["locator"], row["sha256"]) != (artifact.id, locator, sha):
            raise IntegrityError("Citation identity collision")
        return self._unit(row)

    def put(self, scope: Scope, source: str, text: str, media_type: MediaType = "text") -> Artifact:
        """Capture one invocation and its complete units in the same write transaction."""
        if not isinstance(source, str) or not source.strip() or len(source) > 200:
            raise ValueError("source must be nonblank and at most 200 characters")
        if not isinstance(text, str):
            raise TypeError("Evidence must be a UTF-8-compatible string")
        if len(text.encode("utf-8")) > self.max_capture_bytes:
            raise ValueError("Capture exceeds the configured byte limit")
        projections = segments(text, media_type)
        artifact = Artifact("a_" + uuid4().hex, source, text, media_type, digest(text), time.time())
        with self._transaction(write=True) as db:
            db.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,NULL)",
                (
                    artifact.id,
                    scope.tenant,
                    scope.session,
                    source,
                    text,
                    media_type,
                    artifact.sha256,
                    artifact.created_at,
                ),
            )
            for ordinal, segment in enumerate(projections):
                self._insert_unit(db, artifact, segment.locator, segment.text, ordinal)
        return artifact

    def get(self, scope: Scope, artifact_id: str) -> Artifact:
        """Recover exact captured text after scope, lifetime and digest checks."""
        with self._transaction() as db:
            return self._get(db, scope, artifact_id)

    def units(self, scope: Scope, artifact_ids: tuple[str, ...]) -> tuple[Excerpt, ...]:
        """Load indexed units from the requested captures, failing closed on any missing ID."""
        result: list[Excerpt] = []
        with self._transaction() as db:
            for artifact_id in dict.fromkeys(artifact_ids):
                self._get(db, scope, artifact_id)
                rows = db.execute(
                    "SELECT u.*, a.source FROM units u JOIN artifacts a ON a.id=u.artifact_id "
                    "WHERE artifact_id=? AND ordinal>=0 ORDER BY ordinal",
                    (artifact_id,),
                ).fetchall()
                result.extend(self._unit(row) for row in rows)
        return tuple(result)

    def resolve(self, scope: Scope, artifact_id: str, locator: str) -> Excerpt:
        """Register a precise reread projection, preserving the original archive."""
        with self._transaction(write=True) as db:
            artifact = self._get(db, scope, artifact_id)
            text = extract(artifact.text, artifact.media_type, locator)
            return self._insert_unit(db, artifact, locator, text, -1)

    def record(self, scope: Scope, pack: Pack) -> None:
        """Commit exposure only when every displayed unit is exact and still live."""
        if len({unit.citation for unit in pack.excerpts}) != len(pack.excerpts):
            raise ValueError("A pack cannot expose a citation twice")
        with self._transaction(write=True) as db:
            for artifact_id in {unit.artifact_id for unit in pack.excerpts}:
                self._get(db, scope, artifact_id)
            for unit in pack.excerpts:
                row = db.execute(
                    "SELECT u.*, a.source FROM units u JOIN artifacts a ON a.id=u.artifact_id "
                    "WHERE citation=?",
                    (unit.citation,),
                ).fetchone()
                if row is None or self._unit(row) != unit:
                    raise IntegrityError("Pack unit does not match the immutable vault")
            db.execute(
                "INSERT INTO receipts VALUES(?,?,?,?,1,NULL)",
                (pack.receipt, scope.tenant, scope.session, time.time()),
            )
            db.executemany(
                "INSERT INTO exposure VALUES(?,?)",
                ((pack.receipt, unit.citation) for unit in pack.excerpts),
            )

    def verify(self, scope: Scope, receipt: str, citation: str, quote: str) -> Verdict:
        """Require a live, unaltered unit in this receipt and an exact nonempty quotation."""
        with self._transaction() as db:
            row = db.execute(
                "SELECT * FROM receipts WHERE id=? AND tenant=? AND session=?",
                (receipt, scope.tenant, scope.session),
            ).fetchone()
            if row is None:
                return Verdict(False, "unknown_receipt")
            if row["invalid_reason"]:
                return Verdict(False, row["invalid_reason"])
            unit_row = db.execute(
                "SELECT u.*, a.source FROM exposure e JOIN units u ON u.citation=e.citation "
                "JOIN artifacts a ON a.id=u.artifact_id WHERE e.receipt=? AND e.citation=?",
                (receipt, citation),
            ).fetchone()
            if unit_row is None:
                return Verdict(False, "not_exposed")
            if not isinstance(quote, str) or not quote.strip():
                return Verdict(False, "empty_quote")
            try:
                self._get(db, scope, unit_row["artifact_id"])
                unit = self._unit(unit_row)
            except (IntegrityError, Deleted, NotFound):
                return Verdict(False, "integrity_error")
            if quote not in unit.text:
                return Verdict(False, "quote_mismatch")
            return Verdict(True, "exact_exposed_quote")

    def release(self, scope: Scope, receipt: str) -> None:
        """Remove this receipt's retention pin; verification lasts until evidence deletion."""
        with self._transaction(write=True) as db:
            cursor = db.execute(
                "UPDATE receipts SET active=0 WHERE id=? AND tenant=? AND session=?",
                (receipt, scope.tenant, scope.session),
            )
            if not cursor.rowcount:
                raise NotFound("Receipt is unavailable in this scope")

    @staticmethod
    def _tombstone(db: sqlite3.Connection, artifact_id: str) -> None:
        db.execute(
            "UPDATE receipts SET active=0, invalid_reason='artifact_deleted' WHERE id IN "
            "(SELECT e.receipt FROM exposure e JOIN units u ON e.citation=u.citation "
            "WHERE u.artifact_id=?)",
            (artifact_id,),
        )
        db.execute("UPDATE units SET text='' WHERE artifact_id=?", (artifact_id,))
        db.execute(
            "UPDATE artifacts SET text='', deleted_at=? WHERE id=?",
            (time.time(), artifact_id),
        )

    def delete(self, scope: Scope, artifact_id: str, *, force: bool = False) -> None:
        """Delete captured payloads; forcing deletion also invalidates dependent receipts."""
        with self._transaction(write=True) as db:
            self._get(db, scope, artifact_id)
            pinned = db.execute(
                "SELECT 1 FROM receipts r JOIN exposure e ON r.id=e.receipt "
                "JOIN units u ON u.citation=e.citation "
                "WHERE u.artifact_id=? AND r.active=1 LIMIT 1",
                (artifact_id,),
            ).fetchone()
            if pinned and not force:
                raise Pinned("Release active receipts before deleting evidence, or use force=True")
            self._tombstone(db, artifact_id)

    def collect(self, scope: Scope, before: float) -> int:
        """Tombstone old captures only when no active receipt depends on them."""
        if not math.isfinite(before):
            raise ValueError("Collection cutoff must be finite")
        with self._transaction(write=True) as db:
            rows = db.execute(
                "SELECT a.id FROM artifacts a WHERE tenant=? AND session=? "
                "AND deleted_at IS NULL AND created_at<? AND NOT EXISTS "
                "(SELECT 1 FROM units u JOIN exposure e ON u.citation=e.citation "
                "JOIN receipts r ON r.id=e.receipt WHERE u.artifact_id=a.id AND r.active=1)",
                (scope.tenant, scope.session, before),
            ).fetchall()
            for row in rows:
                self._tombstone(db, row["id"])
            return len(rows)
