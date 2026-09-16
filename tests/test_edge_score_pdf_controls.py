"""Contract-test extracted PowerShell control helpers without live UI access."""

from pathlib import Path
import os
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


HARNESS = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @'
using System;
public static class ContextPaletteScoreNative {
    public static int DialogProcessId;
    public static long LastWindowHandle;
    public static int WindowProcessId(IntPtr handle) {
        LastWindowHandle = handle.ToInt64();
        return DialogProcessId;
    }
}
'@
$script:expectedProperty = [System.Windows.Automation.AutomationElement]::ControlTypeProperty
$script:expectedValue = [System.Windows.Automation.ControlType]::Button

$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $pwd 'src\context_palette\edge_score_pdf.ps1'),
    [ref]$tokens,
    [ref]$errors
)
if ($errors.Count) { throw 'The companion script did not parse.' }
foreach ($name in 'One-Control', 'Score-PrintMatches', 'Score-PrintControl', 'Is-EdgeDialogProcess', 'Ready-SaveDialog') {
    $definition = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)
    if ($definition.Count -ne 1) { throw "Expected one $name definition." }
    Invoke-Expression @($definition)[0].Extent.Text
}
function Condition($property, $value) {
    # Preserve the exact values Score-PrintMatches passes to its query without
    # constructing a live UIA condition object in this fake-only harness.
    return [pscustomobject]@{ Property = $property; Value = $value }
}

class FakeCurrent {
    [bool]$IsOffscreen
    [bool]$IsEnabled
    [string]$Name
    [string]$ClassName
    [int]$ProcessId
    [int]$NativeWindowHandle
    FakeCurrent([bool]$offscreen, [bool]$enabled) {
        $this.IsOffscreen = $offscreen
        $this.IsEnabled = $enabled
        $this.Name = 'PRINT'
        $this.ClassName = '#32770'
        $this.ProcessId = 42
        $this.NativeWindowHandle = 500
    }
}
class FakeElement {
    [FakeCurrent]$Current
    [object[]]$Matches
    [int]$FindCalls
    [bool]$IsButton
    FakeElement([bool]$offscreen, [bool]$enabled) {
        $this.Current = [FakeCurrent]::new($offscreen, $enabled)
        $this.Matches = @()
        $this.IsButton = $true
    }
    [object[]] FindAll([object]$scope, [object]$condition) {
        $this.FindCalls++
        if ($condition.Property -ne $script:expectedProperty -or $condition.Value -ne $script:expectedValue) {
            throw 'ASSERT:Score-PrintMatches did not request Button controls'
        }
        return @($this.Matches | Where-Object { $_.IsButton })
    }
}

function Fail([string]$code) { throw "FAIL:$code" }
function Assert-Source {
    $script:sourceCalls++
    if (-not $script:sourceOk) { Fail 'unavailable_window' }
    return 1
}
function Score-Address($address) {
    $script:addressCalls++
    return $script:addressValue
}
function Visible-Matches($parent, $condition) { return $script:visibleMatches }
function Get-Process {
    param([int]$Id, $ErrorAction)
    if ($script:dialogProcessUnreadable -or $Id -ne $script:dialogProcessId) {
        throw 'process unavailable'
    }
    return [pscustomobject]@{ Path = $script:dialogProcessPath }
}
function Reset-State {
    $script:sourceOk = $true
    $script:sourceCalls = 0
    $script:addressCalls = 0
    $script:addressValue = 'https://tabs.ultimate-guitar.com/tab/artist/song-official-1'
    $script:edgeProcessId = 42
    $script:edgeExecutable = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    $script:dialogProcessId = 77
    $script:dialogProcessPath = $script:edgeExecutable
    $script:dialogProcessUnreadable = $false
    [ContextPaletteScoreNative]::DialogProcessId = $script:dialogProcessId
    [ContextPaletteScoreNative]::LastWindowHandle = 0
    $script:visibleMatches = @()
}
function Assert-True([bool]$condition, [string]$message) { if (-not $condition) { throw "ASSERT:$message" } }
function Expect-Fail([string]$code, [scriptblock]$action) {
    try { & $action; throw "ASSERT:expected $code" }
    catch {
        if ($_.Exception.Message -ne "FAIL:$code") { throw }
    }
}

$url = 'https://tabs.ultimate-guitar.com/tab/artist/song-official-1'

