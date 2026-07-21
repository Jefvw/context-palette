# Work Items discovery plan

Status: **Approved — Phases 1–4 implemented; Phase 5 not implemented**

This document records the agreed product design and implementation plan for
finding local work-item folders and their matching Excel starting files.
Current behavior remains defined by [MVP](MVP.md) and
[Architecture](ARCHITECTURE.md).

## Goal

Let the user quickly find a work item, open its exact matching `.xlsx`
starting file when present, or open its folder otherwise. Work items must be
searchable by structured name metadata, automatically detected project codes,
and personal tags without turning every folder into a persisted action.

## Confirmed decisions

- Work-item locations are configured explicitly because paths differ between
  computers.
- Each source points to a `workitems` folder and has a stable local source ID
  and user-facing name.
- Visual marker folders are omitted completely from results.
- A visual marker is recognized by a name ending in at least five hyphens.
- Discovery inspects only direct, non-marker children of `workitems`.
- Marker folders and everything beneath them are skipped completely. There is
  no recursion and `details` folders are never inspected.
- A work item may have no project code or multiple project codes.
- Project codes are detected automatically rather than assigned manually. A
  project-code token is exactly four characters and its third character is
  `9` (conceptually `..9.`).
- Project codes remain searchable and filterable as structured metadata but do
  not populate the ordinary personal-tag checklist.
- Only an exact, case-insensitive `<folder-name>.xlsx` match directly inside
  the work-item folder is considered its starting workbook.
- Run opens the matching workbook by default. If no exact match exists, Run
  opens the work-item folder.
- Other Excel files are never selected as substitutes.
- Personal tags and source configuration stay in ignored local Context Palette
  files; work-item folders are not modified.

## Name model

A conventional work-item name is parsed as:

```text
ISS-CAP40-age-verification
│   │     └─ subject
│   └─────── organisational unit
└─────────── work-item kind
```

Known kind codes:

| Code | Meaning |
| --- | --- |
| `CAS` | Case |
| `ISS` | Issue |
| `TRCK` | Track |
| `QST` | Question |
| `PRJ` | Project |

Unknown codes remain visible and searchable. Parsing failure must not hide an
otherwise valid work-item folder.

Project codes are independent of the organisational unit. For example, a
CAP40 work item may contain zero, one, or several four-character project-code
tokens whose third character is `9`.

## Discovery model

Configured source:

```json
{
  "id": "cap40-product",
  "name": "CAP40 Product",
  "workitems_path": "D:\\work\\cap40-product\\workitems"
}
```

Supported layouts:

```text
workitems/
├── ISS-CAP40-age-verification/      indexed direct work item
└── ISS-CAP40----------------/       marker and contents skipped
    └── ISS-CAP40-other-issue/       not scanned
```

The scanner must:

1. Validate the configured source without creating or changing folders.
2. Enumerate only direct children.
3. Skip every marker folder without enumerating its contents.
4. Never perform recursive traversal.
5. Ignore all nested folders, including `details`.
6. Detect only an exact, case-insensitive `.xlsx` filename match.
7. Continue using the last successful in-memory index when a source becomes
   temporarily unavailable.

Only direct non-marker folders are eligible work items.

## Runtime model

A discovered work item is a transient indexed resource, not an entry in
`actions.json`.

Proposed fields:

```text
source_id
source_name
relative_folder
folder_path
display_name
kind_code
kind_name
organisation
subject
project_codes[]
personal_tags[]
matching_workbook_path?
```

Automatic search terms include the original folder name, parsed kind,
organisation, subject, source name, and project codes. Subject words remain
searchable but do not automatically become personal tags.

## Main-window layout

The main window keeps its current dimensions and Input / Output area.

```text
┌──────────────────────────────────────┬───────────────────────────────┐
│ ACTIONS                              │ QUICK ACTIONS                 │
│ Find action                          │                               │
│ [ issue CAP40 verification       ]   │ Frequent passwords            │
│                              [Work]  │                               │
│                              [Pass]  │                               │
│ Work items                   [Types] │                               │
│                              [Tags]  │                               │
│ Issue                        [Open]  │                               │
│  Issue → CAP40 age verification [?] │                               │
│  Issue → CAP40 other issue          │                               │
│                                      │                               │
│ Track                                │                               │
│  Track → CAP40 business rules       │                               │
├──────────────────────────────────────┴───────────────────────────────┤
│ Input / Output                                                       │
├──────────────────────────────────────────────────────────────────────┤
│ Opens matching workbook · Shift+Enter opens folder                  │
└──────────────────────────────────────────────────────────────────────┘
```

Proposed behavior:

- A compact **Work items** control activates the source without enlarging the
  main window.
- Empty Find may group results by parsed kind. Visual marker folders never
  appear as headings or rows.
- Non-empty Find shows a flat matching list.
- The existing Tags filter applies personal tags.
- Project codes have a structured filter group and remain searchable directly.
- One row represents one work item; workbook and folder are not duplicate rows.
- Enter, double-click, or **Open** uses the exact workbook, then folder fallback.
- `Shift+Enter` always opens the work-item folder.
- The context menu offers **Open workbook** when available, **Open work-item
  folder**, **Open source folder**, and **Edit tags**.

Preview and tooltip:

```text
ISS-CAP40-age-verification
Issue · CAP40 · CAP40 Product
Project codes: AB9C, XY9Z
Tags: urgent, waiting
Workbook: ISS-CAP40-age-verification.xlsx
Default: Open workbook
```

## Configuration layout

Add a proposed **Work Items** tab to Configure:

