# Quick-action menu configuration

Quick actions are compact global navigation menus that remain available when
Focus or Find changes.

## Recommended: Configure window

Choose **Configure**, or press `Ctrl+,`, then open **Quick actions**. The tree
shows configured menus and the automatic Passwords, Folders, and Prompts menus
in one place.

Configured menus can:

- contain ordered Actions and personal Work Items;
- place Actions at the menu root or under as many as three submenu levels;
- add, rename, move, and delete their own saved structure;
- stay in **My configuration**, or deliberately change **Built-in** starter
  data after its Git/multi-computer warning.

Automatic menus are live projections of Active credential, folder, and prompt
Actions. Select an automatic menu or branch to create a correctly typed Action
with the normal full form. Contexts, tags, target, storage, and validation all
remain available; only the Action type and selected **Quick menu** branch are
prefilled. Select a leaf to edit that Action. The generated tree itself is not
saved or reordered separately.

## Interaction contract

- Left-click a menu launcher, or press Enter/Space on it, to browse. Nothing
  executes merely because the launcher was opened.
- Right-click the launcher to add or organize that same menu.
- Inside the open menu, left-click an Action to run exactly that Action.
- Right-click an Action to edit that exact record without running it.
- Right-click a submenu to add or organize within that exact branch.
- Work Item entries open through the existing workbook-first constrained
  opener; right-click selects the Work Item in Configure.

All Action execution still uses the same constrained executor as search
results. Quick actions never interpret command strings.

## Advanced JSON files

- `data/command_surface.json`: Built-in starter menus tracked through Git.
- `data/local_command_surface.json`: personal or machine-specific menus ignored
  by Git.
- `data/local_command_surface.example.json`: safe setup template.

Shared and local group IDs must be unique case-insensitively. Item IDs must be
unique within their complete group tree.

```json
{
  "id": "reference-sites",
  "label": "Reference sites",
  "presentation": "nested_menu",
  "items": [
    {
      "id": "python-documentation",
      "label": "Python documentation",
      "action_ids": [
        "general-open-python-docs"
      ]
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| Group `id` | Stable internal menu reference |
| Group `label` | Visible launcher label |
| Group `items` | Ordered submenu tree |
| Item `id` | Stable internal reference within the group |
| Item `label` | Visible submenu label |
| `primary_action_id` | Legacy first-in-menu Action reference; never an implicit launcher execution |
| `action_ids` | Ordered Action references |
| `targets` | Ordered mixed Action/Work Item references used by newer personal items |

The loader still accepts the historical `rows` and `nested_menu` presentation
values and legacy target fields so old personal files and backups remain valid.
Both presentations now render as menu launchers. Existing files are not
rewritten merely because they were loaded.

Every Action ID must resolve to an available Action. A Built-in menu may refer
only to Built-in Actions; otherwise another computer would receive a menu
without its private target. My configuration may refer to either Action
storage and to personal Work Items. The configuration checker reports invalid
references with their owning menu and item.

After an external JSON edit, return to or reopen the palette. File-signature
monitoring normally reloads the change without restarting.

## Limitations

Menus are global, not Context-conditional. Ordering uses explicit Move up and
Move down controls rather than drag-and-drop. Native Windows/Tk menus do not
provide app-managed search or scrolling, so organize large collections into
short, meaningful branches and use **Find matching Actions…** as the escape
route.
