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
5. Explicit action types, including a user-owned Windows ShellExecute target,
   instead of an application-defined compound command language.
6. Permanent confirmed Action creation with direct reviewed deletion; legacy
   Archived records remain inactive, deletion-only compatibility data.
7. Standard-library implementation where practical.

It is intentionally a personal, single-user desktop application. There are no
accounts, roles, team workspaces, or concurrent-editing guarantees. That narrow
boundary does not relax validation, privacy, lifecycle, or constrained-execution
requirements.

## Runtime overview

```text
run-context-palette.bat
        |
        +-- verify the local environment and tracked requirements signature
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
                +-- register one non-transient topmost drop-target Toplevel
                `-- run the Tk main loop
```

The first process remains resident. Later launches notify it through a project-specific localhost port and exit. This avoids repeated Python and Tk startup cost.

A bare first process displays its already-created root window without replaying a synthetic `show` request. This keeps Input / Output empty on application startup. First launches carrying an explicit integration context or search term still process those parameters.

## Source modules

### `resource_operations.py`

Runtime-only, immutable requests connect existing entry points to existing
effect adapters. `OpenTargetRequest` carries an already-expanded Action;
`CopyFilesRequest` carries exact input text and a `FolderResource` projected
from an Action, Work Item or folder picker; `ExcelWorkflowRequest` carries
either an exact CSV-source snapshot or manual live-workbook selection metadata.
`WebpagePdfRequest` carries one exact URL and a chosen new PDF path; its adapter
accepts manual invocation only. It adds no saved Action type or persisted data.
`EdgeScorePdfRequest` instead carries a captured source HWND and an absolute
destination folder from a `save_edge_score_pdf` Action for the current signed-in
Edge score. It is manual-only; its adapter validates the actual browser/page
before native execution.
`dispatch_resource_operation` validates the request variant and invokes exactly
one host callback. It acquires no clipboard/UI input and owns no persistence.

The launcher adapts requests to its existing target handler, `FileTransferWindow`
and Excel windows. Folder/workbook Work Items remain resources, not persisted
Actions. Normal Run/Quick menus, Send to and approved Drop share these adapters.
The new `send_files_to_folder` Action stores only its destination in the existing
Action `value`; source files are supplied at invocation. It does not acquire
automatic membership in the Folders menu.

Invocation source is not run authority. Drop approval stays in `drop_action.py`;
overwrite review, source fingerprints, partial outcomes and recovery remain
domain-owned. Dispatch returns **opened** or **workflow_started**, never an
asynchronous completion result. In particular, constructing `FileTransferWindow`
can start conflict-free copying: Preview must never dispatch or construct it.
New drops cannot replace an open copy or Excel review. Live Excel remains
manual, with host-owned startup gating and existing workbook selection.

This is not a recipe engine, a second Action catalogue or a data migration.
The older single-file Work Item copy route retains its different no-overwrite
contract rather than silently inheriting Send-to suffix/overwrite behavior.

### `edge_score_pdf.py`, `edge_score_pdf.ps1`, and `edge_score_pdf_window.py`

The owner accepts the current observed stop at Save As for manual folder/name
choice and final Save. The native automation below still attempts automatic
completion; it does not enforce a manual pause. The exact `filename_missing`
protocol outcome now becomes a typed `EdgeScorePdfManualSave` handoff after
helper exit. Staging cleanup finishes before the worker queues this outcome;
the Tk window sets a neutral status and closes without lifting a failure dialog.
Other failures and uncertain helper termination retain the error UI. The stopped path neither applies the
configured folder nor verifies a later manual save or numbers its duplicates.
These are accepted current limitations, not claims that automatic saving passed.

The score adapter controls only the captured Microsoft Edge window and its
Ultimate Guitar Official score or Guitar Pro tab PRINT workflow. It accepts the
existing supported Official URL shape and the exact
`https://tabs.ultimate-guitar.com/tab/{artist}/{song}-guitar-pro-{digits}`
shape only when the inspected document title agrees with that page type. Normal
text tabs, chords, and arbitrary webpages remain outside this adapter. Windows PowerShell and inbox
.NET UI Automation provide named-control access without a Python dependency,
extension, debugging port or browser-profile access. The helper verifies the
page and PDF printer, fills a private staging filename and reports completion.
The site PRINT lookup trims accessible-label whitespace within the verified
document and requires a unique Button. Native Save As is resolved from the
owned foreground HWND and checked for dialog identity and modal state. The
native window's process must use the same executable path as the verified source
Edge process; it need not have the same process ID or UIA provider attribution.
The owner chain and foreground checks still bind it to the captured score
window. Discovery does not depend on a fixed UI Automation tree location. Filename ID 1001 is also
restricted to Edit controls because the address toolbar can share that ID.
The small companion `edge_score_pdf_native.cs` checks native window ownership
and isolates potentially blocking Invoke calls on background MTA threads inside
that same helper process. It compiles through inbox PowerShell/.NET; no separately
installed compiler is required and execution policy is not overridden.
The Python boundary checks the staged PDF and publishes without overwriting.
Cancellation terminates only the adapter helper, never the user's browser.

The dedicated Tk window owns worker progress, cancel/close and saved-file
controls; the launcher owns the saved-Action runner, captured-window handoff and
Quit guard. `save_edge_score_pdf` stores one literal absolute folder in its
ordinary Action value and accepts no arguments, working directory, or templates.
It can use configured Quick actions and Context slots, but never Drop, AI
proposals, or sequences. `edge_score_pdf_settings.py` continues to load the
ignored legacy settings JSON; the saved Action configuration is authoritative.
Input / Output and the general
webpage renderer do not acquire browser automation behavior.

The first version targets the observed English Edge/Windows controls and
requires real Windows UAT. Test doubles cannot prove that a changing browser
or website continues to expose those controls.

### `main.py`

Application entry point.

- Resolves the project root.
- Derives a stable project-specific local port.
- Notifies an existing instance before treating a pending journal as an
  interrupted transaction.
- Completes rollback from a pending restore journal before migrations or
  configuration loading.
- Starts the Tk launcher with paths to local data.

### `launcher.py`

Presentation and application orchestration.

- Builds the Tkinter interface.
- Maintains one transient Context choice in the unified **Filter** menu. That
  choice controls canonical visible membership and the active slot bank for
  6–0; **All contexts** selects General's membership and bank.
- Exposes the complete configuration workspace through **Configure**. Its
  ordinary route opens a task-oriented Start page, while **Manage contexts…**
  in the unified Filter menu routes directly to Contexts. All routes reuse one
  live editor and retarget its section or selected record; a new editor is
  created only after the previous one closes.
- Renders the active Context bank's shortcut rows 6–0 when Find is empty, plus
  mixed or kind-specific result projections constrained by that Context.
  Non-empty Find results use relevance ranking without shortcut promotion.
- Renders the global JSON-configured Quick-action surface below discovery
  and the fixed action-bound Passwords, Folders, and Prompts hierarchies.
- Composes a bounded horizontal main split: the command console occupies about
  40% initially and the full-height Input / Output workspace about 60%.
- Owns the communication line, systematic widget tooltips, Inbox, sheets, Help,
  and action editors; `WorkspacePanel` owns the Input / Output presentation.
- Owns the safe drop-result handoff: it clears stale captured-selection and
  source-window state, reveals the ordinary palette without clipboard
  synchronization or permanent topmost state, and asks `WorkspacePanel` to
  place the completed normalized text.
- Unmaps/remaps the existing workspace pane for its session-only visibility
  checkbox; the editor and histories are not rebuilt. A hidden-input marker and
  fallback communication line remain visible. Show-only drops and completed
  text results reveal the pane; direct copy/open/CSV drops do not stage input.
- Builds optional execution previews from explicit input snapshots. Opt-in Drop
  dispatch resolves an approved Action and supplies a separate exact input
  snapshot through existing execution callbacks, retaining attended workflows.
- Connects platform-independent action execution to Windows-specific callbacks.
- Ensures Tk operations stay on the Tk main thread.
- Resets transient presentation state through the main-window `F5` shortcut
  without changing legacy focus/pin compatibility data, per-Context slot
  assignments, Actions, or configuration. Context, tag, type, and project
  filters are cleared because they are in-memory presentation state; General's
  bank becomes active with **All contexts**.
- Switches the existing discovery area among explicit **All items**,
  **Actions**, and **Work Items** scopes without changing the main-window
  dimensions. Find, shared Context/tag filters, kind-specific project-code/type
  filters, selection,
  previews, and constrained open commands consume the immutable in-memory Work
  Item index; kind-specific filter state remains intact. All keyboard, default, and
  context-menu targets pass through one constrained Work Item opening boundary.
  The mode-specific **New item** control opens the existing Configure creation
  flow; the launcher does not duplicate template validation or filesystem
  creation. The primary action row becomes a two-part control in Work Items
  mode: **Open** retains workbook-first behavior while its adjacent folder
  button requests the same constrained boundary with the folder target.

Discovery and Quick actions form the left command console; Input / Output and
the one-line status display form the right workspace. A result toolbar owns
selection commands, the workspace header owns text/input commands, and a small
application toolbar follows Quick actions. Secondary
Inbox and Inbox-action-creation presentation lives in `inbox_window.py`;
`launcher.py` retains only the capture command and window orchestration.

The launcher does not implement action transformations or window matching directly. Those responsibilities live in specialized modules.

### `action_workbook.py`, `action_bulk.py`, and `action_bulk_window.py`

`action_workbook.py` owns the dependency-free, versioned Excel interchange
boundary for bulk Action creation. It writes a standard `.xlsx` template with
Instructions, Actions, and Reference sheets and reads only that exact bounded
contract through ZIP/XML. It never starts Office, follows links, evaluates
formulas, or accepts macros. Formula cells and changed headers are rejected;
the file and expanded-package, entry, row, cell, and text limits are fixed.

`action_bulk.py` converts workbook rows through `configured_action()`, validates
only existing personal Context memberships, and classifies Ready, excluded,
invalid, exact-existing, and possible-duplicate records. The reviewed plan is
tied to the complete workbook digest and canonical stored-Action signature.
Commit rechecks both, then appends the selected personal Active Actions through
`append_actions_with_context_memberships()` so ordinary Action and Context
validation/rollback remains authoritative. Sequences, fixed Excel automation
Actions, and lossless-parameter text-file transforms are excluded from the
generic workbook contract.

`action_bulk_window.py` owns the centered attended review table, row selection,
details, template save/choose/reload routes, and the single effect-labelled
**Create N Actions** confirmation. It writes no state during review and does
not add a redundant Yes/No dialog. Configure → Actions → **More Action
tasks** is the primary route.

### `action_update_workbook.py`, `action_bulk_update.py`, and `action_bulk_update_window.py`

`action_update_workbook.py` owns a separate deterministic version-1 standard
`.xlsx` round-trip contract for eligible personal Active Actions. Its immutable
identity columns are Action ID, type, state, and the original canonical-record
fingerprint. Name, Value, personal Contexts, tags, description, Quick menu,
lossless JSON arguments, and working folder are editable. Only ordinary types
supported by this contract are exported; sequence, `excel_automation`, and
`transform_file_text` remain in their guided editors. Built-in and legacy
inactive Actions are never exported. The bounded ZIP/XML reader rejects formula cells,
macros, links, changed structure, unsafe packages, and changed identity.

`action_bulk_update.py` maps each verified row back to its stable personal
Action ID, validates edits through the ordinary Action catalogue, and produces
Ready, no-change, or error candidates with exact changed fields. Planning is
read-only. Commit rechecks the complete workbook digest, current Action
signature, per-row identity, and current personal Contexts while holding the
configuration mutation gate. Selected Ready changes are written as one Action
and Context operation; a failed Context write restores the exact prior Action
bytes. Removed workbook rows have no meaning and never delete records.

`action_bulk_update_window.py` owns export, choose/reload, exact before/after
review, selected-Ready-row toggles, and one effect-labelled **Update N Actions**
button. That button is the confirmation: there is no redundant Yes/No dialog
and no Action executes. A successful update makes the review stale and requires
a fresh export before another operation. Direct Action deletion remains
outside workbook semantics. Configure exposes
**Export personal Actions for update…** and **Review updated Actions
workbook…** under **More Action tasks**.

### `action_bulk_lifecycle.py` and `action_bulk_lifecycle_window.py`

`action_bulk_lifecycle.py` owns read-only, identity-based review plans and
guarded batch commits for direct personal Action deletion. It accepts Active
and legacy inactive personal IDs, identifies unselected dependent sequences,
inventories the selected set's combined Context, slot, legacy-pin, and
configured Quick-menu effects, and fingerprints every participating Action,
Context, command-surface, and palette file. Commit holds the configuration
mutation gate, recreates the plan, rejects stale state, and delegates to the
set-aware deletion transaction in `action_deletion.py`. Selected dependent
sequences may be deleted with the Actions they reference; unselected
dependencies remain blockers.

`action_deletion.py` processes a selected ID set against each reference file
once, writes every changed primary file at most once, and snapshots both primary
and `.bak` bytes before effects. Failed writes restore those exact bytes or
report incomplete rollback. The plural boundary also compares the freshly
computed aggregate report with the reviewed report before its transaction
writes anything, so an impact mismatch is a known no-write result rather than
a post-commit error. Singular and plural deletion use the same set-aware
boundary.

