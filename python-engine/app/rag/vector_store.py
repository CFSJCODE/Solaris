"""ChromaDB wrapper — file-based vector store, zero instalação."""

# Importa as bibliotecas necessárias
from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path
from typing import Any

_client: Any | None = None


# Função para obter o diretório de armazenamento, verificando a variável de ambiente SOLARIS_STORAGE
def _storage_dir() -> Path:
    base = os.getenv("SOLARIS_STORAGE", "")
    if base:
        return Path(base).resolve()
    return Path(__file__).parent.parent.parent.parent / "storage"


# Função para obter o cliente ChromaDB, criando-o se ainda não existir, e configurando o diretório de armazenamento
def _get_client() -> Any:
    global _client
    if _client is None:
        chromadb = import_module("chromadb")
        ChromaSettings = import_module("chromadb.config").Settings
        chroma_dir = _storage_dir() / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


# Função para gerar o nome da coleção com base no ID do projeto, retornando "default" se o ID for None
def _collection_name(project_id: int | None) -> str:
    return f"project_{project_id}" if project_id is not None else "default"


# Função para adicionar chunks de texto à coleção, incluindo embeddings, textos e metadados
def add_chunks(
    project_id: int | None,
    chunk_ids: list[str],
    embeddings: list[list[float]],
    texts: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    col = _get_client().get_or_create_collection(
        name=_collection_name(project_id),
        metadata={"hnsw:space": "cosine"},
    )
    col.add(ids=chunk_ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


# Função para pesquisar na coleção com base em um embedding de consulta, retornando os resultados com conteúdo, metadados e pontuação
def search(
    project_id: int | None,
    query_embedding: list[float],
    n_results: int = 5,
) -> list[dict[str, Any]]:
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

    hits: list[dict[str, Any]] = []
    for i, doc in enumerate(results["documents"][0]):
        hits.append(
            {
                "content": doc,
                "metadata": results["metadatas"][0][i],
                "score": 1 - results["distances"][0][i],
            }
        )
    return hits


# Função para deletar chunks da coleção com base em seus IDs, ignorando erros se a coleção não existir
def delete_chunks(project_id: int | None, chunk_ids: list[str]) -> None:
    col_name = _collection_name(project_id)
    client = _get_client()
    try:
        col = client.get_collection(col_name)
        col.delete(ids=chunk_ids)
    except Exception:
        pass
