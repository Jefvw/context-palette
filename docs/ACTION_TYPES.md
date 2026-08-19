# Standard Action Types

This overview is generated from `context_palette.action_types`, the shared source of truth used by validation and AI guidance.

AI prompt, folder, and credential actions also accept an optional **Quick
menu** path of up to three levels. Their fixed Prompts, Folders, and Passwords
menus include every Active matching action automatically; an empty path shows
the Action at that menu's root.

| Action type | Icon | User label | Family | Input | Output | Portability | AI proposals |
|---|---|---|---|---|---|---|---|
| `copy_text` | ⧉ | Paste saved text | Saved content | A fresh destination captured by F9 or Ctrl+Alt+P is optional. | Replaces clipboard text, then pastes into a fresh destination when available; Input / Output is unchanged. | Portable when the saved text contains no private information. | Enabled |
| `workspace_template` | ▤ | Place a template in Input / Output | Saved content | No runtime input. | Replaces Input / Output and clipboard text. | Portable when the template contains no private information. | Not yet |
| `ai_prompt` | ✦ | AI prompt | AI assistance | No runtime input. | Replaces Input / Output and clipboard text; never submits the prompt. | Portable only when the prompt contains no private or organization-specific information. | Not yet |
| `open_url` | ↗ | Open a website | Open target | No runtime input unless supported template variables are present. | Opens the validated website. | Portable for public URLs; private URLs belong in local actions. | Enabled |
| `open_windows_target` | ⌁ | Open or run a Windows target | Open target | No runtime input unless supported template variables are present. | Passes the target and optional arguments to Windows ShellExecute. | Windows-only. The target can execute code and is not sandboxed; configure only targets you trust. | Not yet |
| `open_file` | ▧ | Open a file | Open target | No runtime input. | Opens the configured file. | Machine-local unless the path uses a supported portable placeholder. | Not yet |
| `open_folder` | 📁 | Open a folder | Open target | No runtime input. | Opens the configured folder. | Machine-local unless the path uses a supported portable placeholder. | Not yet |
| `launch_app` | ▶ | Run an application | Open target | Uses fixed reviewed arguments and working directory. | Starts the validated .exe target. | Usually machine-local; requires an installed executable. | Not yet |
| `sequence` | ⇥ | Run a sequence | Action sequence | Uses configured Actions only; no clipboard or typed input. | Confirms every resolved step, then starts them in order. | Started effects cannot be undone. Waits are delays, not completion checks. | Not yet |
| `paste_credential` | 🔑 | Paste a Windows credential | Protected credential | Requires a fresh F9 or Ctrl+Alt+P invocation from the destination field. | Confirms the destination, pastes through a no-history/no-cloud clipboard item, then clears it conditionally. | Windows-only and machine-local; the action stores only the credential target name. | Not yet |
| `build_url_open` | ⇱ | Build and open a URL from a prompt | URL builder | Prompts for an identifier or value. | Copies and opens the complete URL. | Portable when the URL template is suitable for sharing. | Not yet |
| `build_url_selection_open` | ⇗ | Build and open a URL from selection | URL builder | Reads selected text, Input / Output, or clipboard text. | Copies and opens the complete URL. | Portable when the URL template is suitable for sharing. | Not yet |
| `transform_file_text` | ↻ | Transform a text file | Text file | Reads the configured existing local text file when the action runs. | Shows the transformed text in Input / Output and copies it; the source remains unchanged until explicitly replaced. | The source path is normally machine-local. Relative paths can be portable when every computer uses the same project layout. | Not yet |
| `transform_list_csv` | ⇄ | Convert Input / Output lines to a list | Input / Output transformation | Reads Input / Output text. | Replaces Input / Output and clipboard text. | Portable; operation is constrained by the application. | Not yet |
| `transform_text` | ✎ | Transform Input / Output | Input / Output transformation | Reads Input / Output text. | Replaces Input / Output and clipboard text. | Portable; operations are implemented by Context Palette. | Not yet |
| `transform_slashes` | ／ | Convert Input / Output path slashes | Input / Output transformation | Reads Input / Output text. | Replaces Input / Output and clipboard text. | Portable; operation is constrained by the application. | Not yet |

## AI guidance boundary

AI-proposable types use the shared request safety rules plus their catalogue-specific guidance. An enabled type creates a validated permanent local action after confirmation. Types marked **Not yet** remain available for ordinary actions but cannot be proposed through the Inbox AI workflow.

The **Create action** catalogue can omit compatibility-only types. Those types remain loadable and editable so existing saved actions keep their behavior.
