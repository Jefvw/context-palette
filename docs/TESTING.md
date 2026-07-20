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

## Manual Windows smoke test

Run this when launcher behavior, styling, hotkeys, clipboard handling, or configuration windows change:

1. Start with `run-context-palette.bat`; verify only one resident instance is created.
2. Press `F9`, then `Ctrl+Alt+P`; verify the palette appears and selected text is captured where the source application permits simulated copy.
3. Verify `Esc` hides, `Ctrl+L` focuses Find, `Ctrl+,` opens Configure, and `F1` opens Help.
4. Search, navigate with the keyboard, run a safe copy action, and verify number-row shortcuts run only while Find has focus.
5. Activate Focus Actions and verify keyboard focus enters its list. Search for
   an action from another Focus, verify the flat results remain global, change
   Focus while Find is non-empty, then clear Find and verify the new Focus list
   returns. Confirm only slots 6–9 change and pins 1–5 remain stable.
6. Tab to a right-side button and run its primary action with Enter or Space.
7. Create and edit a disposable personal Draft, context, and button; reload and confirm persistence. Remove the disposable records afterward.
8. In an action form, verify `Alt+C` focuses Specific contexts and `Alt+T`
   focuses Tags. From each field, verify `Alt+Down` or `F4` opens **Choose…**,
   arrow keys move through the checklist, Space toggles an item, and `Esc`
   closes it without losing typed values.
9. Trigger a validation error and confirm the message identifies the field without losing the form contents.
10. Capture an Inbox item, convert it to a Draft, test it, and promote it only after confirmation.
11. Open Help and verify in-document search.

## Platform-effect checks

Perform only when relevant:

- Open a reviewed HTTP/HTTPS URL.
- Open an existing file and folder.
- Launch an explicitly configured executable with fixed arguments.
- Exercise `integrations\Invoke-ContextPalette.ps1` with valid and unknown
  contexts when testing the optional Power Automate bridge.


## Final repository checks

```powershell
git diff --check
git status --short
```

Confirm that no personal/runtime files are staged. Automated checks do not replace a privacy review of tracked JSON examples.
