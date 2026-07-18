# Context Palette Architecture

This document describes the current implemented architecture. It is the technical source of truth for how the application is structured today.

Use related documents for other purposes:

- `PRODUCT_VISION.md`: durable product direction.
- `MVP.md`: agreed minimum product scope.
- `DECISIONS.md`: chronological technical and product decisions with rationale.
- `HELP.md`: user-facing operation and troubleshooting.
- `BACKLOG.md`: planned work.

## Architectural goals

Context Palette is optimized for:

1. Fast resident use through `F9`, with `Ctrl+Alt+P` as a fallback.
2. Portable operation from a user-writable Windows folder.
3. No administrator requirement, installer, service, registry modification, or mandatory AutoHotkey.
4. Inspectable local JSON and Markdown data.
5. Constrained action types instead of arbitrary command execution.
6. Incremental context authoring through Inbox, Draft, Trusted, and Archived states.
7. Standard-library implementation where practical.

## Runtime overview

```text
run-context-palette.bat
        |
        v
pythonw.exe -> context_palette.main
        |
        +-- parse constrained show/context/search integration arguments
        +-- notify existing instance and exit
        |
        `-- create Tk root and LauncherApp
                |
                +-- load actions, contexts, command surface, palette state, Inbox, and cheat sheets
                +-- start localhost single-instance listener
                +-- register F9 and Ctrl+Alt+P on a background message thread
                `-- run the Tk main loop
```

The first process remains resident. Later launches notify it through a project-specific localhost port and exit. This avoids repeated Python and Tk startup cost.

A bare first process displays its already-created root window without replaying a synthetic `show` request. This keeps Input / Output empty on application startup. First launches carrying an explicit integration context or search term still process those parameters.

## Source modules

### `main.py`

Application entry point.

- Resolves the project root.
- Derives a stable project-specific local port.
- Notifies an existing instance when one is running.
- Starts the Tk launcher with paths to local data.

### `launcher.py`

Presentation and application orchestration.

- Builds the Tkinter interface.
- Maintains the active focus context.
- Renders numbered slots and search results.
- Renders a global JSON-configured quick-action surface beside search results.
- Owns Input / Output, the communication line, systematic widget tooltips, Inbox, sheets, Help, and action editors.
- Connects platform-independent action execution to Windows-specific callbacks.
- Ensures Tk operations stay on the Tk main thread.

The main-window construction is divided into focused header, results/command-surface, shortcut, workspace, and footer builders. Inbox, Draft, and Cheat Sheet windows still live in this module and are the next safe extraction boundary; this is documented in `TECHNICAL_REVIEW.md`.

The launcher does not implement action transformations or window matching directly. Those responsibilities live in specialized modules.

### `actions.py`

Action domain model, persistence, validation, search, transformation, and dispatch.

Important principles:

- Each action type is explicitly allow-listed.
- JSON is validated when loaded.
- Arbitrary shell commands are rejected.
- Pure transformations are separated from UI callbacks.
- Platform effects are injected through callbacks where practical, enabling tests without opening applications.
- Clipboard access during template expansion is lazy: actions without clipboard variables do not fail when the clipboard contains a non-text format.

### `action_types.py`

Defines the machine-readable catalogue for every supported action type: user label, family, description, required fields, input/output effects, portability, AI eligibility, and type-specific AI guidance. `actions.py` derives its supported-type set from this catalogue, and AI prompt generation consumes the same definitions.

The catalogue renders `docs/ACTION_TYPES.md`; an automated test requires the user-readable overview to remain identical to the executable definitions.

### `persistence.py`

Owns JSON replacement for application-written data. It serializes to a temporary sibling file, flushes it to disk, preserves the previous destination as `<name>.bak`, and uses `os.replace` so readers see either the previous complete file or the new complete file. Temporary and backup files are ignored by Git because they can contain private runtime data.

Actions, Inbox state, palette state, captured snapshots, and snapshot launch-target edits use this single writer.

### `configuration_check.py`

Provides a read-only project validation report and command-line exit status. It reuses the existing action, context, command-surface, Inbox, palette, cheat-sheet, and window-layout loaders, then verifies that context, command-surface, and palette action references resolve. `check-context-palette.bat` runs this validation before source compilation and the complete unit suite.

### `configuration_window.py` and `configuration_data.py`

Provide the guided personal-configuration workspace and its persistence operations. Action creation starts from the executable built-in action catalogue, which includes a concrete example for every type. All personal action types are editable. Personal contexts can assign slots 6–9, and personal right-side buttons can reference existing actions without exposing technical IDs. Shared records are visible but read-only. Writes use the same atomic JSON replacement path as the rest of the application.

### `palette_state.py`

Stores and calculates launcher organization.

- Slots 1–5: persistent global pins.
- Slots 6–9: top four actions for the focus context.
- Duplicate actions across both groups are intentional.
- Missing context slots fall back to useful General/available actions.

