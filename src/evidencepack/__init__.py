"""Budgeted tool evidence with scoped recovery and verifiable exposure receipts."""

from .counters import ByteCounter, HuggingFaceCounter, TiktokenCounter
from .domain import (
    Artifact,
    BudgetTooSmall,
    Deleted,
    EvidenceError,
    Excerpt,
    IntegrityError,
    NotFound,
    Pack,
    Pinned,
    Scope,
    Verdict,
)
from .repository import SQLiteRepository
from .selection import BudgetPacker, LexicalRanker
from .service import EvidenceService

__all__ = [
    "Artifact",
    "BudgetPacker",
    "BudgetTooSmall",
    "ByteCounter",
    "Deleted",
    "EvidenceError",
    "EvidenceService",
    "Excerpt",
    "HuggingFaceCounter",
    "IntegrityError",
    "LexicalRanker",
    "NotFound",
    "Pack",
    "Pinned",
    "SQLiteRepository",
    "Scope",
    "TiktokenCounter",
    "Verdict",
]
