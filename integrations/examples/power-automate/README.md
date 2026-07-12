# Power Automate Desktop example

## Direct working example

Run from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\integrations\examples\power-automate\Show-Tijdsregistratie.ps1"
```

It shows the resident Context Palette, selects `Tijdsregistratie`, searches for `agenda`, and returns a small result object.

## Create the desktop flow

Add **Run PowerShell script** and paste:

```powershell
& "C:\path\to\context-palette\integrations\Invoke-ContextPalette.ps1" `
    -Context "Tijdsregistratie" `
    -Search "agenda"
```

Alternatively, use **Run application**:

- Application: `powershell.exe`
- Arguments: `-NoProfile -ExecutionPolicy Bypass -File "C:\path\to\context-palette\integrations\examples\power-automate\Show-Tijdsregistratie.ps1"`
- Working folder: the repository root
- Window style: Hidden

Expected result: Context Palette appears with the requested context and filter. The flow does not execute an action automatically.
