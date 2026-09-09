@echo off
setlocal
set "PYTHONUTF8=1"
set "SCRIPT=%~dp0scripts\local_platform_connector.py"
set "CWH_RUNTIME=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CWH_RUNTIME%" ("%CWH_RUNTIME%" "%SCRIPT%" & goto :eof)
where py >nul 2>nul && (py -3 "%SCRIPT%" & goto :eof)
where python >nul 2>nul && (python "%SCRIPT%" & goto :eof)
echo No Python runtime was found. Install Python or start the connector from Codex.
pause
