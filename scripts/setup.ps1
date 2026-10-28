# Solaris — Setup inicial (execute uma vez)
# Requisitos: Python 3.11+, Node.js 20+, Rust/Cargo, PostgreSQL 16

param(
    [switch]$SkipDb
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Write-Host "`n=== Solaris Setup ===" -ForegroundColor Cyan

# ── Python venv ────────────────────────────────────────
Write-Host "`n[1/5] Criando ambiente virtual Python..." -ForegroundColor Yellow
Push-Location "$root\backend"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .venv\Scripts\pip install --upgrade pip --quiet
& .venv\Scripts\pip install -r requirements.txt
Pop-Location

# ── Copiar .env ────────────────────────────────────────
Write-Host "`n[2/5] Configurando .env..." -ForegroundColor Yellow
if (-not (Test-Path "$root\backend\.env")) {
    Copy-Item "$root\backend\.env.example" "$root\backend\.env"
    Write-Host "  -> Edite backend\.env com suas chaves de API" -ForegroundColor Magenta
} else {
    Write-Host "  -> .env já existe, pulando"
}

# ── Node / frontend ────────────────────────────────────
Write-Host "`n[3/5] Instalando dependências do frontend..." -ForegroundColor Yellow
Push-Location "$root\frontend"
npm install --silent
Pop-Location

# ── Banco de dados ─────────────────────────────────────
if (-not $SkipDb) {
    Write-Host "`n[4/5] Criando banco Solaris no PostgreSQL..." -ForegroundColor Yellow
    Write-Host "  Assumindo PostgreSQL rodando em localhost com usuário postgres."
    try {
        psql -U postgres -c "CREATE ROLE solaris LOGIN PASSWORD 'solaris';" 2>$null
        psql -U postgres -c "CREATE DATABASE solaris OWNER solaris;" 2>$null
        psql -U postgres -d solaris -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>$null
        Write-Host "  -> Banco criado com extensão pgvector"
    } catch {
        Write-Host "  -> Execute manualmente se necessário:" -ForegroundColor Magenta
        Write-Host "     psql -U postgres -f scripts\init_db.sql"
    }
} else {
    Write-Host "`n[4/5] Banco de dados: pulado (-SkipDb)" -ForegroundColor Gray
}

# ── Pasta de modelos ───────────────────────────────────
Write-Host "`n[5/5] Criando pasta de modelos..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "$root\models" | Out-Null
Write-Host "  -> Os modelos ONNX serão baixados na primeira execução"

Write-Host "`n=== Setup concluído! ===" -ForegroundColor Green
Write-Host "Execute: .\scripts\dev.ps1" -ForegroundColor Cyan
