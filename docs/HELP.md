# Context Palette Help

Context Palette is a fast, portable Windows launcher for reusable actions,
work Contexts, captured material, and transformations.

The interface uses a neutral surface with Segoe UI typography and a dark teal
accent. The selected **All items / Actions / Work Items** control uses pale teal
with dark text; **Run/Open** stays solid teal. Green rows identify the active
Context bank's shortcuts 6–0, and neutral rows are ordinary results. Alternating
light/darker row bands separate neighboring results, including within the
green shortcut group; the selected row stays solid teal with white text. Focus
borders make keyboard location visible. Input / Output keeps its monospace
font, with a themed focus border and teal text selection. Quick-menu launchers
have one right-aligned arrow; click, keyboard browsing, and right-click editing
work as before.

Developers can find the current implementation in
[Architecture](ARCHITECTURE.md) and its chronological rationale in
[Decisions](DECISIONS.md).

Help is rendered as Markdown inside Context Palette. Use **Documents** in this
window to open other project Markdown pages, or activate a rendered local
Markdown link. Use **←**, **→**, and **Home** to move through document
history or return to the page that opened the viewer. Choose **Edge** to open
the current validated local Markdown file in Microsoft Edge, where an installed
Markdown extension can provide browser-grade rendering.
`Alt+Left`, `Alt+Right`,
and `Alt+Home` provide the same navigation from the keyboard; `Ctrl+F` searches
the currently displayed page. Open-file actions targeting an existing `.md`
file use this viewer automatically. Other file actions keep their normal
Windows behavior. The viewer never opens arbitrary commands.

Context Palette looks for Edge on `PATH` and in the standard per-user and
system installation folders. If Edge cannot be found, the viewer remains open
and shows an error in its status line. The Markdown extension must have
permission to read local `file:` URLs if that extension requires it.

The viewer supports normal headings, emphasis, nested lists, block quotes,
fenced code, links, separators, strikethrough, and responsive bordered tables.
It is a normal resizable Windows window and can be maximized from its title bar.
For safety it treats embedded HTML as text and does not run JavaScript, submit
forms, fetch remote content, or navigate to web links. Images are currently not
loaded inside the viewer.

Multi-PC cloning, GitHub publishing, portable paths, and shared/local data are
documented in [Multi-PC development](MULTI_PC_DEVELOPMENT.md).
OCR installation, offline handoff, use, configuration transfer, and developer
verification are documented in [OCR setup](OCR_SETUP.md).
Each development computer creates its own ignored `.venv` by running
`setup-context-palette.bat` or `develop-context-palette.bat`. Setup accepts
Python 3.12 or newer 3.x only when pip and Tkinter are available; it preserves
an incompatible local environment as `.venv-unusable*` before rebuilding.
Personal Context Palette data is stored outside `.venv`.
After pulling a revision with changed requirements, stop the resident app and
run setup again. The normal launcher checks the tracked requirements signature
and refuses to start with a stale environment instead of silently omitting a
feature.

Image-to-text extraction uses an optional local OCR component. From the Context
Palette folder, run `setup-ocr-context-palette.bat`, then restart the app. It
stays inside that folder, needs no administrator rights, and adds about 270 MB.
Recognition works offline after setup; the initial setup download requires
package access. If compatible Python and Tk are installed but package downloads
are blocked, prepare `offline-packages` on a connected compatible PC and run
`setup-offline-context-palette.bat` on the target. If compatible Python itself
cannot be installed, the current source distribution cannot run there.

Power Automate Desktop setup is documented in
[Power Automate integration](../integrations/README.md).

## Create Actions from Excel

Press `Ctrl+,`, open **Actions**, then choose **More Action tasks → Get blank
Actions workbook…**. Save the generated standard `.xlsx`, fill one Action per
row on its **Actions** sheet, save it, and choose **More Action tasks → Create
Actions from Excel…**. The same review window can save a blank workbook or
choose another one.

The workbook includes Instructions and a Reference sheet of supported Action
type IDs and labels. Blank **Import** means Yes; enter No to keep a row visible
but excluded. Separate Contexts and Tags with semicolons, Quick-menu levels with
`>`, and Arguments with line breaks. Leave Contexts blank for General only.
Only already-defined My configuration Contexts can be assigned.
Arguments and **Working folder** are accepted only for application and
Windows-target Actions; irrelevant hidden fields are reported as row errors.

Context Palette reads at most 1,000 populated rows from the exact versioned
workbook. It does not start Excel or Python Excel, run macros, follow links, or
evaluate formulas. Formula cells, changed headers, unsafe/corrupt packages, and
unsupported Action types are rejected. Sequences and fixed Excel automation
Actions are intentionally outside this generic workbook. The folder-only
**Save current score as PDF** Action is allowed but is never run during import.
Text-file transforms
also stay in their guided editor because their operation parameters can include
meaningful empty or whitespace-only values that a simple Excel cell cannot
represent safely.

The review lists Ready, possible-duplicate, exact-existing, excluded, and error
rows. Ready rows start selected; duplicate warnings require an explicit choice.
Inspect the selected row's complete value, Contexts, tags, and messages. The
workbook and saved Action collection are rechecked immediately before the one
effect-labelled **Create N Actions** operation. Created records are personal
Active Actions and nothing is run during import.

This workbook remains create-only. Updating uses the separate identity-bound
workbook below. Deletion remains a separate reviewed in-app operation.

## Update personal Actions from Excel

Press `Ctrl+,`, open **Actions**, then choose **More Action tasks → Export
personal Actions for update…**. Save the generated version-1 standard `.xlsx`,
edit it, and save it without changing its structure. Then choose **More Action
tasks → Review updated Actions workbook…** and select that file. This is a
separate contract from the blank creation workbook.

The workbook contains only eligible **My configuration**, Active Actions. It
does not export Built-in or legacy inactive Actions, sequences, fixed Excel-automation
Actions, or text-file transformations. **Action ID**, **State**, **Action type**,
and **Original fingerprint** are verified identity fields; do not edit them. You may edit
**Name**, **Value**, personal **Contexts**, **Tags**, **Description**, **Quick
menu**, **Arguments (JSON)**, and **Working folder**. JSON arguments preserve
empty and whitespace-only values that a line-based cell cannot represent
losslessly. Leave Contexts blank for General only; only existing personal
Contexts are accepted.
Separate Contexts and tags with semicolons. If a Context or tag itself contains
a semicolon, enclose that one value in double quotes, for example
`"Client; Europe"; Monthly`.

Context Palette reads the workbook locally through the same bounded ZIP/XML
boundary as bulk creation. It never starts Excel or Python Excel, runs an
Action, evaluates a formula, follows a link, or runs a macro. Formula cells,
macros, links, changed headers/identity, corrupt or unsafe packages, and stale
original fingerprints are rejected. Removing an exported row does not delete
or otherwise change its Action.

The attended review marks only real valid changes **Ready** and selects those
rows by default. Select a row to compare exact Before and After values; clear
any Ready row you do not want. **Update N Actions** is the one confirmation,
with no second Yes/No dialog. Immediately before writing, Context Palette
rechecks the workbook and current Action/Context configuration. Selected Ready
changes are applied together; if Context persistence fails, the exact previous
Action bytes are restored. If that rollback cannot restore every participating
Action, Context, or backup file, the review is locked and reports that saved
configuration may have changed. Do not retry that workbook; inspect the latest
backups and Diagnostics, then verify the saved configuration first. After
success, export a fresh workbook before making another batch. Removing a
workbook row still never deletes an Action.

## Delete multiple personal Actions

Press `Ctrl+,`, open **Actions**, then choose **More Action tasks → Delete
multiple personal Actions…**. This is an in-app review; no spreadsheet is
required. Only **My configuration** Actions are offered. Use Find, select the
exact rows you intend to delete, and inspect the combined number of Context,
slot, and configured Quick-menu references plus any dependent sequences.
Active and legacy inactive records can be selected together.

Find narrows the shown rows without clearing selection. **Select all shown**
adds only visible rows; **Clear selection** clears the complete selection. The
status reports selected rows hidden by the current filter, and the final
**Delete N Actions permanently** label counts them. That effect-labelled button
is the only confirmation; there is no preparation stage or extra Yes/No dialog.

A referenced Action is blocked unless its dependent sequence is also selected
in the same stage or edited first. Every file is rechecked immediately before
the batch write. If a write fails, Context Palette restores the exact previous
configuration and backup-sidecar bytes when possible. The workflow never runs
an Action and never deletes or changes its target file, folder, website,
workbook, application, credential, or Inbox item. Built-in Actions retain their
ordinary direct-delete review because their changes travel through Git.

## Harvest website links from documents

For the primary route, press `Ctrl+,`, then open **Actions** and choose **More
Action tasks → Harvest website links…**. You can also choose **Harvest website
links...** in Inbox. The workflow extracts possible website actions from
several documents at once. Supported files are Markdown (`.md`), text (`.txt`),
Word (`.docx`), and Excel (`.xlsx`). Context Palette reads these files locally;
it does not start Office, evaluate formulas, run macros, fetch links, or execute
discovered content.

The review window shows each source and every candidate URL with its label and
location. Search or filter the list, inspect provenance, edit one candidate,
select or deselect candidates, and add or remove Context memberships and tags in
bulk. A specific active Context filter is proposed as membership; **General**
remains implicit. Source filenames and folders are not converted into tags.

The workflow is keyboard-operable. Use `Ctrl+O` to add documents, `Ctrl+F` to
focus candidate search, and `F5` to rescan. In Sources, `Delete` removes the
highlighted source. In Candidates, `Space` changes inclusion and `Enter` edits
one highlighted candidate. Focus moves to the candidate results when a scan
finishes, or to Sources when the scan has no candidates. The action preview has
an explicit Close button and closes with `Esc`.

Only HTTP and HTTPS targets can become actions. Existing Active URLs
and repeats across the selected documents are identified before creation. Word
hyperlinks, Excel hyperlinks, plain URL cells, and literal `HYPERLINK` formulas
are readable; formulas are never calculated. Unsupported targets stay visible
but cannot be selected.

Choose **Preview selected actions**, then **Create selected actions**. All selected
actions are validated again and written to the personal action file together;
their Context memberships are synchronized to My configuration Context
definitions, with rollback if either write fails. They are permanent Active
actions. Cancelling the scan or closing the review window creates nothing.
Per-file failures do not discard successful results from other files, and
size, compression, worksheet, cell, occurrence, and candidate limits keep
scans bounded.

Folder scanning or source drag-and-drop inside website Harvest, OneNote document
extraction, PDF/HTML/email parsing, recursive crawling, remote fetching, and
automatic trust are not part of this version. The separate general drop target
can place dropped paths, links, or text in Input / Output; it does not add a
Harvest source automatically.

## Open and close the palette

- Start once with `run-context-palette.bat`.
- The main window opens at a compact `780x600` on an ordinary monitor. By
  default, the command console occupies about 40% of the width and Input /
  Output occupies about 60%. Drag the vertical divider to adjust that balance
  for the current session.
- Press `F9` or `Ctrl+Alt+P` to capture the current text selection and show the resident palette. On laptops in media-key mode, use `Fn+F9` or enable Fn Lock.
- The mouse cursor chooses the monitor when `F9` or `Ctrl+Alt+P` is pressed;
  the palette opens in the middle of that monitor's usable area.
