# Context Palette Help

Context Palette is a fast, portable Windows launcher for reusable actions,
working contexts, captured material, and transformations.

The interface uses a clean neutral surface with Segoe UI typography and a high-contrast dark teal accent. Teal is reserved for primary actions and active selections. Two light teal row shades distinguish pinned and focus-context slots, while slot numbers preserve the same meaning without relying on color alone. Native focus borders make keyboard location visible.

Developers can find the current implementation in
[Architecture](ARCHITECTURE.md) and its chronological rationale in
[Decisions](DECISIONS.md).

Help is rendered as Markdown inside Context Palette. Use **Documents** in this
window to open other project Markdown pages, or activate a rendered local
Markdown link. Use **←**, **→**, and **Home** to move through document
history or return to the page that opened the viewer. Choose **Browser** to
open the current validated local Markdown file in the default browser.
`Alt+Left`, `Alt+Right`,
and `Alt+Home` provide the same navigation from the keyboard; `Ctrl+F` searches
the currently displayed page. Open-file actions targeting an existing `.md`
file use this viewer automatically. Other file actions keep their normal
Windows behavior. The viewer never opens arbitrary commands.

Multi-PC cloning, GitHub publishing, portable paths, and shared/local data are
documented in [Multi-PC development](MULTI_PC_DEVELOPMENT.md).

Power Automate Desktop setup is documented in
[Power Automate integration](../integrations/README.md).

## Harvest actions from documents

For the primary route, press `Ctrl+,`, then open **Actions** and choose
**Harvest documents...**. You can also choose **Harvest documents...** in
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
finishes, or to Sources when the scan has no candidates. The Draft preview has
an explicit Close button and closes with `Esc`.

Only HTTP and HTTPS targets can become actions. Existing Draft and Trusted URLs
and repeats across the selected documents are identified before creation. Word
hyperlinks, Excel hyperlinks, plain URL cells, and literal `HYPERLINK` formulas
are readable; formulas are never calculated. Unsupported targets stay visible
but cannot be selected.

Choose **Preview selected Drafts**, then **Create selected Drafts**. All selected
actions are validated again and written to the personal action file in one
atomic operation. They always start as Drafts. Cancelling the scan or closing
the review window creates nothing. Per-file failures do not discard successful
results from other files, and size, compression, worksheet, cell, occurrence,
and candidate limits keep scans bounded.

Folder scanning, drag and drop, OneNote extraction, PDF/HTML/email parsing,
recursive crawling, remote fetching, and automatic trust are not part of this
version.

## Open and close the palette

- Start once with `run-context-palette.bat`.
- Press `F9` or `Ctrl+Alt+P` to capture the current text selection and show the resident palette. On laptops in media-key mode, use `Fn+F9` or enable Fn Lock.
- The palette uses the mouse cursor position at shortcut time as its top-left corner. Near a monitor edge it shifts only as far as needed to keep the complete window visible.
- Press `Esc`, click `Hide`, or close the window to hide it.
- Press `Ctrl+L` or `Ctrl+K` to return keyboard focus to Find.
- Press `Ctrl+I` to capture clipboard text, `Ctrl+,` to open Configure, or `F1` to open Help.
- Press `Ctrl+Shift+D` to open Configure directly on the safe Diagnostics tab.
- Click the **⌨** footer button for the authoritative keyboard-shortcut page.
- Press `F5` while the main palette is focused to clear transient screen state
  and return to the startup view. Find, type/tag filters, Focus Actions mode,
  captured selection, and Input / Output are cleared. Saved Focus, pins,
  context slots, actions, and configuration are preserved.
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

Use the compact active-Focus menu to switch context explicitly. Choose **Manage focuses…** in that selector to open the existing Context configuration area, create or edit personal contexts, and choose up to four preferred actions for slots 6 through 9. Shared definitions remain visible but read-only. Shared definitions live in `data/contexts.json`; private or work-specific definitions live in ignored `data/local_contexts.json`. The complete format and QTP-style recipes are in `docs/CONTEXT_CONFIGURATION.md`.

