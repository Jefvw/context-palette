@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Context Palette offline setup
echo =============================
echo This setup uses only the prepared offline-packages folder.
echo It does not require administrator rights or package-download access.
echo.

if not exist "offline-packages\." (
    echo ERROR: The offline-packages folder is missing.
    echo Prepare it on a compatible connected Windows PC first.
    exit /b 1
)

set "CONTEXT_PALETTE_WHEELHOUSE=%CD%\offline-packages"
call setup-context-palette.bat --skip-tests
if errorlevel 1 exit /b 1

set "OCR_SETUP_FAILED=0"
call setup-ocr-context-palette.bat
if errorlevel 1 set "OCR_SETUP_FAILED=1"

call check-context-palette.bat
if errorlevel 1 exit /b 1

echo.
if "%OCR_SETUP_FAILED%"=="1" (
    echo Core offline setup and checks are complete. Optional OCR is unavailable.
    echo Context Palette still works; only Extract text is unavailable.
) else (
    echo Offline setup, optional OCR, and checks are complete.
)
echo Start with run-context-palette.bat
exit /b 0
