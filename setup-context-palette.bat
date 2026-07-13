@echo off
setlocal
cd /d "%~dp0"

echo Context Palette setup
echo =====================

if not exist ".venv\Scripts\python.exe" (
    echo Creating local Python environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3.12 -m venv .venv 2>nul
        if errorlevel 1 py -3 -m venv .venv
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo ERROR: Python 3 was not found.
            echo Install Python 3.12 from https://www.python.org/downloads/windows/
            exit /b 1
        )
        python -m venv .venv
    )
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
    echo ERROR: Python works, but Tkinter is unavailable.
    echo Use the standard Python installer from python.org with Tcl/Tk enabled.
    exit /b 1
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
