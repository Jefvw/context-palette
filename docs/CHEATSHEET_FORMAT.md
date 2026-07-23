# Cheat-sheet format

Context Palette loads one structured JSON file per application, project,
workflow, or topic from `data/cheatsheets/`. Sheets are searchable in the app,
and an individual entry can be promoted to a permanent personal `copy_text`
action.

```json
{
  "id": "vscode",
  "title": "VS Code",
  "kind": "application",
  "aliases": ["code", "visual studio code"],
  "summary": "Daily commands and reminders for working in VS Code.",
  "updated_at": "2026-07-18",
  "sections": [
    {
      "title": "Start here",
      "items": [
        {
          "label": "Open command palette",
          "detail": "Ctrl+Shift+P",
          "tags": ["shortcut", "navigation"]
        }
      ]
    }
  ]
}
```

## Fields

| Field | Meaning |
| --- | --- |
| `id` | Stable sheet identifier |
| `title` | Display name |
| `kind` | Descriptive category such as `application`, `topic`, `project`, or `workflow` |
| `aliases` | Additional sheet search terms |
| `summary` | Short overview |
| `updated_at` | Last content-review date |
| `sections` | Ordered groups |
| Section `title` | Group heading and search text |
| Item `label` | Short visible name |
| Item `detail` | Useful text, shortcut, command, or note |
| Item `tags` | Optional item search terms |

Search covers sheet and section metadata plus item labels, details, and tags.

Promotion copies one item into `data/local_actions.json` as an Active action
after confirmation. It does not modify the source sheet. Review command-like
text before saving or using it; a cheat-sheet detail is reference text, not an
executable shell action.

JSON is used because it supports validation, item-level search, and item-level promotion without a third-party parser. Markdown can still be used for drafting before content is converted to this structure.