`action_bulk_lifecycle_window.py` owns the centered attended selection, Find,
combined impact review, and one effect-labelled **Delete N Actions
permanently** command. Find narrows shown candidates without clearing selected
IDs; the status and command label count selected rows hidden by the filter.
There is no redundant generic confirmation or preparation stage. Active and
legacy inactive personal records can be removed. Built-in Actions, workbook row
removal, Action execution, and external target mutation are outside this
workflow. Configure exposes it as **More Action tasks → Delete multiple
personal Actions…**.

### `harvest.py` and `harvest_window.py`

`harvest.py` is the platform-independent bulk document-harvesting boundary. It
defines transient source, occurrence, candidate, and batch models; bounded
local extractors for `.md`, `.txt`, `.docx`, and `.xlsx`; conservative URL
normalization and semantic deduplication; Active-action conversion; and the background
scan coordinator. OOXML packages are inspected as ZIP/XML without starting
Office or evaluating formulas.

`harvest_window.py` owns the attended review workflow: multi-file selection,
progress and cancellation, source and candidate filters, provenance, individual
and bulk edits, preview, and one atomic append to the personal action store.
The visible route is **Harvest website links…** because every candidate is an
HTTP/HTTPS `open_url` Action. The launcher exposes the window from Inbox, while
the Actions configuration section is the primary route. No harvested candidate
enters persistent data before the final confirmation. This URL-specific model
is deliberately separate from structured bulk Action workbooks.

### Discovery scopes, Context, and secondary filters

The shared discovery area combines three item-kind scopes with one unified
**Filter** menu. Its transient Context choice is the single current Context:
**All contexts** uses the complete General-root collection and General's slot
bank, while a specific Context uses its canonical membership and bank.

| State | Heading/results | Secondary tools | Primary action |
| --- | --- | --- | --- |
| All items | Mixed Actions and discovered Work Items, optionally limited by Context and tag | Filter menu: Context and Tag | Run or Open, selected-kind specific |
| Actions | Actions only, optionally limited by Context, tag, and type | Filter menu: Context, Tag, and Type | Run |
| Work Items | Indexed Work Item folders, optionally limited by Context, tag, and project; never Action records | Filter/tools menu: New item, To inbox, Copy file, Context, Tag, and Project | Open |
| Empty Find | The active Context bank's slots 6–0 may be projected before ordinary results | Scope-specific tools | Selected-kind specific |
| Non-empty Find | All matches ordered by relevance; no shortcut promotion | Scope-specific tools | Selected-kind specific |

The scope selection, empty state, selection preview, toolbar state, status, and
primary verb must all describe the active scope and selected kind. Redundant
pane headings and counts are maintained as internal state only, not rendered.
`ActionDiscoveryPanel` owns those widgets; `LauncherApp` owns scope policy,
typed selection resolution, and the constrained Run/Open
callbacks. Both `?` controls continue to open the same general Help document.

Search remains an AND match across normalized terms. For a non-empty query,
Actions rank exact title or ID first, then title prefix, title substring,
all-term title matches, exact Context/tag labels, and other metadata. Work
Items similarly rank exact/prefix/substring display-name matches, then subject
matches and other metadata. Stable visible-name and identity keys break ties.
Context and tag filter state is shared across all three item-kind scopes. Only
Context chooses the slot bank. Find and tag narrow the current projection;
type and project retain their kind-specific state and likewise never choose a
bank. When dormant in another scope, type and project remain named in the
filter chip rather than becoming hidden state. All filter state is in memory,
is cleared by the normal transient reset, and adds no field or migration to
persisted palette data.

### `actions.py`

Action domain model, persistence, validation, search, transformation, and dispatch.

Important principles:

- Each action type is explicitly allow-listed.
- Windows target actions pass one configured target, optional structured
  arguments, and an optional working folder to `os.startfile()`/ShellExecute.
  Registered protocols, file URIs, drive paths, documents, and associated
  scripts are deliberately accepted. Unset optional ShellExecute parameters are
  omitted rather than passed as `None`, matching Python's real Windows API
  contract. The action preview makes clear that the target can execute code and
  is not sandboxed.
- Local file, folder, application, Windows-target, and working-folder paths
  resolve the literal configured value first. When that target is unavailable,
  a percent-decoded path or decoded `file:` URI is accepted if it resolves to
  the required local target. HTTP/HTTPS addresses remain encoded and unchanged.
- Guided creation and JSON loading share the same action-value validation, while
  execution retains safety checks around platform effects.
- The app does not tokenize or interpret a compound shell command language.
- Pure transformations are separated from UI callbacks.
- Platform effects are injected through callbacks where practical, enabling tests without opening applications.
- Clipboard access during template expansion is lazy: actions without clipboard variables do not fail when the clipboard contains a non-text format.
- Launcher Find, Configure Find, and Configure action pickers consume one
  canonical in-memory action search document containing identity, readable and
  technical type metadata, organization, state, target/value, arguments, and
  working folder. Configure adds storage ownership as surface-specific metadata.

### `action_bound_quick_actions.py`

Builds the shared Passwords, Folders, and Prompts `CommandGroup` hierarchies
directly from Active actions and their optional `quick_action_path`. Both the
launcher and Configure consume this builder, so displayed membership, nesting,
and menu-root placement cannot diverge. An empty path becomes a group-root
Action; a non-empty path creates only the named branches. Configure adds
presentation-only
selection records: generated action leaves delegate to the normal action
editor, while generated groups and levels offer a typed full Action form and
the automatic-menu organizer.
The generated hierarchy is never written as a second assignment store.

### `quick_menu_path_dialog.py`

Owns the structured, searchable automatic-menu location chooser shared by the
Action editor and organizer. It derives the fixed Passwords, Folders, or
Prompts root from the Action type, shows the real case-canonical branch tree and
Action counts, represents the root explicitly, and permits a proposed submenu
only within the existing three-level bound. It returns a normalized tuple and
does not persist an empty branch independently.

### `action_quick_menu_organization.py`

Plans and commits automatic-menu placement changes without changing the
command-surface schema. Assignment moves selected same-type Actions to one
exact path. Branch move/rename rewrites a case-insensitive path prefix for all
matching Active Actions in Built-in and personal storage. Legacy inactive
records are deletion-only. Plans report exact Action, ownership, and file
counts and are fingerprinted
against both Action files. Commit rechecks the plan under the configuration
mutation gate, writes each changed Action file once, and restores exact primary
and backup bytes when a later write fails. Only `quick_action_path` changes;
Actions, external targets, and configured Quick-action references are never
deleted or executed.

### `action_quick_menu_organization_window.py`

Owns the attended Configure UI for reviewing and committing selected Action
placement changes or explicit automatic-submenu Create/Rename/Move/Remove
tasks. Create assigns selected Actions to a new child path; rename replaces the
last source level; move chooses a parent and preserves the submenu name; remove
uses the parent as the destination so direct Actions and nested suffixes are
promoted without deletion. An Action-level removal uses the same assignment
plan but accepts only direct members and promotes them exactly one level; the
Quick-actions tree can preselect one exact stable Action ID. The fixed root
exposes no Action-removal command because every matching Active Action must
remain in its automatic menu. The window
uses the shared path/name choosers, operation-specific review and effect labels,
and delegates all persistence, stale-state detection, and rollback behavior to
`action_quick_menu_organization.py`.

### `action_configured_placement.py`

Plans and commits configured Quick-menu references for one Active Action. A
location has stable identity from its storage, group ID, and item-ID path;
display labels are not identity. The plan compares every eligible configured
root/branch with the Action's current references and reports exact additions,
removals, newly empty items, Built-in/My configuration effects, and files to
write. Built-in Actions may be referenced from either storage, while personal
Actions are restricted to My configuration. Commit fingerprints both Action
files and both command-surface files, rechecks under the configuration mutation
gate, writes each changed surface once, and restores exact primary and `.bak`
bytes after failure. Stale state and rollback completeness remain explicit.
The same service inventories configured locations for a not-yet-saved Action
and owns the composite create/edit transaction used by the Action form. That
transaction saves the Action record, Context memberships, and configured
references under one mutation gate and restores exact participating primary and
`.bak` bytes if a later step fails.

### `action_configured_placement_window.py`

Owns the attended **Other menus…** UI from a selected
Active Action. It shows automatic type/path placement as read-only independent
information, provides a searchable configured root/branch checklist, and
renders one exact add/remove review before the effect-labelled apply command.
It never edits the Action's type or `quick_action_path` and delegates all
persistence and recovery decisions to `action_configured_placement.py`.

### `quick_menu_path_dialog.py`

Owns the combined **Menu locations** chooser used during Folder, Password, and
AI-prompt Action creation/editing. It stages one automatic path plus zero or
more stable configured-location keys and performs no writes. Ownership-disabled
locations remain visible; the final Action save delegates the staged selection
to `action_configured_placement.py`.

### `palette_items.py`

Defines the immutable typed reference shared by Context membership, preferred
context slots, and mixed Quick-action targets. A reference identifies exactly one
Action ID or one stable Work Item source/folder identity; it contains no
execution behavior. Owning services resolve and execute the referenced entity,
so Work Items retain their discovery lifecycle and Actions retain their
allow-listed executor.

### `action_types.py`

Defines the machine-readable catalogue for every supported action type: icon,
user label, family, description, required fields, input/output effects,
portability, new-action visibility, AI eligibility, and type-specific AI
guidance. Supported legacy types can remain loadable and editable while the
Action type chooser omits them. `actions.py`
derives its supported-type set and compact row icon from this catalogue, and AI
prompt generation consumes the same definitions.

The catalogue renders `docs/ACTION_TYPES.md`; an automated test requires the user-readable overview to remain identical to the executable definitions.

### `action_preview.py`

Builds the side-effect-free, structured explanation shown before Action
execution. It combines the selected Action with the canonical action-type
catalogue and boolean runtime availability supplied by the launcher; that summary
does not read the clipboard, expand templates, validate targets, or execute an
effect. Every supported type produces a bounded **Input → Effect** summary plus
full labelled details for Type, configured values, arguments, working folder,
and recovery or limitations. Current workspace, captured-selection, and fresh
destination availability refine the summary without exposing their contents.

`build_execution_preview` additionally accepts explicit workspace, selection,
and clipboard snapshots from the launcher and returns an immutable
`ExecutionPreview`. It reuses existing template expansion, lexical validation,
URL building, and pure transformation functions; it never acquires clipboard,
credentials, file contents, or engine data itself. External operations are
plan-only and unavailable sources are explicit. Computation/expansion and
display sizes are bounded independently. Preview grants no execution authority:
ordinary Run still evaluates current input and existing confirmations.

`ExecutionPreview.display_blocks()` supplies bounded semantic display roles
to the launcher's read-only Tk text widget; `full_text()` uses those same
blocks. The UI tags headings, notices and literal content directly, without
parsing user text as markup. It puts the Run explanation before large input
snapshots and suppresses duplicate saved content/targets in the display only.
Text transformations use a task-specific explanation and actual before/after
snapshots. Safe static examples are separately labelled and never assigned to
runtime input or computed output. Their optional details control only rerenders
the immutable snapshot; it never rereads the clipboard or invokes an Action.
The full text report retains the additional details within the same bounds.

### `workspace_transforms.py`

Defines the ordered, user-facing catalogue for Input / Output transformations:
menu groups, labels, operation keys, completion feedback, and readable
parameter definitions. The workspace menu and guided reusable action editor
for text files both consume this catalogue, while the launcher renders action previews
without duplicating operation names. The launcher renders its Transform menu
from this catalogue instead of repeating every command in the UI orchestrator.
Pure transformation algorithms and validation remain in `actions.py`.

### `workspace_panel.py`

Owns the complete Input / Output UI component: text widget, edit menu, visible
Back, Forward, literal **Send to…**, Capture, Inbox, **Create from Input**,
**Extract text**, and **Text tools** controls; selection-first source choice and replacement;
undo boundaries; prompting;
clipboard copy and replacement, transformation feedback, and file-transform
preview provenance. Its separate session-only history retains at most ten
meaningful whole-content states, coalesces manual typing until the next
navigation or semantic change, and applies normal branch semantics after Back;
native Tk Undo/Redo remains available for finer edits. It also owns the shared
undoable incoming-text placement
boundary used by OCR and drag-and-drop, including explicit Replace, Append,
and Cancel for a non-empty workspace. A file preview exposes explicit replace, save-as, and
dismiss commands; ordinary workspace replacement clears that provenance. It
depends on small injected callbacks for Action suggestion orchestration,
clipboard access, status messages, tooltip registration, and on-demand Send-to
menu population. `launcher.py`
retains compatibility delegates for action execution and integration flows,
but no longer owns workspace widget mechanics.

### `drop_extraction.py`

Defines immutable typed `path`, `url`, and `text` items plus pure bounded
normalization. It accepts already decoded values, recognizes Windows drive and
UNC paths, HTTP(S), Windows `file:` URIs, and percent encoding, preserves
first-seen order, and performs type-aware deduplication. It never imports Tk,
reads a file, resolves a shortcut, touches the clipboard, starts a process,
logs dropped values, or persists data. It also provides the pure bounded parser
for decoded `.url` Internet Shortcut content.

### `drop_adapter.py`

Owns the narrow platform adapter between TkDND events and the pure extraction
core. `DND_Files` payloads are decoded only through the originating widget's
Tcl `splitlist`; `DND_Text` remains one library-native payload. Raw values,
counts, text length, shortcut bytes, subprocess duration, and output are
bounded. `.url` files are read with a small encoding-aware limit. `.lnk`
resolution invokes a fixed hidden PowerShell/WScript.Shell target-only query
with separate arguments and discards the shortcut argument string; an error,
timeout, or unusable target keeps the original shortcut path and a structured
warning. The single-flight daemon coordinator performs those reads off the Tk
thread and exposes immutable completion through polling. It never executes the
resolved target or writes application state.

