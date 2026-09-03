# Testing

Context Palette combines automated domain/UI-construction tests with manual Windows checks for behavior that cannot be proven reliably in a headless test.

## Complete automated check

From the repository root:

```powershell
.\check-context-palette.bat
```

This command:

1. Validates shared and local configuration and cross-file action references.
2. Compiles `src`.
3. Runs the complete `unittest` suite, including internal Markdown-link and
   filename-casing validation for root, `docs/`, and `integrations/` guides.

It is read-only except for Python bytecode caches.

### Python access from Codex

The project-local `.venv` uses a Python installation under the Windows user
profile. A restricted Codex workspace sandbox can block that external
interpreter and produce `Access is denied` or `Unable to create process`, even
when Python works normally.

If that happens, rerun the same read-only check with authorized normal Windows
access before concluding that `.venv` needs repair. Rebuild the environment only
when the normal Windows check also fails.

Setup applies the same safeguard. A failed `.venv` check, including a missing
pip installation, does not move or rebuild the environment unless an
independent compatible Python 3.12 or newer 3.x interpreter with pip and
Tkinter can launch in that process. When both checks are inaccessible, setup
stops and requests a normal Windows retry.

## Targeted tests

Run one module while developing:

```powershell
.\python-context-palette.bat -m unittest tests.test_actions
```

Run the entire suite directly:

```powershell
.\python-context-palette.bat -m unittest discover tests
```

The wrapper runs the project-local interpreter with `src` on Python's import
path, so application modules work consistently from the repository root. It
distinguishes an unusable Python environment (repair with setup) from a project
import error (investigate with the complete check).

The inert real-Tk visual baselines have a focused size/scaling stress check:

```powershell
.\python-context-palette.bat -m unittest tests.test_ui_mockups
```

It constructs the main palette, Configure Work Items, and Configure Actions at
their normal and minimum sizes under simulated 100%, 125%, and 150% text
scaling. This protects geometry and state contracts but does not replace the
actual Windows display-scale review in [Real-Tk UI mockups](UI_MOCKUPS.md).

Do not document a fixed test count; it changes as coverage grows.

## Why GitHub runs the tests again

The repository contains `.github/workflows/tests.yml`. GitHub automatically
runs that workflow after every push and for every pull request; starting a run
does not require a separate instruction from the user or Codex.

This check deliberately repeats the local automated check in a fresh Windows
environment. The local check provides fast feedback before a commit, while the
GitHub check verifies that the committed repository can set itself up without
the current computer's existing virtual environment, caches, ignored personal
files, or other local state. Its Windows, Python, and Tk versions can also
expose portability problems that do not reproduce on the development computer.

A push should therefore normally follow a successful local
`.\check-context-palette.bat` run, but a local pass does not guarantee that the
GitHub run will pass. If GitHub reports a failure, open the linked workflow run
and inspect the failed step and test output before changing code. Warnings and
the final `Process completed with exit code 1` annotation are often secondary;
the first failed command or test identifies the useful cause.

GitHub may email the repository owner or subscribed participants when this
automatic run fails. That notification is controlled by the user's GitHub
Actions notification settings, not by Context Palette. A message saying that
all jobs failed can still represent one failed test when the workflow contains
only one job.

## Bulk Actions workbook manual check

1. Open Configure → Actions → **More Action tasks → Get blank Actions
   workbook…** and save the generated `.xlsx`.
2. In Excel, add Ready rows for several supported types, General and personal
   Contexts, normalized and mixed-case tags, descriptions, a supported Quick
   menu, multiline arguments, and a Working folder. Add Import=No, an undefined
   Context, unknown/excluded type, exact duplicate, possible duplicate, and
   same-workbook duplicate rows. Put Arguments and a Working folder on an
   Action type that does not support them and confirm they are row errors. Save
   and close the workbook.
3. Choose **Create Actions from Excel…**. Confirm row/status counts, complete
   selected-row details, default selection of only Ready rows, and explicit
   selection for a possible duplicate. Errors and exact-existing rows must not
   become selectable.
4. Change the workbook after review and confirm creation stops until Reload.
   Change an Action or Context store after review and confirm the same stale
   stop. Restore the review, choose **Create N Actions**, and confirm there is no
   second Yes/No dialog, all selected personal Active Actions and Context
   memberships appear together, and no Action executes.
5. Confirm formulas, changed headers, corrupt/encrypted or oversized packages,
   data outside A–J, and more than 1,000 populated rows stop without writes.
   Repeat at 100%, 125%, and 150% scaling and on a PC without Excel installed.

## Automatic Quick-menu organization manual check

Status: **Manual UAT pending.**

1. Create or edit one Password, Folder, and AI-prompt Action. Confirm the form
   names the correct fixed menu, shows **Menu root** explicitly, and uses a
   read-only breadcrumb plus **Choose…**, not a free-text `>` field.
2. In the chooser, search existing branches, select the root and a nested
   branch, create a new submenu under each, and verify a fourth level is
   unavailable. Cancel once and confirm the saved placement is unchanged.
3. In Configure → Quick actions, select an automatic root and choose **Manage
   menu…**. Confirm **Submenu tasks** offers only **New submenu…** at the root.
   Select one or more Active Actions, create a submenu, and verify every exact
   before → after path plus ownership/file counts before **Create submenu
   with N Actions**. Confirm no-selection explains why an Active Action is
   required, and level three disables creation.
4. Select a populated automatic branch and choose **Manage this submenu…**.
   Confirm **Submenu tasks** offers New child, Rename, Move, and Remove. Rename
   it, move it beneath a new parent while preserving its name, and merge it into
   a case-variant existing branch. Remove it and verify direct Actions move to
   the parent, child submenus move up intact, and the final button says **Remove
   submenu; keep N Actions**.
