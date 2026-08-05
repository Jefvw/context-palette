# Backup and restore plan

Status: Phase 1 data foundations and Phase 2 aggregate validation were
implemented on 2026-08-04. Phase 3 deterministic backup creation and Phase 4
UI-independent restore core were implemented on 2026-08-05. No Configure UI,
selective export/import, merge, path remapping, or mutating restore CLI is
implemented.

The primary goal is reliable disaster recovery for Context Palette
configuration. Selective, portable export/import is related but remains a
later concern because it needs merge, identity-conflict, and path-remapping
policy that exact backup/restore does not.

## Executive recommendation

Keep the existing standard-library JSON persistence. Phases 1 through 4
complete the backup and restore-core foundations required before restore UI:

1. one catalog of every application-owned data asset and its privacy/ownership
   policy (implemented);
2. one aggregate configuration snapshot and validator for live or safely
   staged `AppDataPaths` sources (implemented and used by backup); and
3. one recoverable multi-file restore transaction with a journal and automatic
   rollback (implemented).

A database is not recommended. The present data volume is small, JSON is
inspectable and portable, and the hard restore problems are cross-file
references, external machine paths, privacy scope, and crash recovery. Moving
the same concepts into SQLite would not remove those problems and would add a
migration and operational boundary to a lightweight portable application.

## Readiness review

| Area | Current state | Assessment |
| --- | --- | --- |
| Individual file writes | Reentrant mutation gate plus temporary sibling, flush, `.bak`, and atomic replace | Strong foundation |
| Domain loaders | Validate most fields and local invariants | Strong foundation |
| Aggregate validation | Immutable snapshot loads live or backup-staged structured assets and reports hard/soft references, portability, and legacy forms | Phases 2 and 3 complete |
| In-memory reload | Replaces active configuration only after successful loading | Useful model for post-restore reload |
| Data-file inventory | Immutable central paths and declarative policies are implemented in `data_catalog.py` | Phase 1 complete |
| Schema evolution | Logical per-asset version 1 is catalogued; JSON files still have no general persisted version field | Later compatibility work remains |
| Multi-file consistency | Backup and restore use the in-process gate and strong staged fingerprints; restore writes a durable independent recovery archive and journal before replacement | Core implemented; UI must remain in-process |
| Portability | Stable IDs help; some records contain absolute paths or external resources | Must be reported, not silently rewritten |
| Privacy | Catalog policy drives payloads and restore plans report only operational identities, sensitive categories, and safe warnings | Tkinter restore/backup UX remains future work |

## Backup and export are different operations

### Backup/restore

- Preserves stable IDs and exact records.
- Replaces the selected scope rather than merging it.
- Is intended primarily for the same application/data-model generation.
- Includes machine-local paths as configured and reports them during restore.
- Creates a recovery snapshot of the current state before replacing anything.

### Export/import — later and optional

- Selects individual Actions, Contexts, Quick actions, or knowledge records.
- Merges into an existing installation.
- Needs duplicate-ID handling, dependency closure, path remapping, and a
  detailed preview.
- Must never be implemented as a differently labelled destructive restore.

Version 1 should implement backup/restore only.

## Foundation 1: central data-asset catalog

Implemented in the small UI-independent `data_catalog.py` module with two
concepts.

### `AppDataPaths`

A single immutable object derives every known path from the application root
or an explicit data directory. `main.py` and configuration checking construct
it from the project root. Normal launcher startup receives that object; a
compatibility adapter derives it from the existing Actions directory for direct
callers, and the launcher no longer constructs Work Item filenames itself.

### `DataAssetSpec`

One frozen declarative record exists per data asset or narrow excluded runtime
pattern:

| Property | Purpose |
| --- | --- |
| `asset_id` | Stable manifest identity independent of filename |
| `relative_path` or constrained glob | Location below the application root |
| `ownership` | Built-in, personal, machine-local, captured content, or derived |
| `required` | Whether absence is valid |
| `sensitivity` | Configuration, private paths, captured content, or diagnostics |
| `backup_policy` | Core, complete-only, optional, or excluded |
| `schema_version` | Version understood by the owning loader/adapter |
| `validator` | Domain loader binding is owned by the aggregate snapshot service |

