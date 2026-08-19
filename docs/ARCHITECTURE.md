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
  **Configure** button. Its ordinary route opens a task-oriented Start page;
  the Focus selector retains a direct **Manage focuses…** route to the Contexts
  tab. All Configure routes reuse one live editor and retarget its tab or
  selected record; a new editor is created only after the previous one closes.
- Renders color-coded shortcut rows, a normal mixed global projection of Actions
  and Work Items with selected-Focus members grouped first, kind-specific
  projections, or an explicitly activated flat mixed list belonging to the
  selected Focus.
- Renders the global JSON-configured Quick-action surface below discovery
  and the fixed action-bound Passwords, Folders, and Prompts hierarchies.
- Composes a bounded horizontal main split: the command console occupies about
  40% initially and the full-height Input / Output workspace about 60%.
- Owns the communication line, systematic widget tooltips, Inbox, sheets, Help,
  and action editors; `WorkspacePanel` owns the Input / Output presentation.
- Connects platform-independent action execution to Windows-specific callbacks.
- Ensures Tk operations stay on the Tk main thread.
- Resets transient presentation state through the main-window `F5` shortcut
  without changing persisted Focus, pins, slots, actions, or configuration.
- Switches the existing discovery area among explicit **All items**,
  **Actions**, and **Work Items** scopes without changing the main-window
  dimensions. Find, shared Context/tag filters, project-code/type filters, selection,
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

### Discovery scopes and Focus view

The shared discovery area has three explicit scopes plus the reversible Focus
presentation. Focus is never inferred or changed automatically, and Find
remains global regardless of Focus.

| State | Heading/results | Secondary tools | Primary action |
| --- | --- | --- | --- |
| All items | Mixed Actions and discovered Work Items: color-coded shortcut rows first, then matching members of a selected specific Focus, a non-action divider when needed, and remaining global matches | Filters menu: Context and Tag | Run or Open, selected-kind specific |
| Actions | Actions only, including Action slots | Filters menu: Type, Context, and Tag | Run |
| Work Items | Indexed Work Item folders, never Action records | Filters/tools menu: New item, To inbox, Copy file, Project, Context, and Tag | Open |
| Focus items, empty Find | Flat mixed membership of the selected Focus, including soft unavailable Work Item references | All-items tools | Run or Open |
| Find while Focus items is active | Normal mixed global matches; changing Focus does not filter them | All-items tools | Run or Open |
| Find cleared after Focus items | Restores the selected Focus's flat mixed membership list | All-items tools | Run or Open |

The scope selection, empty state, selection preview, toolbar state, status, and
primary verb must all describe the active scope and selected kind. Redundant
pane headings and counts are maintained as internal state only, not rendered.
`ActionDiscoveryPanel` owns those widgets; `LauncherApp` owns scope policy,
typed selection resolution, and the constrained Run/Open
callbacks. Both `?` controls continue to open the same general Help document.

Focus-first grouping is applied after Find and tag candidate filtering, so the
candidate set and count remain global. It is suppressed for General and for an
explicit Context filter, where grouping would be redundant or misleading.
Actions-only, Work-Items-only, and Focus-items projections keep their existing
ordering policy. The divider has no typed item reference and pointer, keyboard
navigation, preview, and execution paths must treat it as presentation only.

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
editor, while generated groups and levels offer a typed full Action form plus
the matching Actions list.
The generated hierarchy is never written as a second assignment store.

### `palette_items.py`

Defines the immutable typed reference shared by Context membership, preferred
Focus slots, and mixed Quick-action targets. A reference identifies exactly one
Action ID or one stable Work Item source/folder identity; it contains no
execution behavior. Owning services resolve and execute the referenced entity,
so Work Items retain their discovery lifecycle and Actions retain their
allow-listed executor.

### `action_types.py`

Defines the machine-readable catalogue for every supported action type: icon,
user label, family, description, required fields, input/output effects,
portability, new-action visibility, AI eligibility, and type-specific AI
guidance. Supported legacy types can remain loadable and editable while the
Create action catalogue omits them. `actions.py`
derives its supported-type set and compact row icon from this catalogue, and AI
prompt generation consumes the same definitions.

The catalogue renders `docs/ACTION_TYPES.md`; an automated test requires the user-readable overview to remain identical to the executable definitions.

