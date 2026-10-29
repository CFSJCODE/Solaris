# build.ps1 — Compila o SOLARIS para Windows (.msi / .exe instalável)
# Uso: .\scripts\build.ps1
# Requer: Python (com .venv), Node/npm, Rust/Cargo

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$TauriDir = Join-Path $Root "src-tauri"
$BinDir = Join-Path $TauriDir "binaries"

Write-Host "=== SOLARIS Build ===" -ForegroundColor Cyan

# 1. Compilar backend com PyInstaller
Write-Host "`n[1/4] Compilando backend (PyInstaller)..." -ForegroundColor Yellow
Set-Location $BackendDir

$Python = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Venv nao encontrado em $BackendDir\.venv. Rode: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
}

# Instalar PyInstaller se necessário
& $Python -m pip install pyinstaller --quiet

# Compilar
& $Python -m PyInstaller solaris_backend.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller falhou." }

# 2. Copiar binário para src-tauri/binaries com sufixo do target triple
Write-Host "`n[2/4] Copiando binario para src-tauri/binaries..." -ForegroundColor Yellow
$null = New-Item -ItemType Directory -Path $BinDir -Force

$BuiltExe = Join-Path $BackendDir "dist\solaris-backend.exe"
if (-not (Test-Path $BuiltExe)) {
    Write-Error "Binario nao encontrado: $BuiltExe"
}

# Tauri 2 usa o triple do host; para Windows x64 é x86_64-pc-windows-msvc
$TargetTriple = "x86_64-pc-windows-msvc"
$DestExe = Join-Path $BinDir "solaris-backend-$TargetTriple.exe"
Copy-Item $BuiltExe $DestExe -Force
Write-Host "  -> $DestExe" -ForegroundColor Green

# 3. Build do frontend
Write-Host "`n[3/4] Build do frontend..." -ForegroundColor Yellow
$FrontendDir = Join-Path $Root "frontend"
Set-Location $FrontendDir
& npm run build
if ($LASTEXITCODE -ne 0) { Write-Error "npm run build falhou." }

# 4. Build do Tauri (.msi + .exe)
Write-Host "`n[4/4] Build Tauri (pode demorar)..." -ForegroundColor Yellow
Set-Location $Root
& npm run tauri build
if ($LASTEXITCODE -ne 0) { Write-Error "tauri build falhou." }

Write-Host "`n=== Build concluido! ===" -ForegroundColor Green
Write-Host "Instalador em: src-tauri\target\release\bundle\" -ForegroundColor Cyan
