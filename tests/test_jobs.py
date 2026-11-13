import ctypes
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tabber.jobs import run_conversion


def test_completed_job_keeps_stdout_stderr_and_exit_status(tmp_path):
    log = tmp_path / "result/run.log"
    result = run_conversion(
        [
            sys.executable,
            "-c",
            "import sys; print('output'); print('detail',file=sys.stderr); sys.exit(7)",
        ],
        cwd=tmp_path,
        log_path=log,
        cancel_event=threading.Event(),
    )
    assert result.returncode == 7 and not result.cancelled
    assert "output" in log.read_text() and "detail" in log.read_text()


def test_live_progress_reaches_the_caller_before_conversion_finishes(tmp_path):
    marker = tmp_path / "progress-received"
    messages = []

    def show_progress(message):
        messages.append(message)
        marker.touch()

    script = """
import time
from pathlib import Path
print("debug line", flush=True)
print("Progress: Resolving overlapping notes.", flush=True)
for _ in range(100):
    if Path("progress-received").exists():
        break
    time.sleep(0.05)
else:
    raise RuntimeError("Progress was not received while the child was running")
"""
    log = tmp_path / "run.log"
    result = run_conversion(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        log_path=log,
        cancel_event=threading.Event(),
        on_progress=show_progress,
    )
    assert result.returncode == 0
    assert messages == ["Resolving overlapping notes."]
    assert "debug line" in log.read_text()


def test_cancel_before_launch_never_starts_process(tmp_path):
    event = threading.Event()
    event.set()
    marker = tmp_path / "should-not-exist"
    result = run_conversion(
        [sys.executable, "-c", "from pathlib import Path; Path('should-not-exist').touch()"],
        cwd=tmp_path,
        log_path=tmp_path / "run.log",
        cancel_event=event,
    )
    assert result.cancelled and not marker.exists()


def test_start_failure_returns_control_with_log_folder_retained(tmp_path):
    with pytest.raises(OSError):
        run_conversion(
            [str(tmp_path / "missing-program.exe")],
            cwd=tmp_path,
            log_path=tmp_path / "result/run.log",
            cancel_event=threading.Event(),
        )
    assert (tmp_path / "result/run.log").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows job-object descendant ownership check")
def test_windows_cancel_stops_owned_child_but_leaves_unrelated_process_and_files(tmp_path):
    from ctypes import wintypes as w

    marker = tmp_path / "child.pid"
    partial = tmp_path / "diagnostic.json"
    partial.write_text("keep diagnostic", encoding="utf-8")
    source = tmp_path / "source.audio"
    source.write_bytes(b"unchanged original")
    child = tmp_path / "child.py"
    child.write_text(
        "import os,sys,time\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(str(os.getpid()))\nprint('child ready',flush=True)\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess,sys,time\nsubprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]])\nprint('parent ready',flush=True)\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes, api.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
    api.WaitForSingleObject.argtypes, api.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
    api.CloseHandle.argtypes, api.CloseHandle.restype = [w.HANDLE], w.BOOL
    event, handle = threading.Event(), None
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                run_conversion,
                [sys.executable, str(parent), str(child), str(marker)],
                cwd=tmp_path,
                log_path=tmp_path / "run.log",
                cancel_event=event,
            )
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline and not future.done():
                    time.sleep(0.02)
                assert marker.exists(), future.result() if future.done() else "Child did not start"
                handle = api.OpenProcess(0x100000, False, int(marker.read_text()))  # SYNCHRONIZE
                assert handle
                event.set()
                result = future.result(timeout=10)
                assert result.cancelled
                assert api.WaitForSingleObject(handle, 2000) == 0  # owned child terminated
                assert unrelated.poll() is None
            finally:
                event.set()
        assert (
            partial.read_text() == "keep diagnostic"
            and source.read_bytes() == b"unchanged original"
        )
        assert "Cancelled by user" in (tmp_path / "run.log").read_text()
    finally:
        if handle:
            api.CloseHandle(handle)
        unrelated.terminate()
        unrelated.wait(timeout=5)
