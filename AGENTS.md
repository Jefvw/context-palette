# AI Collaboration Guide

This repository is intentionally prepared for collaboration with Codex and other AI coding assistants.

## Read first

Before changing code, read:

1. `docs/ARCHITECTURE.md` — current implementation and boundaries.
2. `docs/PRODUCT_VISION.md` — durable product direction.
3. `docs/MVP.md` — current agreed scope.
4. `docs/DECISIONS.md` — chronological rationale.
5. `BACKLOG.md` — planned work.

Detailed development guidance also exists in `docs/AGENTS.md` and `docs/DEVELOPMENT_PROCESS.md`.

## Product constraints

- Target Windows without administrator rights.
- Keep the application portable and fast.
- Prefer Python standard library and Tkinter.
- Do not introduce a dependency without verifying portability and explaining why it is necessary.
- Do not implement arbitrary shell-command execution.
- Keep actions constrained, previewable, and testable.
- Preserve the Capture -> Draft -> Test -> Refine -> Trusted lifecycle.

## Data ownership

Shared, reviewable examples belong in tracked files such as `data/actions.json` and `data/*.example.json`.

Never commit personal/runtime data:

- `data/inbox.json`
- `data/local_actions.json`
- `data/palette.json`
- `data/layouts/snapshots/`

Snapshots can contain window titles, executable paths, URLs, and other private working context.

Do not move local user data into tracked examples without explicit user approval and a privacy review.

## Development commands

From the repository root:

```powershell
.\setup-context-palette.bat
.\.venv\Scripts\python.exe -m unittest discover tests
.\run-context-palette.bat
.\stop-context-palette.bat
```

## Change rules

- Inspect existing changes before editing; they may be user-owned.
- Keep changes focused and update tests.
- Update `docs/ARCHITECTURE.md` when implementation structure changes.
- Add a dated entry to `docs/DECISIONS.md` for important choices.
- Update `docs/HELP.md` for user-visible behavior.
- Update README, MVP, and Backlog where appropriate.
- Do not rewrite Git history, delete user data, push, or publish without explicit authorization.

## Completion checks

Before handing off:

1. Run all tests.
2. Run `git diff --check`.
3. Confirm runtime/personal files are not staged.
4. Clearly separate automated verification from manual Windows UI verification.
