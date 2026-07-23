# MVP baseline

This document defines the implemented minimum product baseline and distinguishes partial or deferred capabilities. It is a scope reference, not a future-feature list.

## Product promise

Context Palette helps a Windows user capture useful material, turn it into a
constrained permanent action after confirmation, edit any stored configuration,
and retrieve it quickly in a chosen focus context.

## Status

| Capability | Status | Current boundary |
| --- | --- | --- |
| Resident launcher and global shortcut | Implemented | `F9` primary, `Ctrl+Alt+P` fallback |
| Global search and keyboard execution | Implemented | Search stays global; fixed slots use 1–9 |
| Global pins and focus-context slots | Implemented | Pins 1–5, context slots 6–9 |
| Guided configuration | Implemented | Actions, contexts, and Quick actions use My configuration or Built-in ownership; context membership, order, defaults, and complete menus are editable without JSON |
| Confirm → Active → Archived | Implemented | Creation and editing are permanent after confirmation; archiving is represented in data but has limited UI |
| Constrained action execution | Implemented | Thirteen allow-listed types; no arbitrary shell action |
| Protected credential paste | Implemented with limitations | Exact standard Windows or generic credential target; confirmed, hotkey-originated paste only |
| Input / Output transformations | Implemented | Selection or full field; result copied |
| Cheat sheets and promotion | Implemented | Structured local JSON sheets |
| Attended AI assistance | Partial | Reviewable stored prompt templates and manual clipboard handoff; `copy_text` and `open_url` proposals only |
| Context model | Partial | General root, per-PC context-owned action membership, tags, explicit focus, preferred actions; Developing Context Palette is the only shipped specific context |
| Work Items discovery | Implemented | Bounded local discovery, main-window search/opening, and guided private source/tag configuration |
| Work Item creation | Implemented | Editable suggested name, one local generic `.xlsx` template, collision-safe folder/workbook creation, optional tags |
| Work Item Inbox | Implemented | Attended append of Input / Output to the selected exact-name `.xlsx`; creates `Inbox` and offers template-based workbook creation when missing |
| Work Item file copy | Implemented | Copies one exact absolute file path from Input / Output into the selected Work Item folder; background, collision-safe, no overwrite |
| Bulk action harvesting | Implemented | Attended local extraction of HTTP/HTTPS candidates from selected `.md`, `.txt`, `.docx`, and `.xlsx` files; review and atomic permanent creation |
| External automation | Partial by design | Show/context/search only; no action execution API |
| Clipboard transactions | Deferred | No automatic preservation/restoration |
| Safe action sequences | Deferred | No multi-step sequence language |
| Rich clipboard/image actions | Deferred | Plain-text workspace only |
| Automatic context inference | Deferred | The user chooses focus explicitly |

## Acceptance criteria

The MVP baseline is satisfied when:

1. A fresh clone can be set up on supported Windows with user-level permissions.
2. The resident palette opens, searches, and runs constrained actions predictably.
3. Actions, contexts, Quick-action groups, ordered items, defaults, and menu
   assignments can be configured without editing technical IDs.
4. Captured material can enter the Inbox and become an Active action after confirmation.
5. Active actions of every supported type can be edited and saved permanently.
6. Built-in starter data and My configuration data remain separated and recoverable from interrupted writes.
7. Invalid configuration and action inputs fail with actionable messages.
8. Automated checks pass and Windows-dependent behavior has a documented manual test.
9. Several supported documents can be harvested locally, reviewed with
   provenance and duplicate states, and committed only as explicitly selected
   permanent personal URL actions.

## Safety boundary

The MVP:

- validates every persisted action type and its fields;
- permits only HTTP/HTTPS web targets;
- validates file, folder, executable, and working-directory targets;
- does not interpret shell command strings;
- keeps the integration bridge attended;
- treats captured material and AI responses as untrusted;
- stores personal data locally in ignored files.
- stores only credential target references in actions; passwords remain in Windows Credential Manager.

## Not required for the MVP

- Installer, administrator rights, service, or mandatory tray integration.
- Application-provided speech and dedicated screen-reader conformance testing.
  Ordinary keyboard operation and clear native control labels remain required.
- Cloud synchronization or accounts.
- Arbitrary scripts, loops, conditions, or unattended workflows.
- Automatic application-aware context switching.
- Exact restoration of unsaved documents, browser history, or tab groups.
- Third-party UI or persistence frameworks.

See [Roadmap](ROADMAP.md) for proposed outcomes and [Backlog](../BACKLOG.md) for actionable tasks.
