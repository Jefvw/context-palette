"""Read-only, runtime-only OneNote process identity for attended worker calls.

Importing this module does not load Windows APIs or enumerate processes. Callers
must capture on their worker thread only for an explicit probe or immediately
before/after an attended read, and must never log or persist the fingerprint.
No windows, document titles, notebooks, COM objects, or process paths are read.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os


_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 0x00000102
_ERROR_NO_MORE_FILES = 18
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_ERROR_MESSAGE = "OneNote session readiness could not be verified. Probe again."


class SessionError(Exception):
    """A discovery failure without process metadata or underlying error text."""

    def __init__(self) -> None:
        super().__init__(_ERROR_MESSAGE)


class _ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _load_kernel32():
    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    signatures = {
        "CreateToolhelp32Snapshot": ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
        "Process32FirstW": ([wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)], wintypes.BOOL),
        "Process32NextW": ([wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)], wintypes.BOOL),
        "GetCurrentProcessId": ([], wintypes.DWORD),
        "ProcessIdToSessionId": ([wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "GetProcessTimes": (
            [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4,
            wintypes.BOOL,
        ),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel32, name)
        function.argtypes = arguments
        function.restype = result
    return kernel32


def _session_id(kernel32, pid: int) -> int:
    session = wintypes.DWORD()
    if not kernel32.ProcessIdToSessionId(pid, ctypes.byref(session)):
        raise SessionError()
    return int(session.value)


def _creation_time(kernel32, pid: int) -> int:
    handle = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE, False, pid
    )
    if not handle or handle == _INVALID_HANDLE_VALUE:
        raise SessionError()
    try:
        creation, exit_time, kernel_time, user_time = (
            wintypes.FILETIME() for _ in range(4)
        )
        if not kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel_time), ctypes.byref(user_time),
        ):
            raise SessionError()
        # Unlike GetExitCodeProcess, this also handles an exit code of 259.
        if kernel32.WaitForSingleObject(handle, 0) != _WAIT_TIMEOUT:
            raise SessionError()
        timestamp = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        if not timestamp:
            raise SessionError()
        return timestamp
    finally:
        if not kernel32.CloseHandle(handle):
            raise SessionError()


def _capture_once(kernel32, session_id: int) -> tuple[tuple[int, int], ...]:
    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
        raise SessionError()
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        identities = []
        seen = set()
        while found:
            if entry.szExeFile.casefold() == "onenote.exe":
                pid = int(entry.th32ProcessID)
                if not pid or pid in seen:
                    raise SessionError()
                seen.add(pid)
                # An unavailable candidate session cannot safely be ignored.
                if _session_id(kernel32, pid) == session_id:
                    identities.append((pid, _creation_time(kernel32, pid)))
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != _ERROR_NO_MORE_FILES:
            raise SessionError()
        return tuple(sorted(identities))
    finally:
        if not kernel32.CloseHandle(snapshot):
            raise SessionError()


def capture_session() -> tuple[tuple[int, int], ...]:
    """Return a stable current-session fingerprint, or fail closed.

An empty tuple means no desktop ONENOTE.EXE process was found in this Windows
session. Exact tuple comparison detects exits, additions, and PID reuse. This
is a bounded observation rather than a monitor: callers must recheck around
every operation and discard results when the fingerprint changes.
"""
    try:
        if os.name != "nt":
            raise SessionError()
        kernel32 = _load_kernel32()
        session_id = _session_id(kernel32, int(kernel32.GetCurrentProcessId()))
        first = _capture_once(kernel32, session_id)
        second = _capture_once(kernel32, session_id)
        if first != second:
            raise SessionError()
        return first
    except Exception:
        # Never expose native error details, PIDs, or synthetic adapter text.
        raise SessionError() from None
