# MVP baseline

This document defines the implemented minimum product baseline and distinguishes partial or deferred capabilities. It is a scope reference, not a future-feature list.

## Product promise

Context Palette helps a Windows user capture useful material, turn it into a
constrained permanent Action after confirmation, edit stored configuration,
and retrieve an Action or Work Item quickly from search, an explicit Context
filter, or an organized Quick-action menu.

## Status

The owner accepted the current Input / Output, Preview, Drop, Send-files and
cosmetic batch for now on 2026-09-09 with partial UAT coverage. See the
[acceptance record](UAT_CURRENT_BATCH.md). Unreported scenarios remain
unverified; separate broader manual matrices and live Excel gates retain
their existing status.

| Capability | Status | Current boundary |
| --- | --- | --- |
| Resident launcher and global shortcut | Implemented | `F9` primary, `Ctrl+Alt+P` fallback |
| Global search and keyboard execution | Implemented | All items searches Actions and Work Items together; one transient Context choice in the unified Filter menu controls visible membership and slots 6–0; Context and tag span every item scope, Action type applies in Actions, and project applies in Work Items; non-empty Find results are relevance-ranked and do not promote context slots |
| Context slots | Implemented | Context slots 6–0 accept Actions or Work Items; All contexts selects General's bank and a specific Context selects its own, while Find/tag/type/project narrow results without selecting another bank; global runtime pins 1–5 are retired while legacy IDs remain round-trippable for rollback |
| Guided configuration | Implemented | A task-oriented Start page routes ordinary Configure use into Actions, Contexts, Quick actions, Work Items, backup, and diagnostics; records use My configuration or Built-in ownership; virtual General is a fixed non-deletable Context row with a local 6–0 shortcuts-only editor; Folder/Password/AI-prompt creation and editing choose the automatic menu location and zero-or-more configured references together, with one rollback-protected save and a standalone Other menus route for saved Actions; derived automatic submenus expose explicit New/Rename/Move/Remove tasks, while one or many direct Action members can be promoted one level without deleting the Actions or targets; automatic-root membership remains required for matching Active Actions, so deleting the owning Action is the only way to remove its root leaf; automatic organization and configured references retain separate storage and ownership without schema migration; one obvious website or absolute file/folder/application path in Input / Output can prefill the reviewed Action form without probing the target |
| Confirm → Active; reviewed permanent deletion | Implemented | Creation and editing save immediately; Configure can directly review and permanently delete an Action while removing its saved placements transactionally. The external target is never deleted or changed. Legacy `Archived` records remain inactive, visible as **Legacy inactive**, and deletion-only; no Archive or Restore command remains. |
| Explicit action execution | Implemented | 19 allow-listed types with standard icons and current-state Input → Effect previews, including saved file-copy destinations, the constrained Edge score PDF Action, two copy-and-open URL builders, user-owned Windows targets, preview-first text-file transformations, attended optional Python Excel CSV export, and direct live Excel formatting |
| Protected credential paste | Implemented with limitations | Exact standard Windows or generic credential target; confirmed, hotkey-originated paste only |
| Input / Output transformations | Implemented | Selection or full field; result copied; includes filtering, delimiters, explicit comma-list quote variants, naming styles, JSON, URL/SQL encoding, file URIs, and path slashes; Back/Forward retains at most ten meaningful whole-content states in memory while native Undo/Redo remains available |
| Always-on-top drop intake | Implemented | One non-transient Toplevel accepts bounded paths, links, shortcuts and text; only the drop target is permanently topmost. Default show-only intake and explicit history resend use Input / Output Replace/Append/Cancel. Configured Actions run directly on the exact drop without editor staging; completed text output may be delivered afterward. The last ten drops remain in session history for inspection/recovery; no automatic retry or persistent input log. |
| Local image-to-text extraction | Implemented with optional component | Exact selected image path, clipboard bitmap, or reviewed file choice; background RapidOCR; local-only; Replace/Append/Cancel; clipboard image preserved; optional runtime adds about 270 MB and currently requires separate local setup |
| Text-file transformations | Implemented | One configured existing local text source; result is reviewed in Input / Output; guarded explicit replace or save-as preserves encoding and refuses stale overwrites |
| Focused UI enhancements | Implemented; owner UAT accepted for now, coverage partial | Default-shown Input / Output can be hidden without losing content, selection, or history; optional snapshot Preview performs no effects; Drop settings opt into a compatible exact-input Action with existing confirmations, stale-approval refusal, retained input on failure, and show-only history replay. Existing Contexts/tags and normal Run/Open stay unchanged; no redesign or data migration. |
| Cheat sheets and promotion | Implemented | Structured local JSON sheets |
| Attended AI assistance | Partial | Reviewable stored prompt templates and manual clipboard handoff; `copy_text` and `open_url` proposals only |
| Context model | Partial | General root, per-PC Context membership for Actions and Work Items, tags, and one transient Context filter coupled to mixed preferred slots; legacy saved focus data remains compatibility-only; Developing Context Palette is the only shipped specific context |
| Work Items discovery | Implemented | Bounded local discovery, mixed or Work Item-only main-window search/opening, Context/tag/project filtering, guided private source/tag configuration, stable personal Quick-action references, non-destructive source disconnection that retains organization, and transactional Forget of Palette-only organization without external-file deletion |
| Work Item creation | Implemented | Editable suggested name, one local generic `.xlsx` template, collision-safe folder/workbook creation, optional tags |
| Work Item Inbox | Implemented | Attended append of Input / Output to the selected exact-name `.xlsx`; creates `Inbox` and offers template-based workbook creation when missing |
| Work Item file copy | Implemented | Copies one exact absolute file path from Input / Output into the selected Work Item folder; background, collision-safe, no overwrite |
| Outbound Send to file copy | Implemented, manual UAT pending | A visible Input / Output menu copies 1–100 exact existing files to a Context-relevant Folder Action, selected/searchable Work Item, recent successful destination, or one-off folder; planning and copying stay off the Tk thread; collision-safe `(1)`, `(2)` suffixes are the default and explicit reviewed overwrite may replace only unsuffixed files; exact partial results, stop-between-files, and Quit guarding are supported; sources, clipboard, and Input / Output remain unchanged |
| VS Code folder opener | Implemented, manual UAT pending | The separate **Send to… → Open with** route accepts one existing absolute folder or file path; a folder opens itself and a file opens its containing folder through Windows' registered `vscode:` protocol; it copies nothing, leaves Input / Output and clipboard unchanged, does not run Folder Actions or persist receivers, and is not a generic plugin framework |
| Webpage PDF | Implemented, owner UAT pending | **Input / Output → Send to… → Save webpage as PDF…** snapshots one HTTP(S) URL, chooses a new PDF path and renders with installed Edge/Chrome in a temporary session. Background work, cancellation, no-overwrite publication and Quit guarding preserve existing files, editor and clipboard. Signed-in pages and exact page layout require normal browser printing; the saved PDF must be inspected. |
| Current Edge score PDF | Owner accepted current manual completion | Run the saved Action on a supported Official Ultimate Guitar score or Guitar Pro tab in Edge, then choose the final folder/filename and finish Save As manually. The exact supported URL type must agree with the displayed document title; ordinary text tabs, chords, and arbitrary webpages are excluded. At the accepted Save As handoff, Palette closes its progress window without an error popup; other failures remain visible. The automatic-save attempt is unchanged; this is not an enforced pause mode. The configured folder is not applied at the observed stop. Full automatic saving is not required; unreported broader UAT remains optional. |
| Excel CSV automation | Implemented with limitations | Optional separately bootstrapped Python Excel engine with exact direct-sibling discovery or an explicit machine-local launcher; accepts up to 100 closed exact `.xlsx` paths from Input / Output/drop intake; first workbook folder is the overridable output default; asynchronous describe-plan-review-execute against exact automation 2.0; all used columns; unchecked collision-safe `(1)`, `(2)` suffixing or checked reviewed unsuffixed create/atomic replace; no source mutation, progress, cancellation, live Excel, sequences, replacement backup/batch rollback, or automatic retry after stale/partial/unknown outcomes |
| Live Excel format template | Implemented with limitations | Optional attended `inventory_live_excel` then `apply_live_format_profile` integration against Python Excel commit `e405e14`; acts only on already-open workbooks, one selected worksheet or all visible worksheets, with fixed Standard data formatting. AutoSave must be off. The Apply button is confirmation; Context Palette never saves/closes Excel. No planning, backup, rollback, progress, cancellation, retry, or undo guarantee; stale/partial/unknown results require manual inspection and Refresh. A disposable one-worksheet real-Excel smoke passed; the broader manual matrix remains pending. |
| Live Excel scientific-notation conversion | Development/UAT; mutation UAT pending | Optional attended capability, inventory, paged physical-column preflight, fingerprinted plan, precision acknowledgement, and recovery-backed execution against Python Excel `08af313` (`1.0` operations). Read-only review remains available, while Execute requires `CONTEXT_PALETTE_UAT_LIVE_TEXT_CONVERSION=1` at process startup. The engine creates and verifies the recovery workbook; Context Palette never saves/closes Excel and never retries partial or unknown outcomes automatically. |
| Bulk Action creation from Excel | Implemented | Generates and locally reads one bounded versioned standard `.xlsx`; reviews up to 1,000 structured rows, ordinary validation, personal Contexts, duplicates, and errors; creates selected personal Active Actions through one guarded Action/Context operation; no formulas, Office startup, sequences, fixed Excel automations, whitespace-sensitive text-file transforms, updates, or deletes |
| Bulk Action update from Excel | Implemented, manual UAT pending | Exports eligible personal Active ordinary Actions to a separate deterministic version-1 `.xlsx` with immutable ID/type/state/original fingerprint; reviews editable Name, Value, personal Contexts, tags, description, Quick menu, lossless JSON arguments, and working folder; selected Ready changes use one guarded exact-byte-rollback Action/Context update with no execution; Built-in, legacy inactive, sequence, fixed Excel automation, text-file transform, row-removal deletion, and deletion operations are excluded |
| Bulk Action deletion | Implemented, manual UAT pending | One centered personal-only window reviews explicit Action IDs, sequence blockers, hidden selected rows, and combined saved-placement effects. One **Delete N Actions permanently** button is the confirmation. The transaction rechecks all participants, removes Active or legacy inactive records and their internal references together, never infers deletion from workbook rows, never executes Actions, and never touches external targets. |
| Website-link harvesting | Implemented | Attended local extraction of HTTP/HTTPS candidates from selected `.md`, `.txt`, `.docx`, and `.xlsx` files; provenance review and atomic personal Active `open_url` creation |
| External automation | Partial by design | Show/context/search only; no action execution API |
| Clipboard transactions | Partial | Protected credential paste atomically captures and conditionally restores prior plain text; non-text-only content stops safely; ordinary saved text and rich/image formats are not preserved |
| Safe action sequences | Implemented with limits | 2–12 references to reviewed launch/open Actions, bounded waits, complete confirmation, Stop remaining, and dependency-safe lifecycle; no paste/keys, loops, conditions, inline commands, completion checks, retry, or rollback |
| Rich clipboard/image actions | Partial | Image content is not persisted as an Action, but a local clipboard or file image can produce editable Input / Output text; rich HTML, reusable image Actions, and typed image pipelines remain deferred |
| Automatic context inference | Deferred | The user chooses the Context filter explicitly |

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
10. Eligible personal Active Actions can be exported with stable identity,
    edited in a separate standard workbook, reviewed as exact changes, and
    updated without executing or deleting them.
11. Personal Actions can be explicitly selected for one-window bulk deletion;
    one effect-labelled operation removes the reviewed records and internal
    references while every external target remains unchanged.

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
