# Standard Action Types

This overview is generated from `context_palette.action_types`, the shared source of truth used by validation and guided Action management.

AI prompt, folder, and credential actions also accept an optional **Quick
menu** path of up to three levels. Their fixed Prompts, Folders, and Passwords
menus include every Active matching action automatically; an empty path shows
the Action at that menu's root.

| Action type | Icon | User label | Family | Input | Output | Portability |
|---|---|---|---|---|---|---|
| `copy_text` | ⧉ | Paste saved text | Saved content | A fresh destination captured by F9 or Ctrl+Alt+P is optional. | Replaces clipboard text, then pastes into a fresh destination when available; Input / Output is unchanged. | Portable when the saved text contains no private information. |
| `workspace_template` | ▤ | Place a template in Input / Output | Saved content | No runtime input. | Replaces Input / Output and clipboard text. | Portable when the template contains no private information. |
| `ai_prompt` | ✦ | AI prompt | AI assistance | No runtime input. | Replaces Input / Output and clipboard text; never submits the prompt. | Portable only when the prompt contains no private or organization-specific information. |
| `open_url` | ↗ | Open a website | Open target | No runtime input unless supported template variables are present. | Opens the validated website. | Portable for public URLs; private URLs belong in local actions. |
| `open_windows_target` | ⊞ | Open or run a Windows target | Open target | No runtime input unless supported template variables are present. | Passes the target and optional arguments to Windows ShellExecute. | Windows-only. The target can execute code and is not sandboxed; configure only targets you trust. |
| `open_file` | 📄 | Open a file | Open target | No runtime input. | Opens the configured file. | Machine-local unless the path uses a supported portable placeholder. |
| `open_folder` | 📁 | Open a folder | Open target | No runtime input. | Opens the configured folder. | Machine-local unless the path uses a supported portable placeholder. |
| `send_files_to_folder` | ⇥ | Send files to folder | File transfer | Uses the exact Input / Output text as the file-source list. | Delegates the reviewed transfer to the attended file-transfer workflow; it does not change Input / Output or the clipboard. | The destination can use ordinary portable or date placeholders; the attended workflow checks sources and the destination before copying. |
| `save_edge_score_pdf` | ♫ | Save current score as PDF | Browser automation | The Edge window captured by F9 or Ctrl+Alt+P; Input / Output is not used. | Attempts to save a new PDF in the configured folder with duplicate numbering; at the accepted Save As handoff, choose the folder and filename and save manually in Edge. | Windows and English Edge controls required. Choose an available PDF folder on each PC. Manual only; no Drop or sequences. |
| `launch_app` | ▶ | Run an application | Open target | Uses fixed reviewed arguments and working directory. | Starts the validated .exe target. | Usually machine-local; requires an installed executable. |
| `excel_automation` | XL | Run an Excel automation | Excel automation | CSV export reads exact .xlsx paths from Input / Output; live workflows inventory already-open Excel workbooks. | CSV export plans reviewed outputs. Live workflows can apply Standard data formatting or convert selected physical columns to text, with optional Review. | The Action is portable; each computer needs a machine-local Python Excel setup. Live workflows change an open workbook, may clear Excel Undo, and never save or close Excel. Conversion to text requires an engine-created verified backup. |
| `sequence` | ≡ | Run a sequence | Action sequence | Uses configured Actions only; no clipboard or typed input. | Confirms every resolved step, then starts them in order. | Started effects cannot be undone. Waits are delays, not completion checks. |
| `paste_credential` | 🔑 | Paste a Windows credential | Protected credential | Requires a fresh F9 or Ctrl+Alt+P invocation from the destination field. | Confirms the destination, pastes through a no-history/no-cloud clipboard item, then clears it conditionally. | Windows-only and machine-local; the action stores only the credential target name. |
| `build_url_open` | ?↗ | Build and open a URL from a prompt | URL builder | Prompts for an identifier or value. | Copies and opens the complete URL. | Portable when the URL template is suitable for sharing. |
| `build_url_selection_open` | T↗ | Build and open a URL from selection | URL builder | Reads selected text, Input / Output, or clipboard text. | Copies and opens the complete URL. | Portable when the URL template is suitable for sharing. |
| `transform_file_text` | ↻ | Transform a text file | Text file | Reads the configured existing local text file when the action runs. | Shows the transformed text in Input / Output and copies it; the source remains unchanged until explicitly replaced. | The source path is normally machine-local. Relative paths can be portable when every computer uses the same project layout. |
| `transform_list_csv` | ⇄ | Convert Input / Output lines to a list | Input / Output transformation | Reads Input / Output text. | Replaces Input / Output and clipboard text. | Portable; operation is constrained by the application. |
| `transform_text` | T | Transform Input / Output | Input / Output transformation | Reads Input / Output text. | Replaces Input / Output and clipboard text. | Portable; operations are implemented by Context Palette. |
| `transform_slashes` | ／ | Convert Input / Output path slashes | Input / Output transformation | Reads Input / Output text. | Replaces Input / Output and clipboard text. | Portable; operation is constrained by the application. |

## Creation and legacy metadata

The Capture Inbox AI-proposal workflow is retired. No type is enabled for that workflow. Stored prompt Actions, manual creation, creation from Input / Output, and supported Excel bulk management remain available. Existing Actions created through retired tools keep their normal behavior.

The **Create action** catalogue can omit compatibility-only types. Those types remain loadable and editable so existing saved actions keep their behavior.