5. Select one automatic Action leaf in that branch and choose **Remove from
   submenu…**. Confirm its exact stable ID is preselected, the review promotes
   it one level, and the record and external target remain unchanged. Repeat
   with several direct members through **Remove selected from this submenu**;
   include two equal titles and confirm the correct IDs move. Confirm the last
   member removes the empty branch. At the automatic root, confirm no Remove
   command appears and the UI names permanent Action deletion as the only way
   to remove the required automatic leaf.
6. Change an Action file after review and confirm commit stops as stale. Inject
   a second-file write failure and verify exact primary/backup rollback; inject
   rollback failure and verify the organizer locks further mutation and directs
   backup/Diagnostics inspection. Confirm no Action executes and no external
   file, folder, credential, prompt target, or configured Quick-action reference
   changes.
7. Repeat the editor, chooser, and manager using keyboard only and at 100%,
   125%, and 150% scaling. Confirm search, tree, reviewed detail, fixed status,
   Submenu tasks menu, effect-labelled button, and Close remain reachable.

## Configured Quick-action placements manual check

Status: **Manual UAT pending.**

1. Create a Folder, Password, or AI-prompt Action and open **Menu locations**.
   Confirm the same screen shows one automatic tree and an optional configured
   checklist. Select a configured location, save once, and confirm both the
   Action and reference exist. Repeat while editing, then select the saved
   Action in Configure → Actions and open **Other menus…**. Confirm its
   **Automatic placement (read-only)** value names the exact
   Folders/Passwords/Prompts location and `quick_action_path`. Open another
   Action type with no automatic
   menu and confirm it says none without disabling configured placement
   management.
2. Search the configured root/branch table and select zero, one, then multiple
   locations. Confirm the current references are represented exactly and the
   review lists every addition, removal, and newly empty item before the
   effect-labelled Apply command. Applying must not show another Yes/No dialog,
   execute the Action, change its automatic placement, or reorder unrelated
   targets.
3. Switch Storage before creation and confirm newly invalid staged locations
   are cleared with a visible explanation. With a personal Action, confirm
   Built-in locations are visibly blocked and
   cannot be selected. With a Built-in Action, add eligible Built-in and My
   configuration references, reload, and confirm every placement remains.
   Revert disposable tracked changes afterward.
4. Remove all configured references and confirm the automatic menu remains
   unchanged. Then add the same Action to several configured roots/branches and
   confirm every launcher reference resolves the same Action ID; no duplicate
   Action or new placement schema should appear in either command-surface file.
5. Change a participating Action or command-surface file after review and
   confirm Apply stops as stale. Inject a later-file write failure and verify
   exact primary and `.bak` rollback. Inject rollback failure and confirm
   further writes are disabled with backup/Diagnostics guidance and no success
   claim.
6. Repeat with keyboard-only selection, Find focused during `Ctrl+A`, and at
   100%, 125%, and 150% scaling. The searchable table, exact review, fixed
   status, effect-labelled Apply button, and Close must remain reachable.

## Bulk Action update workbook manual check

Status: **Manual UAT pending.**

1. Open Configure → Actions → **More Action tasks → Export personal
   Actions for update…** and save the deterministic version-1 `.xlsx`. Confirm
   it contains only eligible personal Active ordinary Actions. Built-in,
   Legacy inactive, sequence, Excel-automation, and text-file-transform Actions must
   not appear.
2. In Excel, edit Name, Value, personal Contexts, tags, description, Quick menu,
   lossless Arguments JSON (including an empty and whitespace-only argument),
   and Working folder on representative compatible types. Include a quoted
   Context or tag containing a semicolon and a Context containing repeated
   spaces. Leave one row
   unchanged. Remove another complete row. Save and close the workbook.
3. Choose **More Action tasks → Review updated Actions workbook…**. Confirm
   only real valid changes are Ready and selected by default, the unchanged row
   is not selectable, every exact Before/After value is readable, and the
   removed row causes no deletion or Action-state change. Clear and restore one
   Ready selection with mouse and keyboard.
4. On separate fresh exports, change Action ID, State, Action type, Original
   fingerprint, a header, a formula cell, and workbook/package structure.
   Confirm each tampered, macro/link-bearing, corrupt, or unsafe workbook is
   rejected without writes. Also confirm undefined/shared Contexts and invalid
   type-specific fields become row errors.
5. Change the workbook after review, then separately change the saved Action or
   Context configuration after review. Confirm **Update N Actions** stops and a
   fresh review/export is required. Restore a Ready review and update selected
   rows; confirm the labelled button is the only confirmation, all changes land
   together, no Action runs, and deletion remains outside workbook semantics.
6. In the automated failure fixture, make Context persistence fail after the
   Action write and compare the local Action file byte-for-byte with its prior
   contents. No partial Action update may remain. Then inject a rollback write
   failure and confirm the window says configuration may have changed, disables
   export/choose/reload/update, and never says that no Actions were updated or
   offers a generic retry. Repeat the attended UI at 100%, 125%, and 150%
   scaling and on a PC without Excel installed.

## Bulk Action deletion manual check

Status: **Manual UAT pending.**

1. Create several disposable personal Active Actions and place them in a
   personal Context, Context slots, and configured Quick menus. Add one
   sequence that refers to another disposable Action. Keep the external test
   files, folders, URLs, or applications easy to inspect afterward.
2. Open Configure → Actions → **More Action tasks → Delete multiple
   personal Actions…**. Confirm Built-in Actions are absent. Use Find,
   **Select all shown**, **Clear selection**, mouse selection, and `Space`.
   Verify the footer buttons, status, and selected-Action details remain visible
   at 100%, 125%, and 150% scaling. Change Find after selecting rows and confirm
   the status and final button count selected rows hidden by the filter.
