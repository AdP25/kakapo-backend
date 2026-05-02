"""
Layer 4 — Rule-based complexity classifier.
Returns (tier, source_tag) for a cache-miss query.
"""
from dataclasses import dataclass
from typing import Literal
import tiktoken

Tier = Literal["simple", "standard", "complex"]

_enc = tiktoken.get_encoding("cl100k_base")

# ── Scoring signals ─────────────────────────────────────────────────────────

_MULTI_STEP = {
    "explain", "compare", "analyse", "analyze", "why", "difference",
    "summarise", "summarize", "evaluate", "contrast", "discuss",
    "how does", "what causes", "impact of", "implications",
}

_CODE_SIGNALS = {
    "write a script", "give me json", "sql query", "code", "function",
    "write code", "implement", "algorithm", "regex", "write a program",
    "debug", "fix this", "refactor",
}

_DOMAIN_HIGH_STAKES = {
    "legal", "compliance", "regulation", "regulatory", "medical",
    "clinical", "financial", "audit", "liability", "contract",
    "gdpr", "hipaa", "sox",
}

_CONVERSATIONAL = {
    "what is", "who is", "hello", "hi", "hey", "thanks",
    "thank you", "ok", "okay", "yes", "no",
}

# ── Source-tag detection ────────────────────────────────────────────────────

_CODEBASE_SIGNALS = {
    "code", "function", "class", "module", "api", "endpoint",
    "service", "repo", "repository", "branch", "commit", "deploy",
    "script", "bug", "error", "exception", "test", "database",
}

_HR_SIGNALS = {
    "leave", "holiday", "vacation", "sick", "policy", "hr",
    "expense", "reimbursement", "payroll", "salary", "benefit",
    "onboarding", "offboarding", "performance", "review",
}

_ORG_SIGNALS = {
    "org chart", "organisation", "organization", "department", "team",
    "reports to", "manager", "director", "ceo", "cto", "vp",
    "head of", "who runs", "who leads",
}

_PRICING_SIGNALS = {
    "price", "pricing", "cost", "quote", "discount", "subscription",
    "plan", "tier", "billing", "invoice", "charge",
}


@dataclass
class ClassifierResult:
    tier: Tier
    source_tag: str
    score: int


def classify(query: str) -> ClassifierResult:
    q = query.lower()
    tokens = len(_enc.encode(query))
    score = 0

    if any(s in q for s in _MULTI_STEP):
        score += 3
    if any(s in q for s in _CODE_SIGNALS):
        score += 3
    if any(s in q for s in _DOMAIN_HIGH_STAKES):
        score += 3
    if tokens > 50:
        score += 2
    if tokens > 100:
        score += 2
    if any(s in q for s in _CONVERSATIONAL):
        score -= 2

    score = max(0, score)

    if score >= 6:
        tier: Tier = "complex"
    elif score >= 3:
        tier = "standard"
    else:
        tier = "simple"

    # source_tag detection
    if any(s in q for s in _CODEBASE_SIGNALS):
        source_tag = "codebase"
    elif any(s in q for s in _HR_SIGNALS):
        source_tag = "hr_policy"
    elif any(s in q for s in _ORG_SIGNALS):
        source_tag = "org_chart"
    elif any(s in q for s in _PRICING_SIGNALS):
        source_tag = "pricing"
    else:
        source_tag = "general_knowledge"

    return ClassifierResult(tier=tier, source_tag=source_tag, score=score)
