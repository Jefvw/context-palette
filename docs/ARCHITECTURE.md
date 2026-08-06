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
6. Permanent confirmed action creation with Active and Archived states.
7. Standard-library implementation where practical.

It is intentionally a personal, single-user desktop application. There are no
accounts, roles, team workspaces, or concurrent-editing guarantees. That narrow
boundary does not relax validation, privacy, lifecycle, or constrained-execution
requirements.

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
- Notifies an existing instance before treating a pending journal as an
  interrupted transaction.
- Completes rollback from a pending restore journal before migrations or
  configuration loading.
- Starts the Tk launcher with paths to local data.

### `launcher.py`

Presentation and application orchestration.

- Builds the Tkinter interface.
- Maintains the explicitly selected focus context through a compact menu launcher.
- Exposes the complete configuration workspace through one direct
  **Configure** button. The Focus selector retains a direct **Manage focuses…**
  route to the Contexts tab. All Configure routes reuse one live editor and
  retarget its tab or selected record; a new editor is created only after the
  previous one closes.
- Renders numbered slots, global flat search results, or an explicitly activated
  flat list of actions belonging to the selected Focus.
- Renders the global JSON-configured Quick-action surface beside search results
  and the fixed action-bound Passwords, Folders, and Prompts hierarchies.
- Owns Input / Output, the communication line, systematic widget tooltips, Inbox, sheets, Help, and action editors.
- Connects platform-independent action execution to Windows-specific callbacks.
- Ensures Tk operations stay on the Tk main thread.
- Resets transient presentation state through the main-window `F5` shortcut
  without changing persisted Focus, pins, slots, actions, or configuration.
- Switches the existing discovery list into Work Items mode without changing
  the main-window dimensions. Find, project-code/tag filters, selection,
  previews, and constrained open commands consume the immutable in-memory Work
  Item index; action mode state remains intact. All keyboard, default, and
  context-menu targets pass through one constrained Work Item opening boundary.
  The mode-specific **New item** control opens the existing Configure creation
  flow; the launcher does not duplicate template validation or filesystem
  creation. The primary action row becomes a two-part control in Work Items
  mode: **↗** retains workbook-first Open behavior while its adjacent folder
  button requests the same constrained boundary with the folder target.

The main-window construction is divided into focused header,
results/command-surface, shortcut, workspace, and footer builders. Secondary
Inbox and Inbox-action-creation presentation lives in `inbox_window.py`;
`launcher.py` retains only the capture command and window orchestration.

The launcher does not implement action transformations or window matching directly. Those responsibilities live in specialized modules.

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
The launcher exposes the window from Inbox, while the Actions configuration tab
is the primary route. No harvested candidate enters persistent data before the
final confirmation.

### Discovery modes

The shared discovery area has three explicit modes. Focus is never inferred or
changed automatically, and action Find remains global regardless of Focus.

| State | Heading/results | Rail | Primary action |
| --- | --- | --- | --- |
| Actions, empty Find | Ordinary actions, including slots 1–0 | Passwords, Work, Types, Tags, Help | Run |
| Focus Actions, empty Find | Flat actions explicitly belonging to the selected Focus | Same action rail | Run |
| Action Find or filter active | Flat global action matches; changing Focus does not filter them | Same action rail | Run |
| Find cleared after Focus Actions | Restores the selected Focus's flat membership list | Same action rail | Run |
| Work Items | Indexed Work Item folders, never action records | Work, New item, Projects, Tags, Help; action-only Passwords is hidden | Open |

The heading, count, empty state, selection preview, rail labels, status, and
primary verb must all describe the active mode. `ActionDiscoveryPanel` owns
those widgets; `LauncherApp` owns mode policy and the constrained Run/Open
callbacks. Both `?` controls continue to open the same general Help document.

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
and **Unsorted** placement cannot diverge. Configure adds presentation-only
selection records: generated action leaves delegate to the normal action
editor, while generated groups and levels route to a filtered Actions list.
The generated hierarchy is never written as a second assignment store.

### `action_types.py`

Defines the machine-readable catalogue for every supported action type: icon,
user label, family, description, required fields, input/output effects,
portability, new-action visibility, AI eligibility, and type-specific AI
guidance. Supported legacy types can remain loadable and editable while the
Create action catalogue omits them. `actions.py`
derives its supported-type set and compact row icon from this catalogue, and AI
prompt generation consumes the same definitions.

The catalogue renders `docs/ACTION_TYPES.md`; an automated test requires the user-readable overview to remain identical to the executable definitions.