### `action_preview.py`

Builds the side-effect-free, structured explanation shown before Action
execution. It combines the selected Action with the canonical action-type
catalogue and only boolean runtime availability supplied by the launcher; it
does not read the clipboard, expand templates, validate targets, or execute an
effect. Every supported type produces a bounded **Input → Effect** summary plus
full labelled details for Type, configured values, arguments, working folder,
and recovery or limitations. Current workspace, captured-selection, and fresh
destination availability refine the summary without exposing their contents.

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
Capture, Inbox, **Create from Input**, **Extract text**, and **Text tools** bitmap controls;
selection-first source choice and replacement; undo boundaries; prompting;
clipboard copy and replacement, transformation feedback, and file-transform
preview provenance. A file preview exposes explicit replace, save-as, and
dismiss commands; ordinary workspace replacement clears that provenance. It
depends on small injected callbacks for Action suggestion orchestration,
clipboard access, status messages, and tooltip registration. `launcher.py`
retains compatibility delegates for action execution and integration flows,
but no longer owns workspace widget mechanics.

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

### `action_suggestions.py`

Defines the pure, typed inference boundary for creating an Action from Input /
Output. It accepts only one complete HTTP/HTTPS URL or one clear absolute
Windows/file-URI target that can be identified lexically as a file, folder, or
`.exe`. Script-like suffixes are not inferred as ordinary files. It does no
filesystem probing, clipboard access, persistence, network retrieval, or
execution and returns no suggestion for mixed or ambiguous content.

### `action_discovery_panel.py`

Owns construction and event wiring for the left action-discovery presentation:
readable Focus and scope rows; one Find row containing the search field and
Filters menu; an active-filter chip; flat result list, Focus list, scrollbar, row tooltips;
and the stable `+A`, Edit, Pin, and Run/Open result toolbar. Action-only and Work
Item-only commands live in the Filters menu instead of reshaping the toolbar.
Routine icon controls use retained 16-pixel Tk bitmap images with semantic
tooltips, avoiding font-dependent Unicode toolbar symbols and new dependencies. Search
policy, action ranking, filtering, Focus membership, selection meaning, and execution remain in
`launcher.py` and are supplied through narrow callbacks. Compatibility aliases
allow existing launcher orchestration to migrate incrementally.

Context and tag filters open the shared searchable single-selection popup from
the Filters menu. Each supplies its own wording and explicit All choice; the
launcher callback remains the only owner of filter state and result refresh.

Right-click callbacks preserve the clicked flat or Focus row as the current
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
or concurrently Archived Action leaves Configure usable and opens no editor.

### `context_membership_field.py`

Provides reusable comma-separated picker fields used by Configure, Inbox
conversion, and action editing. Context membership combines an editable field
with a checklist of canonical defined contexts. Tag selection uses a shared
searchable multi-select picker for existing normalized tags but continues to
allow new free-form values. The discovery Filters menu uses the same picker in
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
the Actions table, slots, Context filtering, and Focus items all see the same
memberships.
Action create/edit flows write the action record and context definitions as
one recoverable operation, remove context metadata from newly persisted action
records, and reject a My configuration action reference from a Built-in
context. Startup performs an idempotent one-time union of compatible legacy
action-side memberships into context definitions. Legacy metadata remains
readable for pre-migration definitions but is not an independent current
membership source.

### `searchable_selection.py`

Provides the compact searchable tag popup shared by guided multi-select tag
fields and the discovery Filters menu's single-tag filter. It preserves selections
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
as mixed Quick-action targets. Built-in Contexts and pins 1–5 remain
Action-only. Quick-action groups remain global and have no Context visibility
field; the shared reference boundary permits, but does not imply, that future
feature.

Action creation starts from the educational **Action types** catalogue, the
launcher **+ Action** or Configure **New Action** searchable type chooser, or a conservative
**Create from Input** suggestion beside Input / Output. The suggestion route uses
selected text first, requires one clear supported target, and prepopulates
the existing form with a visible review notice. It does not change the general
type chooser or bypass confirmation. All routes
open the same `ActionDialog` and use the same atomic Action/Context-membership
persistence operation; the quick chooser is modal and never writes state on
cancel. Action creation and editing refresh every Configure view derived from actions,
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
their exact tab, selected-record, focus, singleton-window, and save behavior.

