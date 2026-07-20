# Decisions

## 2026-07-20 - Isolate current Focus policy before context redesign

**Decision:** Move the pure Focus-to-action hierarchy rule from the Tk launcher
into `focus_model.py`, with dedicated characterization tests. Keep context
definitions and palette persistence unchanged until the replacement context
approach is specified.

**Reason:** A planned context overhaul needs a clear domain boundary, but
changing storage or product semantics prematurely would encode guesses. The
focused module separates current policy from UI orchestration and provides one
intentional replacement point.

**Consequences:** Current Focus behavior is unchanged. Future context work can
evolve or replace the pure model before adapting the launcher and persistence
edges.

The boundary also owns current available-Focus discovery, preferred-slot
resolution, and missing-Focus fallback. The launcher retains only loading,
persistence, Tk variable updates, and rendering.

## 2026-07-20 - Arm protected clipboard cleanup before paste dispatch

**Decision:** Schedule the sequence-checked credential clipboard clear
immediately after the protected clipboard write, before the delayed destination
focus and paste callback runs.

**Reason:** Scheduling cleanup only after sending the paste shortcut left an
exception path where protected clipboard content could remain without a timer.
Arming cleanup first preserves the existing 15-second usability window while
making dispatch failures fail closed.

**Consequences:** Destination failures still clear immediately. The delayed
callback remains harmless if another application replaces the clipboard because
the existing sequence-number check prevents clearing unrelated content.

## 2026-07-19 - Keep Focus browsing explicit and global search global

**Decision:** Replace the wide Focus combobox with a compact explicit menu,
add a Focus Actions tree in the existing Actions region, and switch back to the
unchanged global flat results whenever Find contains text or a type filter is
active. The tree includes only visible actions whose explicit context matches
the active Focus and groups them by Technology and Task.

**Rationale:** Focus should make repeated work easier to browse without silently
changing what global search means. Reusing action leaves and the existing
dispatcher preserves lifecycle and execution safety.

**Decision:** Move Sheets from the footer into a Knowledge Quick action through
a closed `open_sheets` built-in-command allow-list.

**Rationale:** Sheets is knowledge retrieval rather than an action lifecycle
command. A one-command allow-list provides the requested placement without
turning Quick-action configuration into arbitrary method or shell execution.

## 2026-07-19 - Group action controls into an Actions workspace

**Decision:** Remove the separate full-width Find row and place the unchanged
Find entry directly above the Actions list. Place the existing Passwords,
Types, Run, and action-Help controls in an 88-pixel vertical rail beside the
list. Start the dashboard at approximately 44% Actions workspace and 56% Quick
actions.

**Reason:** Search, filtering, execution, and action-specific Help operate on
the numbered Actions list. Grouping them communicates that relationship,
removes an unrelated full-width control row, and retains enough list width
without making the Quick-action menu launchers unreadable.

**Consequences:** Widget types, labels, callbacks, menus, tooltips, creation
order, focus traversal, and enabled states do not change. Global Help remains
in the Focus header. The existing bounded and user-adjustable dashboard
divider remains in effect.

## 2026-07-19 - Present Quick actions as subject menus

**Decision:** Render each configured Quick-action subject as one full-width
vertical row with a native right-side menu indicator. Keep groups in their
canonical row-major two-column order and start the action console at
approximately 33% Actions and 67% Quick actions.

**Reason:** A Quick-action subject can expose several existing operations.
Three small labels across a row made subjects resemble unrelated one-shot
buttons and truncated useful names. Vertical menu-launcher rows communicate
the subject/menu relationship and provide more label width without widening
the application.

**Consequences:** The indicator is presentation-only. Left click, Enter, and
Space still execute the primary-first available action; right click opens the
same ordered action menu; Shift/Ctrl+click opens the same configuration files.
Configuration records, titles, callbacks, menu contents, enabled states, and
execution rules do not change. Both main splitters use bounded positions so
neither side can be accidentally collapsed; undersized displays divide space
proportionally.

## 2026-07-19 - Unify action discovery and text transformation

**Decision:** Keep the main window at `780` pixels wide, use available monitor
height up to `1000` pixels, and place the existing action-discovery area and
Input / Output workspace in a user-adjustable vertical split weighted 52/48.
Preserve the user's adjusted ratio during later resizing in the same session.
Keep command buttons and status outside that split.

**Reason:** Context Palette is an action launcher with an integrated
text-transformation workspace. Action discovery and recurring transformations
are successive parts of one workflow, so neither should visually overwhelm the
other. Extra vertical space improves both without reducing width or introducing
navigation, tabs, or conventional document-editor features.

**Consequences:** Secondary windows retain their standardized `780x600` size.
The main window reduces on smaller displays and, when invoked by hotkey,
shrinks only when required to fit the cursor monitor before using the existing
on-screen positioning clamp. All existing widgets, callbacks, bindings, data,
and execution behavior remain unchanged.

## 2026-07-19 - Remove window restoration and PowerToys integration

**Decision:** Remove `window_layout` and `restore_window_snapshot` actions,
snapshot capture/restore UI, native layout code, shared layout configuration,
and PowerToys-specific examples and reference material. Retain the constrained
show/context/search bridge for Power Automate Desktop.

**Reason:** Window restoration and PowerToys integration are no longer desired
product responsibilities. Removing their complete implementation and
configuration surface reduces platform-specific complexity and keeps Context
Palette focused on quickly finding and running repeated actions.

**Consequences:** Existing ignored snapshot files are not deleted, but Context
Palette no longer reads, creates, validates, or restores them. Historical
decision entries below describe the former implementation and are superseded by
this decision.

## 2026-07-19 - Track the Python family, not the virtual environment

**Decision:** Declare the supported Python family in `.python-version`, keep
`.venv` ignored and machine-local, validate its Python version and repository
location during setup, and provide `develop-context-palette.bat` as the
setup-and-check entry point.

**Reason:** Virtualenv and Conda environments contain machine-specific paths and
executables. Synchronizing the environment itself is unreliable, while a
tracked version and dependency recipe can be reproduced consistently on every
development computer.