3. Select an Action that an unselected sequence uses. Confirm it is blocked and
   names the dependent sequence. Select that personal sequence too and confirm
   the batch becomes Ready. Review the combined saved-reference, empty
   Quick-action-item, and changed-file counts. No Action may execute.
4. Choose **Delete N Actions permanently**. Confirm this effect-labelled button
   is the only confirmation and there is no extra Yes/No dialog; the exact
   selected records and saved placements disappear; unrelated Actions and
   empty root Quick menus remain; and every external target is unchanged.
5. Repeat with one legacy inactive personal record. Confirm it is explicitly
   labelled, cannot be edited or restored, and can be included in the same
   deletion review without becoming Active.
6. In separate automated fixtures, change a participating Action, Context,
   palette, or Quick-menu file after review and confirm deletion stops as
   stale. Make a later configuration write fail and compare every participating
   primary file and `.bak` sidecar byte-for-byte with its prior state. No
   partial stage may remain.

## Send files to a folder manual check

Use disposable source and destination folders only. Include small text files,
a larger file, two same-named files from different folders, and pre-existing
destination files.

1. Put one exact absolute file path in Input / Output and choose **Send to…**.
   Confirm the menu exposes a selected Work Item when applicable,
   Context-relevant Folder Actions first, session recents, hierarchical all
   Folder Actions, **Find destination…**, **Choose another folder…**, and
   **Manage Folder Actions…**. Confirm ordinary execution of that same Folder
   Action still opens its folder and copies nothing. Include one relative
   Folder Action and one `file:` URI and confirm they resolve like ordinary Run.
   Include one Folder Action containing `%CLIPBOARD%`; confirm it is visibly
   unavailable as a copy destination, the clipboard is not read, and no copy
   workflow starts, while ordinary Run still expands it normally.
2. Choose an empty destination. Confirm choosing it is the only confirmation,
   copying begins in the background, the source and Input / Output remain
   unchanged, and the exact created file plus **Open destination folder** are
   shown. Confirm the successful destination enters Recent; cancel/error and
   partial results must not enter it. Restart the app and verify Recent is
   empty.
3. Create an existing `report.txt`, then send another `report.txt` with
   overwrite off. Confirm review shows the exact `report(1).txt` mapping and
   one **Copy 1 file** button. Add `report(1).txt` and confirm `report(2).txt`.
   Check **Allow overwrite** and confirm the plan targets unsuffixed
   `report.txt`, identifies one replacement, and uses **Replace 1 file** with
   no further Yes/No dialog.
4. Send two sources with the same basename. Confirm they never target the same
   final path, including with overwrite checked. Send a source already in the
   destination and confirm it is skipped rather than duplicated. Change a
   source or destination after review and verify copying stops as stale before
   an unreviewed effect.
5. Exercise quoted paths, Unicode, UNC availability, blank lines, a relative
   path, missing file, folder, URL/prose, duplicate source, 100 files, and 101
   files. Invalid input must produce no destination effects. Verify no source
   path is copied to the clipboard, logs, configuration, or recent-destination
   state.
6. During a multi-file copy choose **Stop remaining**. Confirm the current file
   completes, later files do not start, completed destinations remain, exact
   effects are reported, and no rollback/retry is claimed. Confirm Hide remains
   available but Quit is blocked until the operation's outcome is delivered.
7. Repeat the header, conflict review, busy, stopped, partial, and result states
   at 100%, 125%, and 150% display scaling and the supported minimum window.
   Confirm the literal Send-to label, status, review controls, and fixed footer
   never disappear.

## Open one Input / Output path in VS Code manual check

Use disposable local paths and close without saving anything VS Code may show.
This is an operating-system protocol handoff, not a file-copy test.

1. Put one existing absolute folder path in Input / Output and choose **Send
   to… → Open with → Open folder in VS Code**. Confirm VS Code opens that exact
   folder and no copy-review window appears.
2. Repeat with one existing file path, including matching outer quotes and a
   path containing spaces and Unicode. Confirm VS Code opens the file's
   containing folder, not a new copy and not a persisted recent destination.
3. Exercise empty, two-line, relative, missing, unavailable network, and
   unmatched-quote input. Confirm each invalid case opens nothing and explains
   how to provide one existing absolute file or folder.
4. On a disposable standard-user machine without VS Code or without a
   registered `vscode:` handler, confirm the handoff reports that setup problem
   without administrator rights or raw operating-system details. The rest of
   Context Palette must continue to work.
5. Before and after every case, compare Input / Output and the clipboard and
   inspect the source path. Confirm they are unchanged, no file was copied or
   moved, no copy destination was added to Recent, and no Folder Action ran.
   Run the same **Open a folder** Action normally and confirm it still performs
   only its ordinary open-folder effect.
6. Repeat the menu at 100%, 125%, and 150% scaling and at the supported minimum
   window. Confirm **Open with:** visually separates the opener from copy
   destinations and **Open folder in VS Code** remains readable and reachable.

## Harvest website links manual check

Last completed: **Passed on Windows on 2026-07-21.** The attended check used
representative Markdown, text, Word, and Excel files, including cross-format
duplicates, unsupported and malformed links, a corrupt source, cancellation,
an initially absent personal action store, a late duplicate, repeated
submission, and a cold application restart. All requested workflow checks
passed. The check also exposed and corrected clipped bulk-edit controls at the
standard Harvest window size.

Keyboard accessibility check: **Passed on Windows on 2026-07-22.** Physical
Windows key input verified `Ctrl+F` candidate search, `F5` rescan with focus
returning to Candidates, `Space` inclusion toggling, and `Enter` candidate
editing. The isolated check created no personal action store. The remaining
bindings, action-preview Close control, and focus-restoration callbacks are
covered by real-Tk and focused unit tests.