### `command_surface.py`

Loads and validates global quick-action groups and their compact items from shared and local JSON. Each item has an individual action menu and retains its source configuration path. Groups reference existing action IDs; they do not define a second execution language. Duplicate group IDs and duplicate item IDs within a group are rejected case-insensitively.

### `tooltips.py`

Owns delayed tooltip behaviour for ordinary widgets and individual listbox rows. Keeping these presentation helpers outside `launcher.py` prevents the main application orchestrator from also owning reusable hover-window mechanics.

### `style.py`

Owns the shared native ttk theme, Segoe UI font policy, grey/teal/aqua palette, and hover/focus state maps. Classic Tk widget defaults are applied through the root option database. The module changes presentation only; widget construction, layout, geometry, and action behaviour remain in their existing owners.

### `help_window.py`

Owns construction and in-document search for the searchable Help window. `launcher.py` retains orchestration responsibility and opens this focused secondary view with the project Help path.

### `hotkeys.py`

Native Windows hotkey and selection-copy support using `ctypes`.

- Registers one-key `F9` and fallback `Ctrl+Alt+P` with `RegisterHotKey` and no-repeat behaviour.
- Runs the Windows message loop on a daemon thread.
- Queues activation back to `LauncherApp`; it does not manipulate Tk widgets from the background thread.
- Sends a constrained `Ctrl+C` sequence before the palette takes focus.
- Captures cursor coordinates and the nearest monitor work area in the hotkey thread, then uses the cursor as the palette's top-left anchor. The position is clamped only when needed to keep the complete window on-screen.

### `contexts.py`

Loads and validates standalone shared and local context definitions. A definition provides identity metadata and up to four preferred action IDs. Explicit per-machine choices in `palette.json` override configured defaults.

### `single_instance.py`

Resident-process coordination through a localhost socket.

- Only the first process owns the port.
- Later processes send a show request and terminate.
- Requests may carry only `command`, `context`, and `search` string fields in size-limited JSON.
- Invalid commands and fields are ignored; the bridge cannot execute actions or shell commands.
- The port is derived from the project path to reduce collisions between workspaces.

### Windows integration boundary

`main.py` accepts optional `--context` and `--search` arguments. `integrations/Invoke-ContextPalette.ps1` provides the parameterized wrapper for Power Automate Desktop; the ordinary batch launcher remains argumentless.

PowerToys Keyboard Manager can remap a shortcut to the canonical `Ctrl+Alt+P` hotkey, preserving selection capture. PowerToys Workspaces can start the ordinary launcher. A native PowerToys Run plug-in remains separate because it would introduce a version-specific .NET build and packaging surface.

The bridge is attended by design: it may reveal and filter the palette but cannot run an action by ID. Any future unattended execution API requires a Trusted-action policy, confirmation rules, structured results, and separate security tests.

### `inbox.py`

Capture Inbox domain model and persistence.

- Creates clipboard captures.
- Loads and validates Inbox JSON.
- Updates maturity state.
- Keeps captured material separate from actions until conversion.

The Inbox creation UI supports guided `copy_text` and URL-builder Drafts. URL templates are validated through the same domain function used at execution, and the dialog keeps its action footer outside the expandable form so buttons remain visible at smaller window sizes.

### `ai_guidance.py` and `ai_guidance_window.py`

`ai_guidance.py` builds a user-previewable request from an Inbox capture, a constrained prompt variation, and catalogue-owned type guidance. It parses plain versioned JSON or exactly one complete JSON Markdown fence without surrounding commentary. It accepts only the variation's catalogue-enabled action types, rejects unknown fields, and creates actions through type-specific Draft constructors. Envelope errors reject the response; proposal errors are reported individually so valid siblings remain reviewable. A local example response supports evaluation without contacting an AI.

`ai_guidance_window.py` owns the attended clipboard handoff: choose guidance, review and copy the request, paste an AI response, validate and select proposals, and explicitly create local Draft actions. It also exposes the local test-response path and per-proposal validation status. Selected proposals are batch-validated before the local action file is written. The window does not contact an AI provider, store credentials, or promote actions to Trusted.

### `cheatsheets.py`

Structured local reference material.

- Loads and validates sheet JSON.
- Searches sections, labels, details, and tags.
- Promotes an individual sheet entry to a Draft action.

### `window_layouts.py`

Native Windows monitor, window-layout, and snapshot support using `ctypes`.

- Detects monitor work areas with `EnumDisplayMonitors`.
- Opens and positions configured Explorer windows with `SetWindowPos`.
- Stores relative coordinates rather than fixed pixels.
- Captures ordinary visible, non-minimized application windows.
- Matches snapshots by executable, native window class, and title preference.
- Restarts missing ordinary desktop applications when possible.
- Restores foreground state.
- Uses explicit saved browser URLs when provided.

