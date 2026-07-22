# Keyboard shortcuts

This is the authoritative keyboard-shortcut reference for Context Palette.
Open it from the **⌨** button at the bottom of the main window.

## Show or hide Context Palette

| Shortcut | Result |
| --- | --- |
| `F9` | Capture the current selection and show the resident palette. On some laptops use `Fn+F9`. |
| `Ctrl+Alt+P` | Alternative global capture-and-show shortcut. |
| `Esc` | Hide the focused main palette. |

## Main palette

| Shortcut | Result |
| --- | --- |
| `Ctrl+L` or `Ctrl+K` | Move focus to Find. |
| `Ctrl+I` | Capture clipboard text into Inbox. |
| `Ctrl+,` | Open Configure. |
| `Ctrl+Shift+D` | Open Configure on Diagnostics. |
| `F1` | Open complete Help. |
| `F5` | Reset transient screen state without changing saved actions, Focus, pins, or slots. |
| `Up`, `Down`, `Page Up`, `Page Down`, `Home`, `End` | Navigate action results. |
| `Enter` | Run the selected action. |
| `Enter` in Work mode | Open the selected Work Item's exact matching `.xlsx` workbook, or its folder when no exact workbook exists. |
| `Shift+Enter` in Work mode | Open the selected Work Item folder instead of its workbook. |
| `Shift` + physical top-row `1`–`9` while Find is focused | Run the corresponding action slot. This uses key positions and works on AZERTY and QWERTY. |
| Plain number-row or numpad `1`–`9` | Enter text in Find; do not run an action. |

Only Shift plus a physical top-row number key executes a slot. Ctrl-, Alt-,
AltGr-, plain number-row, and numpad input never execute action slots.

## Configure

| Shortcut | Result |
| --- | --- |
| `Alt+A` | Open Actions. |
| `Alt+T` | Open Built-in action types. |
| `Alt+C` | Open Contexts. |
| `Alt+Q` | Open Quick actions. |
| `Alt+W` | Open Work Items. |
| `Alt+D` | Open Diagnostics. |
| `Ctrl+Tab` | Select the next tab. |
| `Ctrl+Shift+Tab` | Select the previous tab. |
| `Ctrl+F` | Focus Find actions. |
| `Enter` | Edit the selected action, context, or Quick action. |
| `Esc` | Close Configure. |

### Work Items in Configure

| Shortcut | Result |
| --- | --- |
| `F6` | Switch focus between the Sources and Discovered Work Items lists. |
| `Insert` in Sources | Add a Work Item source. |
| `Delete` in Sources | Remove the selected source after confirmation. |
| `F5` in either list | Refresh the Work Item index. |
| `Enter` in Sources | Edit the selected source. |
| `Enter` in Discovered Work Items | Edit personal tags for the selected item. |

## Action forms

| Shortcut | Result |
| --- | --- |
| `Alt+C` | Focus Specific contexts. |
| `Alt+T` | Focus Tags. |
| `Alt+Down` or `F4` | Open the focused context or tag checklist. |
| Arrow keys | Move through an open checklist. |
| `Space` | Select or clear a checklist item. |
| `Esc` | Close the checklist or form. |

## Other controls and windows

| Shortcut | Result |
| --- | --- |
| `Tab` / `Shift+Tab` | Move between controls. |
| `Enter` / `Space` | Activate a focused right-side quick action. |
| `Ctrl+A` | Select all text in Input / Output. |
| `Ctrl+F` | Focus search in Help. |
| `Enter` in Help search | Find the next match. |
| `Alt+Left` in document viewer | Open the previous document in history. |
| `Alt+Right` in document viewer | Open the next document in history. |
| `Alt+Home` in document viewer | Return to the Help, Shortcuts, or action document that opened the viewer. |
| `Esc` | Close Help, Sheets, Inbox, and editing windows. |

### Harvest actions

| Shortcut | Result |
| --- | --- |
| `Ctrl+O` | Add one or more documents. |
| `Ctrl+F` | Focus and select the candidate search text. |
| `F5` | Scan or rescan the selected documents. |
| `Delete` in Sources | Remove the selected source from the transient batch. |
| `Space` in Candidates | Select or deselect the highlighted candidates for Draft creation. |
| `Enter` in Candidates | Edit the single highlighted candidate. |
| `Esc` | Close the Harvest or Draft preview window. An active scan is cancelled safely. |

## Scope

Only `F9` and `Ctrl+Alt+P` are system-wide. All other shortcuts require the
relevant Context Palette window or control to have keyboard focus.