### `workspace_transforms.py`

Defines the ordered, user-facing catalogue for Input / Output transformations:
menu groups, labels, operation keys, completion feedback, and readable
parameter definitions. The workspace menu and guided reusable action editor
for text files both consume this catalogue, while the launcher renders action previews
without duplicating operation names. The launcher renders its Transform menu
from this catalogue instead of repeating every command in the UI orchestrator.
Pure transformation algorithms and validation remain in `actions.py`.

### `workspace_panel.py`

Owns the complete Input / Output UI component: text widget, edit and Transform
menus, selection-first replacement, undo boundaries, prefix/suffix prompting,
clipboard copy and replacement, transformation feedback, and file-transform
preview provenance. A file preview exposes explicit replace, save-as, and
dismiss commands; ordinary workspace replacement clears that provenance. It
depends on small injected callbacks for clipboard access, status messages, and
tooltip registration. `launcher.py` retains compatibility delegates for action
execution and integration flows, but no longer owns workspace widget mechanics.

### `action_discovery_panel.py`

Owns construction and event wiring for the left action-discovery presentation:
heading and count, global Find entry, type and searchable single-tag controls, Run and Help
controls, flat result list, Focus list, scrollbar, and row tooltips. Search
policy, action ranking, filtering, Focus membership, selection meaning, and execution remain in
`launcher.py` and are supplied through narrow callbacks. Compatibility aliases
allow existing launcher orchestration to migrate incrementally.

Right-click callbacks preserve the clicked flat or Focus row as the current
selection, then route its stable action ID into the existing Configure Actions
workspace. `configuration_window.py` highlights that action after rendering;
My configuration actions persist to the ignored local action file. Built-in
actions may also be edited after an explicit developer-impact warning and
persist to the Git-tracked starter action file.

### `context_membership_field.py`

Provides reusable comma-separated picker fields used by Configure, Inbox
conversion, and action editing. Context membership combines an editable field
with a checklist of canonical defined contexts. Tag selection uses a shared
searchable multi-select picker for existing normalized tags but continues to
allow new free-form values. The discovery rail uses the same picker in
single-select mode, including its explicit clear choice. Selection mechanics
remain separate from domain validation in
`actions.py`, so typed values and non-UI callers follow the same persistence
rules. Underlined Windows mnemonics move focus directly to each field, and
`Alt+Down`/`F4` opens either Tk's native context checklist or the searchable
tag picker.

### `context_membership.py`

Owns the single source of truth for action-to-context membership. Context
definitions supply the canonical ordered `action_ids`; action objects used by
the launcher and Configure are projected from those definitions so search,
the Actions table, slots, and Focus Actions all see the same memberships.
Action create/edit flows write the action record and context definitions as
one recoverable operation, remove context metadata from newly persisted action
records, and reject a My configuration action reference from a Built-in
context. Startup performs an idempotent one-time union of compatible legacy
action-side memberships into context definitions. Legacy metadata remains
readable for pre-migration definitions but is not an independent current
membership source.

### `searchable_selection.py`

Provides the compact searchable tag popup shared by guided multi-select tag
fields and the discovery rail's single-tag filters. It preserves selections
while search narrows the visible list, provides an explicit clear choice for
filters, and restores an owning dialog's modal grab when it closes.

### `action_picker.py`

Provides the shared searchable action selector used throughout Configure.
Pinned slots, context membership, preferred Focus slots, and Quick-action
assignments open the same dialog instead of rendering separate long combobox
menus. The picker matches all entered terms against the action's readable
label and the canonical action search document, while callers continue to
persist stable action IDs. Restricted Built-in pickers display their storage
scope and an explicit empty-result explanation.

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
Built-in and personal collections separately, preserve stored Archived Actions,
expose only Active Actions in the executable projection, and defensively copy
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
external resources, templates, and credential secrets are never selected.

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
recovery can run.

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
prohibits personal paths, secrets, and private work details. Contexts can assign
an unlimited action membership plus slots 6–0, and personal Quick actions can
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

Action creation and editing refresh every Configure view derived from actions,
including pins, context and Quick-action summaries, and diagnostics. Action
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

Configure list tables use the shared `treeview_utils.py` scrollable-tree
builder. Actions, contexts, Quick actions, Work Item sources, and discovered
Work Items retain visible final columns and consistent vertical scrolling at
the supported minimum window size.

