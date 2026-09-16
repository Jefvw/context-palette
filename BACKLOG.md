# Backlog

This file contains actionable future work. Completed user-visible work belongs in [CHANGELOG.md](CHANGELOG.md), and ordered outcomes belong in [Roadmap](docs/ROADMAP.md).

The owner accepted the current Input / Output, Preview, Drop, Send-files and
cosmetic batch on 2026-09-09 with partial UAT coverage. See the
[acceptance record](docs/UAT_CURRENT_BATCH.md). Unreported checks remain
unverified and are deferred; they do not block this accepted batch.

The owner accepted the current Edge score workflow on 2026-09-15: prepare an
Official or Guitar Pro Ultimate Guitar score, then choose its folder/filename and
complete Save As manually. The accepted
handoff now closes Palette's progress window without an error popup; the
automatic-save mechanics are unchanged. Full automatic saving is no longer a required fix;
broader unreported UAT remains optional. See [Testing](docs/TESTING.md).

## Now

- Optional score-PDF follow-up: complete Save As manually and inspect the PDF's
  score, instrument and page count. The Guitar Pro Action reached a two-page
  preview and Save As without a Palette popup in the 2026-09-15 live check.
  Official-score recheck, cancellation, changed foreground, scaling and another
  PC remain unreported; see [Testing](docs/TESTING.md).

- Validate the new **Send to… → Save webpage as PDF…** with a public article,
  a longer page, and a page with images/JavaScript. Open the results and check
  expected text, images and page breaks. Try Cancel, an existing filename and
  an invalid address; confirm original PDFs, Input / Output and clipboard stay
  unchanged. Check controls with keyboard and Windows scaling. This feature is
  separate from the earlier accepted batch; see [Testing](docs/TESTING.md).

- Manually validate combined **Menu locations** while creating and editing a
  Folder, Password, and AI-prompt Action, then validate **Other menus…** from a
  selected saved Active Action. Confirm the automatic
  Passwords/Folders/Prompts location is always present and independent; add the
  same Action to zero, one, and multiple eligible configured roots/branches;
  switch between My configuration and Built-in before saving; remove selected
  references; and verify personal Actions cannot use Built-in locations. Review exact
  additions, removals, and newly empty items before applying, then exercise
  stale-plan, complete-rollback, and incomplete-rollback outcomes. Repeat
  keyboard-only and at 100%, 125%, and 150% scaling.
- Manually validate structured automatic Quick-menu organization for
  Passwords, Folders, and Prompts. From a new and existing Action, choose the
  menu root, an existing branch, and a newly created three-level branch without
  typing `>`. In Configure → Quick actions, use the explicit New/Rename/Move/
  Remove submenu tasks for all three automatic roots. Cover no-selection,
  maximum depth, selected Built-in/personal and Active Actions, nested-child
  promotion, and case-variant merge. Trigger stale-plan
  and injected rollback failures, and confirm empty branches disappear while
  Actions and external targets remain unchanged. Repeat with keyboard-only use
  and at 100%, 125%, and 150% scaling.
- From an automatic submenu, remove one Action leaf with **Remove from
  submenu…**, then remove several direct members with **Remove selected from
  this submenu**. Confirm every selected Action moves exactly one level, the
  target and record remain, the last-member branch disappears, and two
  same-titled Actions are distinguished by stable ID. At the automatic root,
  confirm no Remove command appears and direct Action deletion is explained as
  the only way to remove that required automatic leaf.
- Manually validate **Send to… → Open with → Open folder in VS Code** with one
  existing absolute folder, one file whose parent should open, outer quotes,
  spaces, Unicode, and an unavailable network path. Cover empty, multiple,
  relative, missing, and unmatched-quote input plus a machine without a
  registered `vscode:` handler. Confirm the command copies nothing, leaves
  Input / Output and the clipboard unchanged, does not add a recent copy
  destination or run a Folder Action, and stays visible at 100%, 125%, and
  150% scaling.
