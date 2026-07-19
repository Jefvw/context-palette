# AI Collaboration Guide

This repository is intentionally prepared for collaboration with Codex and other AI coding assistants.

## Read first

Before changing code, read:

1. `docs/ARCHITECTURE.md` — current implementation and boundaries.
2. `docs/PRODUCT_VISION.md` — durable product direction.
3. `docs/MVP.md` — current agreed scope.
4. `docs/DECISIONS.md` — chronological rationale.
5. `BACKLOG.md` — planned work.

Detailed development guidance also exists in `docs/AGENTS.md` and `docs/DEVELOPMENT_PROCESS.md`.

## Product constraints

- Target Windows without administrator rights.
- Keep the application portable and fast.
- Prefer Python standard library and Tkinter.
- Do not introduce a dependency without verifying portability and explaining why it is necessary.
- Do not implement arbitrary shell-command execution.
- Keep actions constrained, previewable, and testable.
- Preserve the Capture -> Draft -> Test -> Refine -> Trusted lifecycle.

## Data ownership

Shared, reviewable examples belong in tracked files such as `data/actions.json` and `data/*.example.json`.

Never commit personal/runtime data:

- `data/inbox.json`
- `data/local_actions.json`
- `data/local_command_surface.json`
- `data/local_contexts.json`
- `data/palette.json`
- `data/layouts/snapshots/`
- `data/context-palette.log*`

Snapshots can contain window titles, executable paths, URLs, and other private working context.

Do not move local user data into tracked examples without explicit user approval and a privacy review.

## Development commands

From the repository root:

```powershell
.\setup-context-palette.bat
.\.venv\Scripts\python.exe -m unittest discover tests
.\run-context-palette.bat
.\stop-context-palette.bat
```

Use `.\check-context-palette.bat` for the complete configuration, compilation, and test check.

## Change rules

- Inspect existing changes before editing; they may be user-owned.
- Keep changes focused and update tests.
- Update `docs/ARCHITECTURE.md` when implementation structure changes.
- Add a dated entry to `docs/DECISIONS.md` for important choices.
- Update `docs/HELP.md` for user-visible behavior.
- Update README, MVP, and Backlog where appropriate.
- Update `CHANGELOG.md` for user-visible changes.
- Do not rewrite Git history, delete user data, push, or publish without explicit authorization.

## Completion checks

Before handing off:

1. Run all tests.
2. Run `git diff --check`.
3. Confirm runtime/personal files are not staged.
4. Clearly separate automated verification from manual Windows UI verification.

## Efficient Codex execution

- Read only the documentation sections relevant to the current task.
- Combine related edits into one focused patch whenever practical.
- Combine independent repository checks and final verification commands.
- Do not repeat a successful check unless later changes invalidate it.
- Use targeted tests while editing, then run the required complete suite once.
- Do not restart the GUI unless runtime behavior changed or the user requests it.
- If a file-edit operation takes more than 10 seconds, report its elapsed time
  and do not retry the identical edit unless it failed.
- Distinguish Codex tool latency from measured Windows filesystem latency.

## Application improvement iterations

The user is a non-developer and may request an autonomous maintenance iteration
with a short command such as `Improve: reliability`. Treat these commands as a
request to investigate, implement, verify, and report one focused improvement;
do not stop after producing a plan unless a decision only the user can make
genuinely blocks progress.

### Shared operating contract

When asked to run an application improvement iteration:

1. Act as the senior engineer responsible for this application.
2. Inspect the repository, relevant documentation and configuration, current
   working-tree changes, recent relevant work, and available tests. Build enough
   understanding for an evidence-based decision; do not assume every file needs
   equal analysis.
3. Select the single highest-value safe improvement within the requested mode.
   Preserve intended functionality and product scope. Keep the change focused,
   incremental, and consistent with the existing architecture.
4. Before editing:
   - state the selected improvement and cite concrete evidence;
   - explain why it has the best return on effort in this mode;
   - name the strongest alternatives considered and why they were deferred;
   - state how the change will be verified.
5. During implementation:
   - preserve unrelated and uncommitted user changes;
   - do not invent product requirements;
   - avoid speculative cleanup, broad rewrites, breaking changes, migrations,
     and new dependencies unless clearly necessary;
   - add or update tests when appropriate.
6. Verify with the most relevant available tests, checks, builds, and focused
   manual inspection. Fix regressions caused by the change. Clearly distinguish
   automated verification, manual verification, and anything still uncertain.
7. If the selected change proves unsafe, unnecessary, or unverifiable, do not
   force it. Select the next-best safe improvement in the same mode.
8. At completion, report:
   - what changed and why it matters;
   - files affected;
   - verification performed and results;
   - remaining limitations or risks;
   - the next highest-value improvement in the same mode.

### Short improvement modes

The following commands select the improvement mode:

- `Improve: reliability` — fix the most consequential evidence-backed bug,
  failure mode, data-integrity risk, or error-handling weakness. Prefer a
  reproducible issue or failing test. Do not add features.
- `Improve: UX` — improve the highest-friction existing user journey without
  adding a product feature. Prioritize confusing states, poor feedback,
  preventable errors, responsiveness, and accessibility.
- `Improve: testing` — protect the most critical behavior lacking meaningful
  automated coverage. Add the smallest robust regression test; change
  production code only when the test exposes a real defect.
- `Improve: security` — remediate the highest-confidence security or privacy
  weakness supported by repository evidence. Do not perform destructive or
  external security testing.
- `Improve: accessibility` — fix the highest-impact barrier in a critical
  journey, prioritizing keyboard access, focus, labels, contrast, motion, and
  error communication.
- `Improve: performance` — improve a demonstrated bottleneck in a critical
  path, with a baseline and comparison. If no meaningful bottleneck is
  measurable, improve performance observability instead of guessing.
- `Improve: maintainability` — reduce the most costly complexity, duplication,
  brittleness, or unclear ownership in a frequently changed or critical area,
  while demonstrating preserved behavior.
- `Improve: developer experience` — remove the largest evidenced obstacle to
  safely understanding, setting up, running, testing, debugging, or modifying
  the application.
- `Improve: regression review` — inspect the latest relevant implementation or
  working-tree changes and fix the highest-risk defect, missing edge case, or
  verification gap without expanding scope.
- `Improve: general` — select the single highest-value safe improvement across
  reliability, UX, maintainability, performance, testing, accessibility,
  security, documentation, and developer experience.

`Run the next sensible improvement mode` means inspect recent work, avoid
repeating its focus when another mode has stronger value, choose the next mode,
and follow the same operating contract. A suggested rotation is Reliability,
UX, Testing, Accessibility, Security, Maintainability, Performance, Developer
Experience, Regression Review, then General.
