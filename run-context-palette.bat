@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: The local Python environment is missing.
    echo Run setup-context-palette.bat first.
    exit /b 1
)

".venv\Scripts\python.exe" -c "import sys, tkinter" >nul 2>nul
if errorlevel 1 (
    echo ERROR: The local Python environment is unusable.
    echo Run setup-context-palette.bat to repair it.
    exit /b 1
)

start "" ".\.venv\Scripts\pythonw.exe" -m context_palette.main
exit /b 0