1. Press `Ctrl+,`, open **Actions**, choose **More Action tasks → Harvest
   website links…**, and select
   several representative `.md`, `.txt`, `.docx`, and `.xlsx` files.
2. Confirm progress remains responsive, Cancel stops safely, and a corrupt or
   unavailable file reports its own failure without hiding successful sources.
3. Check a repeated URL, conflicting labels, an existing Active URL, and a
   non-HTTP target. Verify their readiness and duplicate
   states, provenance, and default selection.
4. Edit one candidate and use explicit Add/Remove for Context memberships and
   tags. Preview the selected actions.
5. Cancel the confirmation and verify the personal action file is unchanged.
   Then confirm once and verify all selected actions appear together as Active
   **Open a website** actions.
6. Repeat the launch from Inbox and verify it opens the same review workflow.

Run the documentation-link check directly after moving or renaming a guide:

```powershell
.\python-context-palette.bat -m unittest tests.test_documentation_links
```

The checker reports the source document, line number, target, and whether the
path is missing or has incorrect filename casing. It intentionally ignores web
links, email links, heading-only anchors, inline-code examples, and fenced code
blocks.

`tests.test_launcher_smoke` exercises the real Tk view transitions among All
items, Actions, and Work Items with the unified transient Filter menu. Its
temporary fixture proves that one Context or tag can return both an Action and
a Work Item and only canonical Context members enter Context-filtered results.
It also verifies that **All contexts** uses General's slot bank, a specific
Context selects its own bank, Context and tag operate across all item scopes,
type and project remain kind-specific without changing banks, non-empty Find
results are relevance-ranked without context-slot promotion, and dormant
type/project filters remain visible in the filter chip.
`tests.test_launcher_interactions` verifies that F5 returns to **All contexts**
while preserving per-Context slot assignments and compatibility palette data.
`tests.test_action_preview` requires every supported Action type to produce a
bounded, readable **Input → Effect** summary and structured details without
technical type IDs. It protects current-input, captured-selection, destination,
credential, AI, file-recovery, and Windows-target safety wording. The launcher
smoke test verifies real Action and Work Item selections, workbook/folder
fallback, content-change refresh, and restoration after an operational message.
The same module also constructs a clean-PC data directory containing only the
tracked Built-in actions, context, and Quick-action files. It verifies that the
launcher and Configure window load entirely from those files without creating
Inbox, palette, Work Item, or local customization files merely by reading
configuration. A second clean-PC integration creates the first personal action,
context, and Quick action through the real Configure save boundaries, then
constructs a fresh launcher and verifies all three reload while unrelated
private files remain absent.
It also verifies that the real Configure page stack exposes Diagnostics with a
read-only scrollable summary plus keyboard-reachable Refresh and Copy controls.
`tests.test_diagnostics` protects the allow-listed parser and privacy boundary;
`tests.test_configuration_window` verifies exact safe-summary copying and
honest failure feedback when the Windows clipboard is unavailable.
`tests.test_action_deletion` verifies direct Active and legacy-inactive deletion,
exact saved-reference cleanup, and restoration of exact bytes across all
attempted files when any write fails, including explicit incomplete rollback.
`tests.test_work_item_organization` verifies inspection, idempotent Forget,
complete personal-reference cleanup, exact-byte rollback, and the hard boundary
that no external Work Item content path participates in the transaction.

## Manual Windows smoke test

### Verification record

Use this record for every manual pass. Do not replace **Not tested** with a
result until the check was actually performed on Windows.

| Field | Value |
| --- | --- |
| Date | Not tested |
| Tester | Not tested |
| Commit/working tree | Not tested |
| Computer and Windows version | Not tested |
| Display scale and resolution | Not tested |
| Keyboard layout | Not tested |
| Python version | Not tested |
| Work Item source/path used | Not tested |
| Excel version | Not tested |
| Overall result | **Not tested** |
| Notes/issues | Not tested |

Record each numbered check below as **Pass**, **Fail**, **Blocked**, or **Not
tested**, with a short note for any result other than Pass. Automated tests may
support the record but must never be entered as a manual Pass.

### Work Items Phase 5 result — 2026-07-21

User-reported manual checks on the primary Windows computer:

| Check | Result | Notes |
| --- | --- | --- |
| Open an exact matching workbook in Excel | Pass | Opened successfully in real Excel. |
| Fall back to the Work Item folder when the exact workbook is absent | Pass | Folder fallback worked. |
| Unavailable or network source | Not tested | Requires a suitable unavailable or network location. |
| Keyboard navigation and Work Item context menu | Pass | Keyboard and context-menu opening worked. |
| Different computer with a different absolute source path | Not tested | Requires the second development computer. |
| Display scaling and responsive layout | Pass | User confirmed the interface remained usable; scale percentage and resolution were not recorded. |

This is a partial manual result, not completion of Phase 5. The unavailable
source and different-computer/path checks remain outstanding.

Run this when launcher behavior, styling, hotkeys, clipboard handling, or configuration windows change:

1. Start with `run-context-palette.bat`; verify only one resident instance is created.
2. Press `F9`, then `Ctrl+Alt+P`; verify the palette appears centered in the
   usable area of the cursor's monitor and selected text is captured where the
   source application permits simulated copy. Repeat on a secondary monitor,
   including one with negative desktop coordinates. Move Configure to that
   monitor and open an Action editor; confirm the editor centers on the same
   monitor. Confirm compact filter pickers, menus, and tooltips remain attached
   to their controls, and the separate drop target retains its lower-right,
   user-movable placement.
