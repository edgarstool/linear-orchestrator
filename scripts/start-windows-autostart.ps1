# Login autostart: start linear-orchestrator in background if not already listening.
# Logs append to %USERPROFILE%\.local\share\linear-orchestrator\orchestrator.log
param([int]$Port = 8645)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path $PSScriptRoot -Parent
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $env:USERPROFILE ".local\share\linear-orchestrator"
$logFile = Join-Path $logDir "orchestrator.log"

if (-not (Test-Path $venvPy)) { exit 1 }

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) { exit 0 }

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
"$(Get-Date -Format o) autostart: launching linear-orchestrator on :$Port" | Add-Content $logFile

$envFile = Join-Path $env:USERPROFILE ".hermes\.env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
      Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
    }
  }
}
if (-not $env:HERMES_PATH) {
  $defaultHermes = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\hermes.exe"
  if (Test-Path $defaultHermes) { $env:HERMES_PATH = $defaultHermes }
}
$env:ORCHESTRATOR_PORT = "$Port"

Start-Process -FilePath $venvPy -ArgumentList '-m', 'linear_orchestrator' `
  -WorkingDirectory $root -WindowStyle Hidden `
  -RedirectStandardOutput $logFile -RedirectStandardError $logFile
