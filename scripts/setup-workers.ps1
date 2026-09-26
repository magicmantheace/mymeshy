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
Write-Host "Add these lines to .env:" -ForegroundColor Yellow
Write-Host "MYMESHY_ISOLATED_WORKERS=true"
Write-Host "MYMESHY_TRIPOSR_WORKER_PYTHON=.workers\triposr\Scripts\python.exe"
Write-Host ""
Write-Host "Restart the backend and inspect /api/system." -ForegroundColor Cyan
Write-Host "The TripoSR adapter probe is executed inside this worker environment."
Write-Host "For a GPU-free process-isolation check run:"
Write-Host ".venv\Scripts\python.exe scripts\test_worker_framework.py"
