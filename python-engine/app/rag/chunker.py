"""Divide texto em chunks com sobreposição para melhor recuperação."""
from __future__ import annotations

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


def chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunk = text[start:start + CHUNK_SIZE].strip()
        if chunk:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def extract_text(content: bytes, mime_type: str) -> str:
    if mime_type == "application/pdf":
        return _extract_pdf(content)
    return content.decode("utf-8", errors="replace")


def _extract_pdf(content: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams
        import io
        out = io.StringIO()
        extract_text_to_fp(io.BytesIO(content), out, laparams=LAParams())
        return out.getvalue()
    except ImportError:
        return content.decode("latin-1", errors="replace")
