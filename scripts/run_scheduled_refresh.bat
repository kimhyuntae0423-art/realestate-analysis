@echo off
REM Wrapper for Windows Task Scheduler - weekly data refresh + hypothesis re-check.
REM No non-ASCII characters here on purpose: cmd.exe misreads the project's Korean
REM path when it appears as literal text in the .bat source (codepage bug), so we
REM resolve the path at runtime via %~dp0 (this script's own directory) instead.
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%.."
echo ===== %date% %time% ===== >> logs\scheduled_refresh.log
"%SCRIPT_DIR%..\.venv\Scripts\python.exe" -m scripts.scheduled_refresh --months 3 >> logs\scheduled_refresh.log 2>&1
echo. >> logs\scheduled_refresh.log