## Action model

An action currently contains:

```text
id
title
technology
task
context
type
value
state
arguments
working_directory
```

Technology, Task, Context, and Action title are separate facets. They are not stored as one hierarchical name.

### Presentation versus search

Compact result rows show:

```text
Command → subject
```

The command is taken from a recognized leading verb such as Open, Copy, Convert, Search, Arrange, or Restore. When a title does not include one, a suitable command is inferred from the constrained action type. Context, Technology, Task, and the original title are shown in a delayed per-row hover tooltip.

The full explanation path is:

```text
Technology > Task > Context > Action title
```

Search indexes title, technology, task, context, type, value, and maturity state. Multiple query terms use AND semantics.

This separation allows visual simplification without losing retrieval power.

The main window defaults to `780x600` with a `700x480` minimum. A responsive horizontal paned area gives the left half to command-first search results and the right half to the global quick-action surface. Both panes expose headings and live counts. Management buttons use a compact five-column, two-row grid so every function remains visible.

Each group renders as a subarea containing multiple compact labels. Left-click opens the owning command-surface JSON plus the corresponding shared/local action JSON. Right-click exposes the item's action-ID list through the same `_execute_action` path used by selected and numbered actions.

Quick-action labels participate in keyboard focus. Enter or Space executes the first available primary action. Empty search, Inbox, cheat-sheet, and command-surface states contain recovery guidance rather than blank widgets. Reloads use a short busy cursor/status state; local loading is intentionally not animated.

## Supported action types

The current allow-list includes:

- `copy_text`
- `open_url`
- `open_file`
- `open_folder`
- `launch_app`
- `build_url_copy`
- `build_url_open`
- `build_url_selection_open`
- `transform_list_csv`
- `workspace_template`
- `window_layout`
- `restore_window_snapshot`

Action types that cause external effects use constrained implementations. `launch_app`, for example, accepts an existing absolute `.exe`, fixed argument list, and optional validated working directory.

## Input and output flow

```text
External selected text
        |
        | Ctrl+Alt+P -> Ctrl+C before focus changes
        v
captured_selection
        |
        v
Input / Output workspace <---- Paste / manual edit
        |
        +-- transformation -> replace workspace + copy result
        +-- URL builder -> consume workspace -> copy/open URL
        `-- copy-only action -> clipboard, workspace unchanged
