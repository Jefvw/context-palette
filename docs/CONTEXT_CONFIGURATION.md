# Configure contexts without the UI

Contexts and actions are plain JSON. Restart Context Palette after editing.

## Shared versus local

- `data/contexts.json`: portable, reviewable contexts shared through Git.
- `data/local_contexts.json`: personal or work-specific contexts; ignored by Git.
- `data/actions.json`: portable actions referenced by shared contexts.
- `data/local_actions.json`: personal actions, unreviewed internal URLs, and machine-specific paths; ignored by Git.

Do not put internal URLs, customer names, work paths, or OneNote identifiers in shared files by default. A reviewed work URL may be shared only with explicit approval and must not contain credentials, tokens, personal IDs, or captured user data.

## Context shape

```json
{
  "name": "Archives",
  "description": "Build an archive URL from selected or copied text.",
  "technology": "Browser",
  "task": "Archive lookup",
  "preferred_action_ids": ["archives-open-selected-item"]
}
```

`preferred_action_ids` determines up to four default actions in slots 6–9. Personal explicit slots already stored in `data/palette.json` win over this default. Actions still declare their context, keeping global search useful.

## Matching URL-builder action

```json
{
  "id": "archives-open-selected-item",
  "title": "Open selected archive item",
  "context": "Archives",
  "technology": "Browser",
  "task": "Archive lookup",
  "type": "build_url_selection_open",
  "value": "http://linkto/archives/{id_url}",
  "state": "Draft"
}
```

Input comes from Input / Output, captured selection, or clipboard. `{id_url}` URL-encodes it. The resulting URL is copied and opened.

`Product lookup` is a shared example of a larger context: its four preferred actions fill slots 6–9, while additional destination-specific URL builders remain available through Find. Keeping one destination per action prevents one identifier from opening many browser windows unintentionally.

## Most useful QTP-style patterns

| Need | Action type or template |
| --- | --- |
| Reusable snippet | `copy_text` |
| Date/time snippet | `copy_text` with `%LDF%`, `%LTF%`, `%CW%` |
| Clipboard inside text | `copy_text` with `%CLIPBOARD%` or `%CLIPBOARD_URL%` |
| Build URL from selection | `build_url_selection_open` with `{id_url}` |
| Ask for an ID and copy/open URL | `build_url_copy` or `build_url_open` |
| Turn lines into query values | `transform_list_csv` with `sql_strings` |
| Reusable editable form | `workspace_template` |
| Open a safe target | `open_url`, `open_file`, `open_folder`, `launch_app` |
| Prepare windows | `window_layout` or `restore_window_snapshot` |

These cover the highest-value QTP behaviour currently implemented. Direct paste/key sequences, clipboard transactions, and rich content remain planned because they need stronger preview and safety controls. Arbitrary shell commands remain unsupported.

## Create a local context

1. Copy `data/local_contexts.example.json` to `data/local_contexts.json` if setup has not done so.
2. Add the context record to its `contexts` list.
3. Add matching actions to `data/local_actions.json`.
4. Keep IDs and context names unique across shared and local files.
5. Restart Context Palette.
6. Test every Draft action before marking it Trusted.
