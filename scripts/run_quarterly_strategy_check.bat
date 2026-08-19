@echo off
REM Wrapper for Windows Task Scheduler - quarterly strategy backtest re-check.
REM No non-ASCII characters here on purpose: cmd.exe misreads the project's Korean
REM path when it appears as literal text in the .bat source (codepage bug), so we
REM resolve the path at runtime via %~dp0 (this script's own directory) instead.
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%.."
echo ===== %date% %time% ===== >> logs\quarterly_strategy_check.log
"%SCRIPT_DIR%..\.venv\Scripts\python.exe" -m scripts.quarterly_strategy_check >> logs\quarterly_strategy_check.log 2>&1
echo. >> logs\quarterly_strategy_check.log
