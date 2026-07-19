from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.windows_credentials import (
    CRED_TYPE_DOMAIN_PASSWORD,
    CRED_TYPE_GENERIC,
    CredentialAccessError,
    CredentialSecret,
    _CredentialNotFound,
    decode_credential_blob,
    read_windows_credential,
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
