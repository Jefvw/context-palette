@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist ".venv\Scripts\pythonw.exe" (
    echo ERROR: The local Python environment is missing.
    echo Run setup-context-palette.bat first.
    exit /b 1
)

".venv\Scripts\python.exe" -c "import sys, tkinter, context_palette.ui_mockups" >nul 2>nul
if errorlevel 1 (
    echo ERROR: The UI mockups could not start with the local environment.
    echo Run check-context-palette.bat and review the reported problem.
    exit /b 1
)

start "" ".\.venv\Scripts\pythonw.exe" -m context_palette.ui_mockups
exit /b 0
