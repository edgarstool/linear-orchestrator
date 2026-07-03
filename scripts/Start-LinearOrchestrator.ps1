param(
    [switch]$Wait,
    [int]$WaitSeconds = 15
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "LinearOrchestratorCommon.psm1") -Force

$repoRoot = Get-OrchestratorRepoRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
Ensure-OrchestratorRunDir

$wslConflict = Test-WslOrchestratorConflict
if ($wslConflict) {
    Write-Host "WARN: $wslConflict"
    Stop-WslOrchestrator | Out-Null
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing venv. Run scripts\Install-LinearOrchestratorWindows.ps1 first."
}

Clear-StaleOrchestratorPidFile

$existing = Get-OrchestratorProcess
if ($existing -and (Test-OrchestratorHealth) -and -not $Wait) {
    Write-Host "Already running pid=$($existing.Id)"
    exit 0
}

if ($existing) {
    Write-Host "Stopping stale pid=$($existing.Id)"
    Stop-Process -Id $existing.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Remove-Item -LiteralPath (Get-OrchestratorPidFile) -Force -ErrorAction SilentlyContinue
}

$hermesPath = Resolve-HermesPath
Write-Host "Hermes: $hermesPath"

$launch = Get-DopplerLaunchArgs -PythonExe $venvPython -PythonArgs @("-m", "linear_orchestrator")
$envBlock = Build-OrchestratorEnvironment
foreach ($key in $envBlock.Keys) {
    Set-Item -Path "Env:$key" -Value $envBlock[$key]
}

if ($launch.UsesDoppler) {
    Write-Host "Starting with Doppler (handcraft-mcp/prd) ..."
} else {
    Write-Host "Starting without Doppler (using C:\Users\$env:USERNAME\.hermes\.env) ..."
}

$proc = Start-Process `
    -FilePath $launch.FilePath `
    -ArgumentList $launch.ArgumentList `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-OrchestratorRunDir) "orchestrator.out.log") `
    -RedirectStandardError (Join-Path (Get-OrchestratorRunDir) "orchestrator.err.log") `
    -PassThru

Write-Host "Launcher pid=$($proc.Id) (waiting for python listener on :8645)"

if ($Wait) {
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-OrchestratorHealth) {
            if (Save-OrchestratorPidFile) {
                $listener = Get-OrchestratorProcess
                Write-Host "Health OK: $(Get-OrchestratorHealthUrl) (orchestrator pid=$($listener.Id))"
            } else {
                Write-Host "Health OK: $(Get-OrchestratorHealthUrl)"
            }
            exit 0
        }
        Start-Sleep -Seconds 1
    }
    throw "Timed out waiting for health at $(Get-OrchestratorHealthUrl). See $(Join-Path (Get-OrchestratorRunDir) 'orchestrator.err.log')"
}

Start-Sleep -Seconds 2
if (Save-OrchestratorPidFile) {
    $listener = Get-OrchestratorProcess
    Write-Host "Started orchestrator pid=$($listener.Id)"
} else {
    Write-Host "Started launcher pid=$($proc.Id) (orchestrator pid not detected yet)"
}
