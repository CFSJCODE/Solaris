# Solaris — Ambiente de desenvolvimento
# Inicia o backend FastAPI + Tauri dev (que já sobe o Vite)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Write-Host "`n=== Solaris Dev ===" -ForegroundColor Cyan

# ── Backend ────────────────────────────────────────────
Write-Host "[1/2] Iniciando backend FastAPI (porta 8765)..." -ForegroundColor Yellow
$backendJob = Start-Process -FilePath "$root\backend\.venv\Scripts\uvicorn.exe" `
    -ArgumentList "app.main:app --host 127.0.0.1 --port 8765 --reload" `
    -WorkingDirectory "$root\backend" `
    -PassThru -NoNewWindow

Write-Host "  PID do backend: $($backendJob.Id)"
Start-Sleep -Seconds 2

# ── Tauri dev (inclui o Vite) ──────────────────────────
Write-Host "[2/2] Iniciando Tauri dev (inclui Vite na :5173)..." -ForegroundColor Yellow
Push-Location "$root\src-tauri"
cargo tauri dev
Pop-Location

# Ao fechar o Tauri, para o backend também
Write-Host "`nParando backend..." -ForegroundColor Yellow
Stop-Process -Id $backendJob.Id -ErrorAction SilentlyContinue
Write-Host "Encerrado." -ForegroundColor Green
