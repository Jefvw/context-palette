@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
start "" ".\.venv\Scripts\pythonw.exe" -m context_palette.main
exit /b 0
