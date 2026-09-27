param(
    [string]$Suite = "benchmarks\suite.json"
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Backend venv not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

$suitePath = if ([System.IO.Path]::IsPathRooted($Suite)) { $Suite } else { Join-Path $root $Suite }
if (-not (Test-Path $suitePath)) {
    Write-Host "Benchmark suite not found: $suitePath" -ForegroundColor Red
    exit 1
}
$config = Get-Content $suitePath -Raw | ConvertFrom-Json
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $root "data\benchmarks\suite-$stamp"
New-Item -ItemType Directory -Force $runDir | Out-Null

Write-Host ">> Capturing hardware/system state" -ForegroundColor Cyan
& (Join-Path $root "scripts\validate-hardware.ps1") -Output (Join-Path $runDir "hardware.json")
if (-not $?) {
    Write-Host "Hardware validation command reported a problem; continuing so available evidence is preserved." -ForegroundColor Yellow
}

Write-Host ">> Capturing isolated worker runtime versions" -ForegroundColor Cyan
& $python (Join-Path $root "scripts\worker-runtime-info.py") --output (Join-Path $runDir "worker-runtimes.json")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Worker runtime provenance failed; continuing so benchmark failures can still be recorded." -ForegroundColor Yellow
}

$failures = 0
foreach ($adapter in $config.adapters) {
    foreach ($caseId in $config.cases) {
        $out = Join-Path $runDir "real-model-$adapter-$caseId.json"
        Write-Host ""
        Write-Host ">> $adapter / $caseId" -ForegroundColor Cyan
        & $python (Join-Path $root "scripts\real_model_test.py") `
            $adapter $caseId `
            --target-polycount ([int]$config.settings.target_polycount) `
            --texture-size ([int]$config.settings.texture_size) `
            --seed ([int]$config.settings.seed) `
            --output $out
        if ($LASTEXITCODE -ne 0) {
            $failures++
            Write-Host "   run failed; report retained at $out" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host ">> Aggregating reports" -ForegroundColor Cyan
& $python (Join-Path $root "scripts\benchmark_summary.py") $runDir
$summaryExit = $LASTEXITCODE

Write-Host ""
Write-Host "Benchmark suite directory: $runDir"
if ($summaryExit -ne 0) {
    Write-Host "Summary generation failed." -ForegroundColor Red
    exit $summaryExit
}
if ($failures -gt 0) {
    Write-Host "$failures benchmark run(s) failed. Inspect benchmark-summary.json and the individual reports." -ForegroundColor Yellow
    exit 1
}
Write-Host "All benchmark runs completed successfully." -ForegroundColor Green
