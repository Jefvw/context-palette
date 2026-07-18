# Documentation index

This directory separates current behavior, durable direction, historical rationale, and future work. When documents disagree, use the priority below.

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
- [Action types](ACTION_TYPES.md) — generated catalogue of supported actions.
- [Context configuration](CONTEXT_CONFIGURATION.md) — guided configuration and JSON reference.
- [Right-side buttons](COMMAND_SURFACE_CONFIGURATION.md) — guided configuration and JSON reference.
- [Cheat-sheet format](CHEATSHEET_FORMAT.md) — sheet authoring and promotion.
- [Multi-PC use](MULTI_PC_DEVELOPMENT.md) — cloning and private-data boundaries.
- [Windows integrations](../integrations/README.md) — attended Power Automate and PowerToys integration.

### Contributors and AI agents

- [Contributing](../CONTRIBUTING.md) — setup, change workflow, and review expectations.
- [AI collaboration guide](../AGENTS.md) — repository-specific agent constraints.
- [Development process](DEVELOPMENT_PROCESS.md) — feature workflow and documentation responsibilities.
- [Testing](TESTING.md) — automated and manual verification.
- [Architecture](ARCHITECTURE.md) — modules, flows, storage, threading, and security.

### Product and architecture

- [MVP](MVP.md) — implemented baseline and explicit deferrals.
- [Product vision](PRODUCT_VISION.md) — durable direction; proposals are labeled.
- [Roadmap](ROADMAP.md) — ordered outcomes.
- [Backlog](../BACKLOG.md) — actionable work items.
- [Decisions](DECISIONS.md) — append-only rationale.
- [Changelog](../CHANGELOG.md) — user-visible history.
- [Technical review](TECHNICAL_REVIEW.md) and [performance audit](PERFORMANCE_AUDIT.md) — dated audits, including completed findings.

## Maintenance rules

- Describe current behavior in present tense and proposals with **Proposed** or **Deferred**.
- Do not use decision history as current documentation; add a new decision when one is superseded.
- Keep the roadmap outcome-oriented and the backlog task-oriented.
- Put user-visible changes in `CHANGELOG.md`.
- Update `ARCHITECTURE.md` when module boundaries, data flow, persistence, threading, or security changes.
- `ACTION_TYPES.md` is generated from `src/context_palette/action_types.py`; update the catalogue and its tests instead of editing the Markdown by hand.
- Use repository-relative Markdown links so documentation works locally and on Git hosts.
