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
| Global search and keyboard execution | Implemented | All items searches Actions and Work Items together with shared Context/tag filters; explicit kind scopes retain type/project controls; fixed slots use 1–0, with physical `0` as the tenth slot |
| Global pins and focus-context slots | Implemented | Machine-local Action pins 1–5 are directly assignable in Configure; Context slots 6–0 accept Actions or Work Items and follow the selected Focus |
| Guided configuration | Implemented | A task-oriented Start page routes ordinary Configure use into the existing Actions, Focus, Quick-action, Work Item, backup, and diagnostic editors; records use My configuration or Built-in ownership; one obvious website or absolute file/folder/application path in Input / Output can prefill the reviewed Action form without probing the target |
| Confirm → Active → Archived | Implemented | Creation and editing save immediately; Configure can archive, inspect, edit, restore, or permanently delete stored Actions, while only Active Actions appear in runtime discovery and assignment pickers |
| Explicit action execution | Implemented | 16 allow-listed types with standard icons and current-state Input → Effect previews, including two copy-and-open URL builders, user-owned Windows targets, and preview-first text-file transformations |
| Protected credential paste | Implemented with limitations | Exact standard Windows or generic credential target; confirmed, hotkey-originated paste only |
| Input / Output transformations | Implemented | Selection or full field; result copied; includes filtering, delimiters, explicit comma-list quote variants, naming styles, JSON, URL/SQL encoding, file URIs, and path slashes |
| Always-on-top drop intake | Implemented | One non-transient Toplevel owned by the resident process accepts bounded Windows paths, UNC paths, HTTP(S), file URIs, `.url`, `.lnk`, and text; only the drop target is permanently topmost; successful results use Input / Output Replace/Append/Cancel without clipboard writes or persistence |
| Local image-to-text extraction | Implemented with optional component | Exact selected image path, clipboard bitmap, or reviewed file choice; background RapidOCR; local-only; Replace/Append/Cancel; clipboard image preserved; optional runtime adds about 270 MB and currently requires separate local setup |
| Text-file transformations | Implemented | One configured existing local text source; result is reviewed in Input / Output; guarded explicit replace or save-as preserves encoding and refuses stale overwrites |
| Cheat sheets and promotion | Implemented | Structured local JSON sheets |
| Attended AI assistance | Partial | Reviewable stored prompt templates and manual clipboard handoff; `copy_text` and `open_url` proposals only |
| Context model | Partial | General root, per-PC Context membership for Actions and Work Items, tags, explicit focus, mixed preferred items, and deterministic Focus-first grouping in global All-items discovery; Developing Context Palette is the only shipped specific context |
| Work Items discovery | Implemented | Bounded local discovery, mixed or Work Item-only main-window search/opening, shared Context/tag filtering, guided private source/tag configuration, and stable personal Quick-action references |
| Work Item creation | Implemented | Editable suggested name, one local generic `.xlsx` template, collision-safe folder/workbook creation, optional tags |
| Work Item Inbox | Implemented | Attended append of Input / Output to the selected exact-name `.xlsx`; creates `Inbox` and offers template-based workbook creation when missing |
| Work Item file copy | Implemented | Copies one exact absolute file path from Input / Output into the selected Work Item folder; background, collision-safe, no overwrite |
| Bulk action harvesting | Implemented | Attended local extraction of HTTP/HTTPS candidates from selected `.md`, `.txt`, `.docx`, and `.xlsx` files; review and atomic permanent creation |
| External automation | Partial by design | Show/context/search only; no action execution API |
| Clipboard transactions | Partial | Protected credential paste atomically captures and conditionally restores prior plain text; non-text-only content stops safely; ordinary saved text and rich/image formats are not preserved |
| Safe action sequences | Implemented with limits | 2–12 references to reviewed launch/open Actions, bounded waits, complete confirmation, Stop remaining, and dependency-safe lifecycle; no paste/keys, loops, conditions, inline commands, completion checks, retry, or rollback |
| Rich clipboard/image actions | Partial | Image content is not persisted as an Action, but a local clipboard or file image can produce editable Input / Output text; rich HTML, reusable image Actions, and typed image pipelines remain deferred |
| Automatic context inference | Deferred | The user chooses focus explicitly |

## Acceptance criteria

The MVP baseline is satisfied when:

1. A fresh clone can be set up on supported Windows with user-level permissions.
2. The resident palette opens, searches, and runs constrained actions predictably.
3. Actions, contexts, Quick-action menus, ordered targets, and menu assignments
   can be configured without editing technical IDs.
4. Captured material can enter the Inbox, become an Active action after
   confirmation, and be deleted independently when its captured copy is no
   longer needed.
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
- delegates one user-configured Windows target plus structured arguments to
  ShellExecute without interpreting a compound command string;
- keeps the integration bridge attended;
- treats captured material and AI responses as untrusted;
- stores personal data locally in ignored files.
- stores only credential target references in actions; passwords remain in Windows Credential Manager.

## Not required for the MVP

- Installer, administrator rights, service, or mandatory tray integration.
- Application-provided speech and dedicated screen-reader conformance testing.
  Ordinary keyboard operation and clear native control labels remain required.
- Cloud synchronization or accounts.
- Loops, conditions, compound command parsing, or unattended workflows.
- Automatic application-aware context switching.
- Exact restoration of unsaved documents, browser history, or tab groups.
- Third-party UI or persistence frameworks.

See [Roadmap](ROADMAP.md) for proposed outcomes and [Backlog](../BACKLOG.md) for actionable tasks.
