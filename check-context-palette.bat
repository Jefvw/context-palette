@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: The local Python environment is missing.
    echo Run setup-context-palette.bat first.
    exit /b 1
)

echo Validating Context Palette configuration...
".venv\Scripts\python.exe" -m context_palette.configuration_check
if errorlevel 1 exit /b 1

echo Compiling source...
".venv\Scripts\python.exe" -m compileall -q src
if errorlevel 1 exit /b 1

echo Running tests...
".venv\Scripts\python.exe" -m unittest discover tests
if errorlevel 1 exit /b 1

echo.
echo Context Palette checks passed.
exit /b 0
