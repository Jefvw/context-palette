# Context Palette — Product Vision

## Problem

Existing text-expansion and shortcut tools are useful for executing predefined commands, but they become difficult to maintain as the number of snippets and shortcuts grows.

The user works in several distinct contexts, including:

* database querying;
* data analysis;
* interaction with LLMs;
* email management;
* reporting;
* temporary projects.

Each task requires different prompts, snippets, terminology, applications, references, and procedures.

A large undifferentiated collection of hotkeys is difficult to remember and maintain.

Configuration files such as INI files are also inaccessible to users who are not experienced developers.

## Product concept

Context Palette is a portable Windows application that organizes reusable work around contexts rather than isolated hotkeys.

A context represents a type of work or a specific task.

Examples:

* Database;
* Data Analysis;
* Email;
* LLM;
* Revenue Analysis;
* Monthly Reporting;
* Temporary Customer Project.

A context can contain:

* actions;
* text snippets;
* quick cheat sheets;
* prompt templates;
* launch commands;
* business definitions;
* terminology;
* reference notes;
* examples;
* variables;
* development notes;
* recent feedback.

## What a context can do

A context is a reusable work package, not merely a category attached to actions. It combines four dimensions:

### Identity

The context explains what kind of work it represents, when it is useful, its maturity, and how it relates to broader or narrower contexts.

### Knowledge

The context carries the information needed while working: terminology, rules, examples, references, cheat sheets, and lessons captured from previous use.

### Capabilities

The context exposes relevant actions and transformations. These may consume selected text or clipboard content and produce text, URLs, opened targets, or a short safe action sequence.

### Activation

The context may prepare a workspace by opening a constrained set of applications, folders, files, URLs, and its own quick reference. Activation is visible and editable; it is not arbitrary scripting.

```text
Choose context
-> capture current input
-> prepare workspace
-> expose relevant knowledge and actions
-> execute and preview safely
-> capture feedback for refinement
```

## Context input and output

A context can declare inputs such as selected text, clipboard content, prompted fields, a chosen file or folder, or no input. Outputs may include copied or pasted text, a transformed selection, a built URL, an opened workspace, filled form fields, rich content, an image, or a new refinement note.

Inputs and outputs should be explicit in previews so the user can understand what an action will read, change, open, or preserve.

## Productivity capabilities inspired by QuickTextPaste

Context Palette will incorporate five capability families without copying QTP's opaque command syntax:

1. Previewable transformations of selected text.
2. Context activation through safe workspace bundles.
3. Constrained linear form-filling sequences.
4. Clipboard transactions that preserve and restore prior content.
5. Rich-content and image actions with format-aware previews.

These capabilities belong to contexts and use the same Capture, Draft, Test, Refine, Trusted, and Archived lifecycle as other actions.

## App cheat sheets

Context Palette should eventually help the user become productive inside the current application, not only launch actions.

One future feature is a small pop-up cheat sheet for an application or work context. It would show the most useful commands, shortcuts, notes, and reminders for that specific app without opening a browser.

Examples:

* VS Code: project commands, useful shortcuts, common terminal commands, debugging notes.
* Codex: project goal, next task, useful prompts, local run commands.
* Email: tone rules, common replies, follow-up patterns.
* Database tools: query templates, naming conventions, common checks.

These cheat sheets should follow the same lifecycle as actions:

```text
Capture
-> Draft
-> Test
-> Refine
-> Trusted
```

LLM-assisted generation of cheat sheets for frequently used programs is a promising later feature, but it should wait until local contexts, editing, previewing, and trust states are working.

## Two equally important modes

### Use mode

The user opens a launcher, searches for an action, and executes it.

Example:

```text
Database › Explain selected SQL
Database › Insert SELECT template
Analysis › Analyze copied results
Email › Rewrite professionally
```

### Build mode

The user captures, develops, tests, and improves contexts and actions while doing real work.

The user should not need to leave the current task and navigate a complex settings interface merely to record something useful.

## Central workflow

```text
Capture
→ Draft
→ Test
→ Refine
→ Promote
→ Review
```

### Capture

The user records something reusable with minimal interruption.

Possible captured material:

* selected text;
* clipboard content;
* SQL;
* a prompt;
* a useful email response;
* a procedure;
* a business rule;
* an action idea;
* a complete task context.

Captured material enters an Inbox.

### Draft

The user converts captured material into a structured action or context.

A draft may define:

* name;
* description;
* context;
* action type;
* expected input;
* action content;
* expected output;
* test example.

### Test

The user can run the draft with sample input and inspect the result.

The tool records whether the result was:

* useful;
* in need of improvement;
* incorrect.

### Refine

The user can edit the action immediately after use or testing.

The system should preserve the original input, produced output, and user correction when practical.

### Promote

Actions have simple maturity states:

* Inbox;
* Draft;
* Trusted;
* Archived.

Unproven or sensitive actions should require preview.

### Review

The application presents a manageable maintenance queue containing items such as:

* uncategorized captures;
* drafts needing work;
* possible duplicates;
* trusted candidates;
* unused actions.

## Context hierarchy

Contexts may exist at several levels.

### Core

Reusable actions that are broadly applicable.

Examples:

* copy text;
* paste text;
* rewrite;
* summarize;
* open a URL.

### Domain

A general area of work.

Examples:

* Database;
* Email;
* Analysis;
* LLM.

### Task

A recurring, more specific workflow.

Examples:

* Revenue Analysis;
* Monthly Reporting;
* Query Documentation.

### Temporary

A project-specific context that may later be archived.

Examples:

* FY2026 Budget Review;
* Customer Migration Project.

## Context composition

Contexts should be composable.

For example:

* Email may reuse a general Rewrite capability while adding email-specific tone rules.
* Database may reuse Summarize while adding SQL terminology.
* Revenue Analysis may inherit database actions and add business definitions.

Avoid duplicating identical actions across contexts.

## User experience principles

* Search is more important than remembering hotkeys.
* Capture must be faster than organizing.
* Draft material must be separated from trusted material.
* The application must explain its behaviour.
* Actions should be previewable and testable.
* Management should use clear forms rather than raw configuration files.
* Advanced behaviour should remain optional.
* The application must degrade gracefully when global hotkeys or automation are blocked.
* User data must remain portable and inspectable.

## Target environment

* Windows;
* no administrator privileges;
* potentially restrictive corporate environment;
* small laptop;
* no guaranteed developer tools;
* no guaranteed AutoHotkey;
* no guaranteed local LLM;
* portable user-writable folder.

## Non-goals for the first version

The first version will not attempt to provide:

* arbitrary process automation;
* unrestricted scripting;
* autonomous database access;
* autonomous email sending;
* a plugin marketplace;
* cloud synchronization;
* collaborative editing;
* model fine-tuning;
* semantic vector search;
* complex workflow graphs;
* automatic context detection.

These may be reconsidered only after the central capture-development loop has been validated.

## Product success

The product succeeds when the user can progressively build a useful personal system during normal work without the system itself becoming another maintenance burden.