The Focus context tells Context Palette what kind of work is currently most important. It changes slots 6 through 9 and influences which actions appear first.

Focus and Find are compact one-line controls. Hover over or click their `?` buttons for guidance without permanently consuming screen space.

- Slots `1–5` are personal pinned actions and never change with context.
- Slots `6–9` are the top four actions for the selected focus context.
- An action may appear in both groups.

Focus and pin changes are saved before they take effect. If the local palette
file cannot be written, Context Palette keeps the previous selection and
explains the problem instead of showing an unsaved change.

Choose **Focus actions** to browse actions explicitly assigned to the active
Focus. The list stays flat and follows the normal action order. General contains
every action; a specific Focus contains actions assigned to that context.
Select an action and use Run, Enter, or double-click as usual. Activating
**Focus actions** moves keyboard focus directly into the list so arrow-key
navigation can begin immediately.

Find remains global. Typing while Focus Actions is active temporarily shows the
existing flat global results; it does not limit search to the Focus. Clearing
Find returns to the Focus list. Changing Focus refreshes the list only while
that list is visible with Find empty.

## Find and run actions

The left side of the action dashboard is one Actions workspace. Find action
sits directly above the numbered list it filters. Passwords, Types, Run, and
the action-search Help control form the narrow rail beside that list.

Search matches tags, contexts, Action name, type, and content.

- Type to filter actions.
- Click **Passwords** for the protected-credential shortcut, or open **Types**
  to filter by any built-in action type. Choose **All types** to clear the type
  filter.
- Open **Tags** to filter by one exact reusable tag. Choose **All tags** to
  clear it. Find text, type, and tag filters work together.
- Use Up/Down, Page Up/Page Down, Home, and End to navigate.
- Press Enter, double-click, or click **Run**.
- A saved-text action opened through `F9` or `Ctrl+Alt+P` copies its text,
  returns to the captured application, and pastes automatically. When Context
  Palette has no fresh destination, the text remains on the clipboard and the
  status asks you to paste manually with `Ctrl+V`.
- Right-click an action row to open the Actions tab in Configure with that
  exact action highlighted. Personal actions can then be edited, including
  name, contexts, tags, type-specific value, and supported launch settings.
  Shared project actions can also be edited after acknowledging their warning.
- Plain number-row and numpad digits remain ordinary Find text.
- Shift plus a physical top-row number key executes slots 1 through 9 only
  while Find has focus. This positional rule works on AZERTY and QWERTY.
- Selecting an action updates the slim communication line at the bottom.

The Actions heading shows the current match count. When nothing matches, the list explains how to clear Find or create an action instead of presenting a blank pane.

Blue rows are pinned slots 1–5. Green rows are focus-context slots 6–9. Neutral rows are other search results.

## Find and open Work Items

Choose **Work** in the Actions rail to use the same result area for configured
local work-item folders. The heading changes to **Work Items**, Find becomes
**Find Work Item**, action-only **Passwords** is hidden, **Types** becomes
**Projects**, and **Run** becomes **Open**. Choose **Work** again to return to
Actions. Existing action filters and Focus slots are preserved while Work Items
is active.

- **New item** opens the guided Work Item creation flow. If setup is incomplete,
  Configure opens on the missing source or generic Excel template first.
- **To inbox** appends the current Input / Output to the selected Work Item
  workbook's `Inbox` sheet. The result context menu offers the same command.
- Find matches the folder name, parsed kind, organisation, subject, source
  name, detected project codes, and personal tags.
- **Projects** filters by one detected four-character project code.
- **Tags** filters by one personal Work Item tag.
- Enter, double-click, or **Open** opens the exact matching
  `<folder-name>.xlsx`; when it does not exist, the work-item folder opens.
- Shift+Enter always opens the work-item folder.
- Right-click offers the exact workbook when available, the work-item folder,
  and the configured source folder.
- Right-click a result and choose **Edit personal tags…** to open that exact
  Work Item in Configure.