Configure list tables use the shared `treeview_utils.py` scrollable-tree
builder. Actions, contexts, Quick actions, and discovered Work Items retain
visible final columns and consistent vertical scrolling at the supported
minimum window size.

The Actions page keeps its single primary **New Action** command in the page
header and moves the type catalogue and Harvest behind **Other ways to
create**. Machine-local pins are summarized in a collapsed card; expanding it
reveals the same five live searchable pickers in vertical rows, so hiding the
card neither discards edits nor changes persistence. Its summary explicitly
marks unsaved hidden choices. Selection titles are display-bounded so arbitrary
names cannot displace lifecycle commands at minimum width. Tags remain searchable
and appear in the selected-Action strip instead of consuming a permanent table
column. The lifecycle filter controls which records are listed; the State
column appears only when Active and Archived records are mixed.

The Contexts and Quick actions pages use the same visual hierarchy without
introducing shared domain state: a page title and purpose, one primary creation
command, Find, a dominant scrollable table, and a selection-aware card. The
Contexts card preserves the existing Context-ID lookup and deletion boundary.
Its editor presents membership before optional Focus shortcuts 6–0. The Quick
actions card derives enabled commands from the selected record's ownership and
depth: configured records may be edited, moved, or deleted; automatic groups
route to filtered Actions and automatic leaves route to their owning Action.
All existing command-surface persistence and ownership validation remains in
the original callbacks.

The Work Items page selects one current source and keeps **Refresh** visible.
**Manage sources…** exposes Add, Edit, Remove, and creation-template commands
through their existing persistence paths. Edit and Remove are disabled when no
source exists, while Add and template setup remain reachable. The complete
folder path, availability, Work Item / Type / Project table, and selected-item
details remain visible in the main page.

Backup & restore remains the same background-worker and recovery boundary, but
its visible stages are literal: **Create backup…**, **Choose backup to
inspect…**, then the disabled-until-inspected destructive **Apply inspected
changes…**. Diagnostics renders the same privacy-safe summary in a read-only
scrollable text widget; Refresh is secondary and **Copy safe summary** is the
primary outcome.

Every Configure field that references an existing action uses the shared
searchable action picker. Its readonly field keeps the selected human-readable
label visible; **Find…** opens a keyboard-operable filtered list with a result
count. The five pin fields use the same behavior in a default-collapsed
vertical layout that preserves the supported minimum window width and daily
table height.

New Actions, Contexts, and Quick-action menus explicitly choose **My
configuration** or **Built-in** and default to My configuration. The
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
keeps storage, membership, Focus shortcuts, assignments, and summaries
reachable at 125%/150% scaling and on short monitor work areas. Focus entering
an off-screen field scrolls it into view; text, list, and combobox controls keep
their own native wheel behavior.

Automatic-menu Add commands reuse the ordinary `ActionDialog` and persistence
path. They constrain only the Action type and prefill `quick_action_path`; the
normal storage, name, description, Contexts, tags, target, validation, and
review fields remain present. Saving one Active Action then rebuilds both the
launcher menu and Configure tree from the single Action source of truth.

### `context_deletion.py`

Owns dependency-aware context deletion and renaming across the defining file,
legacy project/local action metadata, and palette Focus state. Canonical action
membership is removed with the defining context itself. A material rename
first writes a safe intermediate definition containing both names, updates
legacy and palette references, and then removes the old definition. The final
write preserves the true pre-rename definition as the context file's backup.

### `action_deletion.py`

Owns dependency-aware Action lifecycle mutations. It validates and inventories
Context, Quick-action, pin, and Focus-slot references before the UI asks for
confirmation. Archive removes those active-only references before changing the
retained record to Archived; restore changes that same record back to Active
without recreating former assignments. Permanent deletion uses the same
reference-cleanup boundary before removing the record. This ordering makes an
interrupted multi-file update more likely to leave an unused Active Action than
an invalid reference to an Archived or missing Action. Every changed file still
uses atomic replacement and its local backup behavior. A Quick-action item
with no remaining target is removed; removing a legacy primary Action preserves
the remaining menu order without creating a new launcher default.

