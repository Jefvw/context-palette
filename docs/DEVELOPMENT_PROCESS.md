# DEVELOPMENT_PROCESS.md

# Development Process

This project is developed iteratively.

The objective is **not** to build the perfect application immediately.

The objective is to continuously improve both the application and the process used to create contexts.

---

# Core Principle

The application should develop in exactly the same way that users develop their own contexts.

Every reusable idea should move through the same lifecycle:

```
Idea
↓
Capture
↓
Draft
↓
Test
↓
Refine
↓
Trusted
↓
Review
```

The software itself should be built using this philosophy.

---

# Development Philosophy

Prefer:

* many small improvements
* working software
* frequent testing
* simple solutions
* documentation kept current

Avoid:

* large rewrites
* unnecessary abstraction
* premature optimization
* building infrastructure for features that do not yet exist

---

# Session Workflow

Every development session follows the same sequence.

## Step 1 — Understand

Before writing code:

* understand the request
* inspect the current project
* inspect existing documentation
* identify affected files

Never start coding immediately.

---

## Step 2 — Clarify

Summarize:

* what will be built
* why it is needed
* possible alternatives
* chosen approach

If assumptions are made, state them explicitly.

---

## Step 3 — Design

Think in terms of the smallest useful increment.

Ask:

"What is the smallest version that provides value?"

Avoid designing future features unless necessary.

---

## Step 4 — Implement

Keep changes small.

Prefer modifying existing code over creating new frameworks.

One logical feature per implementation.

---

## Step 5 — Test

Every feature must be tested.

Testing can be:

* automated
* manual

Manual testing instructions must always be provided.

---

## Step 6 — Document

Update documentation immediately.

Never postpone documentation.

Update when necessary:

* README
* DECISIONS
* BACKLOG
* MVP
* PRODUCT_VISION

---

## Step 7 — Review

After implementation explain:

* what changed
* why
* limitations
* future improvements

---

# Feature Lifecycle

Every feature begins as an idea.

## Idea

An observation during daily work.

Example:

"I explain SQL queries repeatedly."

Ideas are not immediately implemented.

---

## Capture

Record the idea quickly.

Minimal information:

* title
* description
* source
* date

Store in the Inbox.

---

## Draft

Transform the capture into something structured.

Possible outputs:

* action
* snippet
* prompt
* workflow
* context
* business rule

---

## Prototype

Create the smallest possible implementation.

Ask:

"Can this be demonstrated?"

Avoid trying to solve every edge case.

---

## Test

Use the feature in real work.

Observe:

* usefulness
* friction
* missing capabilities
* unnecessary complexity

---

## Refine

Improve only after real usage.

Do not optimize speculative problems.

---

## Trusted

A feature becomes trusted only after repeated successful use.

Trusted features become part of the normal workflow.

---

# Context Development Process

Contexts evolve continuously.

## Capture

Capture:

* prompts
* SQL
* emails
* procedures
* snippets
* terminology
* business rules

---

## Organize

Assign captures to contexts.

Examples:

Database

Email

Analysis

Programming

Temporary Project

---

## Refine

Improve wording.

Remove duplication.

Split overly large contexts.

---

## Promote

Frequently used drafts become trusted actions.

---

## Archive

Unused contexts should be archived rather than deleted.

---

# Coding Principles

Prefer:

simple

readable

maintainable

portable

predictable

Avoid:

clever code

deep inheritance

premature abstraction

large dependencies

---

# Architecture Growth

The architecture should grow naturally.

Current order:

1. Launcher

2. Contexts

3. Actions

4. Inbox

5. Drafts

6. Testing

7. Search

8. LLM integration

9. Workflows

Do not skip steps.

---

# Documentation Rules

Whenever something important changes:

record

* why

* consequences

* alternatives

Never rely on memory.

---

# Technical Decisions

Every important decision belongs in DECISIONS.md.

Each decision should contain:

Date

Decision

Reason

Alternatives

Consequences

---

# Backlog

BACKLOG.md represents future work.

Completed items are removed or marked complete.

Never let the backlog become a wish list.

Prioritize.

---

# Role of Codex

Codex is an implementation partner.

Before coding Codex should:

* inspect documentation
* explain the approach
* identify affected files

After coding Codex should:

* explain changes
* update documentation
* provide testing instructions
* suggest the next smallest improvement

---

# Role of the User

The user provides:

* ideas
* priorities
* testing
* workflow knowledge

The user is not expected to know software architecture.

---

# Success Criteria

A development session is successful when:

* the application still runs
* one useful improvement has been completed
* documentation is updated
* testing instructions are available
* the next step is obvious

---

# Guiding Question

Every feature should answer one question:

**"Does this make capturing, developing, testing, organizing, or using contexts easier?"**

If the answer is no, the feature should probably not be built.
s