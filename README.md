# Context Palette

Context Palette is a portable Windows launcher for finding, running, and organizing reusable actions around the work context that matters now. It is built with Python and Tkinter, runs without administrator rights, and keeps configuration in inspectable local files.

The application is under active development. Captured, harvested, configured,
and AI-proposed actions become permanent Active actions as soon as the user
confirms creation; Archived actions remain outside normal retrieval. See
[MVP](docs/MVP.md) for the exact implementation boundary.

## What it does today

- Opens instantly from a resident process with `F9` or `Ctrl+Alt+P`.
- Searches actions by name, tag, context, type, state, and content.
- Keeps five global pinned slots and four slots for the selected focus context.
- Runs the constrained, allow-listed [standard action types](docs/ACTION_TYPES.md)
  without an arbitrary shell-command action.
- Pastes Windows or generic credentials without storing passwords in action JSON.
- Provides compact, fully configurable Quick-action groups and ordered menus.
- Configures My configuration or Built-in actions, contexts, groups, and menu items through
  a guided window without exposing technical IDs.
- Captures clipboard material into an Inbox and converts it into permanent actions.
- Supports attended, schema-validated AI proposals for selected action types.
- Searches cheat sheets and promotes entries to permanent actions.
- Loads stored AI prompt templates into Input / Output from a compact quick-action menu.
- Finds configured local Work Item folders, filters them by text, project code,
  and personal tags, and opens an exact matching workbook or folder fallback.
- Creates a Work Item folder and exact-name workbook from one configured local
  generic `.xlsx` template, using an editable suggested name.
- Sends the current Input / Output text to columns A–D of a selected Work
  Item workbook's `Inbox` sheet, creating that sheet when necessary.
- Copies the one exact Windows file path in Input / Output into the selected
  Work Item folder without replacing an existing file.
- Stores personal data locally and writes application-managed JSON atomically.

## Requirements

- Windows 10 or Windows 11.
- Python 3.12 with Tcl/Tk support.
- A user-writable folder; administrator rights are not required.

The application primarily uses the Python standard library and Tkinter. Its
in-app documentation viewer uses pinned Markdown and HTML-rendering libraries;
`setup-context-palette.bat` installs the exact declared versions into the local
`.venv`.

## Quick start

From the repository root:

```powershell
.\develop-context-palette.bat
.\run-context-palette.bat
```

`develop-context-palette.bat` is the single development entry point. It creates
or repairs this computer's `.venv`, installs declared dependencies, initializes
missing personal data from safe examples, and runs the complete project check.

## Developing on multiple computers

Commit and synchronize the repository, but never copy or synchronize `.venv`.
Both virtualenv and Conda environments contain machine-specific executables and
paths. Each computer should install the Python family declared in
[`.python-version`](.python-version), then run:

```powershell
git pull
.\develop-context-palette.bat
```

The tracked `.python-version`, `requirements.txt`, and setup scripts are the
portable environment recipe. The ignored `.venv` is a disposable local result.
Setup detects an environment from another repository location, an unavailable
base installation, or the wrong Python family. It preserves a failed environment
as `.venv-unusable*` and recreates it only after a compatible base Python can
run and validate the repair path. If neither Python can launch, setup leaves
`.venv` untouched and asks for a normal Windows retry or Python repair.
Personal Context Palette data lives outside `.venv` and is not removed during
repair. Existing environments are adopted by writing an ignored
repository-location marker on their first successful setup.
See
[Multi-PC development](docs/MULTI_PC_DEVELOPMENT.md) for the complete workflow.

Setup finds Python through the `py` launcher, `PATH`, and the standard
python.org per-user and system installation folders. For a custom installation,
set `CONTEXT_PALETTE_PYTHON` to the full `python.exe` path before running setup:

```powershell
$env:CONTEXT_PALETTE_PYTHON = "D:\Tools\Python312\python.exe"
.\develop-context-palette.bat
```

For first-time application-only setup, `setup-context-palette.bat` remains
available and includes the test suite.

For project-aware Python commands, use `.\python-context-palette.bat` instead
of invoking `.venv\Scripts\python.exe` directly. The wrapper makes the
`src\context_palette` package available automatically; for example:

```powershell
.\python-context-palette.bat -m unittest tests.test_actions
```

After the application starts:

