# Testing

Context Palette combines automated domain/UI-construction tests with manual Windows checks for behavior that cannot be proven reliably in a headless test.

## Find the right check

- [Complete automated check](#complete-automated-check) — required repository gate.
- [Targeted tests](#targeted-tests) — focused commands while changing the app.
- [Manual Windows smoke test](#manual-windows-smoke-test) — current attended checklist.
- [Platform-effect checks](#platform-effect-checks) — relevant external-app checks.
- [Current batch acceptance](UAT_CURRENT_BATCH.md) — September owner decision
  and optional follow-up, with later guidance clearly separated.

The dated verification records below preserve what was observed at each
checkpoint. Use the current commands and checklists linked above for a new run;
later changes may supersede old flags, layouts or workflows. Private evidence
under `outputs/` is not part of a Git checkout and is referenced as plain text.
Documentation maintenance, 2026-10-05: **17 focused checks** passed locally
and in a disposable copy of Git-tracked files with no local outputs or `.venv`.
The existing repository interpreter ran those checks. The complete check passed
configuration validation,
compilation and **1,677 tests in 180.431 seconds, with 2 skipped**. Whitespace
checks passed. No app/engine code, personal data or live UAT state was changed.

The current Input / Output, Preview, Drop and Send-files batch has
[owner acceptance for now with partial coverage](UAT_CURRENT_BATCH.md),
recorded on 2026-09-09. Its checklist remains available for optional follow-up.
Keep that decision separate from per-check results, automated output and
simulated DPI; unreported manual checks remain unverified.

## Compact secondary UI and Capture/Harvest retirement (2026-10-05)

OneNote Search, CSV review, bulk Action creation and Context editing use compact
current-state guidance, reserved effect controls and optional details. Capture
Inbox, its creator/AI flow, and Harvest entrypoints and implementations are
removed. Existing Actions and legacy capture data remain; Work Item workbook
Inbox is retained. Startup no longer reads or migrates old capture records.

Focused evidence: 44 OneNote UI tests; 39 CSV/bulk tests; 178 Context/configuration
checks; then 436 integrated host checks, 70 documentation/data/backup checks and
44 startup-preservation/backup/documentation checks passed. These use real Tk
with fakes and disposable data; none operate live Office or the resident app.
Final check-context-palette.bat passed configuration validation, compilation and
**1,631 tests in 187.958 seconds, with 2 skipped**. git diff --check passed.
Private complete-check output is under outputs/compact-ui-retirement-20261005/.
Nothing is staged, committed or pushed for this batch.

Remaining attended checks: compact controls and readable exact values at
physical 100/125/150% scaling; OneNote Search/Preview/Use with its existing
scoped permission; CSV overwrite/no-backup warning and fixed controls; bulk
All fields; Context shortcut disclosure/validation and unchanged unavailable
references. Confirm retirement removes Capture/Inbox/Harvest routes while
manual/Excel Action management and Work Item Inbox remain. No unperformed case
is marked passed. Existing-page OneNote append is not implemented: the current
engine has no append operation. The owner chose append/content preservation;
ONENOTE_APPEND_ENGINE_HANDOVER.md records the required engine extension.

## Find tooltip on opening (2026-10-05)

The original-code regression reproduced the owner's overlay: automatic Find
focus and reopening scheduled its help popup; query typing did not dismiss
the displayed help. Find alone now opts out of focus-triggered help. Delayed
hover remains available, typing dismisses it, and the default focus explanations
on other controls plus F1 Help are unchanged.

Focused tooltip/launcher checks passed **141 tests in 11.331 seconds**. The
new launcher regression uses isolated production Tk widgets, synthetic focus,
pointer and key events, and the real hover timer. It covers initial focus,
reopening, the registered tooltip, hover text, dismissal and continued query
typing. External execution, clipboard and resident-app integrations use fakes.
This is automated Windows Tk verification, not owner-observed pointer UAT.

No owner application was restarted, no Action ran and no personal settings were
changed. The complete `check-context-palette.bat` passed configuration validation,
compilation and **1,676 tests in 180.916 seconds, with 2 skipped**. Final
`git diff --check` passed; nothing is staged, committed or pushed for this fix.
Private output is under `outputs/find-tooltip-fix-20261005/complete-check.txt`.
After updating and restarting the resident app, the owner should verify normal
opening/F9 keeps the first result visible, hover still explains Find, typing
clears that help, and F1 remains usable. Those attended checks are unperformed.

## Normal-startup Excel conversion (2026-10-05)

The temporary live-text conversion startup gate is retired. Normal startup,
including a missing or obsolete `CONTEXT_PALETTE_UAT_LIVE_TEXT_CONVERSION`
value of `0` or `1`, uses the same attended workflow. No environment value
grants or denies execution. Current Help, Architecture and MVP supersede
earlier records of a disabled build or an uncommitted engine correction.

Python Excel remote `main` was checked at **c081510**; its ancestor **be4f67f**
contains the direct COM `Value2` write and shared recovery-package validation.
This is Git/source evidence, not a new engine run or a live Excel check.
The owner reports the published engine works on another PC, separately from
the remaining host-button issue. No engine file was edited.

Focused host checks passed **488 tests in 21.011 seconds**. Isolated Tk windows
and fake process responses cover normal startup without opt-in, inert legacy
flag values, no plan/execution merely from selecting columns, one explicit
Convert, optional read-only Review, complete pagination, missing/incompatible
capabilities, precision consent, exact plan correlation, recovery collisions,
stale callbacks and partial/unknown no-retry behavior. No live Excel was used.

The first complete-check attempt hit the documented sandbox restriction while
starting the user-profile Python interpreter. It was retried with normal Windows
access without repairing the environment. The final `check-context-palette.bat`
passed configuration validation, compilation and **1,674 tests in 202.408
seconds, with 2 skipped**. Final `git diff --check` passed. Nothing is staged,
committed or pushed for this change. Private complete-check output is under
`outputs/excel-startup-release-20261005/complete-check.txt`.

Fresh live host acceptance remains unperformed. After updating and restarting
Palette normally, the owner can check one saved disposable `.xlsx` with AutoSave
off and a free sibling backup path: select a worksheet/columns, confirm Convert
becomes available, invoke it once (acknowledge precision risk if shown), then
inspect converted text, true blanks and the recovery copy. Excel must remain
open and unsaved. Existing backups still block conversion; replacement remains
an engine-owner follow-up. Earlier scoped live permissions are not blanket
authorization for a new agent-operated Office session.

## Single-line Drop information (2026-10-04)

The later height revision supersedes the separate wrapped text rows recorded
below. It uses one non-wrapping information line and two control rows, a compact
selected/total history counter and inline Settings. With the production theme,
empty-history client dimensions measured **272×107 at Tk scaling 1.33** and
**384×138 at scaling 2.0**. The prior themed 1.33 target was 328×174; the new client
is about 39% shorter. These are isolated Tk scaling measurements, not physical
Windows display-setting acceptance.

Regressions cover fixed collapsed dimensions with long names/history/errors,
full read-only information before the first drop, keyboard Space to open Details,
visible Run/blocked state, selected-drop identification, exact-result resend,
two-scale control containment and retained monitor placement. No resend or
configured Action is performed by inspecting information. Actual dragging and
the owner's physical multi-monitor setup remain unverified for this revision.

Focused Drop and launcher checks passed **182 tests in 37.465 seconds**, using
isolated windows/fakes without Office access. Agent-operated Windows inspection
of the final production layout used synthetic prepared drops and mocked TkDND:
the client remained 272×107, Previous changed the one-line summary from text to
the selected Report.xlsx path and its counter from 2 / 2 to 1 / 2, and Hide
withdrew the isolated window with both drops retained. An earlier empty-history
visual check opened read-only Details with the complete instructions, configured
behaviour and status. No real drop, configured Action or external application
effect was exercised; the running owner Palette was not restarted.
After the final production/test changes, `check-context-palette.bat` passed
configuration validation, compilation and **1,674 tests in 334.654 seconds,
with 2 skipped**. Final `git diff --check` passed and staging remained empty.
Nothing was committed or pushed. Complete-check output is private under
`outputs/drop-ui-review-20261004/single-line-complete-check.txt`.

## Compact Drop and Excel wording (2026-10-04)

This records the earlier, taller layout. Its text-row arrangement is superseded
by the single-line revision above; its Excel release boundaries are unchanged.

The collapsed Drop window retains visible Previous/Next, Send again, Show
details, Settings and Hide. With the production theme, an empty-history target
measured 328×174 at Tk scaling 1.33 and 380×238 at scaling 2.0. Automated
regressions cover this footprint, complete long Action labels, history and
resend identity, expanded details, settings, Hide/Show retention and all controls
inside a synthetic monitor work area. Initial placement includes native frame
dimensions; a separate regression covers absolute positioning on a synthetic
monitor left of and above the primary screen. These scaling/monitor checks do
not establish physical multi-monitor or Windows display-settings acceptance.

Agent-operated Windows inspection used an isolated production Drop surface,
the shared theme and synthetic prepared drops, with TkDND registration mocked.
The populated collapsed target measured 340×174 at this PC's current scaling.
History navigation showed the selected filename, details expanded and exposed
the full prepared path, Send again returned that exact synthetic result, and
Hide withdrew the test window with both drops retained. All commands remained
visible. This was a layout/interaction check, not an actual drag from Explorer
or a test of a configured Action; no Office, clipboard or owner data was accessed.

The shipped Action/factory choice now reads Convert Excel values to text,
with a plain build-restriction explanation. IDs, startup opt-in, precision
acknowledgement and engine backup rules are unchanged. Personal titles are not
migrated. Normal Excel conversion release and backup replacement remain pending.

Focused checks passed **503 tests in 38.533 seconds**, covering Drop/history,
configuration, absolute monitor positioning, Action catalogue/Preview, launcher
routing, conversion-window gate/precision behaviour and documentation links.
These tests use isolated windows and fakes; they do not launch Office.
After the final production/test changes, `check-context-palette.bat` passed
configuration validation, compilation and **1,672 tests in 352.732 seconds,
with 2 skipped**. Final `git diff --check` passed, staging stayed empty and
nothing was committed or pushed. Complete-check output is private under
`outputs/drop-ui-review-20261004/complete-check.txt`.

## Live Excel conversion: optional Review (2026-10-04)

The owner changed the normal flow to select columns → Convert. Review is now
an optional read-only command. Direct Convert obtains a fresh plan in the
background and executes its exact fingerprint once for a correlated ready plan
with no precision risk. A reported risk uses a short acknowledgement screen;
confirming its checkbox alone never executes.

Focused host checks passed **211 tests in 13.336 seconds**, using fakes without
launching Office. Added regressions cover direct B/D/F conversion without Review,
exact fingerprint/path/target propagation, repeated clicks, stale/duplicate plan
callbacks and receipts, consumed authority, optional Review performing no writes,
mandatory risk acknowledgement, disabled gate, blocked/mismatched/missing-path
plans, closed-window revocation and preservation of an existing backup collision.
The prior stale/partial/unknown no-retry tests remain and pass.

After the final production and test changes, `check-context-palette.bat` passed
configuration validation, compilation and **1,670 tests in 325.393 seconds,
with 2 skipped**, using normal Windows Python access. `git diff --check` passed
and staging remained empty. Existing unrelated work was preserved; nothing was
committed or pushed. The complete-check output remains private under
`outputs/excel-ui-review-20261004/optional-review-complete-check.txt`.

Agent-operated Windows checks used the production Tk window and shared theme
with a fake coordinator at the current PC scaling. Ordinary clicks selected
B/D/F, then one Convert click proceeded through the automatic plan and one
simulated execution to the succeeded result, without opening Review. A separate
700×480 simulated risk plan displayed the short confirmation and full wrapped
Unicode paths; acknowledgement enabled Convert but submitted no execution before
the test window was closed. These checks called neither the engine nor Office.
Fresh attended real-Excel acceptance of this direct path remains outstanding;
the earlier real-Excel evidence below does not establish it.

The requested one refreshed backup is not supported by engine `1.0`. The owner
chose an engine-owner handover, stored in `EXCEL_SINGLE_BACKUP_ENGINE_HANDOVER.md`.
The host still refuses to bypass a collision; automatic backup replacement and
new live-Excel acceptance have not been performed by this change.

## Live Excel conversion: compact review (2026-10-04)

This records the earlier UI check. The optional-Review flow above supersedes its
mandatory human-review step; the underlying engine verification remains separate.

The later UI revision replaces the raw plan report with exact target identity,
counts, three bounded Before → After examples, recovery path and warnings.
Technical details are collapsed; conversion stays in the fixed footer. Separate
columns toggle with ordinary clicks. Change columns reuses inspection but discards
reviewed authority; another plan and any required acknowledgement are mandatory.
The startup execution gate, process contract and no-retry policy are unchanged.

Focused checks passed **22 conversion-window tests in 15.916 seconds** and
**182 protocol, shared-target-selector and launcher tests in 3.337 seconds**.
They use fakes and do not launch Office. New regressions cover disjoint single
clicks, effect-first review, details preserving authority/acknowledgement without
process calls, cached selection requiring a fresh plan, recovery replanning
resetting acknowledgement, and complete long-path wrapping with horizontal and
vertical conversion-button containment at the supported minimum size.

After the final production changes, `check-context-palette.bat` passed
configuration validation, compilation and **1,663 tests in 295.103 seconds,
with 2 skipped** using normal Windows Python access. `git diff --check` passed
and staging remained empty. The only production file changed by this UI revision
is `src/context_palette/excel_live_text_conversion_window.py`; its focused tests
are in `tests/test_excel_live_text_conversion_window.py`. Help, architecture,
decisions, backlog, testing notes and changelog were updated; existing unrelated
and earlier integration work was preserved. Nothing was committed or pushed.

Agent-operated Windows UI checks used production Tk widgets and the shared theme
with a fake coordinator. At this PC's current scaling, ordinary clicks selected
B/D/F and generated the exact `[2, 4, 6]` plan request; acknowledgement enabled
conversion, Details preserved it and the visible footer, and Change columns kept
selection but required acknowledgement again on the fresh review. A second
minimum-size 700×480 window displayed complete long Unicode workbook/recovery
paths with wrapping; scrolling exposed the short acknowledgement and Undo warning
while conversion stayed visible. No engine process, Excel read or Excel write
occurred in these UI checks. The private harness remains local under `outputs/`.

This verifies the revised UI separately from the earlier real-Excel check below.
Owner acceptance of the revised live flow, other display-scaling settings and
second-PC deployment remain pending. The engine correction is still uncommitted;
this revision does not promote the Development/UAT Action to normal execution.

## Live Excel conversion: host integration verification (2026-10-04)

Focused protocol, conversion-window, shared target-selector and launcher-route
tests passed **198 tests in 8.608 seconds**. The normal automated suite uses
fakes and does not launch Excel. Regression tests establish that a failed receipt
cannot claim completed effects, a clean-workbook partial failure retains recovery
and inspection guidance, stale scope is a known pre-effect failure, and every
review displays the Undo warning without relying on engine warning messages.

The complete `check-context-palette.bat` passed configuration validation, source
compilation and **1,657 tests in 287.663 seconds, with 2 skipped**, using normal
Windows access after the restricted sandbox could not launch profile Python.
No environment repair was needed. Existing machine-local configuration warnings
remain warnings; raw personal paths are omitted.

### Fresh disposable Context Palette end-to-end check

Agent-operated Windows verification used a newly created `.xlsx`, its own fresh
sibling recovery path, and isolated private Palette settings. It did not reuse
the engine's evidence workbook, running session or recovery. The production main
Palette's saved Action **Run** route opened the existing conversion dialog,
shared workbook/worksheet selector and real process client. A private wrapper
limited inventory to that sole fixture, plans to the two reviewed scopes, and
execution to one acknowledged B/D/F request with its reviewed fingerprint. It
did not fabricate engine responses. Global hotkey registration was disabled in
that isolated process to preserve the owner's resident F9 registration.

The bounded check passed:

- Ordinary click plus Shift+Down selected B/C. A formula in C blocked the plan
  with 4 eligible, 3 compliant, 8 blank and 1 blocked cell. Independent direct COM
  snapshots confirmed all fixture values, formulas and formats stayed unchanged;
  planning created no recovery file.
- The real B/D/F plan displayed 5 eligible, 3 compliant, 16 blank, 0 blocked and
  5 precision-risk cells, its exact recovery path, and the Undo warning. Execute
  was disabled before acknowledgement; clicking it sent no execution request.
- One acknowledged execution used the exact reviewed fingerprint and reported
  `result.state="succeeded"`, 5 changed, 3 compliant, 16 blank and physical
  columns 2/4/6 completed. No retry occurred.
- Independent direct COM `Value2` and Excel `ISBLANK` checks confirmed all 16
  original true blanks remained blank. Scientific text and numeric scalars became
  the expected text; leading-zero and already-compliant text remained intact.
  Headers, unselected values/formulas/formats and the second worksheet were
  unchanged. The long numeric value preserved the actual value Excel exposed,
  including precision already lost on load.
- Independent file-based inspection confirmed recovery values, types, formulas
  and formats matched the pre-write live Excel snapshot. Recovery is the live
  pre-change state, which can differ from the original ZIP's numeric literal
  after Excel precision loss. The original disk hash was unchanged; one original
  Excel process remained and the source was open, dirty and unsaved. The isolated
  test Palette was closed without saving or closing Excel.

This is bounded agent-operated verification, not owner-observed acceptance.
The desktop tool cannot hold Ctrl while clicking; Windows Tk's ordinary arrow
bindings do not preserve a disjoint selection. After confirming no mutation,
the isolated test Palette was restarted with a private F6 B/D/F selection preset
and the real review/acknowledgement/execute controls were used. No preset was
added to production. This earlier session did not verify ordinary disjoint
selection; the later compact-UI checks above verify the new single-click controls
with simulated data, separately from live Excel acceptance.
The actual main Run route is verified; F9/Return-to-Excel, recovery opening in
desktop Excel, Unicode live paths, duplicate workbooks/headers, pagination,
100%/125% scaling and second-PC setup remain unverified. The displayed window was
inspected at this PC's current scaling only. Partial/unknown/conflict/no-retry
cases are covered with fakes, not forced failures in this live workbook.
Private fixture paths, settings, tokens and cell matrices remain local output
evidence, not tracked documentation. Nothing was staged, committed or pushed.

The engine checkout remains read-only at HEAD `08af313`. Its uncommitted
`selected_range.api.Value2 = output` correction is present. The `1.0` catalogue
does not identify deployment of that correction, so a dedicated engine commit
remains necessary for another PC. Its contract document also lists obsolete
recovery error names and overstates `plan_stale` coverage: actual recovery
failures use `operation.live_recovery_failed`, and later scope checks use
`conflict.live_conversion_scope_stale`. The host uses authoritative receipt
state and recognizes the actual outer scope-stale failure.

Files changed in this focused integration: `src/context_palette/excel_automation.py`,
`src/context_palette/excel_live_text_conversion_window.py`,
`tests/test_excel_automation.py`, `tests/test_excel_live_text_conversion_window.py`,
`docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/HELP.md`, `docs/MVP.md`,
`docs/TESTING.md`, `BACKLOG.md` and `CHANGELOG.md`. Existing unrelated OneNote and
earlier Excel work was preserved. Fresh fixture, private Launcher harness and
direct-COM/file verification evidence remain unstaged under local `outputs/`.

## Live Excel conversion: bounded test blocked (2026-10-03)

This is historical evidence. The engine working tree's corrected direct COM
write boundary passed focused engine UAT on 2026-10-04; its dedicated deployment
commit is still outstanding. Keep that engine evidence separate from the fresh
Context Palette end-to-end check and remaining host acceptance matrix.

The owner approved one disposable `.xlsx`, one visible worksheet, a zero-write
formula-blocking plan, one two-column conversion and one exact future sibling
recovery file. The other workbooks were closed. This was agent-operated Windows
verification in the production conversion window with isolated private settings,
not owner-observed acceptance or the main launcher/F9 journey. Test-only keyboard
presets selected the exact approved columns because the computer-use tool could
not hold Ctrl during a click; ordinary multi-column selection is not verified.

Two host defects reproduced before their fixes: preflight omitted the exclusive
formula class from its reconciled total, and the native recovery picker returned
forward slashes while the engine returned native separators. Focused regression
tests failed before each fix. After both fixes, the protocol and conversion-window
tests passed **63 tests in 10.333 seconds**. The parser still rejects double
classification, and a different recovery filename still fails correlation.
The complete `check-context-palette.bat` then passed configuration validation,
source compilation and **1,653 tests in 356.002 seconds, with 2 skipped**, using
normal Windows access. Final diff checks passed; nothing is staged or committed.

Against Python Excel HEAD `08af313` with its existing uncommitted work preserved,
the actual Windows run established:

- With the UAT gate off, a ready plan remained read-only even after precision
  acknowledgement. No execution request was sent.
- With the gate enabled only in the isolated test process, a selected formula
  blocked the plan with zero writes. A formula outside the selected columns did
  not block the subsequent ready plan. The native recovery override produced a
  fresh trusted plan and did not create the file during planning.
- Exactly one execution reported success: 5 eligible conversions, 3 compliant
  cells, 8 blanks and both reviewed columns completed. Independent direct COM
  reads confirmed the nonblank text values/types, the live numeric value preserved
  as text, and unchanged header/unselected values, formulas and formats.
- The engine verified its recovery copy. Independent file-based inspection parsed
  that `.xlsx` and confirmed all original fixture values, types and formulas,
  including true blanks. The original disk hash was unchanged. One original Excel
  process remained, with the source workbook open, dirty and unsaved. The recovery
  was not opened in desktop Excel.
- **Mutation UAT failed blank preservation:** all 8 selected cells that had direct
  COM `Value2=None` became `Value2=""`, and Excel's `ISBLANK` returned false for
  every one. The engine reported these as unchanged blanks. Display equivalence
  does not preserve spreadsheet semantics.

The engine's gateway bulk-writes a selected column through xlwings `.value`, whose
Windows converter changes `None` to an empty string. The fake gateway tests store
the Python payload directly, so their `None` assertion misses that conversion.
The engine contract requires blanks to remain blank; fix the engine write boundary
and add a regression that exercises the real conversion stage plus an attended
direct-COM `Value2`/`ISBLANK` check. Do not reinterpret empty strings as blanks in
Context Palette, copy workbook logic into the host, or retry this mutation.

At that time, the UAT label and execution gate remained and engine code was not
edited. Full launcher
activation, recovery opening in Excel, stale/conflict/partial/unknown cases,
Unicode live paths, duplicate workbooks/headers, pagination, Return to Excel,
display-scaling coverage and the second-PC setup issue were unverified. Private
fixture paths, launcher settings, tokens, matrices and samples are kept in local
output evidence, not tracked documentation.

## OneNote Send single-button UI (2026-10-03)

The separate Review control has been replaced by a locally displayed complete
page and one **Send to OneNote** approval. The 2026-09-28 record below remains
historical evidence for the original host slice.

Final focused verification passed **90 tests in 31.675 seconds**: 56 Send
protocol/Tk tests, 23 owned-transport tests and 11 launcher smoke tests. After the
last test-helper refinement, all three visual cases passed in 3.583 seconds.
The final `check-context-palette.bat` passed configuration validation, source
compilation and **1,651 tests in 171.594 seconds, with 2 skipped**. The sandbox
could not launch the existing profile Python; the unchanged check used normal
Windows access, without environment repair. Tracked and new-file diff checks
passed and nothing is staged.

The first complete run executed 1,651 tests in 165.200 seconds, with 2 skipped
and 10 failed layout/focus assertions. The failures reproduced after the earlier
launcher scaling tests: the Send widget heading retained a 51-pixel requested
height at every simulated scale, while a newly created diagnostic font changed
size correctly. Setting a deterministic baseline before widget construction and
using a fresh interpreter/theme per scale corrected this cached-font test state.
The tests restore display scaling, finalize earlier Tk variables, and wait for
native mapping/geometry/focus to settle. No fit assertion was relaxed. The matrix
also requires the actual heading height to increase at each scale, and checks
complete long Unicode/tab/blank-line text plus scrolling.

Synthetic regression coverage includes all five outcomes, strict full-plan
comparison with the clicked snapshot, normalization redisplay, fixed click-time
expiry during planning/readiness/final approval, and cancellation or source,
title, destination, engine and session changes during each preflight stage.
The final Tk handoff catches source revision changes even without a notification.
Tests also cover fast completed double-clicks, held Ctrl+Enter across completion,
fresh intentional equal-content sends, worker/Tk separation, Tab/Escape, retained
uncertain receipts and IDs, acknowledgement semantics, and Close/Quit blocking.

Independent read-only review identified three corrected issues: a callback
exception could leave the preflight gate/polling stalled; metadata-read cleanup
could fabricate a Send receipt; and a later read-cleanup failure could repeat an
old success. Regression tests protect each correction and the visibility of an
earlier unresolved write during a new cleanup failure.

Real Tk construction checked short/long title and destination, small usable
windows, conditional controls and shared-style preservation at simulated Windows
100%, 125%, 150% and 200% scaling. These are synthetic checks, not physical DPI
or multi-monitor UAT. Fresh native captures of the script-owned synthetic window
were inspected at 100%: private screenshots `ready-100.png`, `verified-100.png`
and `unknown-100.png`, retained locally under `outputs/onenote-send-ui-20261003/`.
These files are not shared through Git. All content and
client responses are fake. The first PrintWindow captures omitted themed widgets;
those incomplete images were replaced by client-area captures before inspection.
The render exposed global font defaults overriding heading weights, corrected
with explicit shared fonts within this dialog, without global theme changes.

No live OneNote read/write, Python OneNote edit, application restart, commit or
push was performed. Existing uncommitted work and private settings were preserved.
The [revised one-page attended UAT proposal](ONENOTE_SEND_UAT.md) still needs
exact owner-approved scope before agent-operated live access. Relocated bootstrap,
other clients/notebooks and interrupted real writes remain separately unverified.

## Send text to OneNote host slice (2026-09-28)

This is a new host implementation, independent of the removed prototype.
Final host gate: `check-context-palette.bat` passed configuration validation,
source compilation and **1,630 tests, 2 skipped**, in 162.785 seconds. The initial
sandboxed attempt could not launch the existing profile Python; the unchanged
check passed with normal Windows access. No environment repair was performed.
Focused Send protocol/Tk verification passed 35 tests in 5.973 seconds; the owned
transport suite passed 23 tests. Earlier menu/data-catalog expectations and one
source-revision test assertion were corrected before this final gate. Tracked
and new-file diff checks passed; no runtime data is staged and nothing was committed.

Synthetic protocol tests use a fixed canonical golden plan and digest, all five
write outcomes, strict types/effects/exit matching, Unicode/control/size limits,
confirmation expiry, bounded paging/ancestry, and private destination persistence.
The native Windows subprocess tests use disposable fake launchers and children,
including the production `OneNoteSendClient.execute` default path and its 45-second
allowance. No test imports the engine or accesses Office.

Real Tk construction with fake clients covers inert opening/editing, complete
review, source/engine/section invalidation, one send per review, equal-content
intentional sends after new review, pre/post-dispatch cancellation, stale-result
retention, partial IDs, expiry during readiness, cleanup blocking, Close/Quit,
destination selection, keyboard use and simulated scaling. These are synthetic
UI checks, not physical DPI or owner-observed OneNote evidence.

Independent review found two corrected gaps: accepting unexpected execution
warnings/artifacts, and risking no-effect classification for an unexpected
exception after entering Execute. Such malformed or lost replies now remain
unknown; validated terminal receipts can retain more precise effects. A permanent
result label keeps uncertain outcomes visible even after editing title/source.

No live host read/write, application restart or OneNote navigation was performed
for this slice. The [exact disposable UAT proposal](ONENOTE_SEND_UAT.md) requires
new approval after the automated gate. The engine owner's earlier 1,113-test gate
and one verified engine-only creation are not acceptance of this host feature.
Relocated bootstrap/live access remains separately scoped and unverified.

## Multi-monitor placement regression (2026-09-24)

The owner reported Palette straddling two displays on a laptop with two external
screens. Code review found signed desktop coordinates encoded as Tk right/bottom
offsets. Regression coverage now checks absolute negative X/Y in a real invisible
Windows Tk test window, synthetic left/primary/raised monitor locations, startup
and ordinary Show, a fresh laptop-only location after undocking, captured hotkey
location, manual resize centering, oversized-window fitting, and interleaved
native monitor calls. The Tk window is undecorated and the monitor topology is
synthetic; these checks do not establish physical three-monitor or mixed-DPI UAT.

Full working-tree verification (including separate, pending OneNote work): all
159 focused geometry/hotkey/launcher-interaction/enhancement UI tests passed in
20.379 seconds. The complete `check-context-palette.bat` passed
configuration validation, compilation and 1,591 tests with 2 skipped in 275.519
seconds. The first sandboxed attempt could not launch the profile Python;
the unchanged command succeeded with normal Windows access. Independent
read-only review found no remaining blocker after the resize regression fix.

Monitor-only release verification: the staged source was exported to an
isolated temporary directory, without pending OneNote modules or personal
runtime data, and checked using the existing Python environment. Its full
`check-context-palette.bat` passed configuration validation, compilation and
1,487 tests with 2 skipped in 168.500 seconds. The 11-file staged diff passed
whitespace and independent scope/privacy/dependency review. Physical monitor
and mixed-scaling UAT remains pending.

Pending owner check on the affected PC: after installing the updated code and
restarting Palette, move the pointer to each screen and open with F9 / Ctrl+Alt+P.
Confirm the whole window centers on that screen, including any screen left of
or above the primary. Repeat an ordinary launcher open and a manually resized
window. Disconnect external displays, open again on the laptop, reconnect and
repeat; check a child dialog on the chosen screen too. Preserve current Input /
Output before restarting. No live application restart or personal data change
is part of this automated check.

## OneNote closed-notebook recovery (2026-09-19)

The owner reported closing the agreed disposable notebook and restarting. Their
screenshot showed the saved notebook still selected, no results, and a misleading
engine-unavailable/repair message. This was a failed recovery check, not acceptance.

An authorized diagnostic through Palette's owned transport used only the saved
exact disposable notebook and previously agreed marker; it performed no root
inventory, preview, navigation or content writes. Static describe and the active
probe succeeded, but scoped search returned `internal.desktop_bridge`, category
`internal_error`, exit 70. The host incorrectly mapped this known read failure to
engine incompatibility. The engine currently does not distinguish a closed/stale
notebook from other failures in this bridge error; no specific cause is inferred
from the error code alone. Python OneNote was inspected but not edited.

The correction recognizes that code, preserves the configured engine and exact
notebook, clears failed results/readiness, and keeps Search / Choose notebook
available. It makes no automatic retry or fallback. Two new regressions failed
before the fix; all 73 focused protocol/Tk tests then passed in 16.194 seconds.
They also cover private error-detail suppression, mismatched-exit rejection,
clearing an existing preview and a fresh describe/probe on explicit same-scope
retry. Independent read-only review found no blocker.

The corrected production client was exercised once against the same live failure:
it returned the new fixed recovery message, with private settings byte-for-byte
unchanged. This is live adapter evidence, not a corrected resident-window check.
Palette was not restarted again or its current Input / Output discarded. The
owner still needs to restart Palette, check the revised closed-notebook message,
then reopen the notebook and retry (reselect explicitly if its identity changed).
The complete repository check passed configuration validation, compilation and
1,580 tests with 2 skipped in 163.362 seconds. Tracked and new-source/test
whitespace checks passed. No personal/runtime files are staged; nothing was
committed or pushed.

### Reopened notebook follow-up — blocker confirmed (2026-09-19)

The owner supplied the corrected recovery message and confirmed the notebook was
already open. The message fix is visible, but reopened-notebook recovery has failed;
opening the notebook alone did not resolve the saved scope.

An authorized metadata-only diagnostic found successful describe/probe followed by
`input.unsupported_onenote_xml_element` (exit 3) from root notebook inventory.
A temporary, process-owned observation around the unchanged engine parser emitted
only schema element names and identity-match booleans, never raw XML, notebook
names, IDs, paths or text. The sole notebook matched the agreed disposable title,
but its identity differed from the saved identity. The xs2013 metadata contained
`Notebooks`, `Notebook` and `UnfiledNotes`; the engine parser allows only the first
two of these. Settings remained byte-for-byte unchanged. No root page search,
preview, notebook mutation, automatic remapping or engine edit was performed.

Consequently the saved reference is stale, and Choose notebook cannot repair it
because inventory rejects the metadata. Engine work is needed to handle the known
UnfiledNotes structure without widening scope or accepting arbitrary XML, followed
by explicit notebook reselection and a same-scope search/preview check. Never select
by title automatically; duplicate titles and opaque identity rules still apply.
The owner chose an engine-owner handover rather than engine edits in this task.
See [the prepared prompt](ONENOTE_ENGINE_RECOVERY_HANDOVER.md). Host test totals
above remain valid; this follow-up changed no code.
## OneNote engine discovery (2026-09-16)

Automatic direct-sibling discovery is implemented. The focused host check passed
82 tests in 28.453 seconds, using synthetic launchers/responses and real Tk.
It covers explicit-path precedence, missing/invalid/corrupt settings and unusable
explicit engines with a valid sibling present; absent/inaccessible siblings;
exact sibling-only bounds; space/Unicode installation paths and a foreign cwd
with a decoy engine; module-derived installation root independent of settings;
no engine call/read/readiness on open or typing; notebook retention on repair;
and notebook persistence without pinning the detected engine. The complete
repository check passed configuration validation, compilation and 1,578 tests
with 2 skipped in 185.107 seconds. Tracked and new-file whitespace checks passed;
independent review found no blocker. Those checks used synthetic engines; the
subsequent attended live check is recorded separately below.

The Python OneNote owner's 2026-09-16 `docs/STATUS.md` and
`docs/CONTEXT_PALETTE_PRODUCT_OWNER_HANDOVER.md` record 561 engine tests, Ruff,
compileall, pip check and diff checks. Its real launcher passed static requests
from isolated space/non-ASCII installations and a foreign cwd. This host task
inspected that evidence without rerunning the engine gate or editing that repo.
Neither those static checks nor the host synthetic tests establish full bootstrap
or live OneNote access from relocated paths; those remain a separate follow-up.

### Attended Windows UAT — partial evidence (2026-09-16)

The owner explicitly agreed the disposable notebook, section, page and search
marker, allowed listing open notebook names, and confirmed that no other notebook
was open. The owner also allowed Palette restart and discarding its current
Input / Output text. Exact local identifiers and note content are not retained
in this record. OneNote was already running; this check used the existing saved
engine at its original location, not automatic sibling discovery or a relocated
engine.

- The updated UI reused the saved engine without Check setup / Connect steps.
  Choose notebook listed only the agreed notebook. Its selection survived closing
  the picker and a full Palette quit/relaunch. Opening and typing left the UI idle;
  no-call behavior is established by the synthetic tests, not live instrumentation.
- Search returned three rows, all within the selected notebook, with notebook /
  section locations visible. Only the agreed page was selected and previewed.
  Preview reported complete basic text of 1,098 characters. The results included
  a deleted-pages location; other returned pages were not previewed.
- With harmless destination text, Cancel visibly retained it; Append displayed
  that text followed by the note; Replace displayed the note alone. Ctrl+Z restored
  the original text after both Append and Replace. These are live visual checks;
  exact text equality and unchanged clipboard have synthetic coverage but were
  not independently measured in this live session.
- No OneNote content-write or navigation command was issued, and no unexpected
  prompt was observed. Notebook immutability and background synchronization were
  not independently instrumented. Search was first observed complete at 12 seconds
  and preview at 8 seconds after their clicks; tool/polling delays mean these are
  polling observations, not operation latency measurements.
- The unavailable-notebook live check was pending owner preparation at this
  checkpoint; see the 2026-09-19 failure and correction above. Broader coverage
  below and full bootstrap/live reads from relocated paths remain unverified.
  This partial session is not blanket owner acceptance.

### Bounded attended UAT procedure

Use an explicitly agreed disposable scope and isolate it before inventory/root
search. The agreement above applies only to this session and its named scope;
historical engine UAT is not blanket authorization. Preserve useful Input / Output
text before restart and keep OneNote already running under a standard account.

1. Restart Palette, open Find OneNote notes and verify the expected engine status.
   Opening and typing must not start a request. Choose the agreed notebook, then
   close/reopen the picker and restart Palette; the same notebook must remain shown.
2. Choose Search with the agreed text. Review notebook/section breadcrumbs and
   select only the agreed page. Explicitly Preview its complete basic text. Verify
   no unexpected OneNote navigation, prompt, synchronization or content change.
3. With disposable Input / Output text, exercise Use text → Cancel, Append and
   Replace. Cancel retains original text; Append adds exactly the reviewed text;
   Replace shows exactly it; Undo restores the previous value. Clipboard unchanged.
4. Have the owner make only the agreed notebook unavailable, then search its saved
   scope. Confirm a clear failure, no results from other notebooks and the same
   saved scope. Reopen the notebook explicitly and reselect if its identity changed.
5. Record only coarse timings, pass/fail observations and remaining limits. Keep
   bootstrap/live reads at relocated engine paths outside this session unless
   separately authorized. Stop on scope ambiguity, unexpected prompts or changes.

## OneNote host first slice (2026-09-16)

The attended **Find OneNote notes…** integration is implemented. On 2026-09-16,
`check-context-palette.bat` passed configuration validation, compilation and
**1,541 tests with 2 skipped** in 204.589 seconds after the placement correction. The 65 new tests cover strict
protocol/settings (15), owned Windows synthetic child processes (19), injected
session metadata (10), and real Tk with fake notes/placement/launcher wiring (21).
Focused checks and tracked/new-file whitespace checks passed. Ordinary tests use
fake responses and never activate or inspect OneNote, notebooks or Graph.

The real local engine's static `describe_capabilities` handshake also passed
(`can_probe=True`) through the new owned transport. This does not attach to
OneNote or establish desktop readiness. Synthetic Tk journey/layout checks passed;
a separate desktop screenshot inspection timed out at the tool's app-approval
step, so visual review was not claimed at that checkpoint. The resident Palette
had not yet been restarted.

**Owner-run host UAT: search, preview and corrected Replace confirmed.** The owner supplied a
screenshot showing two search matches and a complete basic-text preview, but
reported that Replace did not leave the note in Input / Output. A success label
in the picker is not evidence of successful end-to-end placement. An automated
real-Tk regression reproduced the missing reveal of a hidden main window; a
subsequent normal Show/F9 reloads the old clipboard. Replace and Append now reveal
and focus the editor without clipboard access; Cancel leaves the view unchanged.
The new regression covers both placement modes, hidden/collapsed workspace,
exact text, unchanged clipboard, focus and Undo. The owner subsequently confirmed
"this works" on 2026-09-16. Broader UAT and observed timings remain pending.

The owner then requested a remembered engine and notebook instead of repeated
setup/connection steps. The new flow performs setup/probe automatically only
after explicit Search/Enter or Choose notebook. A chosen notebook is stored in
private local settings and sent as an exact scoped identity; errors never widen
scope. Real-Tk/fake-engine focused checks passed 59 tests covering restart reuse,
fresh-session reprobe, cancellation between stages, missing/moved engine,
scope persistence, chooser cancellation/close and strict inventory/scoped-result
contracts. The complete check passed configuration validation, compilation and 1,566 tests with 2 skipped in 164.656 seconds; tracked/new-file whitespace checks also passed.
The later partial live check of this new flow is recorded above.

At this earlier first-slice checkpoint, the agent had not performed a live notebook
read. The engine's earlier disposable
UAT on 2026-09-13 verified its own probe/search/preview and recorded roughly one second per
read. Its runner selected a preapproved result automatically; it did not test
Context Palette, human result selection or this placement UI. That engine
evidence is not host acceptance, general coverage or a performance guarantee.

The owner subsequently identified the existing disposable notebook/page by
screenshot for host UAT. An attempt to inspect the current OneNote window timed
out at the desktop-control tool's app-approval step. No agent-operated live probe,
search, preview or placement was performed during that attempt. The first
screenshot established the selected test target; owner-run and subsequent
agent-operated live evidence are recorded above. The broader matrix below
remains only partially exercised; preserve useful Input / Output text before
any further restart.

After synthetic checks pass, the owner must explicitly agree a disposable
scope for a separately attended host acceptance session. Root search reads all
open notebooks: isolate the approved disposable content before authorizing
Search/Choose notebook, rather than treating earlier engine consent as permission to
read personal or business notebooks. Use standard-user execution and OneNote
already running; independently observe no unexpected navigation, prompts,
synchronization or content change.

The broader host acceptance matrix is (completed parts are recorded above):

- Open from selected Input / Output and from an empty typed query: neither
  opening nor typing may read OneNote. Choose a notebook once and verify that
  reopening remembers both engine and scope. Search/Enter must check/connect as
  needed, then send only the selected scope with unindexed pages and limit 20.
  Test closed/moved notebooks and an unavailable/moved engine without silent root
  fallback. Choose notebook reads open notebook names only on explicit request.
- Review empty/multiple/untitled/Unicode/limited results and available breadcrumbs.
  Select a human-chosen exact result, explicitly Preview text, then test Replace,
  Append and Cancel, including an empty destination. Verify the clipboard and
  OneNote remain unchanged, and only the reviewed complete text is placed.
- Confirm a preview over 50,000 characters is labelled and cannot be used. Change
  query, selection and destination during work/review; no stale completion or
  destination change during the chooser may overwrite working text.
- Exercise cancellation, timeout, Close, one-request-at-a-time behavior and
  process exit/restart/addition. Confirm host-owned descendants are gone before
  another request, OneNote is never terminated, and readiness is re-probed when
  invalidated. Use synthetic fixtures for unsafe/unavailable process scenarios.
- Inspect generic errors and diagnostics for query/content/ID/raw stderr leakage;
  confirm settings are ignored and excluded from configuration backup. Test
  keyboard navigation, focus, responsiveness and normal Windows scaling.
- Test representative disposable workloads and an engine checkout/launcher path
  containing spaces and non-ASCII characters. A foreign working-directory check
  alone does not establish checkout-path portability.

Provisional latency goals are at most **5 seconds per search or preview** and
**10 seconds for search plus preview**, excluding setup and human selection.
These goals and broader coverage remain unverified. The 10/30-second transport
deadlines are safety limits, not acceptable routine latency targets. Record only
coarse timings and non-sensitive observations.

## Current Edge score PDF acceptance

### Guitar Pro tab extension (2026-09-15)

**Focused automated checks passed:** 44 Python/real-Tk tests covered the score
boundary, Action routing/Preview, window lifecycle and generated catalogue.
Two additional tests covered Python URL validation and AST-extracted PowerShell
page-identity helpers, including the observed Guitar Pro URL/title, Official
regression cases, type mismatches, and malformed URLs. These helpers did not
inspect or drive a live browser.

**Complete automated check passed:** `check-context-palette.bat` ran **1,476
tests with 2 skipped in 318.487 seconds** on 2026-09-15. Configuration validation
and compilation passed. The ignored machine-local log is
`score-pdf-guitar-pro-check.log`.

**Live Windows handoff passed:** After a graceful Palette restart, the saved
Action was run from F9/Find on the open Dont Cry Sister Guitar Pro tab. Edge
opened the site's print layout with a two-page PDF preview and native Save As.
The Palette progress window closed without a failure popup. The dialog retained
Edge's suggested filename and Downloads location and was left open for the user
to choose the final folder/name and Save. No final Save was clicked, and no
finished PDF or content fidelity was verified.

An Official score was not retested live in this change. Its identity regression
checks passed automatically. Final manual save/content inspection, alternate
instruments, cancellation, changed foreground, scaling and second-PC checks
remain unverified unless separately reported. This does not reopen the earlier
requirement for full automatic saving. Historical complete-check and failed
automatic-save records below remain separate evidence.

**Owner accepted manual completion (2026-09-15).** Keep the observed behavior:
run the score Action, then choose the folder/filename and finish Save in Edge.
The owner prefers the chance to change the filename. Full automatic saving is
not an acceptance requirement. The later request removes the failure popup for
the known filename-control lookup failure after verified Save As: the Palette
progress window closes, leaving manual completion in Edge. Other errors remain
visible. Native execution is unchanged; this is not an implemented always-pause mode. The configured folder and
automatic duplicate numbering do not apply to the observed manual finish.

The failed automatic-save test below remains a failed technical test. Owner
acceptance of manual completion does not claim that it passed, or that any
previously unreported Windows UAT was performed. See the latest
[owner decision](DECISIONS.md) and the
[usage steps](HELP.md#save-the-current-ultimate-guitar-score-from-edge).

**Handoff message change (2026-09-15):** 29 focused Python/real-Tk tests passed
with a simulated renderer/helper. They cover the exact protocol classification,
conflicting outcomes, ordinary errors, staging cleanup without PDF publication,
and closing the progress window once without lifting a result dialog. This is
not a live Edge test. The remaining focused Windows check is to run the Action,
confirm Save As stays available without the Palette popup, then choose a folder
and filename and save manually. At that point the application had not been restarted; see the later Guitar Pro live check above.

The required complete check then passed: `check-context-palette.bat` ran
**1,474 tests with 2 skipped in 174.911 seconds** on 2026-09-15, including
configuration validation and compilation. The machine-local ignored log is
`score-pdf-manual-handoff-check.log`. This does not claim a new live Edge test.

**Historical automatic-save test: failed (2026-09-15).** The native-process fix now
gets past dialog identity checks, but the live helper reports `filename_missing`.
A separate live accessibility inspection finds the visible `File name:` Edit
with AutomationId `1001` under `FileNameControlHost`. A bounded ten-second retry
of the unchanged selector also failed on the existing Black Star score. The
unproven polling change and its tests were reverted; no completed PDF was
verified. Further automatic-save repair and repeat UAT are not required under
the owner's manual-completion decision. The earlier
1,469-test pass does not establish that automatic saving works.

The score function has separate acceptance from generic webpage PDF rendering
and the earlier accepted batch. Its automated tests use injected process/UI
boundaries; Tk tests check window lifecycle and presentation. They do not execute
the Windows accessibility helper against the user's browser.
`test_edge_score_pdf_native.py` parses the PowerShell script and compiles the C#
companion using Windows' own assemblies without invoking any UI/native method.
`test_edge_score_pdf_controls.py` executes extracted PowerShell functions with
fake controls. It covers normalized PRINT labels, ambiguity, visibility,
source/page changes, and native Save As identity/readiness. Native host checks
cover the exact foreground handle, a separate Edge process, case-insensitive
executable equality, other-directory executables, missing/unreadable process
paths, and a zero process ID. It does not inspect or operate the real browser.
Python protocol tests also cover stage-specific
failure messages and suppression of unrecognized raw output.

On 2026-09-13, the reported control lookup failure was reproduced through the
saved Action against the existing Edge score. Diagnostics confirmed surrounding
whitespace in the accessible PRINT label. The corrected lookup reached Edge's
PDF preview and Windows Save As. Save As discovery then failed; the foreground
HWND correction reached Save As but rejected its identity. A subsequent read-only
inspection confirmed the native dialog name, class, handle, and enabled state;
it did not establish its process identity against the original browser window.
The readiness retry also reached Save As and timed out on 2026-09-13. A later
diagnostic from the original captured score isolated the mismatch to the UIA
process ID; name, class, exact handle, source ownership and modal state matched.
The correction now verifies the native host process's executable against the
source Edge executable. It does not require equal process IDs. On 2026-09-15,
desktop control stopped because it could not reliably determine Edge's current
URL. The corrected complete live save remains unverified.

The complete check for the native-process correction passed on 2026-09-15:
configuration validation, source compilation, and **1,469 tests, 2 skipped**
(343.356 seconds for the test suite). Focused controls/native checks also
passed. `git diff --check` passed; no files are staged. These results cover
simulation and native compilation, not a completed live browser save.

The earlier check, before the native-process correction, passed on 2026-09-13:
configuration validation, source compilation, and **1,469 tests, 2 skipped**
(277.640 seconds for the test suite). `git diff --check` passed. No files were
staged. These automated results do not establish a completed browser save.

The user reported that the previous live happy path works. That report does not
cover the saved-Action menu, shortcut, or folder-editing paths. Automated tests
use injected process/UI boundaries; they do not execute the Windows accessibility
helper against the user's browser.

Optional follow-up checks, not a condition of the current owner acceptance:
Action creation/folder editing, Music menu/right-click edit and slot 6 after
F9 capture; correct instrument/pages after manual Save; manual filename/folder
choice and Edge overwrite handling; Cancel, unavailable configured folder,
wrong-page/printer refusal, changed foreground, display scaling and a second PC.
Input / Output and clipboard preservation is assessed after the usual F9
capture. These checks remain unverified unless separately recorded. Automatic
publication, duplicate numbering and verified-result controls remain outside
the accepted manual path; do not mark them passed from a manual PDF save.

## Webpage PDF acceptance

The new webpage PDF function has separate acceptance from the 2026-09-09 batch.
Focused automated coverage lives in `test_webpage_pdf.py`,
`test_webpage_pdf_window.py` and `test_webpage_pdf_integration.py`. Backend and
routing tests use mocked process/picker boundaries. Window tests use actual Tk
widgets with an injected renderer; they prove lifecycle behavior, not website fidelity.

On 2026-09-13, a controlled Windows smoke used installed Edge 153.0.4234.32
against a temporary loopback HTTP fixture. It produced a 50,809-byte, two-page
PDF in 2.97 seconds. Both rendered PDF pages were visually inspected: text,
print styles, accented/currency characters, a table, an inline SVG image and
JavaScript-generated text were present. A second save preserved an existing
PDF byte-for-byte. Cancelling a deliberately slow page left no destination or
staging directory. A separate public `https://example.com/` render produced a
readable one-page PDF with the expected Example Domain content. These checks
prove browser integration, not arbitrary website fidelity or completed owner
UAT. Test files are ignored runtime evidence.

On Windows, paste a complete URL into Input / Output and choose **Send to… →
Save webpage as PDF…**. Check a public article, a long page and a page containing
images or JavaScript. Choose a new file, open it and inspect text, images and
page breaks. Then check cancellation, repeated activation, Quit while busy,
an existing destination, an invalid/multiple URL, and a failed page load. Keep
Input / Output and clipboard sentinel text for comparison. Verify Open PDF and
Open folder, keyboard access and controls at 100%, 125% and 150% Windows scaling.
Use browser printing for pages that need sign-in; isolated output may contain a
cookie notice or error page, which is not a successful content-fidelity check.

## Complete automated check

From the repository root:

```powershell
.\check-context-palette.bat
```

This command:

1. Validates shared and local configuration and cross-file action references.
2. Compiles `src`.
3. Runs the complete `unittest` suite, including internal Markdown-link and
   filename-casing validation for root, `docs/`, and `integrations/` guides.

It is read-only except for Python bytecode caches.

### Python access from Codex

The project-local `.venv` uses a Python installation under the Windows user
profile. A restricted Codex workspace sandbox can block that external
interpreter and produce `Access is denied` or `Unable to create process`, even
when Python works normally.

If that happens, rerun the same read-only check with authorized normal Windows
access before concluding that `.venv` needs repair. Rebuild the environment only
when the normal Windows check also fails.

Setup applies the same safeguard. A failed `.venv` check, including a missing
pip installation, does not move or rebuild the environment unless an
independent compatible Python 3.12 or newer 3.x interpreter with pip and
Tkinter can launch in that process. When both checks are inaccessible, setup
stops and requests a normal Windows retry.

## Targeted tests

Run one module while developing:

```powershell
.\python-context-palette.bat -m unittest tests.test_actions
```

Run the entire suite directly:

```powershell
.\python-context-palette.bat -m unittest discover tests
```

The wrapper runs the project-local interpreter with `src` on Python's import
path, so application modules work consistently from the repository root. It
distinguishes an unusable Python environment (repair with setup) from a project
import error (investigate with the complete check).

The inert real-Tk visual baselines have a focused size/scaling stress check:

```powershell
.\python-context-palette.bat -m unittest tests.test_ui_mockups
```

It constructs the main palette, Configure Work Items, and Configure Actions at
their normal and minimum sizes under simulated 100%, 125%, and 150% text
scaling. This protects geometry and state contracts but does not replace the
actual Windows display-scale review in [Real-Tk UI mockups](UI_MOCKUPS.md).

Do not document a fixed test count; it changes as coverage grows.

## Why GitHub runs the tests again

The repository contains `.github/workflows/tests.yml`. GitHub automatically
runs that workflow after every push and for every pull request; starting a run
does not require a separate instruction from the user or Codex.

This check deliberately repeats the local automated check in a fresh Windows
environment. The local check provides fast feedback before a commit, while the
GitHub check verifies that the committed repository can set itself up without
the current computer's existing virtual environment, caches, ignored personal
files, or other local state. Its Windows, Python, and Tk versions can also
expose portability problems that do not reproduce on the development computer.

A push should therefore normally follow a successful local
`.\check-context-palette.bat` run, but a local pass does not guarantee that the
GitHub run will pass. If GitHub reports a failure, open the linked workflow run
and inspect the failed step and test output before changing code. Warnings and
the final `Process completed with exit code 1` annotation are often secondary;
the first failed command or test identifies the useful cause.

GitHub may email the repository owner or subscribed participants when this
automatic run fails. That notification is controlled by the user's GitHub
Actions notification settings, not by Context Palette. A message saying that
all jobs failed can still represent one failed test when the workflow contains
only one job.

## Bulk Actions workbook manual check

1. Open Configure → Actions → **More Action tasks → Get blank Actions
   workbook…** and save the generated `.xlsx`.
2. In Excel, add Ready rows for several supported types, General and personal
   Contexts, normalized and mixed-case tags, descriptions, a supported Quick
   menu, multiline arguments, and a Working folder. Add Import=No, an undefined
   Context, unknown/excluded type, exact duplicate, possible duplicate, and
   same-workbook duplicate rows. Put Arguments and a Working folder on an
   Action type that does not support them and confirm they are row errors. Save
   and close the workbook.
3. Choose **Create Actions from Excel…**. Confirm row/status counts, complete
   selected-row details, default selection of only Ready rows, and explicit
   selection for a possible duplicate. Errors and exact-existing rows must not
   become selectable.
4. Change the workbook after review and confirm creation stops until Reload.
   Change an Action or Context store after review and confirm the same stale
   stop. Restore the review, choose **Create N Actions**, and confirm there is no
   second Yes/No dialog, all selected personal Active Actions and Context
   memberships appear together, and no Action executes.
5. Confirm formulas, changed headers, corrupt/encrypted or oversized packages,
   data outside A–J, and more than 1,000 populated rows stop without writes.
   Repeat at 100%, 125%, and 150% scaling and on a PC without Excel installed.

## Automatic Quick-menu organization manual check

Status: **Manual UAT pending.**

1. Create or edit one Password, Folder, and AI-prompt Action. Confirm the form
   names the correct fixed menu, shows **Menu root** explicitly, and uses a
   read-only breadcrumb plus **Choose…**, not a free-text `>` field.
2. In the chooser, search existing branches, select the root and a nested
   branch, create a new submenu under each, and verify a fourth level is
   unavailable. Cancel once and confirm the saved placement is unchanged.
3. In Configure → Quick actions, select an automatic root and choose **Manage
   menu…**. Confirm **Submenu tasks** offers only **New submenu…** at the root.
   Select one or more Active Actions, create a submenu, and verify every exact
   before → after path plus ownership/file counts before **Create submenu
   with N Actions**. Confirm no-selection explains why an Active Action is
   required, and level three disables creation.
4. Select a populated automatic branch and choose **Manage this submenu…**.
   Confirm **Submenu tasks** offers New child, Rename, Move, and Remove. Rename
   it, move it beneath a new parent while preserving its name, and merge it into
   a case-variant existing branch. Remove it and verify direct Actions move to
   the parent, child submenus move up intact, and the final button says **Remove
   submenu; keep N Actions**.
5. Select one automatic Action leaf in that branch and choose **Remove from
   submenu…**. Confirm its exact stable ID is preselected, the review promotes
   it one level, and the record and external target remain unchanged. Repeat
   with several direct members through **Remove selected from this submenu**;
   include two equal titles and confirm the correct IDs move. Confirm the last
   member removes the empty branch. At the automatic root, confirm no Remove
   command appears and the UI names permanent Action deletion as the only way
   to remove the required automatic leaf.
6. Change an Action file after review and confirm commit stops as stale. Inject
   a second-file write failure and verify exact primary/backup rollback; inject
   rollback failure and verify the organizer locks further mutation and directs
   backup/Diagnostics inspection. Confirm no Action executes and no external
   file, folder, credential, prompt target, or configured Quick-action reference
   changes.
7. Repeat the editor, chooser, and manager using keyboard only and at 100%,
   125%, and 150% scaling. Confirm search, tree, reviewed detail, fixed status,
   Submenu tasks menu, effect-labelled button, and Close remain reachable.

## Configured Quick-action placements manual check

Status: **Manual UAT pending.**

1. Create a Folder, Password, or AI-prompt Action and open **Menu locations**.
   Confirm the same screen shows one automatic tree and an optional configured
   checklist. Select a configured location, save once, and confirm both the
   Action and reference exist. Repeat while editing, then select the saved
   Action in Configure → Actions and open **Other menus…**. Confirm its
   **Automatic placement (read-only)** value names the exact
   Folders/Passwords/Prompts location and `quick_action_path`. Open another
   Action type with no automatic
   menu and confirm it says none without disabling configured placement
   management.
2. Search the configured root/branch table and select zero, one, then multiple
   locations. Confirm the current references are represented exactly and the
   review lists every addition, removal, and newly empty item before the
   effect-labelled Apply command. Applying must not show another Yes/No dialog,
   execute the Action, change its automatic placement, or reorder unrelated
   targets.
3. Switch Storage before creation and confirm newly invalid staged locations
   are cleared with a visible explanation. With a personal Action, confirm
   Built-in locations are visibly blocked and
   cannot be selected. With a Built-in Action, add eligible Built-in and My
   configuration references, reload, and confirm every placement remains.
   Revert disposable tracked changes afterward.
4. Remove all configured references and confirm the automatic menu remains
   unchanged. Then add the same Action to several configured roots/branches and
   confirm every launcher reference resolves the same Action ID; no duplicate
   Action or new placement schema should appear in either command-surface file.
5. Change a participating Action or command-surface file after review and
   confirm Apply stops as stale. Inject a later-file write failure and verify
   exact primary and `.bak` rollback. Inject rollback failure and confirm
   further writes are disabled with backup/Diagnostics guidance and no success
   claim.
6. Repeat with keyboard-only selection, Find focused during `Ctrl+A`, and at
   100%, 125%, and 150% scaling. The searchable table, exact review, fixed
   status, effect-labelled Apply button, and Close must remain reachable.

## Bulk Action update workbook manual check

Status: **Manual UAT pending.**

1. Open Configure → Actions → **More Action tasks → Export personal
   Actions for update…** and save the deterministic version-1 `.xlsx`. Confirm
   it contains only eligible personal Active ordinary Actions. Built-in,
   Legacy inactive, sequence, Excel-automation, and text-file-transform Actions must
   not appear.
2. In Excel, edit Name, Value, personal Contexts, tags, description, Quick menu,
   lossless Arguments JSON (including an empty and whitespace-only argument),
   and Working folder on representative compatible types. Include a quoted
   Context or tag containing a semicolon and a Context containing repeated
   spaces. Leave one row
   unchanged. Remove another complete row. Save and close the workbook.
3. Choose **More Action tasks → Review updated Actions workbook…**. Confirm
   only real valid changes are Ready and selected by default, the unchanged row
   is not selectable, every exact Before/After value is readable, and the
   removed row causes no deletion or Action-state change. Clear and restore one
   Ready selection with mouse and keyboard.
4. On separate fresh exports, change Action ID, State, Action type, Original
   fingerprint, a header, a formula cell, and workbook/package structure.
   Confirm each tampered, macro/link-bearing, corrupt, or unsafe workbook is
   rejected without writes. Also confirm undefined/shared Contexts and invalid
   type-specific fields become row errors.
5. Change the workbook after review, then separately change the saved Action or
   Context configuration after review. Confirm **Update N Actions** stops and a
   fresh review/export is required. Restore a Ready review and update selected
   rows; confirm the labelled button is the only confirmation, all changes land
   together, no Action runs, and deletion remains outside workbook semantics.
6. In the automated failure fixture, make Context persistence fail after the
   Action write and compare the local Action file byte-for-byte with its prior
   contents. No partial Action update may remain. Then inject a rollback write
   failure and confirm the window says configuration may have changed, disables
   export/choose/reload/update, and never says that no Actions were updated or
   offers a generic retry. Repeat the attended UI at 100%, 125%, and 150%
   scaling and on a PC without Excel installed.

## Bulk Action deletion manual check

Status: **Manual UAT pending.**

1. Create several disposable personal Active Actions and place them in a
   personal Context, Context slots, and configured Quick menus. Add one
   sequence that refers to another disposable Action. Keep the external test
   files, folders, URLs, or applications easy to inspect afterward.
2. Open Configure → Actions → **More Action tasks → Delete multiple
   personal Actions…**. Confirm Built-in Actions are absent. Use Find,
   **Select all shown**, **Clear selection**, mouse selection, and `Space`.
   Verify the footer buttons, status, and selected-Action details remain visible
   at 100%, 125%, and 150% scaling. Change Find after selecting rows and confirm
   the status and final button count selected rows hidden by the filter.
3. Select an Action that an unselected sequence uses. Confirm it is blocked and
   names the dependent sequence. Select that personal sequence too and confirm
   the batch becomes Ready. Review the combined saved-reference, empty
   Quick-action-item, and changed-file counts. No Action may execute.
4. Choose **Delete N Actions permanently**. Confirm this effect-labelled button
   is the only confirmation and there is no extra Yes/No dialog; the exact
   selected records and saved placements disappear; unrelated Actions and
   empty root Quick menus remain; and every external target is unchanged.
5. Repeat with one legacy inactive personal record. Confirm it is explicitly
   labelled, cannot be edited or restored, and can be included in the same
   deletion review without becoming Active.
6. In separate automated fixtures, change a participating Action, Context,
   palette, or Quick-menu file after review and confirm deletion stops as
   stale. Make a later configuration write fail and compare every participating
   primary file and `.bak` sidecar byte-for-byte with its prior state. No
   partial stage may remain.

## Send files to a folder manual check

Use disposable source and destination folders only. Include small text files,
a larger file, two same-named files from different folders, and pre-existing
destination files.

1. Put one exact absolute file path in Input / Output and choose **Send to…**.
   Confirm the menu exposes a selected Work Item when applicable,
   Context-relevant Folder Actions first, session recents, hierarchical all
   Folder Actions, **Find destination…**, **Choose another folder…**, and
   **Manage Folder Actions…**. Confirm ordinary execution of that same Folder
   Action still opens its folder and copies nothing. Include one relative
   Folder Action and one `file:` URI and confirm they resolve like ordinary Run.
   Include one Folder Action containing `%CLIPBOARD%`; confirm it is visibly
   unavailable as a copy destination, the clipboard is not read, and no copy
   workflow starts, while ordinary Run still expands it normally.
2. Choose an empty destination. Confirm choosing it is the only confirmation,
   copying begins in the background, the source and Input / Output remain
   unchanged, and the exact created file plus **Open destination folder** are
   shown. Confirm the successful destination enters Recent; cancel/error and
   partial results must not enter it. Restart the app and verify Recent is
   empty.
3. Create an existing `report.txt`, then send another `report.txt` with
   overwrite off. Confirm review shows the exact `report(1).txt` mapping and
   one **Copy 1 file** button. Add `report(1).txt` and confirm `report(2).txt`.
   Check **Allow overwrite** and confirm the plan targets unsuffixed
   `report.txt`, identifies one replacement, and uses **Replace 1 file** with
   no further Yes/No dialog.
4. Send two sources with the same basename. Confirm they never target the same
   final path, including with overwrite checked. Send a source already in the
   destination and confirm it is skipped rather than duplicated. Change a
   source or destination after review and verify copying stops as stale before
   an unreviewed effect.
5. Exercise quoted paths, Unicode, UNC availability, blank lines, a relative
   path, missing file, folder, URL/prose, duplicate source, 100 files, and 101
   files. Invalid input must produce no destination effects. Verify no source
   path is copied to the clipboard, logs, configuration, or recent-destination
   state.
6. During a multi-file copy choose **Stop remaining**. Confirm the current file
   completes, later files do not start, completed destinations remain, exact
   effects are reported, and no rollback/retry is claimed. Confirm Hide remains
   available but Quit is blocked until the operation's outcome is delivered.
7. Repeat the header, conflict review, busy, stopped, partial, and result states
   at 100%, 125%, and 150% display scaling and the supported minimum window.
   Confirm the literal Send-to label, status, review controls, and fixed footer
   never disappear.

## Open one Input / Output path in VS Code manual check

Use disposable local paths and close without saving anything VS Code may show.
This is an operating-system protocol handoff, not a file-copy test.

1. Put one existing absolute folder path in Input / Output and choose **Send
   to… → Open with → Open folder in VS Code**. Confirm VS Code opens that exact
   folder and no copy-review window appears.
2. Repeat with one existing file path, including matching outer quotes and a
   path containing spaces and Unicode. Confirm VS Code opens the file's
   containing folder, not a new copy and not a persisted recent destination.
3. Exercise empty, two-line, relative, missing, unavailable network, and
   unmatched-quote input. Confirm each invalid case opens nothing and explains
   how to provide one existing absolute file or folder.
4. On a disposable standard-user machine without VS Code or without a
   registered `vscode:` handler, confirm the handoff reports that setup problem
   without administrator rights or raw operating-system details. The rest of
   Context Palette must continue to work.
5. Before and after every case, compare Input / Output and the clipboard and
   inspect the source path. Confirm they are unchanged, no file was copied or
   moved, no copy destination was added to Recent, and no Folder Action ran.
   Run the same **Open a folder** Action normally and confirm it still performs
   only its ordinary open-folder effect.
6. Repeat the menu at 100%, 125%, and 150% scaling and at the supported minimum
   window. Confirm **Open with:** visually separates the opener from copy
   destinations and **Open folder in VS Code** remains readable and reachable.

## Historical Harvest verification — retired

Harvest was retired on 2026-10-05. The dated observations and procedure below
are historical evidence, not commands for the current app. No re-run is required.

Last completed: **Passed on Windows on 2026-07-21.** The attended check used
representative Markdown, text, Word, and Excel files, including cross-format
duplicates, unsupported and malformed links, a corrupt source, cancellation,
an initially absent personal action store, a late duplicate, repeated
submission, and a cold application restart. All requested workflow checks
passed. The check also exposed and corrected clipped bulk-edit controls at the
standard Harvest window size.

Keyboard accessibility check: **Passed on Windows on 2026-07-22.** Physical
Windows key input verified `Ctrl+F` candidate search, `F5` rescan with focus
returning to Candidates, `Space` inclusion toggling, and `Enter` candidate
editing. The isolated check created no personal action store. The remaining
bindings, action-preview Close control, and focus-restoration callbacks are
covered by real-Tk and focused unit tests.

1. Press `Ctrl+,`, open **Actions**, choose **More Action tasks → Harvest
   website links…**, and select
   several representative `.md`, `.txt`, `.docx`, and `.xlsx` files.
2. Confirm progress remains responsive, Cancel stops safely, and a corrupt or
   unavailable file reports its own failure without hiding successful sources.
3. Check a repeated URL, conflicting labels, an existing Active URL, and a
   non-HTTP target. Verify their readiness and duplicate
   states, provenance, and default selection.
4. Edit one candidate and use explicit Add/Remove for Context memberships and
   tags. Preview the selected actions.
5. Cancel the confirmation and verify the personal action file is unchanged.
   Then confirm once and verify all selected actions appear together as Active
   **Open a website** actions.
6. Repeat the launch from Inbox and verify it opens the same review workflow.

Run the documentation-link check directly after moving or renaming a guide:

```powershell
.\python-context-palette.bat -m unittest tests.test_documentation_links
```

The checker reports the source document, line number, target, and whether the
path is missing or has incorrect filename casing. It intentionally ignores web
links, email links, heading-only anchors, inline-code examples, and fenced code
blocks.

`tests.test_launcher_smoke` exercises the real Tk view transitions among All
items, Actions, and Work Items with the unified transient Filter menu. Its
temporary fixture proves that one Context or tag can return both an Action and
a Work Item and only canonical Context members enter Context-filtered results.
It also verifies that **All contexts** uses General's slot bank, a specific
Context selects its own bank, Context and tag operate across all item scopes,
type and project remain kind-specific without changing banks, non-empty Find
results are relevance-ranked without context-slot promotion, and dormant
type/project filters remain visible in the filter chip.
`tests.test_launcher_interactions` verifies that F5 returns to **All contexts**
while preserving per-Context slot assignments and compatibility palette data.
`tests.test_action_preview` requires every supported Action type to produce a
bounded, readable **Input → Effect** summary and structured details without
technical type IDs. It protects current-input, captured-selection, destination,
credential, AI, file-recovery, and Windows-target safety wording. The launcher
smoke test verifies real Action and Work Item selections, workbook/folder
fallback, content-change refresh, and restoration after an operational message.
The same module also constructs a clean-PC data directory containing only the
tracked Built-in actions, context, and Quick-action files. It verifies that the
launcher and Configure window load entirely from those files without creating
Inbox, palette, Work Item, or local customization files merely by reading
configuration. A second clean-PC integration creates the first personal action,
context, and Quick action through the real Configure save boundaries, then
constructs a fresh launcher and verifies all three reload while unrelated
private files remain absent.
It also verifies that the real Configure page stack exposes Diagnostics with a
read-only scrollable summary plus keyboard-reachable Refresh and Copy controls.
`tests.test_diagnostics` protects the allow-listed parser and privacy boundary;
`tests.test_configuration_window` verifies exact safe-summary copying and
honest failure feedback when the Windows clipboard is unavailable.
`tests.test_action_deletion` verifies direct Active and legacy-inactive deletion,
exact saved-reference cleanup, and restoration of exact bytes across all
attempted files when any write fails, including explicit incomplete rollback.
`tests.test_work_item_organization` verifies inspection, idempotent Forget,
complete personal-reference cleanup, exact-byte rollback, and the hard boundary
that no external Work Item content path participates in the transaction.

## Manual Windows smoke test

### Verification record

Use this record for every manual pass. Do not replace **Not tested** with a
result until the check was actually performed on Windows.

| Field | Value |
| --- | --- |
| Date | Not tested |
| Tester | Not tested |
| Commit/working tree | Not tested |
| Computer and Windows version | Not tested |
| Display scale and resolution | Not tested |
| Keyboard layout | Not tested |
| Python version | Not tested |
| Work Item source/path used | Not tested |
| Excel version | Not tested |
| Overall result | **Not tested** |
| Notes/issues | Not tested |

Record each numbered check below as **Pass**, **Fail**, **Blocked**, or **Not
tested**, with a short note for any result other than Pass. Automated tests may
support the record but must never be entered as a manual Pass.

### Work Items Phase 5 result — 2026-07-21

User-reported manual checks on the primary Windows computer:

| Check | Result | Notes |
| --- | --- | --- |
| Open an exact matching workbook in Excel | Pass | Opened successfully in real Excel. |
| Fall back to the Work Item folder when the exact workbook is absent | Pass | Folder fallback worked. |
| Unavailable or network source | Not tested | Requires a suitable unavailable or network location. |
| Keyboard navigation and Work Item context menu | Pass | Keyboard and context-menu opening worked. |
| Different computer with a different absolute source path | Not tested | Requires the second development computer. |
| Display scaling and responsive layout | Pass | User confirmed the interface remained usable; scale percentage and resolution were not recorded. |

This is a partial manual result, not completion of Phase 5. The unavailable
source and different-computer/path checks remain outstanding.

Run this when launcher behavior, styling, hotkeys, clipboard handling, or configuration windows change:

1. Start with `run-context-palette.bat`; verify only one resident instance is created.
2. Press `F9`, then `Ctrl+Alt+P`; verify the palette appears centered in the
   usable area of the cursor's monitor and selected text is captured where the
   source application permits simulated copy. Repeat on a secondary monitor,
   including one with negative desktop coordinates. Move Configure to that
   monitor and open an Action editor; confirm the editor centers on the same
   monitor. Confirm compact filter pickers, menus, and tooltips remain attached
   to their controls, and the separate drop target retains its lower-right,
   user-movable placement.
3. Verify `Esc` hides, `Ctrl+L` focuses Find, `Ctrl+N` opens the Action-type
   chooser, `Ctrl+,` opens Configure on **Start**, and `F1` opens Help. On
   Start, verify all six primary tasks are visible without scrolling. Open each
   destination and confirm it reuses the same Configure window. Verify
   **Create an Action...** opens the existing type chooser, while direct Edit,
   Work Item, Diagnostics, and Filter-menu **Manage contexts…** routes bypass
   Start. In the chooser,
   verify typing filters types, arrows and Enter choose one, and Escape or
   Cancel changes nothing. Repeat with **New Action…** and `Ctrl+N` on Configure
   → Actions; confirm a specific active Context filter is offered as the initial Context,
   an existing Configure workspace is reused, and backup/restore busy state
   refuses the request.
   Put one absolute file path in Input / Output, including a quoted path with
   spaces, and choose **Create Action...** beside **Text tools**. Verify **Open a
   file** opens directly with an editable suggested name and the complete path
   prefilled, even when it wraps visually. Repeat with an existing folder,
   `.exe`, and complete HTTP/HTTPS address. Select just the address inside a
   longer note and verify the selection wins. Try prose, multiple targets, a
   genuine multi-line value, a relative path, and a script-like path; verify
   none is guessed. Try an unavailable absolute document path and verify the
   review form appears immediately without waiting for the drive.
   Cancel each form and confirm nothing is created or run. Finally verify the
   existing launcher **Create Action** control still opens its normal unprefilled type chooser.
   On initial display, verify the command console occupies about 40% of the
   width, Input / Output occupies about 60% and nearly the full height, Find is
   no wider than its result list, and up to seven result rows are visible at
   normal scaling, with fewer retained at increased scaling. Verify
   there is no separate top toolbar or bottom command bar. Confirm **All items**
   contains both Actions and Work Items. Select one of
   each and verify the primary command changes between Run and Open. Choose one
   Context filter and one tag that each belong to both kinds and verify both
   remain in the mixed results. Switch to Actions, then Work Items, and back;
   verify the shared Context/tag filters and chosen slot bank remain active and the
   filter menu changes between Action type tools and Work Item/project tools
   without moving Find, the result list, or the stable Create Action/Edit/Run toolbar.
   Verify Configure, Help, and More remain below Quick actions. Resize to the
   supported minimum and verify the filter control, item toolbar, app controls,
   and all three scope labels remain available. Drag
   the vertical divider and verify both sides remain bounded and the manual
   balance remains adjustable for the session.
   While moving through representative Actions and Work Items, verify the
   bottom line consistently reads **Input → Effect** before Run/Open. Include an
   empty and populated Input / Output transform, a saved-text action opened
   with and without a fresh hotkey destination, an AI prompt, a protected
   credential, a Windows target, a text-file transform, and Work Items with and
   without matching workbooks. Confirm risk, non-submission, cleanup, unchanged
   source, and folder fallback remain visible. Hover and click the line to
   verify structured details, then run an item and confirm its operational
   result temporarily replaces the preview. Select again to restore it.
4. Enter Find text, choose a Context filter, activate tag/type/project filters,
   and put text in Input / Output. Press `F5`; verify transient values clear,
   Find regains focus, **All contexts** and General's slot bank become active,
   and legacy focus/pin data plus every per-Context slot assignment remain
   unchanged. Restart and confirm no result filter is restored or added to
   `data/palette.json`.
5. From a disposable text field, open the palette with the hotkey and run a
   saved-text action. Verify the palette hides, the original window regains
   focus, and the text is pasted. Open Context Palette without a captured
   destination and verify the same action copies only with a manual-paste
   status. Reopen by hotkey, run or cancel a non-paste action, then verify a
   later saved-text action does not paste into the original window. Verify
   number-row shortcuts run only while Find has focus.
   With simulated Windows input dispatch failure, verify the hidden palette
   returns, ordinary text remains on the clipboard, protected credential text
   is cleared, and the error gives the appropriate recovery instruction.
   Inspect the local log for success, no-destination, unavailable-destination,
   and dispatch-error outcomes. Verify sample saved text, credential targets,
   usernames, passwords, and window titles are absent from every event.
6. Right-click a personal Action in ordinary results.
   Verify Configure opens on Actions with the clicked row highlighted and its
   name, contexts, and tags editable after choosing **Edit…**. From the
   main palette, select the same Action and choose **Edit**; verify its editor
   opens directly in the reused Configure workspace. Repeat with a disposable Built-in action,
   verify the Git/private-data warning appears, cancel once, then accept and
   verify the Built-in file receives the reviewed edit. Revert that disposable
   edit afterward. In Configure -> Actions, delete a disposable personal Action
   assigned to a Context, context slot, and configured Quick action. Cancel the
   first review and confirm nothing changes. Repeat and verify the review names
   the exact stable ID and placement impact, the Action disappears from every
   runtime placement, and its external target remains unchanged. Repeat review
   cancellation with a disposable Built-in Action and verify the
   Git/multi-computer warning.
   In Configure, confirm **Set up** and **Support** are visually separate and no
   horizontal tab strip appears. On Actions, verify no pin configuration or Pin
   toolbar command remains and the delete command stays readable. On Work
   Items, verify **Manage sources…** contains Add, Edit, Remove, and Creation
   template while Refresh remains visible; with no sources, Add and template
   stay available while Edit, Remove, and Refresh are disabled.
7. While **All items** is active, choose a specific **Filter by context…** value
   and verify Actions and Work Items are limited to canonical membership while
   slots 6–0 switch to that Context's bank. Repeat in Actions and Work Items;
   verify the same Context and tag remain active across all three views. Apply
   Action type, Work Item project, tag, and Find values in turn and verify they
   narrow results without selecting another slot bank. Choose **All contexts**
   and verify global results plus General's bank return. With Find empty,
   confirm genuine slots 6–0 can appear first and unused slots remain empty.
   Enter queries matching an exact name, prefix, visible-name substring, and
   metadata only; verify relevance order and no shortcut promotion. Confirm
   Shift+1–5 never executes and legacy focus/pin IDs survive a palette-state
   save without restoring a Context filter.
   Open Configure → Contexts and verify **General — All items** is the fixed
   first row. Confirm its card offers **Edit shortcuts…** but no rename,
    membership, or delete command. Assign an Action and a Work Item to slots 6
    and 7, save, clear to **All contexts**, and verify that General bank appears.
    Reopen the editor and verify unassigned rows show their effective
    **Automatic — _item_** values. Return every row to **Automatic**, save, and
    verify automatic General ordering returns. Confirm no General record was
    added to either Context file and the preferences were stored only in local
    palette state.
8. At the standard `780x600` size and supported minimum, verify Quick actions
   use two readable columns without clipping beneath discovery. Narrow the
   command console until one column is genuinely necessary, then verify stable
   row-major order returns. Confirm fixed Standard is first, personal configured
   menus precede shared configured menus, automatic Passwords/Folders/Prompts
   follow them, and every launcher remains menu-only. Tab through the visible scope controls,
   Find/filter/results, item toolbar, Quick actions, app controls, workspace
   header controls, and Input / Output. Press Enter or Space on a
   Quick-action launcher and verify it opens the menu without running an
   Action. Open every Text tools group and verify it matches the
   right-click Transform catalogue. Exercise a text-file preview and verify its
   provenance, Replace original, Save as, and Dismiss strip remains usable.
   In **Lists**, transform separate `alpha`, `42`, and `O'Brien` values with
   the no-quote, single-quoted-text, and double-quoted-text commands. Verify the
   outputs match Help, numbers remain unquoted, embedded quotes are doubled,
   and a quoted value containing a comma remains one value. Verify the SQL
   command adds parentheses and keeps `NULL` unquoted.
9. Create disposable actions and contexts in both **My configuration** and
   **Built-in**; reload and confirm each uses the selected file. In a My
   configuration Context, assign a Built-in Action, a personal Action, and a
   disposable Work Item, then verify all three appear under that Context filter
   without editing either Action or the Work Item folder. Put the Work Item in slot 6,
   verify `Shift+6` opens its workbook/folder, disconnect its source, and verify
   the unavailable reference remains saved and recoverable after reconnection. Create
   two Quick-action groups, add more than four ordered Actions to one item,
   move the item and groups, and verify launcher left-click browses while
   launcher right-click offers Add/Organize. Inside the menu, verify Action
   left-click runs only the selected Action and Action right-click opens only
   its editor. Rename and delete an item and group. Delete a
   disposable Context and verify its Action memberships and slot configuration clear.
   Assign an Action to a context slot, Context preference, and Quick action.
   Choose **Delete permanently…**, verify the
   confirmation reports its references, cancel once, then accept and verify the
   action and all references disappear. Repeat the warning check with a
   disposable Built-in action, revert tracked test changes, and remove the
   remaining disposable records afterward.
   In every Action-reference field used above—Context membership,
   preferred slots, and Quick-action assignments—open **Find…**, search by
   action name and by a metadata term such as type, context, or tag, and verify
   Down Arrow plus Enter and double-click select the expected action. Verify
   **Not assigned** clears a preferred slot without widening
   Configure beyond the screen.
10. In an action form, verify `Alt+C` focuses Specific contexts and `Alt+T`
   focuses Tags. From each field, verify `Alt+Down` or `F4` opens **Choose…**,
   arrow keys move through the checklist, Space toggles an item, and `Esc`
   closes it without losing typed values.
11. Verify compact bitmap controls remain fully visible and their tooltips begin
    with semantic command names for Filter, Edit, Capture, Inbox, Extract
    text, Text tools, Configure, Help, and More. Switch views and verify the
    stable item toolbar does not move while scope-specific commands change in
    the filter menu. Open More and verify the searchable Keyboard Shortcuts page
    appears. With
    Find focused on an AZERTY keyboard, press Shift plus
    each physical top-row key from 6 through 0 and verify the corresponding
    populated context slots execute. Verify Shift+1–5 do nothing, plain
    number-row and numpad digits filter Find, and
    Ctrl+number does not execute a slot.
    Confirm result labels have no numeric prefixes, context shortcut rows are
    green, ordinary results are neutral, and a
    shortcut-row tooltip reports its exact Shift+number binding. Confirm the
    compact controls remain visible without clipping.
    Confirm row icons share one aligned column, names start at one aligned
    position without a dash, and no blank tree-expansion gutter remains before
    the icons in All items.
12. With at least one disposable local Work Item source configured, choose
    **Configure**, then **Work Items**. Add and edit a source using Browse,
    confirm its state and item summary, edit a discovered item's personal tags
    and existing My configuration Context memberships in the same dialog,
    and use Refresh index. Confirm removing the source clearly states that no
    folders or files will be deleted and all Palette organization is retained.
    Re-add it with the same identity and confirm organization returns. On a
    disposable Work Item, choose **Organize → Forget Palette organization…**;
    confirm tags, Context/preferred placement, context slots, and personal
    Quick-menu references are removed while its folder, workbook, files, and
    workbook Inbox remain. Re-add organization needed for the opening checks. Choose
    **Work** and verify Find, Projects, and Tags combine correctly. Press Enter
    on an item with an exact workbook and verify that workbook opens; press
    Shift+Enter and verify its folder opens. Verify an item without the exact
    workbook falls back to its folder. Right-click and check workbook, item
    folder, and source-folder routes. Temporarily make one source unavailable
    and verify other sources refresh while its last successful rows remain.
    Open **Configure**, choose **Quick actions**, add a My configuration level,
    choose an action and at least two Work Items, reorder them together, and verify the resulting
    Quick-action menu preserves the
    mixed order, the Work Item opens the exact workbook, and it falls back to the folder when that workbook is
    absent, and remains configured with a clear unavailable message while its
    source is disconnected. Confirm a Built-in Quick action does not offer a
    Work Item assignment.
    Right-click Passwords, Folders, and Prompts. Confirm each offers its typed
    Add command and Organize/Find commands. Create one disposable Action inside
    a branch and verify the normal form still includes storage, name,
    description, Contexts, tags, target, and the prefilled menu location. Clear
    the location and verify the Action appears at the menu root with no
    **Unsorted** submenu. Delete the disposable Action afterward.
    Select a specific Context filter with fewer than five genuine members and
    confirm slots 6–0 remain empty after its final member instead of showing
    unrelated global Actions. Clear to **All contexts** and confirm General's
    bank returns.
    Run **UAT: Run a harmless sequence**, inspect its two project-folder steps
    and five-second wait, cancel once, then confirm and use **Stop remaining**
    during the wait. Verify the in-app step progress; Explorer may reuse one
    window. Confirm no script runs and no file or clipboard changes.
13. Trigger a validation error and confirm the message identifies the field without losing the form contents.
14. Verify Capture/Inbox and Harvest commands are absent. Existing Actions remain
    editable; old data/inbox.json bytes must not be read/migrated on startup.
    Work Item workbook Inbox is separate and remains available.
15. Open Help, verify in-document search, resize it, maximize it, restore it,
    and confirm responsive tables remain readable.
16. Open Configure → Diagnostics. Verify configuration counts are current,
    Refresh updates recent automatic-paste outcomes, and Copy safe summary
    places the visible report on the clipboard. Confirm raw error messages,
    sample action values, pasted text, credential fields, paths, and window
    titles are absent. Open it directly with `Ctrl+Shift+D` from the focused
    main palette and cycle with `Ctrl+Tab`; verify focus enters the Diagnostics
    summary and each other section's primary control. On QWERTY and AZERTY, verify
    `Alt+A`, `Alt+T`, `Alt+C`, `Alt+Q`, `Alt+W`, `Alt+B`, and `Alt+D` directly select their
    corresponding sections—including **Quick actions** for `Alt+Q`—without closing Configure. With the main palette focused,
    verify `Ctrl+2` and `Ctrl+3` neither close/hide it nor execute action slots;
    plain `2` and `3` must enter Find text without executing a slot.
    Only Shift plus physical top-row `6`–`0`, with Find focused, executes
    the selected Context's slots; All contexts uses General's bank.

## Platform-effect checks

Perform only when relevant:

- Start the app with an empty clipboard and verify **Drop into Context
  Palette** is the only permanently topmost window. Hide the ordinary palette
  and confirm the target remains mapped; show the palette with F9/Ctrl+Alt+P
  and confirm its existing auto-hide and temporary-attention behavior are
  unchanged. Hide and restore the target through **More → Show drop target**.
  Drop Explorer files, a folder, multiple ordered items, a UNC path, a
  percent-encoded path, `.url`, `.lnk`, a browser URL, OneNote link/text, and a
  desktop shortcut. With empty Input / Output, verify direct placement. With
  existing text, independently verify Replace, Append, and Cancel. Confirm the
  target remains visible, stale captured selection/destination state never
  wins, the clipboard is byte-for-byte unchanged, and no target opens or runs.
  Make more than ten successful drops and confirm only the newest ten remain;
  use Previous/Next and confirm the compact path name, web-link host, text
  length, or mixed counts identify each selection. Expand **Show details** and
  verify exact normalized values plus `.url`/`.lnk` warnings, wrapped vertical
  scrolling, a visible truncation notice for large content, and no filesystem,
  web, clipboard, or execution effect. Confirm Hide/Show and a new drop collapse
  details while retaining the in-memory list. Use **Send again** to restore an
  older drop—including content beyond a truncated preview—through the same
  placement choice. Confirm errors/empty drops are absent. In Input / Output, verify Back/Forward across typed,
  dropped, OCR, transformed, and clipboard-replaced content; verify a new edit
  after Back discards the old forward branch while native Undo/Redo still works.
  Repeat the window/layout checks at 100%, 125%, and 150%; after every summary,
  Previous/Next change, and details expansion confirm the complete text plus
  Previous, Next, Send again, Show/Hide details, Hide, and title-bar controls
  remain inside the current monitor work area. Move the target near every edge
  and onto a secondary monitor before repeating. Finally simulate an
  unavailable TkDND component and confirm only the drop target is unavailable,
  launcher status points to **More → Show drop target**, the dialog prescribes
  stop/setup/restart, and no withdrawn partial Toplevel remains after native
  registration or either event-binding failure.

- On a second standard-user PC, pull a revision whose `requirements.txt` does
  not match the local setup marker. Confirm `run-context-palette.bat` refuses
  launch before `pythonw` starts and prints the stop/setup/retry sequence. Run
  setup and confirm normal launch plus the Drop target. Then simulate a native
  TkDND initialization failure with a current marker and confirm the main app
  still opens, every non-drop feature works, and restarting is required after
  repair. No step should require administrator rights.

- On a standard-user Windows PC, first start Context Palette with Python Excel
  absent and then with an invalid configured path. Confirm only the Excel CSV
  Action is unavailable and ordinary discovery, Input / Output, drop intake,
  Actions, Contexts, and Quick menus continue to work. With a separately
  cloned/transferred and bootstrapped Python Excel engine, use disposable
  closed `.xlsx` fixtures. Place exact paths one per Input / Output line and
  repeat from Drop into Context Palette. Confirm the 100-workbook limit,
  required worksheet prompts, automatic first-workbook-folder output, the
  reviewed output-folder override, asynchronous planning, and an
  exact Input → Effect review before execution. Export all used columns to a
  new folder; verify sources are byte-for-byte unchanged, every displayed CSV
  exists, and **Open output folder** opens that folder. Verify an existing
  **Allow overwrite** starts unchecked, and `report.csv` remains unchanged
  while the unchecked plan reviews and creates
  `report(1).csv`, then `report(2).csv` when both earlier names exist. Turn
  **Allow overwrite** on and verify the review targets unsuffixed `report.csv`,
  labels it **Replaces**, shows exact create/replace counts, and uses one
  effect-labelled button. Confirm a mixed batch can show **Replace 1 and create
  2 CSV files**. Execute only against disposable outputs; verify created and
  replaced results are listed separately and sources remain byte-for-byte
  unchanged. Change a reviewed source or destination and confirm exact
  stale-plan handling requires a fresh plan and review. Inject a pre-effect
  failure, partial-effect failure, and lost process and confirm distinct honest
  states with no automatic retry. Confirm no replacement backup/rollback,
  cancellation/progress claim, sequence route, Context Palette filename
  allocation, or desktop Excel launch.

- With a separately bootstrapped Python Excel engine at commit `e405e14`, use
  a disposable already-open workbook to run **Apply Excel format template**.
  Confirm missing/invalid launcher setup disables only Excel Actions; inventory
  finds the active workbook; the workbook/worksheet labels, captured-F9
  preselection, active-sheet fallback, inline Refresh, and Return eligibility
  match the conversion Action; one-worksheet and all-visible choices act only on
  the displayed target; AutoSave is rejected; and Standard data applies Aptos
  11 to the used range, row-1 header treatment, freeze top row, and a filter
  only when absent. Verify hidden sheets are skipped, stale inventory requires
  Refresh, and exact partial/unknown results require inspection rather than an
  automatic retry. Confirm Context Palette never saves or closes Excel, Apply
  has no second confirmation, and Return to Excel is only a best-effort focus
  request. The disposable one-worksheet path with an existing filter passed on
  2026-08-25. Repeat the complete matrix at 100%, 125%, and 150% display
  scaling.

- Against published Python Excel `c081510` or a later revision retaining the
  blank-preserving fix, run **Convert Excel values to text** from normal startup.
  Confirm capability discovery and that its initial workbook/worksheet chooser
  matches the format-template Action, including duplicate-name labels,
  captured-F9 preference, active visible worksheet, inline Refresh, and
  Return-to-Excel eligibility. Then confirm paged preflight, physical
  column selection, and planning work. Convert must remain disabled with no
  selected columns or incomplete column pages, then enable after complete
  selection. No startup opt-in is needed; optional Review must not execute.
  Old flag values must not change availability. Use only a disposable open
  `.xlsx`: include scientific text, ordinary text,
  leading-zero identifiers, current numeric scalars, blank and duplicate
  headers, and formulas outside the selected columns. Verify selected eligible
  cells become text; ordinary/leading-zero text content is unchanged; only
  selected physical columns and used data rows change; the header and formulas
  outside scope are untouched; Excel remains open, dirty, and unsaved; and no
  extra Excel process remains. In a separate fixture, put a formula inside the
  selected scope and verify the plan blocks with no Execute.
- Review default and overridden sibling recovery paths; every override must
  produce a new plan. Confirm the engine-created recovery workbook opens and
  contains the pre-change state. Exercise precision-risk acknowledgement,
  stale workbook/sheet/plan, an existing recovery path, a clean failure with a
  verified recovery, partial failure, and process/protocol loss. Confirm no
  automatic retry, exact completed-column/count reporting, and guidance to
  inspect Excel and recovery before another run. Repeat with Unicode names,
  duplicate workbook names in separate Excel processes, blank/duplicate
  headers, enough columns to exercise paging/truncation, Return to Excel, and
  100%/125%/150% scaling. Never record the configured launcher path, workbook
  token, path, header, or sample content in tracked files or ordinary logs.

- With the optional OCR component prepared, copy a Snipping Tool bitmap and
  choose **Extract text**. Verify the UI stays responsive, useful text appears
  in Input / Output, the original image remains on the clipboard, and Undo
  restores the prior workspace. Repeat with one exact selected image path, the
  file-picker fallback, non-empty and concurrently edited workspace text, a
  no-text image, an oversized image, accented Latin text, and networking
  disabled. On a copy without the component, verify the command explains local
  setup and leaves Input / Output unchanged. Also verify the app still starts
  and ordinary Find, Configure, Quick actions, and Work Items remain usable.

- Run the real Windows keyboard path with
  `$env:CONTEXT_PALETTE_PHYSICAL_KEY_TEST='1'; .\python-context-palette.bat -m unittest tests.test_physical_keyboard_shortcuts`.
  This briefly focuses a Tk test field and uses Windows `SendInput`; it verifies
  Shift plus physical top-row 1–9 through the active keyboard layout and
  confirms Ctrl+numpad 1 does not execute a slot.

- Open a reviewed HTTP/HTTPS URL.
- Open an existing file and folder using normal paths, `%20`-encoded paths, and
  `file:` URIs. Confirm an HTTP/HTTPS URL containing `%20` stays encoded.
- Launch an explicitly configured executable with fixed arguments and test a
  `%20`-encoded executable or working-folder path when this behavior changes.
- Exercise `integrations\Invoke-ContextPalette.ps1` with valid and unknown
  contexts when testing the optional Power Automate bridge.
- For AI-boundary changes, verify a response above 1,000,000 characters is
  rejected without replacing the existing response field.


## Final repository checks

```powershell
git diff --check
git status --short
```

Confirm that no personal/runtime files are staged. Automated checks do not replace a privacy review of tracked JSON examples.
