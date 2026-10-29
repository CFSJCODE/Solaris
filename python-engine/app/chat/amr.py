"""Adaptive Model Router — keyword heuristic to pick provider + model."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ModelSelection:
    provider: str
    model: str
    reason: str


_COMPLEX_KEYWORDS = {
    "código", "code", "programa", "debug", "erro", "analisa", "analyze",
    "explica", "explain", "compara", "compare", "resumo", "summary",
    "traduza", "translate", "refatora", "refactor", "arquitetura",
    "architecture", "implemente", "implement",
}


def route(user_message: str) -> ModelSelection:
    has_ant = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_or  = bool(os.getenv("OPENROUTER_API_KEY"))

    if not has_ant and not has_or:
        return ModelSelection(provider="", model="", reason="no providers configured")

    msg_lower = user_message.lower()
    is_complex = any(kw in msg_lower for kw in _COMPLEX_KEYWORDS) or len(user_message) > 300

    if has_ant:
        model = "claude-sonnet-4-5-20250514" if is_complex else "claude-haiku-3-5-20251101"
        reason = "complex task → Sonnet" if is_complex else "simple task → Haiku"
        return ModelSelection(provider="anthropic", model=model, reason=reason)

    # OpenRouter only
    model = "mistralai/mistral-7b-instruct:free" if is_complex else "meta-llama/llama-3.1-8b-instruct:free"
    return ModelSelection(provider="openrouter", model=model, reason="openrouter fallback")
