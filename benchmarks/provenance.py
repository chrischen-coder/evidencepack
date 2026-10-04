"""Content fingerprints for the implementation used in a measured run."""

import hashlib
from pathlib import Path


def source_digest() -> str:
    """Fingerprint implementation code independently of checkout location or Git state."""
    root = Path(__file__).resolve().parents[1]
    paths = sorted([*root.joinpath("src").rglob("*.py"), *root.joinpath("benchmarks").glob("*.py")])
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()
