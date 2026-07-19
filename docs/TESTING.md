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
3. Runs the complete `unittest` suite.

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
.\.venv\Scripts\python.exe -m unittest tests.test_actions
```

Run the entire suite directly:

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

Do not document a fixed test count; it changes as coverage grows.

## Manual Windows smoke test

Run this when launcher behavior, styling, hotkeys, clipboard handling, configuration windows, or window restoration changes:

1. Start with `run-context-palette.bat`; verify only one resident instance is created.
2. Press `F9`, then `Ctrl+Alt+P`; verify the palette appears and selected text is captured where the source application permits simulated copy.
3. Verify `Esc` hides, `Ctrl+L` focuses Find, `Ctrl+,` opens Configure, and `F1` opens Help.
4. Search, navigate with the keyboard, run a safe copy action, and verify number-row shortcuts run only while Find has focus.
5. Change Focus and verify only slots 6–9 change; verify pins 1–5 remain stable.
6. Tab to a right-side button and run its primary action with Enter or Space.
7. Create and edit a disposable personal Draft, context, and button; reload and confirm persistence. Remove the disposable records afterward.
8. Trigger a validation error and confirm the message identifies the field without losing the form contents.
9. Capture an Inbox item, convert it to a Draft, test it, and promote it only after confirmation.
10. Open Help and verify in-document search.

## Platform-effect checks

Perform only when relevant:

- Open a reviewed HTTP/HTTPS URL.
- Open an existing file and folder.
- Launch an explicitly configured executable with fixed arguments.
- Capture and restore a disposable window snapshot across the available monitors.
- Verify the UI remains responsive during restore and rejects a concurrent restore.
- Exercise `integrations\Invoke-ContextPalette.ps1` with valid and unknown contexts.

Window restoration is best-effort. Do not use unsaved work as test material.

## Final repository checks

```powershell
git diff --check
git status --short
```

Confirm that no personal/runtime files are staged. Automated checks do not replace a privacy review of tracked JSON examples.