The catalog is now the source of path, ownership, sensitivity, required-status,
and backup-policy truth. Current startup, aggregate validation, and configuration
checking consume its paths; backup, restore, diagnostics counts, and setup
initialization can consume the same boundary as their phases are implemented.
It contains no user values and inspects no filesystem, external Work Item root,
or credential store.

The catalog declares logical schema version 1 for current structured assets
without rewriting any JSON file. Future formats should persist explicit
top-level schema versions and provide focused migrations rather than inferring
formats from application age.

## Foundation 2: aggregate configuration snapshot

Implemented in the pure `configuration_snapshot.py` service. It loads an
`AppDataPaths` source into an immutable `ConfigurationSnapshot` and returns a
structured `SnapshotValidationReport`. Each asset loads independently, allowing
partial diagnostic results without hiding unrelated state.

It reuses current domain loaders and owns these aggregate checks:

- all Action, Context, palette, command-surface, Inbox, Work Item source,
  metadata, settings, and cheat-sheet files are structurally valid;
- stable identities are unique at their documented scope;
- all hard Action references resolve;
- Built-in records never depend on personal records;
- palette Focus and context-slot names are classified as current, canonical,
  or preserved historical references;
- Work Item metadata and Quick-action identities reference known sources, with
  unavailable items reported as soft warnings;
- absolute or external paths are listed as portability warnings without
  exposing them in general diagnostics;
- legacy formats are identified so a later restore can migrate deliberately.

Stored Archived Actions are retained but cannot satisfy executable references.
Collections preserve Built-in/personal ownership and are defensively frozen.
Managed text is classified by presence only, excluded assets are not read, and
external resources are never probed. `configuration_check.py` is now a
presentation/CLI compatibility adapter over the service instead of maintaining
a second partial inventory. Backup and restore create and validate private
staged `AppDataPaths` trees; restore first subjects hostile ZIP input to strict
catalog, path, header, type, size, CRC, and digest checks.

## Backup archive version 1 (implemented 2026-08-05)

`backup.py` uses Python's standard `zipfile`, `hashlib`, and `json` modules. The
archive is a data package, not a copy of the whole repository. `backup_cli.py`
provides the service-level command; it is not connected to the launcher.

Suggested layout:

```text
context-palette-backup-2026-08-04T120000Z.zip
├── manifest.json
└── payload/
    └── data/
        ├── actions.json
        ├── contexts.json
        ├── command_surface.json
        ├── local_actions.json
        ├── local_contexts.json
        ├── local_command_surface.json
        ├── palette.json
        ├── inbox.json
        ├── local_work_item_sources.json
        ├── local_work_item_metadata.json
        ├── local_work_item_settings.json
        └── cheatsheets/...
```

The manifest should contain only operational metadata:

```json
{
  "format": "context-palette-backup",
  "format_version": 1,
  "data_model_version": 1,
  "created_at": "2026-08-04T12:00:00Z",
  "scope": "complete-configuration",
  "entries": [
    {
      "asset_id": "personal-actions",
      "path": "payload/data/local_actions.json",
      "schema_version": 1,
      "size": 1234,
      "sha256": "..."
    }
  ]
}
```

Do not put source-computer absolute paths into manifest metadata. They remain
inside the configuration files that already own them.

### Included by default

- Built-in and My configuration Actions, Contexts, and Quick actions, because
  Built-in records are user-editable and may contain deliberate changes.
- Palette state.
- Work Item source definitions, personal metadata, and creation settings.
- Cheat sheets.
- Inbox, with a clear notice that captures may contain sensitive text and an
  option to exclude it.

### Optional managed content

- `data/local_text_action_source.txt`, with an explicit content/privacy notice.

### Always excluded

- `.bak`, `.tmp`, logs, caches, `.venv`, source code, and Git metadata;
- external Action targets, Work Item folders/workbooks, and Excel templates;
- Windows Credential Manager secrets.

