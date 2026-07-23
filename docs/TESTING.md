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

## Harvest actions manual check

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

1. Press `Ctrl+,`, open **Actions**, choose **Harvest documents...**, and select
   several representative `.md`, `.txt`, `.docx`, and `.xlsx` files.
2. Confirm progress remains responsive, Cancel stops safely, and a corrupt or
   unavailable file reports its own failure without hiding successful sources.
3. Check a repeated URL, conflicting labels, an existing Active URL, and a
   non-HTTP target. Verify their readiness and duplicate
   states, provenance, and default selection.
4. Edit one candidate and use explicit Add/Remove for Focus memberships and
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

`tests.test_launcher_smoke` exercises the real Tk view transition between
explicit Focus Actions and flat global search results. Its temporary fixture
proves that only explicit context members enter the Focus list, search remains
global, a Focus change does not silently filter visible global results, and
clearing Find restores the list when Focus Actions mode remains active.
It also verifies that the real Configure notebook exposes Diagnostics with a
read-only rendered summary plus keyboard-reachable Refresh and Copy controls.
`tests.test_diagnostics` protects the allow-listed parser and privacy boundary;
`tests.test_configuration_window` verifies exact safe-summary copying and
honest failure feedback when the Windows clipboard is unavailable.

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
2. Press `F9`, then `Ctrl+Alt+P`; verify the palette appears and selected text is captured where the source application permits simulated copy.
3. Verify `Esc` hides, `Ctrl+L` focuses Find, `Ctrl+,` opens Configure, and `F1` opens Help.
4. Enter Find text, activate type/tag filters and Focus Actions, and put text in
   Input / Output. Press `F5`; verify those transient values clear, Find regains
   focus, and saved Focus, pins, and context slots remain unchanged.
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
6. Right-click a personal action in ordinary results and in Focus Actions.
   Verify Configure opens on Actions with the clicked row highlighted and its
   name, contexts, and tags editable. Repeat with a disposable Built-in action,
   verify the Git/private-data warning appears, cancel once, then accept and
   verify the Built-in file receives the reviewed edit. Revert that disposable
   edit afterward.
7. Activate Focus Actions and verify keyboard focus enters its list. Search for
   an action from another Focus, verify the flat results remain global, change
   Focus while Find is non-empty, then clear Find and verify the new Focus list
   returns. Confirm only slots 6–9 change and pins 1–5 remain stable.
8. Tab to a Quick action and run its primary action with Enter or Space.
9. Create disposable actions and contexts in both **My configuration** and
   **Built-in**; reload and confirm each uses the selected file. In a My
   configuration context, assign both a Built-in action and a personal action,
   then verify both appear in Focus Actions without editing either action. Create
   two Quick-action groups, add more than four ordered actions to one item,
   change its default, move the item and groups, and verify left-click and
   right-click match the preview. Rename and delete an item and group. Delete a
   disposable context and verify its action memberships and Focus state clear.
   Assign an action to a pin, Focus slot, context preference, and Quick action.
   Choose **Delete selected**, verify the
   confirmation reports its references, cancel once, then accept and verify the
   action and all references disappear. Repeat the warning check with a
   disposable Built-in action, revert tracked test changes, and remove the
   remaining disposable records afterward.
10. In an action form, verify `Alt+C` focuses Specific contexts and `Alt+T`
   focuses Tags. From each field, verify `Alt+Down` or `F4` opens **Choose…**,
   arrow keys move through the checklist, Space toggles an item, and `Esc`
   closes it without losing typed values.
11. Open the **⌨** footer button and verify the searchable Keyboard Shortcuts
    page appears. With Find focused on an AZERTY keyboard, press Shift plus
    each physical top-row number key and verify the corresponding populated
    slots execute. Verify plain number-row and numpad digits filter Find, and
    Ctrl+number does not execute a slot.
12. With at least one disposable local Work Item source configured, choose
    **Configure**, then **Work Items**. Add and edit a source using Browse,
    confirm its state and item summary, edit a discovered item's personal tags,
    and use Refresh index. Confirm removing the source clearly states that no
    folders or files will be deleted. Re-add it for the opening checks. Choose
    **Work** and verify Find, Projects, and Tags combine correctly. Press Enter
    on an item with an exact workbook and verify that workbook opens; press
    Shift+Enter and verify its folder opens. Verify an item without the exact
    workbook falls back to its folder. Right-click and check workbook, item
    folder, and source-folder routes. Temporarily make one source unavailable
    and verify other sources refresh while its last successful rows remain.
13. Trigger a validation error and confirm the message identifies the field without losing the form contents.
14. Capture an Inbox item, confirm conversion, and verify the resulting Active
    action is immediately editable and persists after restart.
15. Open Help, verify in-document search, resize it, maximize it, restore it,
    and confirm responsive tables remain readable.
16. Open Configure → Diagnostics. Verify configuration counts are current,
    Refresh updates recent automatic-paste outcomes, and Copy safe summary
    places the visible report on the clipboard. Confirm raw error messages,
    sample action values, pasted text, credential fields, paths, and window
    titles are absent. Open it directly with `Ctrl+Shift+D` from the focused
    main palette and cycle with `Ctrl+Tab`; verify focus enters the Diagnostics
    summary and each other tab's primary control. On QWERTY and AZERTY, verify
    `Alt+A`, `Alt+T`, `Alt+C`, `Alt+Q`, and `Alt+D` directly select the five
    corresponding tabs—including **Quick actions** for `Alt+Q`—without closing Configure. With the main palette focused,
    verify `Ctrl+2` and `Ctrl+3` neither close/hide it nor execute action slots;
    plain `2` and `3` must retain their existing slot behavior.

## Platform-effect checks

Perform only when relevant:

- Run the real Windows keyboard path with
  `$env:CONTEXT_PALETTE_PHYSICAL_KEY_TEST='1'; .\python-context-palette.bat -m unittest tests.test_physical_keyboard_shortcuts`.
  This briefly focuses a Tk test field and uses Windows `SendInput`; it verifies
  Shift plus physical top-row 1–9 through the active keyboard layout and
  confirms Ctrl+numpad 1 does not execute a slot.

- Open a reviewed HTTP/HTTPS URL.
- Open an existing file and folder.
- Launch an explicitly configured executable with fixed arguments.
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
