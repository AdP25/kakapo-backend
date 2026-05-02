"""
Layer 2 — Pre-cache detector.
Classifies every query as LIVE_DATA | AMBIGUOUS | NORMAL before embedding.
"""
from enum import Enum

_LIVE_DATA_SIGNALS = {
    "today", "right now", "at the moment", "currently", "this week",
    "this month", "this year", "now", "on call", "who is on call",
    "my leave", "my balance", "my expense", "my approval", "my salary",
    "my payslip", "my timesheet", "my schedule", "my request",
    "is the office open", "office hours", "office closed",
    "current status", "latest update",
}

_AMBIGUOUS_PRONOUNS = {"it", "this", "that", "they", "them", "those", "these"}
_AMBIGUOUS_RELATIVES = {"instead", "also", "another", "the same", "similarly", "as well"}


class QueryType(str, Enum):
    LIVE_DATA = "LIVE_DATA"
    AMBIGUOUS = "AMBIGUOUS"
    NORMAL = "NORMAL"


def detect(query: str) -> QueryType:
    q = query.strip().lower()
    words = q.split()

    # Check live-data signals
    for signal in _LIVE_DATA_SIGNALS:
        if signal in q:
            return QueryType.LIVE_DATA

    # Short or ambiguous queries
    if len(words) < 5:
        # Very short — likely needs conversation context
        return QueryType.AMBIGUOUS

    # Starts with or contains context-dependent pronouns as subject
    if words[0] in _AMBIGUOUS_PRONOUNS:
        return QueryType.AMBIGUOUS

    for rel in _AMBIGUOUS_RELATIVES:
        if rel in q:
            return QueryType.AMBIGUOUS

    return QueryType.NORMAL