- Unavailable sources keep their last successful in-memory results for the
  current app session. No Work Item index is written to disk.

To set up Work Items, open **Configure**, then choose **Work Items**. Add one or more folders
named `workitems`, giving each a friendly source name. The stable source ID is
suggested automatically and keeps tags attached when the source path differs
on another computer. The same page shows source state, provides explicit
refresh, and lets you edit comma-separated personal tags. Removing a source
never deletes work folders or files. Its private tags are retained, so adding a
source with the same stable ID restores them.

Source paths and tags remain in ignored local files on this computer. Configure
does not alter the Work Item folders or their Excel files.

For keyboard setup, `F6` switches between the Sources and Discovered Work Items
lists. In Sources, use `Insert` to add and `Delete` to remove; `F5` refreshes
from either list and Enter edits the selected row. Source dialogs place focus in
the Source name field automatically.

### Create a Work Item from the generic Excel template

Choose **Work**, then **New item**. On first use, add at least one source and
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

Choose **Work**, select a Work Item, place the material in **Input / Output**,
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
report success.

## Quick-action surface

The wider right side of the action console contains global configurable
subareas and stays visible when Focus changes. Each group presents one
full-width subject per row. The right-side `▾` indicates that right-click opens
the subject's existing multi-action menu; it does not change left-click
behavior.

- Left-click a label to execute its primary configured action.
- Right-click that label to open its individually assigned executable action menu.
- Shift+click or Ctrl+click a label to open its technical menu configuration and corresponding action file in the default JSON editor.
- Tab to a quick action and press Enter or Space to run its primary action.
- Every item uses the same selected text, Input / Output, clipboard, and safe action executor as the search list.
- Configure shared groups in `data/command_surface.json` and private groups in `data/local_command_surface.json`.
- Press `Ctrl+,`, then use **Quick actions** to add or edit personal groups
  and buttons without editing JSON. Choose existing actions from lists; stable
  IDs are generated from the visible names when left blank.
- Groups remain in configured order across two columns. Subjects remain in
  configured order from top to bottom inside each group.

## Configure

Choose **Manage focuses…** in the Focus selector for direct Focus
configuration. Choose **Configure**, or use the shortcut (`Ctrl+,`), for the
complete guided personal-configuration workspace:

- **Actions:** edit every kind of personal or shared action, including URLs,
  files, folders, applications, credentials, URL builders, and
  transformations. Before a shared action opens for editing, Context Palette
  explains that its Git-tracked change can affect other machines.
- **Built-in action types:** inspect what each built-in type reads and does, see a concrete example, then create a validated personal Draft.
- **Contexts:** add or edit personal contexts and assign actions to slots 6–9.
- **Quick actions:** add or edit personal button groups and assign existing actions. These are stored as right-side button records; technical IDs are generated automatically and are not shown in the normal form.
- **Diagnostics:** review a safe summary of loaded configuration, recent error
  counts, and automatic-paste outcomes. Use **Refresh** after reproducing a
  problem or **Copy safe summary** when asking for help. Raw log messages,
  pasted text, credentials, action values, paths, and window titles are not
  included. `Alt+A`, `Alt+T`, `Alt+C`, `Alt+Q`, and `Alt+D` directly select
  Actions, Built-in action types, Contexts, Quick actions, and Diagnostics.
  `Ctrl+Tab` cycles through all Configure tabs. Both paths move focus into the
  selected tab's main content.

Configure opens with keyboard focus on the action list. Action, context, and button dialogs focus and select their first editable field, so typing can begin immediately.

Use **Choose…** in guided action forms to select one or more defined specific
contexts. The adjacent field remains editable for quick keyboard entry and
shows the selected names as a comma-separated list. Names match without regard
to capitalization and are saved using the context's current spelling. If a
typed name is unknown, the form stays open and identifies it; create the
context first, correct the spelling, or leave the field empty for General only.

The Tags field has the same **Choose…** control for tags already used by other
actions. Tags remain open-ended: select existing ones for consistency, type new
ones when needed, or combine both approaches.

