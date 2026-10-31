<div align="center">

# SOLARIS

**Plataforma de IA pessoal para Windows — chat multi-LLM, RAG local, visão em tempo real e aprendizado adaptativo, tudo rodando na sua máquina.**

[![Versão](https://img.shields.io/badge/versão-0.5.4-blue?style=for-the-badge)](https://github.com/CFSJCODE/Solaris/releases)
[![Plataforma](https://img.shields.io/badge/plataforma-Windows-0078D4?style=for-the-badge&logo=windows)](https://github.com/CFSJCODE/Solaris)
[![Licença](https://img.shields.io/badge/licença-privado-red?style=for-the-badge)](LICENSE)

---

### Stack

[![Tauri](https://img.shields.io/badge/Tauri_2-24C8D8?style=flat-square&logo=tauri&logoColor=white)](https://tauri.app)
[![Rust](https://img.shields.io/badge/Rust-000000?style=flat-square&logo=rust&logoColor=white)](https://www.rust-lang.org)
[![React](https://img.shields.io/badge/React-20232A?style=flat-square&logo=react&logoColor=61DAFB)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev)
[![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org)
[![ONNX](https://img.shields.io/badge/ONNX_Runtime-005CED?style=flat-square&logo=onnx&logoColor=white)](https://onnxruntime.ai)
[![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white)](https://opencv.org)

### Modelos de IA

[![Anthropic](https://img.shields.io/badge/Anthropic_Claude-D4A27F?style=flat-square)](https://anthropic.com)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-6B46C1?style=flat-square)](https://openrouter.ai)
[![YOLOv8](https://img.shields.io/badge/YOLOv8n_ONNX-00FFFF?style=flat-square)](https://docs.ultralytics.com)

### Qualidade

[![Ruff](https://img.shields.io/badge/Ruff-D7FF64?style=flat-square&logo=ruff&logoColor=black)](https://docs.astral.sh/ruff)
[![Prettier](https://img.shields.io/badge/Prettier-F7B93E?style=flat-square&logo=prettier&logoColor=black)](https://prettier.io)
[![Pyright](https://img.shields.io/badge/Pyright-0_erros-brightgreen?style=flat-square)](https://github.com/microsoft/pyright)
[![Testes](https://img.shields.io/badge/testes-49_passando-brightgreen?style=flat-square)](python-engine/tests)

</div>

---

## O que é o SOLARIS

SOLARIS é uma plataforma de inteligência artificial 100 % local para Windows. Ela reúne quatro capacidades em um único aplicativo instalável (`.msi`), sem nuvem obrigatória, sem Docker e sem servidor externo:

| Capacidade | O que faz |
|---|---|
| **Chat multi-LLM** | Conversa com Claude (Anthropic) e qualquer modelo via OpenRouter, com streaming, roteamento adaptativo e custo por mensagem exibido em tempo real |
| **RAG local** | Indexa PDFs, DOCX, Markdown e código no SQLite local; busca trechos relevantes e os injeta automaticamente no contexto da conversa |
| **Visão em tempo real** | Detecção de objetos ao vivo pela webcam com YOLOv8n ONNX, 80 classes COCO em português, sem GPU necessária |
| **Aprendizado adaptativo** | Seleciona quadros da câmera, verifica rótulos e treina ciclos de candidatas localmente; promoção condicionada à avaliação |

Tudo roda em CPU. Nenhum dado sai da máquina sem sua instrução explícita.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│  Aplicativo Windows (.msi)                              │
│                                                         │
│  ┌─────────────────────┐   ┌──────────────────────────┐ │
│  │  Frontend           │   │  Tauri 2 (Rust)          │ │
│  │  React + TypeScript │◄──┤  janela · tray · IPC     │ │
│  │  Vite · SPA         │   │  SQLite · sidecar mgmt   │ │
│  └─────────────────────┘   └──────────┬───────────────┘ │
│                                        │ stdin/stdout    │
│                             ┌──────────▼───────────────┐ │
│                             │  Python Engine (sidecar) │ │
│                             │  FastAPI · ONNX Runtime  │ │
│                             │  OpenCV · LangChain      │ │
│                             │  SQLite-vec · Pyright    │ │
│                             └──────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
   Anthropic / OpenRouter         Disco local
   (somente quando o             (%APPDATA%\com.cfsjcode.solaris)
    usuário envia mensagem)       bancos · pesos ONNX · memória
```

**Sem HTTP externo, sem Docker, sem banco de dados remoto.** O Tauri gerencia a janela e inicia o sidecar Python via `stdin/stdout` (JSON Lines). O frontend se comunica com o Rust por `invoke` e Channels; o Rust repassa para o Python.

---

## Funcionalidades

### Projetos como espaços de trabalho
- Crie projetos com objetivo e instruções próprias
- Adicione PDF, DOCX, Markdown, TXT ou código à biblioteca — texto extraído e indexado localmente
- Memória viva em Markdown: o modelo atualiza `MEMORY.md`, `AGENTS.md` e `DECISOES.md` automaticamente após decisões duráveis
- Histórico de versões dos arquivos de memória, recuperável pela interface

### Chat com roteamento inteligente
- Streaming SSE com Claude e qualquer modelo OpenRouter
- Custo estimado por mensagem (tokens de entrada + saída)
- Fallback automático de provedor em caso de falha
- Contexto montado dinamicamente: trechos de documentos + memória + instruções + histórico

### Visão e detecção ao vivo
- Webcam ao vivo com YOLOv8n ONNX FP32, ~1 FPS em Ryzen 4600G (CPU only)
- 80 classes COCO exibidas em português brasileiro
- Pausar quadro → desenhar caixas → anotar objetos → salvar revisão no projeto
- Aprendizado ativo: coleta quadros, descarta repetição/desfoque, verifica com detector maior, treina candidatas em processo separado

### Sem dependências externas obrigatórias
- Instalador `.msi` único gerado com `scripts/build.ps1`
- Credenciais de API em `.env` local, nunca empacotadas ou versionadas
- SQLite como único banco de dados; sem PostgreSQL, Redis ou MinIO

---

## Requisitos

| Item | Mínimo |
|---|---|
| Sistema operacional | Windows 10/11 (64-bit) |
| CPU | x86-64 com AVX2 (Ryzen/Intel 8ª geração+) |
| RAM | 8 GB (16 GB recomendado) |
| Disco | 2 GB livres |
| GPU | Não necessária |
| Webcam | Opcional (funcionalidade de visão) |

> Desenvolvido e testado em Ryzen 5 4600G, 32 GB RAM, sem GPU discreta.

---

## Instalação

1. Baixe o instalador na página de [Releases](https://github.com/CFSJCODE/Solaris/releases)
2. Execute `SOLARIS_x.x.x_x64_en-US.msi` e siga o assistente
3. Crie o arquivo de credenciais em `%APPDATA%\com.cfsjcode.solaris\.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
```

4. Abra o SOLARIS pelo Menu Iniciar

---

## Desenvolvimento

```powershell
# Pré-requisitos: Node.js 20+, Python 3.11, Rust 1.77+

# Frontend
npm --prefix frontend install
npm --prefix frontend run dev

# Engine Python
cd python-engine
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# Testes Python (49)
python -m pytest tests/ -v

# Lint e formato
python -m ruff check .
python -m ruff format .

# Testes Rust
cargo test --lib --manifest-path src-tauri/Cargo.toml

# Gerar instalador .msi
.\scripts\build.ps1
```

**Antes de contribuir:** leia [`AGENTS.md`](AGENTS.md), [`MEMORY.md`](MEMORY.md), [`DECISOES.md`](DECISOES.md) e [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Regras do ciclo autônomo e do roteador de modelos |
| [`docs/aprendizado-autonomo.md`](docs/aprendizado-autonomo.md) | Pipeline de aprendizado ativo e limites operacionais |
| [`docs/revisao-quadros.md`](docs/revisao-quadros.md) | Interface de anotação de quadros da câmera |
| [`docs/visao.md`](docs/visao.md) | Detalhes do subsistema de visão computacional |
| [`DECISOES.md`](DECISOES.md) | Registro de decisões de arquitetura |

---

## Estado atual (0.5.4)

- ✅ Chat multi-LLM com streaming e custo por mensagem
- ✅ RAG local: indexação e busca FTS5 em SQLite
- ✅ Visão ao vivo com YOLOv8n ONNX, anotação e revisão de quadros
- ✅ Aprendizado ativo com avaliação antes da promoção
- ✅ Memória viva em Markdown com histórico de versões
- ✅ Instalador `.msi` nativo Windows
- 🔄 Classe `powerbank` em ciclo de validação (complemento provisório isolado)
- 📋 Pendente: OCR, busca semântica por embeddings, sincronização externa de Markdown

---

<div align="center">
<sub>Projeto pessoal · Desenvolvido por CFSJCODE · Ryzen 5 4600G · CPU only</sub>
</div>