- Manually validate Input / Output **Send to…** with one and many local files,
  quoted paths, Unicode, UNC paths, duplicate basenames, same-folder sources,
  missing/changed sources, and 100-file input. Cover a Context-relevant Folder
  Action, selected and searchable Work Items, all Folder Actions, recent
  destinations, and a one-off folder. Verify default `(1)`, `(2)` collision
  suffixes, explicit overwrite review and exact button wording, destination
  changes after review, stop/partial outcomes, Open destination folder, Quit
  blocking, unchanged sources/Input/Output/clipboard, fixed relative/file-URI
  Folder resolution, exclusion of clipboard-templated Folder Actions, and
  visible controls at 100%, 125%, and 150% scaling.
- Validate **Create Actions from Excel…** with a generated standard workbook:
  edit it in desktop Excel, create mixed Action types, use General and personal
  Contexts/tags, review duplicates/errors/excluded rows, modify the workbook
  after review, and confirm one guarded rollback-capable personal-Action creation
  at 100%, 125%, and 150% scaling. Repeat without Excel installed by editing a
  fixture copy.
- Validate the separate personal-Action update round trip: choose **Export
  personal Actions for update…**, edit every supported field in desktop Excel,
  then choose **Review updated Actions workbook…**. Cover Ready/no-change/error
  rows, immutable identity columns, removed rows, lossless JSON arguments,
  personal Contexts, stale workbook and configuration changes, selected-row
  commit, exact-byte rollback after an injected Context-write failure, and no
  Action execution or second confirmation. Confirm Built-in, legacy inactive,
  sequence, Excel-automation, and text-file-transform Actions are excluded.
  Repeat at 100%, 125%, and 150% scaling and without Excel installed.
- Validate **More Action tasks → Delete multiple personal Actions…** with
  personal Active, legacy inactive, sequence, Context, slot, and configured
  Quick-menu fixtures. Confirm the centered window deletes only after one
  **Delete N Actions permanently** effect-labelled button. Cover selected and
  unselected dependent sequences, hidden selected rows, shared Quick items,
  stale configuration, injected write/rollback failure, keyboard-only
  selection, and 100%, 125%, and 150% scaling. Confirm every external target
  remains untouched.

- Manually validate the live **Apply Excel format template** Action with a
  disposable workbook against Python Excel commit `e405e14`. The one-sheet
  happy path and preservation of an existing filter passed on 2026-08-25.
  Confirm its shared workbook/worksheet chooser matches the conversion Action,
  then complete the remaining setup/missing-engine, all-visible, AutoSave rejection,
  added-filter, hidden-sheet, stale, partial/unknown, no-retry, Return-to-Excel,
  no-save/no-close, and 100%/125%/150% display-scaling matrix.
- Complete disposable real-Excel UAT for **UAT: Convert scientific-notation
  columns** against Python Excel `08af313` before removing its execution gate.
  Confirm the same shared workbook/worksheet chooser behavior first.
  With `CONTEXT_PALETTE_UAT_LIVE_TEXT_CONVERSION=1` set before startup, cover
  scientific text, numeric scalars, leading-zero and ordinary text, formulas
  outside the selected scope, a formula-in-scope blocked plan, blank and
  duplicate headers, duplicate workbook names across Excel processes,
  pagination/truncation, precision acknowledgement, default and overridden
  sibling recovery paths, stale/recovery conflicts, verified recovery content,
  partial/unknown no-retry guidance, dirty-unsaved/open Excel lifecycle, no
  extra Excel process, Return to Excel, and 100%/125%/150% scaling. Keep the
  Action UAT-labelled and Execute fail-closed until that matrix passes.
