"""
SOLARIS Python Engine — JSON Lines pipe protocol.

Reads one request JSON object per line from stdin.
Writes one or more response JSON objects per line to stdout.
Stdout is line-buffered; no HTTP server, no ports.
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import Any

# Ensure stdout is line-buffered and stdin strips UTF-8 BOM (PowerShell adds it)
sys.stdout.reconfigure(line_buffering=True)   # type: ignore[attr-defined]
sys.stdin.reconfigure(encoding="utf-8-sig")   # type: ignore[attr-defined]

# Add engine root to path
ENGINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ENGINE_ROOT))


def _write(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_chat_stream(req: dict) -> None:
    from app.chat.providers import stream_anthropic, stream_openrouter
    from app.chat.amr import route as amr_route

    req_id = req["id"]
    messages = req.get("messages", [])
    system = req.get("system") or None
    preferred_model = req.get("model")
    preferred_provider = req.get("provider")

    # Determine provider + model
    if preferred_model and preferred_provider:
        provider = preferred_provider
        model = preferred_model
    else:
        sel = amr_route(messages[-1]["content"] if messages else "")
        provider = sel.provider
        model = sel.model

    if not provider:
        _write({"id": req_id, "type": "chat_error", "message": "Nenhum provider configurado."})
        return

    accumulated = ""
    errors: list[str] = []
    usage: dict = {}

    async def stream(prov: str, mdl: str) -> bool:
        nonlocal accumulated, usage
        try:
            gen = stream_anthropic(messages, mdl, system=system) if prov == "anthropic" \
                  else stream_openrouter(messages, mdl, system=system)
            async for event in gen:
                if event["type"] == "delta":
                    accumulated += event["text"]
                    _write({"id": req_id, "type": "chat_delta", "text": event["text"]})
                elif event["type"] == "done":
                    usage = event.get("usage", {})
            return True
        except Exception as exc:
            errors.append(f"[{prov}/{mdl}] {exc}")
            return False

    ok = await stream(provider, model)

    # Circuit breaker: try fallback if primary failed with nothing accumulated
    if not ok and not accumulated:
        fb_prov = "openrouter" if provider == "anthropic" else "anthropic"
        fb_mdl = ("google/gemma-4-31b-it:free" if fb_prov == "openrouter"
                  else "claude-haiku-5-5")
        await stream(fb_prov, fb_mdl)

    if not accumulated:
        _write({"id": req_id, "type": "chat_error",
                "message": "; ".join(errors) or "Falha ao gerar resposta."})
        return

    _write({"id": req_id, "type": "chat_done", "usage": usage})


async def handle_models_list(req: dict) -> None:
    from app.chat.providers import ANTHROPIC_PRICING, OPENROUTER_PRICING
    import os

    models: list[dict] = []
    if os.getenv("ANTHROPIC_API_KEY"):
        models += [
            {"provider": "anthropic", "model": "claude-haiku-5-5",  "label": "Claude Haiku 5.5"},
            {"provider": "anthropic", "model": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5"},
        ]
    if os.getenv("OPENROUTER_API_KEY"):
        models += [
            {"provider": "openrouter", "model": "google/gemma-4-31b-it:free",     "label": "Gemma 4 31B (free)"},
            {"provider": "openrouter", "model": "google/gemma-4-26b-a4b-it:free", "label": "Gemma 4 26B (free)"},
            {"provider": "openrouter", "model": "nvidia/nemotron-3.5-lightning:free", "label": "Nemotron 3.5 (free)"},
        ]
    _write({"id": req["id"], "type": "models_result", "models": models})


async def handle_rag_embed(req: dict) -> None:
    from app.rag.embeddings import embed
    texts = req["texts"]
    embeddings = embed(texts)
    _write({"id": req["id"], "type": "rag_embed_result", "embeddings": embeddings})


async def handle_rag_embed_query(req: dict) -> None:
    from app.rag.embeddings import embed_query
    embedding = embed_query(req["query"])
    _write({"id": req["id"], "type": "rag_embed_query_result", "embedding": embedding})


async def handle_rag_add_chunks(req: dict) -> None:
    from app.rag.vector_store import add_chunks
    add_chunks(
        project_id=req.get("project_id"),
        chunk_ids=req["chunk_ids"],
        embeddings=req["embeddings"],
        texts=req["texts"],
        metadatas=req["metadatas"],
    )
    _write({"id": req["id"], "type": "rag_add_done"})


async def handle_rag_search(req: dict) -> None:
    from app.rag.vector_store import search
    hits = search(
        project_id=req.get("project_id"),
        query_embedding=req["query_embedding"],
        n_results=req.get("n_results", 5),
    )
    _write({"id": req["id"], "type": "rag_search_result", "hits": hits})


async def handle_rag_delete_chunks(req: dict) -> None:
    from app.rag.vector_store import delete_chunks
    delete_chunks(project_id=req.get("project_id"), chunk_ids=req["chunk_ids"])
    _write({"id": req["id"], "type": "rag_delete_done"})


async def handle_extract_text(req: dict) -> None:
    from app.rag.chunker import extract_text
    content = base64.b64decode(req["content_b64"])
    text = extract_text(content, req["mime_type"])
    _write({"id": req["id"], "type": "extract_text_result", "text": text})


_HANDLERS: dict[str, Any] = {
    "chat_stream":       handle_chat_stream,
    "models_list":       handle_models_list,
    "rag_embed":         handle_rag_embed,
    "rag_embed_query":   handle_rag_embed_query,
    "rag_add_chunks":    handle_rag_add_chunks,
    "rag_search":        handle_rag_search,
    "rag_delete_chunks": handle_rag_delete_chunks,
    "extract_text":      handle_extract_text,
}


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main_loop() -> None:
    loop = asyncio.get_event_loop()

    async def readline() -> str:
        return await loop.run_in_executor(None, sys.stdin.readline)

    while True:
        line = await readline()
        if not line:
            break  # stdin closed → exit
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _write({"id": "", "type": "error", "message": f"Invalid JSON: {exc}"})
            continue

        req_type = req.get("type", "")
        handler = _HANDLERS.get(req_type)
        if handler is None:
            _write({"id": req.get("id", ""), "type": "error",
                    "message": f"Unknown request type: {req_type!r}"})
            continue

        try:
            await handler(req)
        except Exception as exc:
            _write({"id": req.get("id", ""), "type": "error", "message": str(exc)})


if __name__ == "__main__":
    # Load .env from the engine's directory (development) or storage dir (packaged)
    try:
        from dotenv import load_dotenv
        # Try packaged location first, then dev location
        for env_path in [
            Path(sys.executable).parent / ".env",
            ENGINE_ROOT / ".env",
            ENGINE_ROOT.parent / "backend" / ".env",  # backward compat
        ]:
            if env_path.exists():
                load_dotenv(env_path)
                break
    except ImportError:
        pass

    asyncio.run(main_loop())
