param(
    [switch]$Public
)

$ErrorActionPreference = "Continue"

Import-Module (Join-Path $PSScriptRoot "LinearOrchestratorCommon.psm1") -Force

Write-Host "=== linear-orchestrator (Windows) ==="
Write-Host "Repo:   $(Get-OrchestratorRepoRoot)"
Write-Host "RunDir: $(Get-OrchestratorRunDir)"
Write-Host "State:  $(Get-OrchestratorStateDir)"
Write-Host "Backups:$(Get-OrchestratorBackupDir)"
Write-Host "Hermes: $(try { Resolve-HermesPath } catch { 'NOT FOUND' })"

$proc = Get-OrchestratorProcess
if ($proc) {
    Write-Host "Process: RUNNING pid=$($proc.Id)"
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

if ($localOk) {
    try {
        $state = Invoke-RestMethod -Uri "http://*********:8645/state" -TimeoutSec 5
        Write-Host ("State db: {0} ({1} bytes, integrity={2})" -f $state.db_path, $state.db_bytes, $state.integrity)
        Write-Host ("State rows: sessions={0} deliveries={1} payloads={2} pending={3}" -f `
            $state.counts.sessions, $state.counts.deliveries, $state.counts.payloads, $state.counts.pending_deliveries)
        if ($state.last_recovery) {
            Write-Host ("Last recovery: interrupted={0} resumed={1}" -f `
                $state.last_recovery.interrupted.Count, $state.last_recovery.resumed.Count)
        }
    } catch {
        Write-Host "State: unavailable — $($_.Exception.Message)"
    }
}

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
