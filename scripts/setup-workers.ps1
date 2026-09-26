# AssetForge isolated worker setup for Windows.
# Creates a dedicated TripoSR Python environment so model dependencies and the
# CUDA context are isolated from the FastAPI backend process.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$workerRoot = "$root\.workers\triposr"
$workerPy = "$workerRoot\Scripts\python.exe"
$env:UV_CACHE_DIR = "$root\data\uv-cache"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv is required. Run scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host ">> Creating TripoSR worker venv..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force "$root\.workers" | Out-Null
if (-not (Test-Path $workerPy)) {
    uv venv $workerRoot --python 3.11
}

Write-Host ">> Installing CUDA PyTorch into the worker..." -ForegroundColor Cyan
uv pip install --python $workerPy torch torchvision --index-url https://download.pytorch.org/whl/cu124

Write-Host ">> Installing shared runtime dependencies..." -ForegroundColor Cyan
uv pip install --python $workerPy -r "$root\backend\requirements.txt"
uv pip install --python $workerPy -r "$root\backend\requirements-ml.txt"
uv pip install --python $workerPy omegaconf einops imageio moderngl huggingface-hub

New-Item -ItemType Directory -Force "$root\external" | Out-Null
if (-not (Test-Path "$root\external\TripoSR")) {
    Write-Host ">> Cloning TripoSR source..." -ForegroundColor Cyan
    git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR "$root\external\TripoSR"
}

Write-Host ""
Write-Host "TripoSR isolated worker ready." -ForegroundColor Green
Write-Host "Add this to .env (or leave it there if already configured):" -ForegroundColor Yellow
Write-Host "MYMESHY_ISOLATED_WORKERS=true"
Write-Host "MYMESHY_TRIPOSR_WORKER_PYTHON=.workers\triposr\Scripts\python.exe"
Write-Host ""
Write-Host "Probe command:" -ForegroundColor Cyan
Write-Host '& ".workers\triposr\Scripts\python.exe" -m app.workers.triposr_worker --probe'
Write-Host "(The backend supplies PYTHONPATH automatically; use /api/system to verify adapter availability.)"
