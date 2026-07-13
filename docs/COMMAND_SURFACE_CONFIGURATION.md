# Configure the quick-action surface

The right half of Context Palette is a global command surface. It is independent of the selected Focus context and contains groups with multiple compact controls.

## Files

- `data/command_surface.json`: reviewed portable groups shared through Git.
- `data/local_command_surface.json`: optional personal or machine-specific groups ignored by Git.
- `data/local_command_surface.example.json`: safe empty template copied by setup.

Shared and local groups are combined. Group IDs must be unique, including differences in letter case. Item IDs must be unique inside their group.

## Group and item shape

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

Group fields:

- `id`: stable unique configuration ID.
- `label`: short heading for the subarea.
- `items`: any number of compact labels/buttons in the subarea.

Item fields:

- `id`: stable ID unique inside the group.
- `label`: compact visible label text.
- `primary_action_id`: optional preferred action inserted first in the right-click menu when it is not already listed.
- `action_ids`: actions shown in this item's right-click menu.

Every action ID should refer to an existing shared or local action. Missing menu IDs are skipped. Labels never execute on left-click; execution is deliberately reserved for their right-click menus.

## Interaction

- Left-click a label to open the owning command-surface JSON and corresponding shared/local action JSON in the default editor.
- Right-click that label to select one of its assigned actions.
- Actions use the same Input / Output, selected-text, clipboard, URL validation, and constrained execution path as actions in the left search list.
- Edit the JSON and restart Context Palette, or use an existing Reload path, to rebuild the surface.

The surface does not execute command strings. It only references allow-listed Context Palette actions.