- Configuration, Help, action editors, pickers, Sheets, AI, Inbox, Harvest, and
  Work Item windows open in the middle of the usable area of their owner's
  current monitor. Moving an owning window to another monitor before opening
  its next screen moves that placement policy with it. Compact filter pickers,
  native menus, and tooltips stay attached to the control that opened them.
- Press `Esc`, click `Hide`, or close the window to hide it.
- The small **Drop into Context Palette** window is separate and stays visible
  when the main palette hides. It remains movable near the lower-right instead
  of being centered; its own **Hide** command hides only that target.
- Press `Ctrl+L` or `Ctrl+K` to return keyboard focus to Find.
- Press `Ctrl+I` to capture clipboard text, `Ctrl+,` to open Configure, or `F1` to open Help.
- Press `Ctrl+Shift+D` to open Configure directly on the safe Diagnostics tab.
- Open **More → Show drop target** to restore a hidden drop target, or
  **More → Keyboard shortcuts** for the authoritative shortcut page.
- Press `F5` while the main palette is focused to clear transient screen state
  and return to the startup view. Find, scope, Context/tag filters, Action type,
  Work Item project filter, captured selection, and Input / Output are cleared.
  Per-Context slot assignments, legacy focus/pin compatibility data, Actions,
  and configuration are preserved; **All contexts** and General's slot bank
  become active.
- Choose **Configure** for a visible route to the complete
  personal-configuration workspace.
- Click `Quit` to stop the resident process completely.
- If a development instance becomes stuck, run `stop-context-palette.bat` and start again. The stop command targets this project's virtual-environment GUI and foreground diagnostic process trees; it does not stop unrelated Python applications or Context Palette clones in other folders.

External Windows tools may safely show and pre-filter the existing instance:

```powershell
.\integrations\Invoke-ContextPalette.ps1 -Context "Database" -Search "SQL"
```

The `-Context` value selects the same transient Context filter and slot bank as
the launcher. This does not execute the highlighted action or persist the
filter. Avoid passing secrets or selected text as command-line search values.

## Context filter and slots 6–0

Use the unified **Filter** menu beside Find as the launcher's one Context
choice:

- **Filter by context…** limits results to the canonical Action and Work Item
  members of one specific Context and selects that Context's mixed
  Action/Work Item slot bank for 6–0.
- **All contexts** restores global retrieval and selects General's slot bank.
- **Filter by tag…** limits results to one exact reusable tag.
- Context and tag apply consistently to **All items**, **Actions**, and **Work
  Items**. Action type appears only in Actions; project appears only in Work
  Items.

Only Context chooses the slot bank. Find, tag, Action type, and Work Item
project narrow visible results without selecting another bank. The Context
filter is transient: `F5` and restart return to **All contexts** and General's
bank. No filter state is added to personal configuration and no data migration
is required.

- Slots `6–0` are the top five genuine Actions or Work Items for the active
  Context bank. Slot `0` follows slot `9`. Unfilled slots remain empty and
  never borrow unrelated items.
- Historical global pin IDs 1–5 remain in `data/palette.json` for rollback,
  but are no longer shown, configured, or executed.

When Find is empty, eligible rows from the active Context's slot bank may appear
first. Tag, type, and project can narrow which rows remain visible without
selecting another bank. As soon as Find contains text, slot rows are not
promoted: matching items are ranked by exact visible name, name prefix, other
name matches, then Context/tag/type/project metadata. Context definitions and
per-Context slot choices remain persisted even though the active Context filter
does not.

Open the unified Filter menu and choose **Manage contexts…** for a direct route,
or choose **Configure** (or press `Ctrl+,`) and select **Contexts**. There you
see **General — All items** first. General's membership, name, and lifecycle are
automatic and cannot be edited or deleted; choose **Edit shortcuts…** to select
up to five preferred Actions or Work Items for its slots 6–0 on this computer.
Rows labelled **Automatic — _item_** show the shortcuts currently in use without
being saved as overrides. Choose fixed items from slot 6 downward; return every
row to **Automatic** to restore fully automatic General ordering.
For a specific Context, create or edit its membership and preferred slots as
before. **My configuration** definitions stay on this PC. **Built-in**
definitions show a developer warning before editing. The only shipped specific
Context is **Developing Context Palette** in
`data/contexts.json`; personal or work-specific definitions live in ignored
`data/local_contexts.json`. The complete format is documented in
`docs/CONTEXT_CONFIGURATION.md`.

## Find and open Palette items

The left side is one compact command console. The three view choices sit above
Find; Find and the result list use the full console width. Quick actions appear
underneath. Choose **All
items** to find Actions and Work Items together, **Actions** for
Action-specific tools, or **Work Items** for Work Item tools. The selected view
is highlighted and does not change the shared Context/tag filters or selected
slot bank. The filter icon beside Find contains the current view's secondary
commands and filters. Active filters appear in one readable chip below Find;
activate the chip to clear them. A type or project filter retained from another
item scope stays named in that chip while dormant, so no hidden state surprises
you when returning to its scope.

Quick actions use only the height required by their visible menu rows. Extra
space automatically enlarges the result list instead of leaving a blank area
below the last Quick-action menu.

Find, **Context**, and **Tag** apply to both Actions and Work Items. A selected
Context filter uses canonical membership for both kinds; a shared Context or
tag can therefore return both kinds in one result list.

- Type in **Find item** to filter both kinds by their searchable names and
  metadata.
- Open the filter icon and choose **Filter by context…** or **Filter by tag…**
  to search and select one exact value. Choose **All contexts** or **All tags**
  to clear it. Changing Context also changes the 6–0 bank; changing tag does
  not. Active filters highlight the icon and appear together in the removable
  chip.
- Select an Action to show **Run**. Select a Work Item to show **Open** and the
  adjacent folder command. Enter and double-click use the selected kind's
  normal execution policy.
- Right-click opens the selected Action in Configure or shows the selected
  Work Item's workbook, folder, source, Inbox, copy-file, and tag commands.
- Actions and Work Items can both be assigned to context slots 6–0 through a
  personal Context. There is no global Pin command.

In the **Actions** view:

- Open the filter icon beside Find, then choose **Filter by type** for any
  built-in Action type. Choose **All types** to clear the type filter.
- Choose **Filter by tag…** to search and select one exact reusable tag. Choose **All tags**
  to clear it. Type part of a tag name, use the arrow keys, then press Enter or
  click **Choose**. Find text, type, and tag filters work together. An active type,
  project-code, or tag filter is highlighted and marked **✓** until it is
  cleared. Its tooltip identifies the selected value, and an empty result
  explains the active filter combination.
- Use Up/Down, Page Up/Page Down, Home, and End to navigate.
- Press Enter, double-click, or click **Run**.
- A saved-text action opened through `F9` or `Ctrl+Alt+P` copies its text,
  returns to the captured application, and pastes automatically. When Context
  Palette has no fresh destination, the text remains on the clipboard and the
  status asks you to paste manually with `Ctrl+V`.
- Right-click an action row to open the Actions section in Configure with that
  exact action highlighted. Personal actions can then be edited, including
  short name, description, contexts, tags, type-specific value, and supported
  launch settings. Context changes update the same Context definitions used by
  the Context filter, slots, search, and the Contexts section.
  Built-in actions can also be edited after acknowledging their developer warning.
- Plain number-row and numpad digits remain ordinary Find text.
- Shift plus a physical top-row key from `6` through `0` executes the matching
  context slot only while Find has focus. `Shift+0` executes the fifth context
  slot; Shift+1–5 and numpad digits never execute. This positional rule works
  on AZERTY and QWERTY.
- Selecting an action updates the slim communication line at the bottom.

The selected scope and results make the current view explicit without a
duplicate heading or count row. When nothing matches, the list explains how to
clear Find or create an action instead of presenting a blank pane.

Green rows map top-to-bottom to the active Context's slots 6–0 when Find is empty.
The numeric prefixes are hidden to leave more room for names; hover a shortcut
row to see its exact Shift+number binding. A non-empty Find query suppresses
shortcut promotion and orders all matches by relevance. Action and Work Item
labels use a font-measured icon column followed directly by the short name.
Symbols with different pixel widths stay aligned without a dash or an unused
tree-expansion gutter.

## Work Item-specific discovery and commands

Choose **Work Items** above Find to use the same result area for configured
local work-item folders. The selected **Work Items** scope remains highlighted,
the filter/tools icon gains Work Item commands, and the primary command
becomes **Open**. Choose **All items** or **Actions** to change view. The shared
Context and tag filters remain active across view changes;
**Filter by project** inside that menu applies only to Work Items and does not
select a different slot bank.

- **New Work Item** opens the guided Work Item creation flow. If setup is incomplete,
  Configure opens on the missing source or generic Excel template first.
- **Send Input / Output to Inbox** appends the current Input / Output to the selected Work Item
  workbook's `Inbox` sheet. The result context menu offers the same command.
- **Copy file into Work Item** copies the one exact file path in Input / Output into the
  selected Work Item folder. The result context menu offers the same command.
- Find matches the folder name, parsed kind, organisation, subject, source
  name, detected project codes, and personal tags.
- **Filter by project** filters by one detected four-character project code.
- **Filter by tag…** uses the same exact reusable tag filter as Actions.
- **Filter by context…** uses the same canonical Context membership
  as All items and Actions.
- Enter, double-click, or **Open** opens the exact matching
  `<folder-name>.xlsx`; when it does not exist, the work-item folder opens.
- The **📁** button beside **Open**, or Shift+Enter, always opens the work-item
  folder directly.
- Right-click offers the exact workbook when available, the work-item folder,
  and the configured source folder.
- Right-click a result and choose **Edit tags and contexts…** to open that exact
  Work Item in Configure.
- To reuse a Work Item on the permanent Quick-action surface, open
  **Configure**, choose **Quick actions**, add or edit a My configuration Quick-action
  item, choose the Work Item, and select **Use Work Item**. Its Quick action retains
  the same matching-workbook-first and folder-fallback behavior.
- Unavailable sources keep their last successful in-memory results for the
  current app session. No Work Item index is written to disk.

To set up Work Items, open **Configure**, then choose **Work Items** in the left
navigator. Add one or more folders named `workitems`, giving each a friendly
source name. Choose a source to show only its discovered items. Its complete
folder path and availability remain visible above the full-width table; use
**Refresh** to scan again and the Find field to narrow names, types, projects,
Contexts, or tags. The stable source ID is suggested automatically and keeps
tags attached when the source path differs on another computer. **Manage sources…**
contains Add, Edit, safe source removal, and generic-template setup; **Refresh**
remains visible for the selected source. Removing a source only disconnects it
from discovery on this PC; it never deletes a folder, workbook, or other file.
Saved tags, Context memberships, context slots, and Quick-action references
are retained but unavailable. Adding a source with the same stable ID and the
same Work Item folder names makes that organization available again.

Double-click a discovered Work Item, press Enter, or choose **Edit tags and
contexts** to update its personal tags and assign it directly to existing **My
configuration** Contexts. The editor writes membership to those Context records,
so the Work Item and Context editors show the same truth. Create or rename
Contexts from the Contexts page first; Built-in Contexts cannot reference
personal Work Items.

