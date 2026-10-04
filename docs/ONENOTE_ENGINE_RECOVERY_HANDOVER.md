# Python OneNote owner handover: notebook reselection after reopening

Prepared 2026-09-19. Copy the prompt below into the Python OneNote owner chat.
This handover authorizes no live reads by itself and dispatches no work.

## Handover prompt

You are the Product Owner and integration lead for Python OneNote.

Repositories:
- Your implementation repository: `D:\dev\python-onenote`.
- Read-only integration reference: `D:\dev\context-palette`.

Goal: unblock Context Palette's **Choose notebook → Search → Preview → Use text**
flow after a notebook is closed and reopened. Implement the smallest safe engine
fix for the reproduced notebook-inventory failure. Preserve all existing work.
Do not edit Context Palette, commit, push, publish, add dependencies, or change
OneNote content/settings.

### Read and inspect first

Read your AGENTS.md, relevant architecture/testing guidance, and:
- `docs/CONTEXT_PALETTE_INTEGRATION.md`
- `docs/INTERFACES.md`
- `docs/CONTEXT_PALETTE_PRODUCT_OWNER_HANDOVER.md`
- `docs/STATUS.md`
- Context Palette's `docs/TESTING.md`, especially the 2026-09-19 recovery and
  reopened-notebook follow-up sections.

Inspect branch/HEAD, status, existing diff and untracked files before editing.
Both repositories contain valuable overlapping uncommitted work. Preserve it.

### Confirmed evidence

1. The owner reopened the disposable notebook, but search with the saved exact
   notebook identity still failed. Describe and the active desktop probe succeeded;
   scoped search returned `internal.desktop_bridge`, category `internal_error`,
   exit 70. This broad error does not itself prove a closed notebook.
2. A separate authorized root **notebook-metadata-only** inventory returned
   `input.unsupported_onenote_xml_element`, exit 3. It returned no usable notebook
   list, so Context Palette cannot complete explicit reselection.
3. A temporary diagnostic around the unchanged engine parser inspected only schema
   element names and identity-match booleans. It observed xs2013 `Notebooks`,
   `Notebook`, and `UnfiledNotes`. There was one Notebook matching the agreed
   disposable title, and its ID differed from the saved ID. That comparison was
   diagnostic only: no title-based remapping or settings update occurred. The
   diagnostic did not retain raw XML, attributes, names, IDs, paths, or content.
4. The current parser in `src/python_onenote/core/onenote_xml.py` accepts only
   `Notebooks`, `Notebook`, `SectionGroup`, `Section`, and `Page`. `_parse_xml_root`
   rejects other elements before identities can be extracted. Inventory traversal
   also assumes every non-Notebooks element maps to a TargetKind; simply adding
   UnfiledNotes to a validation allowlist is insufficient.

These observations establish stale saved identity and an inventory parser blocker.
They do not establish that notebook IDs always change on reopening or that every
bridge error has this cause. UnfiledNotes attributes/children were not captured;
verify its valid schema structure before choosing treatment.

### Required behavior

- Recognize the specific legitimate xs2013 UnfiledNotes structure in its valid
  location. Decide its safe handling from schema and bounded synthetic fixtures.
- Root inventory with `scope: notebooks` must return actual Notebook identities
  without treating UnfiledNotes as a notebook, fabricating IDs, attaching its
  descendants to an unrelated notebook, or widening the requested scope.
- Preserve namespace, DTD/entity prohibition, byte/item/depth bounds, exact anchor
  identity, parent relationships, paging/count consistency and unknown-element
  rejection. Account for shared parser use by search as well as inventory.
- Preserve schema/operation version 1.0, exact acknowledgements, active-probe and
  session guards, process ownership, cancellation and privacy. Do not make reads
  run on host window opening or typing.
- Keep notebook selection explicit. A stale ID must never trigger root search,
  title-based rebinding or automatic selection. Context Palette owns preferences.
- Keep the fix focused on inventory compatibility. A precise stale-target error
  mapping may be proposed separately, but do not guess a COM HRESULT or label all
  internal bridge failures as target.not_found.

### Verification and acceptance

Add synthetic regressions before any live test. Cover a notebook list containing
valid UnfiledNotes metadata; exact notebook IDs and correct totals; relevant
metadata children and invalid placement; unknown/foreign-namespace elements;
existing XML limits and unsafe constructs; scoped inventory/search identities;
and valid machine-protocol responses. No fixture may contain personal metadata.

Use the repository's environment and required full gate: pytest, Ruff, compileall,
pip check, real subprocess protocol tests, and `git diff --check`. Run focused tests
while editing, then the complete gate once after final code changes. Update current
integration/status/testing documentation. The engine's recorded 561-test gate is
historical evidence; it does not verify this fix. Host's latest gate passed 1,580
tests with 2 skipped, but likewise does not verify a future engine change.

After synthetic checks pass, obtain explicit agreement on the exact disposable
notebook/section/page, harmless query, and permission for notebook metadata before
new live reads. Earlier UAT is not blanket permission. Use OneNote already running.
The owner must explicitly reselect the reopened notebook in Context Palette, then
run the agreed scoped Search, Preview and placement flow. Do not change private
host settings directly. Keep relocated-path bootstrap/live reads separately scoped.

Report the actual diff, automated results, live observations and unperformed checks.
State whether explicit notebook reselection now works and what remains blocked.
Do not call the overall integration accepted merely because parser tests pass.

## Model recommendation

GPT-5.6 Sol, high reasoning: this is a narrow change at a strict XML and identity
boundary, where an overly permissive fix could silently widen scope. Retain one
writer and use an independent read-only review of parsing and boundary tests.
