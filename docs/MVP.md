# MVP baseline

This document defines the implemented minimum product baseline and distinguishes partial or deferred capabilities. It is a scope reference, not a future-feature list.

## Product promise

Context Palette helps a Windows user capture useful material, turn it into a constrained action, test and refine it, mark it Trusted explicitly, and retrieve it quickly in a chosen focus context.

## Status

| Capability | Status | Current boundary |
| --- | --- | --- |
| Resident launcher and global shortcut | Implemented | `F9` primary, `Ctrl+Alt+P` fallback |
| Global search and keyboard execution | Implemented | Search stays global; fixed slots use 1–9 |
| Global pins and focus-context slots | Implemented | Pins 1–5, context slots 6–9 |
| Guided personal configuration | Implemented | All built-in action types; shared records read-only |
| Capture → Draft → Test → Refine → Trusted | Implemented | Trust is explicit; archiving is represented in data but has limited UI |
| Constrained action execution | Implemented | Thirteen allow-listed types; no arbitrary shell action |
| Protected credential paste | Implemented with limitations | Exact standard Windows or generic credential target; Trusted, confirmed, hotkey-originated paste only |
| Input / Output transformations | Implemented | Selection or full field; result copied |
| Cheat sheets and promotion | Implemented | Structured local JSON sheets |
| Attended AI assistance | Partial | Manual clipboard handoff; `copy_text` and `open_url` proposals only |
| Context model | Partial | General root, multiple specific memberships, tags, explicit focus, preferred actions; no supporting-context composition or activation bundle |
| Work Items discovery | Implemented | Bounded local discovery, main-window search/opening, and guided private source/tag configuration |
| External automation | Partial by design | Show/context/search only; no action execution API |
| Clipboard transactions | Deferred | No automatic preservation/restoration |
| Safe action sequences | Deferred | No multi-step sequence language |
| Rich clipboard/image actions | Deferred | Plain-text workspace only |
| Automatic context inference | Deferred | The user chooses focus explicitly |

## Acceptance criteria

The MVP baseline is satisfied when:

1. A fresh clone can be set up on supported Windows with user-level permissions.
2. The resident palette opens, searches, and runs constrained actions predictably.
3. Personal actions, contexts, and right-side buttons can be configured without editing technical IDs.
4. Captured material can enter the Inbox and become a reviewable Draft.
5. Draft actions can be tested, edited where supported by the relevant UI, and promoted explicitly.
6. Shared and personal data remain separated and recoverable from interrupted writes.
7. Invalid configuration and action inputs fail with actionable messages.
8. Automated checks pass and Windows-dependent behavior has a documented manual test.

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
- Cloud synchronization or accounts.
- Arbitrary scripts, loops, conditions, or unattended workflows.
- Automatic application-aware context switching.
- Exact restoration of unsaved documents, browser history, or tab groups.
- Third-party UI or persistence frameworks.

See [Roadmap](ROADMAP.md) for proposed outcomes and [Backlog](../BACKLOG.md) for actionable tasks.