Choose **Organize → Forget Palette organization…** when the external Work Item
should stay in place but Context Palette should stop remembering how you
organized it. The confirmation inventories what will be removed. The operation
transactionally removes its personal tags, Context memberships and preferred
placement, context slots, and personal Quick-menu references. It never deletes
or edits the source, Work Item folder, workbook, other files, or workbook
Inbox. If a configuration write fails, all attempted files are restored; an
incomplete rollback is reported explicitly.

Source paths and tags remain in ignored local files on this computer. Configure
does not alter the Work Item folders or their Excel files.

For keyboard setup, `Ctrl+F` moves to Find and `F6` switches between the source
selector and discovered Work Items. `F5` refreshes from either control; Enter
edits the selected Work Item. Source dialogs place focus in the Source name
field automatically.

### Create a Work Item from the generic Excel template

Choose **Work Items**, then **New item**. On first use, add at least one source and
select an existing `.xlsx` file as the generic template in the Work Items
Configure page. The creation dialog then lets you select the source and enter a
kind, organisation, subject, and optional project code. The suggested name is
only assistance: **Final Work Item name** remains editable. **Create Work Item**
on the Configure page opens the same creation dialog.

The confirmation shows the exact folder and workbook. Context Palette refuses
Windows-invalid or marker-style names and existing folders. It creates
`<source>\<final name>\<final name>.xlsx` by copying the template without
opening or changing its contents. Optional tags stay local. If copying fails,
only output newly created by that attempt is cleaned up.

### Send Input / Output to a Work Item Inbox

Choose **Work Items**, select a Work Item, place the material in **Input / Output**,
and choose **To inbox**. Existing matching workbooks are updated immediately
without confirmation. Context Palette creates an `Inbox` sheet when necessary
and appends one row:

| Column | Header | Stored value |
| --- | --- | --- |
| A | Added | Current date and time |
| B | Text | Complete Input / Output text |
| C | Link | First HTTP or HTTPS link, as a clickable hyperlink |
| D | Source | Captured window title when known; otherwise Input / Output |

Additional links remain in the complete text, and duplicate links are allowed.
Text is stored literally rather than evaluated as an Excel formula.

When the exact `<work-item-name>.xlsx` is missing, Context Palette offers to
copy the configured generic template into the existing Work Item folder and
then send the row. It never overwrites an existing workbook. If the template is
missing, it offers to open Work Items configuration. Locked, read-only,
unavailable, invalid, or oversized destinations fail with an error and do not
report success. An unexpected background failure also returns the Inbox
operation to an idle state, so it cannot leave the button or Quit permanently
blocked.

### Copy a file into a Work Item

Choose **Work Items**, select a Work Item, put one exact absolute Windows file path in
**Input / Output**, and choose **Copy file**. Paths copied with Windows
Explorer's **Copy as path** command may remain inside matching quotation marks.

Context Palette copies the file into the selected Work Item folder under its
existing filename. Copying runs in the background. The final filename appears
only after the content copy completes, so an interrupted copy does not expose a
partial file under that name.

For safety:

- Input / Output must contain only one file path, not prose or several paths.
- Folder paths are rejected.
- An existing destination file is never replaced or renamed automatically.
- A source file already inside the Work Item is rejected.
- Missing, unavailable, or failed copies produce an actionable error.

### Send files to a folder

Put one or more exact absolute file paths in **Input / Output**, one per
nonblank line, then choose the clearly labelled **Send to…** menu above the
editor or in its right-click menu. Matching outer quotes from Explorer's
**Copy as path** are accepted. The first slice accepts files only, with a
maximum of 100; folders, relative paths, URLs, prose, missing files, and a
duplicate source path are explained before anything is copied.

The destination menu can contain:

- the currently selected Work Item;
- Active **Open a folder** Actions that belong to the current Context filter;
- the last ten successful destination folders from this app session;
- a hierarchical **All Folder Actions** menu;
- **Find destination…**, which searches Folder Actions and discovered Work
  Items;
- **Choose another folder…** for a one-off copy; and
- **Manage Folder Actions…** for editing the reusable destinations.

A Folder Action is reused only as a destination record inside **Send to…**.
Running that same **Open a folder** Action from Find or a Quick menu still opens
its folder; it does not copy anything. Recent destinations are never written
to configuration or backups, and source paths are never added to that state.

For a reusable copy command, create an Action of type **Send files to folder**
and set its destination folder. Use an existing folder, optionally through a
portable/date placeholder. It uses the exact file paths in Input / Output;
it never substitutes the clipboard for missing input. Run it from the normal
Action list or place it in any configured Quick menu. This is distinct from
**Open a folder**, which opens Explorer rather than copying files.

To copy on drop, choose that saved Action under **Drop window → Settings… →
On drop → Run an Action…**. Saving explicitly permits copying each new drop
to the named destination. Conflict-free copies start automatically; name
conflicts use the existing review with overwrite off by default. Source files,
clipboard and Input / Output remain unchanged. Only files are copied, not
folder trees. Preview describes the input/destination/effect without inspecting
or copying files. A later drop cannot replace an open copy review; changing
the saved destination requires choosing and approving the Action again.
Only **Open a folder** Actions whose destination can be resolved without clipboard text
are offered here. An Action containing `%CLIPBOARD%`, `%CLIPBOARD_URL%`,
`%pptxt%`, or `%cpy_txt_urlencode%` remains available through its ordinary Run
route but is excluded from copy destinations. This prevents a missing clipboard
value from silently changing a destination to its parent folder. Relative
folder values and `file:` URIs use the same resolution as ordinary Folder
Actions.

Choosing a destination is the confirmation when every destination filename is
new, so copying starts without another dialog. If a name already exists, a
centered review shows every source-to-destination mapping. With **Allow
overwrite** off (the default), `report.txt` becomes `report(1).txt`, then
`report(2).txt`. Turning overwrite on replans the exact unsuffixed replacements
and changes the one effect-labelled button, for example to **Replace 1 and copy
2 files**. There is no additional Yes/No question. A replaced destination does
not receive a recovery backup, so leave overwrite off unless replacing that
exact file is intentional.

Planning and copying happen in the background. Context Palette stages complete
temporary files in the destination, rechecks the reviewed sources and
destinations, and only then publishes them. **Stop remaining** finishes the
current file and prevents later files from starting. The result lists exact
created, replaced, skipped, and failed destinations. Earlier completed copies
remain after a later failure or stop; no batch rollback or automatic retry is
claimed. Source files, Input / Output, and the clipboard remain unchanged.
If every source is already the exact file in the selected destination, the
window says **Nothing to copy** and offers neither overwrite nor a copy button.

#### Open one path's folder in VS Code

When Input / Output has exactly one nonblank line, the **Send to…** menu also
shows **Open with → Open folder in VS Code**. Use it with one existing absolute
folder or file path. Matching outer quotation marks from Explorer are accepted.
A folder opens as that VS Code workspace; a file opens its containing folder,
not only the individual file.

This is an open operation, not a copy destination. It does not copy or move the
path, change Input / Output or the clipboard, add a recent destination, or run
an **Open a folder** Action. Windows opens the percent-encoded folder through
the registered `vscode:` protocol, so VS Code must already be installed and
registered for those links. Context Palette does not search for or invoke a VS
Code executable and does not request administrator rights. Empty, relative,
missing, unavailable, unmatched-quote, and multiple paths are explained
without opening anything.

## Save the current Ultimate Guitar score from Edge

This saved Action uses the score already open in Microsoft Edge, including your
signed-in session and current score selection. **Accepted workflow: finish
Save As yourself.** The owner has chosen to keep the current stopping point
so the filename can be reviewed or changed before saving.

1. Create or edit a **Save current score as PDF** Action and choose its absolute
   **PDF folder**. The Action stores no arguments, working folder, or placeholders.
   Put it in a personal Music Quick-action menu if desired.
2. Open an **Official** score or **Guitar Pro** tab on Ultimate Guitar in Edge.
   Choose the instrument and view you want. Close any existing print or Save As
   dialog, then press **F9**.
3. Run the saved Action from the Music menu or, when Music is selected and Find
   is focused, press physical **Shift+6** for Music slot 6.
4. Keep Edge in front while the operation runs. At the accepted **Save As**
   handoff, the Context Palette progress window closes automatically. There is
   no extra message to dismiss; finish in Edge's Save As window.
5. In Edge, choose the **folder and filename**, then click **Save**. The dialog
   may still show Downloads; do not assume the Action's configured folder has
   been selected. Open the saved PDF and check its score and page count.

This handoff means the final save is up to you; it does not mean a PDF has
already been saved. Palette does not verify a PDF saved manually afterward.
To keep an existing file, choose a different filename in Edge;
Palette's automatic duplicate numbering does not apply to this stopped path.

To set up the shortcut on another PC, create a Music Context in Configure and
assign the saved Action to its slot 6. Music is personal configuration; a fresh
clone does not include this menu or shortcut assignment.

The function uses the website's **PRINT** button and Edge's **Save as PDF**
printer. Select that printer in Edge once if the function asks you to; other
printers are never used. It supports only the stated Official score and Guitar
Pro tab page shapes; ordinary text tabs, chords, and arbitrary webpages are not
score-PDF inputs. The first version supports the observed English Edge/Windows
controls. A changed website, title/type mismatch, foreground window, or
unrecognized dialog stops the save with an explanation. It does not sign you in
or change instruments for you.

If the Action stops before opening Save As, the message identifies the missing
or ambiguous control. You can use the website's PRINT button and Edge's Save
as PDF manually instead.
For a hidden PRINT button, make it visible in Edge; for a disabled button, let
the score finish loading. Close any leftover print or Save As dialog before
running the Action again. When finishing manually, check the file in the
folder you chose; Palette will not report or verify that manual save.

The configured PDF folder remains required by the existing automation,
but the observed stop leaves the final folder choice to Edge. The Action,
Music menu and Music slot are personal configuration, excluded from Git. On
another PC, configure an available folder there.

The code still attempts automatic saving. Only the known filename-control
lookup failure in the verified Save As dialog closes quietly; other failures
still show an explanation. Manual completion is the accepted observed stopping
point, not an enforced pause on every PC. Full automatic
saving is not required by the current owner decision. Menu, shortcut and
second-PC checks remain unverified where not reported.

Cancel stops the automation; a print or Save As dialog may need closing in Edge.
Quit is blocked until the worker finishes. This Action does not use or change
Input / Output or the clipboard; F9 retains its usual selection-capture behavior.
It is manual only: Drop, AI proposals, and Action sequences cannot run it. The
old ignored local score-folder preference is retained as legacy data. The saved
Action supplies the automation's configured folder; choose the final manual
save location in Edge.

## Save a webpage as PDF

1. Paste one complete `https://` or `http://` webpage address into **Input / Output**.
2. Choose **Send to… → Save webpage as PDF…**.
3. Choose a folder and a **new PDF filename**. Existing files are never replaced.
4. Wait for **PDF saved**, then choose **Open PDF** to check the content.

