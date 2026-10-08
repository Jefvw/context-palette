# Python Excel handover: replace the previous recovery backup

Prepared: 2026-10-04. Status: requested engine work, not implemented or enabled
by this document.

Update 2026-10-05: the blank-preserving write and recovery-package validation
are now published in Python Excel `c081510` (write fix in `be4f67f`). Preserve
that committed baseline. References below to uncommitted work describe the
original handover snapshot; verify current state before making the still-pending
backup replacement extension. Palette's startup testing gate is now retired.

The Context Palette product owner chose **Replace previous** for the live
scientific-notation/text conversion workflow: select the open workbook,
worksheet and physical columns, click **Convert**, and retain one stable
sibling recovery workbook containing the state immediately before that
conversion. Refresh that same recovery workbook on the next explicitly
authorized conversion. Detailed human **Review** is optional; zero-write
engine planning and exact fingerprint validation remain required.

Update 2026-10-06: the owner waived backup only for the newly requested native
[Text to Columns mode](EXCEL_TEXT_TO_COLUMNS_ENGINE_HANDOVER.md). The existing
checked converter remains unchanged; this recovery-replacement brief applies
to that older workflow, not the new no-backup operation.

## Implementation brief for the Python Excel owner

Implement the smallest public engine-contract extension that supports this
single-backup policy safely. Work in `D:\dev\python-excel`; inspect that
repository's instructions, architecture, current changes and tests first.
Context Palette remains the host and owns selection, buttons, acknowledgement,
asynchronous orchestration and result presentation. Do not implement host UI
in the engine repository or copy workbook/recovery behavior into Context
Palette. Do not commit, push or publish without separate authorization.

Read these engine documents first:

- `docs/CONTEXT_PALETTE_INTEGRATION.md`
- `docs/LIVE_COLUMN_CONVERSION_CONTRACT.md`
- `docs/INTERFACES.md`
- `docs/STATUS.md`

The main current ownership points are
`src/python_excel/operations/live_conversion_plan.py`,
`src/python_excel/operations/live_conversion.py`,
`src/python_excel/excel_automation/xlwings_gateway.py`,
`src/python_excel/cli/machine.py`, capability discovery, and
`src/python_excel/xlsx_validation.py`. Use the existing public process client
and operation contracts; keep schema `1.0` envelopes where compatible.

## Current contract and work that must be preserved

`inventory_live_excel`, `plan_live_column_conversion` and
`convert_live_column_representation` currently expose operation version `1.0`.
The planner defaults recovery to
`<source-stem>.python-excel-recovery.xlsx`, rejects every existing recovery
path with `conflict.recovery_output_exists`, and reports
`recovery.will_overwrite=false`. Execution independently refuses collisions.
Its staged recovery copy is validated before no-clobber publication. The
strict request parser has no recovery replacement option. Version `1.0`
therefore cannot refresh a fixed backup through its public API.

Preserve the version `1.0` create-only behavior and its callers. Preserve the
clean, saved, writable `.xlsx` requirement, known-disabled AutoSave, protection
checks, complete bounded scan, text-only target, physical column identity,
formula/unsupported-value blockers and precision-risk acknowledgement. A
successful conversion leaves the source open, dirty and unsaved. A subsequent
conversion remains blocked until the user explicitly saves their workbook;
this request does not authorize a dirty-input mode or automatic saving.

The corrected write boundary is presently an uncommitted engine change at
HEAD `08af313`: `selected_range.api.Value2 = output` in `xlwings_gateway.py`.
It preserves true blanks and must remain. Preserve unrelated existing changes,
including the recovery package validator and its tests. Do not reset the
working tree, replace the fix from HEAD, or treat the existing engine UAT as
evidence for the new replacement behavior. A deployable corrected engine
commit containing the required fix and prerequisites is required before
Context Palette can rely on it through Git; record its exact revision.

## Required recovery behavior

For each explicit conversion, the stable sibling backup must contain that
conversion's current pre-mutation workbook state, even when a previous backup
already exists. Keep exactly one published recovery workbook at the chosen
stable path; temporary staging is an implementation detail, not another
retained historical backup.

1. Resolve the exact live workbook token, worksheet, physical columns and
   bounded data scope. Validate the current source and recovery destination
   against the requested policy and expected plan fingerprint.
