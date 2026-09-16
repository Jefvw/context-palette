"""Contract tests for the narrow Ultimate Guitar page identities.

The PowerShell portion extracts only pure helpers from the companion script;
it does not load UI Automation or inspect a browser window.
"""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import unittest

from context_palette.edge_score_pdf import EdgeScorePdfError, _validate_ultimate_guitar_url


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_URL = "https://tabs.ultimate-guitar.com/tab/radiohead/there-there-official-2463302"
GUITAR_PRO_URL = "https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257"


PAGE_HELPER_HARNESS = rf'''
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $pwd 'src\context_palette\edge_score_pdf.ps1'),
    [ref]$tokens,
    [ref]$errors
)
if ($errors.Count) {{ throw ($errors | Out-String) }}
foreach ($name in 'Score-Url', 'Score-DocumentTitle') {{
    $definition = $ast.FindAll({{ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }}, $true)
    if ($definition.Count -ne 1) {{ throw "Expected one $name definition." }}
    Invoke-Expression @($definition)[0].Extent.Text
}}
function Fail([string]$code) {{ throw "FAIL:$code" }}
function Assert-Equal($actual, $expected, [string]$message) {{
    if ($actual -cne $expected) {{ throw "ASSERT:$message; expected '$expected', got '$actual'" }}
}}
function Assert-True([bool]$condition, [string]$message) {{
    if (-not $condition) {{ throw "ASSERT:$message" }}
}}
function Expect-Unsupported([string]$value) {{
    try {{ Score-Url $value | Out-Null; throw "ASSERT:accepted $value" }}
    catch {{ if ($_.Exception.Message -ne 'FAIL:unsupported_page') {{ throw }} }}
}}

$official = '{OFFICIAL_URL}'
$guitarPro = '{GUITAR_PRO_URL}'
Assert-Equal (Score-Url $official) $official 'Official URL did not round-trip'
Assert-Equal (Score-Url $guitarPro) $guitarPro 'observed Guitar Pro URL did not round-trip'
foreach ($value in @(
    'http://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257',
    'https://www.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257',
    'https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-2369257',
    'https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-chords-2369257',
    'https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257?foo=bar',
    'https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257?',
    'https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257#part',
    'https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257#',
    'https://user@tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257',
    'https://tabs.ultimate-guitar.com:443/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257'
)) {{ Expect-Unsupported $value }}
foreach ($suffix in @([char]9, [char]10, [char]13)) {{ Expect-Unsupported ($guitarPro + $suffix) }}

Assert-Equal (Score-DocumentTitle '(1) DONT CRY SISTER TAB by J.J. Cale @ Ultimate-Guitar.Com' $guitarPro) 'J.J. Cale - DONT CRY SISTER' 'Guitar Pro title was not normalized'
Assert-Equal (Score-DocumentTitle 'DONT CRY SISTER TAB by J.J. Cale @ Ultimate-Guitar.Com' $guitarPro) 'J.J. Cale - DONT CRY SISTER' 'Guitar Pro title without a counter was not accepted'
Assert-Equal (Score-DocumentTitle '  (2)  DONT   CRY SISTER  TAB by  J.J.   Cale  @ Ultimate-Guitar.Com  ' $guitarPro) 'J.J. Cale - DONT CRY SISTER' 'Guitar Pro counter/whitespace was not normalized'
Assert-Equal (Score-DocumentTitle '(1) OFFICIAL THERE THERE CHORDS & TABS by RADIOHEAD @ Ultimate-Guitar.Com' $official) 'RADIOHEAD - THERE THERE' 'Official title regressed'
Assert-True ($null -eq (Score-DocumentTitle 'DONT CRY SISTER CHORDS by J.J. Cale @ Ultimate-Guitar.Com' $guitarPro)) 'mismatched Guitar Pro title was accepted'
Assert-True ($null -eq (Score-DocumentTitle 'OFFICIAL THERE THERE CHORDS & TABS by RADIOHEAD @ Ultimate-Guitar.Com' $guitarPro)) 'Official title was accepted for a Guitar Pro URL'
Assert-True ($null -eq (Score-DocumentTitle 'DONT CRY SISTER TAB by J.J. Cale @ Ultimate-Guitar.Com' $official)) 'Guitar Pro title was accepted for an Official URL'
$long = ('A' * 140) + ' TAB by ' + ('B' * 140) + ' @ Ultimate-Guitar.Com'
$longTitle = Score-DocumentTitle $long $guitarPro
Assert-True ($longTitle.Length -le 200) 'normalized title is not bounded'
Assert-True ($longTitle -match '^B+ - A+') 'long title lost artist-song order'
'edge-score-page-contract-passed'
'''


class EdgeScorePdfPageTests(unittest.TestCase):
    def test_python_url_validator_accepts_only_supported_score_kinds(self) -> None:
        for value in (OFFICIAL_URL, GUITAR_PRO_URL):
            with self.subTest(value=value):
                _validate_ultimate_guitar_url(value)
        for value in (
            "http://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257",
            "https://www.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257",
            "https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-2369257",
            "https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-chords-2369257",
            f"{GUITAR_PRO_URL}?foo=bar",
            f"{GUITAR_PRO_URL}?",
            f"{GUITAR_PRO_URL}#part",
            f"{GUITAR_PRO_URL}#",
            "https://user@tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257",
            "https://tabs.ultimate-guitar.com:443/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257",
            f"{GUITAR_PRO_URL}\t",
            f"{GUITAR_PRO_URL}\n",
            f"{GUITAR_PRO_URL}\r",
        ):
            with self.subTest(value=value):
                with self.assertRaises(EdgeScorePdfError):
                    _validate_ultimate_guitar_url(value)

    @unittest.skipUnless(os.name == "nt", "Requires Windows PowerShell.")
    def test_powershell_page_helpers_match_the_supported_page_contract(self) -> None:
        powershell = shutil.which("powershell.exe")
        if powershell is None:
            self.skipTest("Windows PowerShell is unavailable.")
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", PAGE_HELPER_HARNESS],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("edge-score-page-contract-passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