### `drop_target_window.py`

Owns one lazily enabled, non-transient `Toplevel` under the existing ordinary
`tk.Tk` root. It uses the maintained `TkinterDnD.require(existing_root)` API,
creates no second root, registers `DND_Files` and `DND_Text`, and returns the
required TkDND copy/refuse actions. Only this small movable window has permanent
`-topmost`; closing it withdraws and later Show reuses the same instance. It
remains mapped when the main root is withdrawn and stays available after a
drop. Its callback returns only a completed structured result to `LauncherApp`;
the component cannot modify Input / Output, clipboard, persistence, Actions,
Inbox, or external applications. Dependency import/native-load failures are
logged and caught at this feature boundary so ordinary startup remains usable.
Registration, binding, and show failures destroy only the partial Toplevel,
clear its widget references, cache a safe unavailable reason until restart,
and expose repair guidance through launcher status and **More → Show drop
target**. The window
retains only the last ten successful non-empty `DropResult` values in memory,
identifies the selected result with type-level metadata, and can resend that
immutable result through a separate show-only launcher callback without re-resolving or
duplicating it. A collapsed disclosure renders a bounded read-only preview of
the exact prepared paths, web links, or text plus warnings; it performs no
filesystem or network inspection and collapses on Hide or a new drop. Preview
truncation never truncates the retained result. Errors and empty drops are not
retained; process exit clears the history.

Its small Settings entry delegates to the launcher; the target only displays
the configured behaviour label. A delivery guard refuses nested new drops or
history sends while a placement/Action callback is active, including Tk modal
event loops. It clears in `finally`; it never queues retries.

### `drop_action.py` and `drop_configuration_window.py`

The pure drop policy owns compatibility reasons and `DropActionSettings`:
show-only by default, or an exact Action ID plus a SHA-256 fingerprint of its
execution-relevant configuration. Changed/missing/inactive/ambiguous Actions
cannot inherit earlier approval. Contexts, tags, and menu placement are not
execution authority. Compatible input-consuming Actions reuse their existing
executor, including Excel CSV's attended review. Arbitrary Windows targets,
associated files, app launch, credentials, sequences, and live Excel are not
enabled for this invocation.

The centered settings dialog uses the existing Action picker, shows effects
and unavailable reasons, and never executes anything. Launcher saves under
the configuration mutation gate, revalidates the selected Action, and merges
fresh palette state so simultaneous Context-slot changes are preserved.
`palette.json` has one optional local `drop_settings` member, omitted for the
default; existing JSON records load unchanged. Focus normalization, runtime
snapshots, and General-shortcut saves preserve it. No Context/tag migration or
generic permissions/recipe schema is introduced.

Drop intake clears stale capture/destination state, then separates execution
from placement. A configured Action rechecks the published configuration and
exact approval before receiving the immutable new drop directly. It neither
reads nor stages input in the editor and never opens Replace/Append first.
Default show-only intake and explicit history replay keep Replace/Append/Cancel.
Text output is buffered until the synchronous Action succeeds, then published
to Input / Output as a result; copy/open/CSV Actions leave the editor alone.
Blocked/failed dispatch shows an explanation without changing existing text;
the Drop target retains the original snapshot in session history, with no
automatic retry. Existing copy/Excel reviews cannot be replaced by a new drop.
Copy and CSV windows detach their transient owner when it is hidden, allowing
their own review/results to remain visible without first opening the Palette.

### `ocr.py`

Defines the optional local image-to-text boundary. Pure source validation
accepts one exact absolute PNG, JPEG, BMP, GIF, TIFF, or WebP file subject to a
50 MiB input limit. Clipboard acquisition lazily uses Pillow to snapshot one
bitmap as PNG bytes without clearing or replacing any clipboard format and
rejects images above 40 million pixels. `RapidOcrProvider` lazily imports and
initializes the pinned RapidOCR/ONNX Runtime stack only after a request; normal
launcher startup and non-OCR tests do not load it. `OcrCoordinator` serializes
one daemon worker and delivers results through the launcher's existing
main-thread polling pattern. Extracted text, source metadata, duration, and
aggregate confidence are transient and are never written to logs or persistent
configuration.

`launcher.py` owns source priority, file-picker fallback, progress, and safe
error presentation. `workspace_panel.py` owns result placement as one undoable
Replace or Append edit and presents a dedicated modal with literal **Replace**,
**Append**, and **Cancel** buttons. A non-empty or concurrently changed workspace
is never overwritten without an attended choice. No-text and failed results change
nothing. OCR does not copy its result automatically, persist the source image,
upload content, or join the current launch-only Action sequence model.

OCR deployment remains independent of core setup. `requirements.txt` contains
required application packages, including pinned `tkinterdnd2==0.6.2` and its
bundled architecture-specific TkDND libraries; `requirements-ocr.txt` contains
the pinned optional engine. Online setup establishes the core environment before
attempting OCR; offline setup additionally runs the complete core check after
the optional attempt. An OCR installation or initialization failure leaves the
core environment and non-OCR launcher behavior available.

`run-context-palette.bat` hashes the tracked core requirements and compares the
result with the marker written only after a successful setup installation. A
missing or mismatched marker refuses normal launch with the exact stop, setup,
and retry sequence; it does not install packages implicitly. A current marker
does not make TkDND a whole-application runtime gate: native Drop-target failure
continues through the isolated behavior above.

### `action_suggestions.py`

Defines the pure, typed inference boundary for creating an Action from Input /
Output. It accepts only one complete HTTP/HTTPS URL or one clear absolute
Windows/file-URI target that can be identified lexically as a file, folder, or
`.exe`. Script-like suffixes are not inferred as ordinary files. It does no
filesystem probing, clipboard access, persistence, network retrieval, or
execution and returns no suggestion for mixed or ambiguous content.

### `action_discovery_panel.py`

Owns construction and event wiring for the left action-discovery presentation:
item-scope controls; one Find row containing the search field and unified
Filter menu; an active-filter chip; flat result list, scrollbar, row tooltips;
and the stable Create Action, Edit, and Run/Open result toolbar. Action-only and Work
Item-only commands live in the Filter menu instead of reshaping the toolbar.
Routine icon controls use retained 16-pixel Tk bitmap images with semantic
tooltips, avoiding font-dependent Unicode toolbar symbols and new dependencies. Search
policy, relevance ranking, Context membership, selection meaning, and execution remain in
`launcher.py` and are supplied through narrow callbacks. Compatibility aliases
allow existing launcher orchestration to migrate incrementally.

Context and tag filters open shared searchable single-selection popups from the
Filter menu. The Context choice also selects the slot bank; tag does not. A
separate **Manage contexts…** menu command opens the existing Contexts
configuration page without adding another selector or state. The launcher
remains the only owner of transient filter state and result refresh.

Right-click callbacks preserve the clicked flat row as the current
selection, then route its stable action ID into the existing Configure Actions
workspace. `configuration_window.py` highlights that action after rendering;
My configuration actions persist to the ignored local action file. Built-in
actions may also be edited after an explicit developer-impact warning and
persist to the Git-tracked starter action file.

The result toolbar's explicit **Edit** command adds a one-shot direct-edit
request to that same stable-ID route. Configure reloads and raises its existing
workspace, clears conflicting Action filters, resolves the ID only against the
current Active projection, and opens the existing `ActionDialog` path after the
window becomes idle. Right-click remains selection-only navigation. A missing
or concurrently deleted Action leaves Configure usable and opens no editor.

### `context_membership_field.py`

Provides reusable comma-separated picker fields used by Configure, Inbox
conversion, and action editing. Context membership combines an editable field
with a checklist of canonical defined contexts. Tag selection uses a shared
searchable multi-select picker for existing normalized tags but continues to
allow new free-form values. The discovery Filter menu separately reuses
`searchable_selection.py` in single-select mode for Context and tag filters,
including an explicit clear choice. Selection mechanics
remain separate from domain validation in
`actions.py`, so typed values and non-UI callers follow the same persistence
rules. Underlined Windows mnemonics move focus directly to each field, and
`Alt+Down`/`F4` opens either Tk's native context checklist or the searchable
tag picker.

### `context_membership.py`

Owns the single source of truth for action-to-context membership. Context
definitions supply the canonical ordered `action_ids`; action objects used by
the launcher and Configure are projected from those definitions so search,
the Actions table, slots, and Context-filtered retrieval all see the same memberships.
Action create/edit flows write the action record and context definitions as
one recoverable operation, remove context metadata from newly persisted action
records, and reject a My configuration action reference from a Built-in
context. Batch updates expose a structured rollback-completed outcome: an
incomplete restore is propagated as an unknown configuration effect so its
attended window locks retry and directs backup/Diagnostics inspection. Startup
performs an idempotent one-time union of compatible legacy
action-side memberships into context definitions. Legacy metadata remains
readable for pre-migration definitions but is not an independent current
membership source.

### `searchable_selection.py`

Provides the compact searchable selection popup shared by guided multi-select
tag fields and the discovery Filter menu's single-Context and single-tag
filters. It preserves selections while search narrows the visible list,
provides an explicit clear choice for filters, and restores an owning dialog's
modal grab when it closes.

### `action_picker.py`

Provides the shared searchable action selector used throughout Configure.
Context membership, preferred context slots, and Quick-action
assignments open the same dialog instead of rendering separate long combobox
menus. The picker matches all entered terms against the action's readable
label and the canonical action search document, while callers continue to
persist stable action IDs. Restricted Built-in pickers display their storage
scope and an explicit empty-result explanation.

### `action_type_picker.py`

Provides the keyboard-first searchable chooser for creatable Action types.
It returns one reviewed type selection to the owning form and performs no
persistence or execution.

### `configuration_mutation.py` and `persistence.py`

`configuration_mutation.py` owns one process-wide reentrant gate for
application configuration. Every JSON replacement acquires it automatically;
logical Action/Context membership changes, deletion/rename operations,
migrations, and cleanup hold it across their complete multi-file sequence and
rollback. Reviewed text-file replacement also participates because its target
may be the catalogued managed text source. Work Item workbooks and external
file-copy operations remain outside this gate.

`persistence.py` owns JSON replacement for application-written data and exact-
byte replacement for restore. Both use a temporary sibling, flush and `fsync`,
and atomic replacement. An ordinary JSON write serializes to a temporary
sibling file, flushes it to disk, preserves the
previous destination as `<name>.bak`, and uses `os.replace` so readers see
either the previous complete file or the new complete file. Temporary and
backup files are ignored by Git because they can contain private runtime data.
Restore byte replacement disables adjacent `.bak` creation because its
independent recovery archive owns aggregate rollback.

Actions, Inbox state, and palette state use this single writer.

### `data_catalog.py`

Defines the UI-independent application-data boundary. Frozen `AppDataPaths`
derives the known Built-in, personal, machine-local, captured-content, and
diagnostic locations from one application root or data directory. Frozen
`DataAssetSpec` records declare stable IDs, constrained relative locations,
ownership, required status, sensitivity, backup policy, and logical schema
versions. Patterns may vary only their final path component, so the catalog
cannot become an unconstrained recursive filesystem scan.

`main.py` and the configuration snapshot service construct this object from the
project root. `launcher.py` receives that same object in normal startup and retains a
compatibility adapter that derives it from the existing Actions directory for
older direct callers; its Work Item configuration paths no longer repeat
filenames. The catalog performs no loading, external Work Item discovery,
credential access, backup, or restore work.

The excluded private-runtime inventory includes the versioned
`data/restore-journal.json` path. It is ignored by Git, excluded from ordinary
backups and snapshots, and used only to finish an interrupted rollback.

### `configuration_snapshot.py`

Owns complete, read-only loading and aggregate validation for catalogued
structured application state. Frozen `ConfigurationSnapshot` values retain
Built-in and personal collections separately, preserve legacy inactive Actions
for deletion compatibility, expose only Active Actions in the executable
projection, and defensively copy
loader-owned lists and mappings. `SnapshotValidationReport` and its frozen
issues provide stable codes, catalog asset provenance, severity, category, and
privacy-safe summaries.

Each asset is loaded independently through its existing domain loader. The
service validates stable identities, hard Active-Action references,
Built-in/personal boundaries, palette context classifications, and soft Work
Item source relationships. It reports machine-local portability and visible
legacy forms without printing private values, checking external path
availability, scanning Work Item roots, reading optional managed text content,
or writing/migrating data. Excluded runtime assets are never loaded.

### `backup.py` and `backup_cli.py`

`backup.py` owns backup format version 1 and the UI-independent complete-
configuration backup service. Frozen manifest records contain only catalog
asset IDs, normalized `payload/` paths, applicable logical schema versions,
exact sizes, and lowercase SHA-256 digests. Frozen results retain the
destination, included files/assets, explicit privacy exclusions, and structured
snapshot warnings.

The service acquires the configuration mutation gate, inventories only
catalog-eligible exact paths and direct cheat-sheet matches, rejects links,
reparse points, root escapes, and declared size/count excesses, then copies
bytes to a private temporary staged root. SHA-256-backed fingerprints before,
during, and after copying detect external-editor or separate-process changes;
three attempts are allowed. The staged root is validated through
`configuration_snapshot.py`, and only those staged bytes are packaged.

