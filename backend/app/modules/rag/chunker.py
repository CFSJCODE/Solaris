"""Divide texto em chunks com sobreposição para melhor recuperação."""

from __future__ import annotations

CHUNK_SIZE = 512  # caracteres por chunk
CHUNK_OVERLAP = 64  # sobreposição entre chunks consecutivos


def chunk_text(text: str) -> list[str]:
    """Retorna lista de chunks com sobreposição."""
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


def extract_text(content: bytes, mime_type: str) -> str:
    """Extrai texto puro a partir de bytes, baseado no MIME type."""
    if mime_type == "application/pdf":
        return _extract_pdf(content)
    # text/plain, text/markdown, etc.
    return content.decode("utf-8", errors="replace")


def _extract_pdf(content: bytes) -> str:
    try:
        import io

        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams

        out = io.StringIO()
        extract_text_to_fp(io.BytesIO(content), out, laparams=LAParams())
        return out.getvalue()
    except ImportError:
        # pdfminer não instalado — retorna representação bruta
        return content.decode("latin-1", errors="replace")
