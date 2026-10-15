# Technical Review

This page collects dated reviews. [Architecture](ARCHITECTURE.md) remains the
current technical source of truth; the sections below distinguish completed
work from recommended follow-ups.

## Input / Output send routes (2026-10-14)

Use separate **Send text to…** and **Send files to…** entry points, with a visible
source scope and clear destination/effect. Header and editor right-click
surfaces share the appropriate builder without combining the different write
protocols. This review inspected current code and synthetic
coverage; it did not send personal text or perform a live Office/chat test.

### Current routes and effects

| Route | Text/source scope | Destination and effect |
| --- | --- | --- |
| OneNote — new text page | Whole raw field; editable title/body with source revision recheck | Exact notebook/section; one explicitly approved new page. Existing-page append still awaits the engine contract. |
| ChatGPT | Nonblank selection, otherwise whole field; editable composer | Opening stages text. A separate Send submits the draft to the chat. |
| Work Item Excel Inbox | Whole field with outer whitespace removed; link/source metadata added | Exact matching workbook; append a row and save the entire workbook. Existing workbook stays open; a workbook opened by the integration is closed. Missing workbook creation is separately confirmed. |
| Send to file destinations | Whole field containing exact absolute file paths, one per line | Folder Action, selected/discovered Work Item, recent folder or one-off folder; reviewed collision-safe file copy, not text storage. |
| Work Item Copy file | One exact file path | Selected Work Item folder; older single-file no-overwrite copy route. |
| Webpage PDF / VS Code | Whole URL / one exact path | Save a webpage PDF / open the path's folder through the registered VS Code protocol. |
| Clipboard, text transformations and saved Actions | Copy all/selection, selection-first transformation, or configured Action inputs | Clipboard handoff, editor output, template/URL invocation or saved-text paste to a captured app. These are not equivalent destination sends. |

Reviewed file-preview **Save As** writes transformation output under its source
provenance guards. **Create from Input** configures an Action. OneNote Find,
OCR and Drop bring material into Input / Output. Keep those incoming,
configuration and file-transformation tasks distinct from outbound text sends.

### Implemented in this pass

The owner-approved follow-up splits header and right-click menus into text and
file destinations. Text offers OneNote, ChatGPT, a selected Inbox shortcut and
**Choose Work Item Excel Inbox…**. File copy, PDF and VS Code remain in the
file menu. A second compact toolbar row protects both full labels at 350px and
100–150% scaling; native keyboard traversal follows their visual order.

The Work Item-only chooser uses cached inventory, preselects an exact current
item when available, and displays source plus full Inbox workbook path below
the list. Long labels were measured to hide distinguishing paths; wrapped
details now grow when a longer destination is selected. **Append text** restores
the native grab, consumes the choice once, and reuses the existing handler.
Text/revision/source, exact stable identity and folder/workbook path changes,
busy operations, canceled or obsolete callbacks stop without fallback/retry.
Opening/browsing reads no workbook and changes no main view/filter. Original
To inbox/context shortcuts remain; retired Capture Inbox remains retired.

The neutral **Copy files to:** heading no longer claims arbitrary prose is a
validated list of file paths. The Send to tooltip explains selection/full-field
differences and the Inbox save effect. That save also persists other unsaved
workbook edits; the live Excel conversion promise of no Save call does not apply
to this CP-owned PowerShell Inbox operation.

### Recommended follow-ups

1. Agree one explicit source rule for text receivers: recommend highlighted
   text when present, otherwise the whole field, with a small visible
   **Selection / All text** indication. Current Inbox and OneNote sends use the
   whole field; do not silently change that behavior. Capture text/revision once
   at the deliberate send/stage gesture and preserve each owner's stale checks.
2. Use concise source/destination/result summaries across destination windows,
   retaining domain-specific approval, Save/Close and partial/unknown outcomes.
   No universal Review gate, automatic retry or shared engine framework.

