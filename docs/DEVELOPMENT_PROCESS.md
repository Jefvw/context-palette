# Development process

This guide explains how a change moves from an idea to a verified Context Palette improvement. Repository rules are in [AGENTS.md](../AGENTS.md); command details are in [Contributing](../CONTRIBUTING.md).

## 1. Establish the boundary

- Confirm current behavior in code, tests, [Architecture](ARCHITECTURE.md), and [Help](HELP.md).
- Classify the request as a bug fix, current-scope improvement, or proposal.
- Check [MVP](MVP.md), [Roadmap](ROADMAP.md), and the root [Backlog](../BACKLOG.md).
- Identify shared versus personal data before opening or changing examples.

## 2. Design the smallest safe change

Prefer constrained action types, pure domain logic with injected platform effects, existing standard-library and Tkinter patterns, explicit validation, visible effects, and Draft-first workflows. Prefer behavior-preserving extraction to broad rewrites.

Record an important or durable choice in [Decisions](DECISIONS.md) before its rationale is lost.

## 3. Implement in a focused patch

- Preserve public behavior unless the change intentionally modifies it.
- Keep Tk operations on the main thread.
- Route application-managed JSON writes through the shared persistence helper.
- Keep identifiers stable and case-insensitively unique.
- Avoid reading clipboard or external state unless the selected action requires it.
- Do not add a dependency without documenting portability, packaging, and maintenance impact.

## 4. Verify proportionally

- Add or update focused automated tests.
- Run targeted tests while iterating.
- Run `.\check-context-palette.bat` after the final code change.
- Perform relevant manual checks from [Testing](TESTING.md).
- Run `git diff --check` and inspect files for private data.

## 5. Update the right documentation

| Change | Documentation |
| --- | --- |
| User-visible behavior | `HELP.md`, root `CHANGELOG.md` |
| Module, data, thread, or security boundary | `ARCHITECTURE.md` |
| Important rationale | append to `DECISIONS.md` |
| Persisted format | relevant configuration reference |
| Scope or priority | `MVP.md`, `ROADMAP.md`, or root `BACKLOG.md` |
| Setup or test workflow | root `README.md`, `CONTRIBUTING.md`, or `TESTING.md` |

Historical decision entries are append-only. If an old decision is no longer current, add a newer decision and update the current source-of-truth documents.

## 6. Hand off clearly

State what changed, which files own the behavior, automated and manual checks, and any remaining limitations.
