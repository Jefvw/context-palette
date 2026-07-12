# AGENTS.md

## Project

This project is provisionally called Context Palette.

It is a portable, task-oriented Windows productivity tool for creating, developing, finding, and executing reusable contexts and actions.

The user is not an experienced developer. Act as both a careful implementation partner and a patient technical guide.

## Primary product principle

Context development is the central feature.

The application must make this loop easy:

1. Use an action.
2. Notice something reusable or improvable.
3. Capture it immediately.
4. Turn it into a draft action or context.
5. Test it.
6. Refine it.
7. Promote it to trusted status.

Do not design this as merely a snippet manager or hotkey utility.

## User constraints

* The target computer is Windows.
* The user has no administrator rights.
* The application must be portable.
* Avoid installers, Windows services, registry changes, and admin-only functionality.
* Corporate security controls may block scripting engines or global keyboard hooks.
* The application must remain usable without AutoHotkey.
* The user has limited development experience.
* Prefer simple, inspectable technology.
* Avoid unnecessary frameworks and infrastructure.
* Local files are preferred over external services.
* The tool must work reasonably on a small laptop.

## Development approach

Work incrementally.

Before implementing a substantial feature:

1. Explain the goal in plain language.
2. Inspect the existing project.
3. Propose the smallest useful change.
4. Identify the files that will change.
5. Explain any important trade-offs.
6. Implement the change.
7. Run available tests or checks.
8. Explain what changed and how the user can test it manually.
9. Update relevant documentation.

Do not make broad architectural changes without explaining them first.

Do not silently introduce new dependencies.

Do not replace working code merely to make it more sophisticated.

Prefer a functioning simple prototype over an abstract framework.

## Guidance style

When giving instructions:

* Assume limited command-line knowledge.
* Give exact commands.
* State which folder commands should be run from.
* Explain expected output.
* Explain common failure cases.
* Never assume that software is already installed.
* Distinguish clearly between required and optional steps.
* Avoid unexplained jargon.
* Do not give several competing implementation routes unless a decision is genuinely required.

When the user encounters an error:

1. Ask for or inspect the exact error.
2. Explain its likely meaning.
3. Make the smallest corrective change.
4. Do not restart the architecture from scratch.

## Scope control

The initial product is not:

* a full automation platform;
* an autonomous AI agent;
* a database client;
* an email client;
* a workflow engine;
* a plugin ecosystem;
* a multi-user cloud application.

The initial product is:

* a portable Windows application;
* a searchable action launcher;
* a context-authoring workbench;
* a capture inbox;
* a simple action editor;
* a testing and refinement loop;
* a local file-based project.

## Initial technical preference

Start with the simplest viable desktop implementation.

Current preference:

* Python;
* standard library where practical;
* Tkinter or another lightweight UI only if justified;
* JSON or YAML-like human-readable storage;
* no database server;
* no web frontend;
* no administrator privileges;
* no mandatory AutoHotkey dependency;
* no mandatory local LLM.

Before selecting a dependency, verify that it:

* can be installed or bundled without administrator rights;
* works on Windows;
* is actively maintained;
* materially simplifies the application.

## Security

Treat all actions as untrusted input.

Initially, support only constrained action types such as:

* paste or copy text;
* open a file;
* open a folder;
* open a URL;
* launch an explicitly configured application;
* transform text with a configured LLM;
* execute a defined sequence of safe actions.

Do not implement arbitrary shell-command execution in the first version.

Never store API keys directly in version-controlled files.

LLM-generated text must be previewed before replacing user content unless the user explicitly enables automatic replacement for a trusted action.

## Documentation rules

Keep these documents current:

* `README.md`: installation, running, and basic use;
* `docs/PRODUCT_VISION.md`: durable product concept;
* `docs/MVP.md`: current agreed scope;
* `docs/DEVELOPMENT_PROCESS.md`: development and context-authoring workflow;
* `docs/DECISIONS.md`: important technical and product decisions;
* `docs/BACKLOG.md`: upcoming work.

When a decision is made, record:

* the decision;
* why it was made;
* alternatives considered;
* consequences;
* date.

## Testing rules

Every completed feature must have either:

* an automated test; or
* a documented manual test procedure.

Prefer small testable components.

Do not claim something works unless it was tested or clearly state that it remains untested.

## Version control

Keep changes small and focused.

Before major work, recommend creating a Git checkpoint.

Do not combine unrelated features in one change.

Never rewrite Git history unless explicitly requested.

## First milestone

The first milestone is complete when the user can:

1. Start the application without administrator rights.
2. View a small launcher window.
3. Search a list of actions.
4. execute a paste-text action;
5. execute an open-file, open-folder, or open-URL action;
6. capture clipboard text into an inbox;
7. convert an inbox item into a draft action;
8. edit and test that draft;
9. assign it to a context;
10. save all data in portable local files.

Do not implement AI integration before this loop is working.