**Consequences:** Each computer needs a compatible Python installation with
Tcl/Tk and creates its own disposable `.venv`. Changing the supported Python
family is now an explicit reviewed repository change. Unusable or mismatched
environments are preserved under numbered `.venv-unusable*` names before
replacement.

Record durable product and technical decisions here.

Decision entries are historical and append-only. Their consequences describe the system at the time; use `ARCHITECTURE.md`, `HELP.md`, and `MVP.md` for current behavior.

## 2026-07-19 - Support both visible Windows credential categories

**Decision:** Resolve a protected-paste target first as a Generic Credential and
then as a standard Windows/domain-password credential using the same exact
target and native `CredReadW` boundary.

**Reason:** Credential Manager presents these as separate visible categories.
Restricting lookup to Generic Credentials rejects valid targets such as
`oracle-pc17` stored in the Windows Credentials section, despite the user
supplying the correct exact name.

**Consequences:** No enumeration or fuzzy matching is introduced. Generic
credentials remain deterministic when duplicate target names exist. Both
supported categories use the existing Trusted-state, fresh-destination,
confirmation, protected-clipboard, and conditional-clear safeguards.

## 2026-07-19 - Keep credential paste native, exact, attended, and ephemeral

**Decision:** Add a `paste_credential` action that stores only an exact generic
Windows Credential Manager target. Retrieve it with native `CredReadW` through
standard-library `ctypes`; require Trusted state, a fresh hotkey-captured
destination, and confirmation. Paste through a clipboard item excluded from
history and cloud synchronization, then clear it conditionally.

**Reason:** Repeated password entry is valuable to accelerate, but treating a
password as saved text or a template variable would expose it to JSON, search,
previews, clipboard history, logs, or AI workflows. Native Windows access avoids
a new dependency and works directly with generic Credential Manager targets.

**Alternatives considered:** Python `keyring` adds a third-party backend and
service/username mapping layer that is unnecessary for this Windows-only
application. Direct simulated typing avoids the clipboard but is less reliable
across password fields and remains observable to keyboard hooks. Unconfirmed or
externally invoked pastes would make destination mistakes too easy.

**Consequences:** Credential enumeration and creation remain outside Context
Palette. Drafts cannot paste, external show requests cannot establish a
destination, prior clipboard contents are not restored, and same-user malware
remains outside the application's threat boundary.

## 2026-07-19 - Bound localhost integration client time

**Decision:** Apply a short receive timeout to every client accepted by the single-instance localhost bridge.

**Reason:** The bridge handles untrusted local connections on one listener thread. A client that connected without sending data could otherwise block that thread indefinitely and prevent later launcher or attended integration requests.

**Consequences:** Stalled and malformed clients are discarded without affecting the resident application. The accepted request schema and attended show/context/search behavior remain unchanged.

## 2026-07-18 - Repair stale local environments during setup

**Decision:** Test the existing virtual environment by running its interpreter rather than trusting that `python.exe` exists. Preserve an unusable environment as `.venv-unusable`, select the first genuinely runnable Python 3.12 interpreter, and recreate `.venv`. Make the launcher reject missing or unusable environments with a setup instruction.

**Reason:** Python virtual environments contain absolute paths and can retain executable shims after the project or base Python moves. File-existence checks incorrectly treated that state as healthy, blocking setup, launch, and verification.

**Consequences:** Recovery is non-destructive and leaves personal data untouched. Setup stops rather than overwrite an existing `.venv-unusable`. A working Python 3.12 installation with Tcl/Tk is still required.

## 2026-07-18 - Separate current documentation, history, and planning

**Decision:** Use `ARCHITECTURE.md` and `HELP.md` for current behavior, `MVP.md` for the implemented scope boundary, `ROADMAP.md` for ordered outcomes, the root `BACKLOG.md` for actionable future work, `CHANGELOG.md` for user-visible history, and this file for chronological rationale. Add a documentation index and keep the root agent guide authoritative.

**Reason:** The prototype grew quickly and several documents mixed current behavior, completed work, proposals, and old consequences. Clear ownership reduces drift and helps both developers and AI agents distinguish executable fact from direction.

**Consequences:** Historical decisions are not rewritten when implementation advances. Current documents must label deferred behavior explicitly. Generated action-type documentation remains owned by the executable catalogue.

## 2026-07-15 - Use one action-type catalogue for validation, documentation, and AI guidance

**Decision:** Define every supported action type in one catalogue containing its user label, family, required fields, input/output effects, portability, AI eligibility, and type-specific prompt guidance. Derive runtime supported types and the generated action overview from that catalogue. Enable AI proposals for `copy_text` and validated fixed `open_url` Drafts.

**Reason:** Independent lists in validation, documentation, editors, and AI prompts would drift as the application adapts. A small declarative catalogue makes later additions explicit and testable without introducing a framework.

**Alternatives considered:** A complete separate prompt per type would duplicate shared safety and schema instructions. Enabling every type immediately would let AI invent machine paths, executable targets, or snapshot configuration before type-specific review flows exist.

**Consequences:** The catalogue is the supported-type source of truth and its generated Markdown overview is test-locked. AI requests combine shared safety text with catalogue guidance. Exactly one complete JSON Markdown fence is normalized, while commentary and multiple blocks remain invalid. Remaining types are explicitly not yet AI-proposable.

## 2026-07-15 - Centralize recoverable JSON writes and configuration checks

**Decision:** Route application JSON writes through one standard-library helper that flushes a temporary sibling, preserves the prior file as `.bak`, and atomically replaces the destination. Add a read-only configuration checker that reuses domain loaders and validates cross-file action references before compilation and tests.

**Reason:** Interrupted direct writes could corrupt complete local data files, while configuration mistakes were discovered only when opening affected UI paths. A shared writer and one repeatable check make user and AI-assisted adaptation safer.

**Alternatives considered:** A database or third-party persistence library would add portability and migration costs. Per-module recovery logic would duplicate subtle file-handling behavior. Reimplementing schemas in the checker would risk disagreement with runtime validation.

