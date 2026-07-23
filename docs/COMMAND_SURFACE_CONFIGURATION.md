# Right-side button configuration

The right pane is a global quick-action surface that remains visible when Focus or Find changes.

## Recommended: Configure window

Choose **Configure**, or press `Ctrl+,`, then open **Quick actions** to manage
the complete right-side surface.
The form:

- creates, renames, deletes, and reorders groups and Quick actions;
- assigns an unlimited ordered list of actions by human-readable name;
- uses the first assigned action for left-click and the complete list for the
  right-click menu;
- previews both behaviors before saving;
- generates stable group and Quick-action IDs;
- explicitly stores new groups in **My configuration** or **Built-in**;
- keeps existing Built-in groups editable after a developer-impact warning;
- limits Built-in groups to Built-in actions so starter configuration never
  depends on one PC. My configuration groups may use either kind of action.

## Advanced JSON files

- `data/command_surface.json`: Built-in starter groups tracked through Git.
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

Every action ID must resolve to an available action. A Built-in group may refer
only to actions in `data/actions.json`; otherwise another computer would receive
the button without its local-only action. A My configuration group may refer to both
Built-in and local actions. The configuration checker reports missing and
non-portable references with the owning group and button.

## Interaction

- Left-click runs the primary available action.
- Right-click opens the button’s assigned action menu.
- Shift+click or Ctrl+click opens the owning JSON configuration and corresponding action file.
- Enter or Space runs the first available primary action when the button has focus.

All routes use the same constrained executor as search results. Buttons never execute command strings.

After an external JSON edit, return to or reopen the palette. Changed files are detected by signature and reloaded; a restart is normally unnecessary.

## Limitations

Groups are global, not context-conditional. Ordering uses explicit Move up and
Move down controls rather than drag-and-drop. Application-owned editor and Work
Item context menus remain fixed program controls rather than stored Quick-action
configuration.
