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
- Notifies an existing instance when one is running.
- Starts the Tk launcher with paths to local data.

### `launcher.py`

Presentation and application orchestration.

- Builds the Tkinter interface.
- Maintains the explicitly selected focus context through a compact menu launcher.
- Exposes the complete configuration workspace through one direct
  **Configure** button. The Focus selector retains a direct **Manage focuses…**
  route to the Contexts tab.
- Renders numbered slots, global flat search results, or an explicitly activated
  flat list of actions belonging to the selected Focus.
- Renders a global JSON-configured quick-action surface beside search results,
  plus an explicit allow-listed `open_sheets` application command.
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

The main-window construction is divided into focused header, results/command-surface, shortcut, workspace, and footer builders. Inbox and Draft windows still live in this module and are the next safe extraction boundary; this is documented in `TECHNICAL_REVIEW.md`.

The launcher does not implement action transformations or window matching directly. Those responsibilities live in specialized modules.

### `harvest.py` and `harvest_window.py`

`harvest.py` is the platform-independent bulk document-harvesting boundary. It
defines transient source, occurrence, candidate, and batch models; bounded
local extractors for `.md`, `.txt`, `.docx`, and `.xlsx`; conservative URL
normalization and semantic deduplication; Draft conversion; and the background
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
| Actions, empty Find | Ordinary actions, including slots 1–9 | Passwords, Work, Types, Tags, Help | Run |
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
- Guided creation and JSON loading share the same action-value validation, while
  execution retains safety checks around platform effects.
- Arbitrary shell commands are rejected.
- Pure transformations are separated from UI callbacks.
- Platform effects are injected through callbacks where practical, enabling tests without opening applications.
- Clipboard access during template expansion is lazy: actions without clipboard variables do not fail when the clipboard contains a non-text format.

### `action_types.py`

Defines the machine-readable catalogue for every supported action type: user label, family, description, required fields, input/output effects, portability, AI eligibility, and type-specific AI guidance. `actions.py` derives its supported-type set from this catalogue, and AI prompt generation consumes the same definitions.

The catalogue renders `docs/ACTION_TYPES.md`; an automated test requires the user-readable overview to remain identical to the executable definitions.

### `workspace_transforms.py`

Defines the ordered, user-facing catalogue for Input / Output transformations:
menu groups, labels, operation keys, completion feedback, and whether an
operation needs an additional prompt. The launcher renders its Transform menu
from this catalogue instead of repeating every command in the UI orchestrator.
Pure transformation algorithms and validation remain in `actions.py`.

### `workspace_panel.py`

Owns the complete Input / Output UI component: text widget, edit and Transform
menus, selection-first replacement, undo boundaries, prefix/suffix prompting,
clipboard copy and replacement, and transformation feedback. It depends on
small injected callbacks for clipboard access, status messages, and tooltip
registration. `launcher.py` retains compatibility delegates for action
execution and integration flows, but no longer owns workspace widget mechanics.

### `action_discovery_panel.py`

Owns construction and event wiring for the left action-discovery presentation:
heading and count, global Find entry, type and tag controls, Run and Help
controls, flat result list, Focus list, scrollbar, and row tooltips. Search
policy, action ranking, filtering, Focus membership, selection meaning, and execution remain in
`launcher.py` and are supplied through narrow callbacks. Compatibility aliases
allow existing launcher orchestration to migrate incrementally.

Right-click callbacks preserve the clicked flat or Focus row as the current
selection, then route its stable action ID into the existing Configure Actions
workspace. `configuration_window.py` highlights that action after rendering;
personal actions persist to the ignored local action file. Shared actions may
also be edited after an explicit risk warning and persist to the Git-tracked
shared action file.

### `context_membership_field.py`

Provides reusable comma-separated picker fields used by Configure, Inbox
conversion, and Draft editing. Context membership combines an editable field
with a checklist of canonical defined contexts. Tag selection uses the same
interaction for existing normalized tags but continues to allow new free-form
values. Selection mechanics remain separate from domain validation in
`actions.py`, so typed values and non-UI callers follow the same persistence
rules. Underlined Windows mnemonics move focus directly to each field, and
`Alt+Down`/`F4` delegates checklist opening to Tk's native menubutton behavior.

