# Standard Action Types

This overview is generated from `context_palette.action_types`, the shared source of truth used by validation and AI guidance.

| Action type | User label | Family | Input | Output | Portability | AI proposals |
|---|---|---|---|---|---|---|
| `copy_text` | Paste saved text | Saved content | A fresh destination captured by F9 or Ctrl+Alt+P is optional. | Replaces clipboard text, then pastes into a fresh destination when available; Input / Output is unchanged. | Portable when the saved text contains no private information. | Enabled |
| `workspace_template` | Place a template in Input / Output | Saved content | No runtime input. | Replaces Input / Output and clipboard text. | Portable when the template contains no private information. | Not yet |
| `ai_prompt` | AI prompt | AI assistance | No runtime input. | Replaces Input / Output and clipboard text; never submits the prompt. | Portable only when the prompt contains no private or organization-specific information. | Not yet |
| `open_url` | Open a website | Open target | No runtime input unless supported template variables are present. | Opens the validated website. | Portable for public URLs; private URLs belong in local actions. | Enabled |
| `open_file` | Open a file | Open target | No runtime input. | Opens the configured file. | Machine-local unless the path uses a supported portable placeholder. | Not yet |
| `open_folder` | Open a folder | Open target | No runtime input. | Opens the configured folder. | Machine-local unless the path uses a supported portable placeholder. | Not yet |
| `launch_app` | Run an application | Open target | Uses fixed reviewed arguments and working directory. | Starts the validated .exe target. | Usually machine-local; requires an installed executable. | Not yet |
| `paste_credential` | Paste a Windows credential | Protected credential | Requires a Trusted action and a fresh F9 or Ctrl+Alt+P invocation from the destination field. | Confirms the destination, pastes through a no-history/no-cloud clipboard item, then clears it conditionally. | Windows-only and machine-local; the action stores only the credential target name. | Not yet |
| `build_url_copy` | Build and copy a URL | URL builder | Prompts for an identifier or value. | Copies the complete URL without opening it. | Portable when the URL template is suitable for sharing. | Not yet |
| `build_url_open` | Build and open a URL | URL builder | Prompts for an identifier or value. | Opens the complete URL without copying it. | Portable when the URL template is suitable for sharing. | Not yet |
| `build_url_selection_open` | Build a URL from selected text | URL builder | Reads selected text, Input / Output, or clipboard text. | Copies and opens the complete URL. | Portable when the URL template is suitable for sharing. | Not yet |
| `transform_list_csv` | Convert lines to a list | Transformation | Reads Input / Output text. | Replaces Input / Output and clipboard text. | Portable; operation is constrained by the application. | Not yet |

## AI guidance boundary

AI-proposable types use the shared request safety rules plus their catalogue-specific guidance. An enabled type still creates only a validated local Draft. Types marked **Not yet** remain available for ordinary reviewed actions but cannot be proposed through the Inbox AI workflow.
