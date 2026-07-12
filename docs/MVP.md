# Minimum Viable Product

## Goal

Validate the central idea:

> A user can capture something during work, convert it into a reusable action, test it, organize it into a context, and retrieve it through search.

## Required capabilities

### Current prototype status

Implemented in the first prototype:

* Starts from a project-local batch file.
* Keeps a resident instance so repeated opens are fast.
* Opens a small launcher window.
* Uses a compact search-first palette layout.
* Searches sample actions.
* Shows action name and context.
* Supports basic keyboard execution with `Enter`.
* Previews the selected action.
* Copies saved text to the clipboard.
* Opens configured URLs, files, folders, or explicitly configured `.exe` targets.
* Opens VS Code with the Context Palette project through a constrained app-launch action.
* Captures clipboard text into a local Inbox JSON file.
* Displays captured Inbox items in a read-only popup.
* Converts an Inbox item into a draft copy-text action.
* Edits draft copy-text actions.
* Marks draft actions as Trusted.
* Displays the first app/topic cheat sheet in a popup.
* Searches within the selected cheat sheet.
* Promotes a cheat-sheet item into a draft copy-text action.
* Reads action data from local JSON.
* Accepts attended show, context, and search requests from optional Windows automation integrations.

Not implemented yet:

* Choosing non-text action types during Inbox conversion.
* Editing non-text actions.
* Creating or editing contexts as standalone records.
* Editing cheat sheets in the app.
* Searching across all cheat sheets at once.
* A true system tray icon.
* Marking actions Trusted from the UI.
* In-app backup and restore.
* Opening or focusing the Codex desktop app directly on this project.

### Portable startup

* Runs from a user-writable folder.
* Requires no administrator rights.
* Uses no Windows service.
* Does not require registry modifications.
* Can be started without AutoHotkey.
* Provides clear startup instructions.

### Launcher

* Small searchable window.
* Displays matching actions.
* Shows action name and context.
* Supports keyboard navigation.
* Executes the selected action.
* Can also be opened through an ordinary desktop or taskbar shortcut.

### Contexts

* Create a context.
* Rename a context.
* Add a short description.
* Assign actions to a context.
* Filter launcher results by context.
* Include a General context.
* Give a context an optional activation action that opens a constrained bundle of URLs, files, folders, and explicitly selected applications.
* Show the context's actions, cheat-sheet items, expected input, and activation behaviour together.

For the MVP, a context is more than a label. It is a reusable work package with four parts:

1. **Identity:** name, description, maturity, and optional parent context.
2. **Knowledge:** notes, terminology, examples, and cheat-sheet items.
3. **Capabilities:** actions and safe transformations available in that context.
4. **Activation:** an optional linear bundle that prepares the workspace.

### Action types

Version one supports only:

1. Paste or copy saved text.
2. Open a URL.
3. Open a file.
4. Open a folder.
5. Launch an explicitly selected executable.
6. Build a URL from captured selected text, copy it, and open it.
7. Transform selected text with a constrained, previewable operation.
8. Execute a short linear sequence containing only supported safe steps.

Arbitrary command execution is out of scope.

The first transformations are case conversion, literal replacement, whitespace/line-ending cleanup, and URL encoding. The first sequence steps are paste text, Tab, Enter, short waits, and constrained open/launch actions. Sequences have no conditions, loops, or scripts.

### Clipboard safety

* Actions declare whether they read, replace, or temporarily borrow the clipboard.
* Temporary clipboard use preserves and restores the previous content by default.
* The preview explains the clipboard effect before a Draft action runs.
* Sensitive clipboard content is not written to history unless explicitly captured by the user.

### QTP-inspired productivity slices

1. **Selection transformations:** MVP, with preview and explicit confirmation before replacement.
2. **Context/workspace activation:** MVP, limited to a safe linear bundle of supported open/launch actions.
3. **Form filling:** MVP proof of concept using paste, Tab, Enter, and short waits; broader automation remains later.
4. **Clipboard transactions:** MVP infrastructure, with preserve/restore enabled by default for temporary operations.
5. **Rich content and images:** immediately after the core MVP; the MVP data model must allow these future action types without treating them as plain text.

### Capture Inbox

* Capture current clipboard text.
* Give the capture a title.
* Optionally assign a suggested context.
* Save it as an Inbox item.
* Display all Inbox items.

### Draft conversion

* Convert an Inbox item into a draft action.
* Choose the action type.
* Edit its title and content.
* Assign a context.
* Save it.

### Testing

* Preview a text action.
* Test opening a file, folder, or URL.
* Report understandable errors.
* Allow the user to mark a draft as working or needing improvement.

### Maturity

Each item has one of these states:

* Inbox;
* Draft;
* Trusted;
* Archived.

Only Draft and Trusted actions appear in the launcher by default.

### Storage

* Store data locally.
* Use a documented human-readable format.
* Keep user data separate from application code.
* Avoid an external database.
* Handle missing or damaged files without losing unrelated data.
* Include simple backup and restore instructions.

## First sample contexts

### General

* Paste current date.
* Open project folder.
* Open a saved URL.

### Database

* Basic SELECT template.
* Basic CTE template.
* Open database application.

### Email

* Professional greeting.
* Follow-up template.
* Standard signature.

These examples validate the system without requiring AI integration.

## Explicit exclusions

Do not implement these in the first milestone:

* LLM integration;
* AutoHotkey dependency;
* global application-aware profiles;
* database connectivity;
* email connectivity;
* automatic selected-text replacement;
* arbitrary scripts;
* workflows containing branches;
* synchronization;
* user accounts;
* web frontend;
* installer;
* automatic updater.

Automatic selected-text replacement is excluded only when no preview or explicit trusted-action permission is present. Constrained transformations confirmed by the user are in scope.

## Acceptance scenario

The milestone passes when the user can complete this sequence:

1. Start the application.
2. Copy a useful paragraph from another application.
3. Open Context Palette.
4. Capture the clipboard into the Inbox.
5. Name the capture.
6. Convert it into a draft paste-text action.
7. Assign it to the Email context.
8. Preview it.
9. Mark it Trusted.
10. Search for it in the launcher.
11. Execute it.
12. Close and restart the application.
13. Confirm that the context and action remain available.
14. Select a value in another application and run a previewable transformation or URL-builder action.
15. Activate a context and confirm that its configured safe workspace targets open.
16. Confirm that temporary clipboard use does not destroy the previous clipboard content.
s
