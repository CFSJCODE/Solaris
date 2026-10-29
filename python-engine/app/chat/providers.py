"""LLM provider adapters — Anthropic and OpenRouter, async generators."""
from __future__ import annotations

import json
import os
from typing import AsyncGenerator

import httpx
from anthropic import AsyncAnthropic

ANTHROPIC_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-3-5-20251101":  {"input": 0.80e-6, "output": 4.0e-6},
    "claude-haiku-3-20240307":    {"input": 0.25e-6, "output": 1.25e-6},
    "claude-sonnet-4-5-20250514": {"input": 3.0e-6,  "output": 15.0e-6},
    "claude-sonnet-4-20250514":   {"input": 3.0e-6,  "output": 15.0e-6},
}

OPENROUTER_PRICING: dict[str, dict[str, float]] = {
    "meta-llama/llama-3.1-8b-instruct:free": {"input": 0.0, "output": 0.0},
    "google/gemma-2-9b-it:free":             {"input": 0.0, "output": 0.0},
    "mistralai/mistral-7b-instruct:free":    {"input": 0.0, "output": 0.0},
}


async def stream_anthropic(
    messages: list[dict],
    model: str = "claude-haiku-3-5-20251101",
    system: str | None = None,
) -> AsyncGenerator[dict, None]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada.")
    client = AsyncAnthropic(api_key=api_key)
    kwargs: dict = {"model": model, "max_tokens": 2048, "messages": messages}
    if system:
        kwargs["system"] = system

    input_tokens = output_tokens = 0
    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield {"type": "delta", "text": text}
        final = await stream.get_final_message()
        input_tokens = final.usage.input_tokens
        output_tokens = final.usage.output_tokens

    pricing = ANTHROPIC_PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
    yield {
        "type": "done",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "model": model,
            "provider": "anthropic",
        },
    }


async def stream_openrouter(
    messages: list[dict],
    model: str = "meta-llama/llama-3.1-8b-instruct:free",
    system: str | None = None,
) -> AsyncGenerator[dict, None]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada.")
    msgs = ([{"role": "system", "content": system}] + messages) if system else messages
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "SOLARIS",
    }
    payload = {"model": model, "messages": msgs, "stream": True, "max_tokens": 2048}
    input_tokens = output_tokens = 0

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", "https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield {"type": "delta", "text": delta}
                    usage = chunk.get("usage")
                    if usage:
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                except Exception:
                    pass

    pricing = OPENROUTER_PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
    yield {
        "type": "done",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "model": model,
            "provider": "openrouter",
        },
    }
