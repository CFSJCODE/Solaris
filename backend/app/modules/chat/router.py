"""FastAPI router for the chat module — conversations + streaming SSE."""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.modules.chat.models import Conversation, Message
from app.modules.chat.schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
)
from app.modules.chat.providers import stream_anthropic, stream_openrouter
from app.modules.chat.router_amr import route as amr_route

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _has_anthropic() -> bool:
    return bool(settings.anthropic_api_key)


def _has_openrouter() -> bool:
    return bool(settings.openrouter_api_key)


# ── Conversations CRUD ─────────────────────────────────────────────────────────


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate, db: AsyncSession = Depends(get_db)
):
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
            {"provider": "anthropic", "model": "claude-haiku-3-5-20251101", "label": "Claude Haiku 3.5"},
            {"provider": "anthropic", "model": "claude-sonnet-4-5-20250514", "label": "Claude Sonnet 4.5"},
        ]
    if _has_openrouter():
        models += [
            {"provider": "openrouter", "model": "meta-llama/llama-3.1-8b-instruct:free", "label": "Llama 3.1 8B (free)"},
            {"provider": "openrouter", "model": "mistralai/mistral-7b-instruct:free", "label": "Mistral 7B (free)"},
            {"provider": "openrouter", "model": "google/gemma-2-9b-it:free", "label": "Gemma 2 9B (free)"},
        ]
    return {"models": models, "amr_enabled": True}


# ── SSE streaming endpoint ─────────────────────────────────────────────────────


@router.post("/conversations/{conv_id}/messages")
async def send_message(conv_id: int, body: ChatRequest):
    """Stream an LLM response via SSE. Saves user + assistant messages to DB."""

    async def event_stream() -> AsyncGenerator[str, None]:
        async with SessionLocal() as db:
            # Load conversation
            result = await db.execute(
                select(Conversation)
                .where(Conversation.id == conv_id)
                .options(selectinload(Conversation.messages))
            )
            conv = result.scalar_one_or_none()
            if not conv:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Conversa não encontrada'})}\n\n"
                return

            # Save user message
            user_msg = Message(
                conversation_id=conv_id,
                role="user",
                content=body.message,
            )
            db.add(user_msg)
            await db.flush()
            await db.refresh(user_msg)

            # Build messages history for the LLM
            history = [
                {"role": m.role, "content": m.content}
                for m in conv.messages
            ]
            history.append({"role": "user", "content": body.message})

            # AMR — pick model
            has_ant = _has_anthropic()
            has_or = _has_openrouter()

            if body.preferred_model:
                # Manual override: detect provider by model name pattern
                if "claude" in body.preferred_model:
                    selection_provider = "anthropic"
                else:
                    selection_provider = "openrouter"
                selection_model = body.preferred_model
                selection_reason = "manual override"
            else:
                sel = amr_route(body.message, has_ant, has_or)
                selection_provider = sel.provider
                selection_model = sel.model
                selection_reason = sel.reason

            if not selection_provider:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Nenhum provider configurado. Adicione ANTHROPIC_API_KEY ou OPENROUTER_API_KEY no .env'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'model', 'provider': selection_provider, 'model': selection_model, 'reason': selection_reason})}\n\n"

            # Stream with circuit breaker: try primary, fallback to other provider
            accumulated = ""
            usage_data: dict = {}
            stream_error: str | None = None

            async def try_stream(provider: str, model: str) -> bool:
                nonlocal accumulated, usage_data, stream_error
                try:
                    if provider == "anthropic":
                        gen = stream_anthropic(history, model)
                    else:
                        gen = stream_openrouter(history, model)

                    async for event in gen:
                        if event["type"] == "delta":
                            accumulated += event["text"]
                            yield f"data: {json.dumps({'type': 'delta', 'text': event['text']})}\n\n"
                        elif event["type"] == "done":
                            usage_data = event.get("usage", {})
                    return True
                except Exception as exc:
                    stream_error = str(exc)
                    return False

            # Primary attempt
            success = False
            async for chunk in try_stream(selection_provider, selection_model):
                yield chunk
                success = True  # At least one chunk yielded

            # If primary failed entirely (no chunks), try fallback
            if stream_error and not accumulated:
                fallback_provider = "openrouter" if selection_provider == "anthropic" else "anthropic"
                fallback_model = (
                    "meta-llama/llama-3.1-8b-instruct:free"
                    if fallback_provider == "openrouter"
                    else "claude-haiku-3-5-20251101"
                )
                has_fallback = (
                    has_or if fallback_provider == "openrouter" else has_ant
                )
                if has_fallback:
                    yield f"data: {json.dumps({'type': 'model', 'provider': fallback_provider, 'model': fallback_model, 'reason': 'fallback'})}\n\n"
                    stream_error = None
                    async for chunk in try_stream(fallback_provider, fallback_model):
                        yield chunk

            if stream_error and not accumulated:
                yield f"data: {json.dumps({'type': 'error', 'message': stream_error})}\n\n"
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

            # Update conversation title from first user message
            if len(conv.messages) == 0:
                conv.title = body.message[:80]

            await db.commit()

            yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id, 'usage': usage_data})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