### `persistence.py`

Owns JSON replacement for application-written data. It serializes to a temporary sibling file, flushes it to disk, preserves the previous destination as `<name>.bak`, and uses `os.replace` so readers see either the previous complete file or the new complete file. Temporary and backup files are ignored by Git because they can contain private runtime data.

Actions, Inbox state, and palette state use this single writer.

### `configuration_check.py`

Provides a read-only project validation report and command-line exit status. It
reuses the existing action, context, command-surface, Inbox, palette, and
cheat-sheet loaders, then verifies that context, command-surface, and palette
action references resolve. `check-context-palette.bat` runs this validation
before source compilation and the complete unit suite.

### `retired_feature_cleanup.py`

Owns narrow, idempotent migrations for deliberately removed local features.
Setup and application startup remove retired action records and their references
from ignored local actions, contexts, quick buttons, and palette state. Every
changed file is written through `persistence.py`, preserving its previous
contents as an ignored `.bak`. The migration stores and logs aggregate counts
only; it does not inspect credential secrets or delete legacy snapshot files.

### `configuration_window.py` and `configuration_data.py`

Provide the guided configuration workspace and its persistence operations.
Action creation starts from the executable built-in action catalogue, which
includes a concrete example for every type. Every personal and shared action
type is editable. Editing a shared action requires acknowledging that its file
is tracked by Git and can affect other machines; the warning also prohibits
personal paths, secrets, and private work details. Personal contexts can assign
slots 6–9, and personal Quick actions can reference existing actions without
exposing technical IDs. Shared contexts and Quick-action records remain
read-only. Writes use the same atomic JSON replacement path as the rest of the
application.

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
- Slots 6–9: top four actions for the focus context.
- Duplicate actions across both groups are intentional.
- Unfilled context slots prefer other actions belonging to the active Focus,
  then fall back to remaining globally available actions.

### `command_surface.py`

Loads and validates global quick-action groups and their compact items from shared and local JSON. Each item has an individual action menu and retains its source configuration path. Groups reference existing action IDs; they do not define a second execution language. Duplicate group IDs and duplicate item IDs within a group are rejected case-insensitively.

The module also owns the canonical primary-first, duplicate-free action ordering used by execution, menus, Configure, and configuration validation.

### `tooltips.py`

Owns delayed tooltip behaviour for ordinary widgets and individual listbox rows. Keeping these presentation helpers outside `launcher.py` prevents the main application orchestrator from also owning reusable hover-window mechanics.

### `style.py`

Owns the shared native ttk theme, Segoe UI font policy, grey/teal/aqua palette, and hover/focus state maps. Classic Tk widget defaults are applied through the root option database. The module changes presentation only; widget construction, layout, geometry, and action behaviour remain in their existing owners.

### `help_window.py`

Owns the reusable in-app Markdown document viewer. It renders the project's
headings, emphasis, code, lists, quotes, separators, and tables with native Tk
text styles; provides in-document search; opens local Markdown links in place;
offers a Documents menu for repository Markdown pages; and maintains explicit
Back, Forward, and Home history. Navigation is restricted to `.md` files
beneath the viewer's local document root. `launcher.py` opens Help and the
authoritative Keyboard Shortcuts page through this component and injects an
opener into the normal action dispatcher so existing `.md` open-file actions
use the same viewer. The Browser control hands only the current validated local
file URI to the default browser. Each page render removes obsolete dynamic link
tags and bindings so navigation cannot accumulate them in the resident process.
Non-Markdown file actions retain the platform opener.

### `cheat_sheet_window.py`

Owns the searchable Cheat Sheet secondary window, including selection, preview,
and promotion to a local Draft action. `launcher.py` retains loading and
orchestration responsibility.

### `hotkeys.py`

Native Windows hotkey and selection-copy support using `ctypes`.

- Registers one-key `F9` and fallback `Ctrl+Alt+P` with `RegisterHotKey` and no-repeat behaviour.
- Runs the Windows message loop on a daemon thread.
- Queues activation back to `LauncherApp`; it does not manipulate Tk widgets from the background thread.
- Sends a constrained `Ctrl+C` sequence before the palette takes focus.
- Captures cursor coordinates and the nearest monitor work area in the hotkey thread, then uses the cursor as the palette's top-left anchor. The position is clamped only when needed to keep the complete window on-screen.