This uses installed Microsoft Edge, or Google Chrome if Edge is unavailable,
in a temporary browser session. No extra Python package is required. It works
best for pages that open without signing in; it does not use your signed-in
browser tabs or cookies. For a signed-in page, use your normal browser's print
dialog and choose **Save as PDF** instead.

The complete Input / Output field supplies the URL, even when text is selected.
Your text and clipboard stay unchanged. Only one PDF job runs at a time. You
can keep using the palette while it runs; **Cancel** requests a stop and waits
for browser cleanup. Quit is blocked until the job finishes. If saving finished
just before cancellation, the result still reports the saved file.

The PDF uses the website's print layout. Cookie notices, sign-in screens,
browser error pages or content that loads late may appear or be missing. A
saved PDF is not proof that all expected website content was captured. Open it
to check the result; use normal browser printing when it needs adjustment.

This is an Input / Output function, not a saved Action or an automatic Drop Action.

## Quick-action surface

Quick actions appear below discovery on the left side of the main palette and
stay visible when the Context filter changes. Every visible control is one menu
launcher; no launcher silently runs a default Action.

- Left-click a menu, or focus it and press Enter or Space, to browse its
  ordered Actions and submenus.
- Right-click that same launcher for related management commands such as Add,
  Organize, and Find matching Actions.
- Inside an open menu, left-click an Action to run exactly that Action.
  Right-click an Action to open that exact record for editing without running
  it. Right-click a submenu to add or organize within that branch.
- Action targets use the same selected text, Input / Output, clipboard, and safe
  executor as the search list. Work Item targets use the same constrained
  workbook-first opener as the Work Items scope.
- Configure shared groups in `data/command_surface.json` and private groups in `data/local_command_surface.json`.
- Press `Ctrl+,`, then use **Quick actions** to add or edit personal menus,
  Quick actions, and submenus without editing JSON. Add Actions and Work Items from their
  searchable lists, then reorder them together; stable IDs are generated from the visible names
  when left blank.
- A configured menu root or branch may explicitly reference an Active Action,
  independently of the automatic menus below. The same Action can therefore
  appear in no configured menu, one configured menu, or several configured
  menus without changing its type or automatic location.
- When creating or editing a Folder, Password, or AI-prompt Action, choose
  **Menu locations → Choose…**. The first section selects its required
  automatic Folders, Passwords, or Prompts location; the second section selects
  zero or more additional configured menu roots or branches. Both are staged
  until **Create action** or **Save action**, which saves the Action and those
  references together. For a saved Active Action, select it under **Actions**
  and choose **Other menus…** as a faster configured-placement-only route. Search the configured
  roots and branches, select the wanted references, and review the exact
  additions, removals, and newly empty items before applying. Built-in
  locations can reference only Built-in Actions; My configuration locations
  may reference either. A stale review or uncertain rollback stops further
  changes and requires a fresh review. Applying placements never executes or
  deletes the Action.
- **Standard** is the single fixed Built-in group. Its one **Standard** launcher
  distributes Active Built-in Actions across root commands and nested subject
  levels. It is always first and cannot be moved or deleted; its contents can
  still be edited through the normal supported commands.
- **Passwords**, **Folders**, and **Prompts** are permanent action-bound nested
  menus. They automatically include every Active `paste_credential`,
  `open_folder`, or `ai_prompt` action respectively, including actions created
  after the launcher opens and reloads.
- In the Action form, **Menu locations** shows the exact automatic breadcrumb
  and a summary of additional configured locations. Choose **Choose…** to
  select **Menu root** or an existing branch from the real menu tree, search
  locations, or create a new submenu below the selected location. Nesting is
  limited to three levels; no `>` path needs to be remembered or typed.
  Deleting the Action removes it
  from its generated menu without maintaining a second assignment.
- Launcher order is **Standard**, personal configured menus, shared configured
  menus, then the automatic **Passwords**, **Folders**, and **Prompts** menus.
  Order within each configured storage file remains stable. The grid adapts to
  one or two columns without changing that sequence.
- The menu and every submenu accept any number of ordered Actions. Nesting
  is bounded at menu → level 1 → level 2 → level 3 → Action. Actions may stop
  at any earlier point, including directly under the menu. Native menus do not
  provide search or app-managed scrolling.

## Configure

Choose **Configure**, or use the shortcut (`Ctrl+,`), for the complete guided
configuration workspace. The left navigator replaces the crowded row of tabs
and keeps every section in one stable place. Frequent destinations are grouped
under **Set up** and backup or troubleshooting destinations under **Support**:

- **Start:** ordinary Configure opens with task choices instead of assuming
  which configuration category you need. Choose **Create an Action...**,
  **Find or edit Actions**, **Organize Contexts**, **Arrange Quick actions**,
  **Set up Work Items**, or **Back up or restore**. **Browse Action types** and
  **View diagnostics** remain available as secondary choices. Each choice
  opens the existing editor; it does not create a second configuration window.
- **Actions:** choose **New Action…** for the normal creation flow. **More Action
  tasks** contains bulk Excel creation/template and update commands,
  website-link Harvest, and the educational Action-type catalogue. Find,
  direct deletion, and selection commands surround one
  Actions table; Contexts and tags for the selection appear below it. Use
  **Delete Action…** to review and permanently remove the selected record plus
  its saved Context, shortcut, and configured-menu references. The confirmation
  names the exact stable ID and states that the external target remains
  unchanged. Old `Archived` records appear as **Legacy inactive** and offer
  deletion only; there is no Archive or Restore command.
  New actions default to **My configuration**; choose **Built-in** only when
  deliberately changing shipped starter data.
- **Create Action / New Action:** use the visible launcher button, Configure's
  **New Action…**, or press
  `Ctrl+N`, to search and choose a type before completing the usual Action
  form. The chooser supports typing, arrow keys, Enter, and Escape; it does
  not save anything until the Action form is confirmed. A specific active
  Context filter is prefilled as a Context. Use **Browse action types…** for
  the full educational catalogue.
- **Action types:** inspect what each available action reads and does, see a
  concrete example, then create a validated permanent action. Older
  Input / Output transformation types remain editable for compatibility but
  are not offered for new actions; use the Transform menu for immediate text
  changes or **Transform a text file** for a repeated file workflow.
- **Contexts:** choose **New Context…**, use Find to search the full table, then
  use the selected-Context card to **Edit…** or **Delete permanently…**. A
  Context organizes visible membership and owns one optional shortcut bank for
  6–0. The editor lists members first, followed by those slots. My
  configuration Contexts can contain built-in Actions, personal Actions, and
  Work Items; Built-in Contexts remain Action-only.
- **Quick actions:** choose **New saved menu…** to create a configured shortcut menu.
  Select a custom menu and use **New Quick action**; select a custom item and
  use **New submenu** where the bounded hierarchy permits it. Edit, Move, and
  Delete apply only to configured structure. Each menu has one launcher;
  assigned Actions and Work Items appear in their explicit menu order.
  The automatic **Passwords**, **Folders**, and **Prompts** menus also appear in
  the same tree, marked as generated from Actions. Select an automatic menu or
  branch to add a correctly typed Action with the ordinary full form, including
  Contexts, tags, target, and a preselected menu location. Choose **Manage
  menu…** or **Manage this submenu…** to search matching stored Actions and use
  the explicit **Submenu tasks** menu. **New submenu** requires at least one
  selected Active Action because an empty automatic submenu is not stored.
  **Rename** changes only the selected submenu name, **Move** chooses a new
  parent while retaining its name, and **Remove submenu** promotes its direct
  Actions and child submenus to the parent. Every operation shows the exact
  before → after paths and Built-in/personal impact before one effect-labelled
  Apply button. Legacy inactive records are deletion-only and are not placement
  candidates. Select an
  automatic Action leaf inside a submenu and choose **Remove from submenu…**
  to promote that exact Action one level, or select several direct members in
  the manager and choose **Remove selected from this submenu**. The review
  shows stable Action IDs so duplicate titles are not ambiguous. The Action
  remains Active and its external target is unchanged. At the automatic root,
  no Remove command appears: move the Action into a submenu, or delete the
  owning Action to remove that required automatic leaf.
  Automatic branches are not separate records: moving the last Action out
  makes an empty branch disappear. Removing a submenu never deletes an Action,
  folder, password, prompt, Work Item, or other external target. Actions at a
  menu root appear before child submenus. The
  selection card shows the complete path and only the commands valid for that
  selection.
  The single fixed Built-in **Standard** group offers only Built-in actions,
  cannot be moved or deleted, and keeps starter commands usable
  without one PC's private files. My configuration groups may use both
  built-in and personal actions, or personal Work Items. A temporarily
  unavailable Work Item remains assigned and reports how to refresh or repair
  its source.
  Quick-action groups are currently global; Context-based visibility or
  grouping is not applied.
- **Diagnostics:** review a safe summary of loaded configuration, recent error
  counts, and automatic-paste outcomes in a scrollable read-only report. Use
  **Refresh** after reproducing a problem or **Copy safe summary** when asking
  for help. Raw log messages,
  pasted text, credentials, action values, paths, and window titles are not
  included.
- **Backup and restore:** create a complete-configuration ZIP or inspect one
  before restoring it. Backups include Inbox by default; clear that option to
  omit captured content. Optional managed text remains excluded unless you
  select it. Configured Action targets, Work Item source paths, template paths,
  working directories, and arguments remain in the backed-up configuration.
  The referenced files, folders, Work Item roots and workbooks, and templates
  themselves are never copied. Credential secrets, logs, caches, environments,
  and unknown files are also excluded.

  **Create backup…** asks where to save the ZIP and asks again before
  replacing an existing file. Its result lists the archive location, included
  file count, warnings, and excluded categories. Treat a backup as sensitive:
  it can contain personal configuration, captured Inbox content, and configured
  machine paths even though external files and credential secrets are absent.

  **Choose backup to inspect…** first inspects the archive without changing live
  configuration. Review files to replace or create, omitted live files that
  stay preserved, Built-in impact, sensitive categories, compatibility and
  legacy status, and privacy-safe portability warnings. **Apply inspected
  changes…** then asks for confirmation and separately confirms any Built-in
  replacement. A successful restore reports the retained recovery archive,
  closes Configure, and reloads the launcher. If rollback completes after a
  failed restore, the previous configuration remains usable. If recovery is
  incomplete, Context Palette blocks further configuration changes and asks
  you to restart so startup recovery can finish.

  While backup, inspection, or commit is active, wait for its progress window;
  Configure cannot be edited or closed, Context Palette will refuse to quit,
  and duplicate operations are ignored. Cancelling a file dialog or declining
  confirmation changes nothing. Restore commit has no Cancel button after final
  confirmation.

  `Alt+A`, `Alt+T`, `Alt+C`, `Alt+Q`, `Alt+W`, `Alt+D`, and `Alt+B` directly
  select Actions, Action types, Contexts, Quick actions, Work Items,
  Diagnostics, and Backup and restore.
  `Ctrl+Tab` cycles through all Configure sections. Both paths move focus into
  the selected section's main content.

Only one Configure workspace opens at a time. Choosing Configure again,
right-clicking an Action, or opening Work Item configuration raises that same
window and moves it to the requested section or record. Close it
when finished; the next request creates a fresh Configure window.

