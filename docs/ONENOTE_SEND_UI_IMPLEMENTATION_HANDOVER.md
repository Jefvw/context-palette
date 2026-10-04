# Implementation prompt: a clearer OneNote Send window

Prepared 2026-10-01. This document prepares the next implementation session.
Creating it does not start implementation or authorize live OneNote access.

Implementation update, 2026-10-03: the single-Send window is implemented and
independently reviewed. The final complete host check passed 1,651 tests with
2 skipped, configuration validation and compilation. See
[the current evidence](TESTING.md#onenote-send-single-button-ui-2026-10-03).
The prompt below remains the design record; do not repeat completed work.
[Live attended acceptance](ONENOTE_SEND_UAT.md) remains pending fresh scope
approval. Nothing was committed/pushed and the live application was not restarted.

The original implementation prompt is retained below as a design record.

---

You are the Product Owner and integration lead for Context Palette in
`D:\dev\context-palette`. Implement the focused OneNote Send UI improvement below.
The owner has agreed to one **Send to OneNote** button instead of separate Review
and Send buttons. Use the existing application colour scheme to make the dialog
clearer and more attractive. Proceed through implementation and verification;
do not stop at another proposal or ask the owner to repeat the history.

## Recover state and preserve existing work

Read `AGENTS.md`, `docs/AGENTS.md`, `docs/DEVELOPMENT_PROCESS.md`,
`docs/CHANGE_GUIDE.md`, and relevant sections of `docs/ARCHITECTURE.md`,
`docs/PRODUCT_VISION.md`, `docs/MVP.md`, `docs/DECISIONS.md`, `docs/HELP.md`,
`docs/TESTING.md`, `docs/DATA_MODEL.md` and `BACKLOG.md`. Inspect branch/HEAD,
recent history, staged and unstaged diffs, and untracked files before editing.

Observed when preparing this prompt: branch `main`, HEAD
`cad02c6ff7666ecb966f444db33f0ecca546214a`, nothing staged, and valuable overlapping
uncommitted OneNote search/Send implementation and documentation. New OneNote
modules and tests are still untracked. Preserve all of them and existing private
`outputs/` content. Recheck these facts rather than trusting this snapshot.

The last recorded complete host check passed **1,630 tests, with 2 skipped**,
configuration validation and compilation on 2026-09-28. This is a baseline, not
verification of your future changes. On 2026-10-01 the owner reported “tested”
and questioned the controls. That statement does not establish every UAT case
or authorize further agent-operated live reads/writes.

Primary owning files:

- `src/context_palette/onenote_send_window.py`: layout, state, consent and results.
- `src/context_palette/onenote_send.py`: normalization, pure plan and write contracts.
- `src/context_palette/style.py`: shared colours, fonts and ttk styles.
- `src/context_palette/launcher.py`, `workspace_panel.py`: entry point, source
  revision notifications and Quit guard; change only if needed.
- `tests/test_onenote_send_window.py`, `test_onenote_send.py`,
  `test_onenote_process.py`, and affected launcher/style/layout tests.

Read the existing process/session/settings modules to preserve their boundaries.
`D:\dev\python-onenote` is a read-only contract reference if needed; do not edit it.

## Scope and appearance

Improve **Send text to OneNote**, not the whole main application. The owner's
main-window screenshot is a reference for the existing teal/neutral visual
language, not a request to redesign it. Do not assume a screenshot is the current UI.

Reuse `COLORS`, fonts and theme setup in `style.py`:

| Role | Existing token/value | Use |
| --- | --- | --- |
| Main action | `accent` / `#087f78` | The single Send button |
| Hover | `accent_hover` / `#066a65` | Primary button hover |
| Background / surface | `#f5f7f8` / `#ffffff` | Quiet background and readable fields |
| Subtle grouping | `topic_header` / `#eef2f4`, `row_light` / `#e8f3f2` | Restrained section backgrounds |
| Text / secondary text | `#1f2933` / `#52616b` | Clear hierarchy |
| Success / warning / error | `#18794e` / `#9a6700` / `#b42318` | Semantic status accent, with words |
| Keyboard focus | `focus` / `#005fcc` | Visible focus indication |

Reference tokens rather than copying hex values into widgets. Prefer existing
`Accent.TButton`/other suitable styles; use narrowly named derived styles for
dialog-specific states so other windows do not change accidentally. Keep disabled
controls readable and distinct from the enabled primary action. Use colour with
text or an icon, never as the sole state indicator. Keep text contrast readable.

Keep the existing `clam` theme and Segoe UI family. No new theme dependency,
global restyling, custom title bar, or DPI-awareness API change. The red title
bar in the screenshot is not a requested application accent. Keep `tk.Text`
where required; standard ttk does not replace the multiline text editor.

## Layout and plain language

Use a compact, resizable layout with consistent 12–16 px outer/section spacing:

1. **Destination**: notebook/section breadcrumb and **Change…** together. Wrap
   long paths when needed; identities remain exact and out of routine UI.
2. **Page**: editable title and complete plain text. Show the actual final title,
   including a wrapping preview if an Entry clips it. A shortened suggested title
   should be identified as an editable suggestion; do not imply the body was
   shortened. Prefer a word boundary when shortening the suggestion. Display a
   useful title count and explain limit failures without silently trimming input.
3. **Current status**: one authoritative banner with a restrained coloured stripe
   or icon. Neutral when ready, amber when attention is needed, green only for a
   verified creation, red for a definite error. A partial/unknown write must clearly
   say that a page may exist. Include **Use current Input / Output** inside the
   input-changed warning. Keep the established Input / Output name.
4. **Commands**: a plain Close button and one accent **Send to OneNote** button at
   bottom right. No separate Review button or mandatory post-success acknowledgement.
   Show **Cancel request** only while busy; explain that cancellation cannot undo
   a page that may already have been created. Put engine selection behind a quiet
   Settings/Change engine control; setup failures must still offer a clear repair.

Give the text area a useful minimum height, then let it expand with the window.
Do not make a very large window mandatory for a short note. Keep complete text
scrollable/selectable and essential controls visible at supported scaling and
small usable window sizes. Reuse existing child-window placement.

**Result details…** appears only after a Send attempt. A completed success becomes
“Page created and verified”; a later edit replaces that current success banner,
while the earlier receipt remains available under details. Unresolved partial or
unknown results must not disappear because the title/source changed. Give them
priority in the status area and retain their full receipts in session memory.
Show **I've checked OneNote** only when an uncertain/partial result needs explicit
acknowledgement. It acknowledges a warning; it must never convert an uncertain
receipt into verified success. Never label that button “Mark as verified”.

Provide sensible tab order, visible focus and initial focus. Escape uses the
existing guarded close path. Ctrl+Enter may invoke Send only when enabled and
must have the same double-click/key-repeat protection as the button.

## Remove the extra click, preserve exact consent

Do not remove the canonical engine plan or weaken its validation. Move technical
checks behind the simpler UI; the visible final page is what the user approves.

- All opening/editing/refresh work stays local. Normalize and validate locally,
  using the existing rules, and visibly present the exact title and complete body
  that would be sent. Preserve Unicode, tabs and blank lines. Opening or typing
  must not launch the engine, probe OneNote, read metadata, or write anything.
  Explicit Change destination retains the existing bounded metadata-read flow.
- On one explicit Send, capture the visible normalized title/body, exact destination,
  source revision, engine identity and **aware UTC confirmation time at the click**.
  Disable/consume this submission before scheduling work. Do not silently normalize
  to different visible content after the click; redisplay legitimate changes and
  require a fresh affirmative action instead.
- Request the pure engine plan in the worker on that explicit action. Validate
  the whole plan, effects and strict canonical equality with the approved snapshot.
  Reject unexpected/altered plans; never accept them merely because their digest
  matches or invite the user to approve an invalid contract.
- Build execution authorization for that validated plan using the original
  click time, with expiry at most 300 seconds later. Readiness, planning and exact
  section rechecks consume this interval; they never renew it. Revalidate the
  current desktop session and exact section/ancestry within the chosen notebook.
  Missing, moved, changed or stale state requires a fresh choice/Send. Never match
  by name, fall back to all notebooks, or create a missing section.
- Source/title/destination/engine changes during preflight invalidate the captured
  authority. No execute call may follow a pre-dispatch cancellation, stale callback,
  mismatch or expiry. Keep Tk operations on the UI thread and one worker in flight.
- Issue at most one execution request per affirmative gesture. Never auto-send
  after planning, edits, reopen, error acknowledgement or retry. After completion,
  equal content may be sent again intentionally, with a fresh gesture and authority;
  held keys or stale callbacks must not count as that gesture.

Preserve all five commit states, known partial page IDs, strict mutation-envelope
parsing, exact acknowledgements, output bounds and privacy. After possible dispatch,
a lost/malformed reply or cancellation remains unknown unless a valid terminal
receipt gives a more precise outcome. Closing, source changes and stale generations
must not erase it. Preserve bounded owned-process cleanup and its blocking latch,
the separate 30-second read / 45-second write allowances plus bounded cleanup,
and Close/Quit guards. Do not terminate the user's OneNote process.

No automatic retry, rollback, deletion, navigation, OneNote startup/synchronization,
append, tables, attachments or existing-page updates. Input / Output and clipboard
stay intact. Keep private Send destination settings separate from search, retain
explicit-engine precedence and repair behavior, and preserve all search behavior.
No personal data, sent text, plans, authority timestamps or receipts go into Git,
normal logs, configuration backups or persistent history.

## Verification and handoff

Use one writer for overlapping files. A bounded independent read-only review of
the new consent/state transitions is worthwhile; the integration lead must inspect
the actual diff and test evidence. Avoid parallel cosmetic and state-machine writers.

Update synthetic tests for the visible normalized snapshot, no calls on open/edit,
automatic pure planning after Send, plan mismatch/expiry, source/engine/destination
changes, double-click and keyboard repeat, intentional second sends, cancellation
before/after dispatch, stale callbacks, all five results, acknowledgement semantics,
retained IDs, and close/quit/cleanup uncertainty. Cover the new single-banner rules:
old success clears on edit, but unresolved effects cannot vanish or turn green.

Verify real Tk construction with synthetic data at 100%, 125%, 150% and 200%
scaling, long destination/title, short and long text, small window sizes, focus,
contrast and conditional controls. Inspect a current synthetic render if available;
do not use an old screenshot as visual acceptance. Check that shared-style use
does not change main-window layout, existing search, file-send or PDF-send behavior.

Run focused tests while editing, then `check-context-palette.bat` once after final
code changes. Run tracked and new-file diff checks; confirm no personal data is
staged. Follow AGENTS.md for sandbox interpreter failures; do not repair the
environment based only on access denied. Update Help, Changelog, the relevant
architecture/decision/testing records, and other scope documents as necessary.

Do not edit Python OneNote, commit, push, publish, add dependencies, consume reset
credits, or restart the live application without authorization. Do not run live
OneNote reads/writes under old consent. Finish implementation and synthetic checks
first, then prepare bounded attended UAT and request any still-missing exact scope
approval, using `docs/ONENOTE_SEND_UAT.md` as a proposal rather than permission.

Final response: briefly report the resulting user flow, changed files, actual
tests/results, review corrections, current visual evidence, remaining live UAT and
concrete blockers. Distinguish automated/simulated checks from owner-observed
behavior. Do not present unperformed checks as passed.

---

Recommended model: **GPT-5.6 Sol**. Reasoning effort: **high**.
Why: the visual work is bounded, but eliminating Review changes consent timing
around a OneNote write. A subtle duplicate-send or uncertain-result regression
could survive ordinary cosmetic tests. This follows `docs/MODEL_SELECTION.md`.
Use one bounded read-only reviewer where useful; retain one implementation writer.
If exact consent or receipt retention cannot be demonstrated, stop the unsafe
execution path and escalate that concrete design issue rather than relaxing guards.