**Consequences:** Existing JSON formats and public domain interfaces remain unchanged. Previous file contents are retained in ignored sibling backups; successful later writes replace the prior backup. The checker validates structure and references but does not execute actions or prove external Windows targets are available.

## 2026-07-14 - Modernize styling with native ttk

**Decision:** Centralize the grey, teal, and aqua palette, Segoe UI fonts, widget styling, and interaction-state maps in `style.py`. Use Python's bundled Tk/ttk `clam` theme as the styling base and retain the existing widget tree and geometry.

**Reason:** A single native style module improves visual consistency and maintainability while preserving portable, administrator-free setup. It also avoids adding and packaging a third-party theme solely for appearance.

**Alternatives considered:** Sun Valley, Azure, and ttkbootstrap provide richer Windows-like visuals, but each adds an external dependency and ongoing compatibility surface. Custom widget classes and layout changes were unnecessary for the requested visual refresh.

**Consequences:** Buttons, entries, group headings, quick-action labels, selections, and focus states share one palette. Native ttk cannot guarantee identical rounded corners across Windows versions, but the application remains standard-library-only and its layout and public behavior are unchanged.

## 2026-07-13 - Keep a bare first-launch workspace empty

**Decision:** Do not replay a synthetic `show` request when the first Context Palette process starts without an explicit context or search parameter.

**Reason:** The root window is already visible. Replaying `show` immediately synchronized arbitrary existing clipboard text into Input / Output, making the application appear to start with unexplained content such as `{`.

**Consequences:** A normal application start has an empty workspace. F9 selection capture, later attended show requests, and first launches with explicit integration parameters retain their existing behaviour.

## 2026-07-13 - Refactor incrementally around existing boundaries

**Decision:** Keep the current architecture and reduce concentrated UI complexity incrementally. Extract reusable tooltip mechanics, divide main-window construction into named sections, and reject case-insensitive duplicate action IDs. Record the broader findings in `docs/TECHNICAL_REVIEW.md`.

**Reason:** The prototype has good constrained domain modules and tests; a rewrite would add risk without improving the product loop. The clearest maintenance problem is the size and responsibility count of `launcher.py`, while ambiguous IDs are a concrete data-integrity risk for pins, context slots, menus, edits, and trust promotion.

**Consequences:** Visible behaviour and JSON schemas remain unchanged. Future maintenance should prioritize atomic JSON writes, a Windows UI smoke test, and mechanical extraction of secondary windows before considering new abstractions or dependencies.

## 2026-07-12 - Use screen space for results and stable guidance

**Decision:** Collapse Focus and Find to single rows, keep Input / Output as a permanent clipboard-backed text box, and use a slim bottom line for action explanations and application communication. Every label and button receives hover guidance; specific descriptions override automatic fallbacks.

**Reason:** Search results are the primary interaction and deserve most vertical space. Guidance remains available through small `?` controls and a predictable location.

**Consequences:** The text box always remains directly editable and usable by actions. The communication line stays compact so results retain most vertical space.

The slot legend and text toolbar are also omitted: their functions remain discoverable through row numbering, tooltips, standard text shortcuts, and the workspace context menu.

## 2026-07-12 - Add F9 as the one-key launcher

**Decision:** Register F9 and Ctrl+Alt+P simultaneously. Both perform selection capture and cursor-based positioning, with key-repeat suppression.

**Reason:** F9 is present on laptops and usually has fewer global conflicts than F12, while the established chord remains a reliable fallback.

**Consequences:** Media-key laptop modes may require Fn+F9 or Fn Lock. Applications that normally use F9 will not receive it while Context Palette owns the global shortcut.

## 2026-07-12 - Position shortcut opens at the cursor monitor

**Decision:** Capture cursor and monitor work-area coordinates when the global shortcut fires, then place the palette near that point after selection capture.

**Reason:** In a multi-monitor workflow, the cursor is the clearest indication of where the user's attention is. Capturing immediately avoids positioning based on later focus changes.

**Consequences:** The window flips left or upward near screen edges and is clamped inside the selected monitor. Power Automate and ordinary launcher opens retain their existing position.

## 2026-07-12 - Make standalone contexts file-first

**Decision:** Load shared `contexts.json` and ignored `local_contexts.json` independently from actions. Context definitions carry identity metadata and up to four preferred action IDs.

**Reason:** Contexts must be configurable upfront, transferable between PCs, and editable with any text or AI assistant without depending on an unfinished management UI.

**Consequences:** Explicit local palette slots override configured defaults. Shared and local context names must be unique. Internal context information remains in the ignored local file.

## 2026-07-12 - Let Inbox conversion start from the intended result

**Decision:** The Draft creator first asks what the action should do and adapts its content guidance accordingly. URL builders expose copy/open behaviour, require `{id}` or `{id_url}`, and show a live example. Primary buttons live in a fixed footer.

**Reason:** A capture is source material, not necessarily the final output. Hardcoding conversion to copy-text concealed existing URL-builder capabilities, while a bottom footer inside expanding content could make the buttons disappear.

## 2026-07-12 - Keep Windows automation integration attended and optional

**Decision:** Power Automate Desktop and PowerToys integrate through a constrained localhost show request containing only optional context and search text. Batch and PowerShell wrappers expose the same surface. It cannot run an action or arbitrary command.

**Reason:** This provides useful integration without making either Windows product a dependency or bypassing Context Palette's visible action selection and trust model.

**Consequences:** A native PowerToys Run plug-in remains a separately packaged future adapter. Unattended action execution is deferred until Trusted-action authorization, confirmation policy, structured results, and security tests are designed.

## 2026-07-10 - Use a local Python virtual environment for development

**Decision:** Use a project-local `.venv` directory for development commands.

**Reason:** The project must stay portable and avoid administrator-only setup. A local environment keeps development files inside the project folder and avoids changing system Python configuration.

**Alternatives considered:**

- Rely on the installed user-profile Python directly without a `.venv`: rejected because a local environment is easier to document and keep isolated.
- Use the installed user-profile Python as the `.venv` base: rejected for now because it does not provide Tkinter in this environment.
- Use Codex's bundled Python runtime: chosen because a nearby working Tkinter project uses it successfully and it provides Tkinter.
- Install Python system-wide: rejected because the target environment may not allow administrator installs.
- Add third-party environment tooling: rejected because the project does not need it yet.

