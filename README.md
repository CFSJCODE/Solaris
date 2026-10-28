# Solaris

Plataforma de IA pessoal — chat multi-LLM, RAG por projeto e visão computacional.

![Tauri](https://img.shields.io/badge/Tauri_2-24C8DB?style=flat&logo=tauri&logoColor=white)
![React](https://img.shields.io/badge/React_18-61DAFB?style=flat&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat&logo=vite&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-4169E1?style=flat&logo=postgresql&logoColor=white)
![Rust](https://img.shields.io/badge/Rust-CE422B?style=flat&logo=rust&logoColor=white)
![Anthropic](https://img.shields.io/badge/Anthropic-D97757?style=flat&logo=anthropic&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=flat&logo=opencv&logoColor=white)
![ONNX](https://img.shields.io/badge/ONNX_Runtime-005CED?style=flat&logo=onnx&logoColor=white)

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
| **2 — Chat** ✅ | Anthropic + OpenRouter, streaming SSE, fallback, custos |
| **3 — RAG** | Upload MD/TXT/PDF, embeddings ONNX, busca por projeto |
| **4 — Visão** | Webcam ao vivo, YOLOv8n, detector de cansaço, gestos |

---

## Design System

O SOLARIS usa a paleta **Sunset**: Ember `#EA6113` · Flare `#F88F22` · Gold `#FBB931` · Glow `#FFE3B3`.

Os tokens CSS estão em `frontend/src/styles/solaris.css`. Não use valores de cor codificados — use as variáveis `--sol-*`.