Ordinary Configure opens on Start with focus on **Create an Action...**. Direct
routes such as Edit, Work Item setup, and Diagnostics open and focus their
requested editor instead. Action, context, and button dialogs focus
and select their first editable field, so typing can begin immediately. Action
create/edit forms keep **Create/Save action** and **Cancel**
visible at the bottom. Their compact rows place labels beside fields; hover over
or move keyboard focus to a field for its explanation, or use the action
type's **?** button for complete input, effect, and example guidance. Scroll the
form body with its vertical scrollbar or the mouse wheel; moving through fields
with Tab automatically reveals the focused field.

All fields that choose an existing Action use the same **Find…** picker:
Context membership, preferred slots 6–0, and Quick-action assignments. Search
by any combination of Action name, description, built-in
type, context, tag, state, stable ID, target or saved value, arguments, or
working folder. The result count and filtered list update while you type. Press
Down Arrow to enter the results, then Enter to select; pressing Enter directly
from Find selects the highlighted result. Double-click works with the mouse.
Choose **Not assigned** to clear a preferred slot.

Built-in contexts and the Built-in **Standard** Quick-action group deliberately
list Built-in actions only, because tracked starter configuration cannot depend
on one computer's private action file. Their picker states this scope and
explains an empty result. To assign a My configuration action, create or edit a
My configuration context or Quick-action group instead.

Use **Choose…** in guided action forms to select one or more defined specific
contexts. The adjacent field remains editable for quick keyboard entry and
shows the selected names as a comma-separated list. Names match without regard
to capitalization and are saved using the context's current spelling. If a
typed name is unknown, the form stays open and identifies it; create the
context first, correct the spelling, or leave the field empty for General only.

The Tags field has the same **Choose…** control for tags already used by other
actions. Tags remain open-ended: select existing ones for consistency, type new
ones when needed, or combine both approaches.

For existing tags, **Choose** opens a searchable list. Select several existing
tags, keep the selection while narrowing the list, then choose **Add selected**.
You can still type any new comma-separated tags directly in the field.

Keyboard shortcuts in these guided forms:

- `Alt+C` moves directly to Specific contexts.
- `Alt+T` moves directly to Tags.
- `Alt+Down` or `F4` opens the context checklist or searchable tag picker from
  its field or **Choose…** button.
- Use the normal arrow keys and Space to select tags, then choose **Add
  selected**. Press `Esc` to close without applying changes.

Use the visible **Find** field in **Actions**, **Contexts**, **Quick actions**,
or **Work Items**
to reduce that table. `Ctrl+F` focuses and selects the Find field for the
current one of those sections. On another Configure section, it opens Actions
and focuses **Find**. Multiple words must all match.

The Actions, Contexts, Quick actions, and discovered Work Items tables resize
within the Configure window instead of hiding their final
columns. Each table has a visible vertical scrollbar for records that extend
beyond the available height.

- Actions search short name, description, stable ID, built-in type, context,
  tag, state, target or saved value, arguments, working folder, and storage.
- Contexts search name, description, member and preferred action names, and
  storage.
- Quick actions search menu name, submenu, assigned Action name, Action
  metadata, and storage. **Menu root** finds automatic entries whose **Quick
  menu** field is empty.

Press Enter on a selected result to edit it.

Creating or editing an Action immediately refreshes the Actions table, Context
summaries, Quick-action summaries, and diagnostics. Actions
created from Inbox, Harvest, or Cheat Sheets also refresh an already-open
Configure workspace.

For a Folder, Password, or AI-prompt Action, the normal create/edit form's
**Menu locations** chooser manages its automatic location and optional
configured references together. For any saved Active Action,
**Other menus…** remains a configured-reference-only shortcut. Uncheck one or
all saved locations there to remove only those optional references; the Action
and its required automatic location remain. No conversion or
migration occurs between the two stored menu models.

The Actions table shows ordinary Active records and any old records marked
**Legacy inactive**. Select an Action and choose **Delete Action…** to review
permanent deletion. The review reports saved Context memberships, slots,
configured Quick-action references, newly empty Quick-action items, and the
automatic menu location that will disappear. It identifies duplicate titles by
stable ID and explicitly states that the external file, folder, website,
application, credential target, or other resource will not be deleted or
changed. A Built-in Action adds a Git and multi-computer warning.

Deletion rechecks that exact impact before writing. A stale review makes no
change and asks for a fresh review. A write failure restores every attempted
configuration and `.bak` file when possible; an incomplete rollback is
reported explicitly. Legacy inactive records cannot run, be edited, or be
restored; deletion is their only available mutation.

The Actions, Contexts, and Quick actions tables select their first useful row
automatically. Use the arrow keys to move, then press Enter to edit the selected
item. Double-click provides the same action with a mouse. In Quick actions,
select a group before adding an item, and use the arrow buttons to reorder the
selected group or item.

Changes are saved atomically. Personal changes use ignored local files. Shared
configuration changes use Git-tracked project files and can therefore reach
your other development computers after commit, push, and pull. Application
usage remains local to the computer where Context Palette is running. Never
store personal paths, secrets, or private work details in shared configuration.
Confirmed creation and editing are permanent; Context Palette keeps the
previous file as an atomic `.bak` backup.

Context slots and button assignments show human-readable action names and contexts. Internal IDs remain stored for stable references but are not part of the normal editing workflow. Successful saves appear in the Configure footer without interrupting work with a confirmation dialog.

If validation or file saving fails, the edit dialog stays open so the entered
values can be corrected without starting over. A file-write error explains
common recovery steps; the existing configuration file and loaded view remain
unchanged.

The complete JSON format is documented in `docs/COMMAND_SURFACE_CONFIGURATION.md`.

## Remove, disconnect, or forget

These commands deliberately affect different kinds of data:

| Entity | Command and result | What remains untouched |
| --- | --- | --- |
| Action | **Delete Action…** reviews and permanently removes the Action plus its saved Context, slot, and configured-menu references. Active and legacy inactive records use the same transactional deletion boundary. | The Action's external file, folder, website, application, or other target. |
| Context | Open **Configure**, choose **Contexts**, then use **Delete permanently…**. This removes that Context, its memberships, and its context-slot configuration. | Member Actions and Work Item folders/files. |
| Quick menu | A configured custom menu or item can use **Delete**. **Standard** is fixed and cannot be moved or deleted; automatic Passwords/Folders/Prompts structure is changed through its owning Actions. | Assigned Actions, Work Items, and external targets. |
| Work Item organization | Open **Configure**, choose **Work Items**, then choose **Organize** and **Forget Palette organization…**. This transactionally removes personal tags, Context membership and preferred placement, context slots, and personal Quick-menu references for that Work Item. | The source, folder, workbook, files, and workbook Inbox. |
| Work Item source | **Manage sources → Remove** disconnects discovery on this PC and retains saved organization for reconnection by the same source ID and folder names. | Every external folder/file and all saved Palette organization. |
| Capture Inbox item | **Inbox → Delete capture…** removes only the selected local capture. | Any Action already created from it. Work Item workbook Inbox rows remain Excel-managed. |

All permanent Palette deletion commands confirm the exact selected entity. A
shared Built-in change also explains its Git and multi-computer impact.

## Input / Output workspace

Input / Output is the text-transformation workspace integrated with the action
launcher, not merely a passive scratchpad or action preview. Use it for quick
manual inspection and editing, and for repeatedly applying constrained actions
to selected text or the complete field. The normal workflow is: capture or
enter text, find and apply an action, inspect or refine the result, then copy
or reuse it.

The main window opens at a compact screen-aware size. Input / Output receives
the full right side and nearly all of its usable height. Drag the vertical
divider to adjust the command-console/workspace balance; the chosen ratio
follows later resizing for the current session. On smaller screens the same
areas shrink and retain their scrolling. Divider movement is bounded so
neither side can be accidentally collapsed. A fresh
application start leaves the workspace empty. Reopening the resident palette
can show the current clipboard or captured selection. Actions can read or
  replace it. Its compact heading includes Back and Forward, the literal
  **Send to…** destination menu, and bitmap controls for Capture, Inbox,
  **Create from Input**, **Extract text**, and **Text tools**.

Use the single **Input / Output** checkbox beside the application controls to
hide or show this panel. It is shown by default each session. Hiding preserves
its text, selection, Back/Forward history, and native Undo/Redo; the communication
line stays visible on the left. A **•** on the collapsed control means it
contains input. Normal clipboard/selection capture still works while hidden.
A show-only drop reveals both the Palette and Input / Output; a configured
Action runs directly and reveals text output only when it produces a result. Contexts and
tags keep their separate controls and meanings; this is not a new layout or
organization model.

Numbered Action triggering is deliberately active only for Shift+6–0 while
Find has focus. Shift+1–5 is retired, and in every other control—including
Input / Output, the result list, filter controls, and buttons—number keys do
not execute Actions. Standard text editing remains available in the workspace.

The bottom communication line always stays one row high. Hover over it for the complete selected-action explanation; click it to open the full message in a selectable information window.

- A text selection captured with `Ctrl+Alt+P` appears here.
- `Ctrl+V` pastes at the cursor; the right-click command `Replace with clipboard` replaces everything.
- Drop files, folders, shortcuts, links, or text onto the separate drop target.
  In default show-only mode, empty Input / Output is replaced directly; existing content gets explicit
  **Replace**, **Append**, and **Cancel** choices. Default show-only dropping
  does not read, replace, or copy the clipboard. An explicitly configured Drop
  Action can have its normal clipboard effects, as described in Drop settings.
- Type or edit text directly.
- Use the Back and Forward arrows to navigate the last ten meaningful complete
  Input / Output states from this session. Consecutive typing is kept as one
  state rather than one entry per character. Going back and then changing the
  content discards the old forward branch. This history preserves whitespace,
  is not persisted, and is separate from native Undo/Redo.
- The right-click command `Clear` empties it.
- The right-click menu also provides Undo, Redo, Cut, Copy, Paste, Select all, and Copy all.
- Choose **Send to…** in the header or right-click menu to copy exact file
  paths to a reviewed folder destination without changing the workspace, or
  use its separate **Open with → Open folder in VS Code** command for one
  existing folder/file path without copying it.
- Open `Transform` through the right-click menu or choose **Text tools**.
- Choose the **Create from Input** icon to turn one clear target into a reusable Action.
  A non-blank selection is used first; otherwise Context Palette checks the
  complete Input / Output field. One complete HTTP/HTTPS address, clear
  absolute file path, folder path, or `.exe` path opens the ordinary Action form
  with its type, editable name, and exact target prefilled. Quoted Explorer
  paths are accepted. A long path that only wraps visually remains one target.
- **Create from Input** never rereads the clipboard, saves, opens, runs, or waits
  for a drive lookup. Review the prefilled name, target, effect, Contexts,
  tags, and storage, then choose **Create action** normally. Multiple targets, prose around a
  target, unsupported addresses, line-broken content, relative paths, and
  script-like targets are explained instead of guessed. An unavailable absolute
  path can still be reviewed for portable or temporarily disconnected use. Use
  the **Create Action** command to choose a type yourself.
