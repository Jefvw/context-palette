# Changelog

This project has not published a versioned release. Changes are recorded under **Unreleased** until a release process and versioning policy are chosen.

## Unreleased

- Added a **Work Items** Configure tab for managing local source folders,
  refreshing the index, reviewing source state, and editing private per-item
  tags. Removing a source never deletes work files, and the result context menu
  opens the selected item directly for tag editing. Source removal is one
  atomic configuration write and retains private tags for safe reuse. Configure
  scans run in the background, and edits made during a scan queue one latest
  refresh instead of freezing the window or being silently missed. Closing
  Configure safely ignores late scan results without retaining destroyed UI.
  Keyboard setup now starts in the first source field and supports F6 pane
  switching plus list-local Insert, Delete, F5, and Enter commands.
- Added Work Items discovery to the main Actions workspace. The compact Work
  button reuses Find and the result list, with structured project-code and
  personal-tag filters, background refresh, clear unavailable/empty states,
  exact workbook opening, folder fallback, Shift+Enter folder opening, and a
  constrained right-click menu.
- Added a dedicated, searchable Keyboard Shortcuts page exposed through the
  main-window **⌨** button. Guided action-form mnemonics now use the same
  layout-independent Alt handling as Configure. Only Shift plus a physical
  top-row number key executes slots 1–9 while Find is focused; plain number-row
  and numpad input remain ordinary Find text.
- Prevented Ctrl/Alt-modified number keys from executing main-palette action
  slots. Plain numbers remain Find text and Shift plus the physical top row
  runs slots 1–9. Inside
  Configure, layout-independent `Alt+A`, `Alt+T`, `Alt+C`, `Alt+B`, and `Alt+D`
  select Actions, Built-in action types, Contexts, Right-side buttons, and
  Diagnostics. Their letters are underlined in the tab labels.
- Added a safe Diagnostics tab to Configure with configuration counts, recent
  automatic-paste outcomes, error counts, Refresh, and Copy safe summary. It
  never displays raw log messages or sensitive action, clipboard, credential,
  or window content. `Ctrl+Shift+D` opens it directly from the focused main
  palette, and native `Ctrl+Tab` cycles Configure tabs with focus entering the
  selected tab's primary content.
- Changed saved-text actions to paste directly into a freshly captured hotkey
  destination after copying. Without a safe destination they remain
  clipboard-only and explicitly request manual `Ctrl+V`; a vanished destination
  restores the palette without losing the copied text. Every action attempt now
  consumes its captured destination so a later paste cannot reuse a stale
  window. Windows paste-dispatch failures also restore the palette with useful
  recovery guidance; protected credential content is cleared immediately.
  Content-free outcome events now distinguish success, clipboard fallback,
  unavailable destinations, cancellation, and input-dispatch failure.
- Added `F5` as a main-window startup-view reset that clears transient search,
  filters, Focus Actions mode, captured selection, and Input / Output while
  preserving saved Focus, pins, slots, actions, and configuration.
- Added direct right-click routing from ordinary and Focus action rows to the
  existing Configure Actions workspace, with the clicked action highlighted
  for editing. Shared actions are now editable after a warning explains that
  their tracked changes can affect other machines and must not contain private
  or machine-specific information.
- Added safe action deletion to Configure. The confirmation reports saved
  references, removes pins, Focus slots, context preferences, and quick-button
  references, and gives shared actions an additional Git-impact warning.
- Bounded attended AI responses to 1,000,000 characters before clipboard
  insertion or JSON parsing, preventing oversized untrusted responses from
  unnecessarily consuming resident UI and parser memory.
