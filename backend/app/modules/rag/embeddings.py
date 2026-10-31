"""Geração de embeddings com multilingual-e5-small (ONNX, CPU-only).

Lazy-loaded: o modelo só é carregado na primeira chamada,
então o startup do app é rápido mesmo sem o arquivo ONNX presente.
"""

from __future__ import annotations

import numpy as np

_session = None
_tokenizer = None


def _load():
    global _session, _tokenizer

    if _session is not None:
        return

    import onnxruntime as ort
    from tokenizers import Tokenizer

    from app.core.config import settings

    model_path = settings.embeddings_model_path
    if not model_path.exists():
        raise FileNotFoundError(
            f"Modelo de embeddings não encontrado: {model_path}\n"
            "Baixe em: https://huggingface.co/intfloat/multilingual-e5-small/tree/main"
        )

    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 2
    opts.intra_op_num_threads = 4
    _session = ort.InferenceSession(str(model_path), sess_options=opts)

    tokenizer_path = model_path.parent / "tokenizer.json"
    _tokenizer = Tokenizer.from_file(str(tokenizer_path))
    _tokenizer.enable_truncation(max_length=512)
    _tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=512)


def embed(texts: list[str]) -> list[list[float]]:
    """Retorna embeddings normalizados (dim=384) para uma lista de textos."""
    _load()

    # multilingual-e5 usa prefix "query:" ou "passage:" — usamos "passage:" para chunks
    prefixed = [f"passage: {t}" for t in texts]
    enc = _tokenizer.encode_batch(prefixed)

    input_ids = np.array([e.ids for e in enc], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)

    outputs = _session.run(
        None,
        {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )

    # Mean pooling sobre o last_hidden_state
    hidden = outputs[0]  # (batch, seq_len, 384)
    mask = attention_mask[:, :, np.newaxis].astype(np.float32)
    summed = (hidden * mask).sum(axis=1)
    counts = mask.sum(axis=1).clip(min=1e-9)
    pooled = summed / counts

    # L2 normalização
    norms = np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
    normalized = pooled / norms

    return normalized.tolist()


def embed_query(query: str) -> list[float]:
    """Embedding para uma query (usa prefix 'query:')."""
    _load()
    prefixed = f"query: {query}"
    enc = _tokenizer.encode(prefixed)

    input_ids = np.array([enc.ids], dtype=np.int64)
    attention_mask = np.array([enc.attention_mask], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)

    outputs = _session.run(
        None,
        {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )

    hidden = outputs[0]
    mask = attention_mask[:, :, np.newaxis].astype(np.float32)
    summed = (hidden * mask).sum(axis=1)
    counts = mask.sum(axis=1).clip(min=1e-9)
    pooled = (summed / counts)[0]

    norm = np.linalg.norm(pooled)
    return (pooled / max(norm, 1e-9)).tolist()
