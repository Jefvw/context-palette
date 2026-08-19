# Backlog

This file contains actionable future work. Completed user-visible work belongs in [CHANGELOG.md](CHANGELOG.md), and ordered outcomes belong in [Roadmap](docs/ROADMAP.md).

## Now

- Manually validate the always-on-top drop target on a second standard-user
  Windows PC and at 100%, 125%, and 150% display scaling. Cover Explorer files,
  folders, multiple items, UNC and percent-encoded paths, `.url`, `.lnk`, a
  browser link, OneNote link/text, and a desktop shortcut; verify empty,
  Replace, Append, and Cancel placement, unchanged clipboard content, ordinary
  palette auto-hide/non-topmost behavior, target Hide/Show, and fallback when
  TkDND cannot load.
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
- Evaluate typed Work Item support for global pins 1–5 only after the normal
  mixed-result projection can display those pins consistently.
- Consider optional Context visibility/grouping for Quick-action groups. The
  current schema deliberately leaves groups global, while their targets already
  use the shared Palette-item reference needed by a later design.
- Add line-ending normalization and CSV/TSV column operations after real-use
  feedback on the expanded reusable text-operation catalogue.
- Design supporting-context composition and weighted ranking while preserving explicit Focus and global search.
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