- Replaced fixed Technology/Task action classification with reusable tags and
  optional multi-context membership. General now acts as a virtual root
  containing every action; Focus Actions is a flat membership list, and Tags
  provides a dedicated discovery filter. Existing legacy personal action files
  remain readable while edited and newly created actions use the new format.
  Partially configured Focus slots now fill with other members of that context
  before unrelated global actions. Saved Focus names and slot keys also match
  current context names case-insensitively. Guided action forms now identify
  unknown specific contexts before saving and retain the form for correction.
  Configure, Inbox conversion, and Draft editing now also provide a reusable
  multi-select context checklist alongside the editable field, plus an
  optional checklist of existing tags that still permits new free-form tags.
  Windows-style `Alt+C` and `Alt+T` mnemonics focus those fields, and
  `Alt+Down`/`F4` opens their native keyboard-navigable checklists.
- Added a Notepad++-inspired transformation starter pack with Proper Case,
  sentence case, inverted case, per-line trimming, blank-line removal, stable
  line sorting, line joining, and consecutive duplicate removal.
- Added a workspace SQL value-list formatter that parenthesizes mixed numbers,
  text, and `NULL`, quotes text, and safely escapes apostrophes.
- Removed an obsolete date placeholder and consolidated two project-folder
  actions onto the portable `%PROJECT_ROOT%` definition.
- Restored a visible route to the complete action and button configuration
  workspace through the compact Manage focus menu, while retaining `Ctrl+,`.
- Preserved active pins, Focus, and context slots when the local palette file
  is temporarily locked or otherwise unreadable, with regression coverage.
- Made compact-control names and explanations appear on keyboard focus as well
  as pointer hover.
- Armed conditional credential clipboard clearing before destination focus and
  paste dispatch, closing an exception path that could leave cleanup unscheduled.
- Extracted the Cheat Sheet secondary window from the launcher orchestrator
  into a focused module without changing its behavior.
- Added safe per-stage timing details to slow configuration-reload diagnostics
  after measurement showed action search itself is already fast.
- Isolated the current Focus action-grouping policy from the Tk launcher in a
  dedicated, characterized domain module to prepare for context-model changes.
- Moved available-Focus discovery, preferred-slot resolution, and fallback
  policy into that same pure model boundary.
- Kept keyboard and hover tooltips on-screen near display edges, including on
  secondary monitors with negative coordinates.
- Replaced the wide Focus selector with a compact explicit menu, added direct
  Focus management, and introduced a Technology → Task → action Focus browser
  that leaves ordinary Find results global. Keyboard focus now moves directly
  into the tree when that browser is explicitly activated. Fixed session
  expansion state leaking from the previously rendered Focus into a newly
  selected Focus, preserved an all-collapsed state, and prevented Run from
  targeting a hidden leaf after expansion restoration.
- Moved Sheets from the compact footer into a keyboard-accessible Knowledge
  Quick action backed by a single explicit built-in command allow-list.
  Knowledge now stays visible directly below Frequent passwords instead of
  falling below the normal Quick-actions viewport.

### Added

- Four pinned-first Frequent passwords buttons for starting protected paste without intermediate filtering or list selection.
- Compact Passwords button beside Find for quickly filtering to protected credential actions.
- Portable multi-machine development recipe with a tracked Python version and a single setup-and-check command.
- Trusted, confirmed paste of exact generic Windows Credential Manager targets through a no-history/no-cloud clipboard item.
- Project-aware Python wrapper for reliable targeted tests, benchmarks, and module commands from the repository root, with distinct environment and source-import recovery guidance.
- Guided configuration for personal actions of every built-in type, focus contexts, context slots, and right-side buttons.
- Built-in action catalogue with examples and generated documentation.
- Capture Inbox, Draft creation, editing, explicit trust promotion, cheat-sheet promotion, and attended AI proposal review.
- Focus-context slots, global pins, configurable quick-action groups, and keyboard operation.
- Constrained URL, file, folder, application, transformation, and workspace actions.
- Atomic JSON replacement with local backups and a read-only configuration checker.
- Searchable in-app Help, local bounded diagnostics, Windows integration examples, and CI on Python 3.12.

### Changed

- Reduced startup and explicit reload work from two complete Quick-action
  widget rebuilds to one after command groups and pin state are both loaded.