- Choose **Extract text** to read one local image into Input / Output. Context
  Palette first checks selected or complete Input / Output for one exact image
  path, otherwise reads a clipboard bitmap, and finally offers an image file
  picker. PNG, JPEG, BMP, GIF, TIFF, and WebP are supported. Recognition runs
  locally in the background and does not upload the image.
- OCR never replaces the clipboard image. If Input / Output is empty, the
  extracted text is inserted directly. If it already contains text, choose
  the explicitly labelled **Replace**, **Append**, or **Cancel** button. If the
  workspace changed during recognition, the
  choice explicitly warns about that change. The insertion is one Undo step.
  No readable text, an unsupported or oversized image, or an OCR failure leaves
  Input / Output unchanged.
- To export Excel workbooks, put one exact absolute `.xlsx` path on each line
  in Input / Output, or drop the workbook paths into Context Palette, then run
  **Export Excel files to CSV**. Context Palette accepts at most 100 closed
  workbooks per batch. It asks for any required worksheet choices and initially
  uses the first workbook's folder for CSV output. Choose **Choose another
  output folder…** in the blocked or reviewed flow to override it. Planning
  runs in the background and shows the exact source-to-CSV effects before
  execution. **Allow overwrite** is off by default. In that mode Python Excel
  keeps existing files and chooses the first free name: `report.csv`,
  `report(1).csv`, `report(2).csv`, and so on. Turn **Allow overwrite** on to
  target the exact unsuffixed name; the review then says whether each CSV will
  be created or replaced. It also shows the create/replace totals and provides
  one matching button, such as **Replace 1 and create 2 CSV files**. There is no
  second generic Yes/No dialog. The export uses all used columns and never
  changes a source workbook. Changing the checkbox or output folder produces a
  new plan. A stale plan must be planned and reviewed again.
- A completed export lists created and replaced files separately and lets you
  open the output folder. A pre-effect failure creates or replaces nothing. A
  partial result lists only confirmed effects; an interrupted/lost engine is an
  unknown outcome. Do not retry either automatically: inspect the output first.
  Replacement publication is atomic per file, but there is no recovery backup
  or batch rollback. This integration also has no progress display,
  cancellation, live Excel support, or Action-sequence support.
- To format an already-open workbook, run **Apply Excel format template** from
  the Standard menu or its normal Action location. This does not read Input /
  Output. The shared live-Excel chooser lists workbooks currently open in
  Excel, prefers the workbook and active visible worksheet captured through F9
  when possible, and provides **Refresh** beside the workbook. Select one visible
  worksheet or **All visible worksheets** and choose **Apply**. The
  fixed Standard data template applies Aptos 11 to the used range, treats row
  1 as a header, freezes its top row, and adds a filter only where none exists.
  Turn AutoSave off first. Apply is the confirmation, and Context Palette never
  saves or closes the workbook. Direct formatting may clear Excel Undo and has
  no backup, rollback, progress, cancellation, or automatic retry. If Excel
  changes before Apply, Refresh and select it again. For partial or unknown
  results, inspect the workbook before retrying. **Return to Excel** only tries
  to return focus to the window captured when you opened the Action.
- To review a column-to-text conversion, run **UAT: Convert
  scientific-notation columns**. It does not read Input / Output. It begins
  with the same live-Excel workbook, worksheet, captured-F9 preference, and
  Refresh controls as the format-template Action. Choose one visible worksheet,
  then exact physical columns;
  blank and duplicate headers remain separate because columns are identified
  by index and letter. Context Palette pages the bounded read-only preflight,
  shows eligible, already-text, blank, formula, unsupported, and precision-risk
  counts plus bounded samples, then asks Python Excel for an exact zero-write
  plan. A selected-scope formula blocks execution.
- Python Excel chooses the default sibling recovery path. Choosing another
  future sibling `.xlsx` path creates a fresh plan; Context Palette never
  creates or overwrites the recovery workbook. If Excel may already have lost
  digits beyond its numeric precision, explicitly acknowledge that conversion
  can preserve only the value Excel currently exposes. The engine creates and
  verifies the reviewed recovery copy before mutation. It converts selected
  eligible values to text, never saves or closes Excel, and reports the exact
  completed columns and counts.
- This Action is a Development/UAT feature. Set
  `CONTEXT_PALETTE_UAT_LIVE_TEXT_CONVERSION=1` before starting Context Palette
  and restart it to enable **Execute**; any other or missing value leaves
  discovery, inventory, preflight, and planning available but mutation
  disabled. From PowerShell, use
  `$env:CONTEXT_PALETTE_UAT_LIVE_TEXT_CONVERSION='1'; .\run-context-palette.bat`
  for that one app process. Close it and start normally to return to read-only
  review. A clean failure means no live-workbook mutation began, although a
  verified recovery copy may exist. A partial failure or lost/unparseable
  engine result may mean partial or unknown effects: inspect Excel and the
  reviewed recovery location, and never retry automatically.
- A transform changes the selection, or the complete field when nothing is selected.
- Every transform result is copied to the clipboard automatically and can be reverted with one Undo.
- Transform groups provide case and naming styles, whitespace cleanup, literal
  replacement, line filtering, custom split/join delimiters, sorting,
  duplicate removal, explicit comma-list formats, JSON formatting, URL
  encoding, SQL escaping and value lists, Windows path/file-URI conversion,
  and path-slash conversion.
- The **Lists** group accepts values separated by lines, commas, tabs, or
  semicolons. Separators inside matching single or double quotes remain part of
  the value. Choose **Comma list: no quotes**, **single-quoted text**, or
  **double-quoted text**. In the quoted modes, signed numbers, decimals,
  scientific notation, and `NULL` remain unquoted; text uses the selected quote
  and doubles that character when it occurs inside the value.
- **Parenthesized SQL value list** uses the same parsing and number detection,
  single-quotes text, escapes apostrophes, preserves `NULL`, and adds
  parentheses.
- Transform actions read it and place their result back in it.
- URL-builder actions use it as selected input when it is not empty.

Example: in the Database context, `Convert lines to SQL string list` turns separate lines into quoted, comma-separated SQL values and copies the result.

For Input / Output containing `alpha`, `42`, and `O'Brien` on separate lines,
the three comma-list choices produce:

- `alpha, 42, O'Brien`
- `'alpha', 42, 'O''Brien'`
- `"alpha", 42, "O'Brien"`

## Task-oriented controls

Controls stay beside the thing they affect. The three item views remain
readable above Find. The bitmap-icon Filter control sits beside Find and owns
Context, tag, Action type, and Work Item project constraints; its Context value
also chooses slots 6–0. Below results, the stable item toolbar
contains the document-plus **Create Action** button, Edit, and Run/Open;
invalid selection commands are disabled
instead of failing after a click. Work Item-specific New, Inbox, Copy file, and
project commands live in the filter/tools menu.

The Input / Output header contains Back, Forward, Capture, Inbox, Create from
Input, Extract text, and Text tools. Configure, Help, and More sit below Quick
actions. These icon-only controls use portable Tk bitmaps rather than font
characters. Hover over or keyboard-focus any icon to see its complete name and
explanation. The document-plus **Create Action** chooser and the wand-shaped
**Create from Input** route remain separate. Creation has a neutral button so
Run/Open remains the main visual command.

Result-list symbols identify Action types: a document for a file, a pane-shaped
window for Windows targets, ordered lines for a Sequence, and a transfer arrow
for Send files. Website actions retain an opening arrow; `?↗` means the URL
asks for a value, while `T↗` uses supplied text. `T` identifies a text
transformation. The full type and effect remain available in the item tooltip
and Preview. Icons do not change what an Action does.

### Run

Executes the highlighted Action or opens the selected Work Item. Before Run or
Open, the bottom communication line uses one stable form:

```text
Input: what will be read → Effect: what will happen
```

It reflects useful current state, such as an empty Input / Output field, a
captured destination, clipboard fallback, a matching Work Item workbook, or
folder fallback. Safety-critical consequences remain visible: Windows targets
say they may execute code, AI prompts say nothing is submitted, protected
credentials describe confirmation and cleanup, and text-file transforms say
the source remains unchanged until explicit replacement.

Progress, success, and errors temporarily replace the preview. Select an item
again—or change Input / Output—to restore its current Input → Effect summary.
Hover over the line for the complete explanation, or click it to open
structured Type, Input, Effect, configured-value, and recovery details. The
compact line never includes captured input content, passwords, or technical
action-type IDs.

#### Optional Preview

Select an Action or Work Item and choose **Preview** beside Run/Open. It shows
the actual input source and snapshot, resolved target where available, expected
effect, and recovery limitations. Text transformations and templates can show
their computed result. File, application, sequence, and Excel operations show
a plan only: Preview does not open targets, inspect workbook contents, retrieve
passwords, write files, or write to the clipboard. Missing runtime choices are
identified rather than guessed. Large inputs/results are bounded and any
display truncation is labelled.

Text transformation previews explain the change and show **Before · your
text** and **After · result** using the whole Input / Output field.
If the field is empty, Preview tells you to add text first; simple slash and
letter-case conversions also show a clearly labelled **Example only — not
your text**. Examples never become your input or result. Unchanged text is
identified explicitly; invalid text shows its problem without inventing a
result. **Show details** reveals settings and Undo/clipboard limitations using
the same snapshot. Run replaces the editor text and copies the result; it
does not change files. Undo can recover the editor text, not the old clipboard.

Other Action previews lead with **When you run this Action**, **Where the input comes
from**, **Where it goes**, and **Can I undo it?**. Bold headings separate the
explanation from shaded **Prompt text**, **Template text**, or **Text result**
blocks. These blocks preserve the actual text, including its line breaks;
instructions inside a prompt are content, not something Preview carries out.
Input snapshots and additional settings follow the explanation. Identical
saved text is shown once, and missing-input notices appear near the top.

Preview is optional. Close it and use normal Run/Open as before. It is a
snapshot, not an approval or reservation: Run uses the then-current input and
retains all existing checks and confirmations. A clipboard-based template
previews the clipboard, not unrelated Input / Output text. Protected credential
clipboard contents are never read by Preview. On narrow windows Preview and
Run/Open share a second toolbar row so their labels remain visible.

#### Run a sequence

Create **Run a sequence** from **Create Action** when several reviewed launch/open
Actions should start in a fixed order. Add existing website, file, folder,
application, or Windows-target Actions, optionally insert waits, and reorder the
list. A sequence needs 2–12 steps. Each wait is 100–10,000 milliseconds; waits
cannot be first, last, or adjacent, and their total cannot exceed 30 seconds.

For safe UAT, run **UAT: Run a harmless sequence**. Its reviewed preview opens
only the local Context Palette project folder, waits five seconds, and dispatches
the same folder again. During the wait, Context Palette remains visible, shows
the current step, and offers **Stop remaining**. Windows may reuse one Explorer
window, so use the in-app progress rather than window count to verify dispatch.
The sequence belongs to the **Developing Context Palette** Context and does not
run a script, modify a file, or use the clipboard.

Running shows every current Action name, type, target, and structured argument
before anything starts. Confirm to dispatch the steps in order. While it runs,
the Run button becomes **Stop remaining**. Stopping skips unstarted steps but
does not close targets, terminate programs, or undo anything already started.
Waits are delays only: they do not test readiness, exit codes, or success.

