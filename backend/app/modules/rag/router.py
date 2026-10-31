"""RAG — upload, indexação e busca de documentos."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.rag import chunker, embeddings, vector_store
from app.modules.rag.models import Chunk, Document

router = APIRouter()

ALLOWED_MIME = {
    "text/plain",
    "text/markdown",
    "application/pdf",
}
MAX_FILE_MB = 20


# ── Schemas ───────────────────────────────────────────────────────────────────


class DocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    size_bytes: int
    chunk_count: int

    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    content: str
    filename: str
    chunk_index: int
    score: float


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    project_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Document)
    if project_id is not None:
        q = q.where(Document.project_id == project_id)
    result = await db.execute(q.order_by(Document.id.desc()))
    return result.scalars().all()


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: Annotated[UploadFile, File()],
    project_id: Annotated[int | None, Form()] = None,
    db: AsyncSession = Depends(get_db),
):
    mime = file.content_type or "text/plain"
    if mime not in ALLOWED_MIME:
        raise HTTPException(400, f"Tipo não suportado: {mime}. Use TXT, MD ou PDF.")

    content = await file.read()
    if len(content) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(413, f"Arquivo maior que {MAX_FILE_MB} MB.")

    # Extrai texto e divide em chunks
    text = chunker.extract_text(content, mime)
    chunks_text = chunker.chunk_text(text)
    if not chunks_text:
        raise HTTPException(422, "Nenhum texto extraído do arquivo.")

    # Gera embeddings (pode demorar para arquivos grandes)
    vecs = embeddings.embed(chunks_text)

    # Persiste documento no SQLite
    doc = Document(
        project_id=project_id,
        filename=file.filename or "arquivo",
        mime_type=mime,
        size_bytes=len(content),
        chunk_count=len(chunks_text),
    )
    db.add(doc)
    await db.flush()  # obtém doc.id

    # Persiste chunks e vetores
    chunk_ids: list[str] = []
    chunk_objs: list[Chunk] = []
    metas: list[dict] = []

    for i, (text_chunk, vec) in enumerate(zip(chunks_text, vecs)):
        cid = str(uuid.uuid4())
        chunk_ids.append(cid)
        chunk_objs.append(
            Chunk(document_id=doc.id, chunk_index=i, content=text_chunk, chroma_id=cid)
        )
        metas.append({"document_id": doc.id, "filename": doc.filename, "chunk_index": i})

    db.add_all(chunk_objs)

    vector_store.add_chunks(
        project_id=project_id,
        chunk_ids=chunk_ids,
        embeddings=vecs,
        texts=chunks_text,
        metadatas=metas,
    )

    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Documento não encontrado.")

    # Coleta IDs dos chunks para deletar do ChromaDB
    result = await db.execute(select(Chunk).where(Chunk.document_id == document_id))
    chroma_ids = [c.chroma_id for c in result.scalars().all()]

    vector_store.delete_chunks(doc.project_id, chroma_ids)
    await db.delete(doc)


@router.get("/search", response_model=list[SearchResult])
async def search_documents(
    q: str,
    project_id: int | None = None,
    n: int = 5,
):
    query_vec = embeddings.embed_query(q)
    hits = vector_store.search(project_id, query_vec, n_results=n)

    return [
        SearchResult(
            content=h["content"],
            filename=h["metadata"].get("filename", ""),
            chunk_index=h["metadata"].get("chunk_index", 0),
            score=round(h["score"], 4),
        )
        for h in hits
    ]


# ── Função helper para o módulo de chat ──────────────────────────────────────


async def retrieve_context(query: str, project_id: int | None, n: int = 3) -> str:
    """Retorna contexto RAG formatado para injetar no prompt do chat."""
    try:
        query_vec = embeddings.embed_query(query)
        hits = vector_store.search(project_id, query_vec, n_results=n)
    except Exception:
        return ""

    if not hits:
        return ""

    parts = []
    for h in hits:
        parts.append(
            f"[{h['metadata'].get('filename', 'doc')} — trecho {h['metadata'].get('chunk_index', 0) + 1}]\n"
            f"{h['content']}"
        )
    return "\n\n---\n\n".join(parts)