Keyboard shortcuts in these guided forms:

- `Alt+C` moves directly to Specific contexts.
- `Alt+T` moves directly to Tags.
- `Alt+Down` or `F4` opens the checklist from either its field or **Choose…**
  button.
- Use the normal arrow keys and Space in the checklist, then `Esc` to close it.

In **Actions**, use **Find actions** or press `Ctrl+F` to filter by action name,
built-in type, context, tag, state, or source. Multiple words must
all match. Press Enter on the selected result to edit it.

Use **Delete selected** to remove an action. The confirmation identifies how
many saved references will also be removed. Pins, Focus slots, context
preferences, and quick-button assignments are cleaned automatically. A quick
button is removed when it has no action left. Deleting a shared action adds a
warning because the action and affected shared configuration are tracked by
Git and can reach other machines after commit and push.

The Actions, Contexts, and Quick actions tables select their first useful
row automatically. Use the arrow keys to move, then press Enter to edit the
selected personal item. Double-click provides the same action with a mouse.

Changes are saved atomically. Personal changes use ignored local files. Shared
action changes use the Git-tracked project action file and can therefore reach
other machines or collaborators after commit and push. Never store personal
paths, secrets, or private work details in a shared action. Shared contexts and
shared Quick-action records remain reference-only. New actions always begin as Drafts
and still require testing before they can be marked Trusted.

Context slots and button assignments show human-readable action names and contexts. Internal IDs remain stored for stable references but are not part of the normal editing workflow. Successful saves appear in the Configure footer without interrupting work with a confirmation dialog.

If validation or file saving fails, the edit dialog stays open so the entered values can be corrected without starting over.

The complete JSON format is documented in `docs/COMMAND_SURFACE_CONFIGURATION.md`.

## Input / Output workspace

Input / Output is the text-transformation workspace integrated with the action
launcher, not merely a passive scratchpad or action preview. Use it for quick
manual inspection and editing, and for repeatedly applying constrained actions
to selected text or the complete field. The normal workflow is: capture or
enter text, find and apply an action, inspect or refine the result, then copy
or reuse it.

The main window uses available monitor height without becoming wider. Actions
and Quick actions receive roughly 52% of the responsive content area and Input
/ Output receives roughly 48%, keeping both parts of the workflow immediately
useful. Drag the horizontal divider to adjust that balance. On smaller screens
the same areas shrink and retain their existing scrolling. Divider movement is
bounded so neither side can be accidentally collapsed. A fresh application
start leaves the workspace empty. Reopening the resident palette can show the
current clipboard or captured selection. Actions can read or replace it. Its
compact heading explains the field without adding a separate toolbar.

Numbered action triggering is deliberately active only while Find has focus. In every other control—including Clipboard / Input / Output, the result list, context selector, and buttons—`1` through `9` do not execute actions. This makes Find the explicit keyboard command mode. Standard text editing remains available in the workspace.

The bottom communication line always stays one row high. Hover over it for the complete selected-action explanation; click it to open the full message in a selectable information window.

- A text selection captured with `Ctrl+Alt+P` appears here.
- `Ctrl+V` pastes at the cursor; the right-click command `Replace with clipboard` replaces everything.
- Type or edit text directly.
- The right-click command `Clear` empties it.
- The right-click menu also provides Undo, Redo, Cut, Copy, Paste, Select all, and Copy all.
- Open `Transform` through the right-click menu or the compact `⋮` button.
- A transform changes the selection, or the complete field when nothing is selected.
- Every transform result is copied to the clipboard automatically and can be reverted with one Undo.
- Transform groups provide lowercase, UPPERCASE, Proper Case, sentence case,
  inverted case, consecutive-space normalization, per-line trimming,
  prefix/suffix, blank-line removal, A–Z or Z–A sorting, joining lines with
  spaces, SQL value-list formatting, and consecutive or global duplicate-line
  removal. SQL formatting accepts lines, commas, tabs, or semicolons; numbers
  and `NULL` remain unquoted, while text is quoted and apostrophes are escaped.