The changes and pending manual/live limits are recorded in
[Testing](TESTING.md#search-recall-and-text-send-access-2026-10-14). Owners remain
`launcher.py`/`workspace_panel.py`, `work_item_inbox.py` plus its fixed
PowerShell adapter, and the existing OneNote/chat/file-transfer modules.

The menu split, direct chooser and clipped-path correction have separate
[follow-up evidence](TESTING.md#separate-textfile-menus-and-inbox-chooser-2026-10-14).

## Maintenance review (2026-10-11)

The host at `61f2300` has 105 source modules and 36 top-level documentation
files. The largest production modules are `configuration_window.py` (7,049
lines), `launcher.py` (6,187) and `excel_automation.py` (3,820). Size identifies
places to inspect; it does not establish that a wholesale rewrite is useful.
This review sampled shared integration policies, persistence, configuration,
test isolation and documentation ownership, rather than claiming a full audit
of every function. No engine repository or personal/runtime data was changed.

The architecture already separates domain rules from most UI and platform
effects. The best first return is eliminating repeated policy and conflicting
guidance while keeping existing public contracts and caller-specific behavior.

| Priority | Evidence and smallest useful change | This pass |
| --- | --- | --- |
| 1 | Four Excel owners repeat configured-launcher versus direct-sibling resolution. Put precedence and availability in one resolver; keep configuration loading unprobed and workflow probes local. | Implemented in `excel_automation.py`; the callers retain their workflow state machines. |
| 2 | Change guide disagrees with the canonical final-check command, Architecture describes the same menu dialog twice, and Testing puts current commands behind more than 1,000 lines of dated evidence. | Consolidated guidance, one dialog owner description, current checks first. |
| 3 | `persistence.py` duplicates atomic replacement for JSON and bytes. Share the file-publication steps only after protecting exact JSON bytes, backups, failure ordering and serialization memory behavior. | Implemented as one streamed temporary-file lifecycle; public APIs, locking, defaults and failure phases remain unchanged. |
| 4 | Excel fakes/builders and disposable launcher fixtures are imported from other test modules or classes. Extract narrowly shared support without weakening effect isolation or Tk scaling cleanup. | Implemented under `tests/support`; existing case identities preserved and four cleanup/effect safety tests added. |
| 5 | ActionDialog duplicates scrolling while several other dialogs use `_ScrollableDialogBody`; wheel/focus/destruction semantics differ. Extract this owner during a focused Configure change. | Implemented in `dialog_scrolling.py`; both existing behavior modes retained with owned focus/binding cleanup. |

Retirement compatibility remains active code: startup cleanup and backup paths
still preserve legacy references and Inbox data. It must not be deleted merely
because the user-facing Capture Inbox/Harvest features are retired. The Excel,
OneNote, CSV, native conversion and format workflows also retain different
effect/close/retry rules; a generic window/engine framework would obscure them.

Verification and remaining Windows/live limits are recorded in
[Testing](TESTING.md#code-and-documentation-maintenance-2026-10-11). No dependency,
data migration or functionality removal is proposed by this pass. Engine live
acceptance and public-interface changes remain separately scoped work.

The owner approved the atomic-writer follow-up. Characterization passed against
the original implementation before extraction, then against the shared streamed
publisher. Exact byte fixtures, gate/serialization timing, publication order and
injected failure phases protect the existing contract, including the possibility
of a partial `.bak` after failed backup copy. See
[the writer verification](TESTING.md#atomic-writer-consolidation-2026-10-11).
Shared test support was subsequently extracted into two focused owners, with
original domain defaults, callback timing, effect isolation and Tk teardown
preserved. Setup/body/construction errors now have explicit cleanup coverage;
the actual Excel-call boundary also blocks pre-captured process factories.
See [shared support verification](TESTING.md#shared-test-support-extraction-2026-10-11).
Configure scrolling now has one focused owner for all five form dialogs,
preserving Action-editor and other-dialog pointer/focus/wheel behavior.
Owned deferred reveals and window bindings are cleaned up without cancelling
unrelated work. Verification is recorded in
[Configure scrolling extraction](TESTING.md#configure-scrolling-extraction-2026-10-11).

## Earlier review (2026-07-13)

Date: 2026-07-13

This is a dated review, not the current architecture source of truth. See
[Architecture](ARCHITECTURE.md) for current behavior. Status notes below were
updated on 2026-07-24; the original rationale remains useful.

## Conclusion

Context Palette has a sound prototype architecture and does not need a rewrite. The standard-library boundary, constrained action model, callback-injected effects, local data ownership, and automated domain tests are good foundations for a portable Windows tool.

The main technical risk is concentrated UI orchestration. `launcher.py` still owns the main window plus several secondary windows and dialogs. The safest path is incremental extraction around existing boundaries while preserving the tested action and persistence formats.

## Strengths

- No mandatory third-party runtime dependency.
- No application-defined compound command parser; one explicit Windows target
  can be delegated to ShellExecute.
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

### Completed: extract remaining secondary windows from `launcher.py`

The UI construction is now divided into header, results/command surface,
shortcuts, workspace, and footer methods. Tooltip behaviour lives in
`tooltips.py`; Help, Cheat Sheet, Inbox, and Inbox action-creation windows now
have focused modules. The remaining launcher work is main-window orchestration;
future extraction should follow demonstrated stable component boundaries
rather than splitting methods for line-count reduction alone.

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

1. Separate Configure dialog families from `configuration_window.py` when the
   next material Configure change needs them.
2. Define clipboard and workspace effects before implementing transactions and sequences.
3. Reassess only after those capabilities have real usage feedback.

This order improves reliability and maintainability without delaying product learning or replacing working code for stylistic reasons.
