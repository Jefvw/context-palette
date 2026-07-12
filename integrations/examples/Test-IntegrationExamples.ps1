$ErrorActionPreference = "Stop"
$exampleRoot = $PSScriptRoot
$scripts = Get-ChildItem -LiteralPath $exampleRoot -Recurse -Filter "*.ps1" |
    Where-Object { $_.FullName -ne $PSCommandPath }

$failures = @()
foreach ($script in $scripts) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $script.FullName,
        [ref]$tokens,
        [ref]$errors
    )
    if ($errors) {
        $failures += $errors
    }
}

if ($failures) {
    $failures | Format-List
    exit 1
}

Write-Output "Validated $($scripts.Count) integration example scripts."
