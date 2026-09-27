# MyMeshy one-time setup. Run from the repo root:  .\scripts\setup.ps1
# Installs uv (if missing), creates a Python 3.11 venv, installs base backend
# deps + MCP deps, and installs frontend npm packages.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# --- uv (manages its own Python toolchains; system Python version is irrelevant)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host ">> Installing uv..." -ForegroundColor Cyan
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# --- frontend prerequisite
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js 18+ with npm is required for the frontend." -ForegroundColor Red
    Write-Host "Install the current Node.js LTS release, reopen PowerShell, then rerun this script."
    exit 1
}
try {
    $nodeMajor = [int]((& node --version).Trim().TrimStart("v").Split(".")[0])
} catch {
    Write-Host "Unable to determine the installed Node.js version." -ForegroundColor Red
    exit 1
}
if ($nodeMajor -lt 18) {
    Write-Host "Node.js 18+ is required; found $(& node --version)." -ForegroundColor Red
    exit 1
}

# --- backend venv (Python 3.11 — the ML ecosystem's sweet spot)
Write-Host ">> Creating backend venv (Python 3.11)..." -ForegroundColor Cyan
uv venv --python 3.11 "$root\.venv"
uv pip install --python "$root\.venv\Scripts\python.exe" -r "$root\backend\requirements.txt"
uv pip install --python "$root\.venv\Scripts\python.exe" -r "$root\mcp\requirements.txt"

# --- frontend
Write-Host ">> Installing frontend packages..." -ForegroundColor Cyan
Push-Location "$root\frontend"
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Base setup complete. Start the app in mock mode with: .\scripts\dev.ps1" -ForegroundColor Green
Write-Host "For the preferred Windows real-model setup, run:" -ForegroundColor Yellow
Write-Host "  .\scripts\install-models.ps1"
Write-Host "Fresh-machine guide: docs\WINDOWS_SETUP.md" -ForegroundColor DarkGray
