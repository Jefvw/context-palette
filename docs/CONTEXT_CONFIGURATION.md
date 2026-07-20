# Context configuration

A focus context gives slots 6–9 a predictable set of preferred actions while search remains global.

## Recommended: Configure window

Choose **Manage focus → Manage focuses…** to open **Contexts** directly, or
press `Ctrl+,` and select **Contexts**. Create or edit a personal context and
choose up to four actions. The form uses action names instead of IDs and saves
to ignored `data/local_contexts.json`. Shared contexts are visible but
read-only.

## Advanced JSON files

- `data/contexts.json`: reviewed portable contexts.
- `data/local_contexts.json`: personal or work-specific contexts, ignored by Git.
- `data/actions.json`: reviewed portable actions.
- `data/local_actions.json`: personal or machine-specific actions, ignored by Git.
- `data/palette.json`: per-machine focus, pins, and explicit slot overrides.

Do not put internal URLs, customer names, work paths, or personal identifiers in shared files without explicit review.

```json
{
  "name": "Archives",
  "description": "Build an archive URL from selected or copied text.",
  "preferred_action_ids": ["archives-open-selected-item"]
}
```

`name` is the stable, case-insensitively unique context identity. `preferred_action_ids` supplies up to four default actions for slots 6–9. Explicit per-machine slots in `palette.json` override those defaults.

Every action belongs to the virtual **General** root. Actions may also carry a
`contexts` list for one or more specific workspaces and a `tags` list for
independent discovery terms. Search remains global regardless of Focus.

```json
{
  "id": "archives-open-selected-item",
  "title": "Open selected archive item",
  "contexts": ["Archives"],
  "tags": ["browser", "archive lookup"],
  "type": "build_url_selection_open",
  "value": "https://example.test/archive/{selection_url}",
  "state": "Draft"
}
```

Do not store General in `contexts`; it is implied for every action. Existing
personal files using singular `context`, `technology`, and `task` remain
readable. Saving an edited action writes the current `contexts` and `tags`
format.

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

Keep action IDs and context names unique across shared and local files, then run:

```powershell
.\check-context-palette.bat
```

Return to or reopen the palette after editing. It reloads files whose signatures changed; a restart is normally unnecessary.

Direct paste/key sequences, clipboard transactions, context activation bundles, and automatic context inference are not implemented.