1. Press `F9` to capture selected text and show the palette. Use `Ctrl+Alt+P` as the fallback shortcut.
2. Type in **Find**, select an action, and press `Enter`.
3. Choose a **Focus** context to change slots 6–9.
4. Choose **Configure**, or press `Ctrl+,`, to add personal actions, contexts,
   or Quick actions. **Manage focuses…** in the Focus selector opens the
   relevant context tab directly.
5. Use **Capture** when material should enter the Inbox before becoming an action.

Configure supports adding, editing, deleting, and ordering actions, contexts,
Quick-action groups, and menu items. Normal user records default to **My
configuration**, which stays on this PC. **Built-in** is the starter
configuration tracked through Git and is intended for deliberate developer
changes.

Close, `Esc`, and **Hide** keep the process resident. **Quit** stops it.

## Core model

```text
Capture or configure → Confirm → Active → Archived
```

Every action belongs to the virtual **General** root. An action can additionally
belong to one or more specific contexts and have any number of reusable tags:

```text
General (all actions)
├── Specific contexts (focused workspaces)
└── Tags (independent discovery filters)
```

Creation and editing are permanent after confirmation. Context Palette keeps
atomic backups, but the user owns the consequences of shared or machine-specific
configuration changes.

## Configuration and data ownership

Portable, reviewed examples are tracked:

| Path | Purpose |
| --- | --- |
| `data/actions.json` | Built-in starter actions |
| `data/contexts.json` | Built-in context definitions; currently only Developing Context Palette |
| `data/command_surface.json` | Built-in Quick-action button records |
| `data/cheatsheets/*.json` | Shared reference sheets |

Personal and runtime files are ignored by Git:

| Path | Purpose |
| --- | --- |
| `data/local_actions.json` | Personal or machine-specific actions |
| `data/local_contexts.json` | Personal contexts |
| `data/local_command_surface.json` | Personal Quick-action button records |
| `data/inbox.json` | Captured material |
| `data/palette.json` | Focus, pins, and per-machine slot choices |
| `data/context-palette.log*` | Bounded local diagnostics |

Choose **Configure**, or press `Ctrl+,`, to open the complete guided
configuration workspace. The
JSON guides are intended for advanced editing, review, and automation:

- [Action types](docs/ACTION_TYPES.md)
- [Context configuration](docs/CONTEXT_CONFIGURATION.md)
- [Right-side button configuration](docs/COMMAND_SURFACE_CONFIGURATION.md)
- [Cheat-sheet format](docs/CHEATSHEET_FORMAT.md)
- [Complete file-based configuration](docs/CONFIGURE_WITH_FILES.md)

Never publish runtime files without a deliberate privacy review.

## Verification

Run the complete local check:

```powershell
.\check-context-palette.bat
```

It validates shared and personal configuration, compiles the source, and runs all unit tests. See [Testing](docs/TESTING.md) for targeted commands and manual Windows checks.

## External integration

The supported external bridge can show the resident palette and optionally select a context or search term:

```powershell
.\integrations\Invoke-ContextPalette.ps1 -Context "Database" -Search "SQL"
```

It cannot execute an action. See [Power Automate Desktop integration](integrations/README.md) for the protocol boundary and example.

## Documentation

Start with the [documentation index](docs/README.md).

- Users: [Help](docs/HELP.md)
- Contributors: [Contributing](CONTRIBUTING.md), [Change guide](docs/CHANGE_GUIDE.md),
  and [Development process](docs/DEVELOPMENT_PROCESS.md)
- Architects: [Architecture](docs/ARCHITECTURE.md), [decisions](docs/DECISIONS.md), and [product vision](docs/PRODUCT_VISION.md)
- Planning: [MVP](docs/MVP.md), [roadmap](docs/ROADMAP.md), and [backlog](BACKLOG.md)
- History: [Changelog](CHANGELOG.md)

AI coding agents must also follow [AGENTS.md](AGENTS.md).

## Current boundaries

Context Palette does not currently provide arbitrary shell actions, unattended action execution, automatic context switching, safe multi-action sequences, clipboard restoration transactions, rich clipboard/image actions, or generic browser-tab/document restoration. Those items are proposals or future work unless the roadmap says otherwise.

## License

No license has been selected. Treat the repository as private unless the owner explicitly chooses and adds a license.