**Consequences:**

- Development commands should use `.\.venv\Scripts\python.exe`.
- The `.venv` folder is ignored by Git and should not be committed.
- The local environment currently does not include `pip`.
- That is acceptable for the first launcher prototype while the project uses only the standard library.

## 2026-07-10 - Use Tkinter for the first launcher prototype

**Decision:** Use Tkinter for the first launcher prototype.

**Reason:** A nearby working Codex project uses Tkinter from Codex's bundled Python runtime. Recreating this project's `.venv` from the same base provides Tkinter 8.6 without adding third-party UI dependencies.

**Alternatives considered:**

- Use the installed user-profile Python: rejected for now because Tkinter is not available there.
- Use a third-party desktop UI package: deferred because the project avoids unnecessary dependencies.
- Start with a command-line prototype: possible for storage and action execution, but it would not satisfy the launcher-window milestone by itself.

**Consequences:**

- The first launcher can be built without a new dependency.
- Packaging or handoff instructions must eventually explain how the bundled/runtime Python is supplied or how to install a Python distribution with Tkinter.

## 2026-07-11 - Store initial actions in local JSON

**Decision:** Store prototype actions in `data/actions.json`.

**Reason:** JSON is human-readable, supported by the Python standard library, easy to back up, and simple enough for the first launcher prototype.

**Alternatives considered:**

- SQLite: rejected for now because the first milestone does not need database features.
- YAML: rejected for now because it would require an additional dependency or a custom parser.
- Python files as configuration: rejected because user data should stay separate from application code.

**Consequences:**

- The first prototype can load sample actions without extra dependencies.
- Editing actions is manual until the action editor exists.
- Future storage changes should include migration or import support if user-created data exists.

## 2026-07-11 - Restrict first action execution to safe action types

**Decision:** The launcher supports only constrained action types: copy text, open URL, open file, open folder, and launch an explicitly configured `.exe`.

**Reason:** The project must treat actions as untrusted input and avoid arbitrary shell-command execution.

**Alternatives considered:**

- Shell command actions: rejected for the first version because they are too broad and risky.
- Workflow actions: deferred until the core capture and testing loop works.

**Consequences:**

- The launcher can demonstrate useful behavior while keeping risk low.
- More powerful action types must be added deliberately and documented as separate decisions.

## 2026-07-11 - Allow fixed arguments for explicitly configured app launches

**Decision:** Allow `launch_app` actions to include fixed string arguments and a fixed working directory.

**Reason:** Opening VS Code with the Context Palette project requires launching a known executable with a known folder argument. This remains constrained because the executable and arguments are stored explicitly in local JSON; no arbitrary shell text is interpreted.

**Alternatives considered:**

- Keep `launch_app` as executable-only: too limited for useful project-opening actions.
- Add shell command actions: rejected because arbitrary shell execution is out of scope for the first version.

**Consequences:**

- The launcher can open VS Code directly on this project.
- App-launch actions still need careful validation before becoming trusted.
- Future editing UI should make fixed arguments visible and understandable.

## 2026-07-11 - Use a resident app hotkey for quick launcher access

**Decision:** Let the running Context Palette app register `Ctrl+Alt+P`.

**Reason:** A Windows shortcut hotkey starts the batch file every time, which is too slow for a QTP-style palette. A resident app hotkey shows the already-running window directly.

**Alternatives considered:**

- Windows shortcut hotkey: used briefly, then rejected because it launched the batch file every time.
- AutoHotkey: rejected for the first milestone because the app must remain usable without it.

**Consequences:**

- Context Palette must be started once before `Ctrl+Alt+P` can show it instantly.
- The `.lnk` shortcut no longer owns `Ctrl+Alt+P`.
- The hotkey is registered with the Windows API from the running Python process.
- Auto-hide is disabled if the hotkey cannot be registered, so the window does not become unreachable.
- Taskbar pinning remains a manual Windows step because scripted taskbar pinning is unreliable.

## 2026-07-11 - Keep launcher keyboard controls window-local

**Decision:** Add arrow-key navigation and number-key execution only while the launcher window is open and focused.

**Reason:** This makes the launcher faster without adding global hooks, services, AutoHotkey, or administrator-only behavior.

**Alternatives considered:**

- Global numpad shortcuts: rejected for now because they require broader keyboard interception and may be blocked in corporate environments.
- Mouse-only selection: rejected because the launcher should be fast from the keyboard.

**Consequences:**

- `Up`, `Down`, `Page Up`, `Page Down`, `Home`, and `End` move through visible results.
- Numpad `1` through `9` run the corresponding visible result slot even while the search box is focused. On Windows, this uses numpad keycodes because Tkinter can report numpad digits as plain numbers when Num Lock is on.
- Keyboard-row numbers still type normally when the search box has focus.
- The first nine visible results are numbered so the numpad slots are discoverable.

## 2026-07-11 - Add a read-only launcher preview pane

**Decision:** Show a read-only preview for the currently selected launcher action.

**Reason:** Preview supports the product's test-and-trust loop without requiring the full action editor yet. It helps the user see what will be copied or opened before executing the action.

**Alternatives considered:**

- Build the full editor first: rejected because preview is a smaller useful step.
- Use a modal preview dialog: rejected because it would slow down keyboard-first launcher use.

**Consequences:**

- Copy-text actions show the text that will be copied.
- Open and launch actions show the configured target.
- Editing still remains a later feature.

## 2026-07-11 - Store clipboard captures in local Inbox JSON

**Decision:** Store captured clipboard text in `data/inbox.json`.

**Reason:** The Inbox is the first step in the capture-to-draft lifecycle. JSON keeps the data local, inspectable, and easy to test without adding dependencies.

**Alternatives considered:**

- Store captures directly as actions: rejected because captures should remain untrusted until converted and tested.
- Use a database: rejected because the first milestone only needs simple local storage.
- Store one file per capture: deferred because a single JSON file is simpler for the first prototype.

