import re
from dataclasses import dataclass
from typing import Tuple

_IGNORANCE_PHRASES = (
    "i don't know",
    "i cannot answer",
    "i'm not sure",
    "i am not sure",
    "i do not know",
    "i cannot help",
    "i'm unable to",
    "i am unable to",
)

_REFUSAL_PHRASES = (
    "i'm sorry, i can't",
    "i cannot assist",
    "i'm not able to help with",
    "i cannot provide",
    "i won't",
    "i will not",
)

_VISIBILITY_RE = re.compile(
    r"\[VISIBILITY:\s*(global|role:[A-Za-z]+|personal)\]",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    ok: bool
    escalate: bool          # retry with a more capable model
    refusal: bool           # do not cache, return generic error
    content: str            # cleaned response (visibility tag stripped)
    visibility: str         # extracted visibility or default


def validate(raw: str, fallback_role: str) -> ValidationResult:
    stripped = raw.strip()

    # Empty / too short → retry
    if len(stripped) < 10:
        return ValidationResult(ok=False, escalate=False, refusal=False, content=stripped, visibility="global")

    lower = stripped.lower()

    # Safety refusal → don't cache, return generic error
    if any(p in lower for p in _REFUSAL_PHRASES):
        return ValidationResult(ok=False, escalate=False, refusal=True, content=stripped, visibility="global")

    # Model says it doesn't know → escalate tier
    if any(p in lower for p in _IGNORANCE_PHRASES):
        return ValidationResult(ok=False, escalate=True, refusal=False, content=stripped, visibility="global")

    # Extract and strip visibility tag
    match = _VISIBILITY_RE.search(stripped)
    if match:
        visibility = match.group(1).lower()
        content = _VISIBILITY_RE.sub("", stripped).strip()
    else:
        visibility = f"role:{fallback_role}" if fallback_role else "global"
        content = stripped

    return ValidationResult(ok=True, escalate=False, refusal=False, content=content, visibility=visibility)
