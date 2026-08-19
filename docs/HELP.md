# Context Palette Help

Context Palette is a fast, portable Windows launcher for reusable actions,
working contexts, captured material, and transformations.

The interface uses a clean neutral surface with Segoe UI typography and a high-contrast dark teal accent. Teal is reserved for primary actions and active selections. Blue rows identify pinned shortcuts, green rows identify focus-context shortcuts, and neutral rows are ordinary results. Native focus borders make keyboard location visible.

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

Image-to-text extraction uses an optional local OCR component. From the Context
Palette folder, run `setup-ocr-context-palette.bat`, then restart the app. It
stays inside that folder, needs no administrator rights, and adds about 270 MB.
Recognition works offline after setup; the initial setup download requires
package access. On a PC where downloads and software preparation are blocked,
use Context Palette without OCR until a prebuilt OCR-enabled portable bundle is
available.

Power Automate Desktop setup is documented in
[Power Automate integration](../integrations/README.md).

## Harvest actions from documents

For the primary route, press `Ctrl+,`, then open **Actions** and choose
**Other ways to create → Harvest documents…**. You can also choose **Harvest documents...** in
Inbox. The workflow extracts possible website actions from several documents
at once. Supported files are Markdown (`.md`), text (`.txt`), Word (`.docx`),
and Excel (`.xlsx`). Context Palette reads these files locally; it does not
start Office, evaluate formulas, run macros, fetch links, or execute discovered
content.

The review window shows each source and every candidate URL with its label and
location. Search or filter the list, inspect provenance, edit one candidate,
select or deselect candidates, and add or remove Focus memberships and tags in
bulk. A specific current Focus is proposed as membership; **General** remains
implicit. Source filenames and folders are not converted into tags.

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
their Focus memberships are synchronized to My configuration context
definitions, with rollback if either write fails. They are permanent Active
actions. Cancelling the scan or closing the review window creates nothing.
Per-file failures do not discard successful results from other files, and
size, compression, worksheet, cell, occurrence, and candidate limits keep
scans bounded.

Folder scanning, drag and drop, OneNote extraction, PDF/HTML/email parsing,
recursive crawling, remote fetching, and automatic trust are not part of this
version.

## Open and close the palette

- Start once with `run-context-palette.bat`.
- The main window opens at a compact `780x600` on an ordinary monitor. By
  default, the command console occupies about 40% of the width and Input /
  Output occupies about 60%. Drag the vertical divider to adjust that balance
  for the current session.
- Press `F9` or `Ctrl+Alt+P` to capture the current text selection and show the resident palette. On laptops in media-key mode, use `Fn+F9` or enable Fn Lock.
- The palette uses the mouse cursor position at shortcut time as its top-left corner. Near a monitor edge it shifts only as far as needed to keep the complete window visible.
- Configuration, Help, action editors, pickers, Sheets, AI, Inbox, Harvest, and
  Work Item windows open relative to their owner and stay inside the usable
  area of the monitor containing the main palette. Moving the main palette to
  another monitor before opening a window moves that window policy with it.
- Press `Esc`, click `Hide`, or close the window to hide it.
- Press `Ctrl+L` or `Ctrl+K` to return keyboard focus to Find.
- Press `Ctrl+I` to capture clipboard text, `Ctrl+,` to open Configure, or `F1` to open Help.
- Press `Ctrl+Shift+D` to open Configure directly on the safe Diagnostics tab.
- Open **More → Keyboard shortcuts** for the authoritative shortcut page.
- Press `F5` while the main palette is focused to clear transient screen state
  and return to the startup view. Find, scope, Context/tag filters, Action type,
  Work Item project filter, Focus items mode, captured selection, and Input /
  Output are cleared. Saved Focus, pins, context slots, actions, and
  configuration are preserved.
- Choose **Configure** for a visible route to the complete
  personal-configuration workspace.
- Click `Quit` to stop the resident process completely.
- If a development instance becomes stuck, run `stop-context-palette.bat` and start again. The stop command targets this project's virtual-environment GUI and foreground diagnostic process trees; it does not stop unrelated Python applications or Context Palette clones in other folders.

External Windows tools may safely show and pre-filter the existing instance:

