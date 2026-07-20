# Right-side button configuration

The right pane is a global quick-action surface that remains visible when Focus or Find changes.

## Recommended: Configure window

Choose **Manage focus → Configure actions and buttons…**, or press `Ctrl+,`,
then open **Right-side buttons** to create or edit personal groups and buttons.
The form:

- lists actions by human-readable name;
- generates stable group and button IDs;
- saves to ignored `data/local_command_surface.json`;
- keeps reviewed shared groups visible but read-only.

## Advanced JSON files

- `data/command_surface.json`: reviewed portable groups shared through Git.
- `data/local_command_surface.json`: personal or machine-specific groups ignored by Git.
- `data/local_command_surface.example.json`: safe template copied by setup.

Shared and local group IDs must be unique case-insensitively. Button IDs must be unique within their group.

```json
{
  "id": "product-systems",
  "label": "Product systems",
  "items": [
    {
      "id": "technical-article",
      "label": "Technical article",
      "primary_action_id": "product-lookup-productinfoscreen",
      "action_ids": [
        "product-lookup-productinfoscreen",
        "product-lookup-fic",
        "product-lookup-rti"
      ]
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| Group `id` | Stable internal reference |
| Group `label` | Visible heading |
| `items` | Ordered buttons in the group |
| Item `id` | Stable internal reference within the group |
| Item `label` | Visible compact label |
| `primary_action_id` | Optional action used by Enter/Space |
| `action_ids` | Actions offered by the right-click menu |

Every action ID should resolve to an existing shared or local action. The configuration checker reports missing references with the owning group and button.

## Interaction

- Left-click runs the primary available action.
- Right-click opens the button’s assigned action menu.
- Shift+click or Ctrl+click opens the owning JSON configuration and corresponding action file.
- Enter or Space runs the first available primary action when the button has focus.

All routes use the same constrained executor as search results. Buttons never execute command strings.

After an external JSON edit, return to or reopen the palette. Changed files are detected by signature and reloaded; a restart is normally unnecessary.

## Limitations

Groups are global, not context-conditional. Drag ordering and richer controls are not implemented. Shared configuration remains file-reviewed and read-only in Configure.
