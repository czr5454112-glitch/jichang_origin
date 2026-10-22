"""Administrative Windows supervisor; never imports or selects scientific work.

The caller supplies one stdin-gated command. Only the supervisor's Job handle
can be cancelled. All measurements use that live handle, not PID enumeration.
Job memory is committed virtual memory, not RSS or pagefile file occupancy.
API layouts: Microsoft Learn JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
PROCESS_MEMORY_COUNTERS_EX; Microsoft hcsshim/internal/winapi/jobobject.go (28).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

SCHEMA = "g31.inventory_spi.offline_owned_resource.v1"
GIB = 1024**3
POLICY = {
    "job_commit_limit_bytes": 4*GIB,
    "launch_minimum": {"physical_available_bytes": 8*GIB,
                       "commit_available_bytes": 12*GIB, "disk_free_bytes": 12*GIB},
    "cancel_below": {"physical_available_bytes": 2*GIB,
                     "commit_available_bytes": 4*GIB, "disk_free_bytes": 6*GIB},
    "cancel_combination": "(physical_low AND commit_low) OR disk_low",
    "sample_seconds": 1., "consecutive_low_samples": 2,
    "closure_wait_seconds": 15.,
}
FLAGS = 0x2000 | 0x0200  # KILL_ON_JOB_CLOSE | JOB_MEMORY; no inheritance/breakaway.


def require(ok, reason):
    if not ok:
        raise ValueError("offline_owned_resource:" + reason)


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    path = Path(path)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wt.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wt.DWORD), ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wt.DWORD), ("SchedulingClass", wt.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [(n, ctypes.c_longlong) for n in ("TotalUserTime", "TotalKernelTime",
                "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")] + [
                (n, wt.DWORD) for n in ("TotalPageFaultCount", "TotalProcesses",
                                       "ActiveProcesses", "TotalTerminatedProcesses")]


class JobMemory(ctypes.Structure):
    _fields_ = [("JobMemory", ctypes.c_ulonglong), ("PeakJobMemoryUsed", ctypes.c_ulonglong)]


class ProcessMemory(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [
        (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize",
        "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


class GlobalMemory(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD)] + [
        (n, ctypes.c_ulonglong) for n in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile",
        "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]


def api():
    require(os.name == "nt", "Windows_required")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ((ctypes.c_void_p, wt.LPCWSTR), wt.HANDLE),
        "SetInformationJobObject": ((wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD), wt.BOOL),
        "QueryInformationJobObject": ((wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p), wt.BOOL),
        "AssignProcessToJobObject": ((wt.HANDLE, wt.HANDLE), wt.BOOL),
        "TerminateJobObject": ((wt.HANDLE, wt.UINT), wt.BOOL),
        "CloseHandle": ((wt.HANDLE,), wt.BOOL),
        "GetHandleInformation": ((wt.HANDLE, ctypes.POINTER(wt.DWORD)), wt.BOOL),
        "GetProcessTimes": ((wt.HANDLE, *[ctypes.POINTER(wt.FILETIME)]*4), wt.BOOL),
        "GlobalMemoryStatusEx": ((ctypes.POINTER(GlobalMemory),), wt.BOOL),
        "K32GetProcessMemoryInfo": ((wt.HANDLE, ctypes.POINTER(ProcessMemory), wt.DWORD), wt.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(k, name)
        fn.argtypes, fn.restype = args, result
    return k


def checked(ok):
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


def resources(disk_path):
    value = GlobalMemory()
    value.dwLength = ctypes.sizeof(value)
    checked(api().GlobalMemoryStatusEx(ctypes.byref(value)))
    return {"at_utc": utc(), "physical_available_bytes": value.ullAvailPhys,
            "commit_available_bytes": value.ullAvailPageFile,
            "physical_total_bytes": value.ullTotalPhys, "commit_limit_bytes": value.ullTotalPageFile,
            "disk_free_bytes": shutil.disk_usage(disk_path).free}


def below(sample, thresholds):
    return [name for name, minimum in thresholds.items() if sample[name] < minimum]


def emergency_reasons(sample, policy):
    low = set(below(sample, policy["cancel_below"]))
    reasons = []
    if {"physical_available_bytes", "commit_available_bytes"} <= low:
        reasons.extend(["physical_available_bytes", "commit_available_bytes"])
    if "disk_free_bytes" in low:
        reasons.append("disk_free_bytes")
    return reasons


class Job:
    def __init__(self, limit):
        require(type(limit) is int and limit > 0, "positive_integer_commit_limit")
        self.k, self.handle = api(), None
        self.handle = self.k.CreateJobObjectW(None, None)
        checked(self.handle)
        try:
            inherit = wt.DWORD()
            checked(self.k.GetHandleInformation(self.handle, ctypes.byref(inherit)))
            require(not (inherit.value & 1), "job_handle_must_not_be_inheritable")
            limits = ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags, limits.JobMemoryLimit = FLAGS, limit
            checked(self.k.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            observed = self.query(9, ExtendedLimits)
            require(observed.BasicLimitInformation.LimitFlags == FLAGS and observed.JobMemoryLimit == limit,
                    "actual_OS_limit_readback_required")
            self.limit = limit
        except BaseException:
            self.close()
            raise

    def query(self, code, cls):
        result = cls()
        checked(self.k.QueryInformationJobObject(self.handle, code, ctypes.byref(result), ctypes.sizeof(result), None))
        return result

    def assign(self, process):
        checked(self.k.AssignProcessToJobObject(self.handle, wt.HANDLE(int(process._handle))))

    def creation(self, process):
        times = [wt.FILETIME() for _ in range(4)]
        checked(self.k.GetProcessTimes(wt.HANDLE(int(process._handle)), *(ctypes.byref(t) for t in times)))
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime

    def snapshot(self, process):
        limits, accounting, memory = self.query(9, ExtendedLimits), self.query(1, Accounting), self.query(28, JobMemory)
        measured = ProcessMemory()
        measured.cb = ctypes.sizeof(measured)
        checked(self.k.K32GetProcessMemoryInfo(wt.HANDLE(int(process._handle)), ctypes.byref(measured), ctypes.sizeof(measured)))
        return {"job_current_commit_bytes": memory.JobMemory,
                "job_peak_commit_bytes": memory.PeakJobMemoryUsed,
                "job_peak_commit_extended_bytes": limits.PeakJobMemoryUsed,
                "active_processes": accounting.ActiveProcesses, "total_processes": accounting.TotalProcesses,
                "direct_child_private_commit_bytes": measured.PrivateUsage,
                "direct_child_peak_commit_bytes": measured.PeakPagefileUsage,
                "direct_child_working_set_bytes": measured.WorkingSetSize,
                "direct_child_peak_working_set_bytes": measured.PeakWorkingSetSize,
                "job_limit_flags_readback": limits.BasicLimitInformation.LimitFlags,
                "job_commit_limit_bytes_readback": limits.JobMemoryLimit}

    def terminate(self):
        checked(self.k.TerminateJobObject(self.handle, 1223))  # explicit administrative cancellation

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            checked(self.k.CloseHandle(handle))


def validate_policy(policy):
    require(type(policy["job_commit_limit_bytes"]) is int and policy["job_commit_limit_bytes"] > 0,
            "positive_job_limit")
    for field in ("launch_minimum", "cancel_below"):
        require(set(policy[field]) == {"physical_available_bytes", "commit_available_bytes", "disk_free_bytes"},
                "exact_resource_fields")
        require(all(type(v) is int and v >= 0 for v in policy[field].values()), "nonnegative_resource_limits")
    for key in policy["launch_minimum"]:
        require(policy["cancel_below"][key] <= policy["launch_minimum"][key], "cancel_not_above_launch")
    require(type(policy["consecutive_low_samples"]) is int and policy["consecutive_low_samples"] > 0,
            "positive_low_sample_count")
    require(policy["cancel_combination"] == "(physical_low AND commit_low) OR disk_low",
            "fixed_combined_memory_emergency")
    require(all(type(policy[k]) in (int, float) and math.isfinite(policy[k]) and 0 < policy[k] <= 60
                for k in ("sample_seconds", "closure_wait_seconds")), "bounded_sampling_and_cleanup")


def run(command, *, timeout, stdout, stderr, admission, cwd, directory,
        policy=None, cancel_probe=None, resource_probe=None, before_release=None):
    """One attempt. Always save actual closure, even on cancellation/error.

    cancel_probe is a supervisor-owned callback, never child-supplied. It returns
    a reason or None. The production driver only reads its bound cancel file.
    Test probes are allowed only in explicitly labelled dummy tests.
    """
    policy = POLICY if policy is None else policy
    validate_policy(policy)
    require(type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0, "positive_timeout")
    directory = Path(directory)
    require(directory.is_dir(), "attempt_directory_precreated")
    require(not any((directory/name).exists() for name in
                    ("process_started.json", "process_closed.json", "resource_samples.jsonl")),
            "fresh_supervisor_attempt_required")
    probe = resource_probe or (lambda: resources(cwd))
    began = time.monotonic()
    initial = probe()
    require(not below(initial, policy["launch_minimum"]), "launch_resources_insufficient")
    job = process = None
    assigned = released = False
    report = {"schema": SCHEMA+".process", "status": "supervisor_error", "pid": None,
              "creation_filetime": None, "exitcode": None, "hard_timeout_seconds": timeout,
              "policy": policy, "initial_resources": initial, "cleanup_errors": [],
              "termination_reason": None, "direct_child_wait_completed": False,
              "job_active_processes_zero_verified": False, "samples": 0}
    peak = {}
    try:
        if time.monotonic()-began >= timeout:
            raise subprocess.TimeoutExpired(command, timeout)
        job = Job(policy["job_commit_limit_bytes"])
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   text=True, cwd=cwd, close_fds=True, creationflags=0x08000000)
        report.update(pid=process.pid, creation_filetime=job.creation(process))
        job.assign(process)
        assigned = True
        first = job.snapshot(process)
        require(first["active_processes"] == 1, "exactly_one_gated_child_before_release")
        report["started_receipt"] = write_new(directory/"process_started.json", {
            "schema": SCHEMA+".started", "at_utc": utc(), "pid": process.pid,
            "creation_filetime": report["creation_filetime"], "command": command,
            "policy": policy, "actual_job": first, "initial_resources": initial,
            "job_handle_noninheritable": True, "stdin_gate_not_yet_released": True})
        # Entry resource state may have changed during setup. Do not release if so.
        require(not below(probe(), policy["launch_minimum"]), "launch_resources_changed")
        if before_release is not None:
            before_release()
        if time.monotonic()-began >= timeout:
            raise subprocess.TimeoutExpired(command, timeout)
        process.stdin.write(admission+"\n")
        process.stdin.flush()
        process.stdin.close()
        released = True
        low = 0
        with (directory/"resource_samples.jsonl").open("x", encoding="utf8") as samples:
            while True:
                actual = job.snapshot(process)
                global_state = probe()
                row = {"at_utc": utc(), "elapsed_seconds": time.monotonic()-began,
                       "pid": process.pid, "creation_filetime": report["creation_filetime"],
                       "owned_job": actual, "global": global_state}
                samples.write(json.dumps(row, separators=(",", ":"), allow_nan=False)+"\n")
                samples.flush()
                report["samples"] += 1
                for key, value in actual.items():
                    if "peak_" in key:
                        peak[key] = max(peak.get(key, 0), value)
                report["last_sample"] = row
                if process.poll() is not None:
                    report["status"] = "exited"
                    break
                violated = emergency_reasons(global_state, policy)
                low = low+1 if violated else 0
                reason = cancel_probe(report) if cancel_probe else None
                if reason:
                    report.update(status="administrative_resource_abort", termination_reason=reason)
                    break
                if low >= policy["consecutive_low_samples"]:
                    report.update(status="administrative_resource_abort",
                                  termination_reason="global_resource_floor:" + ",".join(violated))
                    break
                if time.monotonic()-began >= timeout:
                    report.update(status="hard_timeout", termination_reason="original_job_timeout")
                    break
                time.sleep(min(policy["sample_seconds"], max(.001, timeout-(time.monotonic()-began))))
    except subprocess.TimeoutExpired:
        report.update(status="hard_timeout", termination_reason="original_job_timeout")
    except BaseException as exc:
        report.update(error=type(exc).__name__+":"+str(exc))
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            report.update(status="administrative_resource_abort", termination_reason="owner_interruption")
    finally:
        # Keep the actual Job handle until direct wait AND aggregate-zero query.
        # Cleanup failures cannot erase the already-fsynced PID/creation receipt.
        if process is not None:
            try:
                if assigned:
                    active = job.query(1, Accounting).ActiveProcesses
                    if process.poll() is None or active:
                        job.terminate()
                        report["terminate_owned_job_called"] = True
                        if report["status"] == "exited" and active:
                            report["termination_reason"] = "remaining_owned_descendants_after_direct_exit"
                elif process.poll() is None:
                    process.kill()  # setup failed: only our still-gated direct handle
                    report["terminated_gated_unassigned_child"] = True
                process.wait(timeout=policy["closure_wait_seconds"])
                report.update(exitcode=process.returncode, direct_child_wait_completed=True)
                if assigned:
                    deadline = time.monotonic()+policy["closure_wait_seconds"]
                    while True:
                        active = job.query(1, Accounting).ActiveProcesses
                        if active == 0 or time.monotonic() >= deadline:
                            break
                        time.sleep(.05)
                    report.update(job_final_active_processes=active,
                                  job_active_processes_zero_verified=active == 0)
                    final = job.snapshot(process)
                    report["final_job"] = final
                    for key, value in final.items():
                        if "peak_" in key:
                            peak[key] = max(peak.get(key, 0), value)
            except BaseException as exc:
                report["cleanup_errors"].append(type(exc).__name__+":"+str(exc))
        if job is not None:
            try:
                job.close()
                report["job_handle_closed"] = True
            except BaseException as exc:
                report["cleanup_errors"].append(type(exc).__name__+":"+str(exc))
        report.update(wall_seconds=time.monotonic()-began, finished_at_utc=utc(),
                      windows_job_kill_on_close=assigned, child_released_only_after_job_assignment=released,
                      peak_measurements=peak, memory_units="bytes of committed virtual memory; RSS separately named")
        report["closure_verified"] = (report["direct_child_wait_completed"]
                                     and report["job_active_processes_zero_verified"]
                                     and not report["cleanup_errors"])
        write_new(directory/"process_closed.json", report)
    return report