```powershell
.\integrations\Invoke-ContextPalette.ps1 -Context "Database" -Search "SQL"
```

This does not execute the highlighted action. Avoid passing secrets or selected text as command-line search values.

## Focus context

Use the compact active-Focus menu to switch context explicitly. Choose
**Manage focuses…** in that selector to open the existing Context
configuration area, create or edit any Context, choose its Actions and Work
Items, and select up to five preferred items for slots 6 through 0. **My
configuration** definitions stay on this PC. **Built-in** definitions show a
developer warning before editing. The only shipped specific context is
**Developing Context Palette** in `data/contexts.json`; personal or
work-specific definitions live in ignored
`data/local_contexts.json`. The complete format and QTP-style recipes are in
`docs/CONTEXT_CONFIGURATION.md`.

Renaming a Focus also updates that name in existing actions, the active Focus,
and saved Focus slots. Context Palette uses a safe intermediate state so an
interrupted multi-file save may temporarily show both names, but does not leave
actions assigned to an undefined Focus. Close and reopen Configure, then retry
the rename if Windows reports a locked or unavailable file.

The Focus Context tells Context Palette what kind of work is currently most
important. It changes slots 6 through 0 and controls the mixed **Focus items**
view. In ordinary **All items**, matching Focus members appear before other
matches while Find remains global.

Focus and its icon-only **Show only this Focus** control share the first row
above Find. The same command is available in the Focus menu. The next row keeps
**All items**, **Actions**, and **Work Items** visible without taking width from
the result list.

- Slots `1–5` are personal pinned Actions and never change with Context.
- Slots `6–0` are the top five Actions or Work Items for the selected Focus. Slot
  `0` is the tenth overall slot and follows slot `9`. Unfilled slots use other
  genuine members of that Focus; they remain empty when no members remain and
  never borrow unrelated global Actions. **General** still treats all Actions
  as global members.
- An Action may appear in both groups.

With a specific Focus selected, **All items** keeps matching shortcut rows at
the top, then shows remaining members of that Focus alphabetically. When both
Focus and non-Focus matches exist, **All other matches** separates the remaining
global results. The divider cannot be selected or run. General uses ordinary
global ordering. Choosing an explicit Context filter also uses ordinary
ordering because the result set is already limited to that Context. Actions,
Work Items, and **Focus items** keep their own scope-specific ordering.

Focus and pin changes are saved before they take effect. If the local palette
file cannot be written, Context Palette keeps the previous selection and
explains the problem instead of showing an unsaved change.

Choose **Focus items** to browse Actions and Work Items assigned to the active
Focus. The list stays flat. General contains every Action and currently
discovered Work Item; a specific Focus contains its configured membership,
including unavailable Work Item references. Select an item and use Run, Enter,
or double-click as usual. Activating **Focus items** moves keyboard focus
directly into the list so arrow-key navigation can begin immediately. The button stays highlighted while this mode
is active; choose it again to return to **All items**.

Find remains global. Typing while Focus items is active temporarily shows the
normal mixed global results; it does not limit search to the Focus. Clearing
Find returns to the Focus list. Changing Focus refreshes the list only while
that list is visible with Find empty.

## Find and open Palette items

The left side is one compact command console. Focus and the three view choices
sit above Find; Find and the result list use the full console width. Quick
actions appear underneath. Choose **All
items** to find Actions and Work Items together, **Actions** for
Action-specific tools, or **Work Items** for Work Item tools. The selected view
is highlighted and does not change the active Focus. The filter icon beside
Find contains the current view's secondary commands and filters. An active
filter appears as a readable chip below Find; activate the chip to clear the
current Context, tag, type, and project filters.

Quick actions use only the height required by their visible menu rows. Extra
space automatically enlarges the result list instead of leaving a blank area
below the last Quick-action menu.

Find, **Contexts**, and **Tags** apply to both Actions and Work Items. A
specific Context returns the Actions and Work Items assigned to that Context;
**All contexts** restores global discovery. A shared tag can therefore return
both kinds in one result list.

- Type in **Find item** to filter both kinds by their searchable names and
  metadata.
