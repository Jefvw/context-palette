@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Context Palette offline package preparation
echo ===========================================
echo This downloads the normal and optional OCR packages for another compatible PC.
echo It does not package Python itself.
echo.

call setup-context-palette.bat --skip-tests
if errorlevel 1 exit /b 1

if not exist "offline-packages" mkdir "offline-packages"
if errorlevel 1 (
    echo ERROR: Could not create the offline-packages folder.
    exit /b 1
)

echo Preparing required application packages...
".venv\Scripts\python.exe" -m pip wheel --disable-pip-version-check --wheel-dir "offline-packages" -r requirements.txt
if errorlevel 1 (
    echo ERROR: Could not prepare the required offline application packages.
    exit /b 1
)

set "OCR_PACKAGES_READY=1"
echo Preparing optional OCR packages...
".venv\Scripts\python.exe" -m pip wheel --disable-pip-version-check --wheel-dir "offline-packages" -r requirements-ocr.txt
if errorlevel 1 set "OCR_PACKAGES_READY=0"

echo.
if "%OCR_PACKAGES_READY%"=="1" (
    echo Required application and optional OCR packages are ready in offline-packages.
) else (
    echo WARNING: Required application packages are ready in offline-packages,
    echo but the optional OCR packages could not be prepared.
    echo The target PC can still install and run Context Palette without Extract text.
)
echo On the target PC, use a clean checkout of this same commit and copy only
echo offline-packages into it. Do not copy .venv, data\local_*, Inbox, logs,
echo backups, or other ignored personal/runtime files.
echo Then run setup-offline-context-palette.bat.
exit /b 0
