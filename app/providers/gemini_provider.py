from openai import AsyncOpenAI
from typing import List

from app.providers.base import LLMProvider, LLMMessage, LLMResponse
from app.core.config import settings

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.gemini_api_key,
            base_url=_GEMINI_BASE_URL,
        )

    async def complete(
        self,
        messages: List[LLMMessage],
        model: str,
        max_tokens: int = 1000,
        timeout: float = 8.0,
    ) -> LLMResponse:
        oai_msgs = [{"role": m.role, "content": m.content} for m in messages]
        resp = await self._client.chat.completions.create(
            model=model,
            messages=oai_msgs,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        usage = resp.usage
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=resp.model,
            tokens_used=(usage.prompt_tokens or 0) + (usage.completion_tokens or 0) if usage else 0,
            provider=self.name,
        )
