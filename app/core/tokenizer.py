"""Shared tiktoken encoder for token counting (lazy singleton)."""

from __future__ import annotations

import tiktoken

_tokenizer = None


def get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    return _tokenizer
