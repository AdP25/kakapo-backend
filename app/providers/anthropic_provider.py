import anthropic
from typing import List

from app.providers.base import LLMProvider, LLMMessage, LLMResponse
from app.core.config import settings


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(
        self,
        messages: List[LLMMessage],
        model: str,
        max_tokens: int = 1000,
        timeout: float = 8.0,
    ) -> LLMResponse:
        system_msg = None
        user_messages = []

        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                user_messages.append({"role": m.role, "content": m.content})

        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            messages=user_messages,
            timeout=timeout,
        )
        if system_msg:
            kwargs["system"] = system_msg

        resp = await self._client.messages.create(**kwargs)
        return LLMResponse(
            content=resp.content[0].text,
            model=resp.model,
            tokens_used=(resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0),
            provider=self.name,
        )
