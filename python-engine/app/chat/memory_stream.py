"""Separate bounded memory metadata from visible streaming text."""

# Importa as bibliotecas necessárias
import json
import re
from collections.abc import Iterable
from typing import Any, cast

# Define os delimitadores de início e fim para a memória
START = '<solaris_memory>'
END = '</solaris_memory>'
FILES = {'AGENTS.md', 'README.md', 'CONTRIBUTING.md', 'MEMORY.md', 'DECISOES.md'}

# Classe para gerenciar o fluxo de memória
class MemoryStream:

    # Inicializa a classe MemoryStream com arquivos permitidos, pendentes e metadados
    def __init__(self, allowed_files: Iterable[str] | None = None):
        self.allowed_files = set(allowed_files) if allowed_files is not None else FILES
        self.pending = ''
        self.metadata = None
        self.overflow = False

    # Alimenta o fluxo de memória com texto, separando a parte visível da parte de metadados
    def feed(self, text: str) -> str:
        if self.metadata is not None:
            self.metadata += text
            if len(self.metadata) > 32000:
                self.metadata = self.metadata[:32000]
                self.overflow = True
            return ''
        self.pending += text
        index = self.pending.find(START)
        if index >= 0:
            visible = self.pending[:index]
            self.metadata = self.pending[index + len(START):]
            if len(self.metadata)>32000:
                self.metadata=self.metadata[:32000]
                self.overflow=True
            self.pending = ''
            return visible
        carry = len(START) - 1
        visible, self.pending = self.pending[:-carry], self.pending[-carry:]
        return visible

    # Finaliza o fluxo de memória, validando e retornando os metadados processados
    def finish(self) -> tuple[str, list[dict[str, str]], str | None]:
        if self.metadata is None:
            return self.pending, [], None
        if self.overflow or END not in self.metadata:
            return '', [], 'A resposta foi salva, mas o registro automático de memória veio incompleto.'
        try:
            data = json.loads(self.metadata.split(END, 1)[0])
            if not isinstance(data, dict):
                raise ValueError('invalid updates')

            data = cast(dict[str, Any], data)
            updates = data.get('updates', [])
            if not isinstance(updates, list):
                raise ValueError('invalid updates')
            updates = cast(list[Any], updates)
            if len(updates) > 20:
                raise ValueError('invalid updates')

            valid: list[dict[str, str]] = []
            for item in updates:
                if not isinstance(item, dict):
                    raise ValueError('invalid file')
                item = cast(dict[str, Any], item)

                raw_file_name = item.get('file')
                if not isinstance(raw_file_name, str):
                    raise ValueError('invalid file')
                file_name = raw_file_name
                if file_name not in self.allowed_files:
                    raise ValueError('invalid file')

                raw_content = item.get('content')
                if not isinstance(raw_content, str):
                    raise ValueError('invalid content')
                content = raw_content
                if not 0 < len(content.encode('utf-8')) <= 4000:
                    raise ValueError('invalid content')
                if re.search(r'\bsk-(?:ant-|or-v1-)?[A-Za-z0-9_-]{16,}\b', content):
                    raise ValueError('credential-like content')

                valid.append({'file': file_name, 'content': content.strip()})
            return '', valid, None
        except (ValueError, TypeError, AttributeError):
            return '', [], 'A resposta foi salva; o formato da atualização de memória precisa de revisão.'
