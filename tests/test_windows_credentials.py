from __future__ import annotations

import ctypes
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, call, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.windows_credentials import (
    CF_UNICODETEXT,
    CRED_TYPE_DOMAIN_PASSWORD,
    CRED_TYPE_GENERIC,
    ClipboardTextSnapshot,
    CredentialAccessError,
    CredentialSecret,
    ProtectedClipboardTransaction,
    _CredentialNotFound,
    _clipboard_text_snapshot,
    begin_protected_clipboard_transaction,
    decode_credential_blob,
    read_windows_credential,
    restore_clipboard_text_if_unchanged,
)


class WindowsCredentialTests(unittest.TestCase):
    def test_decodes_windows_unicode_credential_blob(self):
        self.assertEqual(
            decode_credential_blob("sëcret".encode("utf-16-le")),
            "sëcret",
        )

    def test_empty_credential_blob_is_rejected(self):
        with self.assertRaises(CredentialAccessError):
            decode_credential_blob(b"")

    def test_secret_representation_never_contains_password(self):
        secret = CredentialSecret(username="user@example.com", password="do-not-show")

        self.assertNotIn("do-not-show", repr(secret))

    def test_clipboard_snapshot_representation_never_contains_text(self):
        snapshot = ClipboardTextSnapshot("private prior text")

        self.assertNotIn("private prior text", repr(snapshot))

    def test_protected_transaction_representation_never_contains_snapshot(self):
        transaction = ProtectedClipboardTransaction(
            42,
            ClipboardTextSnapshot("private prior text"),
        )

        self.assertNotIn("private prior text", repr(transaction))

    def test_plain_text_snapshot_is_copied_while_clipboard_is_open(self):
        encoded = "previous\0".encode("utf-16-le")
        raw = ctypes.create_string_buffer(encoded, len(encoded))
        user32 = Mock()
        kernel32 = Mock()
        user32.IsClipboardFormatAvailable.return_value = True
        user32.GetClipboardData.return_value = 123
        kernel32.GlobalSize.return_value = ctypes.sizeof(raw)
        kernel32.GlobalLock.return_value = ctypes.addressof(raw)

        snapshot = _clipboard_text_snapshot(user32, kernel32)

        self.assertEqual(snapshot, ClipboardTextSnapshot("previous"))
        kernel32.GlobalUnlock.assert_called_once_with(123)

    def test_non_text_clipboard_is_not_destroyed_for_credential_paste(self):
        user32 = Mock()
        kernel32 = Mock()
        user32.IsClipboardFormatAvailable.return_value = False
        user32.CountClipboardFormats.return_value = 1

        with self.assertRaisesRegex(CredentialAccessError, "non-text content"):
            _clipboard_text_snapshot(user32, kernel32)

        user32.EmptyClipboard.assert_not_called()

    def test_protected_transaction_snapshots_before_replacing_in_one_open(self):
        user32 = Mock()
        kernel32 = Mock()
        user32.EmptyClipboard.return_value = True
        user32.RegisterClipboardFormatW.side_effect = (100, 101, 102)
        user32.GetClipboardSequenceNumber.return_value = 42
        events: list[str] = []

        def win_dll(name: str, **_kwargs: object) -> Mock:
            return user32 if name == "User32.dll" else kernel32

        user32.EmptyClipboard.side_effect = lambda: events.append("empty") or True
        with (
            patch(
                "context_palette.windows_credentials.ctypes.WinDLL",
                side_effect=win_dll,
            ),
            patch("context_palette.windows_credentials._open_clipboard") as open_clipboard,
            patch(
                "context_palette.windows_credentials._clipboard_text_snapshot",
                side_effect=lambda *_args: events.append("snapshot")
                or ClipboardTextSnapshot("previous"),
            ),
            patch(
                "context_palette.windows_credentials._set_clipboard_data",
                side_effect=lambda *_args: events.append("write"),
            ),
        ):
            transaction = begin_protected_clipboard_transaction("secret")

        self.assertEqual(
            transaction,
            ProtectedClipboardTransaction(42, ClipboardTextSnapshot("previous")),
        )
        self.assertEqual(events[0:2], ["snapshot", "empty"])
        self.assertEqual(events.count("write"), 4)
        open_clipboard.assert_called_once_with(user32)
        user32.CloseClipboard.assert_called_once_with()

    def test_failed_protected_metadata_write_removes_secret_before_returning(self):
        user32 = Mock()
        kernel32 = Mock()
        user32.EmptyClipboard.return_value = True
        user32.RegisterClipboardFormatW.return_value = 100

        def win_dll(name: str, **_kwargs: object) -> Mock:
            return user32 if name == "User32.dll" else kernel32

        with (
            patch(
                "context_palette.windows_credentials.ctypes.WinDLL",
                side_effect=win_dll,
            ),
            patch("context_palette.windows_credentials._open_clipboard"),
            patch(
                "context_palette.windows_credentials._clipboard_text_snapshot",
                return_value=ClipboardTextSnapshot("previous"),
            ),
            patch(
                "context_palette.windows_credentials._set_clipboard_data",
                side_effect=(None, CredentialAccessError("metadata failed")),
            ),
            self.assertRaisesRegex(CredentialAccessError, "metadata failed"),
        ):
            begin_protected_clipboard_transaction("secret")

        self.assertEqual(user32.EmptyClipboard.call_count, 2)
        user32.CloseClipboard.assert_called_once_with()

    def test_clipboard_restore_yields_to_newer_clipboard_content(self):
        user32 = Mock()
        user32.GetClipboardSequenceNumber.return_value = 99

        with patch(
            "context_palette.windows_credentials.ctypes.WinDLL",
            return_value=user32,
        ):
            restored = restore_clipboard_text_if_unchanged(
                42,
                ClipboardTextSnapshot("previous"),
            )

        self.assertFalse(restored)
        user32.OpenClipboard.assert_not_called()
        user32.EmptyClipboard.assert_not_called()

    def test_clipboard_restore_reports_temporarily_busy_clipboard(self):
        user32 = Mock()
        user32.GetClipboardSequenceNumber.return_value = 42

        with (
            patch(
                "context_palette.windows_credentials.ctypes.WinDLL",
                return_value=user32,
            ),
            patch(
                "context_palette.windows_credentials._open_clipboard",
                side_effect=CredentialAccessError("busy"),
            ),
        ):
            restored = restore_clipboard_text_if_unchanged(
                42,
                ClipboardTextSnapshot("previous"),
            )

        self.assertIsNone(restored)
        user32.EmptyClipboard.assert_not_called()

    def test_clipboard_restore_replaces_protected_item_with_previous_text(self):
        user32 = Mock()
        kernel32 = Mock()
        user32.GetClipboardSequenceNumber.return_value = 42
        user32.EmptyClipboard.return_value = True

        def win_dll(name: str, **_kwargs: object) -> Mock:
            return user32 if name == "User32.dll" else kernel32

        with (
            patch(
                "context_palette.windows_credentials.ctypes.WinDLL",
                side_effect=win_dll,
            ),
            patch("context_palette.windows_credentials._open_clipboard") as open_clipboard,
            patch("context_palette.windows_credentials._set_clipboard_data") as set_data,
        ):
            restored = restore_clipboard_text_if_unchanged(
                42,
                ClipboardTextSnapshot("previous"),
            )

        self.assertTrue(restored)
        open_clipboard.assert_called_once_with(user32)
        user32.EmptyClipboard.assert_called_once_with()
        set_data.assert_called_once_with(
            CF_UNICODETEXT,
            "previous\0".encode("utf-16-le"),
            user32,
            kernel32,
        )
        user32.CloseClipboard.assert_called_once_with()

    def test_clipboard_restore_clears_when_prior_clipboard_had_no_text(self):
        user32 = Mock()
        user32.GetClipboardSequenceNumber.return_value = 42
        user32.EmptyClipboard.return_value = True

        with (
            patch(
                "context_palette.windows_credentials.ctypes.WinDLL",
                return_value=user32,
            ),
            patch("context_palette.windows_credentials._open_clipboard"),
        ):
            restored = restore_clipboard_text_if_unchanged(
                42,
                ClipboardTextSnapshot(),
            )

        self.assertTrue(restored)
        user32.EmptyClipboard.assert_called_once_with()
        user32.SetClipboardData.assert_not_called()
        user32.CloseClipboard.assert_called_once_with()

    def test_exact_generic_credential_is_preferred(self):
        expected = CredentialSecret(username="generic-user", password="secret")

        with patch(
            "context_palette.windows_credentials._read_credential_type",
            return_value=expected,
        ) as read_type:
            actual = read_windows_credential(" ContextPalette/login ")

        self.assertEqual(actual, expected)
        read_type.assert_called_once_with("ContextPalette/login", CRED_TYPE_GENERIC)

    def test_windows_domain_credential_is_used_when_generic_is_absent(self):
        expected = CredentialSecret(username="domain-user", password="secret")

        with patch(
            "context_palette.windows_credentials._read_credential_type",
            side_effect=(_CredentialNotFound(), expected),
        ) as read_type:
            actual = read_windows_credential("oracle-pc17")

        self.assertEqual(actual, expected)
        self.assertEqual(
            read_type.call_args_list,
            [
                call("oracle-pc17", CRED_TYPE_GENERIC),
                call("oracle-pc17", CRED_TYPE_DOMAIN_PASSWORD),
            ],
        )

    def test_missing_supported_credential_types_report_clear_error(self):
        with (
            patch(
                "context_palette.windows_credentials._read_credential_type",
                side_effect=_CredentialNotFound,
            ),
            self.assertRaisesRegex(
                CredentialAccessError,
                "No generic or Windows credential",
            ),
        ):
            read_windows_credential("missing")


if __name__ == "__main__":
    unittest.main()