- Manually validate the first Python Excel CSV automation vertical slice on a
  second standard-user PC. Cover missing/invalid local engine setup,
  Input/Output and Drop-into exact `.xlsx` intake, the 100-workbook limit,
  direct-sibling discovery, required worksheet parameters, automatic default
  output and its reviewed override, asynchronous plan/review/execute,
  source immutability, unchecked `report.csv`/`report(1).csv` collision
  suffixing, checked unsuffixed create/replace review, exact effect counts and
  execute-button wording, stale-plan replanning, partial commit, unknown
  process loss, Open output folder, and the absence of desktop Excel,
  automatic retry, cancellation, progress, replacement backup/rollback, and
  sequence support.

- Manually validate the always-on-top drop target on a second standard-user
  Windows PC and at 100%, 125%, and 150% display scaling. Cover Explorer files,
  folders, multiple items, UNC and percent-encoded paths, `.url`, `.lnk`, a
  browser link, OneNote link/text, and a desktop shortcut; verify empty,
  Replace, Append, and Cancel placement, unchanged clipboard content, ordinary
  palette auto-hide/non-topmost behavior, last-ten Previous/Next/Send-again
  history, compact selection summaries, bounded on-demand prepared-content
  details and warnings, collapse on Hide/new drop, target Hide/Show, and
  stale-requirements refusal plus setup/restart recovery, and isolated fallback
  when native TkDND cannot load. Also exercise
  the Input / Output Back/Forward history and its branch behavior.
- Manually verify native Quick-action menu right-click delivery on Windows at
  100%, 125%, and 150%: launcher left-click/Enter/Space browses without
  execution; launcher right-click offers Add/Organize; Action right-click opens
  the exact editor without execution; submenu right-click targets the exact
  branch; and normal Action left-click still runs. Include configured,
  Passwords, Folders, Prompts, Work Item, disabled, and three-level cases.
- Manually validate the complete newly implemented Configure page batch at
  normal/minimum sizes on real Windows 100%, 125%, and 150% display scaling.
  Actions and Work Items already passed the user's 125%/150% review; repeat the
  matrix for Contexts, Quick actions, Backup & restore, and Diagnostics. Check
  long names, empty/selected states, automatic versus custom Quick actions,
  scrollbars, and every command edge against the accepted
  [real-Tk baseline](docs/UI_MOCKUPS.md).
- Manually validate the simplified retrieval model at 100%, 125%, and 150%:
  choose **All contexts** and specific Context filters in all three item scopes;
  confirm visible membership and slots 6–0 switch together; verify tag, Action
  type, Work Item project, and Find narrow results without selecting another
  slot bank; verify query relevance and dormant-filter chips; and confirm that
  Shift+1–5 never executes while context slots 6–0 still do.
- Manually validate complete deletion and disconnection wording: permanently
  delete a disposable Action, delete a disposable Context and
  configured Quick menu, and disconnect/reconnect a disposable Work Item
  source while confirming that external folders/files and saved organization
  remain untouched.
- Manually validate optional local OCR on a second standard-user Windows PC,
  including a Snipping Tool bitmap, copied browser image, exact image-file
  path, non-empty workspace, no-text image, accented Latin text, offline use,
  and an environment where optional package downloads are blocked. Record
  startup, first-run, recognition, memory, and installed-size measurements.
- Complete and record the Phase 5 manual Windows verification matrix from the
  reviewed [backup and restore plan](docs/BACKUP_RESTORE_PLAN.md). The Configure
  UI and automated coverage are implemented; native dialogs, keyboard access,
  same-machine temporary-data round trip, disconnected-source warning, live
  reload, recovery location, editing exclusion, alternate path/computer, and
  interruption/startup recovery remain to be checked. Do not begin selective
  import/export until this is complete.
- Complete Phase 5 of the approved [Work Items discovery plan](docs/WORK_ITEMS_PLAN.md):
  representative performance measurements and manual Windows checks on another
  computer/path. Phases 1–4 include guided private source/tag configuration.
- Manually verify generic-template Work Item creation with a real workbook and
  a representative network or disconnected source when back at the Windows desk.
- Manually verify Work Item **To inbox** with a representative Excel workbook:
  existing and missing `Inbox`, an already-open workbook, missing-workbook
  creation, non-ASCII text, a locked workbook, and a network source.