- Open the filter icon and choose **Filter by context…** or **Filter by tag…**
  to open a searchable chooser and narrow the mixed list. Choose **All
  contexts** or **All tags** to clear that filter. Active filters highlight the
  icon and appear in the removable chip until cleared.
- Select an Action to show **Run**. Select a Work Item to show **Open** and the
  adjacent folder command. Enter and double-click use the selected kind's
  normal execution policy.
- Right-click opens the selected Action in Configure or shows the selected
  Work Item's workbook, folder, source, Inbox, copy-file, and tag commands.
- **Pin** remains available only for Actions in slots 1–5. Work Items can be
  assigned to numbered Focus slots 6–0 through a personal Context.

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
  launch settings. Context changes update the same context definitions used by
  Focus items, slots, search, and the Contexts section.
  Built-in actions can also be edited after acknowledging their developer warning.
- Plain number-row and numpad digits remain ordinary Find text.
- Shift plus a physical top-row number key executes slots 1 through 0 only
  while Find has focus. `Shift+0` executes the tenth slot; numpad digits remain
  Find input. This positional rule works on AZERTY and QWERTY.
- Selecting an action updates the slim communication line at the bottom.

The selected scope and results make the current view explicit without a
duplicate heading or count row. When nothing matches, the list explains how to
clear Find or create an action instead of presenting a blank pane.

Blue rows map top-to-bottom to pinned slots 1–5. Green rows map top-to-bottom
to focus-context slots 6–0. The numeric prefixes are hidden to leave more room
for names; hover a shortcut row to see its exact Shift+number binding. A
separator line divides shortcut rows from neutral search results in the
Actions scope. Action and Work Item labels use a font-measured icon column
followed directly by the short name. Symbols with different pixel widths stay
aligned without a dash or an unused tree-expansion gutter.

## Work Item-specific discovery and commands

Choose **Work Items** above Find to use the same result area for configured
local work-item folders. The selected **Work Items** scope remains highlighted,
the filter/tools icon gains Work Item commands, and the primary command
becomes **Open**. Choose **All items** or **Actions** to change view. The shared
Context and tag filters remain active across view changes; **Filter by project**
inside that menu applies only to Work Items.

- **New Work Item** opens the guided Work Item creation flow. If setup is incomplete,
  Configure opens on the missing source or generic Excel template first.
- **Send Input / Output to Inbox** appends the current Input / Output to the selected Work Item
  workbook's `Inbox` sheet. The result context menu offers the same command.
- **Copy file into Work Item** copies the one exact file path in Input / Output into the
  selected Work Item folder. The result context menu offers the same command.
- Find matches the folder name, parsed kind, organisation, subject, source
  name, detected project codes, and personal tags.
- **Filter by project** filters by one detected four-character project code.
- **Tags** uses the same exact reusable tag filter as Actions.
- **Contexts** filters by personal Context membership.
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
remains visible for the selected source. Removing a source never deletes
work folders or files. Its private tags are retained, so adding a source with
the same stable ID restores them.

Double-click a discovered Work Item, press Enter, or choose **Edit tags and
contexts** to update its personal tags and assign it directly to existing **My
configuration** Contexts. The editor writes membership to those Context records,
so the Work Item and Context editors show the same truth. Create or rename
Contexts from the Contexts page first; Built-in Contexts cannot reference
personal Work Items.

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

## Quick-action surface

The wider right side of the action console contains global configurable
menus and stays visible when Focus changes. Every visible control is one menu
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
- **Standard** is the single Built-in group. Its one **Standard** launcher
  distributes all active Built-in actions across root commands and three
  first-level sections with deeper subject levels, leaving the other editable
  group positions for **My configuration**.
- **Passwords**, **Folders**, and **Prompts** are permanent action-bound nested
  menus. They automatically include every Active `paste_credential`,
  `open_folder`, or `ai_prompt` action respectively, including actions created
  after the launcher opens and reloads.
- Edit one of those actions and set **Quick menu** to as many as three levels
  separated by `>`, such as `Work > Reports > Monthly`. Leave it empty to put
  the Action directly at that menu's root, with no extra submenu. Archiving or
  deleting the action removes it
  from its generated menu without maintaining a second assignment.
