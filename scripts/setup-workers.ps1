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
$sourceLocksPath = "$root\backend\model-sources.json"
$env:UV_CACHE_DIR = "$root\data\uv-cache"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv is required. Run scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git is required to install/update model sources." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $sourceLocksPath)) {
    throw "Model source lock file not found: $sourceLocksPath"
}
$sourceLocks = Get-Content $sourceLocksPath -Raw | ConvertFrom-Json
if ([int]$sourceLocks.version -ne 1) {
    throw "Unsupported model source lock version: $($sourceLocks.version)"
}

function Set-EnvValue([string]$File, [string]$Key, [string]$Value) {
    $line = "$Key=$Value"
    $lines = if (Test-Path $File) { @(Get-Content $File) } else { @() }
    $pattern = "^\s*" + [regex]::Escape($Key) + "\s*="
    $found = $false
    $updated = foreach ($existing in $lines) {
        if ($existing -match $pattern) {
            if (-not $found) { $line }
            $found = $true
        } else { $existing }
    }
    if (-not $found) { $updated += $line }
    [System.IO.File]::WriteAllLines($File, [string[]]$updated, [System.Text.UTF8Encoding]::new($false))
}

function Sync-LockedRepo(
    [string]$Url,
    [string]$Path,
    [string]$Name,
    [string]$Revision
) {
    if ($Revision -notmatch '^[0-9a-fA-F]{40}$') {
        throw "$Name source lock is not a full 40-character commit SHA: $Revision"
    }

    if (-not (Test-Path $Path)) {
        Write-Host ">> Initializing $Name source checkout..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Force $Path | Out-Null
        git -C $Path init | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to initialize $Name checkout." }
        git -C $Path remote add origin $Url
        if ($LASTEXITCODE -ne 0) { throw "Failed to configure $Name origin." }
    } elseif (-not (Test-Path "$Path\.git")) {
        throw "$Name source path exists but is not a Git checkout: $Path"
    } else {
        git -C $Path remote get-url origin *> $null
        if ($LASTEXITCODE -eq 0) {
            git -C $Path remote set-url origin $Url
        } else {
            git -C $Path remote add origin $Url
        }
        if ($LASTEXITCODE -ne 0) { throw "Failed to configure $Name origin." }
    }

    Write-Host ">> Syncing $Name to locked revision $Revision..." -ForegroundColor Cyan
    git -C $Path fetch --depth 1 origin $Revision
    if ($LASTEXITCODE -ne 0) { throw "Failed to fetch locked $Name revision $Revision." }
    git -C $Path checkout --detach --force FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw "Failed to checkout locked $Name revision $Revision." }

    $actual = (git -C $Path rev-parse HEAD).Trim()
    if ($actual -ne $Revision) {
        throw "$Name source revision mismatch. Expected $Revision, got $actual."
    }
    Write-Host "$Name revision: $actual (locked)" -ForegroundColor DarkGray
    return $actual
}

$triposrSource = $sourceLocks.sources.triposr
$hunyuanSource = $sourceLocks.sources.hunyuan3d_2
if (-not $triposrSource -or -not $hunyuanSource) {
    throw "model-sources.json must define triposr and hunyuan3d_2 sources."
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
$triposrRevision = Sync-LockedRepo ([string]$triposrSource.url) "$root\external\TripoSR" "TripoSR" ([string]$triposrSource.revision)

Write-Host ">> Creating Hunyuan worker venv..." -ForegroundColor Cyan
if (-not (Test-Path $hunyuanPy)) {
    uv venv $hunyuanRoot --python 3.11
}
uv pip install --python $hunyuanPy torch torchvision --index-url https://download.pytorch.org/whl/cu124
uv pip install --python $hunyuanPy -r "$root\backend\requirements.txt"
uv pip install --python $hunyuanPy -r "$root\backend\requirements-ml.txt"
uv pip install --python $hunyuanPy ninja pybind11 opencv-python pymeshlab pygltflib imageio moderngl rembg onnxruntime xatlas
$hunyuanRevision = Sync-LockedRepo ([string]$hunyuanSource.url) "$root\external\Hunyuan3D-2" "Hunyuan3D-2" ([string]$hunyuanSource.revision)

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
$envFile = "$root\.env"
Set-EnvValue $envFile "MYMESHY_ISOLATED_WORKERS" "true"
Set-EnvValue $envFile "MYMESHY_TRIPOSR_WORKER_PYTHON" ".workers\triposr\Scripts\python.exe"
Set-EnvValue $envFile "MYMESHY_HUNYUAN_SHAPE_WORKER_PYTHON" ".workers\hunyuan\Scripts\python.exe"
Set-EnvValue $envFile "MYMESHY_HUNYUAN_PAINT_WORKER_PYTHON" ".workers\hunyuan\Scripts\python.exe"

Write-Host "Isolated worker environments ready." -ForegroundColor Green
Write-Host "Worker paths were written to .env without replacing other settings." -ForegroundColor Green
Write-Host "Sources were installed from backend\model-sources.json locks." -ForegroundColor Green
Write-Host ""
Write-Host "Restart the backend and inspect /api/system." -ForegroundColor Cyan
Write-Host "For a GPU-free process-isolation check run:"
Write-Host ".venv\Scripts\python.exe scripts\test_worker_framework.py"

Write-Host ""
Write-Host "Installed model source revisions:" -ForegroundColor Cyan
Write-Host "TripoSR: $triposrRevision"
Write-Host "Hunyuan3D-2: $hunyuanRevision"
