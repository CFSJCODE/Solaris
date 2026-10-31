"""FastAPI router for the chat module — conversations + streaming SSE."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.modules.chat.models import Conversation, Message
from app.modules.chat.providers import stream_anthropic, stream_openrouter
from app.modules.chat.router_amr import route as amr_route
from app.modules.chat.schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
)
from app.modules.rag.router import retrieve_context

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _has_anthropic() -> bool:
    return bool(settings.anthropic_api_key)


def _has_openrouter() -> bool:
    return bool(settings.openrouter_api_key)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ── Conversations CRUD ─────────────────────────────────────────────────────────


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Conversation).order_by(Conversation.updated_at.desc()))
    return result.scalars().all()


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationCreate, db: AsyncSession = Depends(get_db)):
    conv = Conversation(title=body.title, project_id=body.project_id)
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
async def get_conversation(conv_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conv_id)
        .options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return conv


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(conv_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Conversation).where(Conversation.id == conv_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    await db.delete(conv)


# ── Models info ────────────────────────────────────────────────────────────────


@router.get("/models")
async def list_models():
    models = []
    if _has_anthropic():
        models += [
            {
                "provider": "anthropic",
                "model": "claude-haiku-3-5-20251101",
                "label": "Claude Haiku 3.5",
            },
            {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250514",
                "label": "Claude Sonnet 4.5",
            },
        ]
    if _has_openrouter():
        models += [
            {
                "provider": "openrouter",
                "model": "meta-llama/llama-3.1-8b-instruct:free",
                "label": "Llama 3.1 8B (free)",
            },
            {
                "provider": "openrouter",
                "model": "mistralai/mistral-7b-instruct:free",
                "label": "Mistral 7B (free)",
            },
            {
                "provider": "openrouter",
                "model": "google/gemma-2-9b-it:free",
                "label": "Gemma 2 9B (free)",
            },
        ]
    return {"models": models, "amr_enabled": True}


# ── SSE streaming endpoint ─────────────────────────────────────────────────────


@router.post("/conversations/{conv_id}/messages")
async def send_message(conv_id: int, body: ChatRequest):
    """Stream LLM response via SSE. Saves user + assistant messages to DB."""

    async def event_stream():
        async with SessionLocal() as db:
            # Load conversation with history
            result = await db.execute(
                select(Conversation)
                .where(Conversation.id == conv_id)
                .options(selectinload(Conversation.messages))
            )
            conv = result.scalar_one_or_none()
            if not conv:
                yield _sse({"type": "error", "message": "Conversa não encontrada"})
                return

            # Save user message first
            user_msg = Message(conversation_id=conv_id, role="user", content=body.message)
            db.add(user_msg)
            await db.flush()

            # Build LLM messages history (existing + new)
            history = [{"role": m.role, "content": m.content} for m in conv.messages]
            history.append({"role": "user", "content": body.message})

            # RAG: retrieve relevant document context
            rag_context = await retrieve_context(body.message, conv.project_id, n=3)
            system_prompt = (
                f"Contexto relevante dos documentos do projeto:\n\n{rag_context}"
                if rag_context
                else None
            )

            # AMR: pick provider + model
            has_ant = _has_anthropic()
            has_or = _has_openrouter()

            if body.preferred_model:
                prov = "anthropic" if "claude" in body.preferred_model else "openrouter"
                model = body.preferred_model
                reason = "manual override"
            else:
                sel = amr_route(body.message, has_ant, has_or)
                prov = sel.provider
                model = sel.model
                reason = sel.reason

            if not prov:
                yield _sse(
                    {
                        "type": "error",
                        "message": "Nenhum provider configurado. Adicione ANTHROPIC_API_KEY ou OPENROUTER_API_KEY no .env",
                    }
                )
                return

            yield _sse({"type": "model", "provider": prov, "model": model, "reason": reason})

            # Stream with circuit breaker
            accumulated = ""
            usage_data: dict = {}
            last_error = ""

            async def do_stream(provider: str, mdl: str) -> bool:
                nonlocal accumulated, usage_data, last_error
                try:
                    gen = (
                        stream_anthropic(history, mdl)
                        if provider == "anthropic"
                        else stream_openrouter(history, mdl)
                    )
                    async for event in gen:
                        if event["type"] == "delta":
                            accumulated += event["text"]
                        elif event["type"] == "done":
                            usage_data = event.get("usage", {})
                    return True
                except Exception as exc:
                    last_error = str(exc)
                    return False

            # Run primary stream, collect all chunks, then yield
            # (SSE requires yielding, so we use a different approach: yield as we go)
            primary_ok = True
            try:
                gen = (
                    stream_anthropic(history, model, system=system_prompt)
                    if prov == "anthropic"
                    else stream_openrouter(history, model, system=system_prompt)
                )
                async for event in gen:
                    if event["type"] == "delta":
                        accumulated += event["text"]
                        yield _sse({"type": "delta", "text": event["text"]})
                    elif event["type"] == "done":
                        usage_data = event.get("usage", {})
            except Exception as exc:
                primary_ok = False
                last_error = str(exc)

            # Circuit breaker: fallback if primary failed entirely
            if not primary_ok and not accumulated:
                fallback_prov = "openrouter" if prov == "anthropic" else "anthropic"
                fallback_mdl = (
                    "meta-llama/llama-3.1-8b-instruct:free"
                    if fallback_prov == "openrouter"
                    else "claude-haiku-3-5-20251101"
                )
                has_fallback = has_or if fallback_prov == "openrouter" else has_ant

                if has_fallback:
                    yield _sse(
                        {
                            "type": "model",
                            "provider": fallback_prov,
                            "model": fallback_mdl,
                            "reason": "fallback",
                        }
                    )
                    try:
                        gen2 = (
                            stream_anthropic(history, fallback_mdl, system=system_prompt)
                            if fallback_prov == "anthropic"
                            else stream_openrouter(history, fallback_mdl, system=system_prompt)
                        )
                        async for event in gen2:
                            if event["type"] == "delta":
                                accumulated += event["text"]
                                yield _sse({"type": "delta", "text": event["text"]})
                            elif event["type"] == "done":
                                usage_data = event.get("usage", {})
                    except Exception as exc2:
                        last_error = str(exc2)

            # If nothing was generated, report error
            if not accumulated:
                yield _sse({"type": "error", "message": last_error or "Falha ao gerar resposta"})
                await db.rollback()
                return

            # Save assistant message
            assistant_msg = Message(
                conversation_id=conv_id,
                role="assistant",
                content=accumulated,
                model=usage_data.get("model"),
                provider=usage_data.get("provider"),
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                cost_usd=usage_data.get("cost_usd", 0.0),
            )
            db.add(assistant_msg)
            await db.flush()
            await db.refresh(assistant_msg)

            # Auto-title conversation from first message
            if not conv.messages:
                conv.title = body.message[:80]

            await db.commit()

            yield _sse({"type": "done", "message_id": assistant_msg.id, "usage": usage_data})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
