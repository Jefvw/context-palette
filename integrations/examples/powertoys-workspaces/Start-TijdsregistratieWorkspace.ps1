[CmdletBinding()]
param(
    [switch]$SkipCompanionWindows
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$integration = Join-Path $projectRoot "integrations\Invoke-ContextPalette.ps1"

& $integration -Context "Tijdsregistratie"

if (-not $SkipCompanionWindows) {
    # Safe public dummy target used while developing away from the work PC.
    Start-Process "https://www.colruyt.be/nl/"

    $outlookCandidates = @(
        "$env:ProgramFiles\Microsoft Office\root\Office16\OUTLOOK.EXE",
        "${env:ProgramFiles(x86)}\Microsoft Office\root\Office16\OUTLOOK.EXE"
    )
    $outlook = $outlookCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if ($outlook) {
        Start-Process -FilePath $outlook
    }
}

[pscustomobject]@{
    Success = $true
    Context = "Tijdsregistratie"
    CompanionWindowsStarted = -not $SkipCompanionWindows
}
