# Product vision

This document describes durable direction. It is not a claim that every capability exists. Current status is defined by [MVP](MVP.md), current implementation by [Architecture](ARCHITECTURE.md), and sequencing by [Roadmap](ROADMAP.md).

## Problem

Snippet and shortcut tools become difficult to scan and maintain as their collections grow. Work is naturally divided into contexts—database work, reporting, communication, analysis, projects—but a flat list does not carry the relevant terminology, references, tools, or repeated procedures.

Configuration also becomes inaccessible when routine changes require editing opaque command strings or technical identifiers.

## Product concept

Context Palette is a portable Windows application that organizes reusable work around explicit contexts and constrained actions.

The intended experience has two equally important modes:

- **Use:** choose a focus, find an action, understand its effect, and run it quickly.
- **Build:** capture useful material during real work, turn it into a Draft, test and refine it, then mark it Trusted deliberately.

```text
Capture → Draft → Test → Refine → Trusted
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

Every action is available through the General root and may belong to one or
more specific contexts. Free-form tags provide quick cross-context discovery
without turning classification into a fixed hierarchy.

## Explicit effects

An action should make its inputs and effects understandable:

- whether it reads selected text, Input / Output, clipboard text, prompted fields, or no input;
- whether it copies or transforms text;
- which URL, file, folder, application, or layout it opens;
- whether it changes window placement;
- what remains recoverable after failure.

This principle is more important than matching the command language of an older automation tool.

## Capability direction

Context Palette may grow through five families:

1. Previewable selected-text transformations.
2. Visible context workspace activation.
3. Constrained linear form-filling sequences.
4. Clipboard transactions that preserve and restore prior content.
5. Rich-content and image actions with format-aware previews.

Only the first family and constrained window preparation are currently implemented. The others remain proposals until their preview, recovery, testing, and trust behavior is designed.

## Knowledge and cheat sheets

Searchable structured cheat sheets are implemented. They keep shortcuts, reference notes, and procedures available without opening a browser, and individual entries can become Draft actions.

Future work may add richer context knowledge, maintenance queues, and attended AI-assisted drafting. AI assistance must remain reviewable: the user sees what leaves the application, responses are treated as untrusted, and created actions begin as Drafts.

## Product principles

1. **Fast first:** repeated use must feel immediate.
2. **Contextual, not hidden:** explicit focus improves relevance without silent automation.
3. **Constrained effects:** no arbitrary shell-command action.
4. **Local ownership:** configuration and captured material remain inspectable local files.
5. **Draft before trust:** generation and capture never imply approval.
6. **Portable by default:** user-writable Windows folders, no administrator requirement.
7. **Progressive complexity:** ordinary configuration uses names and guided forms; advanced JSON remains reviewable.
8. **Recoverable changes:** persistence and future multi-step behavior should define failure recovery.
9. **No framework for its own sake:** add dependencies only when product value outweighs portability and maintenance cost.

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
