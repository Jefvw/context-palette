# Backlog

This file contains actionable future work. Completed user-visible work belongs in [CHANGELOG.md](CHANGELOG.md), and ordered outcomes belong in [Roadmap](docs/ROADMAP.md).

## Now

- Complete Phase 5 of the approved [Work Items discovery plan](docs/WORK_ITEMS_PLAN.md):
  representative performance measurements and manual Windows checks on another
  computer/path. Phases 1–4 include guided private source/tag configuration.
- Perform and record the manual Windows UI/accessibility smoke test for the guided Configure workflow.
- Extract secondary Inbox and Draft views from `launcher.py` incrementally
  without changing behavior. The sheet view has been extracted.
- Refine action discovery and effect descriptions using real repeated-work feedback.
- Add focused tests for configuration-window keyboard order and validation recovery where Tk permits reliable automation.

## Next

- Extend text transformations with literal replace, line-ending cleanup, URL encoding/decoding, and additional line operations.
- Design supporting-context composition and weighted ranking while preserving explicit Focus and global search.
- Design clipboard preservation/restoration as an explicit transaction.
- Design constrained, previewable linear sequences for supported actions, paste, Tab, Enter, and bounded waits.
- Define context activation bundles only after effect preview and recovery behavior are documented.
- Continue extracting stable UI families from `launcher.py`.

## Later

- Add reusable prompted forms with field validation.
- Add rich HTML content with plain-text fallback.
- Add image/visual-asset clipboard actions.
- Add a character picker and explicit clipboard slots.
- Investigate safe browser-specific URL discovery without focus or clipboard manipulation.
- Add optional application-aware context suggestions; never switch automatically.
- Explore a packageable tray icon and optional AutoHotkey adapter.
- Design a Trusted-action external API before any unattended execution.
- Expand attended AI authoring only for types with adequate validation and review.

## Product questions

- Which action effects need a standard preview/result model before sequences are safe?
- How should supporting contexts affect ranking without making results unpredictable?
- What recovery guarantees are realistic for clipboard transactions?
- Which personal actions are frequent enough to justify new built-in types?
