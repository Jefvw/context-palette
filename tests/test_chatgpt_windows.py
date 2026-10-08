import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from context_palette.chatgpt_http import ChatGPTError
from context_palette.chatgpt_windows import protect_credentials, unprotect_credentials, verify_rs256


@unittest.skipUnless(sys.platform == "win32", "Windows DPAPI and CNG")
class ChatGPTWindowsTests(unittest.TestCase):
    def test_dpapi_round_trip_with_synthetic_data_and_tamper_rejection(self):
        plaintext = b'{"access_token":"synthetic-test-only-token"}'
        protected = protect_credentials(plaintext)
        self.assertNotIn(plaintext, protected)
        self.assertNotIn(b"synthetic-test-only-token", protected)
        self.assertEqual(unprotect_credentials(protected), plaintext)
        with self.assertRaises(ChatGPTError):
            unprotect_credentials(protected[:20])

    def test_real_cng_accepts_signature_and_rejects_forged_message(self):
        # This creates a disposable key solely for a public test vector. It does
        # not read files, certificates, credentials, browser state or profiles.
        script = """
        $rsa = [System.Security.Cryptography.RSACryptoServiceProvider]::new(2048)
        $rsa.PersistKeyInCsp = $false
        $message = [System.Text.Encoding]::UTF8.GetBytes('Context Palette synthetic CNG test')
        $signature = $rsa.SignData($message, 'SHA256')
        $parameters = $rsa.ExportParameters($false)
        @{n=[Convert]::ToBase64String($parameters.Modulus); e=[Convert]::ToBase64String($parameters.Exponent); s=[Convert]::ToBase64String($signature)} | ConvertTo-Json -Compress
        $rsa.Dispose()
        """
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, "Synthetic RSA fixture generation failed.")
        vector = json.loads(result.stdout.decode("utf-8-sig"))
        modulus, exponent, signature = (base64.b64decode(vector[name]) for name in ("n", "e", "s"))
        self.assertTrue(verify_rs256(modulus, exponent, b"Context Palette synthetic CNG test", signature))
        self.assertFalse(verify_rs256(modulus, exponent, b"Forged message", signature))
        self.assertFalse(verify_rs256(modulus, exponent, b"Context Palette synthetic CNG test", b"x" * len(signature)))


if __name__ == "__main__":
    unittest.main()
