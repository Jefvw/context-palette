# Context configuration

A Context groups Actions and Work Items for a kind of work. The transient
Context selector in the main **Filter** menu controls both visible membership
and the active shortcut bank in slots 6–0. **All contexts** uses General's bank;
a specific Context uses its own.

## Recommended: Configure window

Open the main **Filter** menu and choose **Manage contexts…** to go directly to
**Contexts**, or choose **Configure** (or press `Ctrl+,`) and select
**Contexts**. Create, edit, or delete a Context, choose every Action and Work
Item that belongs to it, and select up to five preferred items for slots 6–0.
The form uses names instead of technical IDs.

The fixed first row, **General — All items**, is different. Its membership is
computed from every Active Action and available Work Item, so it has no member
editor and cannot be renamed or deleted. Choose **Edit shortcuts…** to set only
its preferred slots 6–0. Those preferences stay in `data/palette.json` on this
computer. Clearing all five positions removes the override and restores
automatic General ordering.

Normal user contexts belong in **My configuration** and stay on this PC. They
may contain Built-in Actions, My configuration Actions, and personal Work Items
without editing the Actions or external folders themselves. **Built-in** is developer-owned starter configuration
tracked through Git. General is implicit, and **Developing Context Palette** is
the only shipped specific context.

Deletion clears that Context's slot configuration and any legacy Action-side
metadata before removing the definition. It also normalizes compatibility-only
legacy focus data when necessary. Removing a Context assignment never deletes
its Actions, Work Item folders, or workbooks.

## Advanced JSON files

- `data/contexts.json`: Built-in starter contexts tracked through Git.
- `data/local_contexts.json`: personal or work-specific contexts, ignored by Git.
- `data/actions.json`: Built-in starter actions.
- `data/local_actions.json`: personal or machine-specific actions, ignored by Git.
- `data/palette.json`: explicit per-Context slot overrides, including optional
  General preferences, plus legacy focus and pin data retained only for
  compatible round-trip.

Do not put internal URLs, customer names, work paths, or personal identifiers
in Built-in files.

```json
{
  "name": "Database",
  "description": "Prepare and reuse SQL query text.",
  "action_ids": [
    "database-select-template",
    "database-lines-to-sql-list",
    "my-local-query"
  ],
  "preferred_action_ids": [
    "database-select-template",
    "database-lines-to-sql-list"
  ]
}
```

`name` is the stable, case-insensitively unique context identity. `action_ids`
is the ordered Action membership list used by Context-filtered retrieval.
`preferred_action_ids` supplies up to five default actions for slots 6–0 and
should be a subset of `action_ids`. Explicit per-machine slots in
`palette.json` override those defaults.

My configuration Contexts may additionally store `work_item_refs`, identified
by stable source ID and direct relative folder, plus an ordered typed
`preferred_items` list when slots mix Actions and Work Items. Unavailable Work
Items remain configured. Built-in Contexts cannot contain Work Items.

Every action belongs to the virtual **General** root. Current context membership
belongs in the context's `action_ids`, allowing each PC to organize Built-in
actions without changing Git-tracked action records. Legacy action records may
still carry a `contexts` list. At startup, compatible legacy memberships are
united into context definitions once; all screens then read only the canonical
definitions. New and edited actions write their context choices back to those
definitions and do not persist a second membership copy. A personal action
cannot be assigned to a Built-in context because that would put a private ID
in a Git-tracked file; use a My configuration context instead. Tags remain
independent discovery terms. Context and tag filters apply to All items,
Actions, and Work Items; Action type and Work Item project filters remain
kind-specific. Only the Context filter chooses the 6–0 bank; Find, tag, type,
and project merely narrow results. The Context filter is session-only UI state:
it adds no persisted field and requires no data migration. Any legacy
`focus_context` value remains compatibility data rather than current UI state.

Do not create a General Context definition; it is implied for every Action and
discovered Work Item, and the guided editor reserves that name. A legacy or
manually authored General definition cannot narrow the virtual root or seed its
slots.
Existing personal files using singular `context`, `technology`, and `task`
remain readable.

## Useful patterns

| Need | Action type |
| --- | --- |
| Reusable snippet | `copy_text` |
| Date, time, or clipboard template | `copy_text` with supported variables |
| Build, copy, and open a URL from selected text | `build_url_selection_open` |
| Prompt for an ID, then build, copy, and open a URL | `build_url_open` |
| Turn lines into query values | `transform_list_csv` |
| Reusable editable form | `workspace_template` |
| Open a reviewed target | `open_url`, `open_file`, `open_folder`, `launch_app` |

See [Action types](ACTION_TYPES.md) for fields and examples.

## External edits

Keep action IDs and context names unique across Built-in and My configuration
files, then run:

```powershell
.\check-context-palette.bat
```

Return to or reopen the palette after editing. It reloads files whose signatures
changed; a restart is normally unnecessary.

Protected credential paste can temporarily replace plain-text clipboard content
and conditionally restore the previous plain text. General multi-format
clipboard transactions, sequence paste/Tab/Enter steps, context activation
bundles, and automatic context inference are not implemented.
