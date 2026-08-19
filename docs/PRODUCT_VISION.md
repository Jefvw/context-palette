# Product vision

This document describes durable direction. It is not a claim that every capability exists. Current status is defined by [MVP](MVP.md), current implementation by [Architecture](ARCHITECTURE.md), and sequencing by [Roadmap](ROADMAP.md).

## Problem

Snippet and shortcut tools become difficult to scan and maintain as their collections grow. Work is naturally divided into contexts—database work, reporting, communication, analysis, projects—but a flat list does not carry the relevant terminology, references, tools, or repeated procedures.

Configuration also becomes inaccessible when routine changes require editing opaque command strings or technical identifiers.

## Product concept

Context Palette is a portable Windows application that organizes reusable work around explicit contexts and constrained actions.

The intended experience has two equally important modes:

- **Use:** choose a focus, find an Action or Work Item, understand its effect,
  and invoke it quickly.
- **Build:** capture or drop useful material during real work, confirm a
  constrained action, and edit it directly whenever the workflow changes.

```text
Capture or configure → Confirm → Active → Archived
```

Archived material leaves normal retrieval without being silently destroyed.

## Context model

The long-term context model has four dimensions:

| Dimension | Purpose | Current status |
| --- | --- | --- |
| Identity | Name, description, and intended use | Implemented |
| Knowledge | References, terminology, examples, and cheat sheets | Partly implemented |
| Capabilities | Preferred actions and transformations | Implemented at a basic level |
| Activation | Visible bundle of reviewed applications, folders, files, URLs, and references | Proposed |

One context is the explicit focus. Supporting contexts may contribute knowledge or ranking in the future, but they must not make action retrieval unpredictable or switch focus silently.

Every Action and available Work Item is visible through the General root.
Specific Context membership is owned by the user's Context definitions, so each
PC can organize Built-in Actions, personal Actions, and personal Work Items
without editing shipped Action records or external folders. Free-form tags
provide quick cross-context discovery without turning classification into a
fixed hierarchy.

When the user explicitly selects a specific Focus, ordinary global discovery
groups matching Focus members before other matches. It does not remove global
results, silently infer a different Focus, or use an unexplained relevance
score. This deterministic ordering makes Focus useful during normal retrieval
while preserving the General root as the complete collection.

## Explicit effects

An action should make its inputs and effects understandable:

- whether it reads selected text, Input / Output, clipboard text, prompted fields, or no input;
- whether it copies or transforms text;
- which URL, file, folder, application, or layout it opens;
- whether it changes window placement;
- what remains recoverable after failure.

The selected item should express that contract before invocation in a stable
**Input → Effect** summary. Current input availability and safe fallback or
stop behavior belong in the immediate summary; configured values, recovery,
and limitations remain available as structured details.

This principle is more important than matching the command language of an older automation tool.

## Capability direction

Context Palette may grow through five families:

1. Previewable selected-text transformations.
2. Visible context workspace activation.
3. Constrained linear form-filling sequences.
4. Clipboard transactions that preserve and restore prior content.
5. Rich-content and image actions with format-aware previews.

The first family, constrained window preparation, and reference-based launch
sequences are implemented. Protected credential paste provides the first
text-only clipboard transaction; sequence paste/key steps, other clipboard
effects, and rich formats remain proposals until their recovery and trust
behavior is designed. Optional local OCR now provides the first bounded
image-derived text workflow without treating images as persistent Actions or
forcing image data through the launch-sequence model.

## Knowledge and cheat sheets

Searchable structured cheat sheets are implemented. They keep shortcuts,
reference notes, and procedures available without opening a browser, and
individual entries can become permanent Active actions after confirmation.
Because this is secondary reference retrieval rather than frequent execution,
Sheets is reached from Help instead of consuming a fixed Quick-action position.

Frequently executed credentials, folders, and prompts are first-class actions.
Their fixed launcher menus derive membership from action type and derive
optional nesting from the action's own Quick menu path, preserving one source
of truth as those action collections grow.

Future work may add richer context knowledge, maintenance queues, and attended
AI assistance. AI assistance remains reviewable: the user sees what leaves the
application, responses are treated as untrusted, and selected actions are saved
permanently only after confirmation.

## Product principles

1. **Fast first:** repeated use must feel immediate.
2. **Contextual, not hidden:** explicit focus improves relevance without silent automation.
3. **Explicit effects:** powerful Windows targets remain visible and
   user-configured; the app does not invent or parse a compound command language.
4. **Local ownership:** ordinary user organization lives in My configuration
   files on one PC; Built-in files contain only reviewed starter data.
5. **Confirm before persistence:** generation and capture never save an action
   until the user confirms it.
6. **Portable by default:** user-writable Windows folders, no administrator requirement.
7. **Progressive complexity:** ordinary configuration uses names and guided forms; advanced JSON remains reviewable.
8. **Recoverable changes:** persistence and future multi-step behavior should define failure recovery.
9. **No framework for its own sake:** add dependencies only when product value outweighs portability and maintenance cost.
10. **Compact screens:** keep labels beside fields where practical, reserve
    permanent space for current values and decisions, and move supplementary
    explanations into keyboard-accessible tooltips or on-demand help.

## Success

The product succeeds when a user can:

- retrieve a repeated action in seconds;
- understand what it will read and do;
- add a useful personal action without managing technical IDs;
- keep stable muscle-memory actions while changing work focus;
- capture improvements during real work without interrupting the task;
- transfer reviewed portable configuration without leaking personal runtime data;
- maintain the system as the number of contexts and actions grows.

## Long-term exclusions

- Opaque arbitrary command execution.
- Unattended execution of unreviewed actions.
- Mandatory cloud accounts or services.
- Silent context switching.
- Automatic publication of captured or machine-specific data.
