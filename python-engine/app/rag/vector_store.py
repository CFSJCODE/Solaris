"""ChromaDB wrapper — file-based vector store, zero instalação."""
from __future__ import annotations

import os
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

_client: chromadb.ClientAPI | None = None


def _storage_dir() -> Path:
    base = os.getenv("SOLARIS_STORAGE", "")
    if base:
        return Path(base).resolve()
    return Path(__file__).parent.parent.parent.parent / "storage"


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        chroma_dir = _storage_dir() / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def _collection_name(project_id: int | None) -> str:
    return f"project_{project_id}" if project_id is not None else "default"


def add_chunks(
    project_id: int | None,
    chunk_ids: list[str],
    embeddings: list[list[float]],
    texts: list[str],
    metadatas: list[dict],
) -> None:
    col = _get_client().get_or_create_collection(
        name=_collection_name(project_id),
        metadata={"hnsw:space": "cosine"},
    )
    col.add(ids=chunk_ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


def search(
    project_id: int | None,
    query_embedding: list[float],
    n_results: int = 5,
) -> list[dict]:
    col_name = _collection_name(project_id)
    client = _get_client()
    try:
        col = client.get_collection(col_name)
    except Exception:
        return []

    results = col.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for i, doc in enumerate(results["documents"][0]):
        hits.append({
            "content": doc,
            "metadata": results["metadatas"][0][i],
            "score": 1 - results["distances"][0][i],
        })
    return hits


def delete_chunks(project_id: int | None, chunk_ids: list[str]) -> None:
    col_name = _collection_name(project_id)
    client = _get_client()
    try:
        col = client.get_collection(col_name)
        col.delete(ids=chunk_ids)
    except Exception:
        pass
