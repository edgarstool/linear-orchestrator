param(
    [switch]$Public
)

$ErrorActionPreference = "Continue"

Import-Module (Join-Path $PSScriptRoot "LinearOrchestratorCommon.psm1") -Force

Write-Host "=== linear-orchestrator (Windows) ==="
Write-Host "Repo:   $(Get-OrchestratorRepoRoot)"
Write-Host "RunDir: $(Get-OrchestratorRunDir)"
Write-Host "Hermes: $(try { Resolve-HermesPath } catch { 'NOT FOUND' })"

Clear-StaleOrchestratorPidFile

$proc = Get-OrchestratorProcess
$localOkEarly = Test-OrchestratorHealth
if ($proc -and $localOkEarly) {
    Write-Host "Process: RUNNING pid=$($proc.Id)"
} elseif ($proc) {
    Write-Host "Process: UNHEALTHY pid=$($proc.Id) (orchestrator process up but healthz failed)"
} else {
    Write-Host "Process: STOPPED"
}

$wslConflict = Test-WslOrchestratorConflict
if ($wslConflict) {
    Write-Host "WSL conflict: $wslConflict"
    Write-Host "Fix: powershell -ExecutionPolicy Bypass -File .\scripts\Start-LinearOrchestrator.ps1 -Wait"
}

$localOk = Test-OrchestratorHealth
Write-Host "Local health ($(Get-OrchestratorHealthUrl)): $(if ($localOk) { 'OK' } else { 'FAIL' })"

if ($Public) {
    try {
        $pub = Invoke-WebRequest -UseBasicParsing -Uri "https://webhooks.edgars.tools/healthz" -TimeoutSec 10
        Write-Host "Public health (webhooks.edgars.tools): $($pub.StatusCode) $($pub.Content)"
    } catch {
        Write-Host "Public health (webhooks.edgars.tools): FAIL — $($_.Exception.Message)"
        Write-Host "Fix tunnel: Cloudflare Dashboard → edgar-local-01-tunnel → webhooks.edgars.tools → http://localhost:8645"
    }
}

if (-not $localOk -and (Test-Path -LiteralPath (Join-Path (Get-OrchestratorRunDir) "orchestrator.err.log"))) {
    Write-Host ""
    Write-Host "--- last 10 lines of err log ---"
    Get-Content -LiteralPath (Join-Path (Get-OrchestratorRunDir) "orchestrator.err.log") -Tail 10
}

if (-not $localOk) { exit 1 }