# Visible one PRINT control: no scroll, source and URL are checked, and it is returned.
Reset-State
$button = [FakeElement]::new($false, $true)
$document = [FakeElement]::new($false, $true); $document.Matches = @($button)
$found = Score-PrintControl $document ([object]::new()) $url
Assert-True ($found -eq $button) 'visible button was not returned'
Assert-True ($script:sourceCalls -ge 1 -and $script:addressCalls -ge 1) 'source/address were not checked'

# The provider's whitespace/case variation is accepted, while other labels and
# non-button controls are not candidates.
Reset-State
$button = [FakeElement]::new($false, $true); $button.Current.Name = '  pRiNt  '
$document = [FakeElement]::new($false, $true); $document.Matches = @($button)
Assert-True ((Score-PrintControl $document ([object]::new()) $url) -eq $button) 'trimmed case-insensitive label was not accepted'
Reset-State
$button = [FakeElement]::new($false, $true); $button.Current.Name = 'PRINT SCORE'
$document = [FakeElement]::new($false, $true); $document.Matches = @($button)
Expect-Fail 'score_print_missing' { Score-PrintControl $document ([object]::new()) $url | Out-Null }
Reset-State
$button = [FakeElement]::new($false, $true); $button.Current.Name = ' PRINT '; $button.IsButton = $false
$document = [FakeElement]::new($false, $true); $document.Matches = @($button)
Expect-Fail 'score_print_missing' { Score-PrintControl $document ([object]::new()) $url | Out-Null }
# Missing, ambiguous, disabled, and hidden raw matches are rejected.
Reset-State
$document = [FakeElement]::new($false, $true); $document.Matches = @()
Expect-Fail 'score_print_missing' { Score-PrintControl $document ([object]::new()) $url | Out-Null }
Reset-State
$first = [FakeElement]::new($false, $true); $first.Current.Name = ' PRINT '
$second = [FakeElement]::new($false, $true); $second.Current.Name = 'print'
$document = [FakeElement]::new($false, $true); $document.Matches = @($first, $second)
Expect-Fail 'score_print_ambiguous' { Score-PrintControl $document ([object]::new()) $url | Out-Null }
Reset-State
$button = [FakeElement]::new($false, $false)
$document = [FakeElement]::new($false, $true); $document.Matches = @($button)
Expect-Fail 'score_print_disabled' { Score-PrintControl $document ([object]::new()) $url | Out-Null }
Reset-State
$button = [FakeElement]::new($true, $true)
$document = [FakeElement]::new($false, $true); $document.Matches = @($button)
Expect-Fail 'score_print_hidden' { Score-PrintControl $document ([object]::new()) $url | Out-Null }
# Changed source/page stop before a selected control can be returned.
Reset-State
$script:sourceOk = $false
$button = [FakeElement]::new($false, $true)
$document = [FakeElement]::new($false, $true); $document.Matches = @($button)
Expect-Fail 'unavailable_window' { Score-PrintControl $document ([object]::new()) $url | Out-Null }
Reset-State
$script:addressValue = 'https://tabs.ultimate-guitar.com/tab/artist/other-official-2'
$button = [FakeElement]::new($false, $true)
$document = [FakeElement]::new($false, $true); $document.Matches = @($button)
Expect-Fail 'page_changed' { Score-PrintControl $document ([object]::new()) $url | Out-Null }

