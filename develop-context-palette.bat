@echo off
setlocal
cd /d "%~dp0"

echo Preparing Context Palette for development...
call setup-context-palette.bat --skip-tests
if errorlevel 1 exit /b 1

echo.
call check-context-palette.bat
exit /b %errorlevel%
