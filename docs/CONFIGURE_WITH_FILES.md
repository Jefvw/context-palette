# Configure Context Palette Through Files (No UI Editing)

This guide explains how to configure Context Palette by editing JSON files directly.

Use this when you want a repeatable, reviewable setup through source control rather than creating or editing items in the app UI.

## 1. Configuration files and ownership

Built-in starter files (tracked in Git):

- `data/contexts.json`: Built-in context definitions.
- `data/actions.json`: Built-in action definitions.
- `data/command_surface.json`: Built-in quick-action surface groups/items.

Local files (ignored by Git):

- `data/local_contexts.json`: personal or machine-specific contexts.
- `data/local_actions.json`: personal/private actions.
- `data/local_command_surface.json`: personal quick-action groups/items.
- `data/palette.json`: per-machine state (focus context, pins, optional explicit slots).

Use Built-in files only for reviewed starter configuration intended to ship
with Context Palette. Use My configuration files for the user's actual
organization, private URLs, local paths, and machine-specific behavior.

## 2. Safe edit cycle

1. Stop Context Palette if it is running.
2. Edit only the relevant JSON files.
3. Run the validation check:

```powershell
.\check-context-palette.bat
```

4. Start Context Palette again:

```powershell
.\run-context-palette.bat
```

Return to or reopen the palette after file edits. Changed definitions are
detected by file signature and reloaded automatically; a restart is normally
unnecessary.

## 3. Define contexts

Normally add contexts to `data/local_contexts.json` (My configuration). Change
`data/contexts.json` only when deliberately changing Built-in starter contexts.

Minimal example:

```json
{
  "name": "Database",
  "description": "Data quality and SQL operations",
  "action_ids": [
    "db-open-dashboard",
    "db-copy-default-query"
  ],
  "preferred_action_ids": [
    "db-open-dashboard",
    "db-copy-default-query"
  ]
}
```

Notes:

- `name` must be unique across Built-in and My configuration context files.
- `action_ids` owns every action shown by Focus Actions for this context.
- `preferred_action_ids` maps up to 4 defaults to slots `6-9`.
- If `data/palette.json` has explicit slot assignments, those explicit local assignments win.

Full format: `docs/CONTEXT_CONFIGURATION.md`.

## 4. Define actions

Add actions to `data/actions.json` (shared) or `data/local_actions.json` (local).

Example `copy_text` action:

```json
{
  "id": "db-copy-default-query",
  "title": "Default DQ query",
  "description": "Copy the standard seven-day data-quality issue query",
  "contexts": ["Database"],
  "tags": ["sql", "data quality"],
  "type": "copy_text",
  "value": "select * from dq_issues where created_at >= current_date - interval '7 day';",
  "state": "Active"
}
```

Example URL-builder action from selected/copied text:

```json
{
  "id": "db-open-dashboard",
  "title": "Dashboard by ID",
  "description": "Open a database dashboard using selected or copied text",
  "contexts": ["Database"],
  "tags": ["dashboard", "lookup"],
  "type": "build_url_selection_open",
  "value": "https://example.company/dashboards/{id_url}",
  "state": "Active"
}
```

Notes:

- Action `id` must be unique across shared and local action files.
- `title` is the required short name shown in action lists.
- `description` is optional longer searchable text. It appears in hover help
  and Action info, not in the compact list row.
- `contexts` is optional. Each value should match a defined context name.
- Every action is automatically available in General; do not add General to `contexts`.
- `tags` is optional and can contain any reusable discovery terms.
- Use only supported `type` values.

Supported action types and behavior: `docs/ACTION_TYPES.md`.

## 5. Configure the quick-action surface

Add groups/items to `data/command_surface.json` (shared) or `data/local_command_surface.json` (local).

Example:

```json
{
  "id": "database-tools",
  "label": "Database tools",
  "items": [
    {
      "id": "dashboard",
      "label": "Dashboard",
      "primary_action_id": "db-open-dashboard",
      "action_ids": [
        "db-open-dashboard",
        "db-copy-default-query"
      ]
    }
  ]
}
```

Notes:

- Group IDs must be unique across shared and local files.
- Item IDs must be unique within their group.
- `action_ids` must refer to existing action IDs.

Full format: `docs/COMMAND_SURFACE_CONFIGURATION.md`.

## 6. Recommended file-first workflow

1. Create/update context in context JSON.
2. Create/update actions that reference that context.
3. Optionally expose key actions in command-surface JSON.
4. Validate with `check-context-palette.bat`.
5. Restart the app and test the Active actions.

## 7. Troubleshooting

- New action does not appear:
  - Check for duplicate IDs and invalid JSON.
  - Verify `context` names match exactly.
  - Run `check-context-palette.bat` and read reported owner references.
- Slots `6-9` are not what you expected:
  - Check `preferred_action_ids` in contexts.
  - Check whether `data/palette.json` contains explicit context slot overrides.
- Quick-action label menu is empty:
  - Confirm every `action_id` exists in shared/local action files.

## 8. Privacy and sharing rules

- Keep internal URLs, local paths, and private identifiers in local files.
- Keep Built-in files reviewable and portable.
- Do not commit personal runtime files like `data/inbox.json` or
  `data/palette.json`.
