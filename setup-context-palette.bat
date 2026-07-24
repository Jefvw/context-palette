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

if not exist ".venv\Scripts\python.exe" goto :create_venv
".venv\Scripts\python.exe" -c "import os, pathlib, sys, tkinter; minimum=tuple(map(int, os.environ['PYTHON_VERSION'].split('.'))); actual=sys.version_info[:2]; expected_prefix=pathlib.Path('.venv').resolve(); actual_prefix=pathlib.Path(sys.prefix).resolve(); marker=expected_prefix / '.context-palette-root'; marker_matches=not marker.exists() or pathlib.Path(marker.read_text(encoding='utf-8').strip()).resolve() == pathlib.Path.cwd().resolve(); raise SystemExit(not (actual[0] == minimum[0] and actual >= minimum and actual_prefix == expected_prefix and marker_matches))" >nul 2>nul
if errorlevel 1 goto :repair_existing_venv
echo Existing .venv found.
goto :environment_ready

:repair_existing_venv
call :find_compatible_python
if not defined PYTHON_CMD goto :venv_check_unavailable
echo Existing .venv is unusable, belongs to another location, or uses Python older than !PYTHON_VERSION!.
set "VENV_BACKUP=.venv-unusable"
if exist "!VENV_BACKUP!" (
    for /l %%N in (1,1,99) do (
        if not exist ".venv-unusable-%%N" if "!VENV_BACKUP!"==".venv-unusable" set "VENV_BACKUP=.venv-unusable-%%N"
    )
)
if "!VENV_BACKUP!"==".venv-unusable" if exist "!VENV_BACKUP!" goto :venv_backup_unavailable
move ".venv" "!VENV_BACKUP!" >nul
if errorlevel 1 goto :venv_preserve_failed
echo Preserved the old environment as !VENV_BACKUP!.

:create_venv
echo Creating local Python !PYTHON_VERSION! environment...
if not defined PYTHON_CMD call :find_compatible_python
if not defined PYTHON_CMD goto :python_unavailable
!PYTHON_CMD! -m venv .venv
if errorlevel 1 goto :venv_creation_failed

:environment_ready

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

:python_unavailable
echo ERROR: A usable Python !PYTHON_VERSION! or newer 3.x installation was not found.
echo Install Python !PYTHON_VERSION! or newer from https://www.python.org/downloads/windows/
echo Setup checked the Python launcher, PATH, and standard Windows install folders.
echo For a custom location, set CONTEXT_PALETTE_PYTHON to its python.exe path.
exit /b 1

:venv_creation_failed
echo ERROR: Could not create .venv.
exit /b 1

:venv_backup_unavailable
echo ERROR: Cannot find a free .venv-unusable backup name.
exit /b 1

:venv_preserve_failed
echo ERROR: Could not preserve the unusable environment as !VENV_BACKUP!.
echo Stop Context Palette and close programs using .venv, then try again.
exit /b 1

:venv_check_unavailable
echo ERROR: Existing .venv could not be checked safely.
echo No compatible Python !PYTHON_VERSION! or newer 3.x interpreter can be launched in this process.
echo The environment was not renamed or rebuilt.
echo If this is a restricted Codex run, retry with normal Windows access.
echo Otherwise install or repair Python !PYTHON_VERSION! or newer, then run setup again.
exit /b 1

:find_compatible_python
set "PYTHON_CMD="
if defined CONTEXT_PALETTE_PYTHON if exist "!CONTEXT_PALETTE_PYTHON!" "!CONTEXT_PALETTE_PYTHON!" -c "import os, sys, tkinter; minimum=tuple(map(int, os.environ['PYTHON_VERSION'].split('.'))); actual=sys.version_info[:2]; raise SystemExit(not (actual[0] == minimum[0] and actual >= minimum))" >nul 2>nul
if defined CONTEXT_PALETTE_PYTHON if exist "!CONTEXT_PALETTE_PYTHON!" if not errorlevel 1 set PYTHON_CMD="!CONTEXT_PALETTE_PYTHON!"
if not defined PYTHON_CMD py -!PYTHON_VERSION! -c "import sys, tkinter" >nul 2>nul
if not defined PYTHON_CMD if not errorlevel 1 set "PYTHON_CMD=py -!PYTHON_VERSION!"
if not defined PYTHON_CMD python -c "import os, sys, tkinter; minimum=tuple(map(int, os.environ['PYTHON_VERSION'].split('.'))); actual=sys.version_info[:2]; raise SystemExit(not (actual[0] == minimum[0] and actual >= minimum))" >nul 2>nul
if not defined PYTHON_CMD if not errorlevel 1 set "PYTHON_CMD=python"
set "PYTHON_CANDIDATE=!LocalAppData!\Programs\Python\Python!PYTHON_MAJOR!!PYTHON_MINOR!\python.exe"
if not defined PYTHON_CMD if exist "!PYTHON_CANDIDATE!" "!PYTHON_CANDIDATE!" -c "import os, sys, tkinter; minimum=tuple(map(int, os.environ['PYTHON_VERSION'].split('.'))); actual=sys.version_info[:2]; raise SystemExit(not (actual[0] == minimum[0] and actual >= minimum))" >nul 2>nul
if not defined PYTHON_CMD if exist "!PYTHON_CANDIDATE!" if not errorlevel 1 set PYTHON_CMD="!PYTHON_CANDIDATE!"
set "PYTHON_CANDIDATE=!ProgramFiles!\Python!PYTHON_MAJOR!!PYTHON_MINOR!\python.exe"
if not defined PYTHON_CMD if exist "!PYTHON_CANDIDATE!" "!PYTHON_CANDIDATE!" -c "import os, sys, tkinter; minimum=tuple(map(int, os.environ['PYTHON_VERSION'].split('.'))); actual=sys.version_info[:2]; raise SystemExit(not (actual[0] == minimum[0] and actual >= minimum))" >nul 2>nul
if not defined PYTHON_CMD if exist "!PYTHON_CANDIDATE!" if not errorlevel 1 set PYTHON_CMD="!PYTHON_CANDIDATE!"
set "PYTHON_CANDIDATE=!ProgramFiles!\Python!PYTHON_MAJOR!.!PYTHON_MINOR!\python.exe"
if not defined PYTHON_CMD if exist "!PYTHON_CANDIDATE!" "!PYTHON_CANDIDATE!" -c "import os, sys, tkinter; minimum=tuple(map(int, os.environ['PYTHON_VERSION'].split('.'))); actual=sys.version_info[:2]; raise SystemExit(not (actual[0] == minimum[0] and actual >= minimum))" >nul 2>nul
if not defined PYTHON_CMD if exist "!PYTHON_CANDIDATE!" if not errorlevel 1 set PYTHON_CMD="!PYTHON_CANDIDATE!"
set "PYTHON_CANDIDATE="
exit /b 0
