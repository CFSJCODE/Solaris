# Solaris

Plataforma de IA pessoal — chat multi-LLM, RAG por projeto e visão computacional.

**Stack:** Tauri 2 · Vite + React + TypeScript · FastAPI (Python) · PostgreSQL + pgvector

---

## Pré-requisitos

| Ferramenta | Versão mínima | Link |
|---|---|---|
| Python | 3.11 | https://python.org |
| Node.js | 20 LTS | https://nodejs.org |
| Rust + Cargo | estável | https://rustup.rs |
| PostgreSQL | 16 | https://postgresql.org |
| pgvector | 0.7+ | https://github.com/pgvector/pgvector |

> **pgvector no Windows:** baixe o instalador em https://github.com/pgvector/pgvector/releases ou use `pg_config --pkglibdir` para localizar o diretório e copie `vector.dll` + `vector.control` manualmente.

---

## Configuração inicial (uma vez)

```powershell
.\scripts\setup.ps1
```

Edite `backend\.env` com suas chaves de API (modelo em `backend\.env.example`).

---

## Rodar em desenvolvimento

```powershell
.\scripts\dev.ps1
```

Isso inicia:
- **Backend FastAPI** → `http://127.0.0.1:8765` (porta interna)
- **Vite dev server** → `http://localhost:5173`
- **Janela Tauri** → app nativo Windows

---

## Estrutura do projeto

```
solaris/
├── src-tauri/          # Shell Tauri 2 (Rust mínimo)
│   ├── src/
│   │   ├── main.rs
│   │   └── lib.rs      # setup, sidecar, tray
│   └── tauri.conf.json
├── frontend/           # Vite + React + TypeScript
│   ├── src/
│   │   ├── App.tsx
│   │   ├── styles/solaris.css   # Design system SOLARIS
│   │   ├── components/
│   │   ├── pages/
│   │   └── hooks/
│   └── vite.config.ts
├── backend/            # FastAPI sidecar (Python)
│   ├── app/
│   │   ├── main.py
│   │   ├── core/       # config, database
│   │   └── modules/
│   │       ├── chat/   # Roteador de modelos (Etapa 2)
│   │       ├── projects/
│   │       ├── rag/    # Embeddings + pgvector (Etapa 3)
│   │       └── vision/ # YOLOv8n + webcam (Etapa 4)
│   └── requirements.txt
├── models/             # Pesos ONNX (não versionados)
├── storage/            # Arquivos do usuário (não versionados)
└── scripts/
    ├── dev.ps1
    ├── setup.ps1
    └── init_db.sql
```

---

## Roteiro do MVP

| Etapa | Conteúdo |
|---|---|
| **1 — Fundação** ✅ | Scaffold, design system, backend stub, scripts |
| **2 — Chat** | Anthropic + OpenRouter, streaming SSE, fallback, custos |
| **3 — RAG** | Upload MD/TXT/PDF, embeddings ONNX, busca por projeto |
| **4 — Visão** | Webcam ao vivo, YOLOv8n, detector de cansaço, gestos |

---

## Design System

O SOLARIS usa a paleta **Sunset**: Ember `#EA6113` · Flare `#F88F22` · Gold `#FBB931` · Glow `#FFE3B3`.

Os tokens CSS estão em `frontend/src/styles/solaris.css`. Não use valores de cor codificados — use as variáveis `--sol-*`.
