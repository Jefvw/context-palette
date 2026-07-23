# Context configuration

A Focus context groups actions for a kind of work and gives slots 6–9 a
predictable set of preferred actions while search remains global.

## Recommended: Configure window

Choose **Manage focuses…** in the Focus selector to open **Contexts** directly,
or choose **Configure** (or press `Ctrl+,`) and select **Contexts**. Create,
edit, or delete a context, choose every action that belongs to it, and select up
to four preferred actions. The form uses action names instead of technical IDs.

Normal user contexts belong in **My configuration** and stay on this PC. They
may contain both Built-in actions and My configuration actions without editing
the actions themselves. **Built-in** is developer-owned starter configuration
tracked through Git. General is implicit, and **Developing Context Palette** is
the only shipped specific context.

Deletion clears saved Focus state and legacy action-side memberships before
removing the definition.

## Advanced JSON files

- `data/contexts.json`: Built-in starter contexts tracked through Git.
- `data/local_contexts.json`: personal or work-specific contexts, ignored by Git.
- `data/actions.json`: Built-in starter actions.
- `data/local_actions.json`: personal or machine-specific actions, ignored by Git.
- `data/palette.json`: per-machine Focus, pins, and explicit slot overrides.

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
is the ordered membership list used by **Focus actions**.
`preferred_action_ids` supplies up to four default actions for slots 6–9 and
should be a subset of `action_ids`. Explicit per-machine slots in
`palette.json` override those defaults.

Every action belongs to the virtual **General** root. Current context membership
belongs in the context's `action_ids`, allowing each PC to organize Built-in
actions without changing Git-tracked action records. Legacy action records may
still carry a `contexts` list and remain readable. Tags remain independent
discovery terms. Search remains global regardless of Focus.

Do not create a General context definition; it is implied for every action.
Existing personal files using singular `context`, `technology`, and `task`
remain readable.

## Useful patterns

| Need | Action type |
| --- | --- |
| Reusable snippet | `copy_text` |
| Date, time, or clipboard template | `copy_text` with supported variables |
| Build a URL from selected text | `build_url_selection_open` |
| Prompt for an ID and copy/open a URL | `build_url_copy`, `build_url_open` |
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

Direct paste/key sequences, clipboard transactions, context activation bundles,
and automatic context inference are not implemented.
