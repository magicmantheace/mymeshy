param(
    [switch]$CompileHunyuanPaint
)

# AssetForge isolated worker setup for Windows.
# Creates dedicated model environments so heavy CUDA contexts and dependency
# stacks stay outside the FastAPI backend process.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$triposrRoot = "$root\.workers\triposr"
$triposrPy = "$triposrRoot\Scripts\python.exe"
$hunyuanRoot = "$root\.workers\hunyuan"
$hunyuanPy = "$hunyuanRoot\Scripts\python.exe"
$env:UV_CACHE_DIR = "$root\data\uv-cache"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv is required. Run scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force "$root\.workers" | Out-Null
New-Item -ItemType Directory -Force "$root\external" | Out-Null

Write-Host ">> Creating TripoSR worker venv..." -ForegroundColor Cyan
if (-not (Test-Path $triposrPy)) {
    uv venv $triposrRoot --python 3.11
}
uv pip install --python $triposrPy torch torchvision --index-url https://download.pytorch.org/whl/cu124
uv pip install --python $triposrPy -r "$root\backend\requirements.txt"
uv pip install --python $triposrPy -r "$root\backend\requirements-ml.txt"
uv pip install --python $triposrPy omegaconf einops imageio moderngl huggingface-hub
if (-not (Test-Path "$root\external\TripoSR")) {
    Write-Host ">> Cloning TripoSR source..." -ForegroundColor Cyan
    git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR "$root\external\TripoSR"
}

Write-Host ">> Creating Hunyuan worker venv..." -ForegroundColor Cyan
if (-not (Test-Path $hunyuanPy)) {
    uv venv $hunyuanRoot --python 3.11
}
uv pip install --python $hunyuanPy torch torchvision --index-url https://download.pytorch.org/whl/cu124
uv pip install --python $hunyuanPy -r "$root\backend\requirements.txt"
uv pip install --python $hunyuanPy -r "$root\backend\requirements-ml.txt"
uv pip install --python $hunyuanPy ninja pybind11 opencv-python pymeshlab pygltflib imageio moderngl rembg onnxruntime xatlas
if (-not (Test-Path "$root\external\Hunyuan3D-2")) {
    Write-Host ">> Cloning Hunyuan3D-2 source..." -ForegroundColor Cyan
    git clone --depth 1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2 "$root\external\Hunyuan3D-2"
}

if ($CompileHunyuanPaint) {
    Write-Host ">> Compiling Hunyuan Paint CUDA extensions..." -ForegroundColor Cyan
    $rasterizer = "$root\external\Hunyuan3D-2\hy3dgen\texgen\custom_rasterizer"
    $renderer = "$root\external\Hunyuan3D-2\hy3dgen\texgen\differentiable_renderer"
    if (-not (Test-Path $rasterizer) -or -not (Test-Path $renderer)) {
        throw "Hunyuan Paint extension source folders were not found."
    }
    Push-Location $rasterizer
    try { & $hunyuanPy setup.py install } finally { Pop-Location }
    Push-Location $renderer
    try { & $hunyuanPy setup.py install } finally { Pop-Location }
} else {
    Write-Host "Hunyuan Shape is ready. Paint still needs its CUDA extensions." -ForegroundColor Yellow
    Write-Host "Re-run with -CompileHunyuanPaint after installing the CUDA toolkit + Visual Studio C++ build tools."
}

Write-Host ""
Write-Host "Isolated worker environments ready." -ForegroundColor Green
Write-Host "Add these lines to .env:" -ForegroundColor Yellow
Write-Host "MYMESHY_ISOLATED_WORKERS=true"
Write-Host "MYMESHY_TRIPOSR_WORKER_PYTHON=.workers\triposr\Scripts\python.exe"
Write-Host "MYMESHY_HUNYUAN_SHAPE_WORKER_PYTHON=.workers\hunyuan\Scripts\python.exe"
Write-Host "MYMESHY_HUNYUAN_PAINT_WORKER_PYTHON=.workers\hunyuan\Scripts\python.exe"
Write-Host ""
Write-Host "Restart the backend and inspect /api/system." -ForegroundColor Cyan
Write-Host "For a GPU-free process-isolation check run:"
Write-Host ".venv\Scripts\python.exe scripts\test_worker_framework.py"
