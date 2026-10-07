@echo off
REM Wrapper for Windows Task Scheduler - weekly data refresh + hypothesis re-check.
REM No non-ASCII characters here on purpose: cmd.exe misreads the project's Korean
REM path when it appears as literal text in the .bat source (codepage bug), so we
REM resolve the path at runtime via %~dp0 (this script's own directory) instead.
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%.."
REM The repo lives on a portable drive shared by several PCs, and a venv only
REM works on the PC that created it. Prefer a per-PC venv under LOCALAPPDATA,
REM fall back to the repo's .venv.
set PY=%LOCALAPPDATA%\venvs\realestate-analysis\Scripts\python.exe
if not exist "%PY%" set PY=%SCRIPT_DIR%..\.venv\Scripts\python.exe
echo ===== %date% %time% ===== >> logs\scheduled_refresh.log
"%PY%" -m scripts.scheduled_refresh --months 3 >> logs\scheduled_refresh.log 2>&1
echo. >> logs\scheduled_refresh.log
