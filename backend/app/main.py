"""Solaris — FastAPI backend sidecar.

Roda na porta 8765 (interna, não exposta para a rede).
O Tauri inicia este processo automaticamente e o frontend
acessa via proxy Vite (/api → http://localhost:8765).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.modules.projects.router import router as projects_router
from app.modules.chat.router import router as chat_router
from app.modules.rag.router import router as rag_router
from app.modules.vision.router import router as vision_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    await init_db()
    yield


app = FastAPI(
    title="Solaris API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────
app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(chat_router,     prefix="/api/chat",     tags=["chat"])
app.include_router(rag_router,      prefix="/api/rag",      tags=["rag"])
app.include_router(vision_router,   prefix="/api/vision",   tags=["vision"])


@app.get("/api/health", tags=["system"])
async def health():
    return {"status": "ok", "version": "0.1.0"}