### `contexts.py`

Loads and validates standalone shared and local context definitions. A definition provides identity metadata and up to four preferred action IDs. Explicit per-machine choices in `palette.json` override configured defaults.

### `focus_model.py`

Owns pure runtime Focus policy independently of Tk and persistence. It discovers
available Focus names, resolves preferred slots and unavailable-Focus fallbacks,
and selects the flat action membership list for a Focus while preserving
canonical action order. This is the intended replacement boundary for future
context-model changes.

### `work_items.py`

Owns the pure, UI-independent first phase of Work Items discovery. Immutable
source and discovered-item models validate stable source identity and absolute
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
the main thread, so worker code has no Tk callback or widget access. A local
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
is delivered to Tk only through main-thread polling.

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

Untrusted AI response text has a 1,000,000-character ceiling enforced before
JSON parsing. The clipboard handoff applies the same limit before replacing the
response widget, avoiding unnecessary UI and parser memory amplification.

`ai_guidance_window.py` owns the attended clipboard handoff: choose guidance, review and copy the request, paste an AI response, validate and select proposals, and explicitly create local Draft actions. It also exposes the local test-response path and per-proposal validation status. Selected proposals are batch-validated before the local action file is written. The window does not contact an AI provider, store credentials, or promote actions to Trusted.

### `cheatsheets.py`

Structured local reference material.

