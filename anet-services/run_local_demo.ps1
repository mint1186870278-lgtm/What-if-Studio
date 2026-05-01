$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Get-Command anet -ErrorAction SilentlyContinue)) {
  throw "anet CLI not found. Run .\setup_windows.ps1 after installing anet."
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "python not found."
}

Write-Host "[1/4] checking daemon..." -ForegroundColor Cyan
anet status | Out-Host

Write-Host "[2/4] starting agent services..." -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File "$root\start_agents.ps1" | Out-Host

Write-Host "[3/4] registering services..." -ForegroundColor Cyan
python "$root\register_agents.py" | Out-Host

Write-Host "[4/4] smoke test composer call..." -ForegroundColor Cyan
python "$root\test_call.py" | Out-Host

Write-Host "ANet local demo bootstrap finished." -ForegroundColor Green
