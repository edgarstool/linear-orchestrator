# Shared paths and helpers for Windows-native linear-orchestrator.
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:RunDir = Join-Path "G:\AI_WORK_512\run" "linear-orchestrator"
$script:PidFile = Join-Path $script:RunDir "orchestrator.pid"
$script:LogFile = Join-Path $script:RunDir "orchestrator.out.log"
$script:ErrLogFile = Join-Path $script:RunDir "orchestrator.err.log"
$script:VenvPython = Join-Path $script:RepoRoot ".venv\Scripts\python.exe"
$script:HealthUrl = "http://127.0.0.1:8645/healthz"
$script:DopplerProject = "handcraft-mcp"
$script:DopplerConfig = "prd"

function Get-OrchestratorRepoRoot {
    return $script:RepoRoot
}

function Get-OrchestratorRunDir {
    return $script:RunDir
}

function Get-OrchestratorPidFile {
    return $script:PidFile
}

function Get-OrchestratorHealthUrl {
    return $script:HealthUrl
}

function Ensure-OrchestratorRunDir {
    New-Item -ItemType Directory -Force -Path $script:RunDir | Out-Null
}

function Resolve-HermesPath {
    if ($env:HERMES_PATH -and (Test-Path -LiteralPath $env:HERMES_PATH)) {
        return $env:HERMES_PATH
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\hermes.exe"),
        (Join-Path $env:USERPROFILE ".local\bin\hermes.exe")
    )
    foreach ($path in $candidates) {
        if (Test-Path -LiteralPath $path) {
            return $path
        }
    }

    $cmd = Get-Command hermes -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw "Hermes CLI not found. Install Hermes desktop app or set HERMES_PATH in C:\Users\$env:USERNAME\.hermes\.env"
}

function Test-OrchestratorHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $script:HealthUrl -TimeoutSec 3
        return [int]$response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-OrchestratorListenerProcess {
    $conns = Get-NetTCPConnection -LocalPort 8645 -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        $pidValue = [int]$conn.OwningProcess
        $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        if (-not $proc -or $proc.ProcessName -notin @("python", "pythonw")) {
            continue
        }
        try {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction Stop).CommandLine
            if ($cmd -match "linear_orchestrator") {
                return $proc
            }
        } catch {
            continue
        }
    }
    return $null
}

function Get-OrchestratorProcess {
    if (Test-Path -LiteralPath $script:PidFile) {
        $raw = (Get-Content -LiteralPath $script:PidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
        if ($raw) {
            $pidValue = 0
            if ([int]::TryParse($raw, [ref]$pidValue)) {
                $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
                if ($proc -and $proc.ProcessName -in @("python", "pythonw")) {
                    try {
                        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction Stop).CommandLine
                        if ($cmd -match "linear_orchestrator") {
                            return $proc
                        }
                    } catch {
                        # fall through to listener lookup
                    }
                }
            }
        }
    }

    return Get-OrchestratorListenerProcess
}

function Clear-StaleOrchestratorPidFile {
    if (-not (Test-Path -LiteralPath $script:PidFile)) {
        return
    }
    if (Get-OrchestratorProcess) {
        return
    }
    Remove-Item -LiteralPath $script:PidFile -Force -ErrorAction SilentlyContinue
}

function Save-OrchestratorPidFile {
    $proc = Get-OrchestratorListenerProcess
    if (-not $proc) {
        return $false
    }
    Set-Content -LiteralPath $script:PidFile -Value $proc.Id -Encoding ascii
    return $true
}

function Get-DopplerLaunchArgs {
    param(
        [string]$PythonExe,
        [string[]]$PythonArgs
    )

    $doppler = Get-Command doppler -ErrorAction SilentlyContinue
    if (-not $doppler) {
        return @{
            FilePath = $PythonExe
            ArgumentList = $PythonArgs
            UsesDoppler = $false
        }
    }

    return @{
        FilePath = $doppler.Source
        ArgumentList = @(
            "run",
            "--project", $script:DopplerProject,
            "--config", $script:DopplerConfig,
            "--",
            $PythonExe
        ) + $PythonArgs
        UsesDoppler = $true
    }
}

function Test-WslOrchestratorConflict {
    $wslrelay = Get-NetTCPConnection -LocalPort 8645 -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -eq "127.0.0.1" }
    if (-not $wslrelay) {
        return $null
    }

    $wslListening = $false
    try {
        $out = wsl -e bash -lc "ss -tln 2>/dev/null | grep -q ':8645 ' && echo yes || echo no" 2>$null
        $wslListening = ($out -match "yes")
    } catch {
        $wslListening = $false
    }

    if ($wslListening) {
        return "WSL linear-orchestrator is listening on :8645. cloudflared -> localhost:8645 hits wslrelay -> WSL (not Windows). Stop WSL orchestrator first."
    }
    return $null
}

function Stop-WslOrchestrator {
    $msg = Test-WslOrchestratorConflict
    if (-not $msg) {
        return $false
    }

    Write-Host "Stopping WSL linear-orchestrator (port 8645 conflict) ..."
    wsl -e bash -lc "pkill -f 'python -m linear_orchestrator' 2>/dev/null || true" | Out-Null
    Start-Sleep -Seconds 2

    $still = Test-WslOrchestratorConflict
    if ($still) {
        Write-Warning $still
        return $false
    }
    Write-Host "WSL orchestrator stopped."
    return $true
}

function Build-OrchestratorEnvironment {
    $hermesPath = Resolve-HermesPath
    $envMap = @{
        HERMES_PATH = $hermesPath
        ORCHESTRATOR_HOST = "0.0.0.0"
        ORCHESTRATOR_PORT = "8645"
    }

    # Doppler uses LINEAR_CLIENT_*; orchestrator expects LINEAR_OAUTH_*.
    if (-not $env:LINEAR_OAUTH_CLIENT_ID -and $env:LINEAR_CLIENT_ID) {
        $envMap["LINEAR_OAUTH_CLIENT_ID"] = $env:LINEAR_CLIENT_ID
    }
    if (-not $env:LINEAR_OAUTH_CLIENT_SECRET -and $env:LINEAR_CLIENT_SECRET) {
        $envMap["LINEAR_OAUTH_CLIENT_SECRET"] = $env:LINEAR_CLIENT_SECRET
    }

    return $envMap
}

Export-ModuleMember -Function @(
    "Get-OrchestratorRepoRoot",
    "Get-OrchestratorRunDir",
    "Get-OrchestratorPidFile",
    "Get-OrchestratorHealthUrl",
    "Ensure-OrchestratorRunDir",
    "Resolve-HermesPath",
    "Test-OrchestratorHealth",
    "Get-OrchestratorProcess",
    "Get-OrchestratorListenerProcess",
    "Clear-StaleOrchestratorPidFile",
    "Save-OrchestratorPidFile",
    "Get-DopplerLaunchArgs",
    "Build-OrchestratorEnvironment",
    "Test-WslOrchestratorConflict",
    "Stop-WslOrchestrator"
)