- Transform actions read it and place their result back in it.
- URL-builder actions use it as selected input when it is not empty.

Example: in the Database context, `Convert lines to SQL string list` turns separate lines into quoted, comma-separated SQL values and copies the result.

## Main buttons

The bottom row uses compact symbols so the workspace can be larger without
increasing the screen size. Hover over or keyboard-focus a button to see its
name first, followed by the complete existing explanation.

| Symbol | Action |
| --- | --- |
| `+` | Capture |
| `▣` | Inbox |
| `✎` | Edit |
| `⌖` | Pin |
| `✓` | Trust |
| `?` | Help |
| `−` | Hide |
| `×` | Quit |

### Run

Executes the highlighted action. The exact effect appears in the bottom communication line when selected.

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

Shows captured items. An item can be converted into a structured Draft action
with contexts, tags, Action name, and a guided action type.

Select an Inbox item and click **Ask AI** for an attended AI-guidance workflow:

1. Choose one saved-text proposal, up to three saved-text proposals, or one fixed website action.
2. Review the generated request, including the captured material, before sharing it.
3. Click **Copy AI request** and paste it into the AI of your choice.
4. Paste the AI's JSON response into Context Palette.
5. Click **Review proposals**, inspect the validated Drafts, and select which ones to create.

To test the workflow without sending captured material anywhere, click **Insert test response** and then **Review proposals**. Context Palette creates that example locally from the selected capture. If a multi-proposal AI response contains both valid and invalid proposals, valid proposals remain selectable and each rejected proposal is reported separately.

The response must be plain JSON in the displayed format. Context Palette also accepts exactly one complete `json` Markdown fence because many AI tools add it automatically; surrounding commentary, multiple fences, and malformed envelopes remain invalid. Context Palette does not send data to an AI automatically, store an API key, accept shell commands, or create Trusted actions. Created proposals are saved in local actions and must still be tested and refined.

AI responses larger than 1,000,000 characters are rejected before parsing or
replacing the current response field. This protects the resident application
from accidentally or maliciously oversized untrusted responses.

The standard action catalogue and current AI eligibility are documented in `docs/ACTION_TYPES.md`. The first AI-enabled types are `copy_text` and `open_url`. Website proposals require a complete HTTP or HTTPS address and remain Drafts until reviewed and tested.

For a URL built from selected or copied text, choose **Build URL — open from selected or copied ID** and use a template such as:

```text
https://domain-product.atlassian.net/browse/{id_url}
```

If the Inbox item already contains only the stable base URL, such as `https://domain-product.atlassian.net/browse/`, the creator appends `{id_url}` for you when you pick that action type. `{id_url}` is replaced with URL-encoded text from Input / Output, the captured selection, or the clipboard. The creator displays a live example before saving. Copy-only and open-only variants can instead ask for input when run.

### Sheets

Open **Quick actions → Knowledge → Sheets** to open searchable local cheat
sheets. Knowledge stays directly below Frequent passwords so Sheets remains
visible before the configurable groups; those groups retain their configured
order and continue scrolling when needed. Individual cheat-sheet entries can
be promoted to Draft actions.

### AI prompts

The **AI** group appears beside **Knowledge**. Left-click **Prompts** to load
the first stored prompt into Input / Output for review; the reusable-template
action also copies it to the clipboard. Right-click **Prompts** to choose any
stored prompt or open **Manage AI prompts…**.

Stored prompts reuse the normal action lifecycle. In Configure, choose
**Built-in action types**, select **AI prompt**, and create a personal Draft.
Enter the visible prompt name and prompt text; no technical tag is required.
Draft and Trusted AI prompt actions appear automatically, while Archived
prompts do not. Personal prompt text stays in ignored `data/local_actions.json`
and is never written to diagnostics by the AI menu.

### Edit

Edits the selected Draft copy-text action from the launcher. To edit any
personal built-in action type, press `Ctrl+,`, then open **Actions**. Shared
actions and Trusted actions remain read-only in the launcher edit flow.

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