2. If a previous recovery file exists, retain it unchanged while preparing
   the replacement. Determine whether it is a replaceable prior recovery
   file for this source; define the exact eligibility boundary. Existing `1.0`
   backups have no ownership marker, so support bounded legacy adoption under
   an explicit replacement policy for the exact source, stable sibling path
   and fingerprinted prior file. Do not add a general provenance registry or
   a recurring human Review gate. Filename/package validity alone does not prove
   ownership: the explicit policy authorizes that particular replacement.
   Refuse unrequested collisions, directories, links or unsupported states with
   a stable code. State clearly how legacy files become eligible.
3. Use Excel `SaveCopyAs` to a unique staging file in the same sibling
   directory. Validate the fresh copy with the existing non-mutating package
   validator, including every ZIP member, duplicate-member rejection, XML and
   relationships. The original source must remain attached and clean.
4. Revalidate both the source scope/state and the planned prior backup state
   after staging and immediately before publication. Changed values,
   identity, backup content, disappearance or an unexpected new file must
   invalidate the authority and produce a conflict before cell writes.
5. Publish the verified fresh copy atomically at the stable path. When a
   previous copy exists, replace it only under the exact explicit policy and
   fingerprinted authority. Do not delete, truncate or move the old copy away
   before a validated replacement is ready. A create disposition must still
   refuse an unexpected destination; a replace disposition must still refuse
   changed or missing prior state.
6. Verify and report publication of the fresh recovery copy, revalidate the
   live source immediately before the first range mutation, then perform the
   existing bounded conversion. Continue to use direct COM bulk `Value2`
   assignments so scattered blanks and wholly blank columns remain true
   blanks.

Any failed staging, validation, destination check, lock/open-file check or
replacement/publication step must abort before cell changes. When replacement
has not completed, the previous valid copy remains available. If publication
completed but later source revalidation fails, report the fresh published copy
and a failed conversion with zero live mutation; do not restore or delete it
silently. Never claim the backup remains unchanged when publication is
uncertain.

Serialize competing engine invocations for the same source/recovery target.
Handle a recovery workbook open in Excel, Windows sharing violations and
external file changes as conflicts or known backup failures; do not close
other workbooks, dismiss prompts, terminate applications or force unlocks.
Document the actual Windows filesystem guarantees and any remaining external
check-to-replace limitation. Do not claim that an atomic publication alone
also makes a prior identity check atomic. Enforce serialization between engine
invocations and reject observed external changes; distinguish those guarantees
from races with unrelated non-cooperating writers. Do not promise filesystem
compare-and-swap that the chosen API cannot provide. If ordinary staging,
validated replacement or old-copy preservation on a known publication failure
cannot be verified, stop before enabling that boundary. Keep unsupported filesystems
explicit rather than broadening this into a general backup manager.

## Versioned public authority and receipts

Choose and advertise a strict compatible versioning path. A new advertised
plan/execute operation version, for example `2.0`, is a reasonable option;
the engine owner should select the exact version and names. Do not change the
meaning of version `1.0`, send undeclared fields to its strict parser, or
advertise replacement before it is implemented and verified.

The new contract must distinguish create-only from explicit
replace-previous policy in both planning and execution. One possible field is
`recovery_policy: "replace_previous"`; this is a proposal, not a released
field. Context Palette will opt into the exact discovered version and policy
only after a separate host integration update.

The zero-write plan must return the exact stable recovery path, `create` or
`replace` disposition, and enough non-content metadata to identify the prior
copy and its replacement eligibility. Fingerprint the policy, destination,
prior existence/identity/content and ownership evidence together with the
existing source identity/state, worksheet, scope, classifications and values.
Changing any of those inputs must make execution stale, even if aggregate
cell counts stay equal. A plan creates no staging or recovery file and reports
zero writes. It is not a lock or replacement authority by itself.

Execution must repeat the explicit replacement policy and exact invocation,
plus `expected_plan_fingerprint`. A fingerprint alone must not imply consent
to replace an existing file. The host's visible **Replace previous backup**
policy and explicit Convert action supply that consent; do not require a new
full human-review dialog for each ordinary ready plan. Report the exact backup
path, create/replace outcome, verification/publication state and any backup
failure stage so the host can explain filesystem effects separately from
live-cell mutation.

Keep authoritative execution `result.state` values `succeeded`, `failed` and
`partial_failure` where compatible, with truthful `mutation_started`,
completed columns/counts, dirty state and lifecycle flags. A successful outer
JSON envelope does not mean conversion succeeded. A conservative
`partial_failure` can have `mutation_started=true` with a clean workbook flag
when an attempted COM assignment failed before an observable edit; retain
that distinction. If a source-state read or publication result is unknown,
expose uncertainty rather than inventing a zero-effect receipt.

