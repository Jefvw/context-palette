@echo off
setlocal EnableExtensions EnableDelayedExpansion
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

if exist "requirements.txt" (
    set "REQUIREMENTS_MARKER=.venv\.context-palette-requirements.sha256"
    set "REQUIREMENTS_HASH="
    set "INSTALLED_REQUIREMENTS_HASH="
    for /f "delims=" %%H in ('.venv\Scripts\python.exe -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest())"') do set "REQUIREMENTS_HASH=%%H"
    if exist "!REQUIREMENTS_MARKER!" set /p "INSTALLED_REQUIREMENTS_HASH="<"!REQUIREMENTS_MARKER!"
    if not defined REQUIREMENTS_HASH goto :dependencies_out_of_date
    if /i not "!REQUIREMENTS_HASH!"=="!INSTALLED_REQUIREMENTS_HASH!" goto :dependencies_out_of_date
)

start "" ".\.venv\Scripts\pythonw.exe" -m context_palette.main
exit /b 0

:dependencies_out_of_date
echo ERROR: Project dependencies are missing or out of date.
echo Run stop-context-palette.bat, then setup-context-palette.bat, then run this launcher again.
exit /b 1