ZIP entries have fixed metadata and deterministic ordering. `manifest.json` is
last. A complete temporary ZIP is created beside the chosen destination,
flushed, and published through an atomic no-clobber operation unless overwrite
was explicitly requested; explicit replacement uses `os.replace`. Failed
publication leaves an existing archive untouched and cleans temporary state.
Default limits are 256 entries, 16 MiB per entry, and 64 MiB total. Inbox is
included unless explicitly excluded; managed text requires explicit inclusion.
Diagnostics, recovery and temporary files, environments, unknown files,
external resource contents, template contents, and credential secrets are
never selected. Their configured references remain inside the catalogued JSON
assets that own them.

`backup_cli.py` is a small service-level command adapter for testing and manual
use. It reports privacy scope, exclusions, counts, and privacy-safe snapshot
warnings. It is not connected to the launcher or Tkinter.

### `restore.py`

Owns the UI-independent Phase 4 restore core. Inspection treats ZIP input as
hostile: it validates strict version-1 manifests through the existing frozen
backup models; rejects unsafe or colliding Windows paths, links/reparse
representations, directories, unsupported compression, unexpected entries,
header disagreements, and configured size/count excesses; and streams every
payload through CRC, size, and SHA-256 verification without using ZIP extract
APIs.

Inspection overlays only manifest-listed payloads onto a temporary same-volume
tree. Existing optional catalogued files omitted by version 1, including
unmatched cheat sheets, are copied into that tree and preserved; required
omissions are not inferred as deletions. The completed tree is loaded through
`configuration_snapshot.py`. A frozen `RestorePlan` retains only operational
hashes, catalog IDs and paths, replacement/creation/preservation categories,
Built-in and sensitive-content acknowledgements, compatibility state, and
privacy-safe warnings. It never retains staged content.

Commit requires a matching immutable confirmation, reacquires the mutation
gate, repeats inspection and staged validation, and rejects changed archive or
live-state fingerprints. Before any live replacement it publishes a no-clobber
recovery ZIP outside the application root containing exact current catalogued
bytes and reads that archive back through the hostile-input validator, then
atomically writes and flushes the excluded restore journal. Exact
manifest destinations are replaced without adjacent `.bak` files. Any normal
failure rolls every candidate back; process interruption leaves the journal so
`main.py` completes idempotent rollback before cleanup or loading on the next
startup. Backup and standalone retirement cleanup refuse to run while that
journal remains unresolved. Commit validates the full expected catalogued
overlay before and after aggregate reload; rollback verifies the complete
pre-restore live-state identity. Recovery does not require the pre-restore
configuration to be valid or required files to exist.

No mutating CLI, merge, selective import, path remapping, migration, or
cross-process exclusion exists. Restore is therefore exposed only inside the
running launcher process.

### `backup_restore_ui.py`

Owns the thin Phase 5 Tkinter orchestration boundary used by Configure. It
receives the launcher's canonical `AppDataPaths`, maps the two user options to
`BackupOptions`, and calls only `create_configuration_backup`,
`inspect_restore_archive`, and `commit_restore`. Preview rendering consumes the
content-free plan's catalog-relative paths, sensitive categories,
compatibility state, and privacy-safe warnings; it never opens payloads or
reimplements catalog, validation, hashing, staging, archive, or transaction
logic.

One bounded non-daemon worker serializes backup, inspection, and commit. A
modal progress child prevents conflicting Configure edits and duplicate starts;
the result queue returns every Tk operation to the UI thread. Commit has no
cancel path after confirmation. Successful restore closes the stale Configure
workspace and invokes the launcher's complete reload. A completed rollback
leaves Configure usable; incomplete rollback closes Configure, hides the
launcher, blocks reopening configuration, and requests process exit so startup
recovery can run. Main-window exit is also refused while the archive worker is
active; if incomplete recovery waits for an existing Work Item write, the
launcher exits as soon as that write finishes.

### `configuration_check.py`

Provides a read-only project validation report and command-line exit status. It
is a thin compatibility adapter over `configuration_snapshot.py`: structured
issues become the existing error and warning tuples and snapshot counts become
the existing report counts. `check-context-palette.bat` runs this validation
before source compilation and the complete unit suite.

### `retired_feature_cleanup.py`

Owns narrow, idempotent migrations for deliberately removed local features.
Setup and application startup remove retired action records and their references
from ignored local actions, contexts, quick buttons, and palette state. It also
normalizes legacy Draft/Trusted actions to Active, converts old copy-only URL
builders to prompted copy-and-open actions, and changes converted Inbox items
to Converted. Every
changed file is written through `persistence.py`, preserving its previous
contents as an ignored `.bak`. The migration stores and logs aggregate counts
only; it does not inspect credential secrets or delete legacy snapshot files.

### `configuration_window.py` and `configuration_data.py`

Provide the guided configuration workspace and its persistence operations.
Action creation starts from the executable built-in action catalogue, which
includes a concrete example for every type. Every My configuration and Built-in
action type is editable. Editing a Built-in action requires acknowledging that
its file is tracked by Git and changes starter defaults; the warning also
prohibits personal paths, secrets, and private work details. Personal Contexts
can assign unlimited Action and Work Item membership plus slots 6–0, and personal Quick actions can
reference an ordered mix of existing actions and discovered Work Items without exposing
technical IDs. Built-in contexts
and Quick-action records are editable after the same developer-impact warning.
Writes use the same atomic JSON
replacement path as the rest of the application.

The launcher passes its canonical `AppDataPaths` through the optional
ConfigurationWindow integration adapter to the dedicated Backup and restore
panel. Existing direct constructors remain compatible by deriving the same
paths from the Built-in Actions location. Window close and Escape are refused
while archive work is active. Restore success destroys the workspace before
launcher reload so no editor keeps stale projections.

Personal Contexts assign an ordered mix of Actions and stable Work Item
references. Their preferred slots 6–0 use the same typed Palette-item reference
as mixed Quick-action targets. Legacy pins 1–5 remain loadable and writable in
palette state but are not projected or configurable. Quick-action groups remain global and have no Context visibility
field; the shared reference boundary permits, but does not imply, that future
feature.

Action creation starts from the educational **Action types** catalogue, the
launcher **Create Action** or Configure **New Action** searchable type chooser, or a conservative
**Create from Input** suggestion beside Input / Output. The suggestion route uses
selected text first, requires one clear supported target, and prepopulates
the existing form with a visible review notice. It does not change the general
type chooser or bypass confirmation. All routes
open the same `ActionDialog` and use the same atomic Action/Context-membership
persistence operation; the quick chooser is modal and never writes state on
cancel. Action creation and editing refresh every Configure view derived from actions,
including Context and Quick-action summaries and diagnostics. Action
creation routes owned by other launcher windows reload an already-open
Configure workspace from storage without raising or replacing that window.
Configure, Inbox conversion, document harvesting, and cheat-sheet promotion
all persist action context choices through `context_membership.py`.
All action-type editors use one compact vertically scrollable canvas body with
a fixed save/cancel footer. Ordinary labels sit beside their fields, action
type and field explanations use keyboard-accessible tooltips/on-demand help,
and multiline content retains an appropriately sized editor. The embedded form
tracks the canvas width, recomputes its scroll region when operation-specific
fields change, handles mouse-wheel input without stealing scrolling from
multiline text widgets or comboboxes, and brings a newly focused field into
view for keyboard traversal.

Configure uses a persistent left-hand task navigator and an internal
`ConfigurationPageStack` content host. The stack preserves the existing stable
section indexes and direct navigation routes without creating a native tab
strip that Windows themes can render unexpectedly. The navigator visually
groups frequent **Set up** destinations above lower-frequency **Support**
destinations while retaining all eight stable routes and shortcuts.
The first section is a navigation-only **Start** page. It owns no domain
state and performs no persistence: its six primary task buttons either invoke
the existing Action chooser or select Actions, Contexts, Quick actions, Work
Items, or Backup and restore. Secondary buttons select the Action-type
catalogue and Diagnostics. Explicit launcher routes bypass Start and retain
their exact section, selected-record, focus, singleton-window, and save behavior.

Configure list tables use the shared `treeview_utils.py` scrollable-tree
builder. Actions, contexts, Quick actions, and discovered Work Items retain
visible final columns and consistent vertical scrolling at the supported
minimum window size.

The Actions page keeps its single primary **New Action** command in the page
header and moves the bulk create/update Excel routes, website-link Harvest,
and type catalogue behind **More Action tasks**. Global pin configuration is
retired. Selection titles are display-bounded so arbitrary
names cannot displace Action commands at minimum width. Tags remain searchable
and appear in the selected-Action strip instead of consuming a permanent table
column. Active and legacy inactive records share one table; the latter have an
explicit non-color-only **Legacy inactive** status and deletion is their only
mutation.

The Contexts and Quick actions pages use the same visual hierarchy without
introducing shared domain state: a page title and purpose, one primary creation
command, Find, a dominant scrollable table, and a selection-aware card. The
Contexts table prepends a synthetic **General — All items** row. It is not a
`ContextDefinition`: its membership is computed from every Active Action and
available Work Item, while its optional 6–0 preferences are read from and
written only to local `PaletteState`. Its selection card hides Delete and opens
a shortcuts-only editor; clearing all choices removes both legacy and typed
General overrides so normal automatic ordering resumes. Persisted definitions
named General are ignored by focus resolution, and the ordinary Context editor
reserves that name. Specific Context cards preserve the existing Context-ID
lookup and deletion boundary, and their editor presents membership before
optional context shortcuts 6–0. The Quick
actions card derives enabled commands from the selected record's ownership and
depth: configured records may be edited, moved, or deleted; automatic groups
route to filtered Actions and automatic leaves route to their owning Action.
All existing command-surface persistence and ownership validation remains in
the original callbacks.

The Work Items page selects one current source and keeps **Refresh** visible.
**Manage sources…** exposes Add, Edit, Remove, and creation-template commands
through their existing persistence paths. Remove disconnects local discovery,
never deletes external folders or files, and deliberately retains tags,
Context membership, slots, and Quick-action references for identity-based
reconnection. Edit and Remove are disabled when no source exists, while Add
and template setup remain reachable. The complete
folder path, availability, Work Item / Type / Project table, and selected-item
details remain visible in the main page.

Backup & restore remains the same background-worker and recovery boundary, but
its visible stages are literal: **Create backup…**, **Choose backup to
inspect…**, then the disabled-until-inspected destructive **Apply inspected
changes…**. Diagnostics renders the same privacy-safe summary in a read-only
scrollable text widget; Refresh is secondary and **Copy safe summary** is the
primary outcome.

Every Configure field that references an existing Action uses the shared
searchable Action picker. Its readonly field keeps the selected human-readable
label visible; **Find…** opens a keyboard-operable filtered list with a result
count. Context membership, slots 6–0, and configured Quick-action assignments
reuse this picker.

New Actions, Contexts, and Quick-action menus explicitly choose **My
configuration** or **Built-in** and default to My configuration. **Standard**
is a fixed first root: it may expose supported content editing, but cannot be
moved or deleted. The
Quick actions section is a hierarchical editor. Persisted menus, Quick actions,
and submenus can be added, renamed, deleted, and reordered. The same tree also shows the
generated Passwords, Folders, and Prompts hierarchies with editable action
leaves; those generated records are reorganized through the owning action's
`quick_action_path`, not through `command_surface.json`.
A menu always contributes one launcher. Menus and their items may each own
ordered Actions; submenus recurse
to a validated maximum depth of three below the menu. Selecting a menu or item
establishes the parent for **New Quick action…** or **New submenu…**, while stable IDs remain
unique across the complete group tree. Left-click/Enter/Space browses; launcher
right-click exposes related Add/Organize commands. Inside a posted native menu,
left-click executes the exact Action entry and right-click dismisses the menu
before opening that exact Action for editing. Submenu right-click routes back
to the same stable Configure branch.
Personal items store mixed targets in one ordered list. Each Work Item target
uses a stable source/folder reference. Execution resolves those references
against the current immutable index and delegates to the same
workbook-first, folder-fallback opening boundary used by Work Items mode.
Unavailable references remain configured and recover when their source returns.
Built-in Quick actions may reference only Built-in
actions so starter configuration cannot depend on ignored machine-local
records or Work Items; My configuration Quick actions may reference either
action storage location or a Work Item.
The configuration checker enforces the same boundary recursively for manually
edited JSON.

Context, Quick-action menu, and Quick-action item dialogs keep Save/Cancel in a
fixed footer and place their forms in a vertically scrollable canvas. This
keeps storage, membership, context shortcuts, assignments, and summaries
reachable at 125%/150% scaling and on short monitor work areas. Focus entering
an off-screen field scrolls it into view; text, list, and combobox controls keep
their own native wheel behavior.

Automatic-menu Add commands reuse the ordinary `ActionDialog` and persistence
path. They constrain only the Action type and preselect `quick_action_path`; the
normal storage, name, description, Contexts, tags, target, validation, and
review fields remain present. The Action form renders that tuple through the
shared read-only tree chooser rather than a free-text delimiter field. The
Quick-actions organizer uses the same chooser for destination-first assignment
and branch move/rename. Saving or organizing then rebuilds both the launcher
menu and Configure tree from the single Action source of truth.

### `context_deletion.py`

Owns dependency-aware context deletion and renaming across the defining file,
legacy project/local action metadata, per-Context slots, and compatibility-only
palette focus data. Canonical action membership is removed with the defining
context itself. A material rename first writes a safe intermediate definition
containing both names, updates legacy and palette references, and then removes
the old definition. The final write preserves the true pre-rename definition
as the context file's backup.

### `action_deletion.py`