3. Verify `Esc` hides, `Ctrl+L` focuses Find, `Ctrl+N` opens the Action-type
   chooser, `Ctrl+,` opens Configure on **Start**, and `F1` opens Help. On
   Start, verify all six primary tasks are visible without scrolling. Open each
   destination and confirm it reuses the same Configure window. Verify
   **Create an Action...** opens the existing type chooser, while direct Edit,
   Work Item, Diagnostics, and Filter-menu **Manage contexts…** routes bypass
   Start. In the chooser,
   verify typing filters types, arrows and Enter choose one, and Escape or
   Cancel changes nothing. Repeat with **New Action…** and `Ctrl+N` on Configure
   → Actions; confirm a specific active Context filter is offered as the initial Context,
   an existing Configure workspace is reused, and backup/restore busy state
   refuses the request.
   Put one absolute file path in Input / Output, including a quoted path with
   spaces, and choose **Create Action...** beside **Text tools**. Verify **Open a
   file** opens directly with an editable suggested name and the complete path
   prefilled, even when it wraps visually. Repeat with an existing folder,
   `.exe`, and complete HTTP/HTTPS address. Select just the address inside a
   longer note and verify the selection wins. Try prose, multiple targets, a
   genuine multi-line value, a relative path, and a script-like path; verify
   none is guessed. Try an unavailable absolute document path and verify the
   review form appears immediately without waiting for the drive.
   Cancel each form and confirm nothing is created or run. Finally verify the
   existing launcher **+ Action** control still opens its normal unprefilled type chooser.
   On initial display, verify the command console occupies about 40% of the
   width, Input / Output occupies about 60% and nearly the full height, Find is
   no wider than its result list, and up to seven result rows are visible at
   normal scaling, with fewer retained at increased scaling. Verify
   there is no separate top toolbar or bottom command bar. Confirm **All items**
   contains both Actions and Work Items. Select one of
   each and verify the primary command changes between Run and Open. Choose one
   Context filter and one tag that each belong to both kinds and verify both
   remain in the mixed results. Switch to Actions, then Work Items, and back;
   verify the shared Context/tag filters and chosen slot bank remain active and the
   filter menu changes between Action type tools and Work Item/project tools
   without moving Find, the result list, or the stable `+A`/Edit/Run toolbar.
   Verify Configure, Help, and More remain below Quick actions. Resize to the
   supported minimum and verify the filter control, item toolbar, app controls,
   and all three scope labels remain available. Drag
   the vertical divider and verify both sides remain bounded and the manual
   balance remains adjustable for the session.
   While moving through representative Actions and Work Items, verify the
   bottom line consistently reads **Input → Effect** before Run/Open. Include an
   empty and populated Input / Output transform, a saved-text action opened
   with and without a fresh hotkey destination, an AI prompt, a protected
   credential, a Windows target, a text-file transform, and Work Items with and
   without matching workbooks. Confirm risk, non-submission, cleanup, unchanged
   source, and folder fallback remain visible. Hover and click the line to
   verify structured details, then run an item and confirm its operational
   result temporarily replaces the preview. Select again to restore it.
4. Enter Find text, choose a Context filter, activate tag/type/project filters,
   and put text in Input / Output. Press `F5`; verify transient values clear,
   Find regains focus, **All contexts** and General's slot bank become active,
   and legacy focus/pin data plus every per-Context slot assignment remain
   unchanged. Restart and confirm no result filter is restored or added to
   `data/palette.json`.
5. From a disposable text field, open the palette with the hotkey and run a
   saved-text action. Verify the palette hides, the original window regains
   focus, and the text is pasted. Open Context Palette without a captured
   destination and verify the same action copies only with a manual-paste
   status. Reopen by hotkey, run or cancel a non-paste action, then verify a
   later saved-text action does not paste into the original window. Verify
   number-row shortcuts run only while Find has focus.
   With simulated Windows input dispatch failure, verify the hidden palette
   returns, ordinary text remains on the clipboard, protected credential text
   is cleared, and the error gives the appropriate recovery instruction.
   Inspect the local log for success, no-destination, unavailable-destination,
   and dispatch-error outcomes. Verify sample saved text, credential targets,
   usernames, passwords, and window titles are absent from every event.
6. Right-click a personal Action in ordinary results.
   Verify Configure opens on Actions with the clicked row highlighted and its
   name, contexts, and tags editable after choosing **Edit…**. From the
   main palette, select the same Action and choose **Edit**; verify its editor
   opens directly in the reused Configure workspace. Repeat with a disposable Built-in action,
   verify the Git/private-data warning appears, cancel once, then accept and
   verify the Built-in file receives the reviewed edit. Revert that disposable
   edit afterward. In Configure -> Actions, delete a disposable personal Action
   assigned to a Context, context slot, and configured Quick action. Cancel the
   first review and confirm nothing changes. Repeat and verify the review names
   the exact stable ID and placement impact, the Action disappears from every
   runtime placement, and its external target remains unchanged. Repeat review
   cancellation with a disposable Built-in Action and verify the
   Git/multi-computer warning.
   In Configure, confirm **Set up** and **Support** are visually separate and no
   horizontal tab strip appears. On Actions, verify no pin configuration or Pin
   toolbar command remains and the delete command stays readable. On Work
   Items, verify **Manage sources…** contains Add, Edit, Remove, and Creation
   template while Refresh remains visible; with no sources, Add and template
   stay available while Edit, Remove, and Refresh are disabled.
