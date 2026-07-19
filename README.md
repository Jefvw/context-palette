# Context Palette

Context Palette is a portable Windows launcher for finding, running, and organizing reusable actions around the work context that matters now. It is built with Python and Tkinter, runs without administrator rights, and keeps configuration in inspectable local files.

The application is under active development. It already supports the complete Capture → Draft → Test → Refine → Trusted lifecycle, but some longer-term workflow capabilities remain proposals. See [MVP](docs/MVP.md) for the exact implementation boundary.

## What it does today

- Opens instantly from a resident process with `F9` or `Ctrl+Alt+P`.
- Searches actions by name, technology, task, context, type, state, and content.
- Keeps five global pinned slots and four slots for the selected focus context.
- Runs thirteen constrained action types without an arbitrary shell-command action.
- Pastes Trusted Windows or generic credentials without storing passwords in action JSON.
- Provides compact, configurable right-side buttons for repeated actions.
- Configures personal actions, contexts, and buttons through a guided window.
- Captures clipboard material into an Inbox and converts it into Draft actions.
- Supports attended, schema-validated AI proposals for selected action types.
- Searches cheat sheets and promotes entries to Draft actions.
- Stores personal data locally and writes application-managed JSON atomically.

## Requirements

- Windows 10 or Windows 11.
- Python 3.12 with Tcl/Tk support.
- A user-writable folder; administrator rights are not required.

The application uses the Python standard library. `requirements.txt` intentionally contains no runtime packages.

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
base installation, or the wrong Python family; it preserves that environment as
`.venv-unusable*` and recreates it. Personal Context Palette data lives outside
`.venv` and is not removed during repair. Existing environments are adopted by
writing an ignored repository-location marker on their first successful setup.
See
[Multi-PC development](docs/MULTI_PC_DEVELOPMENT.md) for the complete workflow.

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
4. Open **Configure** to add personal actions, contexts, or right-side buttons.
5. Use **Capture** when material should enter the Inbox before becoming an action.

Close, `Esc`, and **Hide** keep the process resident. **Quit** stops it.

## Core model

```text
Capture → Draft → Test → Refine → Trusted
```

Actions also have searchable facets:

```text
Technology → Task → Context → Action
```

`Trusted` records an explicit user review; it is not a security sandbox or a guarantee that an external target still exists.

## Configuration and data ownership

Portable, reviewed examples are tracked:

| Path | Purpose |
| --- | --- |
| `data/actions.json` | Shared actions |
| `data/contexts.json` | Shared context definitions |
| `data/command_surface.json` | Shared right-side button groups |
| `data/cheatsheets/*.json` | Shared reference sheets |

Personal and runtime files are ignored by Git:

| Path | Purpose |
| --- | --- |
| `data/local_actions.json` | Personal or machine-specific actions |
| `data/local_contexts.json` | Personal contexts |
| `data/local_command_surface.json` | Personal right-side buttons |
| `data/inbox.json` | Captured material |
| `data/palette.json` | Focus, pins, and per-machine slot choices |
| `data/context-palette.log*` | Bounded local diagnostics |

Use **Configure** for ordinary personal configuration. The JSON guides are intended for advanced editing, review, and automation:

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
- Contributors: [Contributing](CONTRIBUTING.md) and [Development process](docs/DEVELOPMENT_PROCESS.md)
- Architects: [Architecture](docs/ARCHITECTURE.md), [decisions](docs/DECISIONS.md), and [product vision](docs/PRODUCT_VISION.md)
- Planning: [MVP](docs/MVP.md), [roadmap](docs/ROADMAP.md), and [backlog](BACKLOG.md)
- History: [Changelog](CHANGELOG.md)

AI coding agents must also follow [AGENTS.md](AGENTS.md).

## Current boundaries

Context Palette does not currently provide arbitrary shell actions, unattended action execution, automatic context switching, safe multi-action sequences, clipboard restoration transactions, rich clipboard/image actions, or generic browser-tab/document restoration. Those items are proposals or future work unless the roadmap says otherwise.

## License

No license has been selected. Treat the repository as private unless the owner explicitly chooses and adds a license.
