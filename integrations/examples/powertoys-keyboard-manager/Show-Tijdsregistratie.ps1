# Launch target for a PowerToys Keyboard Manager "Start App" shortcut.
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$integration = Join-Path $projectRoot "integrations\Invoke-ContextPalette.ps1"
& $integration -Context "Tijdsregistratie"
