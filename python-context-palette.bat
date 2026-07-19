@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

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

".venv\Scripts\python.exe" -c "import context_palette" >nul
if errorlevel 1 (
    echo ERROR: Context Palette could not be imported from src.
    echo Run check-context-palette.bat and review the error above.
    exit /b 1
)

".venv\Scripts\python.exe" %*
exit /b %errorlevel%
