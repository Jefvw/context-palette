from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone
import re

from .persistence import atomic_write_json


class WindowLayoutError(Exception):
    """Raised when a window layout cannot be loaded or applied."""


@dataclass(frozen=True)
class Monitor:
    left: int
    top: int
    right: int
    bottom: int
    primary: bool = False

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


MONITORINFOF_PRIMARY = 1
SW_RESTORE = 9
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
EXCLUDED_WINDOW_CLASSES = {
    "Windows.UI.Core.CoreWindow",
    "ApplicationFrameWindow",
    "Shell_TrayWnd",
    "Progman",
    "WorkerW",
}


def detect_monitors() -> list[Monitor]:
    user32 = ctypes.windll.user32
    monitors: list[Monitor] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def callback(handle, _hdc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            work = info.rcWork
            monitors.append(
                Monitor(
                    work.left,
                    work.top,
                    work.right,
                    work.bottom,
                    bool(info.dwFlags & MONITORINFOF_PRIMARY),
                )
            )
        return True

    if not user32.EnumDisplayMonitors(None, None, callback_type(callback), 0):
        raise WindowLayoutError("Windows could not enumerate the connected screens.")
    monitors.sort(key=lambda monitor: (not monitor.primary, monitor.left, monitor.top))
    if not monitors:
        raise WindowLayoutError("No usable screen was detected.")
    return monitors


def load_window_layout(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WindowLayoutError(f"Window layout was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WindowLayoutError(f"Window layout is not valid JSON: {path}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("windows"), list):
        raise WindowLayoutError("Window layout must contain a windows list.")
    placements = raw.get("placements")
    if not isinstance(placements, dict):
        raise WindowLayoutError("Window layout must contain placement variants.")
    return raw


def selected_placements(layout: dict[str, object], monitor_count: int) -> dict[str, dict[str, object]]:
    placements = layout["placements"]
    assert isinstance(placements, dict)
    variant = "two_or_more" if monitor_count >= 2 else "one"
    selected = placements.get(variant)
    if not isinstance(selected, dict):
        raise WindowLayoutError(f"Window layout has no '{variant}' placement variant.")
    parsed: dict[str, dict[str, object]] = {}
    for window_id, placement in selected.items():
        if not isinstance(window_id, str) or not isinstance(placement, dict):
            raise WindowLayoutError("Window placements must be objects keyed by window ID.")
        parsed[window_id] = placement
    return parsed


def apply_window_layout(path: Path, *, base_directory: Path | None = None) -> str:
    layout = load_window_layout(path)
    monitors = detect_monitors()
    placements = selected_placements(layout, len(monitors))
    windows = layout["windows"]
    assert isinstance(windows, list)
    opened = 0

    for item in windows:
        if not isinstance(item, dict):
            raise WindowLayoutError("Each configured window must be an object.")
        window_id = item.get("id")
        folder_value = item.get("folder")
        if not isinstance(window_id, str) or not isinstance(folder_value, str):
            raise WindowLayoutError("Each Explorer window needs an ID and folder.")
        placement = placements.get(window_id)
        if placement is None:
            continue
        folder = Path(folder_value).expanduser()
        if not folder.is_absolute():
            folder = (base_directory or path.parent) / folder
        folder = folder.resolve()
        if not folder.is_dir():
            raise WindowLayoutError(f"Explorer folder does not exist: {folder}")
        handle = _open_new_explorer_window(folder)
        _place_window(handle, placement, monitors)
        opened += 1

    return f"Opened and arranged {opened} Explorer windows across {len(monitors)} screen(s)."


def describe_window_layout(path: Path) -> str:
    layout = load_window_layout(path)
    monitors = detect_monitors()
    windows = layout["windows"]
    assert isinstance(windows, list)
    title = str(layout.get("title", path.stem))
    return f"{title}\nDetected screens: {len(monitors)}\nConfigured windows: {len(windows)}"


def capture_window_snapshot(
    directory: Path,
    name: str,
    *,
    exclude_handle: int | None = None,
    foreground_handle: int | None = None,
) -> Path:
    clean_name = name.strip()
    if not clean_name:
        raise WindowLayoutError("Snapshot name cannot be empty.")
    monitors = detect_monitors()
    windows = []
    for z_order, window in enumerate(_visible_windows()):
        if exclude_handle is not None and window["handle"] == exclude_handle:
            continue
        monitor_index, relative = _relative_placement(window["rect"], monitors)
        windows.append(
            {
                "title": window["title"],
                "class_name": window["class_name"],
                "executable": window["executable"],
                "z_order": z_order,
                "was_foreground": window["handle"] == foreground_handle,
                "monitor": monitor_index,
                **relative,
            }
        )
    if not windows:
        raise WindowLayoutError("No ordinary application windows were found to capture.")
    slug = re.sub(r"[^a-z0-9]+", "-", clean_name.casefold()).strip("-") or "snapshot"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug}-{datetime.now():%Y%m%d-%H%M%S}.json"
    data = {
        "title": clean_name,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "screen_count": len(monitors),
        "windows": windows,
    }
    atomic_write_json(path, data)
    return path


def restore_window_snapshot(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WindowLayoutError(f"Window snapshot was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WindowLayoutError(f"Window snapshot is not valid JSON: {path}") from exc
    configured = data.get("windows") if isinstance(data, dict) else None
    if not isinstance(configured, list):
        raise WindowLayoutError("Window snapshot must contain a windows list.")
    monitors = detect_monitors()
    current = _visible_windows()
    used: set[int] = set()
    restored = 0
    launched = 0
    foreground_to_restore: int | None = None
    for saved in configured:
        if not isinstance(saved, dict):
            continue
        if _excluded_saved_window(saved):
            continue
        match = _match_snapshot_window(saved, current, used)
        if match is None:
            match = _launch_snapshot_window(saved, used)
            if match is None:
                continue
            current.append(match)
            launched += 1
        placement = {
            key: saved.get(key) for key in ("monitor", "x", "y", "width", "height")
        }
        monitor_index = int(placement.get("monitor") or 0)
        if monitor_index >= len(monitors):
            placement["monitor"] = 0
        _place_window(match["handle"], placement, monitors)
        used.add(match["handle"])
        if saved.get("was_foreground") is True:
            foreground_to_restore = match["handle"]
        restored += 1
    eligible = [
        saved
        for saved in configured
        if isinstance(saved, dict) and not _excluded_saved_window(saved)
    ]
    missing = len(eligible) - restored
    if foreground_to_restore is not None:
        ctypes.windll.user32.SetForegroundWindow(foreground_to_restore)
    return (
        f"Restored {restored} window(s), launched {launched}; "
        f"{missing} snapshot window(s) could not be restored."
    )


def describe_window_snapshot(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise WindowLayoutError(f"Window snapshot could not be read: {path}") from exc
    windows = data.get("windows", []) if isinstance(data, dict) else []
    return (
        f"Restore snapshot: {data.get('title', path.stem)}\n"
        f"Captured screens: {data.get('screen_count', '?')}\n"
        f"Captured windows: {len(windows)}\n"
        "Matching windows are positioned; missing apps use saved launch details when available."
    )


def browser_windows_without_launch_url(path: Path) -> list[tuple[int, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    windows = data.get("windows", []) if isinstance(data, dict) else []
    result = []
    for index, window in enumerate(windows):
        if not isinstance(window, dict):
            continue
        executable = Path(str(window.get("executable", ""))).name.casefold()
        if executable in {"msedge.exe", "chrome.exe", "brave.exe", "firefox.exe"} and not window.get(
            "launch_target"
        ):
            result.append((index, str(window.get("title", "Browser window"))))
    return result


def set_snapshot_launch_target(path: Path, window_index: int, target: str) -> None:
    clean_target = target.strip()
    if not clean_target:
        return
    if not clean_target.startswith(("http://", "https://")):
        raise WindowLayoutError("Browser launch target must start with http:// or https://.")
    data = json.loads(path.read_text(encoding="utf-8"))
    windows = data.get("windows", []) if isinstance(data, dict) else []
    if not isinstance(windows, list) or not 0 <= window_index < len(windows):
        raise WindowLayoutError("Snapshot browser window was not found.")
    windows[window_index]["launch_target"] = clean_target
    atomic_write_json(path, data)


def _visible_windows() -> list[dict[str, object]]:
    user32 = ctypes.windll.user32
    windows: list[dict[str, object]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(handle, _data):
        if not user32.IsWindowVisible(handle) or user32.IsIconic(handle):
            return True
        if user32.GetWindowLongW(handle, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        title = _window_title(int(handle)).strip()
        if not title or title == "Program Manager":
            return True
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(handle, class_buffer, len(class_buffer))
        if class_buffer.value in EXCLUDED_WINDOW_CLASSES or title.startswith("Context Palette"):
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            return True
        executable = _window_executable(int(handle))
        if not executable:
            return True
        windows.append(
            {
                "handle": int(handle),
                "title": title,
                "class_name": class_buffer.value,
                "executable": executable,
                "rect": (rect.left, rect.top, rect.right, rect.bottom),
            }
        )
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return windows


def _window_executable(handle: int) -> str:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
    if not process:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(process)


def _relative_placement(rect: tuple[int, int, int, int], monitors: list[Monitor]):
    left, top, right, bottom = rect
    areas = []
    for monitor in monitors:
        overlap_width = max(0, min(right, monitor.right) - max(left, monitor.left))
        overlap_height = max(0, min(bottom, monitor.bottom) - max(top, monitor.top))
        areas.append(overlap_width * overlap_height)
    monitor_index = max(range(len(monitors)), key=areas.__getitem__)
    monitor = monitors[monitor_index]
    placement = {
        "x": round(max(0, min(1, (left - monitor.left) / monitor.width)), 4),
        "y": round(max(0, min(1, (top - monitor.top) / monitor.height)), 4),
        "width": round(max(0.01, min(1, (right - left) / monitor.width)), 4),
        "height": round(max(0.01, min(1, (bottom - top) / monitor.height)), 4),
    }
    return monitor_index, placement


def _match_snapshot_window(saved, current, used):
    executable = str(saved.get("executable", "")).casefold()
    title = str(saved.get("title", "")).casefold()
    class_name = str(saved.get("class_name", "")).casefold()
    candidates = [
        window
        for window in current
        if window["handle"] not in used
        and str(window["executable"]).casefold() == executable
        and str(window["class_name"]).casefold() == class_name
    ]
    exact = [window for window in candidates if str(window["title"]).casefold() == title]
    if exact:
        return exact[0]
    partial = [
        window
        for window in candidates
        if title in str(window["title"]).casefold() or str(window["title"]).casefold() in title
    ]
    if partial:
        return partial[0]
    # Titles change frequently in browsers, editors, and documents. Once the
    # executable and native window class match, use the next unused instance.
    return candidates[0] if candidates else None


def _excluded_saved_window(saved: dict[str, object]) -> bool:
    return (
        str(saved.get("title", "")).startswith("Context Palette")
        or str(saved.get("class_name", "")) in EXCLUDED_WINDOW_CLASSES
    )


def _launch_snapshot_window(saved: dict[str, object], used: set[int]):
    executable = Path(str(saved.get("executable", "")))
    if not executable.is_file():
        return None
    before = {window["handle"] for window in _visible_windows()}
    name = executable.name.casefold()
    command = [str(executable)]
    launch_target = str(saved.get("launch_target", "")).strip()
    if name in {"msedge.exe", "chrome.exe", "brave.exe"}:
        command.append("--new-window")
        if launch_target:
            command.append(launch_target)
    elif name == "firefox.exe" and launch_target:
        command.extend(["-new-window", launch_target])
    elif name == "explorer.exe":
        command.append("/n,")
    try:
        subprocess.Popen(command)
    except OSError:
        return None

    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        current = _visible_windows()
        new_windows = [window for window in current if window["handle"] not in before]
        match = _match_snapshot_window(saved, new_windows, used)
        if match is not None:
            return match
        time.sleep(0.1)
    return None


def _explorer_windows() -> list[int]:
    user32 = ctypes.windll.user32
    handles: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(handle, _data):
        if not user32.IsWindowVisible(handle):
            return True
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(handle, class_name, len(class_name))
        if class_name.value in {"CabinetWClass", "ExploreWClass"}:
            handles.append(int(handle))
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return handles


def _window_title(handle: int) -> str:
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(handle)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(handle, buffer, len(buffer))
    return buffer.value


def _open_new_explorer_window(folder: Path) -> int:
    before = set(_explorer_windows())
    subprocess.Popen(["explorer.exe", "/n,", str(folder)])
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        current = _explorer_windows()
        new_handles = [handle for handle in current if handle not in before]
        if new_handles:
            return new_handles[0]
        matching = [
            handle for handle in current if folder.name.casefold() in _window_title(handle).casefold()
        ]
        if matching:
            return matching[0]
        time.sleep(0.1)
    raise WindowLayoutError(f"Explorer window did not appear for: {folder}")


def _place_window(handle: int, placement: dict[str, object], monitors: list[Monitor]) -> None:
    try:
        monitor_index = int(placement.get("monitor", 0))
        x = float(placement.get("x", 0))
        y = float(placement.get("y", 0))
        width = float(placement.get("width", 1))
        height = float(placement.get("height", 1))
    except (TypeError, ValueError) as exc:
        raise WindowLayoutError("Window placement contains invalid coordinates.") from exc
    if not 0 <= monitor_index < len(monitors):
        raise WindowLayoutError(f"Configured monitor {monitor_index + 1} is not connected.")
    if not all(0 <= value <= 1 for value in (x, y, width, height)) or width <= 0 or height <= 0:
        raise WindowLayoutError("Window placement coordinates must be relative values from 0 to 1.")

    monitor = monitors[monitor_index]
    left = monitor.left + round(monitor.width * x)
    top = monitor.top + round(monitor.height * y)
    pixel_width = round(monitor.width * width)
    pixel_height = round(monitor.height * height)
    user32 = ctypes.windll.user32
    user32.ShowWindow(handle, SW_RESTORE)
    if not user32.SetWindowPos(
        handle,
        None,
        left,
        top,
        pixel_width,
        pixel_height,
        SWP_NOZORDER | SWP_NOACTIVATE,
    ):
        raise WindowLayoutError("Windows could not position an Explorer window.")
