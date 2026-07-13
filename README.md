# Context Palette

Context Palette is a portable Windows productivity tool for building and using reusable contexts and actions.

Technical implementation and module boundaries are documented in `docs\ARCHITECTURE.md`. Chronological rationale for important choices is recorded in `docs\DECISIONS.md`.

For cloning, setup, safe GitHub publishing, shared versus local data, and AI-assisted development on multiple PCs, see `docs\MULTI_PC_DEVELOPMENT.md`.

For Power Automate Desktop and PowerToys integration, see `integrations\README.md`.

Contexts can be configured outside the UI. See `docs\CONTEXT_CONFIGURATION.md` for shared/local JSON, preferred slots, and QTP-style recipes.

The project is intentionally small at this stage. The current focus is to build the first local prototype without requiring administrator rights, installers, services, registry changes, AutoHotkey, or external services.

## Current status

The project has a first launcher prototype.

It can:

- open a small launcher window;
- stay resident so later opens are fast;
- open with one-key `F9`, with `Ctrl+Alt+P` retained as fallback;
- use a compact search-first palette layout;
- search sample actions;
- show selected-action guidance in a stable information area;
- provide a persistent editable Clipboard / Input / Output workspace for selected, pasted, typed, and transformed text;
- copy saved text actions to the clipboard;
- open safe URL, file, folder, or explicitly configured application targets;
- capture clipboard text into a local Inbox;
- view captured Inbox items;
- convert an Inbox item into a draft copy-text action;
- edit draft copy-text actions;
- mark draft actions as Trusted;
- view app/topic cheat sheets in a popup;
- load actions from a local JSON file.
- expand dynamic clipboard and date/time variables in text, URLs, and app targets.
- capture selected text and use it to build a URL that is copied and opened.
- keep five global actions pinned to number slots 1-5.
- assign number slots 6-9 to the top four actions for the selected focus context.
- search action technology, task, context, title, type, and value.
- detect connected Windows screens and apply constrained window layouts.
- open complete searchable local help from the app and explain main buttons with hover tooltips.
- accept safe external show, context, and search requests from Windows automation tools.
- load standalone shared and local context definitions with preconfigured slots 6–9.

## Development environment

This project currently uses a local virtual environment stored in `.venv`.

On a new Windows computer, run:

```text
setup-context-palette.bat
```

It creates the local environment and private runtime files from safe examples, verifies Tkinter, and runs the tests.

On this machine, Python 3.12 is installed under the user's profile. A nearby Codex project that already uses Tkinter was checked, and it uses Codex's bundled Python runtime as the base for its `.venv`.

This project follows that same working pattern so Tkinter is available.

Verified:

```powershell
.\.venv\Scripts\python.exe --version
```

Expected output:

```text
Python 3.12.13
```

Tkinter is available:

```powershell
.\.venv\Scripts\python.exe -c "import tkinter; print(tkinter.TkVersion)"
```

Expected output:

```text
8.6
```

## How to run project commands

Run commands from this folder:

```powershell
C:\path\to\context-palette
```

For now, use the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe
```

PowerShell activation is optional. Directly running `.\.venv\Scripts\python.exe` avoids problems on machines where script execution is restricted.

## Run the launcher

Required:

```powershell
.\run-context-palette.bat
```

Expected result:

- a small window titled `Context Palette` opens;
- the search box is focused;
- sample actions appear in the list.

You can also double-click `run-context-palette.bat` in File Explorer.

The first launch starts the app. After that, `Ctrl+Alt+P` is handled by the resident app itself and shows the hidden window without starting the batch file again.

The main window also behaves like a temporary context palette: when it loses focus because you click into another app, it hides itself.

If `Ctrl+Alt+P` cannot be registered, auto-hide is disabled so the app does not disappear without a way to bring it back.

The batch file starts the GUI in a detached `pythonw.exe` process, so the black command window should close immediately.

During development, if old hidden instances get stuck, run:

```powershell
.\stop-context-palette.bat
```

Then start Context Palette again.

You can optionally create a per-PC Desktop shortcut to `run-context-palette.bat`. Shortcut files are ignored by Git because their target paths are machine-specific. Use that shortcut, the batch file, or a taskbar pin to start Context Palette the first time.

After Context Palette is running, the app itself handles this hotkey:

```text
Ctrl+Alt+P
```

If Windows allows it, pin your locally created shortcut to the taskbar.

## Use the launcher

1. Type in the search box, for example `email` or `select`.
2. Select an action in the list.
3. Press `Enter`, double-click the action, or click `Run`.

Keyboard controls:

- `Up` / `Down`: move through the matching actions.
- `Page Up` / `Page Down`: move faster through the matching actions.
- `Home` / `End`: jump to the first or last matching action.
- `Enter`: run the selected action.
- `Esc`: hide the palette.
- `Ctrl+L`: focus the search box.
- `Ctrl+I`: capture the current clipboard text into the Inbox.
- Numpad `1` through `9`: run the matching action with that visible slot number.
- Keyboard-row `1` through `9`: run the matching action in that visible slot when the search box is not focused.

### Focus context and numbered slots

Choose a focus context above the search field. The numbered slots have stable meanings:

- `1` through `5`: globally pinned actions, independent of the focus context.
- `6` through `9`: the top four actions configured or selected for the focus context.

An action may deliberately appear in both groups. Use `Pin / Unpin` on the selected action to manage the five global pins. Pins, focus context, and optional explicit context slots are stored in `data\palette.json`.

Action names can include `technology` and `task` metadata in addition to context and title. All these fields participate in search.

For copy-text actions, the saved text is copied to the clipboard.

For URL, file, folder, and application actions, Windows opens the configured target.

### Dynamic text variables

Actions can include QuickTextPaste-style variables. They are resolved when the preview is shown and again when the action runs.

- `%CLIPBOARD%` or `%pptxt%`: current clipboard text.
- `%CLIPBOARD_URL%` or `%cpy_txt_urlencode%`: current clipboard text encoded for use in a URL.
- `%YYYY%`, `%YY%`, `%MMMM%`, `%MMM%`, `%MM%`, `%M%`: year and month values.
- `%DDDD%`, `%DDD%`, `%DD%`, `%D%`: weekday/day values.
- `%hh%`, `%mm%`, `%ss%`: time values.
- `%LDF%`, `%LTF%`: local date and time.
- `%CW%`, `%CWL%`: calendar week.
- `\n`: line break.

For example, an `open_url` action with `https://translate.google.com/?text=%cpy_txt_urlencode%` opens Google Translate with the current clipboard text.

