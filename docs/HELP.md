# Context Palette Help

Context Palette is a fast, portable Windows launcher for reusable actions,
working contexts, captured material, and transformations.

The interface uses a clean neutral surface with Segoe UI typography and a high-contrast dark teal accent. Teal is reserved for primary actions and active selections. Two light teal row shades distinguish pinned and focus-context slots, while slot numbers preserve the same meaning without relying on color alone. Native focus borders make keyboard location visible.

Developers can find the current implementation architecture in `docs/ARCHITECTURE.md` and decision history in `docs/DECISIONS.md`.

Multi-PC cloning, GitHub publishing, portable paths, and shared/local data are documented in `docs/MULTI_PC_DEVELOPMENT.md`.

Power Automate Desktop setup is documented in `integrations/README.md`.

## Open and close the palette

- Start once with `run-context-palette.bat`.
- Press `F9` or `Ctrl+Alt+P` to capture the current text selection and show the resident palette. On laptops in media-key mode, use `Fn+F9` or enable Fn Lock.
- The palette uses the mouse cursor position at shortcut time as its top-left corner. Near a monitor edge it shifts only as far as needed to keep the complete window visible.
- Press `Esc`, click `Hide`, or close the window to hide it.
- Press `Ctrl+L` or `Ctrl+K` to return keyboard focus to Find.
- Press `Ctrl+I` to capture clipboard text, `Ctrl+,` to open Configure, or `F1` to open Help.
- Choose **Manage focus → Configure actions and buttons…** for a visible route
  to the complete personal-configuration workspace.
- Click `Quit` to stop the resident process completely.
- If a development instance becomes stuck, run `stop-context-palette.bat` and start again. The stop command targets this project's virtual-environment GUI and foreground diagnostic process trees; it does not stop unrelated Python applications or Context Palette clones in other folders.

External Windows tools may safely show and pre-filter the existing instance:

```powershell
.\integrations\Invoke-ContextPalette.ps1 -Context "Database" -Search "SQL"
```

This does not execute the highlighted action. Avoid passing secrets or selected text as command-line search values.

## Focus context

Use the compact active-Focus menu to switch context explicitly. Choose **Manage focus → Manage focuses…** to open the existing Context configuration area, create or edit personal contexts, and choose up to four preferred actions for slots 6 through 9. Shared definitions remain visible but read-only. Shared definitions live in `data/contexts.json`; private or work-specific definitions live in ignored `data/local_contexts.json`. The complete format and QTP-style recipes are in `docs/CONTEXT_CONFIGURATION.md`.

The Focus context tells Context Palette what kind of work is currently most important. It changes slots 6 through 9 and influences which actions appear first.

Focus and Find are compact one-line controls. Hover over or click their `?` buttons for guidance without permanently consuming screen space.

- Slots `1–5` are personal pinned actions and never change with context.
- Slots `6–9` are the top four actions for the selected focus context.
- An action may appear in both groups.

Focus and pin changes are saved before they take effect. If the local palette
file cannot be written, Context Palette keeps the previous selection and
explains the problem instead of showing an unsaved change.

Choose **Focus actions** to browse actions explicitly assigned to the active
Focus. The tree groups them by Technology, then Task. Expand or collapse
branches with the mouse or normal arrow keys; select a leaf and use Run, Enter,
or double-click as usual. Branches cannot run. Missing Technology or Task is
shown as **Other**. Activating **Focus actions** moves keyboard focus directly
into the tree so arrow-key navigation can begin immediately. Returning to a
Focus restores its expanded and collapsed branches; Run never targets an action
hidden beneath a collapsed branch.

Find remains global. Typing while Focus Actions is active temporarily shows the
existing flat global results; it does not limit search to the Focus. Clearing
Find returns to the Focus tree. Changing Focus refreshes the tree only while
that tree is visible with Find empty.

## Find and run actions

The left side of the action dashboard is one Actions workspace. Find action
sits directly above the numbered list it filters. Passwords, Types, Run, and
the action-search Help control form the narrow rail beside that list.

Search matches Technology, Task, Context, Action name, type, and content.

- Type to filter actions.
- Click **Passwords** for the protected-credential shortcut, or open **Types**
  to filter by any built-in action type. Choose **All types** to clear the type
  filter. Find text and type filters work together.