The archive should be described as sensitive. Standard ZIP encryption is not a
safe option in Python's standard library, and custom encryption must not be
invented. Users who require encryption should store the archive on an
OS-encrypted volume or approved encrypted backup destination until a reviewed
encryption design is justified.

Version 1 limits payloads to 256 entries, 16 MiB per entry, and 64 MiB total
uncompressed bytes. Entry order and ZIP metadata are deterministic, and
`manifest.json` is written last. Managed byte content without a logical JSON
schema omits `schema_version` from its manifest entry.

## Backup algorithm (implemented)

1. Acquire one application-level configuration mutation gate.
2. Wait for any configuration writer to finish; do not wait for unrelated
   external Work Item workbook/file operations.
3. Record size/modification fingerprints and copy only catalogued asset bytes
   into a temporary snapshot directory.
4. Recheck the source fingerprints. Abort or retry if any source changed,
   including through an external editor that does not use the application gate.
5. Load and validate the staged bytes as one aggregate snapshot.
6. Package those exact staged bytes into a temporary archive on the destination
   filesystem, hash every entry, and write the manifest last.
7. Flush and atomically replace the chosen destination.
8. Release the mutation gate and show included/excluded scope plus warnings.

Writing the manifest last ensures an interrupted temporary archive cannot be
mistaken for a complete backup. Backup must never mutate application data.

## Restore algorithm (implemented Phase 4 core)

Restore is more safety-critical than backup and should follow an inspect,
stage, validate, commit sequence.

1. Inspection acquires the mutation gate while fingerprinting overlay inputs;
   commit reacquires it and prevents new in-process Configure saves.
2. Inspect the ZIP without extraction APIs: reject absolute paths, `..`, symlinks,
   duplicate entries, unlisted assets, excessive entry counts, and configured
   size limits.
3. Validate manifest format/version, each SHA-256 digest, and declared size.
4. Stream only allow-listed entries to a temporary staging directory on the
   same volume as the application data.
5. Overlay every live optional catalogued asset omitted by version 1, including
   unmatched cheat sheets; preserve unknown live files and never infer deletion.
6. Load the staged directory into `ConfigurationSnapshot` without migration and
   run all hard and soft validation again.
7. Present a restore plan: records/files replaced, migrations, omitted categories,
   Built-in-file impact, sensitive content, unavailable paths, and warnings.
8. After confirmation, create an independent recovery archive of the current
   state and read it back through bounded validation before live mutation.
9. Write a small restore journal containing the recovery archive location and
   intended asset operations.
10. Replace each destination through a new byte-preserving
    `atomic_replace_bytes` persistence boundary that uses the same temporary
    sibling, flush, and replace guarantees as the JSON writer.
11. Verify the exact planned catalogued overlay, reload and validate the
    complete persisted configuration, then verify the overlay again. Phase 5
    connects successful commit to launcher projection reload/restart behavior.
12. If any write or reload fails, roll back every touched asset from the
    recovery archive. Keep the journal until rollback or success is confirmed.
13. On startup, first defer to an already-running launcher; otherwise detect an
    unfinished journal and complete rollback before ordinary migrations or
    configuration loading. Backup and standalone cleanup refuse while the
    journal is unresolved.

There is no universally safe file ordering because Contexts and Actions have
cross-file relationships. The recovery journal and aggregate validation are
therefore mandatory; relying on “Actions first” is insufficient.

Version 1 supports **replace** only. It does not merge arrays by ID,
delete unknown records silently, or rewrite paths automatically.

The implemented `RestorePlan` is frozen and content-free. It records archive,
manifest, and relevant-live-state fingerprints; exact catalog-controlled files
to replace or create; omitted live files preserved; Built-in impact; sensitive
categories; compatibility state; and snapshot warnings. It retains no staging
directory. Commit requires a matching immutable confirmation and separate
Built-in acknowledgement, repeats inspection/staging, then rejects changed
archive or live state.

Recovery creation deliberately does not call normal backup validation, because
an invalid or incomplete live configuration may be the reason for restoring.
The no-clobber recovery archive contains exact current bytes for all existing
backup-eligible catalogued files and fixed-path absence metadata. The excluded,
ignored, versioned restore journal records only operational paths, existence,
sizes, hashes, and the aggregate prior-state identity. Normal failures roll
back immediately and verify that identity; interruption leaves the journal for
idempotent startup rollback before cleanup or configuration loading.