**Consequences:**

- Clipboard captures have `Inbox` state and do not appear in launcher search yet.
- Conversion from Inbox item to draft action is a separate later feature.
- Damaged inbox JSON should be handled carefully before editing features are added.

## 2026-07-11 - Display Inbox items in a read-only popup

**Decision:** Add an `Inbox` button that opens captured items in a read-only popup with a preview.

**Reason:** Viewing captures is the smallest useful step after saving them. It confirms that capture worked and keeps conversion/editing as a separate feature.

**Alternatives considered:**

- Add a full Inbox tab: deferred because the launcher should stay small while the workflow is still forming.
- Convert captures immediately: rejected because the user should be able to inspect captured material before structuring it.

**Consequences:**

- Captured items are visible without opening JSON manually.
- Inbox items still cannot be edited, archived, or converted from the UI.

## 2026-07-11 - Convert Inbox items into draft copy-text actions first

**Decision:** Add Inbox conversion only for draft `copy_text` actions.

**Reason:** Clipboard text capture naturally maps to a paste/copy text action, and this is the smallest useful conversion path for the MVP lifecycle.

**Alternatives considered:**

- Let the user choose every action type immediately: deferred because it would require a larger editor.
- Auto-detect URLs, files, and folders during conversion: deferred until the basic conversion loop is proven.

**Consequences:**

- Converted Inbox items become searchable draft actions immediately.
- The original Inbox item is marked `Draft`.
- Choosing other action types remains a later feature.

## 2026-07-11 - Edit draft copy-text actions first

**Decision:** Add editing only for draft `copy_text` actions.

**Reason:** Draft copy-text actions are the direct result of clipboard capture and are the safest first editing target. The user can refine captured text before trusting it without exposing file, URL, app-launch, or future action types to accidental changes.

**Alternatives considered:**

- Edit all action types immediately: deferred because each type needs different validation.
- Edit raw JSON directly: rejected because the app should use clear forms rather than raw configuration files.

**Consequences:**

- The user can change title, context, and text for draft copy-text actions.
- Trusted actions and non-text actions remain read-only in the UI for now.
- More editors can be added one action type at a time.

## 2026-07-11 - Use one structured JSON file per cheat sheet

**Decision:** Use one JSON file per application or topic cheat sheet, documented in `docs/CHEATSHEET_FORMAT.md`.

**Reason:** Structured JSON is easier for Context Palette to show in compact popups, search by item, and eventually convert individual items into actions.

**Alternatives considered:**

- Markdown files: useful for drafting, but harder for the app to search and promote item-by-item.
- One large cheat-sheet file: rejected because app/topic files are easier to maintain and plug in.

**Consequences:**

- Cheat sheets can be created outside the app and later plugged into `data/cheatsheets`.
- LLM-generated cheat sheets should target the documented structure.
- The first viewer displays cheat sheets in a read-only popup.

## 2026-07-11 - Add Trusted promotion for draft actions

**Decision:** Add a `Mark Trusted` button for draft actions.

**Reason:** The product loop needs a visible promotion step from draft to trusted once an action has been tested and refined.

**Alternatives considered:**

- Promote automatically after editing: rejected because trust should be an explicit user decision.
- Add a full maturity-state editor: deferred because a single promotion action is enough for the first loop.

**Consequences:**

- Draft actions can be promoted to Trusted from the launcher.
- Trusted actions remain visible in the launcher.
- Demotion or archiving remains a later feature.

## 2026-07-11 - Incorporate the Windows 11 cheat sheet as the first popup sheet

**Decision:** Add the provided Windows 11 cheat sheet to `data/cheatsheets/win11.json` and load cheat sheets through a read-only popup.

**Reason:** The file already follows the proposed structured JSON shape. Incorporating it validates the cheat-sheet format with real content and keeps the information in-app rather than opening a browser.

**Alternatives considered:**

- Store it only as a document: rejected because the app should eventually display cheat sheets directly.
- Convert cheat-sheet items into actions immediately: deferred because viewing and searching sheets should come before promotion into actions.

**Consequences:**

- The launcher has a `Cheat Sheets` button.
- The Windows 11 sheet can be viewed in a popup.
- Cheat-sheet editing, search, and promotion remain later features.

## 2026-07-11 - Add search inside the cheat-sheet popup

**Decision:** Filter the selected cheat sheet by matching search terms against section titles, item labels, item details, and tags.

**Reason:** Real cheat sheets can be long. Search makes the Windows 11 sheet useful as a quick popup reference instead of a scrolling document.

**Alternatives considered:**

- Search sheet titles only: rejected because the useful information is inside sections and items.
- Build global cheat-sheet search across all sheets first: deferred until there are multiple sheets.

**Consequences:**

- The popup can quickly narrow the Windows 11 sheet to entries like `clipboard`, `snap`, `wsl`, or `task manager`.
- Search currently filters one selected sheet at a time.
- Ranking and highlighting can be added later.

## 2026-07-11 - Promote cheat-sheet items into draft copy-text actions

**Decision:** Add `Promote to Draft` in the cheat-sheet popup.

**Reason:** Useful cheat-sheet items should be able to enter the same draft, edit, and trusted lifecycle as captured clipboard text.

**Alternatives considered:**

- Convert whole cheat sheets into actions: rejected because promotion should happen item by item.
- Create special shortcut-note actions: deferred because `copy_text` draft actions already support search, preview, editing, and trust.

**Consequences:**

- A cheat-sheet item becomes a draft copy-text action using the sheet title as context.
- The action can then be edited and marked Trusted.
- The original cheat-sheet item remains unchanged.

## 2026-07-11 - Add resident single-instance launcher mode

**Decision:** Keep the first Context Palette process resident and have later launches signal it to show the existing window.

**Reason:** Opening the app should feel instant. Starting Python and Tkinter every time is slower than showing an already-running window.

**Alternatives considered:**

