# Decisions

Record durable product and technical decisions here.

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
