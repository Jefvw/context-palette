param(
    [Parameter(Mandatory=$true)][Int64]$SourceHwnd,
    [Parameter(Mandatory=$true)][string]$StagedPdf
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$script:failureCode = 'unknown'
$script:invocations = @()

function Fail([string]$code) {
    $script:failureCode = $code
    throw 'Score export stopped.'
}
function Condition($property, $value) {
    return [System.Windows.Automation.PropertyCondition]::new($property, $value)
}
function Named-Control([string]$name, $type) {
    return [System.Windows.Automation.AndCondition]::new(
        (Condition ([System.Windows.Automation.AutomationElement]::NameProperty) $name),
        (Condition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty) $type)
    )
}
function Visible-Matches($parent, $condition) {
    return @($parent.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition) |
        Where-Object { -not $_.Current.IsOffscreen -and $_.Current.IsEnabled })
}
function One-Control($parent, $condition, [string]$stage) {
    $controls = @(Visible-Matches $parent $condition)
    if ($controls.Count -eq 0) { Fail ($stage + '_missing') }
    if ($controls.Count -gt 1) { Fail ($stage + '_ambiguous') }
    return $controls[0]
}
function Assert-Source {
    if (-not [ContextPaletteScoreNative]::SourceIsCurrent($script:hwnd, $script:edgeProcessId)) {
        Fail 'unavailable_window'
    }
    $foreground = [ContextPaletteScoreNative]::GetForegroundWindow()
    if (-not [ContextPaletteScoreNative]::IsOwnedBy($script:hwnd, $foreground)) {
        Fail 'focus_changed'
    }
    foreach ($invocation in $script:invocations) {
        if ($invocation.Failed) { Fail 'invoke_failed' }
    }
    return $foreground
}
function Wait-For([scriptblock]$probe, [int]$seconds, [string]$code) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        Assert-Source | Out-Null
        $found = & $probe
        if ($null -ne $found) { return $found }
        Start-Sleep -Milliseconds 100
    } while ($timer.Elapsed.TotalSeconds -lt $seconds)
    Fail $code
}
function Invoke-Control($element) {
    $foreground = Assert-Source
    $script:invocations += [ContextPaletteScoreNative]::InvokeAsync(
        $element, $script:hwnd, $script:edgeProcessId, $foreground
    )
}
function Score-Url([string]$value) {
    try { $uri = [Uri]$value } catch { Fail 'unsupported_page' }
    if ($value -notmatch '^https://tabs\.ultimate-guitar\.com/tab/[a-z0-9-]+/[a-z0-9-]+-(?:official|guitar-pro)-[0-9]+\z' -or
        $uri.Scheme -ne 'https' -or $uri.Host -ne 'tabs.ultimate-guitar.com' -or
        $uri.UserInfo -or -not $uri.IsDefaultPort -or $uri.Query -or $uri.Fragment -or
        $uri.AbsolutePath -notmatch '^/tab/[a-z0-9-]+/[a-z0-9-]+-(?:official|guitar-pro)-[0-9]+\z') {
        Fail 'unsupported_page'
    }
    return $uri.AbsoluteUri
}
function Score-Address($address) {
    $value = $address.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    return Score-Url $value
}
function Score-DocumentTitle([string]$name, [string]$url) {
    $validatedUrl = Score-Url $url
    # URL type and accessible document title must agree. Ordinary text tabs
    # can also say TAB, but do not have the supported guitar-pro URL suffix.
    if ($validatedUrl -match '-guitar-pro-[0-9]+$') {
        $pattern = '^(?:\([0-9]+\)\s*)?(.+) TAB by (.+) @ Ultimate-Guitar\.Com$'
    } else {
        $pattern = '^(?:\([0-9]+\)\s*)?OFFICIAL (.+) CHORDS & TABS by (.+) @ Ultimate-Guitar\.Com$'
    }
    $identity = [regex]::Match($name.Trim(), $pattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if (-not $identity.Success) { return $null }
    $title = ($identity.Groups[2].Value.Trim() + ' - ' + $identity.Groups[1].Value.Trim()) -replace '\s+', ' '
    if ($title.Length -gt 200) { $title = $title.Substring(0, 200) }
    return $title
}
function Score-PrintMatches($document) {
    $condition = Condition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty) ([System.Windows.Automation.ControlType]::Button)
    # Edge can include whitespace in the accessible name of the site's PRINT
    # button. Match only that whole label, after trimming, within this document.
    return @($document.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition) |
        Where-Object { $_.Current.Name.Trim() -ieq 'PRINT' })
}
function Score-PrintControl($document, $address, [string]$url) {
    $controls = @(Score-PrintMatches $document)
    if ($controls.Count -eq 0) { Fail 'score_print_missing' }
    if ($controls.Count -gt 1) { Fail 'score_print_ambiguous' }
    $button = $controls[0]
    if (-not $button.Current.IsEnabled) { Fail 'score_print_disabled' }
    if ($button.Current.IsOffscreen) { Fail 'score_print_hidden' }
    Assert-Source | Out-Null
    if ((Score-Address $address) -ne $url) { Fail 'page_changed' }
    return $button
}
function Is-EdgeDialogProcess($foreground) {
    # The native Save As window can be hosted by another Edge process. Resolve
    # its actual HWND owner process, not the UIA provider's process attribution.
    $dialogProcessId = [ContextPaletteScoreNative]::WindowProcessId($foreground)
    if ($dialogProcessId -le 0 -or -not $script:edgeExecutable) { return $false }
    try {
        $dialogProcess = Get-Process -Id $dialogProcessId -ErrorAction Stop
        return [string]::Equals($dialogProcess.Path, $script:edgeExecutable, [StringComparison]::OrdinalIgnoreCase)
    } catch { return $false }
}
function Ready-SaveDialog($candidate, $edge, $foreground) {
    # UIA properties can initialize after a modal first takes foreground.
    # Keep polling without effects until the entire identity is ready.
    if ($candidate.Current.Name.Trim() -ine 'Save As' -or
        $candidate.Current.ClassName -ne '#32770' -or
        [IntPtr]$candidate.Current.NativeWindowHandle -ne $foreground) { return $null }
    if (-not $edge.Current.IsEnabled -and $candidate.Current.IsEnabled -and
        (Is-EdgeDialogProcess $foreground)) { return $candidate }
    return $null
}
function Assert-PdfPrinter($dialog) {
    $printerGroup = One-Control $dialog (Named-Control 'Printer' ([System.Windows.Automation.ControlType]::Group)) 'printer_group'
    $selector = One-Control $printerGroup (Condition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty) ([System.Windows.Automation.ControlType]::ComboBox)) 'printer_selector'
    $selected = $false
    try {
        $selection = @($selector.GetCurrentPattern([System.Windows.Automation.SelectionPattern]::Pattern).Current.GetSelection())
        $selected = $selection.Count -eq 1 -and $selection[0].Current.Name -eq 'Save as PDF'
    } catch {}
    if (-not $selected) {
        try {
            $selected = $selector.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value -eq 'Save as PDF'
        } catch {}
    }
    if (-not $selected) { Fail 'choose_pdf_printer' }
}
function Complete-Pdf {
    if (-not [IO.File]::Exists($StagedPdf)) { return $null }
    $stream = $null
    try {
        $stream = [IO.File]::Open($StagedPdf, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
        if ($stream.Length -lt 10) { return $null }
        $header = New-Object byte[] 5
        [void]$stream.Read($header, 0, 5)
        [void]$stream.Seek([Math]::Max(0, $stream.Length - 1024), [IO.SeekOrigin]::Begin)
        $tail = New-Object byte[] ([int][Math]::Min(1024, $stream.Length))
        [void]$stream.Read($tail, 0, $tail.Length)
        if ([Text.Encoding]::ASCII.GetString($header) -eq '%PDF-' -and
            [Text.Encoding]::ASCII.GetString($tail) -match '%%EOF\s*$') {
            return $stream.Length
        }
    } catch {} finally { if ($null -ne $stream) { $stream.Dispose() } }
    return $null
}

try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    Add-Type -AssemblyName WindowsBase
    $references = @(
        [System.Windows.Automation.AutomationElement].Assembly.Location,
        [System.Windows.Automation.ControlType].Assembly.Location,
        [System.Windows.Rect].Assembly.Location
    ) | Select-Object -Unique
    Add-Type -Path (Join-Path $PSScriptRoot 'edge_score_pdf_native.cs') -ReferencedAssemblies $references

    # Only the caller's new, private staging filename is eligible for Save As.
    if (-not [IO.Path]::IsPathRooted($StagedPdf) -or
        [IO.Path]::GetFileName($StagedPdf) -ne 'score.pdf' -or
        [IO.Path]::GetFileName([IO.Path]::GetDirectoryName($StagedPdf)) -notlike '.context-palette-edge-score-*' -or
        -not [IO.Directory]::Exists([IO.Path]::GetDirectoryName($StagedPdf)) -or
        [IO.File]::Exists($StagedPdf)) { Fail 'invalid_staging' }

    Write-Output 'CONTEXT_PALETTE_PROGRESS:checking'
    $script:hwnd = [IntPtr]$SourceHwnd
    $edge = [System.Windows.Automation.AutomationElement]::FromHandle($script:hwnd)
    if ($null -eq $edge) { Fail 'unavailable_window' }
    $script:edgeProcessId = $edge.Current.ProcessId
    $edgeProcess = Get-Process -Id $script:edgeProcessId
    if ($edgeProcess.ProcessName -ne 'msedge' -or
        [IO.Path]::GetFileName($edgeProcess.Path) -ne 'msedge.exe') { Fail 'not_edge' }
    $script:edgeExecutable = $edgeProcess.Path
    if (-not $edge.Current.IsEnabled) { Fail 'unexpected_dialog' }
    if ((Assert-Source) -ne $script:hwnd) { Fail 'unexpected_dialog' }

    $address = One-Control $edge (Condition ([System.Windows.Automation.AutomationElement]::AutomationIdProperty) 'view_1021') 'address'
    $url = Score-Address $address
    $documents = @(Visible-Matches $edge (Condition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty) ([System.Windows.Automation.ControlType]::Document)) |
        Where-Object { $null -ne (Score-DocumentTitle $_.Current.Name $url) })
    if ($documents.Count -ne 1) { Fail 'unsupported_page' }
    $document = $documents[0]
    $title = Score-DocumentTitle $document.Current.Name $url
    if (-not $title) { Fail 'unsupported_page' }
    $print = Score-PrintControl $document $address $url
    if ((Score-Address $address) -ne $url) { Fail 'page_changed' }

    Write-Output 'CONTEXT_PALETTE_PROGRESS:opening'
    Invoke-Control $print
    $dialog = Wait-For {
        # Chromium maps a dialog to UIA Window, unlike its inner heading/group.
        $dialogs = @(Visible-Matches $edge (Named-Control 'Print' ([System.Windows.Automation.ControlType]::Window)))
        if ($dialogs.Count -gt 1) { Fail 'unexpected_dialog' }
        if ($dialogs.Count -eq 1) { return $dialogs[0] }
    } 20 'preview_timeout'

    $save = Wait-For {
        $buttons = @(Visible-Matches $dialog (Named-Control 'Save' ([System.Windows.Automation.ControlType]::Button)))
        if ($buttons.Count -gt 1) { Fail 'unsupported_controls' }
        if ($buttons.Count -eq 1) { return $buttons[0] }
        $physical = @(Visible-Matches $dialog (Named-Control 'Print' ([System.Windows.Automation.ControlType]::Button)))
        if ($physical.Count -gt 0) { Fail 'choose_pdf_printer' }
    } 20 'preview_timeout'
    Assert-PdfPrinter $dialog
    Write-Output 'CONTEXT_PALETTE_PROGRESS:saving'
    $previewForeground = Assert-Source
    Invoke-Control $save

    $native = Wait-For {
        # The modal is the owned foreground HWND. Resolving that handle avoids
        # relying on whether a UIA provider places it under Edge or the desktop.
        $foreground = Assert-Source
        if ($foreground -eq $script:hwnd -or $foreground -eq $previewForeground) { return $null }
        $candidate = [System.Windows.Automation.AutomationElement]::FromHandle($foreground)
        Ready-SaveDialog $candidate $edge $foreground
    } 20 'save_dialog_timeout'
    $nativeHandle = [IntPtr]$native.Current.NativeWindowHandle
    if ((Assert-Source) -ne $nativeHandle) { Fail 'focus_changed' }
    $name = One-Control $native ([System.Windows.Automation.AndCondition]::new(
        (Condition ([System.Windows.Automation.AutomationElement]::AutomationIdProperty) '1001'),
        (Condition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty) ([System.Windows.Automation.ControlType]::Edit))
    )) 'filename'
    $filename = $name.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $filename.SetValue($StagedPdf)
    if ($filename.Current.Value -ne $StagedPdf) { Fail 'filename_changed' }
    $nativeSave = One-Control $native ([System.Windows.Automation.AndCondition]::new(
        (Condition ([System.Windows.Automation.AutomationElement]::AutomationIdProperty) '1'),
        (Condition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty) ([System.Windows.Automation.ControlType]::Button))
    )) 'native_save'
    if ((Assert-Source) -ne $nativeHandle -or $filename.Current.Value -ne $StagedPdf) { Fail 'filename_changed' }
    Invoke-Control $nativeSave

    Write-Output 'CONTEXT_PALETTE_PROGRESS:verifying'
    $length = Wait-For { Complete-Pdf } 20 'file_timeout'
    Start-Sleep -Milliseconds 250
    if ((Complete-Pdf) -ne $length) { Fail 'file_timeout' }
    Wait-For {
        try { if (-not $native.Current.IsOffscreen) { return $null } } catch {}
        return $true
    } 5 'file_timeout' | Out-Null
    Write-Output ('CONTEXT_PALETTE_RESULT:' + (@{url=$url; title=$title} | ConvertTo-Json -Compress))
} catch {
    Write-Output ('CONTEXT_PALETTE_ERROR:' + $script:failureCode)
    exit 1
}
