"""LLM provider adapters — Anthropic and OpenRouter, async generators."""

# Importa as bibliotecas necessárias
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from importlib import import_module
from typing import Any
from urllib.request import Request, urlopen

# Define os preços por token para os modelos Anthropic e OpenRouter
ANTHROPIC_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-5-5": {"input": 0.10e-6, "output": 0.50e-6},
    "claude-sonnet-5-5": {"input": 2.0e-6, "output": 10.0e-6},
}

# Define os preços por token para os modelos OpenRouter
OPENROUTER_PRICING: dict[str, dict[str, float]] = {
    "google/gemma-4-31b-it:free": {"input": 0.0, "output": 0.0},
    "google/gemma-4-26b-a4b-it:free": {"input": 0.0, "output": 0.0},
    "nvidia/nemotron-3.5-lightning:free": {"input": 0.0, "output": 0.0},
}


# Função assíncrona para transmitir mensagens para o modelo Anthropic
async def stream_anthropic(
    messages: list[dict[str, Any]],
    model: str = "claude-haiku-5-5",
    system: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada.")
    workspace_id = os.getenv("ANTHROPIC_WORKSPACE_ID", "")
    extra_headers: dict[str, str] = {"anthropic-workspace-id": workspace_id} if workspace_id else {}
    try:
        AsyncAnthropic = import_module("anthropic").AsyncAnthropic
    except ImportError as exc:
        raise RuntimeError("A dependência 'anthropic' não está instalada.") from exc
    client = AsyncAnthropic(api_key=api_key, default_headers=extra_headers)
    kwargs: dict[str, Any] = {"model": model, "max_tokens": 2048, "messages": messages}
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


# Função assíncrona para transmitir mensagens para o modelo OpenRouter
async def stream_openrouter(
    messages: list[dict[str, Any]],
    model: str = "google/gemma-4-31b-it:free",
    system: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada.")
    msgs: list[dict[str, Any]] = (
        ([{"role": "system", "content": system}] + messages) if system else messages
    )
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "SOLARIS",
    }
    payload: dict[str, Any] = {"model": model, "messages": msgs, "stream": True, "max_tokens": 2048}
    input_tokens = output_tokens = 0

    # Usa a biblioteca padrão para evitar uma dependência externa de HTTP.
    request = Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    resp = await asyncio.to_thread(urlopen, request, timeout=60)
    try:
        while True:
            raw_line = await asyncio.to_thread(resp.readline)
            if not raw_line:
                break
            line = raw_line.decode("utf-8").strip()
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
    finally:
        await asyncio.to_thread(resp.close)

    # Calcula o custo com base no número de tokens de entrada e saída e nos preços definidos para o modelo
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