`actions.py` exposes separate combined projections for this boundary: stored
loading includes Active and Archived records with cross-owner duplicate-ID
validation, while ordinary combined loading remains Active-only. Configure
uses the stored projection only for its Actions table and lifecycle controls;
all runtime discovery and assignment pickers continue to consume Active
Actions.

### `palette_state.py`

Stores and calculates launcher organization.

- Slots 1–5: persistent global pins.
- Slots 6–0: top five Actions or Work Items for the Focus Context; internal slot 10 is
  displayed and invoked with the physical `0` key.
- Duplicate actions across both groups are intentional.
- Unfilled context slots use only other Actions or Work Items belonging to the
  active Focus and otherwise remain empty. General continues to treat all
  Actions as global members; a specific Focus never borrows unrelated Actions.

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

### `tooltips.py`

Owns delayed tooltip behaviour for ordinary widgets and individual listbox rows. Keeping these presentation helpers outside `launcher.py` prevents the main application orchestrator from also owning reusable hover-window mechanics.

### `style.py`

Owns the shared native ttk theme, Segoe UI font policy, grey/teal/aqua palette, and hover/focus state maps. Classic Tk widget defaults are applied through the root option database. The module changes presentation only; widget construction, layout, geometry, and action behaviour remain in their existing owners.

### `ui_mockups.py`

Owns a standalone, inert real-Tk gallery used to validate proposed visual
structure before production UI batches. It reuses only the shared theme and
embedded bitmap icons, renders frozen fictional Actions and Work Items, and
keeps search, selection, Focus/filter, sequence-state, source, page, and pin
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

Owns pure runtime Focus policy independently of Tk and persistence. It discovers
available Focus names, resolves Action-only legacy slots and typed mixed slots,
reconciles saved slots against current explicit membership, handles
unavailable-Focus fallbacks, and selects canonical visible Action plus configured
Work Item membership. Stale references are ignored in memory rather than
rewriting personal configuration during reload. The launcher uses that same membership for
**Focus items** and deterministic Focus-first grouping in **All items**.
This remains the replacement boundary for future Context-model changes.

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
previous Context bytes if the paired metadata write fails. Configure scans use
the existing background coordinator;
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

The main content is one user-adjustable horizontal split. It starts at
approximately 40% for the command console and 60% for Input / Output, while
guaranteeing at least half of the default width to the workspace. The bounded
sash keeps both panes usable and preserves a user-adjusted ratio during later
resizing in the session.

The command console stacks discovery above the independently scrolling Quick
actions. Discovery shows seven result rows at the standard size so the complete
standard Quick-action grid remains visible. Focus and scope navigation sit
above Find; one Filters menu shares the Find row; and `+A`,
Edit, Pin, and Run/Open form one stable row below the full-width results.
Actions adds type filtering; Work Items adds New item, To inbox, Copy file,
project filtering, Open, and Open folder through the same stable surface. Quick actions
use two columns at the standard and supported minimum widths, falling back to
one only when the console is narrower. Its canvas height follows the rendered
row height instead of expanding; discovery owns the remaining vertical space
and its result list grows with it. Input / Output consumes nearly the full
right-pane height; its existing communication line sits at the bottom. Capture,
Inbox, Create from Input, and Text tools use bitmap-icon controls in the
workspace header. Configure, Help, and More follow Quick actions. Focus,
discovery scopes, Work Items, and Run/Open retain text because their state must
remain immediately readable. Search text can be combined with one shared
built-in action-type filter; credentials remain selectable through that type
filter and the fixed Passwords Quick-action menu.

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

### Previewable Action sequences

`action_sequences.py` owns the pure `SequenceStep` model, structural bounds,
live reference resolution, immutable run plan, and readable ordered preview.
A sequence persists an explicit `steps` array containing only Action references
and waits. It can reference Active `open_url`, `open_file`, `open_folder`,
`launch_app`, and `open_windows_target` Actions. Nested sequences, clipboard
inputs, credentials, transformations, and missing or Archived references fail
before any effect.

The Action editor adds, removes, and reorders existing Actions and bounded
waits without displaying technical IDs. The launcher resolves every reference,
shows one complete confirmation, and schedules each step through Tk so the UI
remains responsive. While a sequence is active, FocusOut auto-hide is suspended
and the palette remains above launched windows so step progress and the attended
**Stop remaining** control stay accessible. **Stop remaining** cancels only the pending callback;
already opened targets or started processes are not rolled back or terminated.
Archive/delete treats sequence references as blocking semantic dependencies,
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

