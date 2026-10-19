"""Own one Windows child tree; closing its JobObject kills only that tree.

The initial child waits on stdin before doing task work. Assignment is
complete before the parent releases that gate. Descendants inherit the job;
no breakaway flag is allowed. Failure to create/assign aborts before release.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os
import subprocess
import time


class Job:
    def __init__(self):
        if os.name != "nt":raise RuntimeError("bounded_job:Windows_required")
        self.api = ctypes.WinDLL("kernel32",use_last_error=True)
        self.api.CreateJobObjectW.argtypes = (ctypes.c_void_p,wintypes.LPCWSTR)
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = (wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD)
        self.api.AssignProcessToJobObject.argtypes = (wintypes.HANDLE,wintypes.HANDLE)
        self.api.TerminateJobObject.argtypes = (wintypes.HANDLE,wintypes.UINT)
        self.api.CloseHandle.argtypes = (wintypes.HANDLE,)
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit",ctypes.c_longlong),("PerJobUserTimeLimit",ctypes.c_longlong),
                ("LimitFlags",wintypes.DWORD),("MinimumWorkingSetSize",ctypes.c_size_t),("MaximumWorkingSetSize",ctypes.c_size_t),
                ("ActiveProcessLimit",wintypes.DWORD),("Affinity",ctypes.c_size_t),("PriorityClass",wintypes.DWORD),
                ("SchedulingClass",wintypes.DWORD)]
        class Io(ctypes.Structure):
            _fields_ = [(name,ctypes.c_ulonglong) for name in ("ReadOperationCount","WriteOperationCount","OtherOperationCount",
                "ReadTransferCount","WriteTransferCount","OtherTransferCount")]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation",Basic),("IoInfo",Io),("ProcessMemoryLimit",ctypes.c_size_t),
                ("JobMemoryLimit",ctypes.c_size_t),("PeakProcessMemoryUsed",ctypes.c_size_t),("PeakJobMemoryUsed",ctypes.c_size_t)]
        self.handle = self.api.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended();limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error());self.close();raise error

    def assign(self,process):
        if not self.api.AssignProcessToJobObject(self.handle,wintypes.HANDLE(int(process._handle))):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            handle,self.handle = self.handle,None
            if not self.api.CloseHandle(handle):raise ctypes.WinError(ctypes.get_last_error())


def run(command,*,timeout,stdout,stderr,admission,cwd=None):
    """Bound the full child tree, including its own further workers.

    Child must consume exactly admission+'\\n' from stdin before task work.
    Result distinguishes actual process exit from timeout; never certifies its
    artifacts. Setup and assignment consume the same monotonic timeout.
    """
    if type(timeout) not in (int,float) or not 0 < timeout < float("inf"):
        raise ValueError("bounded_job:invalid_timeout")
    started = time.monotonic();job = Job();process = None;status = "not_started"
    try:
        process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,text=True,cwd=cwd)
        job.assign(process)
        remaining = timeout-(time.monotonic()-started)
        if remaining <= 0:raise subprocess.TimeoutExpired(command,timeout)
        process.stdin.write(admission+"\n");process.stdin.flush();process.stdin.close()
        process.wait(timeout=remaining)
        status = "exited"
    except subprocess.TimeoutExpired:
        status = "hard_timeout"
    finally:
        # Closes the only job handle even after parent/child setup errors. On
        # timeout descendants are terminated even if the campaign is waiting
        # inside a synchronous verifier. No process enumeration is used.
        job.close()
        if process is not None:
            if process.poll() is None:
                process.kill()  # assignment failure can leave only the gated child
            process.wait()
    return {"status":status,"pid":process.pid,"exitcode":process.returncode,
            "wall_seconds":time.monotonic()-started,"hard_timeout_seconds":timeout,
            "windows_job_kill_on_close":True,"child_released_only_after_job_assignment":True}
