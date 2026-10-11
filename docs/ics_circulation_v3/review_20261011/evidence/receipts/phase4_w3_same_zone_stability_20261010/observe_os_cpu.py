"""Read-only lifetime CPU observation of the already running frozen full batch."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import psutil
from scripts.experiments.ics_circulation_v3.experiment_protocol import write_new_json
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import file_sha

BASE = Path(__file__).resolve().parent
MODULE = "scripts.experiments.ics_circulation_v3.run_same_zone_stability"
DOCS = ["https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes",
        "https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process"]
KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)
KERNEL.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
KERNEL.OpenProcess.restype = wintypes.HANDLE
KERNEL.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
KERNEL.GetProcessTimes.restype = wintypes.BOOL
KERNEL.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
KERNEL.WaitForSingleObject.restype = wintypes.DWORD
KERNEL.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
KERNEL.GetExitCodeProcess.restype = wintypes.BOOL
KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]
KERNEL.CloseHandle.restype = wintypes.BOOL


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def times(handle, *, exited=False):
    created, ended, kernel, user = (wintypes.FILETIME() for _ in range(4))
    if not KERNEL.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(ended),
                                  ctypes.byref(kernel), ctypes.byref(user)):
        raise ctypes.WinError(ctypes.get_last_error())
    ticks = lambda v: (v.dwHighDateTime << 32) | v.dwLowDateTime
    value = {"creation_filetime_100ns": ticks(created),
        "creation_unix_seconds": ticks(created)/10000000 - 11644473600,
        "kernel_cpu_seconds": ticks(kernel)/10000000, "user_cpu_seconds": ticks(user)/10000000,
        "total_cpu_seconds": (ticks(kernel)+ticks(user))/10000000}
    if exited:
        value["exit_filetime_100ns"] = ticks(ended)
        code = wintypes.DWORD()
        if not KERNEL.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        value["exit_code"] = code.value
    return value


def main():
    cpu, wall = time.process_time(), time.perf_counter()
    handles, identities, failures, observations, finals = {}, {}, [], [], {}
    request_file = BASE / "full/requested_rows.json"
    request_sha = file_sha(request_file)
    receipts = []
    for path in (BASE / "full").glob("*.receipt.json"):
        try:
            receipts.append(read(path))
        except (json.JSONDecodeError, OSError):
            pass  # a concurrent final receipt write; later full summary binds all
    worker_ids = sorted({r["memory"]["pid"] for r in receipts})
    if len(worker_ids) != 6:
        raise ValueError("exactly the recorded six full workers are required")
    parents = {psutil.Process(pid).ppid() for pid in worker_ids}
    if len(parents) != 1:
        raise ValueError("receipt workers have different live parents")
    parent_id = parents.pop()
    parent = psutil.Process(parent_id)
    command = parent.cmdline()
    if MODULE not in command or "--stage" not in command or command[command.index("--stage")+1] != "full":
        raise ValueError("live parent is not the exact full stability CLI")
    if not request_file.stat().st_mtime - 180 <= parent.create_time() <= request_file.stat().st_mtime:
        raise ValueError("full request file and parent creation time do not bind")
    try:
        for pid in [parent_id, *worker_ids]:
            process = psutil.Process(pid)
            identity = {"pid": pid, "role": "parent" if pid == parent_id else "worker",
                "ppid": process.ppid(), "command_line": process.cmdline(),
                "creation_unix_seconds_psutil": process.create_time(), "executable": process.exe()}
            handle = KERNEL.OpenProcess(0x1000 | 0x100000, False, pid)  # query-limited + synchronize only
            if not handle:
                failures.append({"pid": pid, "stage": "open", "error": str(ctypes.WinError(ctypes.get_last_error()))})
                identities[pid] = identity
                continue
            handles[pid] = handle
            initial = times(handle)
            if abs(initial["creation_unix_seconds"] - identity["creation_unix_seconds_psutil"]) > .01:
                raise ValueError("PID creation-time race detected")
            identity["initial_lifetime_times"] = initial
            identities[pid] = identity
        write_new_json(BASE / "os_cpu_monitor_start.json", {"attached_at_utc": datetime.now(timezone.utc).isoformat(),
            "script_sha256": file_sha(__file__), "full_requests_sha256": request_sha,
            "full_protocol_sha256": file_sha(BASE / "protocol.json"), "recorded_receipts_at_attach": len(receipts),
            "parent_pid": parent_id, "worker_pids": worker_ids, "identities": identities, "failures": failures,
            "official_interface_sources": DOCS,
            "late_attachment_scope": "GetProcessTimes reports process/thread kernel+user lifetime totals, not elapsed observation deltas. Kept process handles preserve the signaled process object until queried after exit. No experiment state, priorities, affinity, concurrency or code is changed.",
            "resource_overlap": "Final OS parent+worker lifetime CPU overlaps all invocation/parent timers; compare or replace, never add those overlapping totals."})
        while len(finals) < len(handles):
            for pid, handle in handles.items():
                if pid in finals:
                    continue
                state = KERNEL.WaitForSingleObject(handle, 0)
                if state == 0:
                    try:
                        value = times(handle, exited=True)
                        if value["creation_filetime_100ns"] != identities[pid]["initial_lifetime_times"]["creation_filetime_100ns"]:
                            raise ValueError("retained handle identity changed")
                        finals[pid] = value
                    except Exception as error:
                        failures.append({"pid": pid, "stage": "final_query", "error": repr(error)})
                        finals[pid] = None
                elif state != 258:
                    failures.append({"pid": pid, "stage": "wait", "wait_code": state,
                        "windows_error": ctypes.get_last_error()})
                    finals[pid] = None
            try:
                current = {p.pid for p in parent.children(recursive=False)}
                unexpected = sorted(current - set(worker_ids))
                if unexpected and unexpected not in [r["unexpected_child_pids"] for r in observations]:
                    observations.append({"at_utc": datetime.now(timezone.utc).isoformat(), "unexpected_child_pids": unexpected})
            except psutil.NoSuchProcess:
                pass
            if len(finals) < len(handles):
                time.sleep(30)
        summary_path = BASE / "full/summary.json"
        summary = read(summary_path) if summary_path.exists() else None
        returned_worker_ids = None if summary is None else sorted({r["memory"]["pid"] for r in summary["rows"] if "memory" in r})
        complete = (len(handles) == 7 and not failures and not observations and summary is not None
            and returned_worker_ids == worker_ids and len(summary["rows"]) == 2468
            and all(r["actual_physical_call"] is True for r in summary["rows"])
            and file_sha(request_file) == request_sha)
        known_workers = sum(v["total_cpu_seconds"] for pid, v in finals.items() if pid in worker_ids and v is not None)
        known_parent = None if finals.get(parent_id) is None else finals[parent_id]["total_cpu_seconds"]
        write_new_json(BASE / "os_cpu_monitor_final.json", {"complete_bound_parent_and_worker_lifetimes": complete,
            "identities": identities, "final_lifetime_times": finals, "failures": failures,
            "unexpected_child_observations": observations, "final_receipt_worker_pids": returned_worker_ids,
            "known_worker_lifetime_cpu_seconds": known_workers, "known_parent_lifetime_cpu_seconds": known_parent,
            "known_bound_process_cpu_seconds": known_workers + (known_parent or 0),
            "invocation_worker_cpu_seconds_overlapping": None if summary is None else summary["case_invocation_cpu_seconds_recorded"],
            "recorded_parent_cpu_seconds_overlapping": None if summary is None else summary["parent_cpu_seconds"],
            "worker_excluded_overhead_seconds": None if summary is None else known_workers-summary["case_invocation_cpu_seconds_recorded"],
            "unknown_scope": [] if complete else ["Missing/replaced/failed lifecycle observations; reported known totals are lower bounds, never full lifecycle totals."],
            "resource_overlap": "OS parent+worker lifetime totals supersede overlapping full-stage invocation+parent timers when complete. They do not include bridge, pilot, prior preparation, this observer, root analysis or independent review.",
            "observer_cpu_seconds": time.process_time()-cpu, "observer_wall_seconds": time.perf_counter()-wall,
            "observer_scope": "own process CPU after imports; waiting wall is not CPU; final JSON write/handle close after timer excluded",
            "source_sha256": file_sha(__file__), "official_interface_sources": DOCS})
    finally:
        for handle in handles.values():
            KERNEL.CloseHandle(handle)


if __name__ == "__main__":
    main()