- Loads and validates sheet JSON.
- Searches sections, labels, details, and tags.
- Promotes an individual sheet entry to a Draft action.

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
title
contexts
tags
type
value
state
arguments
working_directory
```

`contexts` and `tags` are optional lists. Every action belongs to the virtual
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

Compact result rows show:

```text
Command → subject
```

The command is taken from a recognized leading verb such as Open, Copy, Convert, Search, Arrange, or Restore. When a title does not include one, a suitable command is inferred from the constrained action type. Contexts, tags, and the original title are shown in a delayed per-row hover tooltip.

The full explanation path is:

```text
Contexts | Tags | Action title
```

Search indexes title, tags, contexts, type, value, and maturity state. Multiple query terms use AND semantics. The tag menu applies an additional exact tag filter.

This separation allows visual simplification without losing retrieval power.

Secondary application screens share a `780x600` default and `700x480` minimum
through `window_geometry.py`. The main window keeps the same `780` width but
uses available monitor height up to `1000` pixels, while retaining a compact
screen-aware minimum. Hotkey placement reduces an oversized window before
clamping it into the cursor monitor's work area.

The main content is a user-adjustable vertical split: approximately 52% for
action discovery and 48% for Input / Output. The ratio scales with window
height; after the user moves the divider, their chosen ratio is used for later
resizing in that session. Sash positions are bounded to keep both panes usable;
when a display cannot fit both preferred minimums, the available space is
divided proportionally. Inside the upper area, a responsive horizontal pane
starts at approximately 44% for the Actions workspace and 56% for the global
quick-action surface. The Actions workspace owns its heading/count, Find entry,
numbered scrolling list, and an 88-pixel rail containing the existing
Passwords, Types, Run, and action-Help controls. The Quick-action side retains
its vertical menu launchers and independent scrolling. The horizontal pane
retains a user-adjusted ratio during later resizing and applies the same
bounded-sash behavior. Fixed bottom action and
status rows remain outside the vertical split, preventing them from being
displaced. Management buttons use a single compact symbol row with name-first
tooltips.
Search text can be combined with one shared built-in action-type filter;
Passwords is a direct shortcut into that same filter state.

Each group renders in stable row-major order within a two-column grid. Its
subjects are full-width vertical menu-launcher rows with a native `▾`
affordance. The affordance is style-only: left-click runs the primary-first
available action, right-click exposes the same canonical action-ID menu, and
Shift/Ctrl+click opens the owning menu and action configuration files.

Quick-action labels participate in keyboard focus. Enter or Space executes the first available primary action. Empty search, Inbox, cheat-sheet, and command-surface states contain recovery guidance rather than blank widgets. Reloads use a short busy cursor/status state; local loading is intentionally not animated.

Ordinary widget tooltips respond to both pointer hover and keyboard focus. This
keeps the full names and explanations of compact symbol controls available
without expanding the fixed-size main-window layout. They prefer the space
below a control, move above it near the bottom edge, and remain inside the
virtual desktop, including secondary monitors with negative coordinates.

Configured Quick-action subjects and allow-listed built-in subjects share one
mouse/keyboard binding contract for left click, right click, Enter, and Space.
Their dispatch callbacks remain separate, so consolidating interaction wiring
does not broaden the built-in command allow-list or action execution model.

## Supported action types

The current allow-list includes:

- `copy_text`
- `open_url`
- `open_file`
- `open_folder`
- `launch_app`
- `paste_credential`
- `build_url_copy`
- `build_url_open`
- `build_url_selection_open`
- `transform_list_csv`
- `workspace_template`

Action types that cause external effects use constrained implementations.
`launch_app`, for example, accepts an existing absolute `.exe`, fixed argument
list, and optional validated working directory. `paste_credential` accepts only
an exact standard Windows or generic credential target, requires Trusted state and a fresh
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
        +-- URL builder -> consume workspace -> copy/open URL
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

The transformation menu groups deterministic operations into Case, Whitespace,
and Lines. Line operations preserve the detected line-ending style and final
newline where applicable.

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

The **Focus actions** control is a separate presentation mode. With Find empty,
it shows a flat list of visible actions belonging to the active Focus in
canonical action order. General contains every action; a specific Focus uses the
action's `contexts` memberships. Typing in Find swaps this view for the global
flat results, and clearing Find restores Focus Actions only when that mode was
explicitly activated. Tags do not create folders in this view because they are
independent filters rather than structural ownership.

Quick actions remain action-ID configuration. Built-in application commands are
not configurable strings or method names: the launcher contains a closed,
testable allow-list whose sole member is `open_sheets`, which invokes the
existing Sheets window. Knowledge and AI are stable built-in groups in the
first two-column row before configurable groups. AI prompt discovery is a pure
filter over active first-class `ai_prompt` actions; execution still uses the
ordinary constrained action path. Its initial executor intentionally shares
review-first workspace/clipboard behavior with templates while retaining a
separate type identity for future prompt-specific evolution.

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

### `data/actions.json`

Reviewed portable action records shared through Git.

Action IDs are unique case-insensitively within a file and across shared/local files. This keeps pins, context slots, command-surface references, edits, and trust promotion unambiguous.
New records store optional `contexts` and `tags` arrays. Omitting `contexts`
means General-only membership; General itself is never persisted as a specific
membership.

### `data/contexts.json` and `data/local_contexts.json`

The shared file contains reviewed portable context definitions. The ignored local file contains personal or work-specific definitions.

### `data/command_surface.json` and `data/local_command_surface.json`

The shared file contains portable global quick-action groups. The ignored local file can add personal or machine-specific groups. Both refer to actions by stable ID.

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
access. Configure routes `Alt+A`, `Alt+T`, `Alt+C`, `Alt+Q`, and `Alt+D` through
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
- Do not execute arbitrary shell command strings.
- Keep API keys out of version-controlled files.
- Never enumerate or write Windows credentials. Credential actions store only
  exact target names and are unavailable to AI proposal and external execution paths.
- Require explicit user action for launches and trust promotion.
- Treat captured text and AI responses as untrusted data. AI requests are previewed and copied manually; responses must remain within the bounded size limit and pass the versioned proposal schema and existing action validation before selected proposals become local Drafts.

## Testing strategy

Tests use `unittest` and focus on pure or callback-injected behavior.

- Action parsing, search, execution dispatch, transformations, and URL building.
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

- Extract secondary Inbox and Draft views from `launcher.py` without changing behavior.
- Add supporting-context composition and weighted ranking.
- Design safe linear action sequences and clipboard transactions as explicit, previewable models.
- Consider optional application-aware context suggestions that never switch focus silently.
- Add rich HTML and image actions only with explicit clipboard semantics.

These are proposals, not implemented capabilities. See [Roadmap](ROADMAP.md).
