# Windows automation integrations

Context Palette exposes a small, safe command-line surface for Power Automate Desktop and PowerToys. It only shows and filters the palette; it cannot execute arbitrary commands or silently run an action.

## Stable commands

From the repository root:

```powershell
.\run-context-palette.bat
.\integrations\Invoke-ContextPalette.ps1 -Search "SQL template"
.\integrations\Invoke-ContextPalette.ps1 -Context "Database"
.\integrations\Invoke-ContextPalette.ps1 -Context "Database" -Search "SQL template"
```

The first call starts the resident app. Wrapper calls send a structured request over localhost to that same instance. Context matching is case-insensitive. An unknown context shows the palette and reports a status message without changing context.

For automation tools that work better with PowerShell, use:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\context-palette\integrations\Invoke-ContextPalette.ps1" -Context "Database" -Search "SQL"
```

Use the actual clone path on each PC. Do not pass selected text, secrets, or tokens as search values. Selection continues to use the normal `Ctrl+Alt+P` clipboard capture flow.

## Power Automate Desktop

Create a desktop flow with **Run application**:

- Application path: `powershell.exe`
- Arguments: `-NoProfile -ExecutionPolicy Bypass -File "<clone>\integrations\Invoke-ContextPalette.ps1" -Context "%ContextName%" -Search "%SearchText%"`
- Working folder: the repository root
- Window style: Hidden

Start with fixed or validated `ContextName` and `SearchText` variables. The wrapper preserves argument boundaries, including spaces. Power Automate can then wait for the Context Palette window and leave final action selection to the user.

Recommended first flows:

1. Show Context Palette in the `Tijdsregistratie` context.
2. Show and search for `Open agenda`.
3. At the end of an existing flow, show a context-specific set of follow-up actions.

Do not automate clicks by row position: search results and numbered context slots can change. A future explicit action-ID API should require Trusted state, confirmation policy, result reporting, and tests before unattended execution is enabled.

## PowerToys Keyboard Manager

Context Palette already owns `Ctrl+Alt+P`. Use Keyboard Manager only to map another convenient shortcut to `Ctrl+Alt+P`; this preserves selected-text capture. Avoid assigning the same shortcut in both products.

Keyboard Manager cannot reliably launch a batch file directly in every version. When a launch target is needed, create a normal Windows shortcut to `run-context-palette.bat`, give that shortcut a Windows shortcut key, and remap to it. Keep `Ctrl+Alt+P` as the canonical app hotkey.

## PowerToys Workspaces

Add Context Palette to a PowerToys Workspace by selecting the running app, or configure the workspace to start `run-context-palette.bat`. Context Palette itself should normally remain resident and does not need a fixed large window position.

Use Context Palette's own `window_layout` and snapshot actions for task-specific layouts. PowerToys Workspaces is best for a broad machine workspace; Context Palette is best for context-specific opening, filtering, and later restoration.

## PowerToys Run plug-in boundary

A native PowerToys Run plug-in would require a separately built and version-matched .NET component. It is intentionally not a dependency of the portable Tkinter app. If later justified, the plug-in should be a thin optional adapter that calls this constrained bridge and is packaged independently.

## Manual integration check

1. Start Context Palette normally.
2. Run `integrations\Invoke-ContextPalette.ps1 -Context "General" -Search "date"`.
3. Confirm the existing instance appears, `General` is focused, and search contains `date`.
4. Run it with a nonexistent context and confirm no context changes and a status message appears.
5. Map a spare PowerToys shortcut to `Ctrl+Alt+P` and confirm selected text still reaches Input / Output.

## Working examples

- `examples/power-automate`: a directly runnable Tijdsregistratie PAD target.
- `examples/powertoys-keyboard-manager`: selection-preserving remap and Start App examples.
- `examples/powertoys-workspaces`: a dummy Tijdsregistratie workspace with browser and optional Outlook.
- `examples/Test-IntegrationExamples.ps1`: syntax-checks every example without opening applications.
