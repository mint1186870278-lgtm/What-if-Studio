$ErrorActionPreference = "Stop"

function Require-Command {
  param([string]$Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing command: $Name"
  }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== ANet Windows setup ==" -ForegroundColor Cyan

try {
  Require-Command -Name "python"
} catch {
  Write-Host "python not found in PATH. Install Python 3.10+ first." -ForegroundColor Red
  throw
}

if (-not (Get-Command anet -ErrorAction SilentlyContinue)) {
  Write-Host "anet CLI not found in PATH." -ForegroundColor Yellow
  Write-Host "Install anet CLI from official release, then re-run this script." -ForegroundColor Yellow
  Write-Host "Docs: https://docs.agentnetwork.org.cn/docs/zh/getting-started/install/" -ForegroundColor Yellow
} else {
  Write-Host "anet found, checking daemon status..." -ForegroundColor Green
  anet status | Out-Host
  anet whoami | Out-Host
}

Write-Host "Installing Python dependencies..." -ForegroundColor Green
python -m pip install --upgrade pip
python -m pip install -r "$root\requirements.txt"

Write-Host "Done. Next steps:" -ForegroundColor Cyan
Write-Host "1) Ensure daemon is running: anet status"
Write-Host "2) Start services: .\start_agents.ps1"
Write-Host "3) Register services: python .\register_agents.py"
