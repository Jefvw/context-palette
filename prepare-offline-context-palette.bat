@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Context Palette offline package preparation
echo ===========================================
echo This downloads the normal and optional OCR packages for another compatible PC.
echo It does not package Python itself.
echo.

call setup-ocr-context-palette.bat
if errorlevel 1 exit /b 1

if not exist "offline-packages" mkdir "offline-packages"
if errorlevel 1 (
    echo ERROR: Could not create the offline-packages folder.
    exit /b 1
)

echo Preparing reusable Windows packages...
".venv\Scripts\python.exe" -m pip wheel --disable-pip-version-check --wheel-dir "offline-packages" -r requirements.txt -r requirements-ocr.txt
if errorlevel 1 (
    echo ERROR: Could not prepare the offline package folder.
    exit /b 1
)

echo.
echo Offline packages are ready in offline-packages.
echo Copy the whole Context Palette folder, including offline-packages, to the target PC.
echo On that PC, run setup-offline-context-palette.bat.
exit /b 0