Direct paste into the previously active application, Tab/Enter sequences, clipboard slots, and the character menu are planned QTP-compatibility layers; they are not active yet.

### Build a URL from selected text

The `build_url_selection_open` action supports the frequent ID-to-URL workflow:

1. Select an ID in another application.
2. Press `Ctrl+Alt+P`.
3. Run the URL-builder action.
4. The complete URL is copied to the clipboard and opened in the browser.

Use `{id}` in the URL template to insert the ID literally, or `{id_url}` to URL-encode it. For example:

```json
{
  "id": "open-work-item",
  "title": "Open work item",
  "context": "Work",
  "type": "build_url_selection_open",
  "value": "https://example.com/items/{id_url}",
  "state": "Draft"
}
```

Selecting `ABC 12` before opening Context Palette builds `https://example.com/items/ABC%2012`.

Selecting an action updates the slim communication line at the bottom with its searchable path and expected effect. Results, warnings, and errors use that same predictable line.

The line remains one row high. Hovering shows the full explanation, while clicking opens selectable details. Numbered action triggering works only while Find has focus and is disabled everywhere else.

### Input / Output workspace

The field below the results is working data rather than an action preview:

- Text selected before `Ctrl+Alt+P` is captured into the field.
- `Ctrl+V` pastes normally; right-click `Replace with clipboard` replaces the complete field.
- Text can be typed or edited directly.
- Transform actions read the field and replace it with their result.
- Transformation results are also copied to the clipboard.
- Right-click `Clear` empties the field; the same menu exposes the standard editing commands.

For example, choose the `Database` focus context and run `Convert lines to SQL string list` on:

```text
alpha
beta
O'Brien
```

The Input / Output field and clipboard become:

```text
'alpha', 'beta', 'O''Brien'
```

Copy-only actions do not replace Input / Output. URL actions can consume the field as their selected input. Directly pasting transformed output back into the previously active application remains a separate future action behaviour.

### Window layouts

The `window_layout` action type detects connected screens, opens configured Explorer folders, and places their windows using relative monitor coordinates. Layouts are inspectable JSON files under `data\layouts`.

The included `data\layouts\three-explorers.json` example is available in the `Developing Context Palette` focus context as `Arrange three Explorer windows`:

- With two or more screens, the project folder fills screen 1; `data` and `docs` use the top and bottom halves of screen 2.
- With one screen, project, `data`, and `docs` use three columns.

The communication line reports the currently detected screen count before execution. Monitor index `0` is the primary screen.

### Capture and restore a window snapshot

Arrange your open application windows, choose the appropriate focus context, and click `Snapshot`. Give the situation a name. Context Palette stores ordinary visible, non-minimized application windows with their executable, title, class, screen, relative position, and whether the window was foreground under `data\layouts\snapshots`.

For each detected browser window, Snapshot asks for an optional launch URL. Windows does not expose normal browser-tab URLs through the ordinary window API, so explicit confirmation is more reliable and does not disturb the browser or clipboard. Saved URLs are used when a missing browser window must be reopened.

It also creates a Draft action in the focus context:

```text
Windows / Win32 > Restore workspace > Context > Restore snapshot name
```

Running that action first repositions matching open windows. Missing ordinary desktop applications are started from their captured executable and then positioned. Browsers reopen as new windows, but their exact previous URLs/tabs cannot be reconstructed from a Windows title snapshot alone. Unrestorable packaged or protected applications are reported.

Closing the main window hides Context Palette instead of quitting it. Clicking outside the window also hides it. Use `Hide` to hide it deliberately, or `Quit` to fully stop the resident app.

