@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo Context Palette setup
echo =====================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys, tkinter" >nul 2>nul
    if errorlevel 1 (
        echo Existing .venv is unusable, usually because the project or Python moved.
        if exist ".venv-unusable" (
            echo ERROR: Cannot preserve .venv because .venv-unusable already exists.
            echo Rename or remove .venv-unusable, then run setup again.
            exit /b 1
        )
        move ".venv" ".venv-unusable" >nul
        if errorlevel 1 (
            echo ERROR: Could not preserve the unusable environment as .venv-unusable.
            echo Stop Context Palette and close programs using .venv, then try again.
            exit /b 1
        )
        echo Preserved the old environment as .venv-unusable.
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating local Python environment...
    set "PYTHON_CMD="
    py -3.12 -c "import sys, tkinter" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.12"
    if not defined PYTHON_CMD (
        py -3 -c "import sys, tkinter; raise SystemExit(sys.version_info < (3, 12))" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=py -3"
    )
    if not defined PYTHON_CMD (
        python -c "import sys, tkinter; raise SystemExit(sys.version_info < (3, 12))" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
    if not defined PYTHON_CMD (
        echo ERROR: A usable Python 3.12 installation was not found.
        echo Install Python 3.12 from https://www.python.org/downloads/windows/
        echo Ensure the Python launcher or python.exe is available, then run setup again.
        exit /b 1
    )
    !PYTHON_CMD! -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create .venv.
        exit /b 1
    )
) else (
    echo Existing .venv found.
)

if not exist "data\inbox.json" copy /y "data\inbox.example.json" "data\inbox.json" >nul
if not exist "data\local_actions.json" copy /y "data\local_actions.example.json" "data\local_actions.json" >nul
if not exist "data\local_contexts.json" copy /y "data\local_contexts.example.json" "data\local_contexts.json" >nul
if not exist "data\local_command_surface.json" copy /y "data\local_command_surface.example.json" "data\local_command_surface.json" >nul
if not exist "data\palette.json" copy /y "data\palette.example.json" "data\palette.json" >nul
if not exist "data\layouts\snapshots" mkdir "data\layouts\snapshots"

echo Verifying Python and Tkinter...
".venv\Scripts\python.exe" -c "import sys, tkinter; print('Python', sys.version.split()[0], '- Tk', tkinter.TkVersion)"
if errorlevel 1 (
    echo ERROR: The local Python environment cannot load Tkinter.
    echo Use the standard Python installer from python.org with Tcl/Tk enabled.
    exit /b 1
)

if exist "requirements.txt" (
    echo Installing project dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Could not install project dependencies.
        exit /b 1
    )
)

echo Running tests...
".venv\Scripts\python.exe" -m unittest discover tests
if errorlevel 1 (
    echo ERROR: Tests failed. Review the output above.
    exit /b 1
)

echo.
echo Setup complete. Start with run-context-palette.bat
exit /b 0
