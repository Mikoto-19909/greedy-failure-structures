"""Bound a local review step and terminate its descendants on exit or cancellation."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any


class WindowsJob:
    """Assign a suspended process before any child code can create descendants."""

    def __init__(self) -> None:
        if sys.platform != 'win32':
            raise OSError('Windows jobs require Windows')
        from ctypes import wintypes as w

        class Limits(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                        ('active', w.DWORD), ('affinity', ctypes.c_size_t),
                        ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

        class Extended(ctypes.Structure):
            _fields_ = [('basic', Limits), ('io', Counters), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def start(self, process: subprocess.Popen[bytes]) -> None:
        if sys.platform != 'win32':
            raise OSError('Windows jobs require Windows')
        handle = int(getattr(process, '_handle'))
        if not self.kernel.AssignProcessToJobObject(self.handle, handle):
            raise ctypes.WinError(ctypes.get_last_error())
        native = ctypes.WinDLL('ntdll')
        native.NtResumeProcess.argtypes = [ctypes.c_void_p]
        native.NtResumeProcess.restype = ctypes.c_long
        status = native.NtResumeProcess(handle)
        if status != 0:
            raise OSError(f'Cannot resume review process (NTSTATUS {status})')

    def close(self) -> None:
        if sys.platform != 'win32':
            return
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def run_step(argv: list[str], cwd: Path, env: dict[str, str], timeout: float,
             stdout: Path, stderr: Path, stdin: bytes = b'') -> dict[str, Any]:
    start = time.monotonic()
    job = WindowsJob() if os.name == 'nt' else None
    process: subprocess.Popen[bytes] | None = None
    state = 'finished'
    try:
        with stdout.open('wb') as out, stderr.open('wb') as err:
            process = subprocess.Popen(
                argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=out, stderr=err,
                start_new_session=os.name != 'nt',
                creationflags=(0x00000004 | 0x00000200) if job else 0,  # SUSPENDED | NEW_PROCESS_GROUP
            )
            if job:
                job.start(process)
            try:
                process.communicate(stdin, timeout=timeout)
            except subprocess.TimeoutExpired:
                state = 'timed_out'
            except KeyboardInterrupt:
                state = 'cancelled'
    finally:
        if job:
            job.close()
        elif process and sys.platform != 'win32':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process and process.poll() is None:
            process.kill()  # Also handles failure to attach a suspended Windows child.
            process.communicate(timeout=10)
    return {'argv': argv, 'state': state, 'exit_code': process.returncode if process else None,
            'seconds': round(time.monotonic() - start, 3)}