```

Input / Output is a permanent editable working text box, not action documentation. It synchronizes from the clipboard when shown and can be explicitly copied, pasted, cleared, transformed, or replaced by actions. Inline transformations apply to the selection, or the complete field when there is no selection, and copy their result to the clipboard. Pure transformation logic lives in `actions.py`; `launcher.py` owns selection ranges, one-step Undo grouping, clipboard updates, and menus. Action explanations and application status share a slim bottom communication line.

Numbered action dispatch is enabled only when the Find entry owns focus. All other widgets suppress it, making shortcut mode explicit and preventing accidental execution while navigating or editing. The communication line never wraps; its full untruncated action explanation is retained separately for a dynamic hover tooltip and click-open detail window.

The numbered-slot colour legend and workspace heading are intentionally not rendered. Slot numbers and row colours carry the distinction. Standard editing and transformations are available through the context menu, with a compact `⋮` transform button as the only persistent workspace control.

## Focus contexts and slots

The application currently implements a focus context rather than a complete multi-context inference engine.

```text
1–5  global pinned actions
6–9  focus-context actions
other rows  ordinary search matches
```

Changing the focus context changes slots 6–9 only. Search always remains global.

The longer-term context model includes identity, knowledge, capabilities, and optional activation, with one focus context and multiple supporting contexts.

## Storage

All data is local and inspectable.

### `data/actions.json`

Reviewed portable action records shared through Git.

Action IDs are unique case-insensitively within a file and across shared/local files. This keeps pins, context slots, command-surface references, edits, and trust promotion unambiguous.

### `data/contexts.json` and `data/local_contexts.json`

The shared file contains reviewed portable context definitions. The ignored local file contains personal or work-specific definitions.

### `data/command_surface.json` and `data/local_command_surface.json`

The shared file contains portable global quick-action groups. The ignored local file can add personal or machine-specific groups. Both refer to actions by stable ID.

### `data/local_actions.json`

Ignored personal and machine-specific actions. New Inbox conversions, cheat-sheet promotions, and snapshots are written here by default.

### `data/inbox.json`

Ignored captured material awaiting or recording conversion.

### `data/palette.json`

Ignored per-machine focus context, pinned IDs, and explicit context slot IDs.

### `data/cheatsheets/*.json`

Structured reference sheets.

### `data/layouts/*.json`

Hand-authored relative window layouts.

### `data/layouts/snapshots/*.json`

Captured window situations, including local executable paths, titles, monitor placement, foreground metadata, and optional launch URLs.

Snapshots are ignored because they may contain private local working information.

Safe initial structures are tracked as `data/*.example.json` and copied by `setup-context-palette.bat`.

## Window layout details

### Monitor ordering

Monitor index `0` is the primary monitor. Remaining monitors are ordered by desktop coordinates.

### Relative placement

Positions use values from 0 to 1 within a monitor's usable work area:

```json
{
  "monitor": 1,
  "x": 0,
  "y": 0.5,
  "width": 1,
  "height": 0.5
}
```

This means bottom half of the second monitor.

### Snapshot limitations

Standard Win32 enumeration exposes window titles, classes, processes, and rectangles, but not a reliable browser-tab URL or unsaved document state.

Consequences:

- Browser launch URLs are explicit user-provided metadata.
- Browser history and tab groups are not reconstructed.
- Packaged/protected applications may not start from captured executable paths.
- Changed titles use executable/class fallback matching, which can swap similar browser windows.
- Full background Z-order is not yet restored.

## Threading and responsiveness

Tkinter widgets are only accessed from the main thread.

- The hotkey message loop runs in a daemon thread and writes a lightweight queue message.
- The single-instance listener also signals through a queue.
- Explicit window layout and snapshot restores run on one daemon worker because missing-window matching may take seconds. Results return through a queue and are presented by the Tk main thread.
- The Tk main loop polls requests every 100 ms.
- No database, network service, web frontend, or heavy UI framework is initialized.

Configuration reloads are skipped when active file existence, modification time, and size are unchanged. Typed search changes are coalesced over 40 ms before recalculating slots and rows.

Window layout restore may wait briefly for launched windows to appear, but this no longer blocks Tk rendering or input. Only one window action runs at a time.

## Diagnostics

The standard-library logging system writes bounded local diagnostics to ignored `data/context-palette.log`. The file rotates at 512 KB and keeps two backups. Logging setup failure does not prevent application startup. Clipboard and Input / Output contents are not written deliberately.

## Tooltips and Help

There are two guidance mechanisms:

1. Communication line: bounded selected-action explanation, results, warnings, and errors.
2. Widget tooltip: delayed hover help for every label and button, including compact `?` guidance buttons. Explicit descriptions override automatically installed fallbacks.

Detailed help is stored once in `docs/HELP.md` and displayed by the in-app searchable Help window.

## Security model

- Treat loaded actions and captured text as untrusted data.
- Only allow known action types.
- Validate URLs to `http` or `https`.
- Validate files, folders, executables, and working directories before opening.
- Do not execute arbitrary shell command strings.
- Keep API keys out of version-controlled files.
- Require explicit user action for launches, window restoration, trust promotion, and browser URL metadata.
- Treat captured text and AI responses as untrusted data. AI requests are previewed and copied manually; responses must pass the versioned proposal schema and existing action validation before selected proposals become local Drafts.

## Testing strategy

Tests use `unittest` and focus on pure or callback-injected behavior.

- Action parsing, search, execution dispatch, transformations, and URL building.
- Inbox and cheat-sheet persistence.
- Slot calculation and palette-state persistence.
- Hotkey constants and single-instance behavior.
- Window-layout schema selection and snapshot matching.

External UI and Windows behavior also require documented manual tests. Current manually verified behavior includes two-monitor Explorer placement and snapshot capture/restore round trips.

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

For the complete configuration, compilation, and test check, run:

```powershell
.\check-context-palette.bat
```

## Extension rules

When adding an action type:

1. Add one definition to the catalogue in `action_types.py`; `SUPPORTED_ACTION_TYPES` is derived from it.
2. Add type-specific parsing, validation, execution, and Draft creation as required.
3. Keep pure transformation logic separate from UI/platform effects.
4. Inject external behavior through a callback where practical.
5. Regenerate `docs/ACTION_TYPES.md` through the catalogue-owned renderer.
6. Add automated tests and any required manual Windows check.
7. Update Help, Architecture, Changelog, MVP/Backlog, and Decisions as appropriate.

When adding context behavior:

1. Preserve global search.
2. Do not silently switch the user's focus context.
3. Keep pinned slots stable.
4. Explain inputs, outputs, clipboard effects, opened targets, and trust state.
5. Prefer composition over duplicating actions.

## Known architectural next steps

- Extract secondary Inbox, Draft, sheet, and snapshot views from `launcher.py` without changing behavior.
- Add supporting-context composition and weighted ranking.
- Design safe linear action sequences and clipboard transactions as explicit, previewable models.
- Improve snapshot selection and launch-target editing.
- Consider optional application-aware context suggestions that never switch focus silently.
- Add rich HTML and image actions only with explicit clipboard semantics.

These are proposals, not implemented capabilities. See [Roadmap](ROADMAP.md).
