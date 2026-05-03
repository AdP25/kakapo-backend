from __future__ import annotations

import asyncio
import time
import random

import httpx

from app.core.config import DEFAULT_MODEL, MOCK_MODE, OPENAI_API_KEY, OPENAI_BASE_URL


def make_mock_response(model: str, tokens_in: int) -> dict:
    tokens_out = random.randint(50, 200)
    content = "Sure, here's an answer to your question. This is a mock response generated in MOCK_MODE."
    return {
        "id": f"chatcmpl-mock-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out, "total_tokens": tokens_in + tokens_out},
    }


async def get_completion(request_payload: dict, tokens_in: int) -> dict:
    model = request_payload.get("model", DEFAULT_MODEL)
    if MOCK_MODE:
        await asyncio.sleep(0.8)
        return make_mock_response(model, tokens_in)

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Configure your environment or enable MOCK_MODE.")

    payload = dict(request_payload)
    if "model" not in payload:
        payload["model"] = DEFAULT_MODEL

    async with httpx.AsyncClient(timeout=60.0) as client:
        api_resp = await client.post(
            OPENAI_BASE_URL.rstrip("/") + "/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        )
        api_resp.raise_for_status()
        return api_resp.json()
