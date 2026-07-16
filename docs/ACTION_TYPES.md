# Standard Action Types

This overview is generated from `context_palette.action_types`, the shared source of truth used by validation and AI guidance.

| Action type | User label | Family | Input | Output | Portability | AI proposals |
|---|---|---|---|---|---|---|
| `copy_text` | Copy saved text | Saved content | No runtime input. | Replaces clipboard text; Input / Output is unchanged. | Portable when the saved text contains no private information. | Enabled |
| `workspace_template` | Place a template in Input / Output | Saved content | No runtime input. | Replaces Input / Output and clipboard text. | Portable when the template contains no private information. | Not yet |
| `open_url` | Open a website | Open target | No runtime input unless supported template variables are present. | Opens the validated website. | Portable for public URLs; private URLs belong in local actions. | Enabled |
| `open_file` | Open a file | Open target | No runtime input. | Opens the configured file. | Machine-local unless the path uses a supported portable placeholder. | Not yet |
| `open_folder` | Open a folder | Open target | No runtime input. | Opens the configured folder. | Machine-local unless the path uses a supported portable placeholder. | Not yet |
| `launch_app` | Run an application | Open target | Uses fixed reviewed arguments and working directory. | Starts the validated .exe target. | Usually machine-local; requires an installed executable. | Not yet |
| `build_url_copy` | Build and copy a URL | URL builder | Prompts for an identifier or value. | Copies the complete URL without opening it. | Portable when the URL template is suitable for sharing. | Not yet |
| `build_url_open` | Build and open a URL | URL builder | Prompts for an identifier or value. | Opens the complete URL without copying it. | Portable when the URL template is suitable for sharing. | Not yet |
| `build_url_selection_open` | Build a URL from selected text | URL builder | Reads selected text, Input / Output, or clipboard text. | Copies and opens the complete URL. | Portable when the URL template is suitable for sharing. | Not yet |
| `transform_list_csv` | Convert lines to a list | Transformation | Reads Input / Output text. | Replaces Input / Output and clipboard text. | Portable; operation is constrained by the application. | Not yet |
| `window_layout` | Arrange a window layout | Window management | Reads a reviewed layout JSON file. | Opens and positions configured windows. | Portable only when its target paths are portable. | Not yet |
| `restore_window_snapshot` | Restore a window snapshot | Window management | Reads a local snapshot containing window metadata. | Matches, starts, and positions restorable windows. | Local and potentially private; snapshots are never shared by default. | Not yet |

## AI guidance boundary

AI-proposable types use the shared request safety rules plus their catalogue-specific guidance. An enabled type still creates only a validated local Draft. Types marked **Not yet** remain available for ordinary reviewed actions but cannot be proposed through the Inbox AI workflow.