```text
┌──────────────────────────────────────────────────────────────────┐
│ Actions | Types | Contexts | Buttons | Work Items                │
├──────────────────────────────────────────────────────────────────┤
│ Name             Workitems folder                         State  │
│ CAP40 Product    D:\work\cap40-product\workitems          Ready  │
│ CAP49 PDQ        C:\projects\cap49-pdq\workitems          Ready  │
│ CAP67 PRS        E:\projects\cap67-prs\workitems          Missing│
│                                                                  │
│ [Add source] [Edit] [Remove] [Refresh index]                     │
├──────────────────────────────────────────────────────────────────┤
│ 47 work items · 35 matching workbooks · 12 folder fallbacks     │
└──────────────────────────────────────────────────────────────────┘
```

Source editor:

```text
Source name       [ CAP40 Product                         ]
Workitems folder  [ D:\work\cap40-product\workitems ] [Browse…]
Stable source ID  [ cap40-product                        ]

[Save source] [Cancel]
```

Work-item metadata editor:

```text
ISS-CAP40-age-verification
Issue · CAP40 · CAP40 Product

Detected project codes (read-only)
AB9C, XY9Z

Personal tags
[ urgent, waiting                              ] [Choose…]

[Save] [Open folder] [Cancel]
```

## Local storage and privacy

Proposed ignored files:

```text
data/local_work_item_sources.json
data/local_work_item_metadata.json
```

Metadata should use a stable source ID plus relative folder path, never the
absolute path as its identity:

```json
{
  "work_items": {
    "cap40-product/ISS-CAP40-age-verification": {
      "tags": ["urgent", "waiting"]
    }
  }
}
```

No work-item name, path, project code, tag, or cached index belongs in tracked
examples without explicit privacy review. The first version should keep its
index in memory rather than persist a cache containing work information.

## Refresh and failure behavior

- Build the index at startup without blocking the main window.
- Refresh when Work Items is opened and the index is stale.
- Support explicit refresh from Configure and the proposed Work Items menu.
  `F5` remains reserved for resetting the main palette to its startup view.
- Never rescan after each Find keystroke.
- Keep successful results from other sources when one source is unavailable.
- Preserve the last successful index for a temporarily unavailable source
  during the current process.
- Show clear states for no sources, no results, missing source, and missing
  exact workbook.
- Do not open or inspect workbook contents while indexing.

## Implementation plan

### Phase 1 — Pure discovery domain — Implemented

- Define immutable source and discovered-work-item models.
- Validate ignored source configuration.
- Implement direct-child enumeration with complete marker-subtree omission.
- Parse kind, organisation, subject, and zero-or-more project codes.
- Detect the exact `.xlsx` match and folder fallback.
- Add temporary-directory tests for valid, marker, missing-workbook, multiple
  workbook, unavailable-source, marker-subtree omission, and no-recursion cases.

Implementation: `src/context_palette/work_items.py`, verified by
`tests/test_work_items.py`. This phase has no application UI or persistence.

### Phase 2 — Local persistence and refresh — Implemented

- Add ignored source and metadata formats with atomic writes.
- Add last-known-good in-memory source results.
- Add a background refresh boundary that never mutates Tk off the main thread.
- Measure representative scan time before considering a persistent cache.

Implementation: `src/context_palette/work_item_storage.py` and
`src/context_palette/work_item_refresh.py`, verified by
`tests/test_work_item_storage.py` and `tests/test_work_item_refresh.py`.
The source and metadata files are ignored, writes are atomic, and the index is
memory-only. A 500-folder direct scan measured 21.9 ms on the development
machine on 2026-07-21, so no persistent private cache was added.

### Phase 3 — Discovery interface — Implemented

- Add the compact Work Items filter and mixed result presentation.
- Implement Find, structured project-code filtering, personal-tag filtering,
  preview, tooltip, empty states, and keyboard behavior.
- Add constrained workbook/folder/source-folder opening.
- Preserve existing action search, Focus, slots, and execution behavior.

Implementation: the main discovery workspace exposes a compact Work mode and
reuses Find, the flat result list, Projects/Tags filters, preview/status area,
keyboard execution, tooltips, and a constrained context menu. Refresh uses the
Phase 2 background queue and retains per-source last-known-good results. Source
and tag authoring is supplied by Phase 4.

### Phase 4 — Guided configuration — Implemented

- Add the Work Items Configure tab and source editor.
- Add the personal-tag metadata editor.
- Reuse existing accessible picker behavior where appropriate.
- Add missing/unavailable source feedback and explicit refresh.

Implementation: the **Work Items** Configure tab manages friendly source names,
stable IDs, validated existing `workitems` folders, source removal, explicit
refresh, discovery summaries, and private comma-separated tags. The main result
context menu deep-links to the selected Work Item. All writes use ignored local
storage, and removing a source never changes work files.

### Phase 5 — Verification and documentation

- Add launcher integration and accessibility tests.
- Run performance measurements against representative source sizes.
- Perform manual Windows checks for opening, missing workbooks, unavailable
  drives, keyboard navigation, and different paths on another computer.
- Update Architecture, Help, MVP, configuration reference, Changelog, and
  privacy checks only when implementation exists.

## Acceptance criteria

- Configured sources may use different absolute paths on different computers.
- Marker folders never appear as work items.
- Discovery considers only direct non-marker children and never recurses.
- Every work item appears once.
- Exact matching `.xlsx` opens by default; otherwise its folder opens.
- Unrelated Excel files are never guessed.
- Zero or multiple detected project codes are searchable and filterable.
- Personal tags can be added without modifying work folders.
- Missing sources do not break available sources or existing action behavior.
- Index refresh does not run on every keystroke or block normal resident use.
- Personal work metadata remains ignored by Git.