## User experience

Add a **Backup and restore** page under Configure only after the core services
are tested without Tkinter.

### Backup

- Choose destination.
- Show one recommended complete-configuration scope.
- Allow explicit exclusion of Inbox and optional managed text content.
- State that referenced files, Work Item content, templates, and credential
  secrets are not included.
- Show a compact success summary and archive timestamp.

### Restore

- Choose archive.
- Inspect and validate before enabling Restore.
- Show exact replacement scope, compatibility, privacy, and portability
  warnings.
- Require confirmation for Built-in-file replacement.
- Show recovery archive location after success.
- Offer restart only if complete live reload cannot be proven safe.

## Implementation phases

### Phase 1 — data foundations (implemented 2026-08-04)

- Add `AppDataPaths` and the asset catalog.
- Move path construction in `main.py`, `launcher.py`, and configuration checking
  behind that object without changing behavior.
- Add catalog completeness tests against known application-owned data files.
- Document every asset's owner, sensitivity, and backup policy.

### Phase 2 — aggregate validation

Implemented 2026-08-04:

- Add `ConfigurationSnapshot` and structured validation results.
- Reuse every domain loader, including Work Item metadata/settings currently
  outside the complete checker.
- Make `configuration_check.py` consume the snapshot service.
- Add hard/soft reference and portability-warning tests.

### Phase 3 — backup core

Implemented 2026-08-05:

- Implement manifest models, deterministic archive creation, limits, hashes,
  and atomic destination replacement.
- Add a command-line/service-level backup path for testing; no UI yet.
- Test missing optional files, sensitive-scope exclusions, concurrent mutation
  blocking, interrupted writes, and deterministic manifests apart from time.

### Phase 4 — restore core (implemented 2026-08-05)

- Implemented archive inspection, safe streaming, staging overlay, compatibility
  checks, restore plans, recovery archive, journal, rollback, and startup
  recovery.
- Added fault injection after replacement steps and proved the original or
  restored complete snapshot survives.
- Tests cover malicious ZIP names, collisions, unexpected entries, links and
  directories, checksum/size mismatch, unknown versions, unavailable external
  paths, conservative omission, legacy classification without migration,
  confirmation, stale plans, normal rollback, and interrupted startup recovery.

### Phase 5 — Configure UI and Windows verification

- Add Backup and Restore flows backed only by the tested core services.
- Block conflicting Configure changes while either operation is active.
- Verify keyboard access, long-running feedback, cancellation before commit,
  same-machine round trip, a second path/computer, disconnected Work Item
  sources, and restart/crash recovery.
- Update Help, Architecture, Decisions, Changelog, and release notes.

### Phase 6 — optional selective export/import

Only after backup/restore is reliable, design dependency-aware selection,
duplicate-ID policies, path remapping, and merge previews. This phase is not
required to protect current configuration.

## Acceptance criteria for backup/restore

1. A backup of a valid snapshot never changes application data.
2. Every archive entry is catalogued, bounded, hashed, and represented in the
   manifest.
3. Restoring a backup recreates an equivalent logical `ConfigurationSnapshot`.
4. A failure or process interruption at any commit step leaves either the old
   complete snapshot or a recoverable journal that restores it on startup.
5. Missing external files or disconnected Work Item sources are reported
   accurately and never copied or silently rewritten.
6. Credential secrets, logs, `.bak` files, caches, and environments never enter
   the archive.
7. Inbox and managed-content privacy scope is explicit before archive creation.
8. Built-in-file replacement is visible and confirmed.
9. Full automated checks and documented manual Windows round trips pass.

## Recommended next implementation slice

Implement Phase 5 only: add Configure backup and restore flows over the tested
services, keep restore application in the launcher process so the mutation gate
can exclude Configure writes, and perform the documented Windows round trips
and interruption recovery checks. Do not add merging, path remapping, selective
import, or a cross-process mutating CLI.