7. While **All items** is active, choose a specific **Filter by context…** value
   and verify Actions and Work Items are limited to canonical membership while
   slots 6–0 switch to that Context's bank. Repeat in Actions and Work Items;
   verify the same Context and tag remain active across all three views. Apply
   Action type, Work Item project, tag, and Find values in turn and verify they
   narrow results without selecting another slot bank. Choose **All contexts**
   and verify global results plus General's bank return. With Find empty,
   confirm genuine slots 6–0 can appear first and unused slots remain empty.
   Enter queries matching an exact name, prefix, visible-name substring, and
   metadata only; verify relevance order and no shortcut promotion. Confirm
   Shift+1–5 never executes and legacy focus/pin IDs survive a palette-state
   save without restoring a Context filter.
   Open Configure → Contexts and verify **General — All items** is the fixed
   first row. Confirm its card offers **Edit shortcuts…** but no rename,
    membership, or delete command. Assign an Action and a Work Item to slots 6
    and 7, save, clear to **All contexts**, and verify that General bank appears.
    Reopen the editor and verify unassigned rows show their effective
    **Automatic — _item_** values. Return every row to **Automatic**, save, and
    verify automatic General ordering returns. Confirm no General record was
    added to either Context file and the preferences were stored only in local
    palette state.
8. At the standard `780x600` size and supported minimum, verify Quick actions
   use two readable columns without clipping beneath discovery. Narrow the
   command console until one column is genuinely necessary, then verify stable
   row-major order returns. Confirm fixed Standard is first, personal configured
   menus precede shared configured menus, automatic Passwords/Folders/Prompts
   follow them, and every launcher remains menu-only. Tab through the visible scope controls,
   Find/filter/results, item toolbar, Quick actions, app controls, workspace
   header controls, and Input / Output. Press Enter or Space on a
   Quick-action launcher and verify it opens the menu without running an
   Action. Open every Text tools group and verify it matches the
   right-click Transform catalogue. Exercise a text-file preview and verify its
   provenance, Replace original, Save as, and Dismiss strip remains usable.
   In **Lists**, transform separate `alpha`, `42`, and `O'Brien` values with
   the no-quote, single-quoted-text, and double-quoted-text commands. Verify the
   outputs match Help, numbers remain unquoted, embedded quotes are doubled,
   and a quoted value containing a comma remains one value. Verify the SQL
   command adds parentheses and keeps `NULL` unquoted.
9. Create disposable actions and contexts in both **My configuration** and
   **Built-in**; reload and confirm each uses the selected file. In a My
   configuration Context, assign a Built-in Action, a personal Action, and a
   disposable Work Item, then verify all three appear under that Context filter
   without editing either Action or the Work Item folder. Put the Work Item in slot 6,
   verify `Shift+6` opens its workbook/folder, disconnect its source, and verify
   the unavailable reference remains saved and recoverable after reconnection. Create
   two Quick-action groups, add more than four ordered Actions to one item,
   move the item and groups, and verify launcher left-click browses while
   launcher right-click offers Add/Organize. Inside the menu, verify Action
   left-click runs only the selected Action and Action right-click opens only
   its editor. Rename and delete an item and group. Delete a
   disposable Context and verify its Action memberships and slot configuration clear.
   Assign an Action to a context slot, Context preference, and Quick action.
   Choose **Delete permanently…**, verify the
   confirmation reports its references, cancel once, then accept and verify the
   action and all references disappear. Repeat the warning check with a
   disposable Built-in action, revert tracked test changes, and remove the
   remaining disposable records afterward.
   In every Action-reference field used above—Context membership,
   preferred slots, and Quick-action assignments—open **Find…**, search by
   action name and by a metadata term such as type, context, or tag, and verify
   Down Arrow plus Enter and double-click select the expected action. Verify
   **Not assigned** clears a preferred slot without widening
   Configure beyond the screen.
10. In an action form, verify `Alt+C` focuses Specific contexts and `Alt+T`
   focuses Tags. From each field, verify `Alt+Down` or `F4` opens **Choose…**,
   arrow keys move through the checklist, Space toggles an item, and `Esc`
   closes it without losing typed values.
11. Verify compact bitmap controls remain fully visible and their tooltips begin
    with semantic command names for Filter, Edit, Capture, Inbox, Extract
    text, Text tools, Configure, Help, and More. Switch views and verify the
    stable item toolbar does not move while scope-specific commands change in
    the filter menu. Open More and verify the searchable Keyboard Shortcuts page
    appears. With
    Find focused on an AZERTY keyboard, press Shift plus
    each physical top-row key from 6 through 0 and verify the corresponding
    populated context slots execute. Verify Shift+1–5 do nothing, plain
    number-row and numpad digits filter Find, and
    Ctrl+number does not execute a slot.
    Confirm result labels have no numeric prefixes, context shortcut rows are
    green, ordinary results are neutral, and a
    shortcut-row tooltip reports its exact Shift+number binding. Confirm the
    compact controls remain visible without clipping.
    Confirm row icons share one aligned column, names start at one aligned
    position without a dash, and no blank tree-expansion gutter remains before
    the icons in All items.
12. With at least one disposable local Work Item source configured, choose
    **Configure**, then **Work Items**. Add and edit a source using Browse,
    confirm its state and item summary, edit a discovered item's personal tags
    and existing My configuration Context memberships in the same dialog,
    and use Refresh index. Confirm removing the source clearly states that no
    folders or files will be deleted and all Palette organization is retained.
    Re-add it with the same identity and confirm organization returns. On a
    disposable Work Item, choose **Organize → Forget Palette organization…**;
    confirm tags, Context/preferred placement, context slots, and personal
    Quick-menu references are removed while its folder, workbook, files, and
    workbook Inbox remain. Re-add organization needed for the opening checks. Choose
    **Work** and verify Find, Projects, and Tags combine correctly. Press Enter
    on an item with an exact workbook and verify that workbook opens; press
    Shift+Enter and verify its folder opens. Verify an item without the exact
    workbook falls back to its folder. Right-click and check workbook, item
    folder, and source-folder routes. Temporarily make one source unavailable
    and verify other sources refresh while its last successful rows remain.
    Open **Configure**, choose **Quick actions**, add a My configuration level,
    choose an action and at least two Work Items, reorder them together, and verify the resulting
    Quick-action menu preserves the
    mixed order, the Work Item opens the exact workbook, and it falls back to the folder when that workbook is
    absent, and remains configured with a clear unavailable message while its
    source is disconnected. Confirm a Built-in Quick action does not offer a
    Work Item assignment.
    Right-click Passwords, Folders, and Prompts. Confirm each offers its typed
    Add command and Organize/Find commands. Create one disposable Action inside
    a branch and verify the normal form still includes storage, name,
    description, Contexts, tags, target, and the prefilled menu location. Clear
    the location and verify the Action appears at the menu root with no
    **Unsorted** submenu. Delete the disposable Action afterward.
    Select a specific Context filter with fewer than five genuine members and
    confirm slots 6–0 remain empty after its final member instead of showing
    unrelated global Actions. Clear to **All contexts** and confirm General's
    bank returns.
    Run **UAT: Run a harmless sequence**, inspect its two project-folder steps
    and five-second wait, cancel once, then confirm and use **Stop remaining**
    during the wait. Verify the in-app step progress; Explorer may reuse one
    window. Confirm no script runs and no file or clipboard changes.
