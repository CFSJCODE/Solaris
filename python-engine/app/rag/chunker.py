"""Divide texto em chunks com sobreposição para melhor recuperação."""

from __future__ import annotations

# Define o tamanho do chunk e a sobreposição entre chunks
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


# Função para dividir o texto em chunks com sobreposição
def chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunk = text[start : start + CHUNK_SIZE].strip()
        if chunk:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# Função para extrair texto de arquivos PDF, DOCX e outros formatos de texto
def extract_text(content: bytes, mime_type: str) -> str:
    if mime_type == "application/pdf":
        return _extract_pdf(content)
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        import io
        import xml.etree.ElementTree as ET
        import zipfile

        with zipfile.ZipFile(io.BytesIO(content)) as doc:
            if sum(item.file_size for item in doc.infolist()) > 30_000_000:
                raise ValueError("DOCX descompactado excede 30 MB.")
            root = ET.fromstring(doc.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            return "\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns))
    if not (mime_type.startswith("text/") or mime_type in ("application/json", "application/xml")):
        raise ValueError(
            "Formato não suportado. Use PDF textual, DOCX, Markdown, TXT ou código em UTF-8."
        )
    return content.decode("utf-8-sig", errors="strict")


# Função auxiliar para extrair texto de arquivos PDF usando a biblioteca pdfminer
def _extract_pdf(content: bytes) -> str:
    try:
        import io
        from importlib import import_module

        extract_text_to_fp = import_module("pdfminer.high_level").extract_text_to_fp
        LAParams = import_module("pdfminer.layout").LAParams
        out = io.StringIO()
        extract_text_to_fp(io.BytesIO(content), out, laparams=LAParams(), maxpages=200)
        return out.getvalue()
    except ImportError as exc:
        raise ValueError("Leitor de PDF indisponível nesta instalação.") from exc
