# Live Excel formatting with AutoSave

Prepared 2026-10-08. Host implementation uses fake/static verification only.
Python Excel was inspected read-only; live formatting with AutoSave has not been
tested through Context Palette or authorized by this implementation task.

## Contract

Schema and operation version remain `1.0`; operation is
`apply_live_format_profile`. The Action first checks available exact inventory
and format capabilities using the shared asynchronous client. Only the format
record's Boolean `supports.autosave_opt_in=true` permits the new argument.
Missing/false support keeps the legacy block for inventory AutoSave=true.
Missing/invalid explicit launchers still require repair, not sibling fallback.

With support, the selection screen always shows:
**AutoSave may save these changes automatically; Excel Undo may be affected.**
One explicit Apply sends the existing token/scope/worksheet/profile fields plus
`allow_autosave_enabled=true`, including when inventory showed AutoSave off.
This covers state changing before execution. Unsupported engines receive the
original request without the argument. No new checkbox, Review, planner, backup,
dependency, settings format or operation-specific process client was added.

## Results and ownership

Optional result metadata is
`autosave: {enabled_at_execution: true|false|null, opt_in_requested: boolean}`.
Opted-in requests require matching metadata; legacy requests may receive an old
reply without it. False opt-in with execution AutoSave=true is contradictory.
Missing/malformed/mismatched replies and every result-null error after Apply
are unknown. No save/close/rollback fact is invented; inspect before any manual
retry. A verified process-start failure is separate and starts no formatting.

`workbook_saved=false` means the engine did not invoke Save. It does not prove
that Excel left changes unsaved. Results show execution-time AutoSave and
`partially_modified_sheets`; filters on partially modified sheets are legitimate
effects. Partial or uncertain changes may already have persisted automatically,
so closing without saving is never promised to reverse them. No automatic retry,
AutoSave toggle, Save/SaveAs/SaveCopyAs, backup, close or Excel startup is added.
Both text-conversion operations retain their existing AutoSave policies.

## Evidence and next test

Observed engine HEAD: `a2ce7d33ce4f2825ebcf401a9b1cd13d4571e200`; 13 tracked
modifications and no untracked files. Its opt-in is in that working tree, not
established as a pushed/deployable revision. Source/serializer matches the
engine-owned `docs/CONTEXT_PALETTE_INTEGRATION.md` handover. Availability must be
discovered on each PC; operation 1.0 alone does not prove opt-in support.

[Testing](TESTING.md#excel-formatting-with-autosave-2026-10-08) records host fake
checks separately from live evidence. Original 2026-08-25 off-state smoke does
not establish acceptance of this new opt-in.

Before any fresh live test, agree on one new disposable workbook where Excel
reports AutoSave enabled, exact worksheet/scope, and inventory metadata access.
Verify F9 → Action → target → warning → one Apply; execution metadata, formatting,
preserved filters/hidden sheets and no engine Save/close/backup/toggle. Verify
actual persistence without inferring it from engine lifecycle flags. Use
separate approved scope for partial/error cases; do not reuse an engine UAT
session or read an unrelated workbook. Physical scaling and another-PC
deployment remain separate from simulated Tk checks.
