# Working example for Power Automate Desktop's "Run PowerShell script" action.
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$integration = Join-Path $projectRoot "integrations\Invoke-ContextPalette.ps1"

& $integration -Context "Tijdsregistratie" -Search "agenda"

[pscustomobject]@{
    Success = $true
    Context = "Tijdsregistratie"
    Search = "agenda"
}