Actions use independent searchable metadata:

```text
Contexts | Tags | Action name
```

Example:

```text
Product lookup | colruyt, cart | Open colruyt.be cart
```

To keep the launcher fast to scan, result rows show `Command → subject`, for
example `Open → colruyt.be cart`. Contexts and tags remain fully searchable
and appear in the row's hover tooltip and the bottom communication line.

The main palette keeps its compact width. Its nine management commands use the
single character strip documented above, keeping every command directly
available without reducing the action console or transformation workspace.
Hover over a compact control, or move keyboard focus to it with `Tab`, to see
its full command name and explanation. The explanation remains visible when
the palette is positioned near a display edge.

## Protected Windows credential paste

Choose **Passwords** in the Actions tool rail to show only protected credential
actions. The highlighted button remains active while ordinary Find text
narrows that password list; choose **Passwords** again to return to all
actions.

Up to four Trusted credential actions also appear under **Frequent passwords**
as direct buttons. Selecting one starts its destination confirmation
immediately. Pinned credential actions appear first in pin order; remaining
positions use other Trusted credential actions. Draft credentials are never
shown as direct-paste buttons.

Press `Ctrl+,`, then choose **Built-in action types → Paste a Windows
credential** to create a personal Draft. The action stores only an exact target
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
6. Review the Draft and mark it Trusted.

To paste:

1. Focus the destination password field.
2. Press `F9` or `Ctrl+Alt+P`.
3. Run the Trusted credential action.
4. Verify the credential target and captured destination in the confirmation.
5. Confirm to return focus and paste.

The password is retrieved only after confirmation. It is placed temporarily on
a Windows clipboard item marked to stay out of clipboard history and cloud
sync, then cleared after 15 seconds if no other program replaced the clipboard.
It is never placed in Input / Output, previews, action files, or logs,
or AI prompts. The prior clipboard is not restored.

If an ordinary clipboard write fails while a protected credential is still
tracked, Context Palette keeps treating the clipboard as protected and will
not synchronize its content into Input / Output.

Credential paste is unavailable after an ordinary launcher/external show
request because that route has no fresh destination window. Credential actions
cannot run as Drafts and are not AI-proposable. Windows Credential Manager
protects storage at rest, but this feature cannot protect against malicious
software already running as the same Windows user.

## Product and reference lookups

Choose the `Product lookup` focus context, select or copy an identifier, then run a destination action. The action URL-encodes the identifier, copies the complete URL, and opens it in the default browser. Shared actions are available for Colruyt, Bio-Planet, ProductInfoScreen, FIC, RTI, Solucious, and the supported MyProduct entity types.

The `Company Reference Prefixes` sheet documents known Archive and ServiceNow prefixes. Archive references can already be opened with `Open selected archive item`. ServiceNow is reference-only until its complete URL template is configured.

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
- `data/local_contexts.json`: ignored personal context definitions.
- `data/local_command_surface.json`: ignored personal Quick-action button records.
- `data/local_work_item_sources.json`: ignored machine-local Work Item sources.
- `data/local_work_item_metadata.json`: ignored personal Work Item tags.
- `data/local_work_item_settings.json`: ignored generic Excel template path.
- `data/cheatsheets`: reviewed cheat sheets shared through Git.
- `data/context-palette.log*`: ignored bounded local diagnostics.

When Context Palette updates a JSON file, it writes and flushes a temporary sibling before replacing the destination. If a previous destination existed, it is preserved beside the file with `.bak` appended. Backup and temporary files are local and ignored by Git because they can contain private data.

Developers and advanced users can validate all shared and local configuration, compile the source, and run every automated test with:

```powershell
.\check-context-palette.bat
```

The configuration report identifies the owning context, command item, or palette slot when an action reference is missing. The check is read-only.

## Safety boundaries

Context Palette uses constrained action types. It does not execute arbitrary shell command strings. Draft actions should be previewed and tested before they are marked Trusted. Browser URLs and application paths remain visible in local files.

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
