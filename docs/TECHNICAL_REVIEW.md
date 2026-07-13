# Technical Review

Date: 2026-07-13

## Conclusion

Context Palette has a sound prototype architecture and does not need a rewrite. The standard-library boundary, constrained action model, callback-injected effects, local data ownership, and automated domain tests are good foundations for a portable Windows tool.

The main technical risk is concentrated UI orchestration. `launcher.py` still owns the main window plus several secondary windows and dialogs. The safest path is incremental extraction around existing boundaries while preserving the tested action and persistence formats.

## Strengths

- No mandatory third-party runtime dependency.
- No arbitrary shell-command action type.
- Domain behaviour is separated into actions, contexts, command-surface configuration, Inbox, cheat sheets, palette state, single-instance coordination, hotkeys, and window layouts.
- External effects are injected into action execution where practical, which keeps URL building, transformations, and dispatch testable.
- Shared configuration and ignored runtime/personal data have explicit ownership rules.
- The application has broad unit coverage for its non-visual behaviour.

## Findings and priorities

### High: make JSON writes resilient

Actions, Inbox items, palette state, and snapshots currently write JSON directly to their destination. An interrupted write can damage the complete file. Introduce one standard-library persistence helper that writes a temporary sibling file, flushes it, and atomically replaces the destination. Add recovery or backup guidance before expanding authoring features.

### High: add a minimal Windows UI smoke test

Unit tests cover domain behaviour but do not construct and close the complete Tk application. Add a Windows-only smoke test or repeatable diagnostic mode that builds the launcher with temporary data and immediately closes it. Keep manual verification for focus, global hotkeys, tooltips, monitor placement, and external application opening.

### Medium: continue splitting `launcher.py`

The UI construction is now divided into header, results/command surface, shortcuts, workspace, and footer methods. Tooltip behaviour lives in `tooltips.py`. A later maintenance pass should move Help, Inbox, Draft editor/creator, and Cheat Sheet windows into one or more focused UI modules. Do this mechanically; do not introduce a UI framework or redesign the screens during extraction.

### Medium: make action input/output effects explicit

`execute_action` remains understandable, but its branches implicitly determine clipboard reads, clipboard writes, workspace output, prompts, and external opening. Before safe action sequences or clipboard transactions are added, define and test explicit effect metadata or a small execution-result model. Avoid a class hierarchy until multiple real action types need it.

### Medium: normalize persistence and error handling

Several modules repeat JSON loading/writing and UI error-dialog patterns. Consolidate only the stable common parts: safe JSON replacement, schema-root validation, and presentation of domain errors. Keep module-specific validation close to its domain.

### Low: improve automated quality checks

The current `unittest`, `compileall`, and `git diff --check` checks are useful. A lightweight standard-library-compatible lint/type policy can be considered later, but it should not become a work-PC runtime dependency.

## Completed in this review

- Extracted widget and list-row tooltip implementations from `launcher.py` into `tooltips.py`.
- Split the main UI construction into focused methods without changing layout or behaviour.
- Added case-insensitive duplicate action-ID validation within and across shared/local files.
- Prevented appending an action whose ID already exists with different casing.
- Added regression tests for the new integrity checks.

## Recommended refactoring order

1. Add atomic JSON persistence and tests.
2. Add a Windows launcher construction/close smoke test.
3. Extract secondary windows from `launcher.py` one family at a time.
4. Define clipboard and workspace effects before implementing transactions and sequences.
5. Reassess only after those capabilities have real usage feedback.

This order improves reliability and maintainability without delaying product learning or replacing working code for stylistic reasons.
