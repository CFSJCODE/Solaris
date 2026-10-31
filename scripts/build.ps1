# Compila o engine de pipes e o instalador; não instala nem abre o app.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EngineDir = Join-Path $Root "python-engine"
$Python = Join-Path $EngineDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Ambiente Python ausente em python-engine/.venv." }
Push-Location $Root
try {
    & $Python scripts/prepare_vision.py
    if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar modelo de visão." }
    Push-Location $EngineDir
    try {
        & $Python -m PyInstaller engine.spec --noconfirm --workpath (Join-Path $Root "storage\build-engine-0.5.6")
        if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar o engine." }
    } finally { Pop-Location }
    $BinDir = Join-Path $Root "src-tauri\binaries"
    $null = New-Item -ItemType Directory -Path $BinDir -Force
    Copy-Item -LiteralPath (Join-Path $EngineDir "dist\solaris-engine.exe") -Destination (Join-Path $BinDir "solaris-engine-x86_64-pc-windows-msvc.exe") -Force
    $oldBuildJobs = $env:CARGO_BUILD_JOBS
    try {
        $env:CARGO_BUILD_JOBS = '1'
        & (Join-Path $Root "frontend\node_modules\.bin\tauri.cmd") build --bundles msi
        if ($LASTEXITCODE -ne 0) { throw "Falha no build Tauri." }
    } finally {
        if ($null -eq $oldBuildJobs) { Remove-Item Env:CARGO_BUILD_JOBS -ErrorAction SilentlyContinue }
        else { $env:CARGO_BUILD_JOBS = $oldBuildJobs }
    }
    Write-Host "Instalador gerado em src-tauri/target/release/bundle/msi."
} finally { Pop-Location }
