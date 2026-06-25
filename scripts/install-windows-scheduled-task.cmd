@echo off
REM Install a Windows Scheduled Task that auto-launches the orchestrator
REM whenever Edgar logs in. Falls back from systemd (works even without
REM WSL systemd or sudo password).
REM
REM Triggers WSL Ubuntu-24.04-G, runs start.sh, exits.

setlocal
set "TASK=linear-orchestrator-on-logon"
set "WSL=wsl.exe"
set "WSL_ARGS=-d Ubuntu-24.04-G -e bash -lc \"cd /mnt/g/AI_WORK_512/repos/linear-orchestrator && bash scripts/start.sh\""

echo Removing old task if any...
schtasks /Delete /TN "%TASK%" /F >nul 2>&1

echo Creating scheduled task "%TASK%" (trigger: at logon, runs as current user)...
schtasks /Create /SC ONLOGON /TN "%TASK%" /TR "%WSL% %WSL_ARGS%" /RL LIMITED /F
if errorlevel 1 (
  echo Failed to create task.
  pause
  exit /b 1
)

echo.
echo Done. Task will fire on next Windows logon.
echo You can also run it now with:
echo   schtasks /Run /TN "%TASK%"
echo Or remove with:
echo   schtasks /Delete /TN "%TASK%" /F
endlocal