# Ready-SaveDialog waits for the foreground-owned Edge native modal's identity
# to stabilize. A mismatch is not actionable; the same candidate can be ready
# only after all identity properties become correct.
Reset-State
$edge = [FakeElement]::new($false, $false)
$candidate = [FakeElement]::new($false, $true); $candidate.Current.Name = '  sAvE aS  '
$ready = Ready-SaveDialog $candidate $edge ([IntPtr]500)
Assert-True ($ready -eq $candidate) 'valid Save As modal was not ready'
foreach ($alter in 'Name', 'ClassName', 'NativeWindowHandle') {
    Reset-State
    $edge = [FakeElement]::new($false, $false)
    $candidate = [FakeElement]::new($false, $true); $candidate.Current.Name = 'Save As'
    switch ($alter) {
        'Name' { $candidate.Current.Name = 'Save As copy' }
        'ClassName' { $candidate.Current.ClassName = 'other' }
        'NativeWindowHandle' { $candidate.Current.NativeWindowHandle = 501 }
    }
    Assert-True ($null -eq (Ready-SaveDialog $candidate $edge ([IntPtr]500))) ("unstable " + $alter + " was incorrectly ready")
    $candidate.Current.Name = 'Save As'
    $candidate.Current.ClassName = '#32770'
    $candidate.Current.ProcessId = 42
    $candidate.Current.NativeWindowHandle = 500
    Assert-True ((Ready-SaveDialog $candidate $edge ([IntPtr]500)) -eq $candidate) ("stabilized " + $alter + " did not become ready")
}
# The Save As window can use a different Edge PID from UIA attribution. Native
# HWND ownership plus the executable path, rather than provider PID, is trusted.
Reset-State
$edge = [FakeElement]::new($false, $false)
$candidate = [FakeElement]::new($false, $true); $candidate.Current.Name = 'Save As'; $candidate.Current.ProcessId = 999
Assert-True ((Ready-SaveDialog $candidate $edge ([IntPtr]500)) -eq $candidate) 'separate native Edge process was not accepted'
$script:dialogProcessPath = 'C:\PROGRAM FILES (X86)\MICROSOFT\EDGE\APPLICATION\MSEDGE.EXE'
Assert-True ((Ready-SaveDialog $candidate $edge ([IntPtr]500)) -eq $candidate) 'case-variant matching Edge executable was not accepted'
Assert-True ([ContextPaletteScoreNative]::LastWindowHandle -eq 500) 'native dialog PID lookup used the wrong window handle'
$script:dialogProcessPath = 'C:\other\msedge.exe'
Assert-True ($null -eq (Ready-SaveDialog $candidate $edge ([IntPtr]500))) 'same basename from another directory was incorrectly ready'
$script:dialogProcessPath = $script:edgeExecutable
$script:dialogProcessUnreadable = $true
Assert-True ($null -eq (Ready-SaveDialog $candidate $edge ([IntPtr]500))) 'unreadable dialog process was incorrectly ready'
$script:dialogProcessUnreadable = $false
[ContextPaletteScoreNative]::DialogProcessId = $script:dialogProcessId
$script:dialogProcessPath = $null
Assert-True ($null -eq (Ready-SaveDialog $candidate $edge ([IntPtr]500))) 'null dialog executable was incorrectly ready'
$script:dialogProcessPath = ''
Assert-True ($null -eq (Ready-SaveDialog $candidate $edge ([IntPtr]500))) 'empty dialog executable was incorrectly ready'
$script:dialogProcessPath = 'C:\PROGRAM FILES (X86)\MICROSOFT\EDGE\APPLICATION\MSEDGE.EXE'
$script:edgeExecutable = ''
Assert-True ($null -eq (Ready-SaveDialog $candidate $edge ([IntPtr]500))) 'missing captured Edge executable was incorrectly ready'
$script:edgeExecutable = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
[ContextPaletteScoreNative]::DialogProcessId = 0
Assert-True ($null -eq (Ready-SaveDialog $candidate $edge ([IntPtr]500))) 'zero native dialog PID was incorrectly ready'
[ContextPaletteScoreNative]::DialogProcessId = $script:dialogProcessId
Assert-True ((Ready-SaveDialog $candidate $edge ([IntPtr]500)) -eq $candidate) 'restored native Edge process was not ready'
Reset-State
$edge = [FakeElement]::new($false, $true)
$candidate = [FakeElement]::new($false, $true); $candidate.Current.Name = 'Save As'
Assert-True ($null -eq (Ready-SaveDialog $candidate $edge ([IntPtr]500))) 'enabled source was incorrectly ready'
Reset-State
$edge = [FakeElement]::new($false, $false)
$candidate = [FakeElement]::new($false, $false); $candidate.Current.Name = 'Save As'
Assert-True ($null -eq (Ready-SaveDialog $candidate $edge ([IntPtr]500))) 'disabled candidate was incorrectly ready'

# One-Control reports its own stage-specific missing/ambiguous outcomes.
Reset-State
$parent = [FakeElement]::new($false, $true)
$script:visibleMatches = @()
Expect-Fail 'printer_selector_missing' { One-Control $parent 'ignored' 'printer_selector' | Out-Null }
$script:visibleMatches = @([object]::new(), [object]::new())
Expect-Fail 'printer_selector_ambiguous' { One-Control $parent 'ignored' 'printer_selector' | Out-Null }

'controls-contract-passed'
'''


@unittest.skipUnless(os.name == "nt", "Requires Windows PowerShell and inbox UIA assemblies.")
class EdgeScorePdfControlsTests(unittest.TestCase):
    def test_extracted_print_and_one_control_contracts_without_live_uia(self) -> None:
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("Windows PowerShell is unavailable.")
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", HARNESS],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("controls-contract-passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