- Keep launching a new process every time: rejected because it feels slow and can create duplicate windows.
- Add a true tray icon immediately: deferred because tray support without dependencies requires extra Windows-specific work.
- Add a global keyboard hook: rejected for now because the app should work without hooks or administrator permissions.

**Consequences:**

- Closing the main window hides it instead of quitting.
- Clicking away from the main window hides it, matching a transient context-palette style.
- `Hide` hides the app, and `Quit` fully stops it.
- The resident app handles `Ctrl+Alt+P` directly for fast repeated opens.
- Later shortcut launches can still send a local `show` message to the resident process and exit.
- The local listener uses a stable project-specific port to avoid collisions between different Context Palette workspaces.
- If a new process cannot own the listener port, it exits instead of opening another duplicate window.
- `run-context-palette.bat` starts `pythonw.exe` through `start` so the command window should close immediately.
- `stop-context-palette.bat` is available as a development reset for this project's hidden `pythonw` process.
- This uses a localhost socket from the Python standard library; no network service or external dependency is installed.

## 2026-07-11 - Use a compact search-first palette layout

**Decision:** Make the main window smaller and prioritize search, results, and preview over management controls.

**Reason:** Once resident hotkey behavior worked, the main UI needed to feel like a quick context palette rather than a settings/workbench window.

**Alternatives considered:**

- Keep the larger workbench layout: rejected because it is slower to scan for frequent use.
- Split into separate use/workbench windows immediately: deferred because a compact single-window layout is a smaller step.

**Consequences:**

- `Run` sits beside search for fast use.
- Secondary controls are shorter: `Capture`, `Inbox`, `Sheets`, `Edit`, `Mark Trusted`, and `Reload`.
- Full workbench separation remains a later design step.

## 2026-07-11 - Keep search focused when the palette opens

**Decision:** Focus and select the search box shortly after the palette is shown, and add `Esc` to hide plus `Ctrl+L` to return to search.

**Reason:** A quick palette should be ready for typing immediately when opened. Focus can be lost during hide/show, so it needs to be restored after the window is visible.

**Alternatives considered:**

- Rely on Tkinter's initial focus only: rejected because focus was unreliable after resident show/hide.
- Put focus on the results list: rejected because search is the primary interaction.

**Consequences:**

- Opening with `Ctrl+Alt+P` should put the cursor in search.
- `Esc` hides the palette.
- `Ctrl+L` returns focus to search.
## 2026-07-11 - Add QuickTextPaste capabilities as safe native action features

**Decision:** Context Palette will reproduce the useful capabilities demonstrated by the existing QuickTextPaste INI file as explicit, inspectable features. The first layer supports dynamic clipboard, URL-encoding, date/time, calendar-week, and newline variables. Direct paste and constrained key sequences, clipboard slots, and a character picker will follow as separate layers.

**Reason:** These capabilities are central to the desired workflow, but arbitrary `run:` command execution would conflict with the project's constrained-action security model. Building each capability as a native action keeps previews, validation, and trust states meaningful.

**Alternatives considered:**

- Import the INI entries only: rejected because importing examples does not provide their behavior.
- Execute QTP command strings directly: rejected because it would introduce an opaque command language and unsafe arbitrary execution.
- Implement every QTP feature in one change: rejected because paste focus handling and simulated keys require separate manual testing on Windows.

**Consequences:** Existing QTP variable names can be reused where practical. Unsupported commands remain inert until a validated native equivalent exists.
## 2026-07-11 - Treat contexts as active work packages and stage five productivity capability families

**Decision:** A context will be modeled as identity, knowledge, capabilities, and optional activation rather than as a category string only. The roadmap incorporates selected-text transformations, safe workspace activation, constrained form filling, clipboard transactions, and rich content/image actions.

**Reason:** The QTP FAQ review showed that the largest productivity gains come from combining current input with transformations, workspace preparation, and controlled multi-step behaviour. These functions become easier to understand and maintain when they belong to a named work context and share previews, maturity states, and testing.

**MVP boundary:** Selected-text transformations, clipboard preservation, a small safe sequence model, and constrained context activation enter the MVP. Rich HTML and image actions follow after the core MVP, but the data model should anticipate them. Conditions, loops, arbitrary scripts, and automatic context switching remain excluded.

**Alternatives considered:**

- Keep contexts as labels: rejected because this does not materially improve on a large snippet list.
- Copy QTP command strings directly: rejected because opaque command syntax conflicts with safe previews and accessible editing.
- Put all five capability families in the first implementation slice: rejected because focus handling, clipboard restoration, sequences, and rich clipboard formats require separate testing.

**Consequences:** Context records and editors become a near-term architectural priority. Actions must declare inputs, outputs, clipboard effects, and supported steps clearly enough for preview and trust decisions.
## 2026-07-11 - Reserve slots 1-5 for global pins and 6-9 for the focus context

**Decision:** Number slots 1 through 5 contain persistent user-pinned actions independent of context. Slots 6 through 9 contain the top four actions for the selected focus context. The same action may appear in both groups. Action display and search include optional technology and task metadata alongside context and title.

**Reason:** A small stable personal muscle-memory layer should coexist with context-sensitive recommendations. Separate number ranges make the behaviour predictable while still adapting to the current task.

**Consequences:** Palette state is stored separately in `data/palette.json`. Selecting a focus context updates slots 6-9 but never changes slots 1-5. Search may show duplicate rows when one action occupies both a pinned and a context slot. The existing action preview remains unchanged.
## 2026-07-11 - Separate action explanation from the Input / Output workspace

**Decision:** Action explanations appear temporarily as tooltips near the selected result. The former permanent preview area becomes an editable Input / Output workspace shared by captured selections, pasted clipboard text, typed input, and transformation output.

**Reason:** Preview text and working data serve different purposes. A persistent working field enables transformations and inspection while a nearby tooltip still explains actions without consuming permanent space.

**Behaviour:** Transformations read and replace Input / Output and may copy the result. Copy-only actions leave the workspace unchanged. Selection-consuming URL actions use workspace text when present. Direct paste back to the previous foreground application will be an explicit separate action behaviour.

**First transformation:** Convert non-empty lines into a comma-separated SQL string list, escaping embedded single quotes.
## 2026-07-11 - Use structured metadata when creating actions from Inbox

