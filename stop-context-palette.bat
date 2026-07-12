@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$projectPython = (Resolve-Path '.\.venv\Scripts\pythonw.exe').Path; Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $projectPython } | Stop-Process -Force"
