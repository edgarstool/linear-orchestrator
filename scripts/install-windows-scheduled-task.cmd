@echo off
REM Install a Windows Scheduled Task that auto-launches the orchestrator on logon.
REM Windows-native (no WSL). Uses scripts\start-windows.ps1.

setlocal
set "TASK=linear-orchestrator-on-logon"
set "PS=powershell.exe"
set "PS_ARGS=-NoProfile -ExecutionPolicy Bypass -File \"V:\projects\linear-orchestrator\scripts\start-windows.ps1\""

echo Removing old task if any...
schtasks /Delete /TN "%TASK%" /F >nul 2>&1

echo Creating scheduled task "%TASK%" (trigger: at logon)...
schtasks /Create /SC ONLOGON /TN "%TASK%" /TR "%PS% %PS_ARGS%" /RL LIMITED /F
if errorlevel 1 (
  echo Failed to create task.
  pause
  exit /b 1
)

echo.
echo Done. Run now: schtasks /Run /TN "%TASK%"
endlocal