- The fixed first rows are **Standard | Passwords** and **Folders | Prompts**.
  Personal configured groups continue below them in their configured order.
- Groups remain in configured order across two columns. Subjects remain in
  configured order from top to bottom inside each group.
- The menu and every submenu accept any number of ordered Actions. Nesting
  is bounded at menu → level 1 → level 2 → level 3 → Action. Actions may stop
  at any earlier point, including directly under the menu. Native menus do not
  provide search or app-managed scrolling.

## Configure

Choose **Manage focuses…** in the Focus selector for direct Focus
configuration. Choose **Configure**, or use the shortcut (`Ctrl+,`), for the
complete guided configuration workspace. The left navigator replaces the
crowded row of tabs and keeps every section in one stable place. Frequent
destinations are grouped under **Set up** and backup or troubleshooting
destinations under **Support**:

- **Start:** ordinary Configure opens with task choices instead of assuming
  which configuration category you need. Choose **Create an Action...**,
  **Find or edit Actions**, **Organize Focuses**, **Arrange Quick actions**,
  **Set up Work Items**, or **Back up or restore**. **Browse Action types** and
  **View diagnostics** remain available as secondary choices. Each choice
  opens the existing editor; it does not create a second configuration window.
- **Actions:** choose **New Action…** for the normal creation flow. **Other ways
  to create** contains the educational Action-type catalogue and attended
  document Harvest. Find, lifecycle, and selection commands surround one
  Actions table; Contexts and tags for the selection appear below it. Choose
  **Show pins** only when assigning the five machine-local slots, then save and
  collapse them again. Hiding preserves unsaved choices for the current
  Configure window and marks the summary **unsaved changes** until Save; closing
  without Save discards them. Empty pin choices are closed automatically when saved.
  New actions default to **My configuration**; choose **Built-in** only when
  deliberately changing shipped starter data.
- **+ Action / New Action:** use the visible launcher button, Configure's
  **New Action…**, or press
  `Ctrl+N`, to search and choose a type before completing the usual Action
  form. The chooser supports typing, arrow keys, Enter, and Escape; it does
  not save anything until the Action form is confirmed. A non-General active
  Focus is prefilled as a Context. Use **Browse action types…** for the full
  educational catalogue.
- **Action types:** inspect what each available action reads and does, see a
  concrete example, then create a validated permanent action. Older
  Input / Output transformation types remain editable for compatibility but
  are not offered for new actions; use the Transform menu for immediate text
  changes or **Transform a text file** for a repeated file workflow.
- **Contexts:** choose **New Context…**, use Find to search the full table, then
  use the selected-Context card to **Edit…** or **Delete permanently…**. A
  Context organizes items; Focus is the Context currently highlighted in the
  palette. The editor lists members first, followed by optional Focus shortcuts
  6–0. My configuration Contexts can contain built-in Actions, personal Actions,
  and Work Items; Built-in Contexts remain Action-only.
- **Quick actions:** choose **New menu…** to create a configured shortcut menu.
  Select a custom menu and use **New Quick action**; select a custom item and
  use **New submenu** where the bounded hierarchy permits it. Edit, Move, and
  Delete apply only to configured structure. Each menu has one launcher;
  assigned Actions and Work Items appear in their explicit menu order.
  The automatic **Passwords**, **Folders**, and **Prompts** menus also appear in
  the same tree, marked as generated from Actions. Select an automatic menu or
  branch to add a correctly typed Action with the ordinary full form, including
  Contexts, tags, target, and a prefilled **Quick menu** location. Select an
  automatic Action leaf to **Edit Action**, or choose **Find all/matching
  Actions** from a menu or branch. Their
  structure cannot be moved or deleted here; organize it through each Action's
  **Quick menu** path. Actions at a menu root appear before child submenus. The
  selection card shows the complete path and only the commands valid for that
  selection.
  The single Built-in **Standard** group offers only Built-in actions, keeping
  starter buttons usable
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

Only one Configure workspace opens at a time. Choosing Configure again, using
Manage focuses, right-clicking an action, or opening Work Item configuration
raises that same window and moves it to the requested section or record. Close it
when finished; the next request creates a fresh Configure window.

