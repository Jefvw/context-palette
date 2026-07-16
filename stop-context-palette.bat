@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$projectExecutables = @((Resolve-Path '.\.venv\Scripts\python.exe').Path, (Resolve-Path '.\.venv\Scripts\pythonw.exe').Path);" ^
  "$processes = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe', 'pythonw.exe') });" ^
  "$rootIds = @($processes | Where-Object { $_.ExecutablePath -in $projectExecutables } | ForEach-Object ProcessId);" ^
  "$targetIds = [System.Collections.Generic.HashSet[uint32]]::new();" ^
  "$rootIds | ForEach-Object { [void]$targetIds.Add($_) };" ^
  "do { $added = $false; foreach ($process in $processes) { if ($targetIds.Contains([uint32]$process.ParentProcessId) -and $targetIds.Add([uint32]$process.ProcessId)) { $added = $true } } } while ($added);" ^
  "$targetIds | Sort-Object -Descending | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
