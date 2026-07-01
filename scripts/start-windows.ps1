# Start linear-orchestrator on Windows (no WSL).
# Loads secrets from %USERPROFILE%\.hermes\.env
$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path "$Root\linear_orchestrator")) { $Root = Split-Path $PSScriptRoot -Parent }
Set-Location $Root

$envFile = Join-Path $env:USERPROFILE ".hermes\.env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
  }
}

if (-not $env:HERMES_PATH) {
  $candidate = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\hermes.exe"
  if (Test-Path $candidate) { $env:HERMES_PATH = $candidate }
}

$env:ORCHESTRATOR_HOST = if ($env:ORCHESTRATOR_HOST) { $env:ORCHESTRATOR_HOST } else { "0.0.0.0" }
$env:ORCHESTRATOR_PORT = if ($env:ORCHESTRATOR_PORT) { $env:ORCHESTRATOR_PORT } else { "8645" }

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Error "Missing venv. Run: py -3.13 -m venv .venv; .\.venv\Scripts\pip install -e ."
}

$pidFile = Join-Path $Root ".pid"
if (Test-Path $pidFile) {
  $old = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
    Write-Host "already running pid=$old"
    exit 0
  }
}

$proc = Start-Process -FilePath $py -ArgumentList "-m", "linear_orchestrator" -WorkingDirectory $Root -WindowStyle Hidden -PassThru
$proc.Id | Set-Content $pidFile
Start-Sleep -Seconds 2
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:$($env:ORCHESTRATOR_PORT)/healthz" -UseBasicParsing -TimeoutSec 5
  Write-Host "started pid=$($proc.Id) healthz=$($r.StatusCode)"
} catch {
  Write-Error "FAILED to start — check orchestrator.log or run in foreground"
}