**Decision:** Inbox conversion collects Technology, Task, Context, and Action name as separate fields. Context defaults to the current focus context. Existing values are editable suggestions, and the form previews the composed display name.

**Reason:** The launcher displays and searches all four dimensions, so asking only for Context creates incomplete actions and inconsistent defaults. The four fields are facets, not one hierarchical context string.

**Current boundary:** The first structured form creates `copy_text` drafts. Selecting other action types and showing type-specific output previews remains a next step.
## 2026-07-12 - Improve visual guidance without adding UI dependencies

**Decision:** Keep the native Tkinter interface and guide scanning through stronger spacing, typography, grouped controls, a prominent focus-context bar, a primary Run button, and colour-coded slot families.

**Reason:** Speed remains the highest priority. A heavier UI framework would increase startup and packaging cost, while the main usability problem can be addressed through hierarchy and consistent visual meaning.

**Visual mapping:** Blue rows represent persistent slots 1-5, green rows represent focus-context slots 6-9, and neutral rows are ordinary search results. Input / Output is a separate labelled workspace and management controls remain secondary.

**Consequences:** No dependency or additional startup work is introduced. Dark-theme adaptation and further polish remain subject to manual testing on the target Windows environment.
## 2026-07-12 - Use native monitor detection and relative window layouts

**Decision:** Implement constrained `window_layout` actions with Windows APIs through Python's standard-library `ctypes`. Layouts use relative coordinates and provide separate one-screen and multi-screen variants.

**Reason:** This keeps context workspace activation portable, fast, dependency-free, and adaptable to different resolutions. Relative work-area coordinates avoid hard-coding laptop-specific pixels.

**First scope:** Open three new Explorer windows and position them. The example places one full-screen Explorer on the primary monitor and two half-screen Explorers on the second monitor, with a three-column single-screen fallback.

**Verification:** The first manual test detected two screens and successfully opened and arranged all three Explorer windows.

**Later:** Capture current layouts interactively, match existing non-Explorer application windows safely, handle additional DPI edge cases, and optionally support FancyZones as an adapter.
## 2026-07-12 - Capture current window situations as restorable Draft actions

**Decision:** Add a `Snapshot` command that records visible, non-minimized ordinary application windows using executable path, window class, title, monitor, and relative work-area coordinates. Saving creates a `restore_window_snapshot` Draft action in the current focus context.

**Reason:** Recording an arrangement is faster and more accessible than manually authoring coordinate JSON. Matching before moving keeps restoration constrained and inspectable.

**Current boundary:** Restoration repositions matching open windows and attempts to restart missing ordinary desktop applications. It does not reconstruct specific documents or browser URLs/tabs unless explicit launch metadata is added later. Packaged or protected applications may not restart from their captured executable path.

**Verification:** A manual round-trip captured and restored 11 open windows across the current desktop with no unmatched windows.

**Matching correction:** Window titles are preferences rather than hard requirements because browser and document titles change. Context Palette and technical Windows shell windows are excluded. Re-testing an older snapshot restored seven eligible windows, launching six that had been closed; one packaged/protected application remained unrestorable.
## 2026-07-12 - Enrich snapshots with launch URLs and foreground state

**Decision:** Record whether a captured window was foreground and restore that foreground window last. Prompt for an optional launch URL for each browser window and store it as explicit launch metadata.

**Reason:** Position and executable alone cannot reconstruct a useful browser workspace. Standard Win32 window enumeration exposes titles but not tab URLs. Asking for URLs avoids invasive focus switching and clipboard replacement during capture.

**Boundary:** Background Z-order is recorded indirectly by enumeration but is not actively restored yet. Exact browser tab groups, navigation history, and unsaved document state remain outside a generic window snapshot.
## 2026-07-12 - Keep help local, searchable, and available at the point of use

**Decision:** Maintain the user guide as `docs/HELP.md`, show it in a searchable in-app Help window, and attach concise documented tooltips to every primary main-window button.

**Reason:** Users need both quick explanations during work and a complete reference. Reading one local Markdown file keeps help portable, inspectable, fast, and free of web or packaging dependencies.

**Consequences:** Button tooltips describe input, effect, and important boundaries. Detailed procedures and troubleshooting live in one source document that is accessible both inside and outside the app.
## 2026-07-12 - Maintain a current architecture source of truth

**Decision:** Keep `docs/ARCHITECTURE.md` as the current technical description of modules, runtime flows, storage, Windows integrations, safety constraints, tests, limitations, and extension rules. Continue using `DECISIONS.md` for chronological rationale.

**Reason:** README and decision entries alone cannot provide a coherent current-system view as the prototype grows. Separating current architecture from historical decisions makes maintenance and future collaboration safer.
## 2026-07-12 - Separate shared configuration from per-machine runtime data

**Decision:** Keep reviewed portable actions in tracked `data/actions.json`. Store new personal and machine-specific actions in ignored `data/local_actions.json`. Ignore Inbox, palette state, and snapshots, while tracking safe `.example.json` templates.

**Reason:** GitHub and multi-PC development require source and intentional shared configuration to travel without leaking captured text, personal URLs, local window titles, executable paths, monitor layouts, or per-PC preferences.

**Consequences:** Inbox conversion, cheat-sheet promotion, and snapshot creation write actions locally by default. Sharing an action becomes an explicit review step. Shared actions use environment placeholders for portable paths.

## 2026-07-12 - Provide repeatable Windows setup and CI

**Decision:** Add `setup-context-palette.bat` for local venv/runtime initialization and a Windows GitHub Actions workflow using Python 3.12.

**Reason:** A clone should become usable without reconstructing this machine's Codex-specific Python environment. Automated Windows tests catch portability regressions for source changes.

## 2026-07-13 - Share reviewed work lookup templates explicitly

**Decision:** Track the reviewed product-system URL builders and Archive/ServiceNow reference-prefix sheet so they are available on both development and work PCs. Each product destination is a separate Draft action. ServiceNow remains reference-only until its complete URL template is known.