Owns dependency-aware Action deletion. It validates and inventories Context,
Quick-action, legacy-pin, and context-slot references before the UI asks for
confirmation. Direct deletion accepts an Active record or a legacy inactive
`Archived` record, cleans those internal references, and removes the record in
one best-effort multi-file transaction. It snapshots the exact bytes of every
participating file before the first write. A failed write restores every attempted file; an
incomplete rollback is explicit and directs recovery. Every individual write
still uses atomic replacement and local backup behavior. A Quick-action item
with no remaining target is removed; removing a legacy primary Action preserves
the remaining menu order without creating a new launcher default.

`actions.py` exposes separate combined projections for this boundary: stored
loading includes Active and legacy inactive records with cross-owner duplicate-ID
validation, while ordinary combined loading remains Active-only. Configure
uses the stored projection only for its Actions table and deletion controls;
all runtime discovery and assignment pickers continue to consume Active
Actions.

### `palette_state.py`

Stores and calculates launcher organization.

- Legacy `focus_context` is still validated, loaded, and serialized for
  compatibility, but it does not select current launcher Context state.
- Legacy `pinned_action_ids` for slots 1–5 are still validated, loaded, and
  serialized unchanged, but no runtime or Configure projection consumes them.
- Slots 6–0: top five Actions or Work Items for the active Context filter;
  internal slot 10 is displayed and invoked with the physical `0` key.
- Unfilled context slots use only other Actions or Work Items belonging to the
  active Context and otherwise remain empty. **All contexts** uses General,
  which treats all Actions and available Work Items as global members; a
  specific Context never borrows unrelated items.

### `command_surface.py`

Loads and validates global quick-action groups and their compact items from
shared and local JSON. Legacy `rows` and `nested_menu` presentation values remain
valid for old files and backups, but both render as menu launchers. A group and
each recursive item retain ordered actions;
items may contain child items to a maximum depth of three. Traversal helpers
provide stable index/ID paths, recursive counts, and complete action-reference
enumeration to rendering, Configure, deletion, and validation. Groups reference
existing action IDs. A personal item may store an ordered `targets` list that
mixes action IDs with validated Work Item source IDs and direct relative folder
names. Legacy action-only fields and the initial single `work_item_ref` form
remain readable. Work Item entries reference the existing constrained opener
rather than defining a second execution language. Duplicate
group IDs and duplicate item IDs anywhere within one group are rejected
case-insensitively.

The module also owns the canonical legacy-primary-first, duplicate-free action
ordering used by menus, Configure, and configuration validation. “Primary” is
an ordering compatibility field only; launcher controls never execute it
implicitly.
`CommandTarget` remains a compatibility export of `PaletteItemReference`.
Command groups do not currently store Context visibility or membership.
The combined Action-form chooser and saved-Action Placements manager work
against these existing root/item Action reference fields. They do not introduce
a placement table, change the schema, or migrate records. A single Active Action
may be referenced by zero or many
configured nodes, while its automatic Passwords/Folders/Prompts membership is
derived independently from Action type and its nested location from
`quick_action_path`. Existing Work Item targets, other Actions, child menus,
and target order are preserved.
At render time, `launcher.py` fixes Standard first, partitions configured groups
by their recorded source path so personal groups precede shared groups while
preserving order within each file, then appends the automatic Action-bound
groups. Every launcher opens a menu; top-level choice counts inform its tooltip
but never select or execute a default.

### `tooltips.py`

Owns delayed tooltip behaviour for ordinary widgets and individual listbox rows. Keeping these presentation helpers outside `launcher.py` prevents the main application orchestrator from also owning reusable hover-window mechanics.

### `style.py`

Owns the shared native ttk theme, Segoe UI font policy, grey/teal/aqua palette, and hover/focus state maps. Classic Tk widget defaults are applied through the root option database. The module changes presentation only; widget construction, layout, geometry, and action behaviour remain in their existing owners.

Palette-specific scope, primary-command, and toolbar styles keep cosmetic
changes separate from Configure navigation, result selection, and destructive
commands. Bitmap-toolbar padding follows caption-font metrics so fixed-size
icons align with text controls. Input / Output's classic `tk.Text` options are
applied locally rather than changing every editor. Quick launchers retain
their existing label bindings and a single theme-rendered right indicator.

Shared result-row color keys and Treeview paint tags alternate neutral and
Context-shortcut green bands in production and the inert mockup. Shortcut
identity tags carry no competing background; each row has exactly one paint
tag. Listbox rows use the same palette keys. Selection remains theme-owned;
row height, labels, order, and execution mappings are unchanged.

### `ui_icons.py`

Creates and retains portable 16×16 Tk bitmap icons for compact controls. It is
presentation-only and owns no application behavior or persisted state.
The document-plus Create Action icon uses the ordinary creation callback, not
the separate Create from Input wand. Toolbar pictograms share a restrained
monochrome stroke treatment. Action-type glyphs remain in `action_types.py`,
the same source used by result labels and the generated type catalogue;
no image-backed result-widget replacement or persisted icon data is required.

### `ui_mockups.py`

Owns a standalone, inert real-Tk gallery used to validate proposed visual
structure before production UI batches. It reuses only the shared theme and
embedded bitmap icons, renders frozen fictional Actions and Work Items, and
keeps search, selection, Context/filter, sequence-state, source, and page
interactions in memory. It does not import launcher orchestration, persistence,
clipboard, OCR, target inspection, or operating-system dispatch boundaries.
`run-ui-mockups.bat` launches the gallery separately from the resident app;
`tests/test_ui_mockups.py` exercises its supported size and simulated scaling
matrix. The mockups are review evidence, not production behavior.

### `help_window.py`

Owns the reusable in-app Markdown document viewer. It renders CommonMark plus
tables and strikethrough through `markdown-it-py`, then presents the generated
document through an embedded `tkinterweb` HTML frame. This provides responsive
bordered tables, nested lists, code blocks, block quotes, complete heading
levels, and consistent document spacing. Raw source HTML, JavaScript, forms,
objects, remote navigation, automatic URL linkification, and image/resource
loading are disabled. Clicked navigation is resolved again by Context Palette
and restricted to `.md` files beneath the viewer's local document root.

The viewer also provides rendered-document search, a Documents menu, and
explicit Back, Forward, and Home history. `launcher.py` opens Help and the
authoritative Keyboard Shortcuts page through this component and injects an
opener into the normal action dispatcher so existing `.md` open-file actions
use the same viewer. The Edge control locates Microsoft Edge through `PATH` or
standard per-user/system installation folders and starts it with only the
current validated local file URI. This supports extension-based Markdown
rendering without making Edge a requirement for the embedded viewer.
Non-Markdown file actions retain the platform opener.

### `cheat_sheet_window.py`

Owns the searchable Cheat Sheet secondary window, including selection, preview,
and promotion to a permanent local Active action. `launcher.py` retains loading and
orchestration responsibility.

### `inbox_window.py`

Owns the captured-item Inbox window and the form that turns one Inbox item into
a permanent personal action. It coordinates the existing Inbox and action
domain helpers, context/tag pickers, and attended AI guidance without depending
on `LauncherApp`. The launcher opens this window and retains compatibility
imports for existing callers.

### `hotkeys.py`

Native Windows hotkey and selection-copy support using `ctypes`.

- Registers one-key `F9` and fallback `Ctrl+Alt+P` with `RegisterHotKey` and no-repeat behaviour.
- Runs the Windows message loop on a daemon thread.
- Queues activation back to `LauncherApp`; it does not manipulate Tk widgets from the background thread.
- Sends a constrained `Ctrl+C` sequence before the palette takes focus.
- Captures cursor coordinates and the nearest monitor work area in the hotkey thread, then uses the cursor as the palette's top-left anchor. The position is clamped only when needed to keep the complete window on-screen.

### `contexts.py`

Loads and validates standalone Built-in and My configuration Context
definitions. A definition owns Action membership plus optional stable Work Item
references and up to five typed preferred Palette items. Built-in definitions
reject personal Work Items. `focus_model.py` combines definition-owned Action
membership with legacy Action-side memberships for backward compatibility and
resolves mixed preferred slots. Explicit per-machine choices in `palette.json`
override configured defaults.

### `focus_model.py`

Owns pure Context membership and slot-bank policy independently of Tk and
persistence. It discovers available Context names, resolves legacy Action-only
slot values and typed mixed slots 6–0, reconciles saved slots against current
explicit membership, handles unavailable-context fallbacks, and selects
canonical visible Actions plus configured Work Item membership. Stale
references are ignored in memory rather than rewriting personal configuration
during reload. The launcher asks for General's projection under **All
contexts** and the matching specific projection otherwise; the same result
supplies Context-filtered retrieval and empty-Find shortcut rows. This remains
the replacement boundary for future Context-model changes.

### `work_items.py`

Owns the pure, UI-independent first phase of Work Items discovery. Immutable
source, reference, and discovered-item models validate stable source identity
and absolute
paths. The scanner enumerates only direct children of one configured
`workitems` folder, rejects unavailable sources without creating them, skips
names ending in at least five hyphens before inspecting the child, and never
recurses. Each eligible folder is parsed without making successful parsing a
condition of discovery. Only an exact case-insensitive `<folder-name>.xlsx`
file directly inside the folder becomes its matching workbook; otherwise the
folder is the default target. Persistence, caching, refresh coordination,
search integration, and UI remain outside this domain boundary.

### `work_item_storage.py` and `work_item_refresh.py`

Provide private Work Items persistence and background refresh. Storage strictly
loads and atomically writes ignored
`local_work_item_sources.json` and `local_work_item_metadata.json`. Metadata
identity combines a stable source ID with one direct relative folder name;
absolute paths exist only in the machine-local source file. Personal tags are
normalized and deduplicated.

Refresh combines independently discovered sources into an immutable in-memory
index. A failed source retains only its own previous successful items while
available sources refresh normally; removed sources leave the index. No index
is written to disk. The background coordinator places completed immutable
results on a thread-safe queue. Future Tk orchestration must call `drain()` on
the main thread, so worker code has no Tk callback or widget access. Unexpected
worker failures are logged and converted into an immutable error result that
retains each source's last-known rows; the coordinator never remains
permanently busy. A local
500-folder direct-scan measurement completed in 21.9 ms on 2026-07-21, providing
no evidence that a private persistent cache is warranted.

### `work_item_configuration.py`

Owns the guided **Work Items** Configure panel and its source/details dialogs. It
validates existing absolute source folders, generates stable local IDs, reports
availability, performs explicit bounded refreshes, and persists edits through
`work_item_storage.py`. One source selector drives a full-width discovered-item
table; the selected source's complete path and availability remain visible,
while a compact selected-item strip exposes folder, Context, tag, edit, and
open-folder actions. Search is local to the chosen source and includes those
same visible identity facets. The editor shows both personal tags and
membership in existing personal Contexts. Context membership remains
owned by `local_contexts.json`; the Work Item route updates the same records,
removes stale preferred placement when membership is removed, and restores the
previous Context bytes if the paired metadata write fails. **Organize → Forget
Palette organization…** delegates complete cleanup to
`work_item_organization.py`; source disconnection is a separate operation and
retains that organization. Configure scans use
the existing background coordinator;
concurrent requests coalesce into one subsequent latest-state refresh. The panel
uses a weak completion callback and ignores late results after its Tk container
is destroyed. Existing-source management never modifies work folders or files;
new-item creation delegates its guarded write to `work_item_creation.py`.

### `work_item_organization.py`

Owns inspection and transactional removal of one Work Item's personal Palette
organization. A typed source/folder reference is removed from local metadata,
personal Context membership and preferred placement, palette context slots,
and personal Quick-action targets; Quick-action items left without a target are
removed. Every participating file is loaded and schema-validated before the
first write, writes remain under the shared configuration mutation gate, and a
failed write restores the exact original bytes of every attempted file. The
service has no external source path input and therefore cannot delete or edit
the Work Item folder, workbook, files, or workbook Inbox.

### `work_item_creation.py`

Owns UI-independent name suggestion, Windows filename validation, collision
refusal, and guarded template copying. It creates one new direct-child folder
and copies the configured generic `.xlsx` to exact `<folder-name>.xlsx`. If the
copy fails, it removes only partial output created by that attempt. The dialog
owns confirmation and optional local-tag saving.

It also owns collision-safe creation of a missing exact-name workbook inside an
existing discovered Work Item. This narrower path copies the configured generic
template with exclusive creation and never creates or removes the Work Item
folder.

### `work_item_inbox.py` and `integrations/Append-WorkItemInbox.ps1`

Provide the constrained boundary for sending Input / Output to a selected Work
Item's exact matching `.xlsx`. The Python layer validates and bounds one
timestamp/text/link/source record, accepts only the exact direct-child workbook,
optionally delegates collision-safe creation to `work_item_creation.py`, and
runs the operation through a single-flight background coordinator. Completion
is delivered to Tk only through main-thread polling. Expected and unexpected
worker failures both enqueue a safe completion, ensuring that controls and the
Quit guard return to their normal state.

The fixed PowerShell integration receives size-limited JSON through standard
input so captured content is absent from command-line history and temporary
files. It uses installed Microsoft Excel automation, opens only `.xlsx` with
link updates disabled, creates or selects the exact `Inbox` sheet, and appends
columns A–D. Text and source cells are explicitly text-formatted to prevent
formula evaluation. It does not accept script, command, worksheet, or arbitrary
workbook targets from the user. Workbooks that Excel exposes through its
registered automation instance remain open;
workbooks opened by the integration are saved and closed. A workbook locked in
another Excel instance fails safely as locked rather than opening a read-only
copy. No third-party Python package or direct OOXML rewrite is introduced.

