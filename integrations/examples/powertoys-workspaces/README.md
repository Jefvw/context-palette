# PowerToys Workspaces example

## Prepare the example workspace

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\integrations\examples\powertoys-workspaces\Start-TijdsregistratieWorkspace.ps1"
```

This starts:

- Context Palette focused on `Tijdsregistratie`;
- the public dummy Colruyt page in the default browser;
- classic Outlook when its executable is found.

The example deliberately contains no private work URLs or OneNote identifiers.

## Capture it in PowerToys

1. Arrange the opened windows as desired.
2. Open PowerToys Workspaces Editor.
3. Select **Create workspace** and capture the desktop.
4. Keep the browser and Outlook entries.
5. For Context Palette, use this launch configuration if Workspaces cannot identify the Python window reliably:
   - App: `powershell.exe`
   - Arguments: `-NoProfile -ExecutionPolicy Bypass -File "<clone>\integrations\examples\powertoys-workspaces\Start-TijdsregistratieWorkspace.ps1" -SkipCompanionWindows`
   - Start in: repository root
6. Save as `Tijdsregistratie example` and launch it from Workspaces.

`-SkipCompanionWindows` prevents the Context Palette entry from opening duplicate browser and Outlook windows when PowerToys already owns those entries.

Expected result: PowerToys restores the companion windows while Context Palette opens in the correct focus context.