**Reason:** These actions are useful portable configuration rather than captured runtime state. Separate actions keep execution predictable and searchable while allowing four common destinations to occupy the focus slots.

**Privacy boundary:** This exception was explicitly approved for GitHub synchronization. The tracked values contain internal host names and example reference shapes, but no credentials, access tokens, personal identifiers, captured clipboard content, or machine paths. Runtime data remains ignored.

## 2026-07-13 - Keep fast text manipulation inside Tkinter

**Decision:** Extend the existing Input / Output `Text` widget with pure Python transformations rather than adopting QScintilla. Remove the workspace heading, expose transformations through both the context menu and one compact `⋮` button, apply them to the selection or complete field, and copy every result automatically.

**Reason:** The required high-frequency operations do not need a programmer-editor component. QScintilla depends on PyQt/Qt, cannot be embedded naturally in the current Tkinter widget tree, adds installation and packaging weight, and introduces GPL/commercial licensing considerations. The dependency-free implementation preserves fast resident startup and work-PC portability.

**First operations:** lowercase, UPPERCASE, normalize consecutive horizontal spaces, add a prefix/suffix to every line, and remove duplicate lines while preserving first-occurrence order.

## 2026-07-13 - Make action rows command-first and narrow the palette

**Decision:** Render launcher rows as `Command → subject` and remove the trailing context from the permanent list text. Infer a command from the constrained action type only when the title has no recognized leading command. Show Context, Technology, Task, and the original title in a delayed row tooltip. Reduce the default window width from 720 to 520 pixels and arrange all ten management buttons in two rows of five.

**Reason:** Command-first rows are faster to scan and eliminate repeated context text. The previous wide listbox had no separate right pane; narrowing the complete window returns that unused screen area while the two-row button grid preserves direct access to every function.

## 2026-07-13 - Use the right half as a global command surface

**Decision:** Restore a wider two-column launcher and use its right half for JSON-configured global quick-action groups. Each group contains multiple compact labels. Left-click opens the label's owning menu configuration and corresponding action file; right-click exposes its executable action-ID menu. Groups are independent of Focus context and shared/local configuration is separated.

**Reason:** The intended empty area was not screen space to remove but room for persistent utilities. Referencing existing action IDs keeps this surface customizable without creating a second or less constrained execution mechanism.

**Boundary:** The first version is configured upfront in JSON. An in-app visual editor, context-conditional groups, drag ordering, and richer controls remain future refinements.

## 2026-07-13 - Anchor F9 opens at the cursor

**Decision:** Treat the cursor coordinates captured at F9 as the desired top-left corner of the palette. Clamp that position only when the window would cross the selected monitor's work-area edge.

**Reason:** A fixed anchor is more predictable than adding a gap or flipping the window around the cursor. It makes the shortcut feel like placing the palette exactly where attention is focused.

## 2026-07-13 - Read clipboard text only for clipboard templates

**Decision:** Template expansion calls the clipboard getter only when an action value, argument, or working directory contains a supported clipboard variable.

**Reason:** Ordinary file, folder, URL, and application targets do not depend on clipboard text. Eager clipboard reads caused unrelated actions—including opening command-surface configuration—to fail when the clipboard held an image or another non-text format.

## 2026-07-17 - Make command-surface left click execute actions

**Decision:** Change command-surface item interaction so ordinary left-click executes the item's primary available action. Keep right-click as the explicit action-selection menu. Preserve configuration access through Shift+click or Ctrl+click on an item label.

**Reason:** The surface is presented as quick action buttons. Requiring right-click for execution made routine use feel non-functional and added avoidable friction. Modifier-assisted configuration retains direct access to JSON editing without sacrificing fast execution.

## 2026-07-18 - Configure personal actions, contexts, and buttons through one guided window

**Decision:** Add a Configure window beside the Focus selector. Action creation begins by choosing a built-in action type and reviewing its input, output, and portability guidance. The same window edits personal contexts and their slots 6–9, plus personal right-side buttons and their action references.

**Reason:** Routine configuration should not require understanding several JSON files or remembering action-type identifiers. Starting with the executable action catalogue keeps the UI aligned with validation and makes effects visible before a Draft is created.

**Boundary:** Shared project examples are visible but read-only. Personal actions of every built-in type are editable; their stable identity and Draft/Trusted state are preserved. Technical context, action, group, and button IDs remain internal references and are generated automatically where the user should not need to manage them.

## 2026-07-18 - Prioritize the find, run, and repeat-action journey in the interface

**Decision:** Standardize the launcher and secondary windows around a neutral high-contrast theme, explicit pane headings and counts, compact consistent spacing, native keyboard focus, actionable empty states, human-readable action choices, and non-blocking success feedback. Keep text labels on important controls and use native Tk widgets rather than adding an icon or animation dependency.

**Reason:** The primary user needs to identify an action quickly, run it with minimal attention, and turn repeated work into a context-specific action. Visual competition, blank states, hidden keyboard behavior, and internal IDs add friction to that journey.

**Accessibility boundary:** Tkinter does not provide web ARIA attributes. Accessibility uses native Windows controls, visible labels, predictable tab order, focus borders, keyboard equivalents, strong contrast, and status text. Decorative animation is omitted because configuration loads locally in under a second and motion would add delay without useful state information.

## 2026-07-18 - Optimize the resident hot path without adding infrastructure

**Decision:** Detect unchanged configuration before reload, coalesce typed search changes briefly, audit stable main-window tooltips once, and move only long-running window layout/restore work to one background worker. Add a bounded ignored diagnostic log and keep the existing 100 ms main-thread queue drain.

**Reason:** Showing and searching the palette must remain immediate over long resident sessions. Rebuilding unchanged widgets, recurring widget-tree traversal, and multi-second restore waits on the Tk thread are avoidable costs. A database, cache service, async framework, or broad UI refactor would cost more maintainability than it saves.

**Consequences:** External JSON edits remain detectable through file signatures. Date/clipboard-dependent action expansion is never cached. Tk widgets remain main-thread-only. Window actions reject concurrent execution and report completion through the existing queue poller.