Ordinary Configure opens on Start with focus on **Create an Action...**. Direct
routes such as Edit, Manage focuses, Work Item setup, and Diagnostics open and
focus their requested editor instead. Action, context, and button dialogs focus
and select their first editable field, so typing can begin immediately. Action
create/edit forms keep **Create/Save action** and **Cancel**
visible at the bottom. Their compact rows place labels beside fields; hover over
or move keyboard focus to a field for its explanation, or use the action
type's **?** button for complete input, effect, and example guidance. Scroll the
form body with its vertical scrollbar or the mouse wheel; moving through fields
with Tab automatically reveals the focused field.

All fields that choose an existing action use the same **Find…** picker:
pinned slots 1–5, context membership, preferred slots 6–0, and Quick-action
assignments. Search by any combination of action name, description, built-in
type, context, tag, state, stable ID, target or saved value, arguments, or
working folder. The result count and filtered list update while you type. Press
Down Arrow to enter the results, then Enter to select; pressing Enter directly
from Find selects the highlighted result. Double-click works with the mouse.
Choose **Not assigned** to clear a pin or preferred slot.

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

Creating or editing an action immediately refreshes the Actions table, pin
selectors, context summaries, Quick-action summaries, and diagnostics. Actions
created from Inbox, Harvest, or Cheat Sheets also refresh an already-open
Configure workspace.

Use **Show** to switch the Actions table between **Active**, **Archived**, and
**All** stored actions. **Archive…** is the normal way to remove an
Active Action from use without destroying its record. The confirmation reports
how many saved pins, Focus slots, Context memberships, and configured Quick
actions will be removed; empty Quick-action buttons are cleaned automatically.
The Archived Action remains searchable and editable in Configure. Restore it
before assigning a Context because Archived Actions cannot own active saved
placements.

Select an Archived Action and choose **Restore…** to make the same
record Active again. Restore does not recreate its former saved placements, so
reassign any wanted pins, Context membership, Focus slots, or configured Quick
actions. Generated Passwords, Folders, or Prompts placement can return
automatically when the Action type and retained **Quick menu** path apply.
**Delete permanently…** is available for Archived Actions and cannot be
undone inside Context Palette. Built-in lifecycle changes add a warning because
they alter starter configuration tracked by Git.

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
replace it. Its compact heading includes bitmap controls for Capture, Inbox,
**Create from Input**, **Extract text**, and **Text tools** without consuming label space.

Numbered action triggering is deliberately active only while Find has focus. In every other control—including Clipboard / Input / Output, the result list, context selector, and buttons—`1` through `9` do not execute actions. This makes Find the explicit keyboard command mode. Standard text editing remains available in the workspace.

The bottom communication line always stays one row high. Hover over it for the complete selected-action explanation; click it to open the full message in a selectable information window.

- A text selection captured with `Ctrl+Alt+P` appears here.
- `Ctrl+V` pastes at the cursor; the right-click command `Replace with clipboard` replaces everything.
- Type or edit text directly.
- The right-click command `Clear` empties it.
- The right-click menu also provides Undo, Redo, Cut, Copy, Paste, Select all, and Copy all.
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
  the unchanged **+ Action** command to choose a type yourself.
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

Controls now stay beside the thing they affect. Focus and the three view
choices remain readable above Find. The bitmap-icon filter control sits beside
Find. Below results, the stable item toolbar contains `+A`, Edit, Pin, and
Run/Open; invalid selection commands are disabled instead of failing after a
click. Work Item-specific New, Inbox, Copy file, and project commands live in
the filter/tools menu.

The Input / Output header contains Capture, Inbox, Create from Input, Extract
text, and Text tools. Configure, Help, and More sit below Quick actions. These icon-only
controls use portable Tk bitmaps rather than font characters. Hover over or
keyboard-focus any icon to see its complete name and explanation. The generic
`+A` chooser and the conservative Create from Input route remain separate.

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

#### Run a sequence