### `work_item_file_copy.py`

Owns the UI-independent Work Item file-copy boundary. It accepts one exact
absolute file path from Input / Output, rejects folders and mixed/multiple
lines, validates the selected Work Item folder, and derives the destination
only from the source filename. It never accepts a destination name or
overwrites an existing entry.

Content is copied off the Tk thread to a unique temporary file inside the
destination folder and renamed into place only after completion. Errors remove
only temporary output created by that attempt; source and existing destination
files are never changed. Metadata preservation is best effort because not all
local and network filesystems support the same Windows attributes. A
single-flight coordinator returns completion to Tk through main-thread polling.

### `file_transfer.py`

Owns the UI-independent outbound **Send to…** boundary. It accepts 1–100
nonblank Input / Output lines, each one matching-quote-tolerant absolute
existing regular file, and rejects folders, prose/relative paths, URLs,
duplicates, and unavailable sources before writing. Planning validates one
existing absolute destination folder, reads bounded source/destination
snapshots, and assigns one exact destination per source. Existing or
same-batch names receive deterministic `(1)`, `(2)` suffixes by default;
explicit overwrite plans the unsuffixed existing file as a replacement.
Same-location sources are skipped rather than duplicated.

The reviewed plan fingerprints source content/identity, destination state,
mapping, disposition, and overwrite choice. Execution replans before effects,
stages every complete source in a private destination-side temporary file,
rechecks source hashes and reviewed destination state, then uses no-clobber
creation or atomic reviewed replacement. It cleans its own temporary files and
returns exact created, replaced, skipped, stopped, and failed effects. A later
publication failure does not roll back earlier completed copies. The
single-flight coordinator performs filesystem work off the Tk thread and
delivers completion only through main-thread draining; it never logs source or
destination values.

### `webpage_pdf.py` and `webpage_pdf_window.py`

`webpage_pdf.py` owns the UI-independent webpage printing boundary: one bounded
HTTP(S) URL, installed Edge/Chrome discovery, an isolated temporary browser
profile, a fixed headless argument list without a shell, cancellation and a
finite timeout. It uses the browser's normal security checks and never reuses
the user's signed-in profile. Completed output is checked as PDF and published
under a new filename without replacing an existing or concurrently created
file. PDF validity does not establish successful website content capture.

`WebpagePdfWindow` owns one worker, cancellation and an attended result window.
The worker returns through a queue; only Tk polling updates widgets. Busy state
includes scheduled startup, preventing Quit during a pending or running job.
The launcher snapshots the whole Input / Output field before its save picker,
then dispatches a manual `WebpagePdfRequest`. It preserves Input / Output and
clipboard, rejects overlapping PDF jobs, and clears window references by
identity. For HTTP(S) input, Send to shows PDF creation instead of file-copy
destinations. This is a workspace function, not a workflow engine or Drop route.

### `file_transfer_window.py`

Owns the centered attended Send-to workflow. Selecting a destination is enough
confirmation for a conflict-free plan and starts copying automatically.
Conflicts render exact mappings, an unchecked **Allow overwrite** choice, and
one effect-labelled copy button; no redundant message box is added. The fixed
footer remains visible while review/result content scrolls. The window exposes
Stop remaining, exact partial-result guidance, Open destination folder, and a
busy state used by Launcher Quit protection. Only a completely successful
result may add that destination to the launcher's bounded session-only recent
list.

### `vscode_integration.py`

Owns the UI-independent, non-copying VS Code receiver exposed under the
Input / Output **Send to…** menu. It accepts at most one bounded nonblank line,
allows matching outer quotes, requires one existing absolute regular folder or
file, and resolves the path without interpreting command text. A folder remains
the target; a file is reduced to its existing containing folder.

The adapter percent-encodes that resolved folder into a `vscode://file/` URI
and asks Windows to open the registered protocol through `ShellExecute` via
`os.startfile`. It does not discover or run a VS Code executable, copy or write
files, change Input / Output or the clipboard, execute an `open_folder` Action,
persist receiver/source state, or define a general receiver/plugin contract.
Missing protocol registration is contained as an actionable, sanitized error.

`launcher.py` builds destinations dynamically from the currently selected Work
Item, Context-relevant Active `open_folder` Actions, all Folder Actions,
discovered Work Items, recent successful destination folders, and a one-off
folder picker. A separate **Open with** section exposes the constrained VS Code
receiver only when Input / Output has one nonblank line. Using an `open_folder`
Action as a copy destination never changes its ordinary run behavior. Input /
Output is snapshotted once when a destination is chosen and is not rewritten or
synchronized through the clipboard. Folder Actions that require clipboard
template expansion are excluded with visible guidance; Send to never resolves
those tokens with an empty clipboard. Fixed relative paths and `file:` URIs use
the same local-folder resolver as ordinary Action execution.

`LauncherApp.quit_app()` checks both Work Item write coordinators and the
active Send-to workflow before
stopping the hotkey, instance server, or Tk root. A running file copy or Excel
Inbox update blocks complete process termination with an actionable warning;
ordinary Hide remains available. This keeps daemon-backed work from being
terminated by the application's own Quit control before completion is
delivered.

### `excel_automation.py`

Provides the optional machine-local boundary to the separately installed
Python Excel engine. It accepts only exact existing absolute `.xlsx` paths
from Input / Output or the general drop intake (up to 100 closed workbooks),
then performs the engine's `describe`, `plan`, and reviewed `execute` protocol
off the Tk thread. The same bounded client also supports direct live-Excel
inventory/formatting plus the `describe_capabilities`, `preflight_live_columns`,
`plan_live_column_conversion`, and `convert_live_column_representation`
version-1.0 operations; live token and sample data remain session-only.
Standard input carries structured requests; stdout and stderr are drained
concurrently with bounded capture, so a verbose child cannot block the Palette
process.

`excel_automation` is an ordinary constrained Action type for discovery,
Contexts, tags, and Quick-action menus, but it is not eligible for sequences
or the ordinary ShellExecute executor. Planning obtains required worksheet and
output-folder parameters and presents the engine's exact Input → Effect review.
When no explicit launcher is configured, discovery checks only the exact
direct sibling `python-excel\python-excel.bat`; it never searches PATH or a
drive and does not persist the detected path. After capability validation, the
first workbook's parent is the deterministic initial output folder. Blocked and
ready views retain an explicit **Choose another output folder…** override.
Execution receives the reviewed fingerprint rather than a recreated plan. The
host requests the exact `excel.export_workbooks_to_csv` automation version
`2.0`; it never allocates a CSV filename itself. With **Allow overwrite** off,
Python Excel returns the first collision-free path (`report.csv`,
`report(1).csv`, `report(2).csv`, and so on). With it on, Python Excel targets
the unsuffixed name and classifies each output as `create` or `replace`. The
review retains those exact dispositions, create/replace totals, invocation,
and fingerprint. Source workbooks are never mutated.

The result envelope, not the child exit code, determines the attended outcome.
`succeeded`, `failed_before_effect`, `failed_after_partial_effect`, stale-plan,
and unknown-after-process-loss states have distinct presentation. Execution
uses the identical reviewed invocation plus its expected fingerprint. A stale
plan (`conflict.automation_plan_stale`) must be planned and reviewed again; the
host never picks a different suffix or retries it. Successful and partial
results distinguish confirmed `outputs_created` from `outputs_replaced`;
partial and unknown outcomes are never retried automatically. The engine stages
the complete batch and publishes reviewed replacements atomically per file,
but does not create replacement backups or claim batch rollback. There is
intentionally no progress, cancellation, live-Excel, or rollback protocol: one
subprocess owns a batch. The configured engine path is stored only in ignored
`data/local_excel_automation_settings.json`.
Absence, misconfiguration, or a failed engine leaves every non-Excel feature
available.

### `excel_live_target_selector.py`

Owns the one reusable already-open Excel target selector used by both live
workflows. It creates disambiguated workbook labels, prefers the workbook from
the captured F9 Excel process and title when that choice is unambiguous, falls
back to Excel's active visible worksheet, and renders the common workbook,
worksheet, and inline **Refresh** controls. It also owns the common rule that a
**Return to Excel** command is offered only when the captured handle's process
appeared in the latest inventory. The component does not decide mutation
policy: direct formatting adds its all-visible scope and blocks AutoSave at
selection time, while conversion may perform read-only inspection and lets its
authoritative plan block unsafe mutation.

### `excel_live_text_conversion_window.py`

Owns the centered attended Development/UAT workflow for Python Excel commit
`08af313` and retains the partial-effect result boundary introduced by
`54f1ab8`. It reuses the one bounded process client/coordinator, machine-local
launcher setting, and shared live-Excel target selector. Its sequence is exact
capability discovery, already-open workbook inventory, one visible worksheet, bounded paged physical-column
preflight, zero-write plan, reviewed fingerprint, and conversion. Columns are
identified by ordered physical index so blank or duplicate headers remain
distinct. All bounds, workbook tokens, column order, recovery path, and plan
fingerprint are correlated at the result boundary.

The engine, not Context Palette, chooses the default sibling recovery path and
creates/verifies the recovery workbook. An override triggers a fresh plan.
Formula or unsupported values in scope remain engine-authored blockers; a
precision-risk plan requires an explicit acknowledgement that lost digits
cannot be reconstructed. Execution is fail-closed unless the exact environment
value `CONTEXT_PALETTE_UAT_LIVE_TEXT_CONVERSION=1` was present at process
startup. Inventory, preflight, and planning remain read-only when the gate is
off. Success, known no-live-mutation failure, partial mutation, and unknown
process/protocol outcomes are distinct; no outcome is retried automatically.
Context Palette never saves or closes Excel and never persists tokens, samples,
workbook paths, or the actual machine-local launcher path in tracked data.

### `excel_live_format_window.py`

Owns the centered attended **Apply Excel format template** workflow against
the Python Excel engine at commit `e405e14`. It reuses the same optional,
machine-local launcher resolution as CSV export, inventories only already-open
Excel workbooks, and uses the shared target selector before offering a selected
visible worksheet or all visible worksheets. It has one fixed **Standard data** profile: Aptos 11 in the used
range, a row-1 header, freeze top row, and an AutoFilter only when none already
exists. Its **Apply** button is the one confirmation.

This is deliberately not a planner: it neither consumes Input / Output nor
creates a fingerprint, backup, recovery point, progress/cancellation channel,
or automatic retry. The engine requires AutoSave to be off; direct formatting
may clear Excel Undo. Context Palette never saves, closes, or launches Excel.
A stale inventory requires Refresh and reselection; partial or unknown process
outcomes tell the user to inspect Excel before deciding whether to run again.
When the main action captured an F9 destination handle, **Return to Excel** is
a best-effort focus request only. The workflow's coordinator keeps engine work
off the Tk thread. A disposable real-Excel one-worksheet smoke confirmed the
formatting path and preservation of an existing filter against that engine
commit.

### `excel_automation_window.py`

Owns the attended Tk workflow for the CSV automation without implementing
workbook behavior. It resolves the optional machine-local launcher and initial
output folder,
renders any worksheet requirements, presents the exact reviewed plan, and
uses one effect-labelled button on that review as the execution confirmation;
there is no redundant generic Yes/No dialog. The session-only **Allow
overwrite** checkbox defaults off and every change invalidates the prior review
and replans. Ready plans show the exact `create`/`replace` disposition, totals,
and a button such as **Replace 1 and create 2 CSV files**. It also distinguishes
successful, known no-effect, partial-effect, and unknown outcomes, while the
workflow-owned coordinator keeps subprocess work off the Tk thread.

### `single_instance.py`

Resident-process coordination through a localhost socket.

- Only the first process owns the port.
- Later processes send a show request and terminate.
- Requests may carry only `command`, `context`, and `search` string fields in size-limited JSON.
- Each accepted client has a short receive timeout so a stalled local connection cannot hold the listener thread indefinitely.
- Invalid commands and fields are ignored; the bridge cannot execute actions or shell commands.
- The port is derived from the project path to reduce collisions between workspaces.

### Windows integration boundary

`main.py` accepts optional `--context` and `--search` arguments. `integrations/Invoke-ContextPalette.ps1` provides the parameterized wrapper for Power Automate Desktop; the ordinary batch launcher remains argumentless.

The bridge is attended by design: it may reveal and filter the palette but
cannot run an action by ID. Any future unattended execution API requires its
own authorization policy, confirmation rules, structured results, and separate
security tests.

### `inbox.py`

Capture Inbox domain model and persistence.

- Creates clipboard captures.
- Loads and validates Inbox JSON.
- Updates maturity state.
- Permanently removes one explicitly selected capture through the same atomic
  JSON write boundary.
- Keeps captured material separate from actions until conversion.

The Inbox creation UI supports guided permanent `copy_text` and URL-builder
actions. It also exposes a confirmed **Delete capture…** command. Deletion
removes only the Capture Inbox record; a converted Action contains copied,
independent data and is never deleted with its source capture. Ask AI and
Harvest remain available under **Other ways to create**. Work Item workbook
Inbox rows are a separate Excel-owned surface and are not deleted here.
URL templates are validated through the same domain function used at
execution, and the dialog keeps its action footer outside the expandable form
so buttons remain visible at smaller window sizes.

### `ai_guidance.py` and `ai_guidance_window.py`

