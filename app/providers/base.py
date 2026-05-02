from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class LLMMessage:
    role: str   # "user" | "assistant" | "system"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int
    provider: str


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(
        self,
        messages: List[LLMMessage],
        model: str,
        max_tokens: int = 1000,
        timeout: float = 8.0,
    ) -> LLMResponse: ...
