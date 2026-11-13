"""Cancellable owned conversion processes with live, retained logs."""

import ctypes
import os
import signal
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class RunResult:
    returncode: int
    cancelled: bool = False


class WindowsJob:
    """A kernel-owned process group; termination never searches by executable/PID."""

    def __init__(self):
        from ctypes import wintypes as w

        class Limits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", w.DWORD),
                ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t),
                ("active_processes", w.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", w.DWORD),
                ("scheduling", w.DWORD),
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("limits", Limits),
                ("io", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t),
                ("peak_job_memory", ctypes.c_size_t),
            ]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [
            w.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            w.DWORD,
        ]
        self.api.SetInformationJobObject.restype = w.BOOL
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.AssignProcessToJobObject.restype = w.BOOL
        self.api.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.api.TerminateJobObject.restype = w.BOOL
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.api.CloseHandle.restype = w.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.limits.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def attach(self, process):
        # CPython's Windows Popen owns this live process handle. A handle avoids
        # PID reuse and never targets another app's independently launched jobs.
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self):
        if not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _latest_progress(log):
    latest = None
    for _ in range(256):
        line = log.readline()
        if not line:
            break
        if not line.endswith(b"\n"):
            log.seek(-len(line), os.SEEK_CUR)
            break
        if line.startswith(b"Progress: "):
            latest = line.removeprefix(b"Progress: ").decode("utf-8", errors="replace").strip()
    return latest


def run_conversion(command, *, cwd, log_path, cancel_event, on_progress=None):
    """Run one owned process tree; preserve partial outputs/logs on cancellation.

    Completion wins if the process has already exited when cancellation is
    observed. Windows uses a job object, including separation/decoder children.
    The CLI waits for those children; POSIX runs in a private process session.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log, log_path.open("rb") as progress_log:
        if cancel_event.is_set():
            log.write(b"Cancelled before conversion started.\n")
            return RunResult(-1, True)
        job = WindowsJob() if os.name == "nt" else None
        process = None
        try:
            environment = os.environ.copy()
            environment["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                start_new_session=os.name != "nt",
                env=environment,
            )
            if job:
                job.attach(process)
            while True:
                try:
                    return RunResult(process.wait(timeout=0.1))
                except subprocess.TimeoutExpired:
                    if cancel_event.is_set():
                        if job:
                            job.terminate()
                        else:
                            os.killpg(process.pid, signal.SIGKILL)
                        try:
                            code = process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            if job:
                                job.terminate()
                            else:
                                os.killpg(process.pid, signal.SIGKILL)
                            code = process.wait(timeout=3)
                        log.write(
                            b"\nCancelled by user; saved diagnostics and partial outputs retained.\n"
                        )
                        return RunResult(code, True)
                    if on_progress is not None and (message := _latest_progress(progress_log)):
                        on_progress(message)
        finally:
            if job:
                job.close()
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait()