If the status line says `Ctrl+Alt+P is unavailable`, the app will stay visible when it loses focus. In that case another shortcut or app is probably still using `Ctrl+Alt+P`.

## Capture to Inbox

1. Copy useful text from any application.
2. Open Context Palette.
3. Click `Capture`, or press `Ctrl+I`.
4. Enter a short title.
5. The capture is saved to:

```text
data\inbox.json
```

This is the first capture step only. Converting an Inbox item into a draft action comes later.

Click `Inbox` to view captured items and preview their content.

In the Inbox popup, select an item and click `Convert to Draft Action`. The structured form asks for Technology, Task, Context, and Action name, and lets you review the captured content. Context defaults to the current focus context. Existing metadata values are offered as editable suggestions. A live `Displayed as` line shows the complete searchable action name before saving. The first form version creates a draft `copy_text` action and reloads the launcher immediately.

## Edit a Draft Action

1. Search for a draft copy-text action.
2. Select it.
3. Click `Edit Draft`.
4. Update the title, context, or text.
5. Click `Save`.

Only draft copy-text actions can be edited right now. Other action types are deliberately read-only until the editor grows safely.

## Mark a Draft Trusted

1. Search for a draft action.
2. Select it.
3. Click `Mark Trusted`.
4. Confirm the prompt.

The action remains searchable, but its state changes from `Draft` to `Trusted`.

## Cheat Sheets

Click `Sheets` to open reviewed app/topic cheat sheets in a popup.

Use the search box inside the cheat-sheet popup to filter the selected sheet. For the Windows 11 sheet, useful searches include `clipboard`, `snap`, `wsl`, `task manager`, and `network`.

Select a cheat-sheet item and click `Promote to Draft` to create a draft copy-text action from it. The new action appears in launcher search and can be edited or marked trusted.

The incorporated sheets include:

```text
data\cheatsheets\win11.json
data\cheatsheets\company-references.json
```

The company-reference sheet makes Archive and ServiceNow prefixes searchable. Product URL builders are grouped in the `Product lookup` focus context; select or copy an ID and run one destination-specific action to copy and open its URL.

## Data storage

The prototype reads actions from:

```text
data\actions.json
```

The prototype writes captures to:

```text
data\inbox.json
```

These files are plain JSON so they can be inspected and backed up easily. Editing is still manual for now; the action editor comes later.

Proposed app/topic cheat-sheet files are documented in:

```text
docs\CHEATSHEET_FORMAT.md
```

## Dependencies

There are currently no third-party Python dependencies.

The local environment currently does not include `pip`. This is acceptable for the first launcher prototype because it can use Python's standard library and Tkinter.

## Help

Click `Help` in the main palette to open the complete searchable local guide. The source document is `docs\HELP.md` and can also be read directly in a text editor. Hover over a main button briefly to see its documented input, effect, and important limitation.

## Run tests

Required:

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

Expected output includes:

```text
Ran 17 tests
OK
```

## Manual test

1. Run `.\run-context-palette.bat`.
2. Search for `email`.
3. Run `Email > Copy professional greeting`.
4. Paste into Notepad or another text field.
5. Confirm the greeting text appears.
6. Search for `python`.
7. Run `General > Open Python documentation`.
8. Confirm the Python documentation opens in your browser.
9. Search for `developing`.
10. Run `Developing Context Palette > Open Context Palette in VS Code`.
11. Confirm VS Code opens this project folder.
12. Reopen the launcher and search for `email`.
13. Confirm the first nine results show visible numbers.
14. Use `Down` to move through results.
15. Confirm the preview changes as the selection changes.
16. Press numpad `1`.
17. Confirm the first visible result runs.
18. Copy a short sentence from another app.
19. Click `Capture`, or press `Ctrl+I`.
20. Give it a title.
21. Confirm `data\inbox.json` contains the captured text.
22. Click `Inbox`.
23. Confirm the captured item appears with a preview.
24. Click `Convert to Draft Action`.
25. Enter `General` as the context.
26. Search for the new draft action title in the launcher.
27. Confirm it appears and its preview shows the captured text.
28. Click `Edit Draft`.
29. Change the text and click `Save`.
30. Confirm the launcher preview shows the updated text.
31. Click `Mark Trusted`.
32. Confirm the prompt.
33. Click `Sheets`.
34. Confirm the Windows 11 cheat sheet opens in a popup.
35. Search inside the cheat-sheet popup for `clipboard`.
36. Confirm only matching cheat-sheet items are shown.
37. Select `Clipboard history` and click `Promote to Draft`.
38. Search for `Clipboard history` in the launcher.
39. Confirm the new draft action appears.
40. Click outside the main Context Palette window.
41. Confirm it hides.
42. Press `Ctrl+Alt+P`.
43. Confirm the existing app reappears quickly.
44. Confirm no batch/command window opens.
45. Click `Quit` when you want to fully stop it.
46. If duplicate hidden instances seem stuck during development, run `.\stop-context-palette.bat` and start again.