- Evaluate whether safe discovery across multiple separately running Excel
  instances is worthwhile. The current integration uses Excel's registered
  automation instance and otherwise reports a locked workbook without writing.
- Manually verify **Copy file** with a representative network source, a large
  file, a destination collision, and an unavailable Work Item source.
- Perform and record the manual Windows UI/accessibility smoke test for the guided Configure workflow.
- Complete the input-first launcher visual matrix on representative 100%, 125%,
  and 150% display scaling, including the supported minimum size, divider
  resizing, keyboard-only traversal, every discovery scope, Quick-action menus,
  file-preview controls, and Action/Work Item execution routes.
- Extract Configure dialog families from `configuration_window.py`
  mechanically when the next material Configure change needs them.
- Validate the new Input → Effect summaries through real repeated-work feedback,
  especially long configured targets and empty/fallback states.
- Add focused tests for configuration-window keyboard order and validation recovery where Tk permits reliable automation.

## Next

- Design a prebuilt portable application bundle that includes Python and an
  optional OCR pack so a locked-down PC needs no installer, pip command,
  administrator rights, or first-use network access.
- Validate the task-oriented main-window toolbar at 100%, 125%, and 150%
  display scaling and refine bitmap contrast only if real Windows themes expose
  a problem.
- Consider optional Context visibility/grouping for Quick-action groups. The
  current schema deliberately leaves groups global, while their targets already
  use the shared Palette-item reference needed by a later design.
- Add line-ending normalization and CSV/TSV column operations after real-use
  feedback on the expanded reusable text-operation catalogue.
- Design supporting-context composition only after the explicit Context filter
  and relevance-ranked search have enough real-use feedback; never apply or
  switch a Context filter implicitly.
- Extend the protected plain-text clipboard transaction to ordinary saved-text
  paste only after destination paste timing and manual-fallback recovery are
  defined; add rich/image formats only through format-specific snapshots.
- Add sequence paste, Tab, and Enter steps only after ordinary clipboard
  restoration, destination-focus recovery, and stop/failure semantics are
  defined and manually verified.
- Define context activation bundles only after effect preview and recovery behavior are documented.
- Continue extracting stable UI families only when a demonstrated change
  boundary benefits; avoid line-count-only refactors.

## Later

- Revisit the [current-batch follow-up checks](docs/UAT_CURRENT_BATCH.md) when
  real-use feedback or a relevant change warrants them: Input / Output
  selection/history, effect-free Preview, exact Drop input and replay,
  Run/Quick-menu file copying, conflicts/open reviews/changed approval, and
  physical 100%/125% DPI plus cross-monitor icon/control rendering. Owner
  acceptance is closed for now; no unreported check is counted as a pass.

- Consider direct source drag-and-drop and folder selection inside Harvest
  after its explicit multi-file workflow has real-use feedback. The implemented
  general intake drop target intentionally does not add Harvest sources.
- Evaluate OneNote, PDF, HTML, and email harvesting only with format-specific
  safety, provenance, and bounded-extraction designs; do not add recursive or
  remote crawling implicitly.
- Add reusable prompted forms with field validation.
- Add rich HTML content with plain-text fallback.
- Add persistent image/visual-asset actions only after the implemented
  image-to-text workspace workflow establishes explicit source, preview, and
  clipboard semantics.
- Add a character picker and explicit clipboard slots.
- Investigate safe browser-specific URL discovery without focus or clipboard manipulation.
- Add optional application-aware context suggestions; never switch automatically.
- Explore a packageable tray icon and optional AutoHotkey adapter.
- Design an explicit authorization policy before any unattended action execution.
- Expand attended AI authoring only for types with adequate validation and review.

## Product questions

- Which action effects need a standard preview/result model before sequences are safe?
- How should supporting contexts affect ranking without making results unpredictable?
- What recovery guarantees are realistic for clipboard transactions?
- Which personal actions are frequent enough to justify new built-in types?