Every Configure field that references an existing action uses the shared
searchable action picker. Its readonly field keeps the selected human-readable
label visible; **Find…** opens a keyboard-operable filtered list with a result
count. The five pin fields use the same behavior in a compact layout that
preserves the supported minimum window width.

New actions, contexts, and Quick-action groups explicitly choose **My
configuration** or **Built-in** and default to My configuration. The
Quick-actions tab is a hierarchical editor. Persisted groups and menu levels
can be added, renamed, deleted, and reordered. The same tree also shows the
generated Passwords, Folders, and Prompts hierarchies with editable action
leaves; those generated records are reorganized through the owning action's
`quick_action_path`, not through `command_surface.json`.
A group chooses direct Quick-action rows or one nested subject-menu launcher.
Nested groups and their menu levels may each own ordered actions; levels recurse
to a validated maximum depth of three below the group. Selecting a group or
level establishes the parent for **Add menu level**, while stable IDs remain
unique across the complete group tree. In row presentation, a visible
top-level item's first available target remains its left-click default; its
context menu can expose every ordered action and Work Item plus descendants.
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

### `context_deletion.py`

Owns dependency-aware context deletion and renaming across the defining file,
legacy project/local action metadata, and palette Focus state. Canonical action
membership is removed with the defining context itself. A material rename
first writes a safe intermediate definition containing both names, updates
legacy and palette references, and then removes the old definition. The final
write preserves the true pre-rename definition as the context file's backup.

### `action_deletion.py`

Owns dependency-aware action removal. It validates and inventories context,
quick-button, pin, and Focus-slot references before the UI asks for
confirmation. On acceptance it removes those references before deleting the
action, so an interrupted multi-file update is more likely to leave an unused
action than a broken reference. Every changed file still uses atomic
replacement and its local backup behavior. A quick button with no remaining
action is removed; a deleted primary action falls back to the button's next
configured action.

### `palette_state.py`

Stores and calculates launcher organization.

- Slots 1–5: persistent global pins.
- Slots 6–0: top five actions for the focus context; internal slot 10 is
  displayed and invoked with the physical `0` key.
- Duplicate actions across both groups are intentional.
- Unfilled context slots prefer other actions belonging to the active Focus,
  then fall back to remaining globally available actions.

### `command_surface.py`

Loads and validates global quick-action groups and their compact items from
shared and local JSON. A validated presentation flag selects direct subject
rows or one nested group launcher; omitted presentation remains row-based for
backward compatibility. A group and each recursive item retain ordered actions;
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

The module also owns the canonical primary-first, duplicate-free action ordering used by execution, menus, Configure, and configuration validation.

### `tooltips.py`

Owns delayed tooltip behaviour for ordinary widgets and individual listbox rows. Keeping these presentation helpers outside `launcher.py` prevents the main application orchestrator from also owning reusable hover-window mechanics.

### `style.py`

Owns the shared native ttk theme, Segoe UI font policy, grey/teal/aqua palette, and hover/focus state maps. Classic Tk widget defaults are applied through the root option database. The module changes presentation only; widget construction, layout, geometry, and action behaviour remain in their existing owners.

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

Loads and validates standalone Built-in and My configuration context
definitions. A definition owns an unlimited ordered `action_ids` membership and
up to five preferred action IDs. `focus_model.py` combines definition-owned
membership with legacy action-side memberships for backward compatibility.
Explicit per-machine choices in `palette.json` override configured defaults.

### `focus_model.py`

Owns pure runtime Focus policy independently of Tk and persistence. It discovers
available Focus names, resolves preferred slots and unavailable-Focus fallbacks,
and selects the flat action membership list for a Focus while preserving
canonical action order. This is the intended replacement boundary for future
context-model changes.

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

Owns the guided **Work Items** Configure panel and its source/tag dialogs. It
validates existing absolute source folders, generates stable local IDs, reports
availability, performs explicit bounded refreshes, and persists edits through
`work_item_storage.py`. Configure scans use the existing background coordinator;
concurrent requests coalesce into one subsequent latest-state refresh. The panel
uses a weak completion callback and ignores late results after its Tk container
is destroyed. Existing-source management never modifies work folders or files;
new-item creation delegates its guarded write to `work_item_creation.py`.

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

`LauncherApp.quit_app()` checks both Work Item write coordinators before
stopping the hotkey, instance server, or Tk root. A running file copy or Excel
Inbox update blocks complete process termination with an actionable warning;
ordinary Hide remains available. This keeps daemon-backed work from being
terminated by the application's own Quit control before completion is
delivered.

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
- Keeps captured material separate from actions until conversion.

