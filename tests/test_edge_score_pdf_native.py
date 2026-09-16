"""Compile the Windows-only companion without invoking any UI or native method."""
from pathlib import Path
import os
import shutil
import subprocess
import unittest


@unittest.skipUnless(os.name == "nt", "Requires Windows PowerShell and inbox UIA assemblies.")
class EdgeScoreNativeCompilationTests(unittest.TestCase):
    def test_powershell_syntax_and_native_compilation(self):
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("Windows PowerShell is unavailable.")
        root = Path(__file__).resolve().parents[1]
        script = r"""
$ErrorActionPreference = 'Stop'
$parseTokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $pwd 'src\context_palette\edge_score_pdf.ps1'),
    [ref]$parseTokens, [ref]$parseErrors
)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName WindowsBase
$references = @(
    [System.Windows.Automation.AutomationElement].Assembly.Location,
    [System.Windows.Automation.ControlType].Assembly.Location,
    [System.Windows.Rect].Assembly.Location
) | Select-Object -Unique
Add-Type -Path (Join-Path $pwd 'src\context_palette\edge_score_pdf_native.cs') -ReferencedAssemblies $references
'compiled-without-ui-invocation'
"""
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            cwd=root, capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("compiled-without-ui-invocation", result.stdout)