For `.bat` or `.cmd`, first configure an **Open or run a Windows target** Action
for the exact script. Direct `.ps1` behavior depends on Windows file
association. For predictable PowerShell dispatch, configure **Run an
application** with an exact `powershell.exe` or `pwsh.exe` and separate reviewed
arguments such as `-NoProfile`, `-File`, and the script path, then add that
Action to the sequence. A sequence never stores inline shell commands.

An Action used by any unselected Active or legacy inactive sequence cannot be
permanently deleted until those sequences are edited or deleted, or selected in
the same personal bulk-delete review. Built-in sequences may use
Built-in Actions only; My configuration sequences may use either source.

For **Paste saved text**, Run directly pastes into the application from which
the palette was opened by hotkey. Every action attempt consumes that captured
destination, including a cancelled or failed action, so a later paste cannot
reuse an old window accidentally. If the destination disappeared, Context
Palette returns and explains that the text is still available on the clipboard.
The same recovery occurs if Windows restores the window but cannot send the
paste command: ordinary text remains available for manual `Ctrl+V`; protected
credential content is cleared instead of being left behind.

For troubleshooting, `data/context-palette.log` records whether automatic paste
succeeded, used clipboard-only fallback, found an unavailable destination, was
cancelled, or encountered a Windows dispatch error. These events contain only
the paste category and outcome reason; they do not contain pasted text,
credential targets, usernames, passwords, or destination window titles.

### Capture

Copies current clipboard text into the Inbox after asking for a title. Captures are stored locally in `data/inbox.json`.

### Inbox

Shows captured items. An item can be converted into a permanent structured action
with contexts, tags, short name, optional searchable description, and a guided
action type.

Select an unused capture and choose **Delete capture…** to permanently remove
only that local Inbox copy. Context Palette confirms the selected title first.
An Action already created from the capture remains unchanged because conversion
copies the reviewed data into the Action; it does not retain an Inbox reference.
**Other ways to create** contains the attended Ask AI and website-link Harvest
routes so the normal **Create action** path remains primary.

This Capture Inbox and `data/inbox.json` are separate from the **Inbox** sheet
inside a Work Item Excel workbook. Context Palette appends to that workbook
sheet but does not delete its rows; remove those in Excel.

Select an Inbox item and click **Ask AI** for an attended AI-guidance workflow:

1. Choose one saved-text proposal, up to three saved-text proposals, or one fixed website action.
2. Review the generated request, including the captured material, before sharing it.
3. Click **Copy AI request** and paste it into the AI of your choice.
4. Paste the AI's JSON response into Context Palette.
5. Click **Review proposals**, inspect the validated actions, and select which ones to create.

To test the workflow without sending captured material anywhere, click **Insert test response** and then **Review proposals**. Context Palette creates that example locally from the selected capture. If a multi-proposal AI response contains both valid and invalid proposals, valid proposals remain selectable and each rejected proposal is reported separately.

The response must be plain JSON in the displayed format. Context Palette also
accepts exactly one complete `json` Markdown fence because many AI tools add it
automatically; surrounding commentary, multiple fences, and malformed
envelopes remain invalid. Context Palette does not send data to an AI
automatically, store an API key, or accept shell commands. Selected proposals
become permanent local actions only after confirmation.

AI responses larger than 1,000,000 characters are rejected before parsing or
replacing the current response field. This protects the resident application
from accidentally or maliciously oversized untrusted responses.

The standard action catalogue and current AI eligibility are documented in
`docs/ACTION_TYPES.md`. The first AI-enabled types are `copy_text` and
`open_url`. Website proposals require a complete HTTP or HTTPS address and are
validated again before permanent creation.

For a URL built from selected or copied text, choose **Build URL — selection,
copy, and open** and use a template such as:

```text
https://domain-product.atlassian.net/browse/{id_url}
```

If the Inbox item already contains only the stable base URL, such as
`https://domain-product.atlassian.net/browse/`, the creator appends `{id_url}`
for you when you pick that action type. `{id_url}` is replaced with URL-encoded
text from Input / Output, the captured selection, or the clipboard. Choose
**Build URL — prompt, copy, and open** when the action should ask for the value
instead. Both variants copy the completed URL and open it. The creator displays
a live example before saving.

### Sheets

Open **Help**, then choose **Cheat sheets**, to open the searchable local
reference sheets. Sheets remain structured Git-tracked JSON under
`data/cheatsheets`, and an individual entry can still be promoted to a
permanent Active action. They no longer occupy a primary Quick-action position.

### AI prompts

The fixed **Prompts** launcher opens a nested menu containing all Active AI
prompt actions. Choosing a prompt loads it into Input / Output for review and
copies it to the clipboard.

Stored prompts reuse normal Action editing and deletion. In Configure, choose
**Action types**, select **AI prompt**, and create a personal action.
Enter the visible prompt name and prompt text; no technical tag is required.
Active AI prompt actions appear automatically, while legacy inactive prompts
do not. Personal prompt text stays in ignored `data/local_actions.json`
and is never written to diagnostics by the AI menu.

### Edit

Opens the selected Action editor directly, reusing the existing Configure
workspace when it is already open. Every supported personal or Built-in Action
type can be edited; Built-in Actions first show a developer-impact warning.
Cancelling that warning leaves Configure open with the Action selected.

### Help

Opens this document inside Context Palette.

### Drop target

**Drop into Context Palette** is a small movable intake window owned by the
same resident process. It alone is permanently always on top. The ordinary
palette remains non-topmost and retains its existing auto-hide behavior.

Drop one or more Explorer files or folders, a desktop `.url` or `.lnk`
shortcut, an HTTP/HTTPS or `file:` link from a browser or OneNote, or a text
object. Context Palette uses Tcl's native file-list decoder, normalizes useful
paths and links in their original order, removes duplicates, and resolves only
the target of a shortcut. It never imports shortcut arguments.

In default show-only mode, a useful drop makes the palette and Input / Output appear without synchronizing from the
clipboard. Any stale hotkey-captured selection or destination is discarded so
it cannot replace or receive the dropped material. Input / Output placement is
one Undo step. The target remembers the last ten successful non-empty drops for
this session. **Previous** and **Next** navigate a compact description such as
the path name, web-link host, text length, or mixed item counts. Choose **Show
details** to expand a read-only preview of exactly what will be sent to Input /
Output, including shortcut warnings. Very large details say when the preview is
truncated; **Send again** still uses the complete prepared result. Details
collapse when the target is hidden or a new drop starts. Changing summaries or
details keeps all text, navigation controls, and window buttons inside the
usable area of the monitor containing the movable target. **Send again** sends
the selected exact normalized result through the same
Replace/Append/Cancel placement flow without resolving it again or creating a
duplicate history entry. Errors and empty drops are not retained. Choose its
**Hide** button to put it away and **More → Show drop target** to restore it.

The default **Show in Context Palette** behaviour does not open or execute
anything, save configuration, create an Action or Inbox item, write a log
containing the dropped value, or modify the clipboard. An unreadable `.url` or unresolved `.lnk` remains as its original
path with a warning. Showing details does not inspect a path, access a web link,
re-resolve a shortcut, or copy anything. If TkDND cannot load or initialize,
the target is unavailable but the resident launcher and every non-drop feature
continue to work. The launcher status points to **More → Show drop target**;
that command explains the required stop, setup, and restart sequence. A failed
Drop-target initialization is retained for the current process, so installing
the dependency without restarting is not sufficient.

Choose **Settings…** on the Drop window to set **On drop**:

- **Show in Context Palette** is the default and can always be restored.
- **Run an Action…** lets you choose a compatible Active Action. Review the
  named Action and its effect before saving. This explicitly permits that
  effect on each new drop; it is not a generic automation permission switch.

Compatible Actions include text/list/slash transformations, selection-based
URL builders, clipboard-placeholder templates/prompts/website/folder Actions,
saved **Send files to folder** Actions, and the existing attended Excel CSV
export workflow. The settings list other
Actions with a reason they cannot use this invocation. Credential paste,
arbitrary Windows targets, associated files/scripts, application launching,
sequences, live Excel, and Actions that ignore dropped input remain manual.

The Action receives exactly the new prepared dropped content, not the prior
clipboard, captured selection, or older text already in Input / Output.
It runs directly, without placing the drop in Input / Output and without a
Replace/Append prompt. Copy/open/Excel Actions leave existing Input / Output
alone; text-producing Actions show their completed result there afterward,
with normal Undo/history. Default **Show in Context Palette** and explicit
**Send again** still use Replace/Append/Cancel. Existing Action-specific
confirmations remain: Excel CSV opens its normal review; name conflicts open
the copy review. These windows can appear while the Palette stays hidden.
A later drop cannot replace an already-open copy or Excel review.

Results appear in the Action's workflow or, for text output, Input / Output.
Blocked or failed execution shows an explanation in the Palette without
replacing existing text. The original drop remains in Drop history; use
**Show details** to inspect it or **Send again** to place it manually. Already
completed external effects are not rolled back; inspect before manually
retrying. There is no automatic retry.
Shortcut warnings, missing/inactive Actions, changed execution configuration,
or a failed configuration reload prevent automatic execution and explain why
nothing ran. Changing an Action's target, parameters, name, or type
requires choosing and saving it again in Drop settings; Context/tag/menu-only
edits do not. An unavailable or changed approved Action is labelled
**Action blocked — review Settings**; it does not silently become show-only.
**Show details** describes the prepared dropped content retained in history,
without promising an execution or Input / Output placement.
Settings are local to this computer. **Previous**, **Next**, and
**Send again** never repeat the automatic effect. A second drop is refused
while the preceding drop's placement or synchronous Action dialog is active.

### Hide

Hides the ordinary palette but keeps it resident. Reopen with `Ctrl+Alt+P`.
The separate drop target remains visible unless you hide it independently.

### Quit

Stops Context Palette completely and releases the global hotkey.

Quit is temporarily refused while **Copy file** or **To inbox** is still
running, because terminating a write could leave an uncertain file or workbook
result. Wait for the success or error message, then quit normally. **Hide**
remains available while the operation finishes.

## Action naming

Actions use independent searchable metadata:

```text
Contexts | Tags | Short name | Description
```

Example:

```text
Product lookup | colruyt, cart | colruyt.be cart | Open the product page for a selected or copied article ID
```

The short name is the compact label shown in action lists. Description is
optional longer text: it is searchable and appears in row help and Action info,
but does not consume permanent list space.

To keep the launcher fast to scan, every built-in action type has one standard
compact symbol:

| Symbol | Action type |
| --- | --- |
| `⧉` | Paste saved text |
| `▤` | Place a template in Input / Output |
| `✦` | AI prompt |
| `↗` | Open a website |
| `⌁` | Open or run a Windows target |
| `▧` | Open a file |
| `📁` | Open a folder |
| `▶` | Run an application |
| `🔑` | Paste a Windows credential |
| `⇱` | Build and open a URL from a prompt |
| `⇗` | Build and open a URL from selection |
| `↻` | Transform a text file |
| `⇄` | Convert Input / Output lines to a list |
| `✎` | Transform Input / Output |
| `／` | Convert Input / Output path slashes |

The complete built-in action type and description remain available beside the
icon in filters and Configure, and in hover help and Action info. Symbols never
replace accessible explanations.