The Inbox creation UI supports guided permanent `copy_text` and URL-builder
actions. URL templates are validated through the same domain function used at
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
- Returns a clipboard sequence number so delayed clearing occurs only if another
  application has not replaced the clipboard.
- Arms delayed conditional clearing before destination focus and paste dispatch,
  so an input-dispatch failure cannot leave cleanup unscheduled.
- Retains protected-clipboard tracking until an ordinary clipboard replacement
  completes, so a failed write cannot make the secret eligible for workspace
  synchronization.
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
through `window_geometry.py`. Every application child resolves the Windows work
area of the monitor containing the main Tk root. Standard dialogs center on
their owning top-level and clamp completely into that work area; compact
selection popups remain anchored to their control, move above it when needed,
and use the same clamp. Auto-sized Work Item dialogs and the larger Harvest
window use the same policy. Native menus and widget tooltips retain their
control-anchored placement paths. The main window uses the same compact
screen-aware `780x600` default and `700x480` minimum as other full screens.
Hotkey placement still reduces an oversized user-resized window before
clamping it into the cursor monitor's work area.

The main content is a user-adjustable vertical split. By default, the action
area derives its absolute height from the bottom of the visible action-control
stack, so the scrolling result list ends alongside those buttons and Input /
Output receives the remaining space. Work Items mode recomputes that compact
height for its additional controls. After the user moves the divider, their
chosen ratio is used for later resizing in that session. Sash positions remain
bounded to keep both panes usable; when a display cannot fit both preferred
minimums, the available space is divided proportionally. Inside the upper area,
a responsive horizontal pane starts at approximately 44% for the Actions
workspace and 56% for the global quick-action surface. The Actions workspace
owns its heading/count, Find entry, numbered scrolling list, and an 88-pixel
rail containing Passwords, Work, Types, Tags, Run, and action-Help controls.
The Quick-action side retains its vertical menu launchers and independent
scrolling. The horizontal pane retains a user-adjusted ratio during later
resizing and applies the same bounded-sash behavior. Fixed bottom action and
status rows remain outside the vertical split, preventing them from being
displaced. Management buttons use a single compact symbol row with name-first
tooltips.
Search text can be combined with one shared built-in action-type filter;
Passwords is a direct shortcut into that same filter state.

Each group renders in stable row-major order within a two-column grid. The
tracked command surface contributes one **Standard** group containing every
active Built-in action exactly once across subject menus. Standard's nested
presentation renders one **Standard** launcher without a duplicate group
heading. Direct group actions become root commands; recursive menu levels
become native cascades; and actions assigned at any level appear before that
level's child cascades. Every configured nested group uses the same compact
group-labelled launcher. A direct group with one row also lets that row
represent the group without a duplicate heading; direct groups with multiple
rows retain their visible heading.
Ignored local groups load after it and occupy the remaining editable positions.
They retain direct rows unless configured for nested presentation.
Three application-owned action-bound groups remain separate from stored
command-surface configuration. **Passwords**, **Folders**, and **Prompts**
derive their complete membership from Active `paste_credential`,
`open_folder`, and `ai_prompt` actions. Their position is fixed beside
**Standard**, and each action's optional `quick_action_path` produces as many
as three native submenu levels. An empty path is projected into **Unsorted**.
Shift/Ctrl+click on a configured group opens its menu and action files;
Shift/Ctrl+click on an action-bound group opens action configuration. The data
model places no numeric limit on a node's ordered actions, but supports at most
group → level 1 → level 2 → level 3 → action and provides no search or
app-managed scrolling inside native menus.

Quick-action labels participate in keyboard focus. Enter or Space executes a
row's first available primary action or opens a nested group at its launcher.
Empty search, Inbox, cheat-sheet, and command-surface states contain recovery
guidance rather than blank widgets. Reloads use a short busy cursor/status
state; local loading is intentionally not animated.

Ordinary widget tooltips respond to both pointer hover and keyboard focus. This
keeps the full names and explanations of compact symbol controls available
without expanding the fixed-size main-window layout. They prefer the space
below a control, move above it near the bottom edge, and remain inside the
virtual desktop, including secondary monitors with negative coordinates.

Configured Quick-action rows, nested group launchers, and action-bound
launchers share one mouse/keyboard binding contract for left click, right
click, Enter, and Space. Every action leaf still uses the ordinary constrained
action executor.

## Supported action types