After any partial mutation or unknown process/protocol/publication outcome,
the host and engine must not retry automatically, replace the backup again,
or roll back by reopening/saving workbooks. Preserve the available recovery
evidence and let the user inspect Excel and the backup. Once mutation starts,
the fresh verified pre-mutation copy is the recovery reference. Return it even
when only some columns complete. Never save or close the source, start a new
Excel instance, or claim Excel Undo guarantees recovery; automation may affect
Undo history.

## Context Palette work already in progress

The host is implementing optional detailed **Review** and a primary
**Convert** action: freeze the exact selection, obtain a zero-write plan in
the background, correlate its target/path/bounds, then execute its exact
fingerprint if ready. Reported precision risk remains an exception requiring
visible explicit acknowledgement before execution. Selection or path changes
invalidate the prior plan and acknowledgement.

Until a tested replacement version is available, this flow continues using
version `1.0` and respects `conflict.recovery_output_exists`. Context Palette
does not delete, rename, rotate or overwrite the previous backup, and does not
choose an unreviewed alternate recovery path to bypass that collision. It
continues to reuse its generic Python Excel client and workbook, worksheet
and physical-column selectors.

## Verification and completion

Add focused fake-based engine tests first. Normal automated suites must not
launch Excel. Cover at least:

- unchanged `1.0` collision refusal and strict parsing; exact new-version
  capability discovery and explicit replacement-policy validation;
- first-time creation and authorized replacement of the owned prior backup;
  one final published backup and no retained staging artifact on known
  successful completion;
- source and prior-backup fingerprints, altered scope with equal counts,
  changed/deleted/new/unrelated destination, competing invocations and stale
  replacement authority;
- `SaveCopyAs`, package validation, open-file/lock and atomic publication
  failures: zero range-format/value effects and old-copy preservation when
  replacement has not completed;
- successful publication followed by stale source state, failure before the
  first observable COM edit, later-column partial failure and truthful
  backup/live-effect receipts;
- unknown outcome ownership without automatic retry or cleanup of a possibly
  valid published backup; no source save/close or application creation;
- direct COM `Value2` regression coverage for scattered and wholly blank
  selected columns, unchanged headers/unselected cells, exact text outputs
  and mandatory precision acknowledgement.

Run the focused tests, complete Python Excel suite, lint/compile/dependency
checks required by that repository, and `git diff --check`. Record commands,
actual counts and failures. The existing recorded 436-test pass is a baseline,
not the result for this change.

After implementation, perform a separately scoped attended disposable
real-Excel UAT. Create a fresh source, stable backup path and evidence
directory; do not reuse the prior Python Excel or Context Palette evidence
workbooks/recovery paths. Prepare the fixture and test plan first, then obtain
owner agreement on the exact disposable paths, reads and writes before live
engine access; earlier UAT permission is not blanket authorization. Prove initial creation and a later authorized
replacement with different pre-conversion values. An operator may deliberately
save the disposable fixture between independent conversions to satisfy the
unchanged clean-input precondition; record that fixture preparation separately
from engine calls. Prove for each engine call that source disk bytes remain
unchanged and the source remains open, dirty and unsaved afterward. Check
recovery contents against that invocation's current pre-mutation state,
direct COM `Value2=None` plus Excel `ISBLANK=true` for all original blanks,
exact bounded ranges, headers/unselected cells and process ownership.

Exercise backup replacement refusal while the prior backup is locked/open in
that disposable session, then verify zero live effects and preservation of the
prior valid copy. Do not use a real user workbook, automatic source saves,
prompt dismissal, process termination or the existing engine evidence
session. Record any filesystem/race behavior that remains unverified rather
than declaring it passed.

Update the engine-owned integration/contract/interface/status documentation
with the exact chosen versions, request fields, fingerprints, ownership rules,
stable error codes and receipt semantics. Return the files changed, automated
verification, separately recorded UAT outcome, remaining limits, and exact
deployable engine revision. Supply copy-ready process JSON and the capability
selection rule for a later focused Context Palette integration. Do not claim
the host supports replacement before that separate integration is tested.

## Model recommendation

Recommended model: **GPT-6.1 Sol (`gpt-6.1-sol`)**.
Reasoning effort: **high**. This is the currently available equivalent of the
repository's stronger-model role for data-integrity work: COM state and atomic
backup publication interact, and plausible mistakes can survive ordinary
fakes. Upgrade to the strongest available model or higher reasoning if the
Windows file/COM boundary, conflict guarantees or effect-state ownership remain
unresolved. This recommendation does not change any active chat's model or
dispatch the handover.
