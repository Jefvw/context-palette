from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import time


CRED_TYPE_GENERIC = 1
CRED_TYPE_DOMAIN_PASSWORD = 2
ERROR_NOT_FOUND = 1168
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
CLIPBOARD_RETRY_COUNT = 5
CLIPBOARD_RETRY_DELAY_SECONDS = 0.02


class CredentialAccessError(Exception):
    """Raised when a Windows credential or protected clipboard operation fails."""


class _CredentialNotFound(Exception):
    """Internal signal used to try the next supported Windows credential type."""


class CredentialW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


@dataclass(frozen=True)
class CredentialSecret:
    username: str
    password: str = field(repr=False)


def decode_credential_blob(blob: bytes) -> str:
    if not blob:
        raise CredentialAccessError("The Windows credential does not contain a password.")
    try:
        value = blob.decode("utf-16-le").rstrip("\0")
    except UnicodeDecodeError:
        try:
            value = blob.decode("utf-8").rstrip("\0")
        except UnicodeDecodeError as exc:
            raise CredentialAccessError(
                "The Windows credential password uses an unsupported encoding."
            ) from exc
    if not value:
        raise CredentialAccessError("The Windows credential does not contain a password.")
    return value


def _read_credential_type(target: str, credential_type: int) -> CredentialSecret:
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(CredentialW)),
    ]
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    credential = ctypes.POINTER(CredentialW)()
    if not advapi32.CredReadW(target, credential_type, 0, ctypes.byref(credential)):
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            raise _CredentialNotFound
        raise CredentialAccessError(
            f"Windows Credential Manager could not read the credential (error {error})."
        )
    try:
        item = credential.contents
        blob = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
        return CredentialSecret(
            username=item.UserName or "",
            password=decode_credential_blob(blob),
        )
    finally:
        advapi32.CredFree(credential)


def read_windows_credential(target_name: str) -> CredentialSecret:
    """Read one exact generic or domain-password credential without enumerating."""
    target = target_name.strip()
    if not target:
        raise CredentialAccessError("The Windows credential target name is empty.")
    for credential_type in (CRED_TYPE_GENERIC, CRED_TYPE_DOMAIN_PASSWORD):
        try:
            return _read_credential_type(target, credential_type)
        except _CredentialNotFound:
            continue
    raise CredentialAccessError(
        "No generic or Windows credential exists with that exact target name."
    )


def _open_clipboard(user32: object) -> None:
    for attempt in range(CLIPBOARD_RETRY_COUNT):
        if user32.OpenClipboard(None):
            return
        if attempt + 1 < CLIPBOARD_RETRY_COUNT:
            time.sleep(CLIPBOARD_RETRY_DELAY_SECONDS)
    raise CredentialAccessError("The Windows clipboard is busy. Try again.")


def _global_memory(data: bytes, kernel32: object) -> int:
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise CredentialAccessError("Windows could not allocate protected clipboard memory.")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise CredentialAccessError("Windows could not lock protected clipboard memory.")
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    return int(handle)


def _set_clipboard_data(format_id: int, data: bytes, user32: object, kernel32: object) -> None:
    handle = _global_memory(data, kernel32)
    if not user32.SetClipboardData(format_id, handle):
        kernel32.GlobalFree(handle)
        raise CredentialAccessError("Windows could not protect the credential clipboard item.")


def set_protected_clipboard_text(value: str) -> int:
    """Replace the clipboard and exclude the secret from history and cloud sync."""
    user32 = ctypes.WinDLL("User32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    _open_clipboard(user32)
    sequence_number = 0
    try:
        if not user32.EmptyClipboard():
            raise CredentialAccessError("Windows could not clear the clipboard.")
        _set_clipboard_data(
            CF_UNICODETEXT,
            (value + "\0").encode("utf-16-le"),
            user32,
            kernel32,
        )
        for format_name in (
            "ExcludeClipboardContentFromMonitorProcessing",
            "CanIncludeInClipboardHistory",
            "CanUploadToCloudClipboard",
        ):
            format_id = user32.RegisterClipboardFormatW(format_name)
            if not format_id:
                raise CredentialAccessError(
                    "Windows could not register protected clipboard metadata."
                )
            _set_clipboard_data(format_id, (0).to_bytes(4, "little"), user32, kernel32)
        sequence_number = int(user32.GetClipboardSequenceNumber())
    except Exception:
        user32.EmptyClipboard()
        raise
    finally:
        user32.CloseClipboard()
    return sequence_number


def clear_clipboard_if_unchanged(sequence_number: int) -> bool:
    user32 = ctypes.WinDLL("User32.dll", use_last_error=True)
    user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    if int(user32.GetClipboardSequenceNumber()) != sequence_number:
        return False
    try:
        _open_clipboard(user32)
    except CredentialAccessError:
        return False
    try:
        if int(user32.GetClipboardSequenceNumber()) != sequence_number:
            return False
        return bool(user32.EmptyClipboard())
    finally:
        user32.CloseClipboard()
