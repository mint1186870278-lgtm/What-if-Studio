$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$agents = @(
  "agent_composer.py",
  "agent_editor.py",
  "agent_director.py",
  "agent_collector.py"
)

foreach ($script in $agents) {
  $scriptPath = Join-Path $root $script
  Start-Process -FilePath "python" -ArgumentList "`"$scriptPath`"" -WorkingDirectory $root | Out-Null
  Write-Host "[ok] started $script"
}

Write-Host "all agents started"
