"""Separate bounded memory metadata from visible streaming text.

O bloco ``<solaris_memory>`` é emitido pelo modelo ao fim da resposta. Modelos maiores
costumam seguir o formato à risca; modelos menores (Haiku, Gemma) desviam de formas
previsíveis: cercas de código em volta do JSON, quebras de linha cruas dentro das strings,
vírgulas sobrando, conteúdo acima do limite, nome de arquivo sem extensão ou em caixa
diferente, ``content`` como lista, tag de fechamento ausente ou o JSON sem tag nenhuma.

O parser aceita esses desvios, descarta só os itens realmente inválidos (em vez de
rejeitar o lote inteiro) e nunca amplia o conjunto de arquivos permitidos: o nome final
precisa coincidir com um dos arquivos de memória existentes, sem caminhos.
"""

import json
import re
from collections.abc import Iterable
from typing import Any

# Delimitadores do bloco de memória
START = "<solaris_memory>"
END = "</solaris_memory>"
FILES = {"AGENTS.md", "README.md", "CONTRIBUTING.md", "MEMORY.md", "DECISOES.md"}

# Limites alinhados ao armazenamento em Rust (project_memory.rs: ≤ 4000 bytes e 5 itens por arquivo)
MAX_ITEM_BYTES = 3800
MAX_ITEMS_PER_FILE = 5
MAX_UPDATES = 20
MAX_METADATA = 32000

_START_RE = re.compile(r"<\s*solaris_memory\b[^>]*>", re.IGNORECASE)
_END_RE = re.compile(r"<\s*/\s*solaris_memory\s*>", re.IGNORECASE)
_FENCE_RE = re.compile(r"```[A-Za-z0-9_-]*")
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_CREDENTIAL_RE = re.compile(r"\bsk-(?:ant-|or-v1-)?[A-Za-z0-9_-]{16,}\b")

_FILE_KEYS = ("file", "arquivo", "filename", "nome", "name", "path")
_CONTENT_KEYS = ("content", "conteudo", "conteúdo", "text", "texto", "body")
_ALIASES = {
    "decisoes": "DECISOES.md",
    "decisões": "DECISOES.md",
    "decisions": "DECISOES.md",
    "memoria": "MEMORY.md",
    "memória": "MEMORY.md",
    "memory": "MEMORY.md",
    "agents": "AGENTS.md",
    "agentes": "AGENTS.md",
    "readme": "README.md",
    "contributing": "CONTRIBUTING.md",
    "contribuindo": "CONTRIBUTING.md",
}
# Textos de exemplo das instruções do sistema; modelos pequenos às vezes os copiam literalmente.
_PLACEHOLDERS = {
    "contexto técnico, componentes, comandos, configurações, abordagens discutidas",
    "decisão confirmada ou proposta, com origem",
    "síntese curta dos fatos e fontes",
    "registro curto da decisão, origem e se é confirmada ou proposta",
}


class MemoryStream:
    def __init__(self, allowed_files: Iterable[str] | None = None, require_tag: bool = True):
        allowed = set(allowed_files) if allowed_files is not None else set()
        # Lista vazia (projeto sem arquivos listados) cai no conjunto padrão em vez de recusar tudo.
        self.allowed_files = allowed or set(FILES)
        # Sem tag, só aceitamos JSON solto quando a gravação foi pedida explicitamente.
        self.require_tag = require_tag
        self.pending = ""
        self.metadata: str | None = None
        self.overflow = False
        self.raw = ""

    def feed(self, text: str) -> str:
        """Recebe um trecho do stream e devolve a parte visível ao usuário."""
        if len(self.raw) < MAX_METADATA * 2:
            self.raw += text
        if self.metadata is not None:
            self.metadata += text
            if len(self.metadata) > MAX_METADATA:
                self.metadata = self.metadata[:MAX_METADATA]
                self.overflow = True
            return ""
        self.pending += text
        match = _START_RE.search(self.pending)
        if match:
            visible = self.pending[: match.start()]
            self.metadata = self.pending[match.end() :]
            if len(self.metadata) > MAX_METADATA:
                self.metadata = self.metadata[:MAX_METADATA]
                self.overflow = True
            self.pending = ""
            return visible
        # Segura o final que pode ser o começo de uma tag dividida entre trechos.
        cut = self.pending.rfind("<")
        if cut >= 0 and len(self.pending) - cut < 64 and ">" not in self.pending[cut:]:
            visible, self.pending = self.pending[:cut], self.pending[cut:]
            return visible
        visible, self.pending = self.pending, ""
        return visible

    def finish(self) -> tuple[str, list[dict[str, str]], str | None]:
        """Devolve (texto visível restante, atualizações válidas, aviso)."""
        if self.metadata is None:
            if not self.require_tag:
                updates = _parse_payload(self.raw, self.allowed_files)
                if updates:
                    return "", updates, None
            return self.pending, [], None

        # Tenta cada bloco encontrado, do último para o primeiro: modelos pequenos às vezes
        # mencionam a tag no texto antes de emitir o bloco real.
        candidates = _blocks(self.metadata)
        saw_payload = False
        for payload in reversed(candidates):
            updates = _parse_payload(payload, self.allowed_files)
            if updates is None:
                continue
            saw_payload = True
            if updates:
                return "", updates, None
        if saw_payload:
            return "", [], "O bloco de memória não trouxe registros aproveitáveis."
        if self.overflow:
            return (
                "",
                [],
                "A resposta foi salva, mas o registro automático de memória veio incompleto.",
            )
        return (
            "",
            [],
            "A resposta foi salva; o formato da atualização de memória precisa de revisão.",
        )


