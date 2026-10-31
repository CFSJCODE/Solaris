"""Adaptive Model Router — heuristic task classifier for model selection."""

from dataclasses import dataclass

CODING_KEYWORDS = {
    "código",
    "code",
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
    "c++",
    "função",
    "function",
    "bug",
    "erro",
    "error",
    "debug",
    "implementar",
    "implement",
    "algoritmo",
    "algorithm",
    "classe",
    "class",
    "método",
    "method",
    "api",
    "endpoint",
    "sql",
    "query",
    "regex",
    "script",
    "programa",
    "program",
}

REASONING_KEYWORDS = {
    "analisa",
    "analyze",
    "explica",
    "explain",
    "raciocina",
    "reasoning",
    "descreve",
    "describe",
    "compare",
    "comparar",
    "pros",
    "cons",
    "decisão",
    "decision",
    "estratégia",
    "strategy",
    "avalia",
    "evaluate",
    "resumo",
    "summary",
    "sumário",
    "sintetiza",
    "synthesize",
    "diferença",
    "difference",
    "vantagem",
    "advantage",
}

QUICK_KEYWORDS = {
    "olá",
    "oi",
    "hi",
    "hello",
    "obrigado",
    "thanks",
    "thank",
    "ok",
    "sim",
    "não",
    "yes",
    "no",
    "tudo bem",
    "certo",
    "entendi",
}


@dataclass
class ModelSelection:
    provider: str  # "anthropic" | "openrouter" | ""
    model: str
    reason: str


def route(message: str, has_anthropic: bool, has_openrouter: bool) -> ModelSelection:
    """Select model based on message content heuristics."""
    if not has_anthropic and not has_openrouter:
        return ModelSelection("", "", "no provider configured")

    lower = message.lower()
    tokens = set(lower.split())

    # Very short quick messages → cheapest free option
    if len(message) < 80 and tokens & QUICK_KEYWORDS:
        if has_openrouter:
            return ModelSelection(
                "openrouter", "meta-llama/llama-3.1-8b-instruct:free", "quick reply"
            )
        return ModelSelection("anthropic", "claude-haiku-3-5-20251101", "quick reply")

    # Coding tasks → Haiku (fast, good at code) or Mistral free
    if tokens & CODING_KEYWORDS:
        if has_anthropic:
            return ModelSelection("anthropic", "claude-haiku-3-5-20251101", "coding task")
        return ModelSelection(
            "openrouter", "mistralai/mistral-7b-instruct:free", "coding task fallback"
        )

    # Long messages or complex reasoning → Sonnet or best free
    if (tokens & REASONING_KEYWORDS) or len(message) > 500:
        if has_anthropic:
            return ModelSelection("anthropic", "claude-sonnet-4-5-20250514", "complex reasoning")
        return ModelSelection(
            "openrouter", "meta-llama/llama-3.1-8b-instruct:free", "reasoning fallback"
        )

    # Default
    if has_anthropic:
        return ModelSelection("anthropic", "claude-haiku-3-5-20251101", "default")
    return ModelSelection("openrouter", "meta-llama/llama-3.1-8b-instruct:free", "default")