The current allow-list includes:

- `copy_text`
- `open_url`
- `open_file`
- `open_folder`
- `launch_app`
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

Action types that cause external effects use constrained implementations.
`launch_app`, for example, accepts an existing absolute `.exe`, fixed argument
list, and optional validated working directory. `paste_credential` accepts only
an exact standard Windows or generic credential target and requires a fresh
hotkey-captured destination, confirms the target window, and never accepts a
password in configuration.

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
        +-- file-transform preview -> review/edit -> replace source or save as
        +-- URL builder -> prompt or consume workspace -> copy + open URL
        `-- saved-text action -> clipboard -> fresh captured destination, or manual-paste fallback

Windows Credential Manager -- exact target --> protected clipboard --> captured destination
```

Destination paste callbacks treat focus restoration and input dispatch as
separate failure points. Both restore the hidden palette. Ordinary saved text
remains on the clipboard for manual recovery, while protected credential data
is cleared immediately. Sequence-aware cleanup ignores an obsolete delayed
callback after an earlier failure has already cleared the protected item.
Automatic-paste observability uses a fixed event schema containing only
category, outcome, and reason. It never accepts action values, clipboard text,
credential targets, usernames, passwords, or window titles. Successful and
clipboard-only outcomes use informational logging, unavailable destinations use
warning logging, and dispatch failures retain their exception at error level.

Input / Output is a permanent editable working text box, not action documentation. It synchronizes from the clipboard when shown and can be explicitly copied, pasted, cleared, transformed, or replaced by actions. Inline transformations apply to the selection, or the complete field when there is no selection, and copy their result to the clipboard. Pure transformation logic lives in `actions.py`; `workspace_panel.py` owns selection ranges, one-step Undo grouping, clipboard updates, and menus. The launcher injects clipboard and status callbacks and retains orchestration delegates. Action explanations and application status share a slim bottom communication line.

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
and Lines. Line operations preserve the detected line-ending style and final
newline where applicable.

Numbered action dispatch is enabled only when the Find entry owns focus. All other widgets suppress it, making shortcut mode explicit and preventing accidental execution while navigating or editing. The communication line never wraps; its full untruncated action explanation is retained separately for a dynamic hover tooltip and click-open detail window.

The numbered-slot colour legend and workspace heading are intentionally not rendered. Slot numbers and row colours carry the distinction. Action rows measure every icon in the active Tk font, pad narrower symbols to one shared pixel column, and then render `- short name`. A non-action separator row divides slots 1–0 from ordinary results; mouse and keyboard selection skip that separator. Standard editing and transformations are available through the context menu, with a compact `⋮` transform button as the only persistent workspace control.

## Focus contexts and slots

The application currently implements a focus context rather than a complete multi-context inference engine.

```text
1–5  global pinned actions
6–0  focus-context actions
other rows  ordinary search matches
```

Changing the focus context changes slots 6–0 only. Search always remains global.

The **Focus actions** control is a reversible, visibly active presentation
mode. With Find empty, it shows a flat list of visible actions belonging to the
active Focus in canonical action order. Choosing the control again returns to
the normal action list. General contains every action; a specific Focus uses
the matching context definition's canonical `action_ids` membership. Typing in
Find swaps this view for the global flat results, and clearing Find restores
Focus Actions only when that mode remains active. Tags do not create folders
in this view because they are independent filters rather than structural
ownership.

Configured Quick actions use action IDs or an ordered personal mix of actions
and stable Work Item references. The launcher first
renders **Standard | Passwords**, then **Folders | Prompts**, followed by
personal configured groups. The last three menus are pure projections over
Active first-class actions and their optional `quick_action_path`; creating,
archiving, or deleting an action therefore updates menu membership without a
second configuration record. AI prompt execution still shares review-first
workspace/clipboard behavior with templates while retaining a separate type
identity for future prompt-specific evolution. Cheat sheets remain a
searchable reference subsystem and are opened as a secondary command from the
Help window rather than occupying a Quick-action slot.

Focus and pin changes are applied in memory only after the updated palette state
has been persisted successfully. A write failure keeps the prior state visible
and reports the failure to the user.

Focus names and matching `context_slots` keys are resolved case-insensitively
to the current canonical spelling. This keeps older per-machine palette files
usable after capitalization changes. Unknown slot keys are preserved, and an
exact canonical key takes precedence if both spellings exist.

The longer-term context model includes identity, knowledge, capabilities, and optional activation, with one focus context and multiple supporting contexts.

