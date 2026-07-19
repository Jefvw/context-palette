# Changelog

This project has not published a versioned release. Changes are recorded under **Unreleased** until a release process and versioning policy are chosen.

## Unreleased

### Added

- Four pinned-first Frequent passwords buttons for starting protected paste without intermediate filtering or list selection.
- Compact Passwords button beside Find for quickly filtering to protected credential actions.
- Portable multi-machine development recipe with a tracked Python version and a single setup-and-check command.
- Trusted, confirmed paste of exact generic Windows Credential Manager targets through a no-history/no-cloud clipboard item.
- Project-aware Python wrapper for reliable targeted tests, benchmarks, and module commands from the repository root, with distinct environment and source-import recovery guidance.
- Guided configuration for personal actions of every built-in type, focus contexts, context slots, and right-side buttons.
- Built-in action catalogue with examples and generated documentation.
- Capture Inbox, Draft creation, editing, explicit trust promotion, cheat-sheet promotion, and attended AI proposal review.
- Focus-context slots, global pins, configurable quick-action groups, and keyboard operation.
- Constrained URL, file, folder, application, transformation, workspace, layout, and snapshot actions.
- Atomic JSON replacement with local backups and a read-only configuration checker.
- Searchable in-app Help, local bounded diagnostics, Windows integration examples, and CI on Python 3.12.

### Changed

- Skipped redundant dependency installation when the tracked requirements declaration has not changed.
- Released tooltip objects for destroyed quick-action and password buttons whenever the surface is rebuilt.
- Allowed protected paste to resolve exact targets from both Windows Credentials and Generic Credentials.
- Unified action-value validation for guided creation and JSON loading, including rejection of invalid list-conversion modes and empty persisted values.
- Made Configure context and button tables directly operable with keyboard selection and Enter.
- Added fast, keyboard-accessible filtering to Configure → Actions across user-visible action facets.
- Preserved last-known-good contexts and right-side buttons when edited configuration files fail validation.
- Kept Focus and pin state consistent when palette persistence fails, with actionable feedback instead of an uncaught UI error.
- Added privacy-safe warnings for genuinely slow result refreshes and configuration reloads.
- Centralized quick-action primary/fallback ordering so execution, configuration, and validation cannot drift.
- Added predictable initial keyboard focus to Configure and its action, context, and button dialogs.
- Preserved last-known-good actions when an edited action file fails to reload.
- Kept Configure edit dialogs open after validation or persistence errors so entered values are not lost.
- Made quick-action mouse, keyboard, and menu routes consistently honor the configured primary action.
- Restored descriptive launcher metadata for shared Archive, Colruyt, and Python documentation actions after an accidental configuration regression.
- Made setup recover from a stale virtual environment after the project or Python installation moves, and made launch failures explain how to repair the environment.
- Refined the interface for compact buttons, consistent spacing, native focus indication, useful empty states, and non-blocking save feedback.
- Moved long-running window restore work off the Tk main thread.
- Added configuration signature checks and brief search coalescing to keep the resident hot path responsive.
- Separated reviewed shared configuration from ignored personal and machine-specific data.

### Security

- Kept credential passwords out of action JSON, previews, workspace text, logs, AI prompts, clipboard history, and cloud clipboard synchronization.
- Rejected credential-bearing and ambiguously parsed HTTP(S) action URLs across creation, loading, generation, and execution.
- Prevented stalled localhost integration clients from holding the single-instance listener indefinitely.
- Kept action execution allow-listed and rejected arbitrary shell-command actions.
- Restricted the external bridge to showing/filtering the palette; it cannot execute actions.
- Validated AI responses through a versioned schema and existing Draft constructors.

See [Decisions](docs/DECISIONS.md) for chronological rationale and [Roadmap](docs/ROADMAP.md) for planned outcomes.
