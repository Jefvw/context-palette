# Configure Context Palette Through Files (No UI Editing)

This guide explains how to configure Context Palette by editing JSON files directly.

Use this when you want a repeatable, reviewable setup through source control rather than creating or editing items in the app UI.

## 1. Configuration files and ownership

Shared files (tracked in Git):

- `data/contexts.json`: shared context definitions.
- `data/actions.json`: shared action definitions.
- `data/command_surface.json`: shared quick-action surface groups/items.

Local files (ignored by Git):

- `data/local_contexts.json`: personal or machine-specific contexts.
- `data/local_actions.json`: personal/private actions.
- `data/local_command_surface.json`: personal quick-action groups/items.
- `data/palette.json`: per-machine state (focus context, pins, optional explicit slots).

Use shared files for team-safe, portable configuration.
Use local files for private URLs, local paths, and machine-specific behavior.

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

Restart is required after file edits so the app reloads definitions.

## 3. Define contexts

Add contexts to `data/contexts.json` (shared) or `data/local_contexts.json` (local).

Minimal example:

```json
{
  "name": "Database",
  "description": "Data quality and SQL operations",
  "technology": "Data",
  "task": "Analysis",
  "preferred_action_ids": [
    "db-open-dashboard",
    "db-copy-default-query"
  ]
}
```

Notes:

- `name` must be unique across shared and local context files.
- `preferred_action_ids` maps up to 4 defaults to slots `6-9`.
- If `data/palette.json` has explicit slot assignments, those explicit local assignments win.

Full format: `docs/CONTEXT_CONFIGURATION.md`.

## 4. Define actions

Add actions to `data/actions.json` (shared) or `data/local_actions.json` (local).

Example `copy_text` action:

```json
{
  "id": "db-copy-default-query",
  "title": "Copy default DQ query",
  "context": "Database",
  "technology": "Data",
  "task": "Analysis",
  "type": "copy_text",
  "value": "select * from dq_issues where created_at >= current_date - interval '7 day';",
  "state": "Draft"
}
```

Example URL-builder action from selected/copied text:

```json
{
  "id": "db-open-dashboard",
  "title": "Open dashboard by ID",
  "context": "Database",
  "technology": "Browser",
  "task": "Lookup",
  "type": "build_url_selection_open",
  "value": "https://example.company/dashboards/{id_url}",
  "state": "Draft"
}
```

Notes:

- Action `id` must be unique across shared and local action files.
- `context` should match a defined context name.
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
5. Restart the app and test Draft actions.
6. Promote to Trusted only after manual verification.

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
- Keep shared files reviewable and portable.
- Do not commit personal runtime files like `data/inbox.json`, `data/palette.json`, or snapshot data under `data/layouts/snapshots/`.
