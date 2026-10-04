"""Synthetic Windows process tests: no OneNote, COM, or engine invocation."""

import ctypes
from ctypes import wintypes as w
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from context_palette import onenote_process as transport


@unittest.skipUnless(sys.platform == "win32", "Windows native process ownership")
class OwnedProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="palette café transport ")
        self.root = Path(self.temporary.name)
        self.launcher = self.root / "python-onenote.bat"
        self.script = self.root / "synthetic.py"
        transport._cleanup_uncertain.clear()

    def tearDown(self):
        self.assertFalse(transport._cleanup_uncertain.is_set(), "synthetic cleanup uncertain")
        self.temporary.cleanup()

    def launcher_for(self, script):
        self.script.write_text(script, encoding="utf-8")
        # Use the real interpreter rather than the virtual-env redirector.
        self.launcher.write_text(
            '@echo off\r\n"' + sys._base_executable + '" "%~dp0synthetic.py" %*\r\n'
            'exit /b %errorlevel%\r\n', encoding="utf-8")

    def run_request(self, request=b"{}", timeout=5, cancel=None):
        return transport.run_owned_request(self.launcher, request, timeout=timeout,
                                            cancel_event=cancel or threading.Event())

    def run_write_request(self, request=b"{}", timeout=5, cancel=None):
        return transport.run_owned_write_request(
            self.launcher, request, timeout=timeout,
            cancel_event=cancel or threading.Event(),
        )

    def assert_code(self, code, **kwargs):
        with self.assertRaises(transport.OwnedProcessError) as caught:
            self.run_request(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)
        return caught.exception

    def assert_write_code(self, code, **kwargs):
        with self.assertRaises(transport.OwnedProcessError) as caught:
            self.run_write_request(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)
        return caught.exception

    def test_utf8_spaces_and_literal_shell_characters_stay_in_stdin(self):
        self.launcher_for("import sys\nassert sys.argv[1:] == ['execute','--request','-']\n"
                          "sys.stdout.buffer.write(sys.stdin.buffer.read())\n")
        request = '{"query":"café 東京 %PATH% & | ^ !", "id":"opaque"}\n'.encode("utf-8")
        result = self.run_request(request)
        self.assertEqual(result, transport.ProcessResult(request, 0))

    def test_nonzero_retains_json_for_protocol_validation_and_discards_stderr(self):
        self.launcher_for("import sys\nsys.stderr.write('private diagnostic')\n"
                          "sys.stdout.buffer.write(b'{\"status\":\"error\"}\\n')\n"
                          "sys.exit(6)\n")
        self.assertEqual(self.run_request(),
                         transport.ProcessResult(b'{"status":"error"}\n', 6))

    def test_concurrent_stream_drain_and_large_input(self):
        self.launcher_for("import sys\nsys.stdout.buffer.write(b'o'*200000)\n"
                          "sys.stdout.buffer.flush()\nsys.stderr.buffer.write(b'e'*60000)\n"
                          "sys.stderr.buffer.flush()\nraw=sys.stdin.buffer.read()\n"
                          "sys.stdout.buffer.write(str(len(raw)).encode())\n")
        result = self.run_request(b"x" * 900000)
        self.assertEqual(result.stdout, b"o" * 200000 + b"900000")

    def test_exact_stream_limits_are_accepted(self):
        self.launcher_for("import sys\nsys.stdin.buffer.read()\n"
                          f"sys.stderr.buffer.write(b'e'*{transport.MAX_STDERR_BYTES})\n"
                          f"sys.stdout.buffer.write(b'o'*{transport.MAX_STDOUT_BYTES})\n")
        self.assertEqual(len(self.run_request().stdout), transport.MAX_STDOUT_BYTES)

    def test_oversized_stdout_and_stderr(self):
        for stream, limit in (("stdout", transport.MAX_STDOUT_BYTES),
                              ("stderr", transport.MAX_STDERR_BYTES)):
            with self.subTest(stream=stream):
                self.launcher_for(f"import sys,time\nsys.{stream}.buffer.write(b'x'*{limit+1})\n"
                                  f"sys.{stream}.buffer.flush()\ntime.sleep(60)\n")
                self.assert_code("transport.oversized")

    def test_timeout_includes_blocked_input_writer(self):
        self.launcher_for("import time\ntime.sleep(60)\n")
        started = time.monotonic()
        self.assert_code("transport.timeout", request=b"x" * 900000, timeout=0.3)
        self.assertLess(time.monotonic() - started, 3)

    def test_cancellation_includes_blocked_input_writer(self):
        self.launcher_for("import time\ntime.sleep(60)\n")
        event = threading.Event()
        timer = threading.Timer(0.3, event.set)
        timer.start()
        try:
            started = time.monotonic()
            self.assert_code("transport.cancelled", request=b"x" * 900000, cancel=event)
            self.assertLess(time.monotonic() - started, 3)
        finally:
            timer.join()

    def test_write_allows_45_second_outer_timeout_while_read_rejects_it(self):
        self.launcher_for("import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n")
        request = b'{"operation":"execute_create_desktop_page"}'
        self.assertEqual(
            self.run_write_request(request, timeout=45),
            transport.ProcessResult(request, 0),
        )
        error = self.assert_code("transport.launch", request=request, timeout=45)
        self.assertFalse(error.dispatched)
        self.assertIsNone(error.response)

    def test_write_cancel_after_input_is_possibly_dispatched_and_cleans_tree(self):
        self.launcher_for(
            "import sys,time\nfrom pathlib import Path\n"
            "sys.stdin.buffer.read()\n"
            "Path(__file__).with_suffix('.received').touch()\n"
            "time.sleep(60)\n"
        )
        event = threading.Event()

        def cancel_after_input():
            deadline = time.monotonic() + 3
            marker = self.script.with_suffix(".received")
            while time.monotonic() < deadline and not marker.exists():
                time.sleep(0.01)
            event.set()

        helper = threading.Thread(target=cancel_after_input)
        helper.start()
        try:
            error = self.assert_write_code("transport.cancelled", cancel=event)
            self.assertTrue(error.dispatched)
            self.assertIsNone(error.response)
        finally:
            helper.join()

    def test_cancelled_before_launch_creates_no_process(self):
        event = threading.Event()
        event.set()
        with patch.object(transport, "_kernel") as kernel:
            self.assert_code("transport.cancelled", cancel=event)
        kernel.assert_not_called()

    def descendant_script(self, parent_sleep):
        self.launcher_for(
            "import subprocess,sys,time\nfrom pathlib import Path\n"
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
            "Path(__file__).with_suffix('.pid').write_text(str(child.pid))\n"
            "sys.stdout.buffer.write(b'ok');sys.stdout.buffer.flush()\n"
            + ("time.sleep(60)\n" if parent_sleep else ""))

    def assert_descendant_gone(self):
        pid = int(self.script.with_suffix(".pid").read_text())
        kernel = transport._kernel()
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        handle = kernel.OpenProcess(0x100000, False, pid)
        if handle:
            try:
                self.assertEqual(kernel.WaitForSingleObject(handle, 0), 0)
            finally:
                kernel.CloseHandle(handle)

    def test_success_cleans_detached_descendants_too(self):
        self.descendant_script(False)
        self.assertEqual(self.run_request().stdout, b"ok")
        self.assert_descendant_gone()

    def test_timeout_cleans_descendants(self):
        self.descendant_script(True)
        self.assert_code("transport.timeout", timeout=1)
        self.assert_descendant_gone()

    def test_cancellation_cleans_descendants(self):
        self.descendant_script(True)
        event = threading.Event()
        timer = threading.Timer(1, event.set)
        timer.start()
        try:
            self.assert_code("transport.cancelled", cancel=event)
            self.assert_descendant_gone()
        finally:
            timer.join()

    def test_assignment_failure_never_resumes_launcher(self):
        self.launcher_for("from pathlib import Path\nPath(__file__).with_suffix('.ran').touch()\n")
        kernel = transport._kernel()
        with patch.object(kernel, "AssignProcessToJobObject", return_value=0), \
                patch.object(kernel, "ResumeThread", wraps=kernel.ResumeThread) as resume, \
                patch.object(transport, "_kernel", return_value=kernel):
            self.assert_code("transport.launch")
        resume.assert_not_called()
        self.assertFalse(self.script.with_suffix(".ran").exists())

    def test_cancellation_during_assignment_never_resumes_launcher(self):
        self.launcher_for("from pathlib import Path\nPath(__file__).with_suffix('.ran').touch()\n")
        kernel = transport._kernel()
        original_assign = kernel.AssignProcessToJobObject
        event = threading.Event()

        def assign(job, process):
            result = original_assign(job, process)
            event.set()
            return result

        with patch.object(kernel, "AssignProcessToJobObject", side_effect=assign), \
                patch.object(kernel, "ResumeThread", wraps=kernel.ResumeThread) as resume, \
                patch.object(transport, "_kernel", return_value=kernel):
            self.assert_code("transport.cancelled", cancel=event)
        resume.assert_not_called()
        self.assertFalse(self.script.with_suffix(".ran").exists())

    def test_native_cleanup_failure_disables_session_and_prevents_relaunch(self):
        self.launcher_for("pass\n")
        kernel = transport._kernel()
        try:
            with patch.object(kernel, "TerminateJobObject", return_value=0), \
                    patch.object(transport, "_kernel", return_value=kernel):
                self.assert_code("transport.cleanup")
            with patch.object(transport, "_kernel") as next_kernel:
                self.assert_code("transport.cleanup")
            next_kernel.assert_not_called()
        finally:
            transport._cleanup_uncertain.clear()

    def test_write_cleanup_failure_retains_complete_terminal_response(self):
        response = b'{"status":"error","result":"partial"}\n'
        self.launcher_for(
            "import sys\n"
            "sys.stdin.buffer.read()\n"
            f"sys.stdout.buffer.write({response!r})\n"
        )
        kernel = transport._kernel()
        try:
            with patch.object(kernel, "TerminateJobObject", return_value=0), \
                    patch.object(transport, "_kernel", return_value=kernel):
                error = self.assert_write_code("transport.cleanup")
            self.assertTrue(error.dispatched)
            self.assertEqual(error.response, transport.ProcessResult(response, 0))
            self.assertTrue(transport._cleanup_uncertain.is_set())
            with patch.object(transport, "_kernel") as next_kernel:
                blocked = self.assert_write_code("transport.cleanup")
            self.assertFalse(blocked.dispatched)
            self.assertIsNone(blocked.response)
            next_kernel.assert_not_called()
        finally:
            transport._cleanup_uncertain.clear()

    def test_repeated_success_and_failures_do_not_leak_handles(self):
        self.launcher_for("import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n")
        kernel = transport._kernel()
        kernel.GetCurrentProcess.restype = w.HANDLE
        kernel.GetProcessHandleCount.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        kernel.GetProcessHandleCount.restype = w.BOOL

        def count():
            value = w.DWORD()
            self.assertTrue(kernel.GetProcessHandleCount(kernel.GetCurrentProcess(),
                                                          ctypes.byref(value)))
            return value.value

        self.run_request()  # Warm up Python thread state before measuring.
        before = count()
        for _ in range(8):
            self.run_request()
        self.launcher_for("import time\ntime.sleep(60)\n")
        for _ in range(3):
            self.assert_code("transport.timeout", timeout=0.1)
        self.assertLessEqual(count(), before + 2)

    def test_launcher_validation_rejects_shell_metacharacters_and_other_names(self):
        kernel = transport._kernel()
        for name in ("wrong.bat", "python-onenote.bat & echo x", "python-onenote%X%.bat"):
            with self.subTest(name=name), self.assertRaises(transport.OwnedProcessError):
                transport._launcher_command(self.root / name, kernel)
        with self.assertRaises(transport.OwnedProcessError):
            transport._launcher_command(Path("python-onenote.bat"), kernel)
        self.launcher_for("pass\n")
        bad_root = self.root / "unsafe&directory"
        bad_root.mkdir()
        bad = bad_root / "python-onenote.bat"
        bad.write_text("@echo off\n")
        with self.assertRaises(transport.OwnedProcessError):
            transport._launcher_command(bad, kernel)