## Storage

All data is local and inspectable.

The logical entities, stable identities, cross-file references, derived state,
external-resource boundary, and implemented asset catalog are summarized in
the [data model](DATA_MODEL.md). Deterministic backup creation, the
UI-independent recoverable restore core, and the in-process Configure workflow
are implemented as described in the [backup and restore plan](BACKUP_RESTORE_PLAN.md).

### `data/actions.json`

Reviewed portable action records shared through Git.

Action IDs are unique case-insensitively within a file and across shared/local files. This keeps pins, context slots, command-surface references, edits, and trust promotion unambiguous.
New records store optional `tags`; specific context membership is stored only
in context definitions. Legacy `context` and `contexts` fields remain readable
for migration. Omitting them does not remove canonical membership because the
context files own it. General itself is always implicit.

### `data/contexts.json` and `data/local_contexts.json`

The Built-in file contains only shipped starter contexts; currently that is
**Developing Context Palette**. The ignored local file contains the user's
personal or work-specific contexts and owns their action memberships. General
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

Ignored per-machine focus context, pinned IDs, and explicit context slot IDs.

### `data/cheatsheets/*.json`

Structured reference sheets.

Safe initial structures are tracked as `data/*.example.json` and copied by `setup-context-palette.bat`.

## Threading and responsiveness

Tkinter widgets are only accessed from the main thread.

- The hotkey message loop runs in a daemon thread and writes a lightweight queue message.
- The single-instance listener also signals through a queue.
- The Tk main loop polls requests every 100 ms.
- No database, network service, web frontend, or heavy UI framework is initialized.

Configuration reloads are skipped when active file existence, modification time, and size are unchanged. Typed search changes are coalesced over 40 ms before recalculating slots and rows.

Configuration reload is transactional in memory: combined shared/local actions,
contexts, and quick-action groups replace their active lists only after complete
validation succeeds. A failed external edit reports the affected file and
retains the last successfully loaded interface configuration.
Invalid or temporarily unreadable palette state follows the same last-known-good
rule: active pins, Focus, and context slots remain in memory while the local
file is corrected or becomes accessible again.
The domain default always contains an empty context-slot mapping, so a missing
or initially invalid palette file cannot fail first-start normalization.
Coordinated startup and reload defer command-surface rendering until both
command groups and palette pin state are loaded, then build the Quick-action
widgets once. Standalone loader calls keep immediate rendering by default.


## Diagnostics

The standard-library logging system writes bounded local diagnostics to ignored
`data/context-palette.log`. The file rotates at 512 KB and keeps two backups.
Logging setup failure does not prevent application startup. Clipboard and Input
/ Output contents are not written deliberately. Slow configuration reload
warnings include safe per-stage durations, but never file paths or configured
content.

The Configure Diagnostics tab uses `diagnostics.py` to render a separate safe
summary rather than exposing the raw log. It reports loaded configuration
counts, error count and last-error timestamp, and allow-listed automatic-paste
category/outcome/reason events. Unknown or malformed event values are ignored.
The rendered and copied summary never includes raw error messages, action
values, clipboard content, credential fields, paths, or window titles.
The main launcher routes `Ctrl+Shift+D` directly to this tab. Configure enables
native `Ctrl+Tab` notebook traversal, then moves focus into the selected tab's
primary interactive or readable control. The Diagnostics summary remains
read-only but participates in keyboard focus for selection and screen-reader
access. Configure routes `Alt+A`, `Alt+T`, `Alt+C`, `Alt+Q`, `Alt+D`, and
`Alt+B` through
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
- Require explicit user action for launches and trust promotion.
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
.\.venv\Scripts\python.exe -m unittest discover tests
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

1. Preserve global search.
2. Do not silently switch the user's focus context.
3. Keep pinned slots stable.
4. Explain inputs, outputs, clipboard effects, opened targets, and persistence.
5. Prefer composition over duplicating actions.

## Known architectural next steps

- Complete the Phase 5 manual Windows backup/restore verification matrix before
  treating selective export/import as an eligible next design phase.
- Separate Configure dialog families from `configuration_window.py` when a
  material Configure change benefits from the boundary.
- Add supporting-context composition and weighted ranking.
- Design safe linear action sequences and clipboard transactions as explicit, previewable models.
- Consider optional application-aware context suggestions that never switch focus silently.
- Add rich HTML and image actions only with explicit clipboard semantics.

These are proposals, not implemented capabilities. See [Roadmap](ROADMAP.md).