`ai_guidance.py` builds a user-previewable request from an Inbox capture, a
constrained prompt variation, and catalogue-owned type guidance. It parses
plain versioned JSON or exactly one complete JSON Markdown fence without
surrounding commentary. It accepts only the variation's catalogue-enabled
action types, rejects unknown fields, and creates actions through type-specific
validated Active-action constructors. Envelope errors reject the response;
proposal errors are reported individually so valid siblings remain reviewable.
A local example response supports evaluation without contacting an AI.

Untrusted AI response text has a 1,000,000-character ceiling enforced before
JSON parsing. The clipboard handoff applies the same limit before replacing the
response widget, avoiding unnecessary UI and parser memory amplification.

`ai_guidance_window.py` owns the attended clipboard handoff: choose guidance,
review and copy the request, paste an AI response, validate and select
proposals, and explicitly create permanent local Active actions. It also
exposes the local test-response path and per-proposal validation status.
Selected proposals are batch-validated before the local action file is written.
The window does not contact an AI provider or store credentials.

### `cheatsheets.py`

Structured local reference material.

- Loads and validates sheet JSON.
- Searches sections, labels, details, and tags.
- Promotes an individual sheet entry to a permanent Active action.

### `windows_credentials.py`

Native standard Windows/generic-credential and protected-clipboard boundary using
standard-library `ctypes`.

- Reads one exact `CRED_TYPE_GENERIC` target from the current Windows logon session.
- Frees the native credential buffer immediately after decoding it.
- Writes the password with Windows clipboard-history and cloud-upload exclusion formats.
- Captures the previous plain-text value and performs protected replacement
  while the clipboard remains open, eliminating a snapshot/replace race, then
  returns a sequence number so recovery occurs only if another application has
  not replaced the protected item.
- Arms delayed conditional restoration before destination focus and paste
  dispatch, so an input-dispatch failure cannot leave recovery unscheduled.
- Restores plain text after timeout or failure; an absent prior text value
  becomes a clear only for an originally empty clipboard. A clipboard with only
  non-text formats stops the operation before replacement. Rich, image,
  private, and delayed-rendered formats are not treated as generic memory and
  remain outside this first transaction boundary.
- Retains protected-clipboard tracking until an ordinary clipboard replacement
  completes, so a failed write cannot make the secret eligible for workspace
  synchronization.
- Retries a busy recovery, warns after bounded failures, and blocks orderly quit
  while the protected transaction remains unresolved.
- Never enumerates credentials, writes credentials, logs passwords, or exposes
  passwords to action JSON, Input / Output, preview, search, or AI guidance.

## Action model

An action currently contains:

```text
id
title (short name)
description
contexts
tags
type
value
state
arguments
working_directory
quick_action_path
```

`description`, `contexts`, `tags`, and `quick_action_path` are optional.
`quick_action_path` is accepted only for AI prompt, folder, and credential
actions and contains at most three labels. It controls presentation in the
corresponding generated Quick-action menu; it does not duplicate membership or
execution configuration. `title` remains the
backward-compatible stored field for the compact name shown in action lists;
`description` holds a longer searchable explanation that appears in hover and
Action info surfaces. Every action belongs to the virtual
General root even when `contexts` is absent. Specific context membership can be
shared by several contexts. Tags are normalized, case-insensitive discovery
facets and never define a hierarchy. Legacy singular `context`, `technology`,
and `task` fields remain readable for existing personal files, but application
writes use `contexts` and `tags`.

Guided action forms validate specific memberships against the currently loaded
context definitions and canonicalize their capitalization before saving.
Their shared context-membership control offers checklist selection while
retaining direct keyboard entry.
The same component offers existing-tag selection without restricting creation
of new tags.
Direct JSON loading remains backward-compatible and permissive so an older
personal action is not made unreadable merely because its context definition is
temporarily missing.

### Presentation versus search

Compact result rows show a type cue followed by the short name:

```text
↗ subject
⧉ subject
✦ subject
```

Every constrained action type owns a standard symbol in `action_types.py`. A
redundant leading command such as Open, Copy, or Convert is removed from an
existing title. The full icon and built-in type, contexts, tags, short name, and
optional description are shown in filters, Configure, delayed row help, and
Action info, so symbols are never the only explanation.

The full explanation path is:

```text
Contexts | Tags | Short name | Description
```

Search indexes short name, description, tags, contexts, type, value, and
maturity state. Multiple query terms use AND semantics. The tag menu applies an
additional exact tag filter.

This separation allows visual simplification without losing retrieval power.

Secondary application screens share a `780x600` default and `700x480` minimum
through `window_geometry.py`. Every ordinary application window resolves the
usable Windows work area of its own or its owner's current monitor, centers in
that work area, and reduces only when the monitor cannot fit its requested
size. This includes auto-sized Work Item dialogs and the larger Harvest
window. The main window uses the same compact screen-aware `780x600` default
and `700x480` minimum; F9 and Ctrl+Alt+P use the cursor to choose the monitor,
then center the palette in that monitor's usable work area. Compact selection
popups remain anchored to their control and move above it when needed. Native
menus and widget tooltips also retain their control-anchored placement paths.

The drop target is deliberately outside that centering policy. It is a
small non-transient Toplevel positioned near the lower-right screen edge,
movable by the user, and independently hideable. With the main root withdrawn,
Windows/Tk keeps this non-transient child mapped; the main palette is never made
permanently topmost to achieve that lifecycle. Unlike ordinary child placement,
its dynamic compact and expanded sizes use `window_monitor_work_area()` for the
monitor containing that specific Toplevel. Its content column reserves a stable
width, user-moved interior positions remain unchanged, and overflow is clamped
with native frame offsets so text, controls, and title buttons stay within the
usable work area.

The main content is one user-adjustable horizontal split. It starts at
approximately 40% for the command console and 60% for Input / Output, while
guaranteeing at least half of the default width to the workspace. The bounded
sash keeps both panes usable and preserves a user-adjusted ratio during later
resizing in the session.

The command console stacks discovery above the independently scrolling Quick
actions. Discovery shows seven result rows at the standard size so the complete
standard Quick-action grid remains visible. Item-scope navigation sits above
Find; one unified Filter menu shares the Find row; and Create Action, Edit, and Run/Open
form one stable row below the full-width results. All views offer Context and
tag filters. Actions adds type filtering; Work Items adds New item, To inbox,
Copy file, project filtering, Open, and Open folder through the same stable
surface. Quick actions
use two columns at the standard and supported minimum widths, falling back to
one only when the console is narrower. Its canvas height follows the rendered
row height instead of expanding; discovery owns the remaining vertical space
and its result list grows with it. Input / Output consumes nearly the full
right-pane height; its existing communication line sits at the bottom. Capture,
Inbox, Create from Input, and Text tools use bitmap-icon controls in the
workspace header. Configure, Help, and More follow Quick actions. Discovery
scopes, Work Items, and Run/Open retain text because their state must remain
immediately readable. Search text can be combined with one shared Context/tag
filter set and the active kind-specific type or project filter; credentials
remain selectable through the Action type filter and the fixed Passwords
Quick-action menu.

Each group renders in stable row-major order within a responsive one- or
two-column grid. The
tracked command surface contributes one **Standard** group containing every
active Built-in action exactly once across subject menus. Standard's nested
presentation renders one **Standard** launcher without a duplicate group
heading. Group actions become root commands; recursive menu levels
become native cascades; and actions assigned at any level appear before that
level's child cascades. Every configured group uses the same compact
group-labelled launcher, including legacy groups stored with `rows`.
Ignored local groups load after it and occupy the remaining editable positions.
Three application-owned action-bound groups remain separate from stored
command-surface configuration. **Passwords**, **Folders**, and **Prompts**
derive their complete membership from Active `paste_credential`,
`open_folder`, and `ai_prompt` actions. Their position is fixed beside
**Standard**, and each action's optional `quick_action_path` produces as many
as three native submenu levels. An empty path places the Action at the menu
root. The data model places no numeric limit on a node's ordered actions, but supports at most
group → level 1 → level 2 → level 3 → action and provides no search or
app-managed scrolling inside native menus.

Quick-action labels participate in keyboard focus. Left-click, Enter, or Space
opens the menu and executes nothing. Launcher right-click opens the same
menu's Add/Organize commands. Each posted menu and submenu keeps an entry-index
to stable target/branch mapping: left-clicking an Action executes that exact
entry; right-clicking it dismisses the native menu and schedules exact guided
editing. Work Item entries use the same live-reference opener and route their
right-click to the selected Work Item in Configure.
Empty search, Inbox, cheat-sheet, and command-surface states contain recovery
guidance rather than blank widgets. Reloads use a short busy cursor/status
state; local loading is intentionally not animated.

Ordinary widget tooltips respond to both pointer hover and keyboard focus. This
keeps the full names and explanations of compact symbol controls available
without expanding the fixed-size main-window layout. They prefer the space
below a control, move above it near the bottom edge, and remain inside the
virtual desktop, including secondary monitors with negative coordinates.

Configured and action-bound launchers share one mouse/keyboard contract. Every
Action leaf still uses the ordinary constrained executor; management callbacks
never invoke it.

## Supported action types

The current allow-list includes:

- `copy_text`
- `open_url`
- `open_file`
- `open_folder`
- `launch_app`
- `sequence`
- `paste_credential`
- `build_url_open`
- `build_url_selection_open`
- `transform_file_text`
- `transform_list_csv`
- `transform_text`
- `transform_slashes`
- `workspace_template`
- `ai_prompt`
- `open_windows_target`
- `excel_automation`
- `save_edge_score_pdf`

Action types that cause external effects use constrained implementations.
`launch_app`, for example, accepts an existing absolute `.exe`, fixed argument
list, and optional validated working directory. `paste_credential` accepts only
an exact standard Windows or generic credential target and requires a fresh
hotkey-captured destination, confirms the target window, and never accepts a
password in configuration.

## Input and output flow

```text
topmost drop target -> typed normalization --+
                                             |
External selected text                       |
        |                                    |
        | Ctrl+Alt+P -> Ctrl+C before focus  |
        v                                    |
captured_selection                           |
        |                                    |
        v                                    v
Input / Output workspace <---- Paste / manual edit
        |
        +-- transformation -> replace workspace + copy result
        +-- file-transform preview -> review/edit -> replace source or save as
        +-- URL builder -> prompt or consume workspace -> copy + open URL
        +-- Excel CSV automation -> describe -> plan -> attended review -> execute
        +-- Live Excel format -> inventory -> one attended Apply
        +-- UAT live text conversion -> capability -> inventory -> preflight -> plan -> execute
        `-- saved-text action -> clipboard -> fresh captured destination, or manual-paste fallback

