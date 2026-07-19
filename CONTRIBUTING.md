# Contributing

Context Palette welcomes focused changes that preserve its portable, constrained Windows design. Read [AGENTS.md](AGENTS.md) when using an AI coding assistant.

## Set up

Requirements are Windows and the Python family declared in `.python-version`,
with Tcl/Tk:

```powershell
.\develop-context-palette.bat
```

The development command creates or repairs the machine-local `.venv`,
initializes ignored personal files from tracked examples, verifies Tkinter, and
runs the canonical project check.

## Before changing code

1. Read the relevant sections of [Architecture](docs/ARCHITECTURE.md), [MVP](docs/MVP.md), and [Decisions](docs/DECISIONS.md).
2. Check [Backlog](BACKLOG.md) and [Roadmap](docs/ROADMAP.md) for intended scope.
3. Inspect the working tree and preserve unrelated changes.
4. Confirm whether affected data is shared or personal.

## Design constraints

- Target Windows without administrator rights.
- Prefer Python standard library and Tkinter.
- Explain and verify portability before adding a dependency.
- Never add arbitrary shell-command execution.
- Keep effects constrained, visible, previewable, and testable.
- Preserve Capture → Draft → Test → Refine → Trusted.
- Keep Tk widget access on the main thread.
- Treat loaded configuration, captured text, and AI output as untrusted data.

## Implement and test

- Keep patches focused and maintainable.
- Add or update tests for behavior changes.
- Use callback injection for external effects where practical.
- Run targeted tests while editing, then run:

```powershell
.\check-context-palette.bat
git diff --check
```

Windows UI, hotkey, clipboard, monitor, and external-application behavior may also require the manual checks in [Testing](docs/TESTING.md).

## Documentation responsibilities

Update:

- `docs/HELP.md` and `CHANGELOG.md` for user-visible behavior.
- `docs/ARCHITECTURE.md` for implementation boundaries.
- `docs/DECISIONS.md` for important choices and rationale.
- `docs/MVP.md`, `docs/ROADMAP.md`, or `BACKLOG.md` when scope changes.
- Configuration references when persisted formats change.

Do not rewrite old decision entries to make history look current. Add a newer superseding decision.

## Data and privacy

Never commit personal/runtime data:

- `data/inbox.json`
- `data/local_actions.json`
- `data/local_contexts.json`
- `data/local_command_surface.json`
- `data/palette.json`
- `data/layouts/snapshots/`
- `data/context-palette.log*`
- `*.bak` and `*.tmp`

Tracked examples must be synthetic or explicitly reviewed for sharing. Check staged files before committing.

## Commit and review

Use a short, outcome-focused commit message. A review should be able to answer:

- Is the behavior within the documented product and security boundaries?
- Are failure states understandable and recoverable?
- Are tests proportional to risk?
- Are current docs and historical rationale updated in the correct places?
- Is personal data excluded?
