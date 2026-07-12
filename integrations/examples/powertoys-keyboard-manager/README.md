# PowerToys Keyboard Manager examples

## Example A: preserve selected-text capture

In PowerToys Settings > Keyboard Manager > Remap a shortcut, add:

| Select | To send | Target app |
| --- | --- | --- |
| `Win+Shift+P` | `Ctrl+Alt+P` | blank/global |

Test it by selecting `5331` in Notepad and pressing `Win+Shift+P`. Context Palette should open and show `5331` in Input / Output.

This is the recommended mapping because it uses the app's canonical hotkey and therefore preserves selection capture.

## Example B: start directly in Tijdsregistratie

Keyboard Manager now supports **Start App** for a shortcut. Add this second example:

| Field | Value |
| --- | --- |
| Shortcut | `Win+Shift+T` |
| Action | Start App |
| App | `powershell.exe` |
| Args | `-NoProfile -ExecutionPolicy Bypass -File "<clone>\integrations\examples\powertoys-keyboard-manager\Show-Tijdsregistratie.ps1"` |
| Start in | repository root |
| Elevation | Normal |
| Visibility | Hidden |

Expected result: `Win+Shift+T` shows Context Palette in the `Tijdsregistratie` context. This variant does not capture selected text; use Example A when selection is the input.