Input / Output is a permanent editable working text box, not action documentation. It synchronizes from the clipboard when shown and can be explicitly copied, pasted, cleared, transformed, or replaced by actions. Inline transformations apply to the selection, or the complete field when there is no selection, and copy their result to the clipboard. Pure transformation logic lives in `actions.py`; `workspace_panel.py` owns selection ranges, one-step Undo grouping, clipboard updates, and menus. The launcher injects clipboard, status, and content-change callbacks and retains orchestration delegates. A selected item places its current-state **Input → Effect** summary in the slim bottom communication line; progress, success, and errors temporarily replace it. Hovering or clicking that line exposes the full structured explanation and current operational message.

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

Numbered action dispatch is enabled only when the Find entry owns focus. All other widgets suppress it, making shortcut mode explicit and preventing accidental execution while navigating or editing. The communication line never wraps; its stable **Input → Effect** summary is bounded to 220 characters. Full structured Type, Input, Effect, configured-value, and recovery information is retained separately for a dynamic hover tooltip and click-open detail window. Editing Input / Output refreshes the current preview without changing Action execution semantics or treating a highlighted text range as Action input.

Shortcut numbers are intentionally omitted from result labels. Blue rows map top-to-bottom to pinned shortcuts 1–5, green rows map top-to-bottom to Focus shortcuts 6–0, and neutral rows are ordinary results; row tooltips expose the exact binding. Action and Work Item rows measure every icon in the active Tk font, pad narrower symbols to one shared pixel column, and render the short name directly without a dash. The flat mixed-result Treeview item layout omits the unused expand/collapse indicator so that its gutter does not survive the removed number column. A non-action separator row divides shortcut rows from ordinary Action-only results; mouse and keyboard selection skip that separator. Standard editing and transformations are available through the context menu and the visible catalogue-backed **Text tools** menu.

## Focus contexts and slots

The application currently implements a focus context rather than a complete multi-context inference engine.

```text
1–5  global pinned actions
6–0  focus-context Actions or Work Items
other rows  ordinary search matches
```

Changing the focus context changes slots 6–0 only. Search always remains global.

The **Focus items** control is a reversible, visibly active presentation mode.
With Find empty, it shows a flat mixed list of visible Actions and Work Items
belonging to the active Focus. General contains every Action and discovered
Work Item; a specific Focus uses the matching Context definition's canonical
Action and Work Item membership. Typing in Find swaps this view for global
mixed results, and clearing Find restores Focus items while that mode remains
active. Outside Focus view, the normal **All items** projection applies shared
Context and tag filters to both entity kinds. **Actions** and **Work Items**
remain explicit scopes for kind-specific filters and commands. Tags remain
independent filters rather than structural ownership.

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

Quick-action groups currently remain global. Context-based visibility or
grouping is deliberately out of scope; a later design can reference Contexts
without changing the typed Action/Work Item target identity.

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

Application shutdown cancels every pending callback registered in the shared
Tk interpreter only after active Work Item and backup/restore operations have
cleared their quit guard. Short-lived child windows cancel their own delayed
focus callbacks when destroyed, so closing a dialog cannot leave an orphaned
Tcl timer behind.

Configuration reloads are skipped when active file existence, modification time, and size are unchanged. Typed search changes are coalesced over 40 ms before recalculating slots and rows.

Configuration reload is transactional in memory: combined shared/local actions,
contexts, and quick-action groups replace their active lists only after complete
validation succeeds. A failed external edit reports the affected file and
retains the last successfully loaded interface configuration.
Presentation reload deliberately retains configured external Action references
without probing their current targets. This matches snapshot/restore
portability policy; creation, editing, and execution retain their stricter
target validation.
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
- Extend clipboard transactions beyond protected plain text only with
  action-specific timing and format semantics before adding sequence paste,
  Tab, or Enter steps.
- Consider optional application-aware context suggestions that never switch focus silently.
- Add rich HTML and image actions only with explicit clipboard semantics.

These are proposals, not implemented capabilities. See [Roadmap](ROADMAP.md).