Windows Credential Manager -- exact target --> protected clipboard --> captured destination
```

### Previewable Action sequences

`action_sequences.py` owns the pure `SequenceStep` model, structural bounds,
live reference resolution, immutable run plan, and readable ordered preview.
A sequence persists an explicit `steps` array containing only Action references
and waits. It can reference Active `open_url`, `open_file`, `open_folder`,
`launch_app`, and `open_windows_target` Actions. Nested sequences, clipboard
inputs, credentials, transformations, and missing or legacy inactive references fail
before any effect.

The Action editor adds, removes, and reorders existing Actions and bounded
waits without displaying technical IDs. The launcher resolves every reference,
shows one complete confirmation, and schedules each step through Tk so the UI
remains responsive. While a sequence is active, FocusOut auto-hide is suspended
and the palette remains above launched windows so step progress and the attended
**Stop remaining** control stay accessible. **Stop remaining** cancels only the pending callback;
already opened targets or started processes are not rolled back or terminated.
Deletion treats sequence references as blocking semantic dependencies,
not removable placements. Built-in sequences may reference Built-in Actions
only; personal sequences may reference either ownership.

Destination paste callbacks treat focus restoration and input dispatch as
separate failure points. Both restore the hidden palette. Ordinary saved text
remains on the clipboard for manual recovery. Protected credential paste
restores the prior plain-text clipboard value on failure or after 15 seconds,
or clears the protected item when no prior text existed. Sequence-aware
recovery yields to newer clipboard content and ignores obsolete callbacks.
Automatic-paste observability uses a fixed event schema containing only
category, outcome, and reason. It never accepts action values, clipboard text,
credential targets, usernames, passwords, or window titles. Successful and
clipboard-only outcomes use informational logging, unavailable destinations use
warning logging, and dispatch failures retain their exception at error level.

Input / Output is a permanent editable working text box, not action documentation. It synchronizes from the clipboard when shown normally and can be explicitly copied, pasted, cleared, transformed, or replaced by actions. Show-only drops use a separate reveal path that skips clipboard synchronization and places the normalized result. Configured drop Actions instead receive the snapshot directly, without editor staging; both routes invalidate stale captured selection/destination state. The outbound **Send to…** route snapshots exact path lines without changing Input / Output or the clipboard: copy destinations delegate reviewed background publication to `file_transfer.py`, while the one-path VS Code receiver delegates only registered-protocol opening to `vscode_integration.py`. Inline transformations apply to the selection, or the complete field when there is no selection, and copy their result to the clipboard. Pure transformation logic lives in `actions.py`; `workspace_panel.py` owns selection ranges, one-step Undo grouping, clipboard updates, menus, and a last-ten session history of meaningful complete states. Back/Forward navigation clears file-preview provenance rather than reconnecting historical text to a stale source hash. The launcher injects clipboard, status, and content-change callbacks and retains orchestration delegates. A selected item places its current-state **Input → Effect** summary in the slim bottom communication line; progress, success, and errors temporarily replace it. Hovering or clicking that line exposes the full structured explanation and current operational message.

The legacy generic `transform_text` action persists one catalogue operation key
and only that operation's ordered parameters. It remains loadable and editable
for compatibility but is no longer offered for new actions. New
`transform_file_text` actions persist a source path plus the shared catalogue
operation and its ordered parameters. Configure requires an existing decodable
text file when creating or editing one; loading remains tolerant when a
machine-local source is temporarily unavailable.

Execution reads at most 10 MiB, detects common Unicode BOMs plus ordinary
Windows text encoding, preserves exact decoded line endings, and rejects likely
binary content. It puts the transformed result in Input / Output without
writing the source. The preview retains the resolved path, source-byte hash,
encoding, and BOM. Explicit replacement rechecks that hash and writes through a
temporary sibling plus `os.replace`; a stale preview cannot overwrite a source
changed by another program. Save-as uses the same encoding-preserving atomic
writer. Literal replacement intentionally preserves an empty replacement.
Invalid JSON, delimiters, paths, file URIs, and parameter counts fail before
replacing the workspace or source file.

The transformation menu groups deterministic operations into Case, Whitespace,
Find and filter, Paths, Lines, Lists, Naming style, Data and encoding, and File
addresses. Line operations preserve the detected line-ending style and final
newline where applicable. List operations share one quote-aware tokenizer for
line, comma, tab, and semicolon input. Explicit plain, single-quoted-text, and
double-quoted-text comma formats leave detected numbers and `NULL` unquoted;
the SQL variant also wraps the result in parentheses. The compatibility
`transform_list_csv` Action retains its historical plain/all-values-as-strings
behavior.

Numbered Action dispatch is enabled only for physical Shift+6–0 while the Find
entry owns focus. Shift+1–5 and all number input in other widgets are ignored
by dispatch, making shortcut mode explicit and preventing accidental execution
while navigating or editing. The communication line never wraps; its stable
**Input → Effect** summary is bounded to 220 characters. Full structured Type,
Input, Effect, configured-value, and recovery information is retained
separately for a dynamic hover tooltip and click-open detail window. Editing
Input / Output refreshes the current preview without changing Action execution
semantics or treating a highlighted text range as Action input.

Shortcut numbers are intentionally omitted from result labels. Green rows map
top-to-bottom to context shortcuts 6–0 only while Find is empty; neutral rows
are ordinary results. A non-empty query removes shortcut promotion and sorts
the matching projection by relevance. Action and Work Item rows measure every
icon in the active Tk font, pad narrower symbols to one shared pixel column,
and render the short name directly without a dash. The flat mixed-result
Treeview layout omits the unused expand/collapse indicator. Standard editing
and transformations are available through the context menu and the visible
catalogue-backed **Text tools** menu.

## Context filter, slots, and result narrowing

The application implements one explicit transient Context choice rather than
automatic multi-context inference or a separate shortcut-context control.

```text
6–0  Active-Context Actions or Work Items (empty Find only)
other rows  relevance-ranked search matches
```

**All contexts** uses General's canonical membership and slot bank. Choosing a
specific Context in the unified Filter menu uses that definition's membership
and bank in every item-kind scope. Context and tag apply across All items,
Actions, and Work Items; Action type and Work Item project remain kind-specific.
Find, tag, type, and project narrow the projection without selecting another
bank. Tags remain independent filters rather than structural ownership. All
result-filter state is transient and never enters `palette.json`.

Configured Quick actions use Action IDs or an ordered personal mix of Actions
and stable Work Item references. The launcher renders fixed **Standard** first,
then personal configured menus, shared configured menus, and finally automatic
**Passwords**, **Folders**, and **Prompts**. The last three menus are pure projections over
Active first-class actions and their optional `quick_action_path`; creating or
deleting an action therefore updates menu membership without a
second configuration record. AI prompt execution still shares review-first
workspace/clipboard behavior with templates while retaining a separate type
identity for future prompt-specific evolution. Cheat sheets remain a
searchable reference subsystem and are opened as a secondary command from the
Help window rather than occupying a Quick-action slot.

Quick-action groups currently remain global. Context-based visibility or
grouping is deliberately out of scope; a later design can reference Contexts
without changing the typed Action/Work Item target identity.

Per-Context slot changes are applied in memory only after updated palette state
has been persisted successfully. A write failure keeps the prior assignments
and reports the failure to the user. Legacy pinned IDs and `focus_context` are
preserved unchanged for compatibility but never select current launcher state.

Context names in `context_slots` keys are resolved case-insensitively to the
current canonical spelling. This keeps older per-machine palette files usable
after capitalization changes. Unknown slot keys are preserved, and an exact
canonical key takes precedence if both spellings exist.

The longer-term context model includes identity, knowledge, capabilities, and
optional activation, with one explicit Context filter and possible supporting
contexts.

## Storage

All data is local and inspectable.

The logical entities, stable identities, cross-file references, derived state,
external-resource boundary, and implemented asset catalog are summarized in
the [data model](DATA_MODEL.md). Deterministic backup creation, the
UI-independent recoverable restore core, and the in-process Configure workflow
are implemented as described in the [backup and restore plan](BACKUP_RESTORE_PLAN.md).

### `data/actions.json`

Reviewed portable action records shared through Git.

Action IDs are unique case-insensitively within a file and across shared/local
files. This keeps legacy pin data, context slots, command-surface references,
and edits unambiguous.
New records store optional `tags`; specific context membership is stored only
in context definitions. Legacy `context` and `contexts` fields remain readable
for migration. Omitting them does not remove canonical membership because the
context files own it. General itself is always implicit.

### `data/contexts.json` and `data/local_contexts.json`

The Built-in file contains only shipped starter contexts; currently that is
**Developing Context Palette**. The ignored local file contains the user's
personal or work-specific Contexts and owns their Action and Work Item
memberships. General
is an implicit root rather than a stored definition.

### `data/command_surface.json` and `data/local_command_surface.json`

The Built-in file contains portable starter Quick-action groups. The ignored My
configuration file can add personal or machine-specific groups. Both refer to
actions by stable ID.

### `data/local_actions.json`

Ignored personal and machine-specific actions. New Inbox conversions and
cheat-sheet promotions are written here by default.

### `data/inbox.json`

Ignored captured material awaiting or recording conversion.

### `data/palette.json`

Ignored explicit per-Context slot references plus preserved legacy
`focus_context` and pinned IDs. Runtime reads and round-trips the compatibility
fields but does not use them to select current Context state or project global
pins.

### `data/cheatsheets/*.json`

Structured reference sheets.

Safe initial structures are tracked as `data/*.example.json` and copied by `setup-context-palette.bat`.

## Threading and responsiveness

Tkinter widgets are only accessed from the main thread.

- The hotkey message loop runs in a daemon thread and writes a lightweight queue message.
- The single-instance listener also signals through a queue.
- Shortcut reads and target-only `.lnk` resolution use one read-only daemon
  worker. The Tk thread polls its completed immutable result; the worker never
  calls Tk or launcher callbacks.
- The Tk main loop polls requests every 100 ms.
- No database, network service, web frontend, or heavy UI framework is initialized.

Application shutdown cancels every pending callback registered in the shared
Tk interpreter only after active Work Item and backup/restore operations have
cleared their quit guard. Short-lived child windows cancel their own delayed
focus callbacks when destroyed, so closing a dialog cannot leave an orphaned
Tcl timer behind.

Configuration reloads are skipped when active file existence, modification time, and size are unchanged. Typed search changes are coalesced over 40 ms before recalculating slots and rows.

After the fault-isolated first-start bootstrap establishes a usable baseline,
configuration reload is transactional in memory. Combined shared/local Actions,
Contexts, Quick-action groups, palette state, and local Work Item configuration
are loaded into one immutable candidate generation. The launcher publishes all
of its cached projections only after every stage validates and the participating
file signature remains unchanged. A late failure therefore reports its owning
area and retains the complete last successfully loaded interface generation;
it cannot combine newly loaded Actions with older menus, Contexts, or slots.
Presentation reload deliberately retains configured external Action references
without probing their current targets. This matches snapshot/restore
portability policy; creation, editing, and execution retain their stricter
target validation.
Invalid or temporarily unreadable palette state follows the same complete-
generation rule: legacy focus/pin compatibility data and per-Context slots
remain in memory together with the Actions, Contexts, menus, and Work Item
configuration with which they were accepted.
The domain default always contains an empty context-slot mapping, so a missing
or initially invalid palette file cannot fail first-start normalization.
Coordinated startup and reload defer command-surface rendering until both
command groups and palette state are loaded, then build the Quick-action
widgets once. Startup keeps its fault-isolated loaders because no earlier
generation exists to preserve; subsequent reloads use the strict staged
generation boundary. Standalone bootstrap loader calls keep immediate
rendering by default.


## Diagnostics

The standard-library logging system writes bounded local diagnostics to ignored
`data/context-palette.log`. The file rotates at 512 KB and keeps two backups.
Logging setup failure does not prevent application startup. Clipboard and Input
/ Output contents are not written deliberately. Slow configuration reload
warnings include safe per-stage durations, but never file paths or configured
content.

The Configure Diagnostics section uses `diagnostics.py` to render a separate safe
summary rather than exposing the raw log. It reports loaded configuration
counts, error count and last-error timestamp, and allow-listed automatic-paste
category/outcome/reason events. Unknown or malformed event values are ignored.
The rendered and copied summary never includes raw error messages, action
values, clipboard content, credential fields, paths, or window titles.
The main launcher routes `Ctrl+Shift+D` directly to this section. Configure enables
`Ctrl+Tab` traversal through its internal page stack, then moves focus into the selected section's
primary interactive or readable control. The Diagnostics summary remains
read-only but participates in keyboard focus for selection and screen-reader
access. Configure routes `Alt+A`, `Alt+T`, `Alt+C`, `Alt+Q`, `Alt+W`, `Alt+D`,
and `Alt+B` through
one generic key-event handler instead of Tk's unreliable symbolic Alt bindings.
This uses semantic letters and remains independent of QWERTY/AZERTY number-row
differences. The main launcher's global slot handler accepts only unmodified
number keys, leaving modified numbers to the focused control.

Complete result refreshes slower than 100 ms and configuration reloads slower than 500 ms write a warning containing only elapsed time and action count. Search text and action content are deliberately excluded.

## Tooltips and Help

There are two guidance mechanisms:

1. Communication line: bounded selected-action explanation, results, warnings, and errors.
2. Widget tooltip: delayed hover help for every label and button, including compact `?` guidance buttons. Explicit descriptions override automatically installed fallbacks.

Detailed help is stored once in `docs/HELP.md` and displayed by the in-app searchable Help window.

## Security model

- Treat loaded actions and captured text as untrusted data.
- Only allow known action types.
- Validate URLs to complete `http` or `https` addresses with an unambiguous
  hostname. Reject embedded usernames/passwords, whitespace/control characters
  in the authority, and backslash-based authority ambiguity.
- Validate files, folders, executables, and working directories before opening.
- Prefer an existing literal local path before trying a percent-decoded
  fallback, so a real filename containing `%20` is never silently redirected.
- Do not invent or parse a compound shell command language; keep Windows target
  execution as one explicit target plus structured arguments.
- Keep API keys out of version-controlled files.
- Never enumerate or write Windows credentials. Credential actions store only
  exact target names and are unavailable to AI proposal and external execution paths.
- Require explicit user action for launches and other external effects.
- Treat captured text and AI responses as untrusted data. AI requests are
  previewed and copied manually; responses must remain within the bounded size
  limit and pass the versioned proposal schema and existing action validation
  before selected proposals become local Active actions.

## Testing strategy

Tests use `unittest` and focus on pure or callback-injected behavior.

- Action parsing, search, execution dispatch, transformations, and URL building.
- Searchable action-picker filtering and Tk selection behavior.
- Inbox and cheat-sheet persistence.
- Slot calculation and palette-state persistence.
- Hotkey constants and single-instance behavior.

External UI and Windows behavior also require documented manual tests.

Run:

```powershell
.\python-context-palette.bat -m unittest discover tests
```

For the complete configuration, compilation, and test check, run:

```powershell
.\check-context-palette.bat
```

## Extension rules

When adding an action type:

1. Add one definition to the catalogue in `action_types.py`; `SUPPORTED_ACTION_TYPES` is derived from it.
2. Add type-specific parsing, validation, execution, and Active-action creation as required.
3. Keep pure transformation logic separate from UI/platform effects.
4. Inject external behavior through a callback where practical.
5. Regenerate `docs/ACTION_TYPES.md` through the catalogue-owned renderer.
6. Add automated tests and any required manual Windows check.
7. Update Help, Architecture, Changelog, MVP/Backlog, and Decisions as appropriate.

When adding context behavior:

1. Keep Context membership and slots 6–0 coupled to one explicit filter.
2. Do not silently switch the user's Context filter.
3. Preserve context slots 6–0 and round-trip legacy focus/pin data without
   using it as current Context state or projecting global pins.
4. Explain inputs, outputs, clipboard effects, opened targets, and persistence.
5. Prefer composition over duplicating actions.

## Known architectural next steps

- Complete the Phase 5 manual Windows backup/restore verification matrix before
  treating selective export/import as an eligible next design phase.
- Separate Configure dialog families from `configuration_window.py` when a
  material Configure change benefits from the boundary.
- Add supporting-context composition and weighted ranking.
- Extend clipboard transactions beyond protected plain text only with
  action-specific timing and format semantics before adding sequence paste,
  Tab, or Enter steps.
- Consider optional application-aware context suggestions that never switch focus silently.
- Add rich HTML and image actions only with explicit clipboard semantics.

These are proposals, not implemented capabilities. See [Roadmap](ROADMAP.md).
