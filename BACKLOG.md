# Backlog

## Now

- Define contexts as standalone records with identity, knowledge, capabilities, and optional activation.
- Add a context selector/filter and a context detail view.
- Refine the implemented focus-context picker and 1-5 pinned / 6-9 context slot layout after manual testing.
- Refine the Input / Output workspace and tooltip preview after manual testing.
- Refine the lightweight visual hierarchy and slot colour coding after manual testing.
- Build QTP-compatible capabilities incrementally: direct paste and safe Tab/Enter sequences, clipboard slots, then a character picker.
- Improve launcher usability after manual testing.
- Find a reliable way to open or focus Codex on this project.
- Explore a true tray icon without making the app hard to package.
- Add context filtering or grouping in launcher results.

## Done

- Load standalone shared/local context definitions with descriptions and preferred actions for slots 6–9.

- Establish the project structure.
- Choose the minimum portable Python setup.
- Decide the initial storage format.
- Create a launcher-window prototype.
- Add sample actions for the launcher.
- Document manual launcher testing.
- Add arrow-key navigation and number-key execution for launcher results.
- Add a simple read-only action preview.
- Start the capture inbox.
- Display Inbox items in the app.
- Convert an Inbox item into a draft copy-text action.
- Add simple editing for draft copy-text actions.
- Add a way to mark a draft action as Trusted.
- Document the proposed app/topic cheat-sheet JSON format.
- Incorporate the Windows 11 cheat sheet as the first popup sheet.
- Add search inside the cheat-sheet popup.
- Add resident single-instance mode for faster repeated opens.
- Add a way to promote a cheat-sheet item into an action.
- Add QTP-style clipboard, URL-encoding, date/time, calendar-week, and newline variables.
- Add a URL-builder action that captures the selected ID, copies the complete URL, and opens it.
- Add persistent global pins on slots 1-5 and focus-context actions on slots 6-9.
- Add technology and task metadata to action display names and search.
- Add native monitor detection and a constrained Explorer window-layout action.
- Add capture and restore of existing visible window snapshots.
- Capture optional browser launch URLs and the foreground window in snapshots.
- Add searchable in-app help and documented tooltips for all primary controls.
- Replace the permanent preview pane with action tooltips and an editable Input / Output workspace.
- Add a lines-to-SQL-string-list transformation that updates Input / Output and the clipboard.
- Align Inbox draft creation with Technology, Task, Context, and Action name metadata.
- Guide Inbox conversion into copy-text and URL-builder actions with live validation and a fixed visible footer.
- Add a constrained show/context/search bridge and setup guidance for Power Automate Desktop and PowerToys.

## Next

- Add previewable selected-text transformations: case, literal replace, whitespace/line endings, and URL encoding.
- Add clipboard transaction support with preserve/restore as the safe default.
- Add constrained linear sequences for paste, Tab, Enter, waits, and supported open/launch actions.
- Add context activation bundles for URLs, files, folders, applications, and quick-reference material.
- Add an in-app editor for non-text actions and activation bundles.

## Later

- Add rich HTML content actions with plain-text fallback.
- Add image/visual-asset paste actions.
- Add reusable form definitions with prompted fields and validation.
- Add context inheritance/composition after standalone contexts work reliably.
- Add an editor to inspect, include, exclude, and rename windows before saving a snapshot.
- Investigate safe browser-specific URL discovery without focus or clipboard manipulation.
- Extend native layouts from Explorer folders to explicitly matched application windows.
- Add optional application-aware context suggestions; never require automatic switching.
- Global shortcut investigation.
- Optional AutoHotkey adapter.
- Evaluate an independently packaged native PowerToys Run plug-in after the attended integration proves useful.
- Design a Trusted-action external API before allowing unattended Power Automate execution.
- LLM-assisted context authoring.
- Pop-up app cheat sheets.
- LLM-assisted cheat sheet drafts for frequently used programs.
- Application-aware context prioritization.
