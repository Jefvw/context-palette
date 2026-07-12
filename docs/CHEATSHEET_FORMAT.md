# Cheat Sheet Format

This is the proposed local format for app or topic cheat sheets.

Use one JSON file per application or topic:

```text
data\cheatsheets\vscode.json
data\cheatsheets\codex.json
data\cheatsheets\email.json
```

JSON is the first format because it is easy for Context Palette to load, search, validate, and display in a popup without adding dependencies.

## Recommended Structure

```json
{
  "id": "vscode",
  "title": "VS Code",
  "kind": "application",
  "aliases": ["code", "visual studio code"],
  "summary": "Daily commands and reminders for working in VS Code.",
  "updated_at": "2026-07-11",
  "sections": [
    {
      "title": "Start Here",
      "items": [
        {
          "label": "Open command palette",
          "detail": "Ctrl+Shift+P",
          "tags": ["shortcut", "navigation"]
        }
      ]
    },
    {
      "title": "Project Commands",
      "items": [
        {
          "label": "Run tests",
          "detail": ".\\.venv\\Scripts\\python.exe -m unittest discover tests",
          "tags": ["command", "testing"]
        }
      ]
    }
  ]
}
```

## Field Guide

- `id`: short stable name, lowercase if possible.
- `title`: display name shown in the popup.
- `kind`: usually `application`, `topic`, `project`, or `workflow`.
- `aliases`: search words that should also find this sheet.
- `summary`: one short sentence.
- `updated_at`: date the sheet was last reviewed.
- `sections`: grouped information for scanning.
- `label`: short visible item name.
- `detail`: the useful text, shortcut, command, note, or reminder.
- `tags`: optional search/filter hints.

## Why This Shape

The popup can show sections directly.

Search can match title, aliases, section titles, labels, details, and tags.

LLM-created drafts can fill this structure without deciding UI layout.

Later, trusted cheat-sheet items can become launcher actions without converting a whole document by hand.

## Keep Separate From Markdown For Now

Markdown is pleasant for humans, but structured JSON is easier for the app to:

- show compact popup sections;
- search individual items;
- promote one item into an action;
- mark individual items as draft or trusted later.

If you are drafting by hand, write the content in any form first, then convert it into this JSON shape when it is ready to plug into Context Palette.
