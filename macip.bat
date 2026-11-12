@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    start "macip-editori" py -3 "%~dp0macip_local_server.py"
) else (
    start "macip-editori" python "%~dp0macip_local_server.py"
)