- Replaced the full-width action-search row with a focused Actions workspace:
  Find sits above the list and Passwords, Types, Run, and Help use a compact
  vertical tool rail.
- Prevented either adjustable main-window divider from collapsing Actions,
  Quick actions, or Input / Output into an unusable pane.
- Presented Quick-action subjects as full-width vertical menu-launcher rows
  with native indicators, while preserving primary execution and existing menus.
- Balanced the upper action console at approximately 44% Actions and 56% Quick
  actions, with responsive user-adjustable sizing.
- Unified action discovery and text transformation in an unchanged-width,
  responsive-height main window with a balanced 52/48 adjustable split.
- Doubled the Input / Output workspace height while consolidating the bottom
  actions into one icon row with name-first explanatory tooltips.
- Added a compact all-action-type filter while retaining the direct Passwords
  filter shortcut.
- Standardized full application screens to the main window size, with
  screen-aware reduction and protected bottom action rows on smaller displays.
- Removed window-layout/snapshot actions and PowerToys-specific integration assets; retained the attended Power Automate bridge.
- Added automatic backed-up cleanup of retired layout actions and local references on every machine.
- Aligned Windows CI dependency installation, configuration validation, compilation, and tests with the complete local development workflow.
- Skipped redundant dependency installation when the tracked requirements declaration has not changed.
- Released tooltip objects for destroyed quick-action and password buttons whenever the surface is rebuilt.
- Allowed protected paste to resolve exact targets from both Windows Credentials and Generic Credentials.
- Unified action-value validation for guided creation and JSON loading, including rejection of invalid list-conversion modes and empty persisted values.
- Made Configure context and button tables directly operable with keyboard selection and Enter.
- Added fast, keyboard-accessible filtering to Configure → Actions across user-visible action facets.
- Preserved last-known-good contexts and right-side buttons when edited configuration files fail validation.
- Preserved active pins, Focus, and context slots when palette-state reload
  fails instead of resetting state and aborting the reload, and made first
  start safe when no valid palette state exists yet.
- Kept Focus and pin state consistent when palette persistence fails, with actionable feedback instead of an uncaught UI error.
- Added privacy-safe warnings for genuinely slow result refreshes and configuration reloads.
- Centralized quick-action primary/fallback ordering so execution, configuration, and validation cannot drift.
- Added predictable initial keyboard focus to Configure and its action, context, and button dialogs.
- Preserved last-known-good actions when an edited action file fails to reload.
- Kept Configure edit dialogs open after validation or persistence errors so entered values are not lost.
- Made quick-action mouse, keyboard, and menu routes consistently honor the configured primary action.
- Restored descriptive launcher metadata for shared Archive, Colruyt, and Python documentation actions after an accidental configuration regression.
- Made setup recover from a stale virtual environment after the project or Python installation moves, and made launch failures explain how to repair the environment.
- Refined the interface for compact buttons, consistent spacing, native focus indication, useful empty states, and non-blocking save feedback.
- Moved long-running window restore work off the Tk main thread.
- Added configuration signature checks and brief search coalescing to keep the resident hot path responsive.
- Separated reviewed shared configuration from ignored personal and machine-specific data.

### Security

- Preserved protected-clipboard tracking when an ordinary clipboard
  replacement fails, preventing credential content from becoming eligible for
  automatic Input / Output synchronization.
- Kept credential passwords out of action JSON, previews, workspace text, logs, AI prompts, clipboard history, and cloud clipboard synchronization.
- Rejected credential-bearing and ambiguously parsed HTTP(S) action URLs across creation, loading, generation, and execution.
- Prevented stalled localhost integration clients from holding the single-instance listener indefinitely.
- Kept action execution allow-listed and rejected arbitrary shell-command actions.
- Restricted the external bridge to showing/filtering the palette; it cannot execute actions.
- Validated AI responses through a versioned schema and existing Draft constructors.

See [Decisions](docs/DECISIONS.md) for chronological rationale and [Roadmap](docs/ROADMAP.md) for planned outcomes.
