param(
    [switch]$Wait,
    [int]$WaitSeconds = 15
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "LinearOrchestratorCommon.psm1") -Force

$repoRoot = Get-OrchestratorRepoRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
Ensure-OrchestratorRunDir
Ensure-OrchestratorStateDir

$wslConflict = Test-WslOrchestratorConflict
if ($wslConflict) {
    Write-Host "WARN: $wslConflict"
    Stop-WslOrchestrator | Out-Null
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing venv. Run scripts\Install-LinearOrchestratorWindows.ps1 first."
}

$existing = Get-OrchestratorProcess
if ($existing -and -not $Wait) {
    Write-Host "Already running pid=$($existing.Id)"
    exit 0
}

if ($existing) {
    Write-Host "Stopping stale pid=$($existing.Id)"
    Stop-Process -Id $existing.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
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

Set-Content -LiteralPath (Get-OrchestratorPidFile) -Value $proc.Id -Encoding ascii
Write-Host "Started pid=$($proc.Id)"

if ($Wait) {
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-OrchestratorHealth) {
            Write-Host "Health OK: $(Get-OrchestratorHealthUrl)"
            exit 0
        }
        Start-Sleep -Seconds 1
    }
    throw "Timed out waiting for health at $(Get-OrchestratorHealthUrl). See $(Join-Path (Get-OrchestratorRunDir) 'orchestrator.err.log')"
}
