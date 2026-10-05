# Documentation index

This directory separates current behavior, durable direction, historical rationale, and future work. When documents disagree, use the priority below.

## Start here

- Using the app: [Help](HELP.md) and [keyboard shortcuts](SHORTCUTS.md).
- Setting up another PC: [Multi-PC setup](MULTI_PC_DEVELOPMENT.md), including
  the optional Excel, OneNote and OCR components.
- Changing the app: [Change guide](CHANGE_GUIDE.md) and [Architecture](ARCHITECTURE.md).
- Checking a change: [Complete check](TESTING.md#complete-automated-check)
  and [manual Windows smoke test](TESTING.md#manual-windows-smoke-test).
- Checking scope or an earlier choice: [MVP](MVP.md), [Backlog](../BACKLOG.md)
  and [dated decisions](DECISIONS.md).

## Source priority

| Priority | Source | Purpose |
| --- | --- | --- |
| 1 | Code and automated tests | Executable behavior |
| 2 | `ARCHITECTURE.md` | Current technical source of truth |
| 3 | `HELP.md` | Current user behavior |
| 4 | Configuration references | Current persisted formats |
| 5 | `MVP.md`, `ROADMAP.md`, root `BACKLOG.md` | Scope and planned work |
| 6 | `PRODUCT_VISION.md`, `DECISIONS.md` | Direction and historical rationale |

## By audience

### Users

- [Help](HELP.md) — complete operation and troubleshooting.
- [Current batch UAT](UAT_CURRENT_BATCH.md) — owner acceptance record and
  optional follow-up checks.
- [Keyboard shortcuts](SHORTCUTS.md) — authoritative shortcut reference,
  also available from **More → Keyboard shortcuts** in the app.
- [Action types](ACTION_TYPES.md) — generated catalogue of supported actions.
- [Context configuration](CONTEXT_CONFIGURATION.md) — guided configuration and JSON reference.
- [Quick actions](COMMAND_SURFACE_CONFIGURATION.md) — guided configuration and JSON record reference.
- [Complete file-based configuration](CONFIGURE_WITH_FILES.md) — advanced
  editing of the related JSON files.
- [Application data model](DATA_MODEL.md) — persisted ownership, references,
  and executable asset catalogue.
- [Cheat-sheet format](CHEATSHEET_FORMAT.md) — sheet authoring and promotion.
- [Multi-PC use](MULTI_PC_DEVELOPMENT.md) — cloning and private-data boundaries.
- [OCR setup and other-PC handoff](OCR_SETUP.md) — online/offline preparation,
  use, configuration transfer, troubleshooting, and developer checks.
- [Power Automate integration](../integrations/README.md) — attended show,
  context, and search integration.

### Contributors and AI agents

- [Contributing](../CONTRIBUTING.md) — setup, change workflow, and review expectations.
- [AI collaboration guide](../AGENTS.md) — repository-specific agent constraints.
- [Model selection for AI work](MODEL_SELECTION.md) — recommendations for
  prompt writing, direct execution, and explicitly requested delegation.
- [Development process](DEVELOPMENT_PROCESS.md) — feature workflow and documentation responsibilities.
- [Change guide](CHANGE_GUIDE.md) — common modifications, owning modules, and
  focused test commands.
- [Testing](TESTING.md) — automated and manual verification.
- [Architecture](ARCHITECTURE.md) — modules, flows, storage, threading, and security.

### Product and architecture

- [MVP](MVP.md) — implemented baseline and explicit deferrals.
- [Product vision](PRODUCT_VISION.md) — durable direction; proposals are labeled.
- [Roadmap](ROADMAP.md) — ordered outcomes.
- [Backlog](../BACKLOG.md) — actionable work items.
- [UI/UX audit (2026-08-18)](UI_UX_AUDIT_2026-08-18.md) — whole-product
  screen evaluation, Tk-native visual rules, and ordered implementation batches.
- [Real-Tk UI mockups](UI_MOCKUPS.md) — inert visual baselines, review
  scenarios, reconciled layout decisions, and Windows scaling checklist.
- [Work Items discovery plan](WORK_ITEMS_PLAN.md) — implemented phases and
  remaining cross-machine verification.
- [Backup and restore plan](BACKUP_RESTORE_PLAN.md) — implemented transaction
  model and remaining manual verification.
- [Decisions](DECISIONS.md) — append-only rationale.
- [Changelog](../CHANGELOG.md) — user-visible history.
- [Technical review](TECHNICAL_REVIEW.md) and [performance audit](PERFORMANCE_AUDIT.md) — dated audits, including completed findings.

### Integration status and handovers

- [OneNote search and preview](HELP.md#find-onenote-notes) and
  [Send text to OneNote](HELP.md#send-text-to-onenote) — current user flows.
- [OneNote Send UAT](ONENOTE_SEND_UAT.md) — proposed attended acceptance;
  it requires its own exact-scope approval before live access.
- [OneNote Send UI design record](ONENOTE_SEND_UI_IMPLEMENTATION_HANDOVER.md) —
  implemented; retain as rationale, not a request to repeat the work.
- [OneNote recovery investigation](ONENOTE_ENGINE_RECOVERY_HANDOVER.md) —
  earlier engine-owner handover; inspect current engine and host status before reuse.
- [Single refreshed Excel backup](EXCEL_SINGLE_BACKUP_ENGINE_HANDOVER.md) —
  pending engine-contract work; current conversion still refuses existing backups.

Use current guides for operation and setup. Dated audits, design sketches,
decisions and verification records explain earlier states; they do not override
current behavior. A handover does not itself authorize implementation or live UAT.

## Maintenance rules

- Describe current behavior in present tense and proposals with **Proposed** or **Deferred**.
- Do not use decision history as current documentation; add a new decision when one is superseded.
- Keep the roadmap outcome-oriented and the backlog task-oriented.
- Put user-visible changes in `CHANGELOG.md`.
- Update `ARCHITECTURE.md` when module boundaries, data flow, persistence, threading, or security changes.
- `ACTION_TYPES.md` is generated from `src/context_palette/action_types.py`; update the catalogue and its tests instead of editing the Markdown by hand.
- Use repository-relative Markdown links so documentation works locally and on Git hosts.
- Shared documentation must not link to private `outputs/` files. Record their
  names or local locations as plain text; keep the evidence private.
