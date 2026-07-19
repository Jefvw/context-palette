# Changelog

This project has not published a versioned release. Changes are recorded under **Unreleased** until a release process and versioning policy are chosen.

## Unreleased

### Added

- Guided configuration for personal actions of every built-in type, focus contexts, context slots, and right-side buttons.
- Built-in action catalogue with examples and generated documentation.
- Capture Inbox, Draft creation, editing, explicit trust promotion, cheat-sheet promotion, and attended AI proposal review.
- Focus-context slots, global pins, configurable quick-action groups, and keyboard operation.
- Constrained URL, file, folder, application, transformation, workspace, layout, and snapshot actions.
- Atomic JSON replacement with local backups and a read-only configuration checker.
- Searchable in-app Help, local bounded diagnostics, Windows integration examples, and CI on Python 3.12.

### Changed

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

- Kept action execution allow-listed and rejected arbitrary shell-command actions.
- Restricted the external bridge to showing/filtering the palette; it cannot execute actions.
- Validated AI responses through a versioned schema and existing Draft constructors.

See [Decisions](docs/DECISIONS.md) for chronological rationale and [Roadmap](docs/ROADMAP.md) for planned outcomes.
