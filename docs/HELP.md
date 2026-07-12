# Context Palette Help

Context Palette is a fast, portable Windows launcher for reusable actions, working contexts, captured material, transformations, and workspace layouts.

Developers can find the current implementation architecture in `docs/ARCHITECTURE.md` and decision history in `docs/DECISIONS.md`.

Multi-PC cloning, GitHub publishing, portable paths, and shared/local data are documented in `docs/MULTI_PC_DEVELOPMENT.md`.

Power Automate Desktop and PowerToys setup is documented in `integrations/README.md`.

## Open and close the palette

- Start once with `run-context-palette.bat`.
- Press `F9` or `Ctrl+Alt+P` to capture the current text selection and show the resident palette. On laptops in media-key mode, use `Fn+F9` or enable Fn Lock.
- The palette opens on the monitor containing the mouse cursor, close to the cursor position at the moment the shortcut was pressed.
- Press `Esc`, click `Hide`, or close the window to hide it.
- Click `Quit` to stop the resident process completely.
- If a development instance becomes stuck, run `stop-context-palette.bat` and start again.

External Windows tools may safely show and pre-filter the existing instance:

```powershell
.\integrations\Invoke-ContextPalette.ps1 -Context "Database" -Search "SQL"
```

This does not execute the highlighted action. Avoid passing secrets or selected text as command-line search values.

## Focus context

Contexts do not have to be created through the UI. Shared definitions live in `data/contexts.json`; private or work-specific definitions live in ignored `data/local_contexts.json`. The complete format and QTP-style recipes are in `docs/CONTEXT_CONFIGURATION.md`.

The Focus context tells Context Palette what kind of work is currently most important. It changes slots 6 through 9 and influences which actions appear first.

Focus and Find are compact one-line controls. Hover over or click their `?` buttons for guidance without permanently consuming screen space.

- Slots `1–5` are personal pinned actions and never change with context.
- Slots `6–9` are the top four actions for the selected focus context.
- An action may appear in both groups.

## Find and run actions

Search matches Technology, Task, Context, Action name, type, and content.

- Type to filter actions.
- Use Up/Down, Page Up/Page Down, Home, and End to navigate.
- Press Enter, double-click, or click `Run selected`.
- Numpad 1 through 9 executes the corresponding fixed slot.
- Number-row 1 through 9 executes slots when focus is not in a text entry field.
- Selecting an action updates the slim communication line at the bottom.

Blue rows are pinned slots 1–5. Green rows are focus-context slots 6–9. Neutral rows are other search results.

## Input / Output workspace

Input / Output is a permanent editable working text box, not an action preview. When the palette opens it shows the current clipboard or captured selection. Actions can read or replace it. Its toolbar is intentionally omitted to save space.

Numbered action triggering is deliberately active only while Find has focus. In every other control—including Clipboard / Input / Output, the result list, context selector, and buttons—`1` through `9` do not execute actions. This makes Find the explicit keyboard command mode. Standard text editing remains available in the workspace.

The bottom communication line always stays one row high. Hover over it for the complete selected-action explanation; click it to open the full message in a selectable information window.

- A text selection captured with `Ctrl+Alt+P` appears here.
- `Ctrl+V` pastes at the cursor; the right-click command `Replace with clipboard` replaces everything.
- Type or edit text directly.
- The right-click command `Clear` empties it.
- The right-click menu also provides Undo, Redo, Cut, Copy, Paste, Select all, and Copy all.
- Transform actions read it and place their result back in it.
- URL-builder actions use it as selected input when it is not empty.

Example: in the Database context, `Convert lines to SQL string list` turns separate lines into quoted, comma-separated SQL values and copies the result.

## Main buttons

### Run selected

Executes the highlighted action. The exact effect appears in the bottom communication line when selected.

### Capture

Copies current clipboard text into the Inbox after asking for a title. Captures are stored locally in `data/inbox.json`.

### Snapshot

Records visible, non-minimized application windows, monitors, relative positions, foreground state, and optional browser launch URLs. It creates a Draft restore action in the current focus context.

### Inbox

Shows captured items. An item can be converted into a structured Draft action with Technology, Task, Context, Action name, and a guided action type.

For a URL built from selected or copied text, choose **Build URL — copy and open using selection/clipboard** and use a template such as:

```text
http://linkto/archives/{id_url}
```

`{id_url}` is replaced with URL-encoded text from Input / Output, the captured selection, or the clipboard. The creator displays a live example before saving. Copy-only and open-only variants can instead ask for input when run.

### Sheets

Opens searchable local cheat sheets. Individual cheat-sheet entries can be promoted to Draft actions.

### Edit

Edits the selected Draft copy-text action. Other action types remain read-only until type-specific editors are added.

### Pin

Adds the selected action to the next free pinned slot from 1 to 5. If already pinned, it removes the pin. When all five slots are occupied, unpin another action first.

### Trust

Promotes a Draft action to Trusted after confirmation. Trusted means the action has been manually reviewed and tested.

### Help

Opens this document inside Context Palette.

### Hide

Hides the palette but keeps it resident. Reopen with `Ctrl+Alt+P`.

### Quit

Stops Context Palette completely and releases the global hotkey.

## Action naming

Actions use four separate searchable fields:

```text
Technology > Task > Context > Action name
```

Example:

```text
Browser > Product lookup > Colruyt > Open selected product ID
```

To keep the launcher fast to scan, result rows show only `Action name · Context`. Technology and Task remain fully searchable and appear in the bottom communication line.

## Window layouts and snapshots

Configured `window_layout` actions can open Explorer folders and position them across detected screens. Relative coordinates allow layouts to adapt to screen resolution.

`Snapshot` captures an existing window situation. Restore first matches open windows by executable, native window class, and title. Missing ordinary desktop applications are started when possible. Explicit browser launch URLs reopen missing browser windows. Exact unsaved document state and browser history cannot be reconstructed generically.

## Action maturity

- Inbox: captured but not yet structured.
- Draft: editable and still being tested.
- Trusted: manually reviewed and accepted.
- Archived: hidden from normal launcher results.

## Local data

- `data/actions.json`: reviewed actions shared through Git.
- `data/local_actions.json`: ignored personal and machine-specific actions.
- `data/inbox.json`: ignored captures.
- `data/palette.json`: ignored per-machine focus context, pins, and context slots.
- `data/cheatsheets`: local cheat sheets.
- `data/layouts`: configured layouts and captured snapshots.

## Safety boundaries

Context Palette uses constrained action types. It does not execute arbitrary shell command strings. Draft actions should be previewed and tested before they are marked Trusted. Browser URLs and application paths remain visible in local files.

## Troubleshooting

### New features are reported as unsupported

A previous resident process is still running. Run `stop-context-palette.bat`, then start `run-context-palette.bat` again.

### Ctrl+Alt+P does not reopen the palette

Another application may own the shortcut. Quit duplicate instances and restart Context Palette.

### Selected text was not captured

Some applications block simulated copy operations. Copy manually, open Context Palette, then press `Ctrl+V` or use the text box's right-click menu.

### Snapshot restore cannot restore everything

Packaged/protected applications may not restart from an executable path. Browser windows need an explicit saved URL to reopen the correct page. Unsaved documents cannot be recreated automatically.
