from pathlib import Path

import pytest

from evidencepack import EvidenceService, Scope, SQLiteRepository


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteRepository:
    return SQLiteRepository(tmp_path / "vault" / "evidence.sqlite")


@pytest.fixture
def evidence(repository: SQLiteRepository) -> EvidenceService:
    return EvidenceService(repository, Scope("tenant-a", "session-a"))
