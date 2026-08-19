@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo Context Palette local OCR setup
echo ===============================
echo This optional component stays inside the Context Palette folder.
echo It does not require administrator rights and adds about 270 MB.
echo.

call setup-context-palette.bat --skip-tests
if errorlevel 1 exit /b 1

if not exist "requirements-ocr.txt" (
    echo ERROR: The tracked requirements-ocr.txt file is missing.
    goto :ocr_unavailable
)

set "OCR_REQUIREMENTS_MARKER=.venv\.context-palette-ocr-requirements.sha256"
set "OCR_REQUIREMENTS_HASH="
set "INSTALLED_OCR_REQUIREMENTS_HASH="
for /f "delims=" %%H in ('.venv\Scripts\python.exe -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('requirements-ocr.txt').read_bytes()).hexdigest())"') do set "OCR_REQUIREMENTS_HASH=%%H"
if not defined OCR_REQUIREMENTS_HASH (
    echo ERROR: Could not calculate the OCR requirements signature.
    goto :ocr_unavailable
)
if exist "!OCR_REQUIREMENTS_MARKER!" set /p "INSTALLED_OCR_REQUIREMENTS_HASH="<"!OCR_REQUIREMENTS_MARKER!"
if "!OCR_REQUIREMENTS_HASH!"=="!INSTALLED_OCR_REQUIREMENTS_HASH!" (
    echo Optional OCR dependencies are unchanged.
) else (
    echo Installing the optional local OCR engine and bundled models...
    if defined CONTEXT_PALETTE_WHEELHOUSE (
        echo Using offline packages from !CONTEXT_PALETTE_WHEELHOUSE!
        ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-ocr.txt --no-index --find-links "!CONTEXT_PALETTE_WHEELHOUSE!"
    ) else (
        ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-ocr.txt
    )
    if errorlevel 1 (
        echo ERROR: The optional OCR component could not be prepared.
        echo This step needs package-download access or a prepared offline package folder,
        echo but never administrator rights.
        goto :ocr_unavailable
    )
)

echo Verifying the local OCR engine...
".venv\Scripts\python.exe" -c "from rapidocr import RapidOCR; import onnxruntime; RapidOCR(params={'Global.log_level':'ERROR'}); print('Local OCR is ready.')"
if errorlevel 1 (
    echo ERROR: The OCR files were downloaded but cannot run on this computer.
    if exist "!OCR_REQUIREMENTS_MARKER!" del /q "!OCR_REQUIREMENTS_MARKER!" >nul
    goto :ocr_unavailable
)
> "!OCR_REQUIREMENTS_MARKER!" echo !OCR_REQUIREMENTS_HASH!

echo.
echo OCR setup complete. Restart Context Palette to use Extract text.
exit /b 0

:ocr_unavailable
echo.
echo Core Context Palette setup completed and remains available.
echo Only Extract text is unavailable. Start with run-context-palette.bat,
echo then retry this optional OCR setup later if needed.
exit /b 1
