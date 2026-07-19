@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

echo Context Palette setup
echo =====================

if not exist ".python-version" (
    echo ERROR: The tracked .python-version file is missing.
    exit /b 1
)
set /p "PYTHON_VERSION="<".python-version"
for /f "tokens=1,2 delims=." %%A in ("!PYTHON_VERSION!") do (
    set "PYTHON_MAJOR=%%A"
    set "PYTHON_MINOR=%%B"
)
if not defined PYTHON_MAJOR (
    echo ERROR: .python-version must contain a version such as 3.12.
    exit /b 1
)
if not defined PYTHON_MINOR (
    echo ERROR: .python-version must contain a version such as 3.12.
    exit /b 1
)

set "RUN_TESTS=1"
if /i "%~1"=="--skip-tests" set "RUN_TESTS=0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import os, pathlib, sys, tkinter; expected_version=os.environ['PYTHON_VERSION']; expected_prefix=pathlib.Path('.venv').resolve(); actual_prefix=pathlib.Path(sys.prefix).resolve(); marker=expected_prefix / '.context-palette-root'; marker_matches=not marker.exists() or pathlib.Path(marker.read_text(encoding='utf-8').strip()).resolve() == pathlib.Path.cwd().resolve(); raise SystemExit(not (f'{sys.version_info.major}.{sys.version_info.minor}' == expected_version and actual_prefix == expected_prefix and marker_matches))" >nul 2>nul
    if errorlevel 1 (
        echo Existing .venv is unusable, belongs to another location, or does not use Python !PYTHON_VERSION!.
        set "VENV_BACKUP=.venv-unusable"
        if exist "!VENV_BACKUP!" (
            for /l %%N in (1,1,99) do (
                if not exist ".venv-unusable-%%N" if "!VENV_BACKUP!"==".venv-unusable" set "VENV_BACKUP=.venv-unusable-%%N"
            )
        )
        if "!VENV_BACKUP!"==".venv-unusable" if exist "!VENV_BACKUP!" (
            echo ERROR: Cannot find a free .venv-unusable backup name.
            exit /b 1
        )
        move ".venv" "!VENV_BACKUP!" >nul
        if errorlevel 1 (
            echo ERROR: Could not preserve the unusable environment as !VENV_BACKUP!.
            echo Stop Context Palette and close programs using .venv, then try again.
            exit /b 1
        )
        echo Preserved the old environment as !VENV_BACKUP!.
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating local Python !PYTHON_VERSION! environment...
    set "PYTHON_CMD="
    py -!PYTHON_VERSION! -c "import sys, tkinter" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -!PYTHON_VERSION!"
    if not defined PYTHON_CMD (
        python -c "import os, sys, tkinter; expected=os.environ['PYTHON_VERSION']; actual=f'{sys.version_info.major}.{sys.version_info.minor}'; raise SystemExit(not actual == expected)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
    if not defined PYTHON_CMD (
        echo ERROR: A usable Python !PYTHON_VERSION! installation was not found.
        echo Install Python !PYTHON_VERSION! from https://www.python.org/downloads/windows/
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

> ".venv\.context-palette-root" echo %CD%

if not exist "data\inbox.json" copy /y "data\inbox.example.json" "data\inbox.json" >nul
if not exist "data\local_actions.json" copy /y "data\local_actions.example.json" "data\local_actions.json" >nul
if not exist "data\local_contexts.json" copy /y "data\local_contexts.example.json" "data\local_contexts.json" >nul
if not exist "data\local_command_surface.json" copy /y "data\local_command_surface.example.json" "data\local_command_surface.json" >nul
if not exist "data\palette.json" copy /y "data\palette.example.json" "data\palette.json" >nul

echo Verifying Python and Tkinter...
".venv\Scripts\python.exe" -c "import sys, tkinter; print('Python', sys.version.split()[0], '- Tk', tkinter.TkVersion)"
if errorlevel 1 (
    echo ERROR: The local Python environment cannot load Tkinter.
    echo Use the standard Python installer from python.org with Tcl/Tk enabled.
    exit /b 1
)

echo Removing retired local configuration...
".venv\Scripts\python.exe" -m context_palette.retired_feature_cleanup
if errorlevel 1 exit /b 1

if exist "requirements.txt" (
    set "REQUIREMENTS_MARKER=.venv\.context-palette-requirements.sha256"
    set "REQUIREMENTS_HASH="
    set "INSTALLED_REQUIREMENTS_HASH="
    for /f "delims=" %%H in ('.venv\Scripts\python.exe -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest())"') do set "REQUIREMENTS_HASH=%%H"
    if not defined REQUIREMENTS_HASH (
        echo ERROR: Could not calculate the requirements signature.
        exit /b 1
    )
    if exist "!REQUIREMENTS_MARKER!" set /p "INSTALLED_REQUIREMENTS_HASH="<"!REQUIREMENTS_MARKER!"
    if "!REQUIREMENTS_HASH!"=="!INSTALLED_REQUIREMENTS_HASH!" (
        echo Project dependencies are unchanged.
    ) else (
        echo Installing project dependencies...
        ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
        if errorlevel 1 (
            echo ERROR: Could not install project dependencies.
            exit /b 1
        )
        > "!REQUIREMENTS_MARKER!" echo !REQUIREMENTS_HASH!
    )
)

if "!RUN_TESTS!"=="1" (
    echo Running tests...
    ".venv\Scripts\python.exe" -m unittest discover tests
    if errorlevel 1 (
        echo ERROR: Tests failed. Review the output above.
        exit /b 1
    )
)

echo.
echo Setup complete. Start with run-context-palette.bat
exit /b 0