- Use Up/Down, Page Up/Page Down, Home, and End to navigate.
- Press Enter, double-click, or click **Run**.
- Numpad 1 through 9 executes the corresponding fixed slot.
- Number-row 1 through 9 executes slots only while Find has focus.
- Selecting an action updates the slim communication line at the bottom.

The Actions heading shows the current match count. When nothing matches, the list explains how to clear Find or create an action instead of presenting a blank pane.

Blue rows are pinned slots 1–5. Green rows are focus-context slots 6–9. Neutral rows are other search results.

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
- Press `Ctrl+,`, then use **Right-side buttons** to add or edit personal groups
  and buttons without editing JSON. Choose existing actions from lists; stable
  IDs are generated from the visible names when left blank.
- Groups remain in configured order across two columns. Subjects remain in
  configured order from top to bottom inside each group.

## Configure

Choose **Manage focus → Manage focuses…** for Focus configuration. Choose
**Manage focus → Configure actions and buttons…**, or use the shortcut
(`Ctrl+,`), for the complete guided personal-configuration workspace:

- **Actions:** edit every kind of personal action, including URLs, files,
  folders, applications, credentials, URL builders, and transformations.
  Shared actions remain read-only.
- **Built-in action types:** inspect what each built-in type reads and does, see a concrete example, then create a validated personal Draft.
- **Contexts:** add or edit personal contexts and assign actions to slots 6–9.
- **Right-side buttons:** add or edit personal button groups and assign existing actions. Technical IDs are generated automatically and are not shown in the normal form.

Configure opens with keyboard focus on the action list. Action, context, and button dialogs focus and select their first editable field, so typing can begin immediately.

In **Actions**, use **Find actions** or press `Ctrl+F` to filter by action name,
built-in type, context, technology, task, state, or source. Multiple words must
all match. Press Enter on the selected result to edit it.

The Actions, Contexts, and Right-side buttons tables select their first useful
row automatically. Use the arrow keys to move, then press Enter to edit the
selected personal item. Double-click provides the same action with a mouse.

Changes are saved atomically to ignored local files. Shared project examples are shown for reference but cannot be changed in this window. New actions always begin as Drafts and still require testing before they can be marked Trusted.

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
- Available transforms are lowercase, UPPERCASE, consecutive-space normalization, prefix/suffix on every line, and duplicate-line removal.
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

### Capture

Copies current clipboard text into the Inbox after asking for a title. Captures are stored locally in `data/inbox.json`.

### Inbox

Shows captured items. An item can be converted into a structured Draft action with Technology, Task, Context, Action name, and a guided action type.

Select an Inbox item and click **Ask AI** for an attended AI-guidance workflow:

1. Choose one saved-text proposal, up to three saved-text proposals, or one fixed website action.
2. Review the generated request, including the captured material, before sharing it.
3. Click **Copy AI request** and paste it into the AI of your choice.
4. Paste the AI's JSON response into Context Palette.
5. Click **Review proposals**, inspect the validated Drafts, and select which ones to create.

To test the workflow without sending captured material anywhere, click **Insert test response** and then **Review proposals**. Context Palette creates that example locally from the selected capture. If a multi-proposal AI response contains both valid and invalid proposals, valid proposals remain selectable and each rejected proposal is reported separately.

The response must be plain JSON in the displayed format. Context Palette also accepts exactly one complete `json` Markdown fence because many AI tools add it automatically; surrounding commentary, multiple fences, and malformed envelopes remain invalid. Context Palette does not send data to an AI automatically, store an API key, accept shell commands, or create Trusted actions. Created proposals are saved in local actions and must still be tested and refined.

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

Actions use four separate searchable fields:

```text
Technology > Task > Context > Action name
```

Example:

```text
Browser / Colruyt > Commercial product ID > Product lookup > Open Colruyt product ID
```

To keep the launcher fast to scan, result rows show `Command → subject`, for example `Open → Colruyt product ID`. Context, Technology, and Task remain fully searchable and appear in the row's hover tooltip and the bottom communication line.

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
- `data/local_command_surface.json`: ignored personal right-side buttons.
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
edited action, context, right-side button, or palette-state file is invalid,
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
