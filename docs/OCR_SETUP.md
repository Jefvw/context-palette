# OCR setup, use, and other-PC handoff

Context Palette can extract readable text from a local image into **Input / Output**.
Recognition runs locally. The image and recognized text are not sent to an online
OCR service, and the clipboard image is not replaced.

The OCR component is optional because its native runtime and models add about
270 MB. It installs inside the repository's ignored `.venv`; administrator
rights are not required. If OCR setup is skipped or fails, Context Palette still
starts normally and every non-OCR feature remains available. Only **Extract
text** reports that its optional component is unavailable.

## Choose the setup that matches the PC

| Target PC | Use this route |
| --- | --- |
| Compatible Python and package-download access | Run `setup-ocr-context-palette.bat` on that PC. |
| Compatible Python, but package downloads are blocked | Prepare `offline-packages` on a connected compatible PC, then copy only that directory into a clean checkout/export of the same commit and run `setup-offline-context-palette.bat`. |
| No compatible Python, and Python cannot be installed | The current source distribution cannot run there. A future self-contained portable release must bundle Python, Tk, application packages, and OCR. Do not copy `.venv` as a workaround. |

A compatible base installation is Python 3.12 or newer 3.x with pip and
Tcl/Tk. A normal per-user python.org installation does not require administrator
rights, but an organization's application policy may still block it.

## Normal setup on another PC

1. Install the Python family named in `.python-version`, with Tcl/Tk enabled.
2. Obtain or update the Context Palette repository.
3. Open a terminal in the Context Palette folder.
4. Run:

   ```powershell
   .\setup-ocr-context-palette.bat
   ```

5. Start or restart the app:

   ```powershell
   .\run-context-palette.bat
   ```

The setup first prepares the normal application, then installs the pinned OCR
packages, initializes the local engine once, and reports **Local OCR is ready**.
Later recognition does not need network access. If the optional installation or
engine check fails after core setup, start Context Palette normally; the setup
output explicitly confirms that only **Extract text** is unavailable.

## Offline package setup

This route is for a target PC that already has compatible Python and Tcl/Tk,
but cannot reach Python package servers.

### On a connected preparation PC

Use a Windows PC with the same processor architecture and exact Python
major/minor version as the target. From a clean checkout of the exact commit
that the target will use, run:

```powershell
.\prepare-offline-context-palette.bat
```

The script prepares the core application environment, downloads/builds required
application packages, then separately attempts the optional OCR packages. It
does not install or initialize OCR merely to prepare the handoff. If OCR package
preparation fails, it keeps a usable core package folder and prints a warning.

On the target, use a clean checkout/export of the same commit and copy only the
generated `offline-packages` directory into it. Do not copy `.venv`, `.venv-*`,
logs, `data/local_*`, Inbox, palette state, `.bak` files, or other ignored
personal/runtime content. Transfer personal configuration separately through
**Configure → Backup and restore**, after reviewing its privacy warning. A
removable drive or an organization-approved file-transfer route is fine.

Do not commit `offline-packages`: it is large, platform-specific, and ignored by
Git. Prepare separate folders for different Windows architectures or Python
major/minor versions.

### On the disconnected or package-blocked target PC

Open a terminal in the copied Context Palette folder and run:

```powershell
.\setup-offline-context-palette.bat
.\run-context-palette.bat
```

Offline setup uses `--no-index`, so it consumes only the prepared local packages
and cannot fall back to a network package source. It installs and checks the
core application first, then attempts optional OCR, then runs the complete
application check. If optional OCR is absent or cannot initialize, the script
reports a core-only success and Context Palette remains usable without
**Extract text**.

To install only the core from the prepared folder, use:

```powershell
$env:CONTEXT_PALETTE_WHEELHOUSE = "$PWD\offline-packages"
.\setup-context-palette.bat
.\run-context-palette.bat
```

## Use Extract text

1. Put the image source in one of these places:

   - select or enter one exact absolute image path in **Input / Output**;
   - copy an image or screenshot to the Windows clipboard; or
   - leave neither source available and choose a file when prompted.

2. Choose the **Extract text** icon in the Input / Output header.
3. Wait for the local background recognition to finish.
4. If Input / Output already contains text, choose **Replace**, **Append**, or
   **Cancel**. Cancel preserves the existing text.
5. Review the result. One normal Undo restores the previous Input / Output edit.

Supported source formats are PNG, JPEG, BMP, GIF, TIFF, and WebP. Context
Palette rejects sources above 50 MiB or 40 million decoded pixels before
native OCR starts. No readable text, a changed source, or an engine error leaves
Input / Output unchanged.

The first extraction after app startup is slower because the local engine and
models initialize. Only one OCR request can run at a time. Closing Context
Palette is blocked while native recognition is active so the background worker
is not abandoned.

## OCR configuration

There is intentionally no OCR engine or language setting in this first slice.
Context Palette uses one tested, pinned local RapidOCR/ONNX Runtime stack and
its bundled default recognition models. This keeps setup repeatable across PCs
and avoids exposing controls that the current engine cannot honor reliably.

Other Context Palette settings remain available through **Configure** or
`Ctrl+,`: Actions, Focuses, Quick actions, Work Items, and Backup and restore.

## Move configuration to another PC

For personal Context Palette data, prefer **Configure → Backup and restore**:

1. On the source PC, create a complete-configuration ZIP. Decide whether Inbox
   and managed text content should be included.
2. Transfer the ZIP securely; it can contain sensitive data and is not encrypted.
3. On the target PC, inspect the ZIP in **Backup and restore**, then restore it.
4. Recreate or transfer external files separately. Backups do not include files,
   folders, scripts, applications, Work Item folders, or workbook templates that
   Actions/settings merely reference.
5. Review machine-specific absolute paths after restore.

Shared Built-in records travel through Git. Personal local records stay outside
Git unless explicitly privacy-reviewed and promoted to Built-in data.

## Developer setup and verification

For normal development with OCR available:

```powershell
.\setup-ocr-context-palette.bat
.\develop-context-palette.bat
```

The main boundaries are `src/context_palette/ocr.py` for safe decoding and the
provider, `workspace_panel.py` for the compact control, `launcher.py` for
background orchestration, `requirements-ocr.txt` for pinned optional packages,
and the OCR/offline setup scripts for deployment.

Focused verification:

```powershell
.\python-context-palette.bat -m unittest tests.test_ocr tests.test_launcher_interactions tests.test_launcher_smoke tests.test_windows_scripts
.\develop-context-palette.bat
```

When updating an OCR dependency, recheck Windows/Python compatibility,
architecture, no-admin installation, license, installed size, first/repeat
speed, offline recognition, malformed/oversized-image handling, and the offline
wheel workflow. Rebuild `offline-packages` after requirement changes.

## Troubleshooting

- **OCR component unavailable:** run `setup-ocr-context-palette.bat`, then
  restart the app. Until it succeeds, continue using the rest of Context
  Palette normally.
- **Package downloads blocked:** use the offline package workflow above.
- **Offline package not found:** keep `offline-packages` next to
  `setup-offline-context-palette.bat` and prepare it again for the target's
  exact Python major/minor and processor architecture.
- **No image available:** copy a screenshot/image, enter one exact absolute
  image path, or choose a file when prompted.
- **No readable text:** try a sharper crop with larger, horizontal text and
  better contrast. The original image and Input / Output remain unchanged.
- **First extraction seems slow:** initial model loading is expected.
- **No usable Python/Tk and installation is prohibited:** stop. The wheel-based
  offline route cannot provide Python itself; use a future self-contained
  release rather than copying another computer's `.venv`.