13. Trigger a validation error and confirm the message identifies the field without losing the form contents.
14. Capture an Inbox item, confirm conversion, and verify the resulting Active
    action is immediately editable and persists after restart. Return to Inbox,
    select that capture, and cancel **Delete capture…** once; confirm it remains.
    Delete it after confirmation and verify only the captured copy disappears
    while the created Action remains. Confirm **Other ways to create** still
    exposes Ask AI and Harvest website links. Do not use this check to delete a Work
    Item workbook Inbox row; those remain Excel-managed.
15. Open Help, verify in-document search, resize it, maximize it, restore it,
    and confirm responsive tables remain readable.
16. Open Configure → Diagnostics. Verify configuration counts are current,
    Refresh updates recent automatic-paste outcomes, and Copy safe summary
    places the visible report on the clipboard. Confirm raw error messages,
    sample action values, pasted text, credential fields, paths, and window
    titles are absent. Open it directly with `Ctrl+Shift+D` from the focused
    main palette and cycle with `Ctrl+Tab`; verify focus enters the Diagnostics
    summary and each other section's primary control. On QWERTY and AZERTY, verify
    `Alt+A`, `Alt+T`, `Alt+C`, `Alt+Q`, `Alt+W`, `Alt+B`, and `Alt+D` directly select their
    corresponding sections—including **Quick actions** for `Alt+Q`—without closing Configure. With the main palette focused,
    verify `Ctrl+2` and `Ctrl+3` neither close/hide it nor execute action slots;
    plain `2` and `3` must retain their existing slot behavior.

## Platform-effect checks

Perform only when relevant:

- Start the app with an empty clipboard and verify **Drop into Context
  Palette** is the only permanently topmost window. Hide the ordinary palette
  and confirm the target remains mapped; show the palette with F9/Ctrl+Alt+P
  and confirm its existing auto-hide and temporary-attention behavior are
  unchanged. Hide and restore the target through **More → Show drop target**.
  Drop Explorer files, a folder, multiple ordered items, a UNC path, a
  percent-encoded path, `.url`, `.lnk`, a browser URL, OneNote link/text, and a
  desktop shortcut. With empty Input / Output, verify direct placement. With
  existing text, independently verify Replace, Append, and Cancel. Confirm the
  target remains visible, stale captured selection/destination state never
  wins, the clipboard is byte-for-byte unchanged, and no target opens or runs.
  Make more than ten successful drops and confirm only the newest ten remain;
  use Previous/Next and confirm the compact path name, web-link host, text
  length, or mixed counts identify each selection. Expand **Show details** and
  verify exact normalized values plus `.url`/`.lnk` warnings, wrapped vertical
  scrolling, a visible truncation notice for large content, and no filesystem,
  web, clipboard, or execution effect. Confirm Hide/Show and a new drop collapse
  details while retaining the in-memory list. Use **Send again** to restore an
  older drop—including content beyond a truncated preview—through the same
  placement choice. Confirm errors/empty drops are absent. In Input / Output, verify Back/Forward across typed,
  dropped, OCR, transformed, and clipboard-replaced content; verify a new edit
  after Back discards the old forward branch while native Undo/Redo still works.
  Repeat the window/layout checks at 100%, 125%, and 150%; after every summary,
  Previous/Next change, and details expansion confirm the complete text plus
  Previous, Next, Send again, Show/Hide details, Hide, and title-bar controls
  remain inside the current monitor work area. Move the target near every edge
  and onto a secondary monitor before repeating. Finally simulate an
  unavailable TkDND component and confirm only the drop target is unavailable,
  launcher status points to **More → Show drop target**, the dialog prescribes
  stop/setup/restart, and no withdrawn partial Toplevel remains after native
  registration or either event-binding failure.

- On a second standard-user PC, pull a revision whose `requirements.txt` does
  not match the local setup marker. Confirm `run-context-palette.bat` refuses
  launch before `pythonw` starts and prints the stop/setup/retry sequence. Run
  setup and confirm normal launch plus the Drop target. Then simulate a native
  TkDND initialization failure with a current marker and confirm the main app
  still opens, every non-drop feature works, and restarting is required after
  repair. No step should require administrator rights.

