"""Harmless Python process tests: no circulation module or NativeSession."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from scripts.experiments.g31_ics_circulation import bounded_windows_job as bounded

pytestmark = pytest.mark.skipif(os.name != "nt",reason="Windows JobObject contract")


def still_running(pid):
    api = ctypes.WinDLL("kernel32",use_last_error=True)
    api.OpenProcess.argtypes = (wintypes.DWORD,wintypes.BOOL,wintypes.DWORD);api.OpenProcess.restype = wintypes.HANDLE
    api.GetExitCodeProcess.argtypes = (wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD))
    api.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = api.OpenProcess(0x1000,False,pid)
    if not handle:return False
    try:
        code = wintypes.DWORD()
        assert api.GetExitCodeProcess(handle,ctypes.byref(code))
        return code.value == 259
    finally:api.CloseHandle(handle)


def test_assigned_child_is_released_and_exits_normally(tmp_path):
    target = tmp_path/"marker.txt"
    command = [sys.executable,"-c","import sys,pathlib; token=sys.stdin.readline().strip(); assert token=='go'; pathlib.Path(sys.argv[1]).write_text(token)",str(target)]
    with (tmp_path/"out").open("w") as out,(tmp_path/"err").open("w") as err:
        result = bounded.run(command,timeout=5.,stdout=out,stderr=err,admission="go")
    assert result["status"] == "exited" and result["exitcode"] == 0
    assert target.read_text() == "go" and not still_running(result["pid"])


def test_timeout_reaps_exact_child_and_grandchild_tree(tmp_path):
    pidfile = tmp_path/"grandchild_pid.txt"
    code = "import sys,subprocess,pathlib,time; assert sys.stdin.readline().strip()=='go'; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)"
    with (tmp_path/"out").open("w") as out,(tmp_path/"err").open("w") as err:
        result = bounded.run([sys.executable,"-c",code,str(pidfile)],timeout=1.,stdout=out,stderr=err,admission="go")
    assert result["status"] == "hard_timeout" and result["wall_seconds"] < 5.
    assert pidfile.exists()
    descendant = int(pidfile.read_text())
    for _ in range(50):
        if not still_running(descendant):break
        time.sleep(.01)
    assert not still_running(result["pid"]) and not still_running(descendant)


def test_assignment_failure_never_releases_gated_child(tmp_path,monkeypatch):
    target = tmp_path/"must_not_exist"
    def reject(self,process):raise RuntimeError("assignment failed")
    monkeypatch.setattr(bounded.Job,"assign",reject)
    code = "import sys,pathlib; x=sys.stdin.readline(); pathlib.Path(sys.argv[1]).write_text(x)"
    with (tmp_path/"out").open("w") as out,(tmp_path/"err").open("w") as err:
        with pytest.raises(RuntimeError,match="assignment failed"):
            bounded.run([sys.executable,"-c",code,str(target)],timeout=3.,stdout=out,stderr=err,admission="go")
    assert not target.exists()


@pytest.mark.parametrize("timeout",[0.,-1.,float("inf"),float("nan"),True])
def test_invalid_timeout_cannot_start_process(timeout):
    with pytest.raises(ValueError):bounded.run([],timeout=timeout,stdout=None,stderr=None,admission="no")
