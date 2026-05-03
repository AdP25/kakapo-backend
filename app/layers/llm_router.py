"""
Layer 5 — LLM router.
Handles provider selection, soft/hard timeouts, retries, fallback, circuit breaker.
"""
import asyncio
import random
from typing import List, Optional

from app.providers.base import LLMMessage, LLMResponse
from app.providers.gemini_provider import GeminiProvider
from app.providers.openai_provider import OpenAIProvider
from app.reliability import circuit_breaker
from app.reliability.response_validator import validate, ValidationResult
from app.core.config import settings

# Singleton provider instances
_gemini = GeminiProvider()
_openai = OpenAIProvider()

# Model map: tier → (primary_provider, primary_model, fallback_provider, fallback_model)
_ROUTING = {
    "simple":   (_gemini, "gemini-2.0-flash",   _openai, "gpt-4o-mini"),
    "standard": (_gemini, "gemini-1.5-pro",     _openai, "gpt-4o"),
    "complex":  (_gemini, "gemini-1.5-pro",     _openai, "gpt-4o"),
}

_TIER_ORDER = ["simple", "standard", "complex"]

_SYSTEM_PROMPT = """\
You are a helpful assistant for an organisation. Answer the user's question accurately and concisely.
At the end of your response, on a new line, add a metadata tag in this exact format:
[VISIBILITY: global|role:{ROLE_NAME}|personal]
Replace {ROLE_NAME} with the relevant department role if the answer is role-specific (e.g. role:HR, role:Finance).
Use "personal" only if the answer is specific to the individual asking.
Use "global" for answers applicable to everyone.\
"""

DEGRADED_RESPONSE = "I wasn't able to find an answer right now. Please try again in a moment."


async def _call_with_timeout(
    provider,
    model: str,
    messages: List[LLMMessage],
    max_tokens: int,
    timeout: float,
) -> LLMResponse:
    return await asyncio.wait_for(
        provider.complete(messages, model=model, max_tokens=max_tokens, timeout=timeout),
        timeout=timeout,
    )


async def _try_provider(
    provider,
    model: str,
    messages: List[LLMMessage],
    max_tokens: int,
    provider_name: str,
) -> Optional[LLMResponse]:
    """Attempt a provider call with retries (rate-limit backoff) and circuit breaker."""
    if await circuit_breaker.is_open(provider_name):
        return None

    for attempt in range(3):
        try:
            resp = await _call_with_timeout(
                provider, model, messages, max_tokens,
                timeout=settings.llm_hard_timeout,
            )
            await circuit_breaker.record_success(provider_name)
            return resp

        except asyncio.TimeoutError:
            await circuit_breaker.record_error(provider_name)
            return None

        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                # Exponential backoff + jitter for rate limits
                wait = (2 ** attempt) + random.uniform(0, attempt + 0.5)
                await asyncio.sleep(wait)
                continue
            await circuit_breaker.record_error(provider_name)
            if attempt == 2:
                return None

    return None


async def route(
    query: str,
    tier: str,
    role: str,
    context_messages: Optional[List[LLMMessage]] = None,
    max_tokens: int = 1000,
) -> tuple[str, str, int]:
    """
    Returns (response_text, model_used, tokens_used).
    Tries primary provider, falls back to secondary, escalates tier on ignorance.
    Returns degraded response if all paths fail.
    """
    primary_prov, primary_model, fallback_prov, fallback_model = _ROUTING[tier]

    messages: List[LLMMessage] = [LLMMessage(role="system", content=_SYSTEM_PROMPT)]
    if context_messages:
        messages.extend(context_messages)
    messages.append(LLMMessage(role="user", content=query))

    escalated = False
    current_tier = tier

    for _ in range(2):  # allow one tier escalation
        primary_prov, primary_model, fallback_prov, fallback_model = _ROUTING[current_tier]

        # Soft timeout: try primary; if it doesn't start in time, launch fallback in parallel
        primary_task = asyncio.create_task(
            _try_provider(primary_prov, primary_model, messages, max_tokens, primary_prov.name)
        )

        try:
            resp = await asyncio.wait_for(
                asyncio.shield(primary_task),
                timeout=settings.llm_soft_timeout,
            )
        except asyncio.TimeoutError:
            # Primary is slow — hedge with fallback
            fallback_task = asyncio.create_task(
                _try_provider(fallback_prov, fallback_model, messages, max_tokens, fallback_prov.name)
            )
            done, pending = await asyncio.wait(
                [primary_task, fallback_task],
                timeout=settings.llm_hard_timeout - settings.llm_soft_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            resp = next((t.result() for t in done if not t.exception() and t.result()), None)
        except Exception:
            primary_task.cancel()
            resp = None

        if resp is None:
            # Primary failed — try fallback directly
            resp = await _try_provider(
                fallback_prov, fallback_model, messages, max_tokens, fallback_prov.name
            )

        if resp is None:
            return DEGRADED_RESPONSE, "none", 0

        validation: ValidationResult = validate(resp.content, role)

        if validation.refusal:
            return "I couldn't find an answer to that question.", resp.model, resp.tokens_used

        if not validation.ok and not escalated:
            # Escalate to next tier once
            idx = _TIER_ORDER.index(current_tier)
            if idx < len(_TIER_ORDER) - 1:
                current_tier = _TIER_ORDER[idx + 1]
                escalated = True
                continue

        return validation.content, resp.model, resp.tokens_used

    return DEGRADED_RESPONSE, "none", 0
