param(
    [switch]$CompileHunyuanPaint
)

# Preferred Windows real-model install entry point.
# Run after scripts\setup.ps1. The backend venv keeps the text-to-image runtime
# (SDXL-Turbo), while image-to-3D models use dedicated short-lived worker venvs.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = "$root\.venv\Scripts\python.exe"
$workerSetup = "$root\scripts\setup-workers.ps1"
$env:UV_CACHE_DIR = "$root\data\uv-cache"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv is required. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $py)) {
    Write-Host "Backend venv not found: $py" -ForegroundColor Red
    Write-Host "Run .\scripts\setup.ps1 first."
    exit 1
}
if (-not (Test-Path $workerSetup)) {
    throw "Worker setup script not found: $workerSetup"
}

Write-Host ">> Installing backend CUDA/ML runtime for SDXL-Turbo..." -ForegroundColor Cyan
uv pip install --python $py torch torchvision --index-url https://download.pytorch.org/whl/cu124
if ($LASTEXITCODE -ne 0) { throw "Failed to install backend CUDA PyTorch." }
uv pip install --python $py -r "$root\backend\requirements-ml.txt"
if ($LASTEXITCODE -ne 0) { throw "Failed to install backend ML requirements." }

Write-Host ""
Write-Host ">> Installing isolated image-to-3D worker environments..." -ForegroundColor Cyan
if ($CompileHunyuanPaint) {
    & $workerSetup -CompileHunyuanPaint
} else {
    & $workerSetup
}
if (-not $?) { throw "Isolated worker setup failed." }

Write-Host ""
Write-Host "Real-model software setup complete." -ForegroundColor Green
Write-Host "The backend venv owns text-to-image; TripoSR and Hunyuan run in isolated worker venvs." -ForegroundColor Green
Write-Host "Worker paths and MYMESHY_ISOLATED_WORKERS=true were written to .env." -ForegroundColor Green
if (-not $CompileHunyuanPaint) {
    Write-Host "Hunyuan Paint CUDA extensions were not compiled; Shape remains usable and can fall back to reference projection." -ForegroundColor Yellow
    Write-Host "After installing the CUDA toolkit + Visual Studio C++ build tools, rerun:" -ForegroundColor Yellow
    Write-Host "  .\scripts\install-models.ps1 -CompileHunyuanPaint"
}

Write-Host ""
Write-Host "Before real generation/benchmarking:" -ForegroundColor Cyan
Write-Host "  .\scripts\doctor.ps1"
Write-Host "  .\scripts\test-control-plane.ps1"
Write-Host "Then restart/start the app and inspect /api/system."
Write-Host "Model weights download from Hugging Face on first use into the configured cache." -ForegroundColor DarkGray
