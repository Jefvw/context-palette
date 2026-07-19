# Multi-PC and GitHub Development

This guide explains how to develop and use Context Palette safely on multiple Windows computers.

## Recommended repository visibility

Use a private GitHub repository while the product and data-separation model is
still evolving. Personal data is ignored now, but earlier local Git history
must also be reviewed before the first push.

No open-source license has been selected yet. Keep the repository private, or choose and add an appropriate license before intentionally publishing it for public reuse.

## First computer: publish preparation

1. Run the complete check:

   ```powershell
   .\check-context-palette.bat
   ```

2. Confirm ignored personal files are not staged:

   ```powershell
   git status --short
   git check-ignore data\inbox.json data\local_actions.json data\local_contexts.json data\local_command_surface.json data\palette.json data\context-palette.log
   ```

3. Review the complete history for previously committed private data before pushing.
4. Create an empty private GitHub repository.
5. Add the remote and push only after the history review is complete.

## Another Windows computer

1. Install Git.
2. Read the tracked `.python-version` file and install that standard 64-bit
   Python family from python.org with Tcl/Tk enabled.
3. Clone the repository.
4. Open a terminal in the cloned folder.
5. Run:

   ```text
   develop-context-palette.bat
   ```

6. Start:

   ```text
   run-context-palette.bat
   ```

The development entry point creates or repairs `.venv`, copies safe local-data
templates when needed, verifies Tkinter, and
runs the canonical configuration, compilation, and test checks.

## Python environments and dependencies across computers

`.venv` is an isolated project environment, but it is not a portable Python installation. It contains machine-specific paths to the Python installation that created it. Do not copy, commit, or synchronize `.venv` between computers. Create it separately on every computer with `setup-context-palette.bat`.

Git transfers source files and dependency declarations; it does not transfer packages installed inside `.venv`. Installing a library on one computer therefore does not make that library available on another computer after `git pull` unless the dependency is also recorded in `requirements.txt`.

The project uses this contract:

- `.python-version`: tracked declaration of the supported Python family.
- `.venv`: ignored, disposable, and local to one computer.
- `requirements.txt`: tracked in Git and shared by every computer.
- `setup-context-palette.bat`: creates or repairs the local environment and
  installs everything declared in `requirements.txt`.
- `develop-context-palette.bat`: performs setup and then runs the complete
  project check; use this as the normal development entry point.
- Python and Tcl/Tk: installed separately on each Windows computer and used as the base for its local environment.

Context Palette currently has no third-party dependencies. `requirements.txt` is present as the shared dependency contract and contains comments only.

### Adding a third-party library

Do not add a dependency casually. First verify that it works on Windows without administrator rights, supports Python 3.12, is actively maintained, and materially improves the application. Record the rationale in the appropriate project documentation.

After choosing a dependency:

1. Install it into this project's environment, never into the global Python installation:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install package-name
   ```

2. Add the reviewed package and an explicit version to `requirements.txt`, for example:

   ```text
   package-name==1.2.3
   ```

   Do not blindly commit the complete output of `pip freeze`; it can include incidental or machine-specific packages. Record the direct dependency deliberately, and include transitive pins only when reproducibility requires them.

3. Run setup and the complete tests:

   ```powershell
   .\develop-context-palette.bat
   ```

4. Commit `requirements.txt` together with the code, tests, and documentation that require the library.
5. Push the commit.

On another computer:

```powershell
git pull --ff-only
.\develop-context-palette.bat
```

The development command installs declared dependencies into that computer's
own `.venv` and runs the complete check. Run it after any pull that changes
`.python-version`, `requirements.txt`, or the setup scripts.

Setup records the hash of the last successfully installed `requirements.txt`
inside ignored `.venv`. Unchanged development runs skip redundant package
installation. Editing `requirements.txt` or recreating `.venv` automatically
invalidates that marker; delete the marker if a manual package change needs to
be repaired without rebuilding the environment.

### Repairing or rebuilding an environment

An environment is disposable. If `.venv` was copied from another computer,
belongs to another repository location, uses the wrong declared Python family,
or points to an unavailable Python installation, run
`develop-context-palette.bat`. Setup preserves the environment under the next
available `.venv-unusable*` name and creates a fresh one. Local Context Palette
data is stored under `data`, not inside `.venv`, so rebuilding the environment
does not remove Inbox items, private actions, contexts, buttons, pins, or
local settings. Setup adopts an existing unmarked environment once, then stores an
ignored repository-location marker inside `.venv` so subsequent folder copies
are detected reliably.

Setup and application startup also remove local actions and references that
belong to deliberately retired features. These migrations are idempotent and
use the normal atomic writer, so each changed personal JSON file retains its
previous contents in the ignored adjacent `.bak` file.

## Shared versus local data

### Shared through Git

- Source code and tests.
- Documentation.
- `data/actions.json`: reviewed portable actions suitable for every computer.
- `data/contexts.json`: reviewed portable context definitions.
- `data/cheatsheets`: reviewed shared cheat sheets.
- `data/command_surface.json`: reviewed shared global quick-action groups.
- `data/*.example.json`: initial local-data templates.

### Local to each computer

- `data/inbox.json`: captured content.
- `data/local_actions.json`: personal or machine-specific actions.
- `data/local_contexts.json`: personal or work-specific contexts.
- `data/local_command_surface.json`: personal or machine-specific quick-action groups.
- `data/palette.json`: pins, focus context, and per-PC slots.
- `data/context-palette.log*`: bounded local diagnostics.
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

New Inbox and cheat-sheet promotion actions are written to
`data/local_actions.json` by default.

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
- run the complete check and relevant manual tests;
- update Architecture, Decisions, Help, Changelog, and planning documents when appropriate;
- show `git status` before committing;
- never push without explicit approval.

## GitHub Actions

`.github/workflows/tests.yml` reads `.python-version`, installs the tracked
requirements, and runs the same configuration validation, source compilation,
and unit-test phases as the local complete check on Windows for pushes and pull
requests. This verifies dependency declarations, portable code paths, and
shared configuration references but does not replace manual testing of global
hotkeys, Tk focus, application launching, window placement, and multi-monitor
behavior.

## Suggested daily workflow

```text
git pull
develop-context-palette.bat
develop and test
git status
git add reviewed source/config only
git commit
git push
```

Never resolve Git conflicts in personal runtime JSON by committing the files. They should remain ignored and local.
