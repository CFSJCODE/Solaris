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
# UTF-8 explícito: no Windows o padrão do pipe é cp1252 e o Rust lê UTF-8 (acentos viravam �)
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # type: ignore[attr-defined]
sys.stdin.reconfigure(encoding="utf-8-sig")  # type: ignore[attr-defined]

# Add engine root to path
ENGINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ENGINE_ROOT))


def _write(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


MEMORY_REQUIRED_INSTRUCTION = (
    "\n\nPEDIDO EXPLÍCITO DE GRAVAÇÃO DE MEMÓRIA. Sua resposta inteira deve ser SOMENTE o bloco "
    "abaixo, sem texto antes ou depois, sem cercas de código:\n"
    '<solaris_memory>{"updates":[{"file":"DECISOES.md","content":"- Decisão 1 (fonte: AGENTS.md)\\n'
    '- Decisão 2 (fonte: AGENTS.md)"},{"file":"MEMORY.md","content":"- Fato técnico relevante"}]}'
    "</solaris_memory>\n"
    "Regras: JSON válido; use \\n para quebras de linha dentro de content; cada content com no "
    "máximo ~3000 caracteres, em tópicos curtos; file só pode ser um dos arquivos de memória "
    "listados nas referências (AGENTS.md, README.md, CONTRIBUTING.md, MEMORY.md, DECISOES.md). "
    "Sintetize com suas palavras o que foi pedido usando o contexto e as referências; não copie a "
    "conversa nem os exemplos acima. Separe decisões confirmadas de propostas. Se o material é "
    "parcial, registre essa limitação. Só retorne updates vazio se realmente não houver nada a "
    "registrar. Não prometa salvar: a aplicação confirma a gravação depois de persistir."
)

MEMORY_RETRY_PROMPT = (
    "Sua resposta anterior não veio no formato de memória exigido. Converta o que deve ser "
    "registrado em JSON e responda SOMENTE com:\n"
    '<solaris_memory>{"updates":[{"file":"DECISOES.md","content":"- item\\n- item"}]}'
    "</solaris_memory>\n"
    "Use apenas AGENTS.md, README.md, CONTRIBUTING.md, MEMORY.md ou DECISOES.md em file, conteúdo "
    "em tópicos curtos (até ~3000 caracteres por item) e nada além do bloco."
)


def _merge_usage(first: dict, second: dict) -> dict:
    """Soma tokens e custo dos dois passes para o painel de uso refletir o gasto real."""
    if not first:
        return second
    if not second:
        return first
    merged = {**first, **second}
    for key in ("input_tokens", "output_tokens", "cost_usd"):
        values = [u.get(key) for u in (first, second) if isinstance(u.get(key), (int, float))]
        if values:
            merged[key] = sum(values)
    return merged


# ── Handlers ──────────────────────────────────────────────────────────────────


async def handle_chat_stream(req: dict) -> None:
    from app.chat.amr import route as amr_route
    from app.chat.memory_stream import MemoryStream
    from app.chat.providers import stream_anthropic, stream_openrouter

    req_id = req["id"]
    messages = req.get("messages", [])
    system = req.get("system") or None
    memory_required = bool(req.get("memory_required"))
    if memory_required:
        # Instrução no FIM do system prompt (mais perto da geração) e com exemplo concreto:
        # modelos menores seguem melhor um formato curto e explícito do que regras longas.
        system = (system or "") + MEMORY_REQUIRED_INSTRUCTION
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
    memory_stream = MemoryStream(req.get("memory_files"), require_tag=not memory_required)
    errors: list[str] = []
    usage: dict = {}
    used = (provider, model)

    async def stream(prov: str, mdl: str, msgs: list | None = None) -> bool:
        nonlocal accumulated, usage, used
        msgs = messages if msgs is None else msgs
        used = (prov, mdl)
        try:
            gen = (
                stream_anthropic(msgs, mdl, system=system)
                if prov == "anthropic"
                else stream_openrouter(msgs, mdl, system=system)
            )
            async for event in gen:
                if event["type"] == "delta":
                    accumulated += event["text"]
                    visible = memory_stream.feed(event["text"])
                    if visible and not memory_required:
                        _write({"id": req_id, "type": "chat_delta", "text": visible})
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
        fb_mdl = "google/gemma-4-31b-it:free" if fb_prov == "openrouter" else "claude-haiku-5-5"
        ok = await stream(fb_prov, fb_mdl)

    if not accumulated:
        _write(
            {
                "id": req_id,
                "type": "chat_error",
                "message": "; ".join(errors) or "Falha ao gerar resposta.",
            }
        )
        return

    tail, updates, warning = memory_stream.finish()

    # Fallback para modelos menores: se a gravação foi pedida e o primeiro passe não trouxe
    # registros aproveitáveis, faz UM segundo pedido curto só de extração, com a saída anterior
    # como insumo e o formato JSON pedido de forma direta.
    if ok and memory_required and not updates:
        first_output = accumulated
        accumulated = ""
        memory_stream = MemoryStream(req.get("memory_files"), require_tag=False)
        retry_messages = [
            *messages,
            {"role": "assistant", "content": first_output[-8000:] or "(sem resposta)"},
            {"role": "user", "content": MEMORY_RETRY_PROMPT},
        ]
        first_usage, usage = usage, {}
        retry_ok = await stream(*used, retry_messages)
        usage = _merge_usage(first_usage, usage)
        if retry_ok:
            _, updates, retry_warning = memory_stream.finish()
            warning = None if updates else (retry_warning or warning)
    if tail and not memory_required:
        _write({"id": req_id, "type": "chat_delta", "text": tail})
    if not ok:
        _write(
            {
                "id": req_id,
                "type": "chat_error",
                "message": "A resposta foi interrompida. A memória não foi atualizada.",
            }
        )
        return
    if updates:
        _write({"id": req_id, "type": "memory_updates", "updates": updates})
    if memory_required and not updates:
        warning = (
            f"O modelo {used[1]} não retornou registros válidos para a memória, nem após uma "
            "segunda tentativa só de formatação. Nenhum arquivo foi alterado. Tente de novo ou "
            "use um modelo maior para este pedido."
        )
    if warning:
        _write({"id": req_id, "type": "memory_update_warning", "message": warning})
    _write({"id": req_id, "type": "chat_done", "usage": usage})


async def handle_models_list(req: dict) -> None:
    import os

    models: list[dict] = []
    if os.getenv("ANTHROPIC_API_KEY"):
        models += [
            {"provider": "anthropic", "model": "claude-haiku-5-5", "label": "Claude Haiku 5.5"},
            {"provider": "anthropic", "model": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5"},
        ]
    if os.getenv("OPENROUTER_API_KEY"):
        models += [
            {
                "provider": "openrouter",
                "model": "google/gemma-4-31b-it:free",
                "label": "Gemma 4 31B (free)",
            },
            {
                "provider": "openrouter",
                "model": "google/gemma-4-26b-a4b-it:free",
                "label": "Gemma 4 26B (free)",
            },
            {
                "provider": "openrouter",
                "model": "nvidia/nemotron-3.5-lightning:free",
                "label": "Nemotron 3.5 (free)",
            },
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

    if len(req["content_b64"]) > 14_000_000:
        raise ValueError("Arquivo maior que 10 MB.")
    content = base64.b64decode(req["content_b64"], validate=True)
    text = await asyncio.to_thread(extract_text, content, req["mime_type"])
    _write(
        {"id": req["id"], "type": "extract_text_result", "text": text, "byte_size": len(content)}
    )


async def handle_health(req: dict) -> None:
    from app.vision.detector import status

    _write({"id": req["id"], "type": "health_result", "vision": status()})


async def handle_vision_detect(req: dict) -> None:
    from app.vision.detector import detect

    result = await asyncio.to_thread(
        detect, req["content_b64"], req.get("project_id"), bool(req.get("adapt"))
    )
    if req.get("adapt"):
        from app.vision.environment import observe

        result = observe(req.get("project_id"), result)
        from app.vision.learning import capture

        try:
            await asyncio.to_thread(capture, req.get("project_id"), req["content_b64"], result)
        except Exception:
            result["learning_warning"] = "Não foi possível coletar este exemplo para aprendizado."
    _write({"id": req["id"], "type": "vision_result", **result})


async def handle_learning_status(req: dict) -> None:
    from app.vision.learning import status

    result = await asyncio.to_thread(status, req.get("project_id"), req.get("enabled"))
    _write({"id": req["id"], "type": "learning_result", **result})


async def handle_learning_incorporate(req: dict) -> None:
    from app.vision.learning import incorporate

    result = await asyncio.to_thread(
        incorporate,
        req.get("project_id"),
        req["revision_id"],
        req["payload"],
        req.get("complete", False),
    )
    _write({"id": req["id"], "type": "learning_result", **result})


async def handle_learning_train_now(req: dict) -> None:
    from app.vision.learning import request_training

    result = await asyncio.to_thread(request_training, req.get("project_id"))
    _write({"id": req["id"], "type": "learning_result", **result})


async def handle_clusters_list(req: dict) -> None:
    from app.vision.clusters import list_clusters

    result = await asyncio.to_thread(list_clusters, req.get("project_id"))
    _write({"id": req["id"], "type": "clusters_result", **result})


async def handle_cluster_rename(req: dict) -> None:
    from app.vision.clusters import rename_cluster

    result = await asyncio.to_thread(
        rename_cluster, req.get("project_id"), req["cluster_id"], req.get("name")
    )
    _write({"id": req["id"], "type": "cluster_rename_result", **result})


_HANDLERS: dict[str, Any] = {
    "clusters_list": handle_clusters_list,
    "cluster_rename": handle_cluster_rename,
    "learning_incorporate": handle_learning_incorporate,
    "learning_train_now": handle_learning_train_now,
    "learning_status": handle_learning_status,
    "health": handle_health,
    "vision_detect": handle_vision_detect,
    "chat_stream": handle_chat_stream,
    "models_list": handle_models_list,
    "rag_embed": handle_rag_embed,
    "rag_embed_query": handle_rag_embed_query,
    "rag_add_chunks": handle_rag_add_chunks,
    "rag_search": handle_rag_search,
    "rag_delete_chunks": handle_rag_delete_chunks,
    "extract_text": handle_extract_text,
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
            _write(
                {
                    "id": req.get("id", ""),
                    "type": "error",
                    "message": f"Unknown request type: {req_type!r}",
                }
            )
            continue

        try:
            await handler(req)
        except Exception as exc:
            _write({"id": req.get("id", ""), "type": "error", "message": str(exc)})


if __name__ == "__main__":
    # Load .env: app data dir (installed app), then engine dir, then dev locations
    try:
        import os

        from dotenv import load_dotenv

        candidates = []
        storage = os.getenv("SOLARIS_STORAGE")
        if storage:
            # O Rust define SOLARIS_STORAGE = <app data>/storage; o .env fica em <app data>,
            # pois o instalador não empacota chaves.
            candidates.append(Path(storage).parent / ".env")
        for env_path in [
            *candidates,
            Path(sys.executable).parent / ".env",
            ENGINE_ROOT / ".env",
            ENGINE_ROOT.parent / "backend" / ".env",  # backward compat
        ]:
            if env_path.exists():
                load_dotenv(env_path)
                break
    except ImportError:
        pass

    from app.vision.detector import start_loading

    start_loading()
    from app.vision.learning import start_worker, stop_worker

    start_worker()
    try:
        asyncio.run(main_loop())
    finally:
        stop_worker()
