from __future__ import annotations

import ctypes
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette import onenote_session as session


class FakeKernel32:
    """Only synthetic process metadata; never calls a native Windows API."""

    def __init__(self, captures=None):
        self.captures = captures if captures is not None else [[], []]
        self.index = -1
        self.position = 0
        self.error = 18
        self.closed = []
        self.opened = []
        self.sessions = {999: 7}
        self.times = {}
        self.fail = None

    def GetCurrentProcessId(self):
        return 999

    def ProcessIdToSessionId(self, pid, output):
        if self.fail == "session" or (self.fail == "candidate_session" and pid != 999):
            return False
        output._obj.value = self.sessions.get(pid, 7)
        return True

    def CreateToolhelp32Snapshot(self, flags, pid):
        if self.fail == "snapshot":
            return session._INVALID_HANDLE_VALUE
        if flags != 2 or pid != 0:
            raise AssertionError("Unexpected snapshot scope")
        self.index += 1
        return 1000 + self.index

    def _entry(self, output):
        entries = self.captures[self.index]
        if self.position == len(entries):
            self.error = 5 if self.fail == "enumeration" else 18
            return False
        pid, name = entries[self.position]
        output._obj.th32ProcessID = pid
        output._obj.szExeFile = name
        self.position += 1
        return True

    def Process32FirstW(self, snapshot, output):
        if output._obj.dwSize != ctypes.sizeof(session._ProcessEntry):
            raise AssertionError("Missing structure size")
        self.position = 0
        return self._entry(output)

    def Process32NextW(self, snapshot, output):
        return self._entry(output)

    def OpenProcess(self, access, inherit, pid):
        self.opened.append((access, inherit, pid))
        return None if self.fail == "open" else pid + 2000

    def GetProcessTimes(self, handle, creation, exit_time, kernel_time, user_time):
        if self.fail == "times":
            return False
        timestamp = self.times.get(handle - 2000, 0x12345678ABCDEF01)
        if isinstance(timestamp, list):
            timestamp = timestamp.pop(0)
        creation._obj.dwLowDateTime = timestamp & 0xFFFFFFFF
        creation._obj.dwHighDateTime = timestamp >> 32
        return True

    def WaitForSingleObject(self, handle, milliseconds):
        if milliseconds != 0:
            raise AssertionError("Process wait must never block")
        return {"exited": 0, "wait": 0xFFFFFFFF}.get(self.fail, 258)

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return self.fail != "close"


