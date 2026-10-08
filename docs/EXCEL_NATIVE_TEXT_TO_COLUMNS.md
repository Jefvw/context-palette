# Native Text to Columns host integration

Prepared 2026-10-07. Host implementation is complete with synthetic verification;
host end-to-end Excel UAT remains separately authorized work. Python Excel was
read-only, and no desktop Excel read or mutation was performed in this task.

## Two distinct Actions

| Action | Meaning | Recovery |
| --- | --- | --- |
| Text to Columns → Text (fast) | Native Excel storage conversion. Literal `1.23E+5` remains `1.23E+5`; numeric `123000` becomes text `123000`; existing `00042` stays text `00042`. Displayed scientific notation may remain unchanged. | No backup; Undo may be affected. |
| Convert Excel values to text | Existing checked conversion, including literal scientific text `1.23E+5` → `123000`, with bounded full-value planning and precision checks. | Existing verified recovery copy, exact plan fingerprint and 10,000-row bound remain unchanged. |

The fast Action is a separate saved Built-in definition. It is offered for Run
only after exact available operation/version metadata is known. Configuration
retains editable existing records even when their engine is unavailable; new
native choices require available metadata. Normal production startup probes
static `describe_capabilities` asynchronously. F9 reads the cached result and
starts no engine process. Engine reselection/workflow closure and configuration
restore refresh the static catalogue. Missing/invalid explicit launchers require
repair and never substitute a sibling. Discovery alone does not read Excel or
authorize mutation. Restart after updating an engine checkout/environment.

The generic definition lives in `data/actions.json`, with its single Standard
quick-menu placement in `data/command_surface.json`. Launcher routing,
configuration choices and pure Preview distinguish this Action from the checked
converter. No personal records or new runtime settings format were introduced.

## Exact contract and shared components

Schema `1.0`, operation `apply_live_text_to_columns_as_text`, operation version
`1.0`. One explicit Convert gesture sends one ordered batch with exactly:
`workbook_token`, `worksheet`, `columns` and `header_row`. Tokens remain opaque.
No planner, recovery path, row limit, representation target or precision
acknowledgement is added to this Action.

The host reuses `PythonExcelProcessClient`, `ExcelAutomationCoordinator`, the
versioned capability/inventory/preflight models, `LiveExcelTargetSelector`, and
the extracted `LiveExcelColumnSelector`. The checked converter keeps its original
list order; native selection tracks click order and preserves it through paging.
Header-only preflight sends `headers_only=true`, with no data-row/sample scan
limits. Its unexamined/truncated rows grant no execution authority. Selected
columns on a loaded page can be converted without fetching unrelated pages.

`ExcelLiveTextToColumnsWindow` reuses the existing live-Excel window scaffolding,
standard result text/unknown views, single-flight polling and attended Return to
Excel. It does not call the inherited checked planning or recovery methods.
The description and **No backup is created; Excel Undo may be affected** remain
visible before Convert. Header/token mismatch or process-start failure before a
mutation request is described as no conversion started.

Machine results use `column_receipts`; the engine's typed Python results use
`receipts`. The host validates target correlation, ordered scope/receipt
partitions, state, ranges and all five false lifecycle flags. `result.state`
governs succeeded/failed/partial_failure/unknown even in a success envelope.
Earlier valid completion/skipped receipts survive structured partial/unknown
results; unknown current ranges require inspection. Preflight failures may have
only a scope prefix; revalidation failures can report a changed or null current
range. Entirely empty selections are valid no-mutation successes.

Missing, malformed, mismatched, process-loss or timeout responses after dispatch
make every requested column possibly changed. No completion or rollback is
inferred from Excel's dirty/Saved flag. Native timeout stops host waiting without
killing or replaying the engine's possible mutation; bounded readers release
handles when the process finishes. Unknown views expose inspection/Return/Close,
not a retry command. The host never saves, closes, reopens or creates a recovery
workbook. Other existing operations retain their previous timeout behavior.

## Engine provenance and evidence

Observed engine HEAD: `c0815104079e8db48a2fc2b98c96f89149746c85`.
Observed working tree: 23 modified tracked files and 5 untracked native contract,
operation and test files. The feature is present in that working tree; it is not
part of the recorded HEAD and is not established as deployable through Git.
Availability is therefore discovered, never assumed from a checkout/version.

Engine-owned contracts inspected read-only:

- `D:\dev\python-excel\docs\LIVE_TEXT_TO_COLUMNS_CONTRACT.md`
- `D:\dev\python-excel\docs\CONTEXT_PALETTE_INTEGRATION.md`
- `D:\dev\python-excel\docs\INTERFACES.md`
- `D:\dev\python-excel\src\python_excel\cli\machine.py` and native gateway/result definitions.

Recorded engine UAT on 2026-10-07: Excel 16.0 build 20430, xlwings 0.36.17,
C/E/G over 20,050 rows, C/G completed and empty E skipped, 361.578 ms. True blanks
retained COM `Value2=None` with sampled `ISBLANK=true`; formulas blocked before
mutation; filters, hidden rows, headers, adjacent cells and source bytes remained
preserved. No recovery/save/close/quit/extra process/retry occurred. This is one
engine-only observation, not a host performance guarantee. The one-column
comparison used the same direct native method, not a human-driven ribbon wizard.
Private engine evidence is at:
`D:\dev\python-excel\.excel-integration-work\native-text-to-columns-uat-20261007-01\verification-attempt-02.json`.

## Remaining host UAT

Do not access live Excel until the owner approves a fresh disposable scope.
Suggested new host workbook (not created or opened yet):
`D:\dev\context-palette\outputs\native-excel-host-uat-20261007\Palette Native Text UAT.xlsx`.

Proposed exact scopes: `Data!C2:C20051`, `E2:E20051`, `G2:G20051`; separate formula
blocker `FormulaBoundary!C2:C3`. Populate numeric/literal scientific values,
leading-zero text and true blanks, with entirely empty E and adjacent markers.
Agree on inventory/open-workbook metadata scope and close unrelated workbooks.
Use F9 → fast Action → workbook/sheet → ordered C/G/E → Convert, then inspect
structured receipts, text types, preserved blanks/header/neighbours and
open-dirty-unsaved/no-backup behavior. Do not reuse the engine's workbook/session
or claim a ribbon comparison was performed. Other Office builds/locales, tables,
dynamic arrays, Undo behavior and another-PC deployment remain outside that test.

Focused/full host verification is recorded in [Testing](TESTING.md#native-excel-text-to-columns-integration-2026-10-07).
