"""Pydantic schemas for the chat module."""

from datetime import datetime

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    model: str | None
    provider: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    title: str
    project_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationCreate(BaseModel):
    title: str = "Nova conversa"
    project_id: int | None = None


class ChatRequest(BaseModel):
    conversation_id: int | None = None
    message: str
    project_id: int | None = None
    preferred_model: str | None = None  # override AMR
