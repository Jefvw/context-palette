[CmdletBinding()]
param(
    [string]$Search = "",
    [string]$Context = ""
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Context Palette is not set up. Run setup-context-palette.bat first."
}

$previousPythonPath = $env:PYTHONPATH
$previousSearch = $env:CONTEXT_PALETTE_SEARCH
$previousContext = $env:CONTEXT_PALETTE_CONTEXT
try {
    $env:PYTHONPATH = Join-Path $projectRoot "src"
    $env:CONTEXT_PALETTE_SEARCH = $Search
    $env:CONTEXT_PALETTE_CONTEXT = $Context
    Start-Process -FilePath $python -ArgumentList "-m", "context_palette.main" -WorkingDirectory $projectRoot -WindowStyle Hidden
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:CONTEXT_PALETTE_SEARCH = $previousSearch
    $env:CONTEXT_PALETTE_CONTEXT = $previousContext
}
