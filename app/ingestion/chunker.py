"""
Content-type-aware text chunker.
Returns a list of (chunk_text, chunk_index) tuples.
"""
from typing import List, Tuple
import re
import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")

# Chunk sizes and overlaps in tokens
_CONFIG = {
    "policy":       (512, 64),
    "wiki":         (512, 64),
    "readme":       (256, 32),
    "slack_thread": (None, 0),   # None = full content as single chunk
    "code":         (None, 0),   # None = split by function/class boundary
}
_DEFAULT = (512, 64)


def _token_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    tokens = _enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(_enc.decode(chunk_tokens))
        if end == len(tokens):
            break
        start += chunk_size - overlap
    return chunks


def _code_chunks(text: str) -> List[str]:
    """Split on function/class boundaries using blank-line heuristic."""
    blocks = re.split(r"\n(?=def |class |async def |\Z)", text)
    chunks = []
    current = ""
    for block in blocks:
        if len(_enc.encode(current + block)) > 800:
            if current:
                chunks.append(current.strip())
            current = block
        else:
            current += block
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text]


def chunk(content: str, content_type: str) -> List[Tuple[str, int]]:
    chunk_size, overlap = _CONFIG.get(content_type, _DEFAULT)

    if chunk_size is None:
        if content_type == "code":
            raw_chunks = _code_chunks(content)
        else:
            raw_chunks = [content]  # slack_thread — whole thread
    else:
        raw_chunks = _token_chunks(content, chunk_size, overlap)

    return [(c, i) for i, c in enumerate(raw_chunks) if c.strip()]
