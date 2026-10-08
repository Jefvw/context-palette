# Python Excel handover: fast Text to Columns as Text

Prepared 2026-10-06. Historical engine-owner brief; superseded by the observed
2026-10-07 native contract and [host integration](EXCEL_NATIVE_TEXT_TO_COLUMNS.md).
The engine feature remains uncommitted at c081510; host UAT is still pending. Python Excel remains
read-only in this Context Palette task. This brief authorizes no live workbook
operation, commit or push.

## Owner decisions

- Match the manual Excel **Data → Text to Columns → Text → Finish** use case.
- No recovery backup for this new native operation; the owner explicitly
  accepts that risk. Do not add a recurring backup acknowledgement or Review gate.
- Keep Context Palette multi-column selection. Excel processes each selected
  physical column separately within one attended request.
- Keep the existing checked convert_live_column_representation workflow
  available and unchanged, including its current row bound and recovery policy.
  Do not replace or silently reroute the old Action to this new operation.

## Implementation prompt for the Python Excel owner

Work in D:\dev\python-excel; use D:\dev\context-palette only as a read-only host
reference. Read AGENTS, architecture/status and CONTEXT_PALETTE_INTEGRATION.md,
INTERFACES.md and LIVE_COLUMN_CONVERSION_CONTRACT.md. Inspect existing changes.
Preserve the published blank-preserving converter and unrelated work. Do not
edit the host, commit, push, publish or access live Excel without separately
scoped authorization.

Add a small, separately advertised versioned operation for the native Excel
TextToColumns method with each output field treated as Text. The engine owns
final operation names and public JSON schemas. Keep the old 1.0 conversion
contract intact; its mandatory recovery must not be bypassed through a flag.

Execution requirements:

1. Reuse already-open workbook inventory and exact workbook/worksheet identity.
   Accept an explicit ordered list of unique physical columns. Column letters
   must never be inferred from a filtered list of nonblank headers.
2. Execute native TextToColumns once per chosen column, in place, with Text
   parsing and every delimiter disabled. Explicitly specify qualifier behavior
   so quotes, spaces and tabs are not silently stripped. Use explicit Text field
   info for the one input column, no text qualifier and all delimiter flags false;
   never pass a multi-column or bounding-span range for nonadjacent selection.
   Set the destination to the same column's top-left data cell; never spill
   into neighbouring columns. Use the actual used data range, preserving
   the header and cells outside it; include hidden/filtered data rows and define
   empty-column and formatting-inflated UsedRange behavior. Do not scan/rewrite
   a million empty rows. Validate every chosen column for formula, merged and
   protected blockers before the first write; recheck each scope before its call.
3. Keep setup/selection lightweight: enumerate headers/coordinates without the
   old full-value conversion planner. No inherited arbitrary 10,000-row cap.
   Document tested scope, process timeout/cancellation and Excel's actual limits;
   do not promise untested unlimited throughput or change the old converter.
4. No SaveCopyAs, recovery file, source save/close or extra Excel instance. Leave
   the workbook open and modified; the owner chooses when to save. Display one
   short consequence: no backup; Excel Undo may be affected. One explicit host
   Convert click is the attended authority; supplementary review is optional.
5. Recheck target, writable/protection state and readiness before effects. A busy
   Excel must stop with a useful message, not be mistaken for a missing workbook
   or worksheet. Decide and document AutoSave/dirty-workbook policy specifically
   for this no-backup operation instead of silently inheriting incompatible gates.
   Permit the expected dirty state caused by this batch: column two must not be
   rejected merely because column one changed the workbook. Keep one engine batch
   request, with ordered native calls inside it, rather than host retries.
6. Prove blanks, existing text/leading zeros and neighbouring cells are preserved.
   Preserve formulas or reject their scope before any mutation; never silently
   flatten them. For an operation that rejects formulas, bulk HasFormula is NULL
   for a mixed range; reject both True and
   indeterminate formula scope, never test only truthiness or a sample. Do not
   claim lost numeric digits can be reconstructed. Define native scientific-text,
   decimal, date and quote behavior explicitly: it may differ
   from the old canonical Python conversion, so do not reuse its output promises.
7. Report per-column completion and authoritative succeeded/failed/partial or
   unknown states. Stop remaining columns after a failed/uncertain call. Never
   automatically restart the batch or replay a native write after rejection,
   cancellation or timeout; earlier columns may already have changed. Retain
   precise inspection guidance and known target identity without sensitive logs.
   Mark mutation_started before each native invocation and report completed,
   current and pending columns/ranges. No Save invoked is distinct from Excel's
   Saved/dirty flag; neither proves rollback after a failed/uncertain call.
   Per-column receipts are authoritative only in a valid structured response.
   If the engine process dies or its receipt is missing/invalid, the host treats
   every requested column as possibly changed; never infer completed columns.

Host integration after a compatible engine is published:

Add a separate, clearly named **Text to Columns → Text** Action. Reuse workbook,
worksheet and multi-column selectors. Show chosen columns, one short effect
summary and Convert. Keep the old **Convert Excel values to text** Action and
its familiar behavior. Do not add unsupported execution UI before the contract
exists, and do not copy Excel automation logic into Context Palette.

## Verification and acceptance

Synthetic tests first: nonadjacent/multi-column order, wrong/stale identities,
empty and duplicate columns/headers, busy/protected/read-only workbooks,
no-backup/no-save/no-close, interrupted multi-column results and duplicate
callbacks. Protect unchanged old converter behavior. Run focused then complete
engine checks and publish integration/interface examples with exact versions.

Propose fresh attended disposable Excel UAT only after synthetic checks. Compare
with the manual wizard for one column, then a multi-selection such as C/E/G.
Include true blanks, existing text, leading-zero identifiers, numeric and literal
scientific values, quotes/spaces/tabs and formula boundaries. Compare full used
range and adjacent columns, prove Value2/ISBLANK for blanks, and record elapsed
time on representative exports above 10,000 rows. Verify no recovery file and
open/unsaved lifecycle. The owner must agree to exact workbook/ranges/input
before any live operation; risk acceptance is not permission to use real files.

Deliver actual changes/tests, performance measurements and limits, authoritative
failure semantics and a deployable engine revision. Host integration and live
acceptance remain separate work.

## Model and review recommendation

Use an available Sol-class model with high reasoning, following the host's
MODEL_SELECTION.md. Native mutation semantics, no-backup execution and partial
multi-column outcomes require one writer and an independent read-only reviewer.
