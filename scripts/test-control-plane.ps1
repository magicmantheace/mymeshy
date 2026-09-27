# Run all GPU-free AssetForge control-plane checks from the repo root.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Backend venv not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

$tests = @(
    "scripts\test_hardware_policy.py",
    "scripts\test_generation_presets.py",
    "scripts\test_benchmark_corpus.py",
    "scripts\test_benchmark_summary.py",
    "scripts\test_worker_framework.py",
    "scripts\test_worker_runtime_diagnostics.py",
    "scripts\test_hunyuan_fallback.py",
    "scripts\test_checkpoint_resume.py",
    "scripts\test_job_asset_link.py",
    "scripts\test_restart_recovery.py",
    "scripts\test_asset_validation.py",
    "scripts\test_texture_map_contract.py",
    "scripts\test_frontend_generation_contract.py",
    "scripts\test_mcp_contract.py"
)

foreach ($test in $tests) {
    Write-Host ">> $test" -ForegroundColor Cyan
    & $python (Join-Path $root $test)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $test" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "All GPU-free control-plane checks passed." -ForegroundColor Green