### Transform Input / Output

Choose **Text tools** in the Input / Output header, or right-click the field and
choose **Transform**. An operation changes the selected text, or the
complete field when nothing is selected. The result remains editable, forms
one Undo step, and is copied automatically.

Available groups include:

- **Find and filter:** literal replacement and case-insensitive keep/remove
  line filters.
- **Lines:** custom delimiter splitting and joining, blank-line cleanup,
  sorting, duplicate removal, SQL value lists, and line prefixes/suffixes.
- **Naming style:** `camelCase`, `PascalCase`, `snake_case`,
  `SCREAMING_SNAKE_CASE`, `kebab-case`, and readable words.
- **Data and encoding:** JSON formatting/minification, URL encoding/decoding,
  and SQL single-quote escaping.
- **File addresses:** Windows path ↔ `file:` URI and both slash directions.

Operations ending in **…** ask only for the values they need. Enter `\t`, `\n`,
or `\r` when a delimiter should be a tab or line break.

The menu is the direct way to transform text already in Input / Output.
Existing saved **Transform Input / Output** actions remain editable and
executable for compatibility, but new repeated transformations are
file-oriented.

### Transform a text file

Open **Configure**, choose **Action types**, then select **Transform a text
file**. Select an existing local text file, choose an operation by its readable
name, and fill only the parameters required by that operation. New forms start
with an ignored machine-local default file beside the personal configuration;
browse to a different file when the action belongs to another recurring source.

Running the action reads the file again, applies the operation, copies the
result, and shows it in Input / Output. A source strip identifies the complete
resolved path and states that the original is unchanged. Review or edit the
result, then choose:

- **Replace original…** to confirm an atomic save back to the source. Context
  Palette refuses when another program changed the file after the preview was
  created.
- **Save as…** to write the reviewed result to another file.
- **Dismiss** to detach the workspace from the source without writing.

UTF-8, UTF-8 with BOM, UTF-16/32 with BOM, and normal Windows text encodings
are supported up to 10 MiB. Replacement preserves the detected encoding, BOM,
and line endings. Files that appear binary or cannot be decoded are rejected.
If a configured path is temporarily unavailable, the action still loads and
remains editable, but running it reports the missing source.

### Open or run Windows targets

Create an **Open or run a Windows target** action when Windows itself knows how
to handle the target. Examples include:

```text
vscode://file/c:/work/project/
vscode://settings/editor.wordWrap
shell:AppsFolder
file:///C:/work/project/readme.md
C:\work\project\readme.md
C:\Tools\script.cmd
```

Optional arguments are entered in a multiline box, one argument per line, so
spaces and quoting remain predictable. Press Enter to start the next argument.
An optional working folder can also be set. Registered protocols work only when
an installed application owns that protocol. If Windows cannot resolve a path,
association, or protocol, Context Palette reports an actionable error.

File, folder, application, Windows-target, and working-folder fields accept
normal paths, URL-encoded local paths such as
`C:\work\Quarterly%20report.xlsx`, and `file:` URIs. Context Palette first uses
an existing literal path, so a real filename containing `%20` still works. If
the literal target does not exist, it tries the decoded local path. Website
addresses remain encoded: `%20` in an HTTP or HTTPS URL is passed to the browser
unchanged.

This is a deliberately powerful personal-tool action. Context Palette passes
registered protocols to Windows ShellExecute as configured; existing local
targets may first be resolved from file-URI or percent-encoded form. Context
Palette does not inspect or sandbox what Windows starts. Targets may execute
code. Configure only targets you intend to run; the application does not add a
confirmation prompt.

Protocol targets such as `onenote:`, `vscode:`, and `shell:` work without
arguments or a working folder. Context Palette omits those unset options when
calling Windows, while still forwarding either option when configured.

The main palette keeps its compact width. Its eight management commands use the
single character strip documented above, keeping every command directly
available without reducing the action console or transformation workspace.
Hover over a compact control, or move keyboard focus to it with `Tab`, to see
its full command name and explanation. The explanation remains visible when
the palette is positioned near a display edge.

## Protected Windows credential paste

Choose **Actions**, open the filter icon, then choose **Filter by type → Paste
a Windows credential** to show only protected credential Actions. Choose **All
types** to return to every Action; ordinary Find text narrows either list.

Every Active credential action also appears automatically under the fixed
**Passwords** Quick-action menu. Choosing one starts the existing protected
destination confirmation. When creating or editing it, use **Passwords menu →
Choose…** to select the menu root, an existing branch, or a new nested location
from the real menu tree.

Press `Ctrl+,`, then choose **Action types → Paste a Windows
credential** to create a permanent personal action. The action stores only an exact target
from the **Windows Credentials** or **Generic Credentials** section of
Credential Manager; it never stores the username or password.

Set up the credential first:

1. Open **Credential Manager** from Windows.
2. Open **Windows Credentials** and add either a standard Windows credential or
   a Generic credential.
3. Give it a distinctive target such as `oracle-pc17` or
   `ContextPalette/example-login`.
4. Enter the username and password there.
5. In Context Palette, use that exact target name as the action value.
6. Save the action after reviewing the target name.

To paste:

1. Focus the destination password field.
2. Press `F9` or `Ctrl+Alt+P`.
3. Run the credential action.
4. Verify the credential target and captured destination in the confirmation.
5. Confirm to return focus and paste.

The password is retrieved only after confirmation. It is placed temporarily on
a Windows clipboard item marked to stay out of clipboard history and cloud
sync. Context Palette remembers the previous plain-text clipboard value and
restores it after 15 seconds, or immediately when automatic paste fails, only
if no other program replaced the clipboard meanwhile. A newer clipboard value
always wins. If the previous clipboard had no text, the protected item is
cleared instead only when the clipboard was empty. Rich text and image formats
are not yet preserved; if the clipboard contains only a file, image, or other
non-text format, credential paste stops without changing it.

The password and remembered text are never placed in Input / Output, previews,
action files, logs, or AI prompts.

If an ordinary clipboard write fails while a protected credential is still
tracked, Context Palette keeps treating the clipboard as protected and will
not synchronize its content into Input / Output. Cleanup retries five times and
then displays a warning; quitting is blocked while protected cleanup remains
unresolved. Copy harmless text and reopen Context Palette to let the sequence
guard recognize that the protected item has been replaced.

Credential paste is unavailable after an ordinary launcher/external show
request because that route has no fresh destination window. Legacy inactive
credential actions are hidden, and credential actions are not AI-proposable.
Windows Credential Manager
protects storage at rest, but this feature cannot protect against malicious
software already running as the same Windows user.

## Product and reference lookups

If you create or retain a `Product lookup` context in My configuration, select
or copy an identifier, then run a destination action. The action URL-encodes the
identifier, copies the complete URL, and opens it in the default browser.
Built-in actions are available for the public Colruyt and Bio-Planet shopping
sites. Add personal destination actions for other product systems through
Configure.

The `Company Reference Prefixes` sheet documents known Archive and ServiceNow prefixes. Archive references can already be opened with `Open selected archive item`. ServiceNow is reference-only until its complete URL template is configured.

## Action records and deletion

- Inbox: captured but not yet structured.
- Active: permanent, editable, and visible in normal action discovery.
- Legacy inactive: an old `Archived` record retained for compatibility, hidden
  from the launcher and assignment pickers, and available only for deletion.

New and edited Actions remain Active. Deletion is a direct reviewed permanent
operation that transactionally removes the selected record and internal saved
placements without changing the external target.

## Local data

- `data/actions.json`: reviewed actions shared through Git.
- `data/local_actions.json`: ignored personal and machine-specific actions.
- `data/inbox.json`: ignored captures.
- `data/palette.json`: ignored per-Context slot overrides plus preserved legacy
  focus and pin compatibility data that no longer selects launcher Context state.
- `data/local_contexts.json`: ignored personal context definitions.
- `data/local_command_surface.json`: ignored personal Quick-action menu records.
- `data/local_work_item_sources.json`: ignored machine-local Work Item sources.
- `data/local_work_item_metadata.json`: ignored personal Work Item tags.
- `data/local_work_item_settings.json`: ignored generic Excel template path.
- `data/local_excel_automation_settings.json`: ignored machine-local path to
  the separately bootstrapped Python Excel engine.
- `data/local_text_action_source.txt`: ignored default source offered when
  creating a personal text-file transformation.
- `data/cheatsheets`: reviewed cheat sheets shared through Git.
- `data/context-palette.log*`: ignored bounded local diagnostics.

When Context Palette updates a JSON file, it writes and flushes a temporary sibling before replacing the destination. If a previous destination existed, it is preserved beside the file with `.bak` appended. Backup and temporary files are local and ignored by Git because they can contain private data.

Developers and advanced users can validate all shared and local configuration, compile the source, and run every automated test with:

```powershell
.\check-context-palette.bat
```

The configuration report identifies the owning context, command item, or palette slot when an action reference is missing. The check is read-only.

## Safety boundaries

Context Palette uses constrained action types. It does not execute arbitrary
shell command strings. Confirmed creation and edits are permanent, so review
paths, URLs, and effects before saving. Browser URLs and application paths
remain visible in local files.

Website actions require a complete HTTP or HTTPS address with a clear hostname.
For privacy and anti-spoofing safety, addresses containing embedded usernames or
passwords, whitespace in the hostname area, or ambiguous backslashes are rejected.

## Troubleshooting

Configuration reloads show a brief busy cursor and status message. Because all
configuration is local and normally loads in under a second, Context Palette
does not show a spinner that would flicker during ordinary use. Errors identify
the affected area. After startup, Actions, Contexts, Quick actions, palette
slots, and Work Item configuration reload as one unit: if any part is invalid
or changes while being read, the complete last successfully loaded interface
remains available while the files are corrected. Context Palette never mixes a
new Action list with older menus, Contexts, or slots. On first start, where no
earlier interface exists to preserve, configuration areas remain fault-isolated
and a missing or invalid palette uses safe empty slots instead of preventing the
launcher from opening. Repeated show requests do not reopen the same error for
an unchanged invalid file; after correcting a transient access problem, press
**F5** to retry the reload explicitly.

For an intermittent startup or configuration problem, inspect
`data/context-palette.log`. The local log is ignored by Git, rotates
automatically, and does not deliberately record clipboard or Input / Output
contents.

### New features are reported as unsupported

A previous resident process is still running. Run `stop-context-palette.bat`, then start `run-context-palette.bat` again.

### The Drop window is missing

Choose **More → Show drop target**. If it reports that the target is
unavailable, close Context Palette and run:

```powershell
.\stop-context-palette.bat
.\setup-context-palette.bat
.\run-context-palette.bat
```

No administrator rights are required. On another computer, its ignored
`.venv` must be prepared locally after a pull; Git transfers the requirements
file, not installed packages. If setup succeeds but the warning persists,
review `data/context-palette.log` or open **Diagnostics** in Configure for the
local initialization error. All non-drop features remain available.

### Ctrl+Alt+P does not reopen the palette

Another application may own the shortcut. Quit duplicate instances and restart Context Palette.

### Selected text was not captured

Some applications block simulated copy operations. Copy manually, open Context Palette, then press `Ctrl+V` or use the text box's right-click menu.
