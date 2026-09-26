param(
    [string]$ApiUrl = "http://127.0.0.1:8420",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $Output) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $Output = Join-Path $root "data\benchmarks\hardware-$stamp.json"
}
New-Item -ItemType Directory -Force (Split-Path -Parent $Output) | Out-Null

$report = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    computer = $env:COMPUTERNAME
    gpu = $null
    system = $null
    errors = @()
}

try {
    $gpuRaw = & nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv,noheader,nounits
    if ($LASTEXITCODE -eq 0 -and $gpuRaw) {
        $parts = $gpuRaw.Split(",") | ForEach-Object { $_.Trim() }
        $report.gpu = [ordered]@{
            name = $parts[0]
            memory_total_mb = [int]$parts[1]
            memory_used_mb = [int]$parts[2]
            driver_version = $parts[3]
        }
    }
} catch {
    $report.errors += "nvidia-smi: $($_.Exception.Message)"
}

try {
    $report.system = Invoke-RestMethod -Uri "$ApiUrl/api/system" -TimeoutSec 10
} catch {
    $report.errors += "api/system: $($_.Exception.Message)"
}

$report | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $Output
Write-Host "Hardware validation report: $Output"
if ($report.system) {
    Write-Host "Profile: $($report.system.memory_policy.hardware_profile)"
    Write-Host "Image-to-3D: $($report.system.active.image_to_3d)"
}
