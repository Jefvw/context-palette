# Technical Review

Date: 2026-07-13

This is a dated review, not the current architecture source of truth. See [Architecture](ARCHITECTURE.md) for current behavior. Status notes below were updated on 2026-07-18; the original rationale remains useful.

## Conclusion

Context Palette has a sound prototype architecture and does not need a rewrite. The standard-library boundary, constrained action model, callback-injected effects, local data ownership, and automated domain tests are good foundations for a portable Windows tool.

The main technical risk is concentrated UI orchestration. `launcher.py` still owns the main window plus several secondary windows and dialogs. The safest path is incremental extraction around existing boundaries while preserving the tested action and persistence formats.

## Strengths

- No mandatory third-party runtime dependency.
- No arbitrary shell-command action type.
- Domain behaviour is separated into actions, contexts, command-surface
  configuration, Inbox, cheat sheets, palette state, single-instance
  coordination, and hotkeys.
- External effects are injected into action execution where practical, which keeps URL building, transformations, and dispatch testable.
- Shared configuration and ignored runtime/personal data have explicit ownership rules.
- The application has broad unit coverage for its non-visual behaviour.

## Findings and priorities

### Completed: make JSON writes resilient

Application-managed JSON now uses `persistence.py` to flush a temporary sibling, preserve the prior destination as `.bak`, and atomically replace the destination. The configuration checker reuses domain loaders and validates cross-file references.

### Completed: add a minimal Windows UI smoke test

The Windows-only suite now constructs the complete Tk application with
temporary data and closes it through the normal shutdown path. The test
isolates global-hotkey and single-instance operating-system boundaries so it
cannot claim those integrations during a test run. Manual verification remains
necessary for focus, global hotkeys, tooltips, monitor placement, and external
application opening.

### Medium: continue splitting `launcher.py`

The UI construction is now divided into header, results/command surface, shortcuts, workspace, and footer methods. Tooltip behaviour lives in `tooltips.py`; Help and Cheat Sheet windows now have focused modules. A later maintenance pass should move Inbox and Draft editor/creator windows into one or more focused UI modules. Do this mechanically; do not introduce a UI framework or redesign the screens during extraction.

### Medium: make action input/output effects explicit

`execute_action` remains understandable, but its branches implicitly determine clipboard reads, clipboard writes, workspace output, prompts, and external opening. Before safe action sequences or clipboard transactions are added, define and test explicit effect metadata or a small execution-result model. Avoid a class hierarchy until multiple real action types need it.

### Partly completed: normalize persistence and error handling

Safe JSON replacement is centralized. Module-specific schema validation remains close to each domain, which is intentional. Presentation of validation errors can still be made more consistent as secondary windows are extracted.

### Low: improve automated quality checks

The current `unittest`, `compileall`, and `git diff --check` checks are useful. A lightweight standard-library-compatible lint/type policy can be considered later, but it should not become a work-PC runtime dependency.

## Completed in this review

- Extracted widget and list-row tooltip implementations from `launcher.py` into `tooltips.py`.
- Extracted the Cheat Sheet secondary window into `cheat_sheet_window.py`
  without changing its behavior.
- Split the main UI construction into focused methods without changing layout or behaviour.
- Added case-insensitive duplicate action-ID validation within and across shared/local files.
- Prevented appending an action whose ID already exists with different casing.
- Added regression tests for the new integrity checks.

## Recommended refactoring order

1. Extract secondary windows from `launcher.py` one family at a time.
2. Define clipboard and workspace effects before implementing transactions and sequences.
3. Reassess only after those capabilities have real usage feedback.

This order improves reliability and maintainability without delaying product learning or replacing working code for stylistic reasons.