class OneNoteSessionTests(unittest.TestCase):
    def capture(self, fake):
        with patch.object(session.os, "name", "nt"), patch.object(
            session, "_load_kernel32", return_value=fake
        ), patch.object(session.ctypes, "get_last_error", side_effect=lambda: fake.error, create=True):
            return session.capture_session()

    def test_import_performs_no_windows_discovery(self):
        specification = importlib.util.spec_from_file_location(
            "isolated_onenote_session", ROOT / "src" / "context_palette" / "onenote_session.py"
        )
        isolated = importlib.util.module_from_spec(specification)
        with patch.object(session.ctypes, "WinDLL", create=True) as loader:
            specification.loader.exec_module(isolated)
        loader.assert_not_called()

    def test_empty_snapshot_means_not_running(self):
        fake = FakeKernel32()
        self.assertEqual(self.capture(fake), ())
        self.assertEqual(fake.opened, [])
        self.assertEqual(fake.closed, [1000, 1001])

    def test_exact_case_insensitive_name_and_current_session_only(self):
        entries = [(42, "OneNote.exe"), (21, "ONENOTE.EXE"), (30, "ONENOTE.EXE"),
                   (12, "ONENOTEIM.EXE"), (13, "ONENOTE.EXE.bak"), (14, "other.exe")]
        fake = FakeKernel32([entries, list(reversed(entries))])
        fake.sessions[30] = 8
        fake.times.update({21: 0x123456789ABCDEF0, 42: 0xABCDEF0012345678})
        self.assertEqual(self.capture(fake), ((21, fake.times[21]), (42, fake.times[42])))
        self.assertEqual([call[2] for call in fake.opened], [42, 21, 21, 42])
        self.assertTrue(all(access == 0x101000 and not inherit for access, inherit, _ in fake.opened))
        self.assertEqual(len(fake.closed), 6)

    def test_process_exit_restart_and_addition_invalidate_capture(self):
        for captures in (
            [[(42, "ONENOTE.EXE")], []],
            [[(42, "ONENOTE.EXE")], [(43, "ONENOTE.EXE")]],
            [[], [(42, "ONENOTE.EXE")]],
            [[(42, "ONENOTE.EXE")], [(42, "ONENOTE.EXE"), (43, "ONENOTE.EXE")]],
            [[(42, "ONENOTE.EXE")], [(42, "other.exe")]],
        ):
            with self.subTest(captures=captures), self.assertRaises(session.SessionError):
                self.capture(FakeKernel32(captures))

    def test_pid_reuse_with_different_creation_time_invalidates_capture(self):
        fake = FakeKernel32([[(42, "ONENOTE.EXE")]] * 2)
        fake.times[42] = [100, 200]
        with self.assertRaises(session.SessionError):
            self.capture(fake)

    def test_discovery_failures_are_generic_and_close_acquired_handles(self):
        for failure in ("session", "candidate_session", "snapshot", "enumeration", "open", "times", "exited", "wait", "close"):
            with self.subTest(failure=failure):
                fake = FakeKernel32([[(42, "ONENOTE.EXE")]] * 2)
                fake.fail = failure
                with self.assertRaises(session.SessionError) as caught:
                    self.capture(fake)
                self.assertEqual(str(caught.exception), session._ERROR_MESSAGE)
                self.assertEqual(repr(caught.exception), f"SessionError({session._ERROR_MESSAGE!r})")
                if failure in ("candidate_session", "enumeration", "open", "times", "exited", "wait", "close"):
                    self.assertIn(1000, fake.closed)
                if failure in ("times", "exited", "wait", "close"):
                    self.assertIn(2042, fake.closed)

    def test_zero_creation_time_and_duplicate_pid_deny_readiness(self):
        fake = FakeKernel32([[(42, "ONENOTE.EXE")]] * 2)
        fake.times[42] = 0
        with self.assertRaises(session.SessionError):
            self.capture(fake)
        fake = FakeKernel32([[(42, "ONENOTE.EXE"), (42, "ONENOTE.EXE")]] * 2)
        with self.assertRaises(session.SessionError):
            self.capture(fake)

    def test_unsupported_platform_does_not_load_windows_api(self):
        with patch.object(session.os, "name", "posix"), patch.object(session, "_load_kernel32") as loader:
            with self.assertRaises(session.SessionError):
                session.capture_session()
        loader.assert_not_called()

    def test_unexpected_native_details_do_not_escape(self):
        private_text = "private executable metadata 424242"
        with patch.object(session.os, "name", "nt"), patch.object(
            session, "_load_kernel32", side_effect=OSError(private_text)
        ):
            with self.assertRaises(session.SessionError) as caught:
                session.capture_session()
        self.assertNotIn(private_text, str(caught.exception))
        self.assertNotIn(private_text, repr(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_native_signatures_use_pointer_sized_handles(self):
        native = Mock()
        with patch.object(session.ctypes, "WinDLL", return_value=native, create=True):
            self.assertIs(session._load_kernel32(), native)
        self.assertIs(native.CreateToolhelp32Snapshot.restype, session.wintypes.HANDLE)
        self.assertIs(native.OpenProcess.restype, session.wintypes.HANDLE)
        self.assertEqual(native.CloseHandle.argtypes, [session.wintypes.HANDLE])


if __name__ == "__main__":
    unittest.main()
