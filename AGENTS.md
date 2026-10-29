# SOLARIS — Guia para Agentes de IA

Plataforma de IA pessoal (single-user) para Windows: Tauri 2 + Vite/React/TypeScript + FastAPI (Python sidecar) + PostgreSQL 16 + pgvector.

---

## Stack e estrutura

```
solaris/
├── src-tauri/          # Shell Tauri 2 (Rust) — janela, tray, sidecar
├── frontend/           # Vite + React + TypeScript
│   └── src/
│       ├── styles/solaris.css  # Design system SOLARIS (tokens --sol-*)
│       ├── components/
│       ├── pages/
│       └── hooks/
├── backend/            # FastAPI Python sidecar
│   └── app/
│       ├── core/       # config, database (SQLAlchemy 2 async)
│       └── modules/
│           ├── chat/   # Roteador AMR + streaming SSE
│           ├── projects/
│           ├── rag/    # Embeddings ONNX + pgvector
│           └── vision/ # YOLOv8n ONNX + webcam
├── models/             # Pesos ONNX (não versionados)
├── storage/            # Arquivos do usuário (não versionados)
└── scripts/            # dev.ps1, setup.ps1, init_db.sql
```

---

## Regras obrigatórias

### Segurança
- **Nunca commitar chaves de API.** Elas ficam somente em `backend/.env` (já no `.gitignore`).
- O backend escuta em `127.0.0.1:8765` apenas — nunca expor externamente.
- Nunca incluir chaves em código, logs, mensagens ou comentários.

### Código
- **Python:** async/await em todo o backend; SQLAlchemy 2 async (`AsyncSession`); Pydantic v2.
- **TypeScript:** sem `any` explícito; componentes funcionais com hooks.
- **CSS:** usar somente variáveis `--sol-*` do design system. Nunca hardcodar valores de cor.
- Não adicionar tratamento de erro para cenários impossíveis; não criar abstrações prematuras.
- Sem comentários que explicam o que o código já diz — só comentários para o "por quê" não-óbvio.

### Git
- Commits atômicos e descritivos em português ou inglês.
- Nunca commitar diretamente em `main` sem revisão.
- Push acompanhado de PR se a branch não for a principal de desenvolvimento.

---

## Design system SOLARIS

Paleta **Sunset**: Ember `#EA6113` · Flare `#F88F22` · Gold `#FBB931` · Glow `#FFE3B3`

Tokens definidos em `frontend/src/styles/solaris.css`:

| Token | Uso |
|---|---|
| `--sol-bg` | Fundo da aplicação (`#0B0D12`) |
| `--sol-surface` | Superfícies elevadas (`#171B25`) |
| `--sol-border` | Bordas (`rgba(255,255,255,.08)`) |
| `--sol-text` | Texto principal (`#E8EAF0`) |
| `--sol-text-muted` | Texto secundário (`rgba(232,234,240,.45)`) |
| `--sol-ember` | `#EA6113` |
| `--sol-flare` | `#F88F22` |
| `--sol-gold` | `#FBB931` |
| `--sol-glow` | `#FFE3B3` |
| `--sol-sunset` | Gradiente diagonal Ember→Gold |
| `--sol-success` | `#4CAF82` |
| `--sol-error` | `#E05C5C` |

---

## Backend — FastAPI

- **Porta:** `127.0.0.1:8765`
- **Variáveis de ambiente:** lidas via `backend/app/core/config.py` (Pydantic Settings)
- **Banco:** PostgreSQL 16 com pgvector. Conexão async via `asyncpg`.
- **Sessão DB:** `AsyncSession` via `SessionLocal()` — usar `async with SessionLocal() as db:` dentro de generators de streaming (não usar `Depends(get_db)` em `StreamingResponse`).
- **SSE:** `StreamingResponse` com generator async; formato `data: <json>\n\n`; evento final `{"type":"done"}`.

### Módulo chat (implementado — Etapa 2 ✅)
- `router_amr.py`: Roteamento por heurística de palavras-chave → Anthropic Haiku/Sonnet ou OpenRouter (modelos free).
- `providers.py`: Streaming Anthropic (`AsyncAnthropic`) e OpenRouter (`httpx` async).
- `router.py`: Endpoint SSE com circuit breaker (fallback automático se provider primário falhar).
- `models.py`: ORM `Conversation` + `Message` com rastreamento de tokens e custo USD.

### Próximos módulos
- **RAG (Etapa 3):** embeddings com `multilingual-e5-small` (ONNX), armazenados em pgvector, isolados por projeto.
- **Visão (Etapa 4):** YOLOv8n ONNX, webcam via OpenCV, detector de cansaço (EAR), gestos de volume.

---

## Frontend — React

- **Roteamento:** estado local em `App.tsx` (sem React Router — SPA com 4 views).
- **Comunicação:** `fetch` para endpoints REST; `ReadableStream` para SSE de streaming.
- **Hook principal:** `useChat` em `frontend/src/hooks/useChat.ts`.
- **Vite proxy:** `/api/*` → `http://127.0.0.1:8765` (configurado em `vite.config.ts`).

---

## Hardware e performance

- **CPU:** Ryzen 5 4600G (6c/12t), sem GPU dedicada, 32 GB RAM.
- Modelos ONNX devem rodar em CPU. Preferir INT8, input 320–416 px.
- Modelos pesados (>100 MB) ficam em `models/` e não são versionados.
- Não usar CUDA, torch com GPU, ou Docker.

---

## Roteiro MVP

| Etapa | Status |
|---|---|
| 1 — Fundação (Tauri 2, scaffold, DB) | ✅ |
| 2 — Chat (AMR, streaming, custos) | ✅ |
| 3 — RAG (embeddings ONNX, pgvector) | ⬜ |
| 4 — Visão (YOLOv8n, webcam, gestos) | ⬜ |