- On a standard-user Windows PC, first start Context Palette with Python Excel
  absent and then with an invalid configured path. Confirm only the Excel CSV
  Action is unavailable and ordinary discovery, Input / Output, drop intake,
  Actions, Contexts, and Quick menus continue to work. With a separately
  cloned/transferred and bootstrapped Python Excel engine, use disposable
  closed `.xlsx` fixtures. Place exact paths one per Input / Output line and
  repeat from Drop into Context Palette. Confirm the 100-workbook limit,
  required worksheet prompts, automatic first-workbook-folder output, the
  reviewed output-folder override, asynchronous planning, and an
  exact Input → Effect review before execution. Export all used columns to a
  new folder; verify sources are byte-for-byte unchanged, every displayed CSV
  exists, and **Open output folder** opens that folder. Verify an existing
  **Allow overwrite** starts unchecked, and `report.csv` remains unchanged
  while the unchecked plan reviews and creates
  `report(1).csv`, then `report(2).csv` when both earlier names exist. Turn
  **Allow overwrite** on and verify the review targets unsuffixed `report.csv`,
  labels it **Replaces**, shows exact create/replace counts, and uses one
  effect-labelled button. Confirm a mixed batch can show **Replace 1 and create
  2 CSV files**. Execute only against disposable outputs; verify created and
  replaced results are listed separately and sources remain byte-for-byte
  unchanged. Change a reviewed source or destination and confirm exact
  stale-plan handling requires a fresh plan and review. Inject a pre-effect
  failure, partial-effect failure, and lost process and confirm distinct honest
  states with no automatic retry. Confirm no replacement backup/rollback,
  cancellation/progress claim, sequence route, Context Palette filename
  allocation, or desktop Excel launch.

- With a separately bootstrapped Python Excel engine at commit `e405e14`, use
  a disposable already-open workbook to run **Apply Excel format template**.
  Confirm missing/invalid launcher setup disables only Excel Actions; inventory
  finds the active workbook; the workbook/worksheet labels, captured-F9
  preselection, active-sheet fallback, inline Refresh, and Return eligibility
  match the conversion Action; one-worksheet and all-visible choices act only on
  the displayed target; AutoSave is rejected; and Standard data applies Aptos
  11 to the used range, row-1 header treatment, freeze top row, and a filter
  only when absent. Verify hidden sheets are skipped, stale inventory requires
  Refresh, and exact partial/unknown results require inspection rather than an
  automatic retry. Confirm Context Palette never saves or closes Excel, Apply
  has no second confirmation, and Return to Excel is only a best-effort focus
  request. The disposable one-worksheet path with an existing filter passed on
  2026-08-25. Repeat the complete matrix at 100%, 125%, and 150% display
  scaling.

- Against Python Excel commit `08af313`, run **UAT: Convert
  scientific-notation columns** first without the UAT environment variable.
  Confirm capability discovery and that its initial workbook/worksheet chooser
  matches the format-template Action, including duplicate-name labels,
  captured-F9 preference, active visible worksheet, inline Refresh, and
  Return-to-Excel eligibility. Then confirm paged preflight, physical
  column selection, and planning work, while Execute remains disabled with a
  persistent Development/UAT explanation. Then stop the app, set
  `CONTEXT_PALETTE_UAT_LIVE_TEXT_CONVERSION=1`, and restart. Use only a
  disposable open `.xlsx`: include scientific text, ordinary text,
  leading-zero identifiers, current numeric scalars, blank and duplicate
  headers, and formulas outside the selected columns. Verify selected eligible
  cells become text; ordinary/leading-zero text content is unchanged; only
  selected physical columns and used data rows change; the header and formulas
  outside scope are untouched; Excel remains open, dirty, and unsaved; and no
  extra Excel process remains. In a separate fixture, put a formula inside the
  selected scope and verify the plan blocks with no Execute.
- Review default and overridden sibling recovery paths; every override must
  produce a new plan. Confirm the engine-created recovery workbook opens and
  contains the pre-change state. Exercise precision-risk acknowledgement,
  stale workbook/sheet/plan, an existing recovery path, a clean failure with a
  verified recovery, partial failure, and process/protocol loss. Confirm no
  automatic retry, exact completed-column/count reporting, and guidance to
  inspect Excel and recovery before another run. Repeat with Unicode names,
  duplicate workbook names in separate Excel processes, blank/duplicate
  headers, enough columns to exercise paging/truncation, Return to Excel, and
  100%/125%/150% scaling. Never record the configured launcher path, workbook
  token, path, header, or sample content in tracked files or ordinary logs.

- With the optional OCR component prepared, copy a Snipping Tool bitmap and
  choose **Extract text**. Verify the UI stays responsive, useful text appears
  in Input / Output, the original image remains on the clipboard, and Undo
  restores the prior workspace. Repeat with one exact selected image path, the
  file-picker fallback, non-empty and concurrently edited workspace text, a
  no-text image, an oversized image, accented Latin text, and networking
  disabled. On a copy without the component, verify the command explains local
  setup and leaves Input / Output unchanged. Also verify the app still starts
  and ordinary Find, Configure, Quick actions, and Work Items remain usable.

- Run the real Windows keyboard path with
  `$env:CONTEXT_PALETTE_PHYSICAL_KEY_TEST='1'; .\python-context-palette.bat -m unittest tests.test_physical_keyboard_shortcuts`.
  This briefly focuses a Tk test field and uses Windows `SendInput`; it verifies
  Shift plus physical top-row 1–9 through the active keyboard layout and
  confirms Ctrl+numpad 1 does not execute a slot.

- Open a reviewed HTTP/HTTPS URL.
- Open an existing file and folder using normal paths, `%20`-encoded paths, and
  `file:` URIs. Confirm an HTTP/HTTPS URL containing `%20` stays encoded.
- Launch an explicitly configured executable with fixed arguments and test a
  `%20`-encoded executable or working-folder path when this behavior changes.
- Exercise `integrations\Invoke-ContextPalette.ps1` with valid and unknown
  contexts when testing the optional Power Automate bridge.
- For AI-boundary changes, verify a response above 1,000,000 characters is
  rejected without replacing the existing response field.


## Final repository checks

```powershell
git diff --check
git status --short
```

Confirm that no personal/runtime files are staged. Automated checks do not replace a privacy review of tracked JSON examples.