class TransportValidationTests(unittest.TestCase):
    def test_safe_error_does_not_echo_unrecognized_code(self):
        self.assertEqual(str(transport.OwnedProcessError("private query")), "transport.launch")

    def test_uncertain_cleanup_refuses_future_launches(self):
        transport._cleanup_uncertain.set()
        try:
            with patch.object(transport, "_kernel") as kernel:
                with self.assertRaises(transport.OwnedProcessError) as caught:
                    transport.run_owned_request(Path("python-onenote.bat"), b"{}", timeout=10,
                                                 cancel_event=threading.Event())
            self.assertEqual(caught.exception.code, "transport.cleanup")
            kernel.assert_not_called()
        finally:
            transport._cleanup_uncertain.clear()

    def test_invalid_timeout_and_request_fail_before_launch(self):
        for timeout in (True, 0, -1, 31, 10**1000, float("nan"), float("inf"), "10"):
            with self.subTest(timeout=timeout), self.assertRaises(transport.OwnedProcessError):
                transport.run_owned_request(Path("python-onenote.bat"), b"{}", timeout=timeout,
                                             cancel_event=threading.Event())

    def test_write_timeout_validation_is_separate_and_bounded(self):
        for timeout in (True, 0, -1, 46, 10**1000, float("nan"), float("inf"), "45"):
            with self.subTest(timeout=timeout), self.assertRaises(transport.OwnedProcessError) as caught:
                transport.run_owned_write_request(
                    Path("python-onenote.bat"), b"{}", timeout=timeout,
                    cancel_event=threading.Event(),
                )
            self.assertFalse(caught.exception.dispatched)
            self.assertIsNone(caught.exception.response)


if __name__ == "__main__":
    unittest.main()
