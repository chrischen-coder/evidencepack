"""Explicit budget units; optional tokenizer imports stay out of the core."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ByteCounter:
    """Count UTF-8 bytes exactly; no token estimate is implied."""

    name: str = "utf8-bytes"

    def count(self, text: str) -> int:
        """Return the size of the actual UTF-8 encoding."""
        return len(text.encode("utf-8"))


class TiktokenCounter:
    """Count one tiktoken encoding, including literal special-token strings."""

    def __init__(self, encoding: str = "cl100k_base") -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding(encoding)
        self.name = f"tokens:{encoding}"

    def count(self, text: str) -> int:
        """Count text tokens; transport and chat-template tokens are separate."""
        return len(self._encoding.encode(text, disallowed_special=()))


class HuggingFaceCounter:
    """Use a locally available model tokenizer without downloading weights."""

    def __init__(self, tokenizer_path: str) -> None:
        tokenizer_factory: Any = importlib.import_module("transformers").AutoTokenizer
        self._tokenizer: Any = tokenizer_factory.from_pretrained(
            tokenizer_path, local_files_only=True, trust_remote_code=False
        )
        self.name = f"tokens:hf:{self._tokenizer.__class__.__name__}"

    def count(self, text: str) -> int:
        """Count the representation with no added chat-template tokens."""
        return len(self._tokenizer.encode(text, add_special_tokens=False))
