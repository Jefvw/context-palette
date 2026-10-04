"""Bounded, private Windows transport for the optional OneNote engine.

The launcher is created suspended, assigned to a non-breakaway kill-on-close
Job Object, then resumed. Only that job is terminated; an existing OneNote
application is never a target. No request, response, or stderr is logged.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass, field
import math
from pathlib import Path
import sys
import threading
import time

MAX_REQUEST_BYTES = MAX_STDOUT_BYTES = 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024
_CLEANUP_SECONDS = 2.0
_cleanup_uncertain = threading.Event()
_CODES = frozenset({"transport.cancelled", "transport.timeout", "transport.oversized",
                    "transport.launch", "transport.nonzero", "transport.cleanup"})


class OwnedProcessError(Exception):
    """Only stable, non-sensitive diagnostics cross the transport boundary."""

    def __init__(self, code: str, *, dispatched: bool = False,
                 response: ProcessResult | None = None):
        self.code = code if code in _CODES else "transport.launch"
        self.dispatched = bool(dispatched)
        self.response = response if isinstance(response, ProcessResult) else None
        super().__init__(self.code)


@dataclass(frozen=True)
class ProcessResult:
    stdout: bytes = field(repr=False)
    returncode: int


class _Security(ctypes.Structure):
    _fields_ = [("length", w.DWORD), ("descriptor", w.LPVOID), ("inherit", w.BOOL)]


class _Startup(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR),
                ("title", w.LPWSTR), ("x", w.DWORD), ("y", w.DWORD),
                ("width", w.DWORD), ("height", w.DWORD), ("chars_x", w.DWORD),
                ("chars_y", w.DWORD), ("fill", w.DWORD), ("flags", w.DWORD),
                ("show", w.WORD), ("reserved_size", w.WORD),
                ("reserved_bytes", w.LPVOID), ("stdin", w.HANDLE),
                ("stdout", w.HANDLE), ("stderr", w.HANDLE)]


class _StartupEx(ctypes.Structure):
    _fields_ = [("startup", _Startup), ("attributes", w.LPVOID)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE),
                ("pid", w.DWORD), ("tid", w.DWORD)]


class _BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", w.DWORD), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_limit", w.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", w.DWORD),
                ("scheduling", w.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ("read", "write", "other", "read_bytes", "write_bytes", "other_bytes")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", _BasicLimits), ("io", _IoCounters),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [("user_time", ctypes.c_longlong), ("kernel_time", ctypes.c_longlong),
                ("period_user", ctypes.c_longlong), ("period_kernel", ctypes.c_longlong),
                ("faults", w.DWORD), ("total", w.DWORD), ("active", w.DWORD),
                ("terminated", w.DWORD)]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    p = w.LPVOID
    for name, args, result in (
        ("CreateJobObjectW", [p, w.LPCWSTR], w.HANDLE),
        ("SetInformationJobObject", [w.HANDLE, ctypes.c_int, p, w.DWORD], w.BOOL),
        ("AssignProcessToJobObject", [w.HANDLE, w.HANDLE], w.BOOL),
        ("TerminateJobObject", [w.HANDLE, w.UINT], w.BOOL),
        ("QueryInformationJobObject", [w.HANDLE, ctypes.c_int, p, w.DWORD, p], w.BOOL),
        ("CreatePipe", [p, p, p, w.DWORD], w.BOOL),
        ("SetHandleInformation", [w.HANDLE, w.DWORD, w.DWORD], w.BOOL),
        ("InitializeProcThreadAttributeList", [p, w.DWORD, w.DWORD, p], w.BOOL),
        ("UpdateProcThreadAttribute", [p, w.DWORD, ctypes.c_size_t, p,
                                       ctypes.c_size_t, p, p], w.BOOL),
        ("DeleteProcThreadAttributeList", [p], None),
        ("CreateProcessW", [w.LPCWSTR, w.LPWSTR, p, p, w.BOOL, w.DWORD,
                             p, w.LPCWSTR, p, p], w.BOOL),
        ("ResumeThread", [w.HANDLE], w.DWORD),
        ("TerminateProcess", [w.HANDLE, w.UINT], w.BOOL),
        ("WaitForSingleObject", [w.HANDLE, w.DWORD], w.DWORD),
        ("GetExitCodeProcess", [w.HANDLE, p], w.BOOL),
        ("OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        ("ReadFile", [w.HANDLE, p, w.DWORD, p, p], w.BOOL),
        ("WriteFile", [w.HANDLE, p, w.DWORD, p, p], w.BOOL),
        ("CloseHandle", [w.HANDLE], w.BOOL),
        ("GetSystemDirectoryW", [w.LPWSTR, w.UINT], w.UINT),
    ):
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    return kernel


def _require(value):
    if not value:
        raise OwnedProcessError("transport.launch")
    return value


def _launcher_command(launcher: Path, kernel):
    if (not isinstance(launcher, Path) or not launcher.is_absolute()
            or launcher.name.lower() != "python-onenote.bat"
            or any(c in str(launcher) for c in '\"%!&|<>^\r\n\x00')
            or not launcher.is_file()):
        raise OwnedProcessError("transport.launch")
    buffer = ctypes.create_unicode_buffer(32768)
    size = kernel.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < size < len(buffer):
        raise OwnedProcessError("transport.launch")
    application = str(Path(buffer.value) / "cmd.exe")
    return application, f'"{application}" /d /s /c ""{launcher}" execute --request -"'


class _OwnedProcess:
    """Native handles stay owned until verified release, including launch failures."""

    def __init__(self, kernel):
        self.kernel = kernel
        self.handles = set()
        self.job = self.process = self.thread = None
        self.stdin = self.stdout = self.stderr = None
        self.assigned = False

    def _own(self, handle):
        self.handles.add(handle)
        return handle

    def _close(self, handle):
        if handle in self.handles:
            if not self.kernel.CloseHandle(handle):
                raise OwnedProcessError("transport.cleanup")
            self.handles.remove(handle)

    def _pipe(self, input_pipe=False):
        read, write = w.HANDLE(), w.HANDLE()
        security = _Security(ctypes.sizeof(_Security), None, True)
        _require(self.kernel.CreatePipe(ctypes.byref(read), ctypes.byref(write),
                                        ctypes.byref(security), 0))
        self._own(read.value)
        self._own(write.value)
        parent = write.value if input_pipe else read.value
        _require(self.kernel.SetHandleInformation(parent, 1, 0))
        return parent, read.value if input_pipe else write.value

    def launch(self, application, command, release_check):
        self.job = self._own(_require(self.kernel.CreateJobObjectW(None, None)))
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE, no breakaway.
        _require(self.kernel.SetInformationJobObject(
            self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        self.stdin, child_in = self._pipe(True)
        self.stdout, child_out = self._pipe()
        self.stderr, child_err = self._pipe()
        # Explicit inheritance excludes every unrelated host handle.
        size = ctypes.c_size_t()
        self.kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attributes = ctypes.create_string_buffer(size.value)
        _require(self.kernel.InitializeProcThreadAttributeList(
            attributes, 1, 0, ctypes.byref(size)))
        try:
            inherited = (w.HANDLE * 3)(child_in, child_out, child_err)
            _require(self.kernel.UpdateProcThreadAttribute(
                attributes, 0, 0x20002, inherited, ctypes.sizeof(inherited), None, None))
            startup = _StartupEx()
            startup.startup.cb = ctypes.sizeof(startup)
            startup.startup.flags = 0x100  # STARTF_USESTDHANDLES
            startup.startup.stdin = child_in
            startup.startup.stdout = child_out
            startup.startup.stderr = child_err
            startup.attributes = ctypes.cast(attributes, w.LPVOID)
            info = _ProcessInfo()
            _require(self.kernel.CreateProcessW(
                application, ctypes.create_unicode_buffer(command), None, None, True,
                0x08080004, None, None, ctypes.byref(startup), ctypes.byref(info)))
            # CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED.
            self.process, self.thread = self._own(info.process), self._own(info.thread)
        finally:
            self.kernel.DeleteProcThreadAttributeList(attributes)
        _require(self.kernel.AssignProcessToJobObject(self.job, self.process))
        self.assigned = True
        for handle in (child_in, child_out, child_err):
            self._close(handle)
        release_check()
        if self.kernel.ResumeThread(self.thread) == 0xFFFFFFFF:
            raise OwnedProcessError("transport.launch")
        self._close(self.thread)

    def poll(self):
        status = self.kernel.WaitForSingleObject(self.process, 0)
        if status == 258:  # WAIT_TIMEOUT
            return None
        if status != 0:
            raise OwnedProcessError("transport.launch")
        code = w.DWORD()
        _require(self.kernel.GetExitCodeProcess(self.process, ctypes.byref(code)))
        return code.value

    def cleanup(self, exchange):
        failed = False
        deadline = time.monotonic() + _CLEANUP_SECONDS
        try:
            members = []
            try:
                members = self._member_handles() if self.job else []
            except Exception:
                failed = True
            # Enumeration failure must not bypass owned-job termination.
            if self.job and not self.kernel.TerminateJobObject(self.job, 1):
                failed = True
            if self.process and not self.assigned:
                # Assignment failed: the still-suspended launcher has never run.
                if not self.kernel.TerminateProcess(self.process, 1):
                    failed = True
            if self.process and self.kernel.WaitForSingleObject(
                    self.process, max(0, int((deadline - time.monotonic()) * 1000))) != 0:
                failed = True
            if self.job:
                while True:
                    accounting = _Accounting()
                    if not self.kernel.QueryInformationJobObject(
                            self.job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
                        failed = True
                        break
                    if accounting.active == 0:
                        break
                    if time.monotonic() >= deadline:
                        failed = True
                        break
                    time.sleep(0.01)
            # ActiveProcesses can reach zero before individual process handles
            # become signaled. Verify observed descendants have fully exited.
            for handle in members:
                if self.kernel.WaitForSingleObject(
                        handle, max(0, int((deadline - time.monotonic()) * 1000))) != 0:
                    failed = True
        except Exception:
            failed = True
        finally:
            if exchange:
                for thread in exchange.threads:
                    thread.join(max(0, deadline - time.monotonic()))
                failed |= any(thread.is_alive() for thread in exchange.threads)
            # Native handles have no Python buffered-stream locks. Closing even
            # after a failed join avoids leaking handles; future calls fail closed.
            for handle in tuple(self.handles):
                try:
                    self._close(handle)
                except Exception:
                    failed = True
        if failed:
            _cleanup_uncertain.set()
            raise OwnedProcessError("transport.cleanup")

    def _member_handles(self):
        capacity = 64
        while capacity <= 65536:
            class ProcessIds(ctypes.Structure):
                _fields_ = [("assigned", w.DWORD), ("count", w.DWORD),
                            ("ids", ctypes.c_size_t * capacity)]

            ids = ProcessIds()
            if self.kernel.QueryInformationJobObject(
                    self.job, 3, ctypes.byref(ids), ctypes.sizeof(ids), None):
                members = []
                for pid in ids.ids[:ids.count]:
                    handle = self.kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE only.
                    if handle:
                        members.append(self._own(handle))
                    elif ctypes.get_last_error() != 87:  # Already-exited PID.
                        raise OwnedProcessError("transport.cleanup")
                return members
            if ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
                raise OwnedProcessError("transport.cleanup")
            capacity = max(capacity * 2, ids.assigned)
        raise OwnedProcessError("transport.cleanup")


class _Exchange:
    def __init__(self, process, request, release_check):
        self.process = process
        self.stdout = bytearray()
        self.failure = None
        self.dispatched = threading.Event()
        self.stdout_complete = threading.Event()
        self.release_check = release_check
        self.changed = threading.Event()
        self.lock = threading.Lock()
        self.threads = [
            threading.Thread(target=self._read, args=(process.stdout, MAX_STDOUT_BYTES, True),
                             daemon=True),
            threading.Thread(target=self._read, args=(process.stderr, MAX_STDERR_BYTES, False),
                             daemon=True),
            threading.Thread(target=self._write, args=(request,), daemon=True),
        ]

    def start(self):
        # Retain only successfully started threads if native thread creation fails.
        planned, self.threads = self.threads, []
        for thread in planned:
            thread.start()
            self.threads.append(thread)

    def _fail(self, code):
        with self.lock:
            if self.failure is None or code == "transport.oversized":
                self.failure = code
        self.changed.set()

    def _read(self, handle, limit, keep):
        size = 0
        buffer = ctypes.create_string_buffer(16384)
        try:
            while True:
                count = w.DWORD()
                if not self.process.kernel.ReadFile(handle, buffer, len(buffer),
                                                    ctypes.byref(count), None):
                    if ctypes.get_last_error() == 109:  # ERROR_BROKEN_PIPE is EOF.
                        if keep:
                            self.stdout_complete.set()
                        return
                    self._fail("transport.launch")
                    return
                if not count.value:
                    if keep:
                        self.stdout_complete.set()
                    return
                size += count.value
                if size > limit:
                    self._fail("transport.oversized")
                    return
                if keep:
                    self.stdout.extend(buffer.raw[:count.value])
        except OwnedProcessError as exc:
            self._fail(exc.code)
        except Exception:
            self._fail("transport.launch")

    def _write(self, request):
        try:
            # Once any input write can begin, cleanup may release a syntactically
            # complete request even if this thread does not observe full delivery.
            # Mark that conservative boundary before the first WriteFile call.
            self.release_check()
            self.dispatched.set()
            offset = 0
            while offset < len(request):
                chunk = request[offset:offset + 16384]
                count = w.DWORD()
                if not self.process.kernel.WriteFile(self.process.stdin, chunk, len(chunk),
                                                     ctypes.byref(count), None):
                    if ctypes.get_last_error() not in (109, 232):
                        self._fail("transport.launch")
                    return
                if not count.value:
                    self._fail("transport.launch")
                    return
                offset += count.value
        except OwnedProcessError as exc:
            self._fail(exc.code)
        except Exception:
            self._fail("transport.launch")
        finally:
            try:
                self.process._close(self.process.stdin)
            except Exception:
                self._fail("transport.cleanup")


def run_owned_request(launcher: Path, request: bytes, *, timeout: float,
                      cancel_event: threading.Event) -> ProcessResult:
    """Exchange JSON bytes; retain nonzero exits for the strict protocol layer.

    The monotonic deadline includes launch and input writing. Cleanup has a
    separate two-second ceiling. Uncertain cleanup disables this transport for
    the rest of the host session, rather than attempting another launch.
    """
    return _run_owned_request(
        launcher, request, timeout=timeout, cancel_event=cancel_event, maximum_timeout=30,
    )


def run_owned_write_request(launcher: Path, request: bytes, *, timeout: float,
                            cancel_event: threading.Event) -> ProcessResult:
    """Exchange one mutation request with a bounded 45-second host allowance.

    The engine owns its shorter mutation deadline.  As with the read transport,
    verified process-tree cleanup has a separate ceiling of two additional
    seconds.  Errors report whether request dispatch may have begun and can
    retain a complete terminal response when only cleanup failed.
    """
    return _run_owned_request(
        launcher, request, timeout=timeout, cancel_event=cancel_event, maximum_timeout=45,
    )


def _run_owned_request(launcher: Path, request: bytes, *, timeout: float,
                       cancel_event: threading.Event, maximum_timeout: float) -> ProcessResult:
    started = time.monotonic()
    if _cleanup_uncertain.is_set():
        raise OwnedProcessError("transport.cleanup")
    if (sys.platform != "win32" or type(timeout) not in (int, float)
            or not 0 < timeout <= maximum_timeout or not math.isfinite(timeout)
            or not isinstance(request, bytes) or not isinstance(cancel_event, threading.Event)):
        raise OwnedProcessError("transport.launch")
    if len(request) > MAX_REQUEST_BYTES:
        raise OwnedProcessError("transport.oversized")
    if cancel_event.is_set():
        raise OwnedProcessError("transport.cancelled")
    deadline = started + timeout
    process = exchange = None
    result = None
    error = None
    try:
        kernel = _kernel()
        application, command = _launcher_command(launcher, kernel)
        process = _OwnedProcess(kernel)
        def check_release():
            if cancel_event.is_set():
                raise OwnedProcessError("transport.cancelled")
            if time.monotonic() >= deadline:
                raise OwnedProcessError("transport.timeout")

        process.launch(application, command, check_release)
        exchange = _Exchange(process, request, check_release)
        exchange.start()
        while True:
            if cancel_event.is_set():
                raise OwnedProcessError("transport.cancelled")
            if time.monotonic() >= deadline:
                raise OwnedProcessError("transport.timeout")
            if exchange.failure:
                raise OwnedProcessError(exchange.failure)
            code = process.poll()
            if code is not None:
                result = code
                break
            exchange.changed.wait(min(0.01, max(0, deadline - time.monotonic())))
    except OwnedProcessError as exc:
        error = exc.code
    except Exception:
        error = "transport.launch"
    finally:
        if process:
            try:
                process.cleanup(exchange)
            except Exception:
                _cleanup_uncertain.set()
                error = "transport.cleanup"
    response = None
    if result is not None and exchange and exchange.stdout_complete.is_set():
        response = ProcessResult(bytes(exchange.stdout), result)
    dispatched = bool(exchange and exchange.dispatched.is_set())
    if exchange and exchange.failure == "transport.cleanup":
        _cleanup_uncertain.set()
        error = "transport.cleanup"
    elif not error and exchange and exchange.failure:
        error = exchange.failure
    if error:
        raise OwnedProcessError(error, dispatched=dispatched, response=response) from None
    return response