def _blocks(metadata: str) -> list[str]:
    """Separa o conteúdo após a primeira tag em blocos candidatos (fechados ou não)."""
    parts = _START_RE.split(metadata)
    result = []
    for part in parts:
        end = _END_RE.search(part)
        result.append(part[: end.start()] if end else part)
    return result


def _parse_payload(payload: str, allowed: set[str]) -> list[dict[str, str]] | None:
    """Extrai atualizações de um trecho. ``None`` = nenhum JSON reconhecível."""
    data = _load_json(payload)
    if data is None:
        return None
    items = _items(data)
    if items is None:
        return None
    return _validate(items[:MAX_UPDATES], allowed)


def _load_json(text: str) -> Any:
    text = _FENCE_RE.sub("", text).strip()
    decoder = json.JSONDecoder(strict=False)  # aceita quebras de linha cruas nas strings
    starts = [i for i, c in enumerate(text) if c in "{["]
    for n, start in enumerate(starts):
        for candidate in (text[start:], _TRAILING_COMMA_RE.sub(r"\1", text[start:])):
            try:
                data, _ = decoder.raw_decode(candidate)
            except ValueError:
                continue
            # Só o primeiro objeto pode ser um item avulso {file, content}. Depois dele, aceitar
            # um item solto faria uma lista truncada parecer completa (itens perdidos sem aviso);
            # por isso só vale um envelope explícito {"updates": [...]}, como após prosa com chaves.
            if n > 0 and not (isinstance(data, dict) and _has_envelope(data)):
                continue
            if _items(data) is not None:
                return data
    return None


def _has_envelope(data: dict[str, Any]) -> bool:
    return any(
        isinstance(data.get(k), list)
        for k in ("updates", "atualizacoes", "atualizações", "memory", "memoria")
    )


def _items(data: Any) -> list[Any] | None:
    if isinstance(data, dict):
        for key in ("updates", "atualizacoes", "atualizações", "memory", "memoria"):
            if isinstance(data.get(key), list):
                return data[key]
        if _pick(data, _FILE_KEYS) is not None and _pick(data, _CONTENT_KEYS) is not None:
            return [data]
        return None
    if isinstance(data, list) and all(isinstance(i, dict) for i in data):
        return data
    return None


def _pick(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {str(k).lower(): v for k, v in item.items()}
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def _normalize_file(raw: Any, allowed: set[str]) -> str | None:
    if not isinstance(raw, str):
        return None
    name = raw.strip().strip("`'\"[]").strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    by_lower = {f.lower(): f for f in allowed}
    if name.lower() in by_lower:
        return by_lower[name.lower()]
    stem = name[:-3] if name.lower().endswith(".md") else name
    if f"{stem}.md".lower() in by_lower:
        return by_lower[f"{stem}.md".lower()]
    alias = _ALIASES.get(stem.lower())
    if alias and alias.lower() in by_lower:
        return by_lower[alias.lower()]
    return None


def _normalize_content(raw: Any) -> str | None:
    if isinstance(raw, list):
        lines = [str(x).strip() for x in raw if isinstance(x, (str, int, float)) and str(x).strip()]
        raw = "\n".join(line if line.startswith(("-", "*", "#")) else f"- {line}" for line in lines)
    if not isinstance(raw, str):
        return None
    content = raw.strip()
    if not content or content.lower().rstrip(".") in _PLACEHOLDERS:
        return None
    return _CREDENTIAL_RE.sub("[credencial removida]", content)


def _chunks(content: str) -> list[str]:
    """Divide conteúdo longo em blocos ≤ MAX_ITEM_BYTES, preferindo quebras de parágrafo/linha."""
    if len(content.encode("utf-8")) <= MAX_ITEM_BYTES:
        return [content]
    chunks: list[str] = []
    rest = content
    while rest and len(chunks) < MAX_ITEMS_PER_FILE:
        if len(rest.encode("utf-8")) <= MAX_ITEM_BYTES:
            chunks.append(rest)
            break
        head = rest.encode("utf-8")[:MAX_ITEM_BYTES].decode("utf-8", errors="ignore")
        cut = max(head.rfind("\n\n"), head.rfind("\n"))
        if cut < len(head) // 2:
            cut = head.rfind(" ")
        if cut <= 0:
            cut = len(head)
        chunks.append(head[:cut].strip())
        rest = rest[cut:].strip()
    return [c for c in chunks if c]


def _validate(items: list[Any], allowed: set[str]) -> list[dict[str, str]]:
    valid: list[dict[str, str]] = []
    per_file: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        file_name = _normalize_file(_pick(item, _FILE_KEYS), allowed)
        content = _normalize_content(_pick(item, _CONTENT_KEYS))
        if file_name is None or content is None:
            continue
        for chunk in _chunks(content):
            if per_file.get(file_name, 0) >= MAX_ITEMS_PER_FILE:
                break
            per_file[file_name] = per_file.get(file_name, 0) + 1
            valid.append({"file": file_name, "content": chunk})
    return valid
