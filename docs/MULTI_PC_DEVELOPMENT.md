# Multi-PC and GitHub Development

This guide explains how to develop and use Context Palette safely on multiple Windows computers.

## Recommended repository visibility

Use a private GitHub repository while the product and data-separation model are still evolving. Runtime snapshots and personal data are ignored now, but earlier local Git history must also be reviewed before the first push.

No open-source license has been selected yet. Keep the repository private, or choose and add an appropriate license before intentionally publishing it for public reuse.

## First computer: publish preparation

1. Confirm tests pass:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover tests
   ```

2. Confirm ignored personal files are not staged:

   ```powershell
   git status --short
   git check-ignore data\inbox.json data\local_actions.json data\local_command_surface.json data\palette.json
   git check-ignore data\layouts\snapshots\example.json
   ```

3. Review the complete history for previously committed private data before pushing.
4. Create an empty private GitHub repository.
5. Add the remote and push only after the history review is complete.

## Another Windows computer

1. Install Git.
2. Install standard 64-bit Python 3.12 from python.org with Tcl/Tk enabled.
3. Clone the repository.
4. Open a terminal in the cloned folder.
5. Run:

   ```text
   setup-context-palette.bat
   ```

6. Start:

   ```text
   run-context-palette.bat
   ```

The setup script creates `.venv`, copies safe local-data templates when needed, creates the snapshot directory, verifies Tkinter, and runs tests.

## Shared versus local data

### Shared through Git

- Source code and tests.
- Documentation.
- `data/actions.json`: reviewed portable actions suitable for every computer.
- `data/cheatsheets`: reviewed shared cheat sheets.
- `data/command_surface.json`: reviewed shared global quick-action groups.
- `data/layouts` except snapshots: reviewed portable example layouts.
- `data/*.example.json`: initial local-data templates.

### Local to each computer

- `data/inbox.json`: captured content.
- `data/local_actions.json`: personal or machine-specific actions.
- `data/local_command_surface.json`: personal or machine-specific quick-action groups.
- `data/palette.json`: pins, focus context, and per-PC slots.
- `data/layouts/snapshots/`: window titles, paths, URLs, and monitor layouts.
- `.venv`: the local Python environment.

## Portable paths

Shared actions should avoid absolute user paths. Supported environment placeholders include:

```text
%PROJECT_ROOT%
%USERPROFILE%
%LOCALAPPDATA%
%APPDATA%
%PROGRAMFILES%
```

Example:

```json
{
  "type": "launch_app",
  "value": "%LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe",
  "arguments": ["%PROJECT_ROOT%"],
  "working_directory": "%PROJECT_ROOT%"
}
```

If an application is installed differently on each computer, keep that action in `data/local_actions.json` instead.

## Sharing an action intentionally

New Inbox, snapshot, and cheat-sheet promotion actions are written to `data/local_actions.json` by default.

To share one across computers:

1. Review it for private URLs, IDs, paths, names, and captured content.
2. Replace machine paths with portable placeholders.
3. Move the reviewed action object into `data/actions.json`.
4. Give it a stable unique ID.
5. Run tests and manually test it on another computer.
6. Commit it as an intentional shared action.

## AI-assisted development

Point any coding assistant to the repository root. The root `AGENTS.md` tells assistants which architecture, product, safety, testing, and data-ownership documents to read.

Ask assistants to:

- preserve ignored runtime files;
- never copy local data into tracked examples automatically;
- run the full test suite;
- update Architecture, Decisions, Help, and Backlog when behavior changes;
- show `git status` before committing;
- never push without explicit approval.

## GitHub Actions

`.github/workflows/tests.yml` runs the unit suite on Windows with Python 3.12 for pushes and pull requests. This verifies portable code paths but does not replace manual testing of global hotkeys, Tk focus, application launching, window placement, and multi-monitor behavior.

## Suggested daily workflow

```text
git pull
setup-context-palette.bat  (first time only, or after environment loss)
develop and test
git status
git add reviewed source/config only
git commit
git push
```

Never resolve Git conflicts in personal runtime JSON by committing the files. They should remain ignored and local.