Create **Run a sequence** from **+ Action** when several reviewed launch/open
Actions should start in a fixed order. Add existing website, file, folder,
application, or Windows-target Actions, optionally insert waits, and reorder the
list. A sequence needs 2–12 steps. Each wait is 100–10,000 milliseconds; waits
cannot be first, last, or adjacent, and their total cannot exceed 30 seconds.

For safe UAT, run **UAT: Run a harmless sequence**. Its reviewed preview opens
only the local Context Palette project folder, waits five seconds, and dispatches
the same folder again. During the wait, Context Palette remains visible, shows
the current step, and offers **Stop remaining**. Windows may reuse one Explorer
window, so use the in-app progress rather than window count to verify dispatch.
The sequence is intentionally visible in the **Developing Context Palette**
Focus and does not run a script, modify a file, or use the clipboard.

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

An Action used by an Active sequence cannot be archived. An Action used by any
Active or Archived sequence cannot be permanently deleted until those sequences
are edited, archived, or deleted as appropriate. Built-in sequences may use
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
**Other ways to create** contains the attended Ask AI and document-Harvest
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

Stored prompts reuse the normal action lifecycle. In Configure, choose
**Action types**, select **AI prompt**, and create a personal action.
Enter the visible prompt name and prompt text; no technical tag is required.
Active AI prompt actions appear automatically, while Archived
prompts do not. Personal prompt text stays in ignored `data/local_actions.json`
and is never written to diagnostics by the AI menu.

### Edit

Opens the selected Action editor directly, reusing the existing Configure
workspace when it is already open. Every supported personal or Built-in Action
type can be edited; Built-in Actions first show a developer-impact warning.
Cancelling that warning leaves Configure open with the Action selected.

### Pin

Adds the selected action to the next free pinned slot from 1 to 5. If already
pinned, it removes the pin. When all five slots are occupied, unpin another
action first. To assign or reorder all five slots directly, open
**Configure**, choose **Actions**, and use **Pinned slots 1–5**.

### Help

Opens this document inside Context Palette.

### Hide

Hides the palette but keeps it resident. Reopen with `Ctrl+Alt+P`.

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
destination confirmation. Set its optional **Quick menu** path when creating or
editing it to organize credentials into as many as three nested levels; leave
the path empty to show it directly at the Passwords menu root.

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
request because that route has no fresh destination window. Archived
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

## Action lifecycle

- Inbox: captured but not yet structured.
- Active: permanent, editable, and visible in normal action discovery.
- Archived: retained and editable by opening **Configure**, choosing
  **Actions**, and setting **Show** to **Archived**, but hidden from the
  launcher and active assignment pickers.

Archiving removes saved placements so the configuration never points at an
inactive Action. Restoring returns the same Action to Active but intentionally
does not recreate those assignments.

## Local data

- `data/actions.json`: reviewed actions shared through Git.
- `data/local_actions.json`: ignored personal and machine-specific actions.
- `data/inbox.json`: ignored captures.
- `data/palette.json`: ignored per-machine focus context, pins, and context slots.
- `data/local_contexts.json`: ignored personal context definitions.
- `data/local_command_surface.json`: ignored personal Quick-action button records.
- `data/local_work_item_sources.json`: ignored machine-local Work Item sources.
- `data/local_work_item_metadata.json`: ignored personal Work Item tags.
- `data/local_work_item_settings.json`: ignored generic Excel template path.
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
the affected area and preserve the rest of the launcher where possible. If an
edited action, context, Quick-action record, or palette-state file is invalid,
its last successfully loaded configuration remains available while the file is
corrected. Palette failures retain the active pins, Focus, and context slots.
On first start, a missing or invalid palette uses safe empty pins and slots
instead of preventing the launcher from opening.

For an intermittent startup or configuration problem, inspect
`data/context-palette.log`. The local log is ignored by Git, rotates
automatically, and does not deliberately record clipboard or Input / Output
contents.

### New features are reported as unsupported

A previous resident process is still running. Run `stop-context-palette.bat`, then start `run-context-palette.bat` again.

### Ctrl+Alt+P does not reopen the palette

Another application may own the shortcut. Quit duplicate instances and restart Context Palette.

### Selected text was not captured

Some applications block simulated copy operations. Copy manually, open Context Palette, then press `Ctrl+V` or use the text box's right-click menu.
