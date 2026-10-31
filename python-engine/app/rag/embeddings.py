"""Geração de embeddings com multilingual-e5-small (ONNX, CPU-only). Lazy-loaded."""
from __future__ import annotations

# Importa as bibliotecas necessárias
import os
from importlib import import_module
from pathlib import Path

import numpy as np

# Variáveis globais para armazenar a sessão ONNX e o tokenizador
_session = None
_tokenizer = None

# Função para obter o caminho do modelo de embeddings, verificando se ele existe em diferentes locais
def _model_path() -> Path:
    # Packaged: next to the .exe; dev: storage/models/
    exe_dir = Path(os.getenv("SOLARIS_STORAGE", "")).resolve()
    candidates = [
        exe_dir / "models" / "multilingual-e5-small.onnx",
        Path(__file__).parent.parent.parent.parent / "storage" / "models" / "multilingual-e5-small.onnx",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[-1]

# Função para carregar o modelo de embeddings e o tokenizador, se ainda não estiverem carregados
def _load():
    global _session, _tokenizer
    if _session is not None:
        return

    # Importa as bibliotecas necessárias para ONNX Runtime e Tokenizers
    ort = import_module("onnxruntime")
    Tokenizer = import_module("tokenizers").Tokenizer

    # Verifica se o modelo de embeddings existe e levanta um erro se não for encontrado
    model_path = _model_path()
    if not model_path.exists():
        raise FileNotFoundError(
            f"Modelo de embeddings não encontrado: {model_path}\n"
            "Baixe em: https://huggingface.co/intfloat/multilingual-e5-small/tree/main"
        )

    # Cria uma sessão ONNX Runtime com opções de threads e carrega o tokenizador
    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 2
    opts.intra_op_num_threads = 4
    _session = ort.InferenceSession(str(model_path), sess_options=opts)

    # Carrega o tokenizador a partir do arquivo tokenizer.json localizado no mesmo diretório do modelo
    tokenizer_path = model_path.parent / "tokenizer.json"
    _tokenizer = Tokenizer.from_file(str(tokenizer_path))
    _tokenizer.enable_truncation(max_length=512)
    _tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=512)

# Função para gerar embeddings para uma lista de textos, normalizando os vetores resultantes
def embed(texts: list[str]) -> list[list[float]]:
    _load()
    assert _tokenizer is not None
    assert _session is not None
    prefixed = [f"passage: {t}" for t in texts]
    enc = _tokenizer.encode_batch(prefixed)

    # Cria arrays numpy para os IDs de entrada, máscara de atenção e IDs de tipo de token a partir das codificações
    input_ids: np.ndarray = np.asarray([e.ids for e in enc], dtype=np.int64)
    attention_mask = np.asarray([e.attention_mask for e in enc], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)

    # Executa a sessão ONNX Runtime para obter os embeddings, aplicando máscara de atenção e normalizando os vetores resultantes
    outputs = _session.run(None, {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": token_type_ids,
    })

    # Aplica a máscara de atenção aos embeddings, soma os vetores e normaliza para obter os embeddings finais
    hidden = outputs[0]
    mask = attention_mask[:, :, np.newaxis].astype(np.float32)
    summed = (hidden * mask).sum(axis=1)
    counts = mask.sum(axis=1).clip(min=1e-9)
    pooled = summed / counts
    norms = np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
    return (pooled / norms).tolist()

# Função para gerar embeddings para uma única consulta, normalizando o vetor resultante
def embed_query(query: str) -> list[float]:
    _load()
    assert _tokenizer is not None
    assert _session is not None
    enc = _tokenizer.encode(f"query: {query}")
    input_ids = np.asarray([enc.ids], dtype=np.int64)
    attention_mask = np.asarray([enc.attention_mask], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)

    # Executa a sessão ONNX Runtime para obter os embeddings da consulta, aplicando máscara de atenção e normalizando o vetor resultante
    outputs = _session.run(None, {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": token_type_ids,
    })

    # Aplica a máscara de atenção aos embeddings, soma os vetores e normaliza para obter o embedding final da consulta
    hidden = outputs[0]
    mask = attention_mask[:, :, np.newaxis].astype(np.float32)
    summed = (hidden * mask).sum(axis=1)
    counts = mask.sum(axis=1).clip(min=1e-9)
    pooled = (summed / counts)[0]
    norm = np.linalg.norm(pooled)
    return (pooled / max(norm, np.float32(1e-9))).tolist()
