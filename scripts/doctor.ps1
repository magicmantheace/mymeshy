# AssetForge/MyMeshy Windows readiness doctor. Does not load generation models.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$failures = 0
$warnings = 0

function Check([string]$Name, [bool]$Ok, [string]$Detail, [string]$Repair = "") {
    if ($Ok) { Write-Host "[OK]   $Name - $Detail" -ForegroundColor Green }
    else {
        $script:failures++
        Write-Host "[FAIL] $Name - $Detail" -ForegroundColor Red
        if ($Repair) { Write-Host "       Repair: $Repair" -ForegroundColor Yellow }
    }
}
function Warn([string]$Name, [string]$Detail) {
    $script:warnings++
    Write-Host "[WARN] $Name - $Detail" -ForegroundColor Yellow
}

Write-Host "AssetForge readiness doctor" -ForegroundColor Cyan
Write-Host "Repo: $root"
Write-Host ""

$git = Get-Command git -ErrorAction SilentlyContinue
Check "Git" ($null -ne $git) ($(if ($git) { (& git --version) } else { "not found" })) "Install Git for Windows."

$node = Get-Command node -ErrorAction SilentlyContinue
$nodeVersion = if ($node) { (& node --version) } else { "" }
$nodeMajor = if ($nodeVersion -match '^v(\d+)') { [int]$Matches[1] } else { 0 }
Check "Node.js" ($nodeMajor -ge 18) ($(if ($nodeVersion) { $nodeVersion } else { "not found" })) "Install Node.js 18+ LTS."

$python = Join-Path $root ".venv\Scripts\python.exe"
Check "Backend venv" (Test-Path $python) $python ".\scripts\setup.ps1"

$nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidia) {
    $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>$null | Select-Object -First 1)
    Check "NVIDIA driver" ($LASTEXITCODE -eq 0 -and [bool]$gpu) $gpu "Install/update the NVIDIA driver."
} else {
    Check "NVIDIA driver" $false "nvidia-smi not found" "Install an NVIDIA driver before real-model generation."
}

$envFile = Join-Path $root ".env"
if (Test-Path $envFile) { Check ".env" $true "present" }
else { Warn ".env" "not present; isolated worker setup should create it" }

$workers = @(
    @("TripoSR", ".workers\triposr\Scripts\python.exe", "external\TripoSR"),
    @("Hunyuan", ".workers\hunyuan\Scripts\python.exe", "external\Hunyuan3D-2")
)
foreach ($worker in $workers) {
    $name, $pyRel, $sourceRel = $worker
    $py = Join-Path $root $pyRel
    $source = Join-Path $root $sourceRel
    Check "$name worker Python" (Test-Path $py) $py ".\scripts\install-models.ps1"
    Check "$name source" (Test-Path (Join-Path $source ".git")) $source ".\scripts\install-models.ps1"
    if (Test-Path $py) {
        $version = (& $py --version 2>&1)
        Check "$name Python runtime" ($LASTEXITCODE -eq 0) $version ".\scripts\install-models.ps1"
    }
}

if (Test-Path $python) {
    $runtimeFile = Join-Path ([System.IO.Path]::GetTempPath()) ("assetforge-worker-runtime-" + [guid]::NewGuid().ToString("N") + ".json")
    try {
        & $python (Join-Path $root "scripts\worker-runtime-info.py") --output $runtimeFile | Out-Null
        if ($LASTEXITCODE -eq 0 -and (Test-Path $runtimeFile)) {
            $runtimeReport = Get-Content $runtimeFile -Raw | ConvertFrom-Json
            foreach ($name in @("triposr", "hunyuan_shape", "hunyuan_paint")) {
                $r = $runtimeReport.workers.$name
                if ($null -ne $r) {
                    $runtimeOk = [bool]$r.python_version -and [bool]$r.torch_version -and [bool]$r.cuda_available
                    $detail = "Python $($r.python_version); Torch $($r.torch_version); CUDA runtime $($r.cuda_runtime); CUDA available $($r.cuda_available)"
                    if ($r.error) { $detail += "; $($r.error)" }
                    Check "$name worker runtime" $runtimeOk $detail ".\scripts\install-models.ps1"

                    $actual = [string]$r.source_revision
                    $expected = [string]$r.expected_source_revision
                    $lockOk = [bool]$r.source_matches_lock
                    $lockDetail = "actual $(if ($actual) { $actual } else { 'unknown' }); expected $(if ($expected) { $expected } else { 'unknown' })"
                    Check "$name source lock" $lockOk $lockDetail ".\scripts\install-models.ps1"
                }
            }
        } else {
            Warn "Worker runtime provenance" "could not collect worker Python/Torch/CUDA/source-lock state"
        }
    } finally {
        Remove-Item $runtimeFile -Force -ErrorAction SilentlyContinue
    }
}

$blender = Get-Command blender -ErrorAction SilentlyContinue
if ($blender) {
    $bv = (& blender --version 2>$null | Select-Object -First 1)
    Check "Blender" $true $bv
} else { Warn "Blender" "not on PATH; FBX export may still work if auto-detected or MYMESHY_BLENDER_PATH is set" }

try {
    $system = Invoke-RestMethod -Uri "http://127.0.0.1:8420/api/system" -TimeoutSec 4
    Check "Backend API" $true "responding on 127.0.0.1:8420"
    Write-Host "       Profile: $($system.memory_policy.hardware_profile); GPU: $($system.gpu.name)"
    Write-Host "       Python: $($system.runtime.python); Torch: $($system.runtime.torch); CUDA runtime: $($system.runtime.cuda_runtime)"
    Write-Host "       Source revision: $($system.runtime.source_revision)"
    foreach ($name in @("triposr", "hunyuan_shape", "hunyuan_paint")) {
        $w = $system.workers.$name
        if ($null -ne $w) {
            $state = if ($w.configured) { "configured" } else { "not configured" }
            $runtime = $w.runtime
            $lock = if ($runtime.source_matches_lock) { "lock ok" } else { "lock mismatch" }
            Write-Host "       Worker ${name}: $state; Python $($runtime.python_version); Torch $($runtime.torch_version); CUDA $($runtime.cuda_runtime); $lock"
        }
    }
} catch { Warn "Backend API" "not running; start .\scripts\dev.ps1 to include runtime adapter probes" }

Write-Host ""
if ($failures -gt 0) {
    Write-Host "Doctor found $failures blocking issue(s) and $warnings warning(s)." -ForegroundColor Red
    exit 1
}
Write-Host "Doctor found no static blockers ($warnings warning(s))." -ForegroundColor Green
Write-Host "This is readiness validation only; it does not prove real-model generation or benchmark performance."
