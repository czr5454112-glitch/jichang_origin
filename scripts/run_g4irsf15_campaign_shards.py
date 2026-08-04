#!/usr/bin/env python3
"""Run preregistered G4IRSF15 campaign shards with bounded concurrency.

Each shard is executed in a fresh subprocess through the campaign
``run-shard`` CLI.  The orchestrator never edits shard artifacts and is
therefore resume-safe: an existing valid shard is handled by the worker's
idempotent validation path.  On the first observed failure no additional
shards are scheduled, while every already-running subprocess is monitored
and reaped before an atomic, self-hashed profile is published.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


PROFILE_SCHEMA = (
    "czr005.g4irsf15.campaign_shard_orchestrator_profile.v2"
)
HEARTBEAT_SCHEMA = (
    "czr005.g4irsf15.campaign_shard_orchestrator_heartbeat.v1"
)
PILOT_PLAN_PATHS = {
    1: Path(
        "artifacts/datasets/g4irsf15_pilot_intervention_manifest.json"
    ),
    2: Path(
        "artifacts/datasets/"
        "g4irsf15_pilot_intervention_manifest_round2.json"
    ),
}
FORMAL_PLAN_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_campaign_plan.json"
)
MAX_PUBLICATION_PROCESS_RSS_MIB = 65_536.0
MAX_HEARTBEAT_INTERVAL_SECONDS = 60.0
TERMINATION_GRACE_SECONDS = 5.0
KILL_REAP_TIMEOUT_SECONDS = 5.0
RSS_UNAVAILABLE_MAX_ATTEMPTS_PER_CYCLE = 3
RSS_UNAVAILABLE_RETRY_DELAY_SECONDS = 0.0
PRODUCTION_RSS_METHODS = frozenset(
    {
        "WINDOWS_TOOLHELP32_PROCESS_TREE_GETPROCESSMEMORYINFO",
        "LINUX_PROC_PROCESS_TREE_STATUS",
    }
)


class OrchestratorError(RuntimeError):
    """Raised when orchestration inputs or immutable plan evidence are bad."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OrchestratorError(message)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    _require(path.is_file(), f"MISSING_FILE:{path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_now_after(previous: str | None) -> str:
    """Return a UTC timestamp strictly later than ``previous``."""

    now = datetime.now(timezone.utc)
    if previous is not None:
        prior = datetime.fromisoformat(
            previous.replace("Z", "+00:00")
        )
        if now <= prior:
            now = prior + timedelta(microseconds=1)
    return now.isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_bytes(value) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory_descriptor = os.open(
                path.parent, os.O_RDONLY
            )
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OrchestratorError(
            f"INVALID_JSON:{path}:{type(exc).__name__}"
        ) from exc
    _require(isinstance(value, dict), f"JSON_NOT_OBJECT:{path}")
    return value


def _plan_path(campaign: str, pilot_round: int) -> Path:
    if campaign == "pilot":
        _require(
            pilot_round in PILOT_PLAN_PATHS,
            "PILOT_ROUND_MUST_BE_1_OR_2",
        )
        return PILOT_PLAN_PATHS[pilot_round]
    _require(campaign == "formal", f"UNKNOWN_CAMPAIGN:{campaign}")
    _require(
        pilot_round == 1,
        "FORMAL_CAMPAIGN_HAS_NO_ROUND_2_NAMESPACE",
    )
    return FORMAL_PLAN_PATH


def _load_plan(
    root: Path, campaign: str, pilot_round: int
) -> tuple[dict[str, Any], Path, list[int]]:
    relative = _plan_path(campaign, pilot_round)
    path = root / relative
    plan = _load_json(path)
    _require(
        plan.get("campaign") == campaign,
        "PLAN_CAMPAIGN_DRIFT",
    )
    if campaign == "pilot":
        _require(
            plan.get("pilot_round") == pilot_round,
            "PLAN_PILOT_ROUND_DRIFT",
        )
    self_sha256 = plan.get("self_sha256")
    if self_sha256 is not None:
        projection = dict(plan)
        projection.pop("self_sha256", None)
        _require(
            self_sha256 == _canonical_sha256(projection),
            "PLAN_SELF_SHA256_DRIFT",
        )
    shards = plan.get("shards")
    _require(isinstance(shards, list), "PLAN_SHARDS_MISSING")
    indices: list[int] = []
    for expected, shard in enumerate(shards):
        _require(
            isinstance(shard, dict)
            and shard.get("shard_index") == expected,
            f"PLAN_SHARD_INDEX_DRIFT:{expected}",
        )
        declared_shard_sha256 = shard.get("shard_sha256")
        _require(
            isinstance(declared_shard_sha256, str)
            and len(declared_shard_sha256) == 64,
            f"PLAN_SHARD_SHA256_MISSING:{expected}",
        )
        shard_projection = dict(shard)
        shard_projection.pop("shard_sha256", None)
        _require(
            declared_shard_sha256
            == _canonical_sha256(shard_projection),
            f"PLAN_SHARD_SHA256_DRIFT:{expected}",
        )
        indices.append(expected)
    _require(
        plan.get("shard_count", len(indices)) == len(indices),
        "PLAN_SHARD_COUNT_DRIFT",
    )
    _require(bool(indices), "PLAN_HAS_NO_SHARDS")
    return plan, relative, indices


def _parse_shard_tokens(
    tokens: Sequence[str] | None,
    *,
    available_indices: Sequence[int],
) -> list[int]:
    available = set(available_indices)
    if not tokens or [token.lower() for token in tokens] == ["all"]:
        return sorted(available)
    _require(
        all(token.lower() != "all" for token in tokens),
        "SHARDS_ALL_MUST_BE_USED_ALONE",
    )
    selected: set[int] = set()
    for raw_token in tokens:
        for token in raw_token.split(","):
            token = token.strip()
            _require(bool(token), "EMPTY_SHARD_TOKEN")
            if "-" in token:
                parts = token.split("-")
                _require(
                    len(parts) == 2
                    and all(part.isdigit() for part in parts),
                    f"INVALID_SHARD_RANGE:{token}",
                )
                lower, upper = (int(part) for part in parts)
                _require(
                    lower <= upper,
                    f"DESCENDING_SHARD_RANGE:{token}",
                )
                selected.update(range(lower, upper + 1))
            else:
                _require(
                    token.isdigit(),
                    f"INVALID_SHARD_INDEX:{token}",
                )
                selected.add(int(token))
    unknown = sorted(selected - available)
    _require(not unknown, f"SHARD_INDEX_NOT_IN_PLAN:{unknown}")
    _require(bool(selected), "NO_SHARDS_SELECTED")
    return sorted(selected)


@dataclass(frozen=True)
class MemorySample:
    current_resident_bytes: int | None
    peak_resident_bytes: int | None
    method: str


def _windows_process_memory_sample(pid: int) -> MemorySample:
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    process_vm_read = 0x0010

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    open_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    get_memory = psapi.GetProcessMemoryInfo
    get_memory.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    get_memory.restype = wintypes.BOOL
    handle = open_process(
        process_query_limited_information | process_vm_read,
        False,
        pid,
    )
    if not handle:
        return MemorySample(None, None, "WINDOWS_GETPROCESSMEMORYINFO")
    try:
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not get_memory(
            handle, ctypes.byref(counters), counters.cb
        ):
            return MemorySample(
                None, None, "WINDOWS_GETPROCESSMEMORYINFO"
            )
        return MemorySample(
            int(counters.WorkingSetSize),
            int(counters.PeakWorkingSetSize),
            "WINDOWS_GETPROCESSMEMORYINFO",
        )
    finally:
        close_handle(handle)


def _windows_process_tree_pids(root_pid: int) -> list[int]:
    from ctypes import wintypes

    toolhelp_snapshot_process = 0x00000002
    max_path = 260

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * max_path),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    create_snapshot.restype = wintypes.HANDLE
    process_first = kernel32.Process32FirstW
    process_first.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    process_first.restype = wintypes.BOOL
    process_next = kernel32.Process32NextW
    process_next.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    process_next.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    snapshot = create_snapshot(toolhelp_snapshot_process, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    snapshot_value = (
        snapshot
        if isinstance(snapshot, int)
        else ctypes.cast(snapshot, ctypes.c_void_p).value
    )
    if not snapshot or snapshot_value == invalid_handle:
        raise OSError(
            ctypes.get_last_error(),
            "CreateToolhelp32Snapshot failed",
        )
    parent_to_children: dict[int, list[int]] = {}
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        has_entry = bool(process_first(snapshot, ctypes.byref(entry)))
        if not has_entry:
            raise OSError(
                ctypes.get_last_error(),
                "Process32FirstW failed",
            )
        while has_entry:
            process_id = int(entry.th32ProcessID)
            parent_id = int(entry.th32ParentProcessID)
            parent_to_children.setdefault(parent_id, []).append(
                process_id
            )
            entry.dwSize = ctypes.sizeof(entry)
            has_entry = bool(
                process_next(snapshot, ctypes.byref(entry))
            )
    finally:
        close_handle(snapshot)
    result: list[int] = []
    pending = [root_pid]
    seen: set[int] = set()
    while pending:
        process_id = pending.pop()
        if process_id in seen:
            continue
        seen.add(process_id)
        result.append(process_id)
        pending.extend(parent_to_children.get(process_id, []))
    return sorted(result)


def _windows_process_tree_memory_sample(pid: int) -> MemorySample:
    process_ids = _windows_process_tree_pids(pid)
    samples = [
        _windows_process_memory_sample(process_id)
        for process_id in process_ids
    ]
    if not samples or any(
        sample.current_resident_bytes is None for sample in samples
    ):
        return MemorySample(
            None,
            None,
            "WINDOWS_PROCESS_TREE_RSS_UNAVAILABLE",
        )
    current = sum(
        int(sample.current_resident_bytes) for sample in samples
    )
    peaks = [
        (
            sample.peak_resident_bytes
            if sample.peak_resident_bytes is not None
            else sample.current_resident_bytes
        )
        for sample in samples
    ]
    return MemorySample(
        current,
        sum(int(value) for value in peaks),
        "WINDOWS_TOOLHELP32_PROCESS_TREE_GETPROCESSMEMORYINFO",
    )


def _linux_process_memory_sample(pid: int) -> MemorySample:
    status = Path(f"/proc/{pid}/status")
    try:
        values: dict[str, int] = {}
        for line in status.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                name, raw = line.split(":", 1)
                amount, unit = raw.split()[:2]
                multiplier = 1024 if unit == "kB" else 1
                values[name] = int(amount) * multiplier
        return MemorySample(
            values.get("VmRSS"),
            values.get("VmHWM", values.get("VmRSS")),
            "LINUX_PROC_STATUS",
        )
    except (OSError, ValueError):
        return MemorySample(None, None, "LINUX_PROC_STATUS")


def _linux_process_tree_pids(root_pid: int) -> list[int]:
    result: list[int] = []
    pending = [root_pid]
    seen: set[int] = set()
    while pending:
        process_id = pending.pop()
        if process_id in seen:
            continue
        seen.add(process_id)
        result.append(process_id)
        children_path = Path(
            f"/proc/{process_id}/task/{process_id}/children"
        )
        try:
            pending.extend(
                int(value)
                for value in children_path.read_text(
                    encoding="ascii"
                ).split()
            )
        except (OSError, ValueError) as exc:
            raise OSError(
                f"unable to enumerate children for pid {process_id}"
            ) from exc
    return sorted(result)


def _linux_process_tree_memory_sample(pid: int) -> MemorySample:
    process_ids = _linux_process_tree_pids(pid)
    samples = [
        _linux_process_memory_sample(process_id)
        for process_id in process_ids
    ]
    if not samples or any(
        sample.current_resident_bytes is None for sample in samples
    ):
        return MemorySample(
            None, None, "LINUX_PROC_PROCESS_TREE_RSS_UNAVAILABLE"
        )
    current = sum(
        int(sample.current_resident_bytes) for sample in samples
    )
    peaks = [
        (
            sample.peak_resident_bytes
            if sample.peak_resident_bytes is not None
            else sample.current_resident_bytes
        )
        for sample in samples
    ]
    return MemorySample(
        current,
        sum(int(value) for value in peaks),
        "LINUX_PROC_PROCESS_TREE_STATUS",
    )


def _memory_sample(pid: int) -> MemorySample:
    """Return worker-process-tree RSS; unsupported platforms return null."""

    if os.name == "nt":
        try:
            return _windows_process_tree_memory_sample(pid)
        except (AttributeError, OSError, TypeError, ValueError):
            return MemorySample(
                None,
                None,
                "WINDOWS_PROCESS_TREE_RSS_UNAVAILABLE",
            )
    if sys.platform.startswith("linux"):
        try:
            return _linux_process_tree_memory_sample(pid)
        except (OSError, TypeError, ValueError):
            return MemorySample(
                None,
                None,
                "LINUX_PROC_PROCESS_TREE_RSS_UNAVAILABLE",
            )
    return MemorySample(None, None, "UNAVAILABLE_ON_THIS_PLATFORM")


@dataclass
class _ActiveShard:
    shard_index: int
    argv: list[str]
    process: subprocess.Popen[bytes]
    stdout_path: Path
    stderr_path: Path
    stdout_handle: Any
    stderr_handle: Any
    started_utc: str
    started_monotonic: float
    peak_resident_bytes: int | None = None
    current_resident_bytes: int | None = None
    rss_sample_method: str = "UNSAMPLED"
    rss_sample_count: int = 0
    rss_successful_sample_count: int = 0
    orchestration_failure_reason: str | None = None
    termination_requested_monotonic: float | None = None
    kill_requested_monotonic: float | None = None
    forced_kill: bool = False


def _update_memory(
    active: Mapping[int, _ActiveShard],
    *,
    sampler: Callable[[int], MemorySample],
    max_process_rss_bytes: int | None,
) -> tuple[
    int | None,
    list[int],
    list[int],
    list[dict[str, Any]],
]:
    current_group_total = 0
    current_available = False
    exceeded: list[int] = []
    unattestable: list[int] = []
    samples: list[dict[str, Any]] = []
    for shard in active.values():
        sample = MemorySample(
            None, None, "PROCESS_ALREADY_EXITED_BEFORE_SAMPLE"
        )
        if shard.process.poll() is None:
            for attempt in range(
                RSS_UNAVAILABLE_MAX_ATTEMPTS_PER_CYCLE
            ):
                sample = sampler(shard.process.pid)
                shard.rss_sample_count += 1
                candidate = sample.peak_resident_bytes
                if candidate is None:
                    candidate = sample.current_resident_bytes
                if (
                    candidate is not None
                    or shard.process.poll() is not None
                ):
                    break
                if (
                    attempt + 1
                    < RSS_UNAVAILABLE_MAX_ATTEMPTS_PER_CYCLE
                    and RSS_UNAVAILABLE_RETRY_DELAY_SECONDS > 0.0
                ):
                    time.sleep(RSS_UNAVAILABLE_RETRY_DELAY_SECONDS)
        shard.current_resident_bytes = sample.current_resident_bytes
        if sample.current_resident_bytes is not None:
            current_group_total += sample.current_resident_bytes
            current_available = True
        candidate = sample.peak_resident_bytes
        if candidate is None:
            candidate = sample.current_resident_bytes
        if candidate is not None:
            shard.rss_sample_method = sample.method
            shard.rss_successful_sample_count += 1
            shard.peak_resident_bytes = max(
                shard.peak_resident_bytes or 0, candidate
            )
        elif (
            shard.peak_resident_bytes is None
            or shard.process.poll() is None
        ):
            shard.rss_sample_method = sample.method
        if max_process_rss_bytes is not None:
            if candidate is None:
                if (
                    shard.process.poll() is None
                    or shard.peak_resident_bytes is None
                ):
                    unattestable.append(shard.shard_index)
            elif candidate > max_process_rss_bytes:
                exceeded.append(shard.shard_index)
        samples.append(
            {
                "shard_index": shard.shard_index,
                "pid": shard.process.pid,
                "current_resident_bytes": (
                    sample.current_resident_bytes
                ),
                "peak_resident_bytes": shard.peak_resident_bytes,
                "rss_sample_method": sample.method,
                "memory_sampling_supported": candidate is not None,
                "rss_sample_count": shard.rss_sample_count,
                "rss_successful_sample_count": (
                    shard.rss_successful_sample_count
                ),
            }
        )
    return (
        current_group_total if current_available else None,
        sorted(exceeded),
        sorted(unattestable),
        sorted(samples, key=lambda row: row["shard_index"]),
    )


def _request_termination(
    shard: _ActiveShard, *, now_monotonic: float
) -> None:
    if shard.process.poll() is not None:
        return
    if shard.termination_requested_monotonic is None:
        shard.termination_requested_monotonic = now_monotonic
        try:
            shard.process.terminate()
        except OSError:
            # The bounded escalation path below still attempts a hard kill.
            pass


def _advance_termination_escalation(
    active: Mapping[int, _ActiveShard],
    *,
    now_monotonic: float,
    termination_grace_seconds: float,
    kill_reap_timeout_seconds: float,
) -> list[int]:
    """Escalate TERM to kill and return workers that still failed to reap."""

    unreaped: list[int] = []
    for shard in active.values():
        if (
            shard.termination_requested_monotonic is None
            or shard.process.poll() is not None
        ):
            continue
        if shard.kill_requested_monotonic is None:
            if (
                now_monotonic
                - shard.termination_requested_monotonic
                < termination_grace_seconds
            ):
                continue
            shard.kill_requested_monotonic = now_monotonic
            shard.forced_kill = True
            try:
                shard.process.kill()
            except OSError:
                pass
            continue
        if (
            now_monotonic - shard.kill_requested_monotonic
            >= kill_reap_timeout_seconds
        ):
            unreaped.append(shard.shard_index)
    return sorted(unreaped)


def _heartbeat_path(profile_output: Path) -> Path:
    return profile_output.with_name(
        f"{profile_output.name}.heartbeat.json"
    )


def _publication_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _file_binding(path: Path, root: Path) -> dict[str, Any]:
    """Return a canonical publication binding for one immutable input."""

    return {
        "path": _publication_path(path, root),
        "file_sha256": _file_sha256(path),
        "byte_count": path.stat().st_size,
    }


def _file_binding_if_present(path: Path, root: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": _publication_path(path, root),
            "file_sha256": None,
            "byte_count": None,
        }
    return _file_binding(path, root)


def _write_heartbeat(
    *,
    path: Path,
    sequence: int,
    previous_heartbeat_utc: str | None,
    status: str,
    campaign: str,
    pilot_round: int,
    started_utc: str,
    requested_indices: Sequence[int],
    scheduled_indices: Sequence[int],
    pending_indices: Sequence[int],
    active: Mapping[int, _ActiveShard],
    completed_results: Sequence[Mapping[str, Any]],
    observed_failure: bool,
    input_artifact_bindings: Mapping[str, Any],
    ending_input_artifact_bindings: Mapping[str, Any],
    input_artifact_drift: Sequence[str],
    available_indices: Sequence[int],
    execution_mode: str,
    max_process_rss_bytes: int,
    poll_interval_seconds: float,
    heartbeat_interval_seconds: float,
    rss_cap_exceeded_indices: Sequence[int],
    rss_cap_unattestable_indices: Sequence[int],
    process_group_peak_resident_bytes: int | None,
    active_memory_samples: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], str]:
    heartbeat_utc = _utc_now_after(previous_heartbeat_utc)
    value: dict[str, Any] = {
        "schema": HEARTBEAT_SCHEMA,
        "status": status,
        "formal_pass_claimed": False,
        "campaign": campaign,
        "pilot_round": pilot_round,
        "input_artifact_bindings": dict(input_artifact_bindings),
        "ending_input_artifact_bindings": dict(
            ending_input_artifact_bindings
        ),
        "input_artifact_drift": list(input_artifact_drift),
        "available_shard_indices": list(available_indices),
        "execution_mode": execution_mode,
        "started_utc": started_utc,
        "heartbeat_utc": heartbeat_utc,
        "heartbeat_sequence": sequence,
        "requested_shard_indices": list(requested_indices),
        "scheduled_shard_indices": sorted(scheduled_indices),
        "pending_shard_indices": list(pending_indices),
        "active_shard_indices": sorted(active),
        "completed_shard_indices": sorted(
            int(row["shard_index"]) for row in completed_results
        ),
        "failure_observed": observed_failure,
        "max_process_rss_bytes": max_process_rss_bytes,
        "rss_sampling_interval_seconds": poll_interval_seconds,
        "heartbeat_interval_seconds": heartbeat_interval_seconds,
        "termination_grace_seconds": TERMINATION_GRACE_SECONDS,
        "kill_reap_timeout_seconds": KILL_REAP_TIMEOUT_SECONDS,
        "rss_cap_exceeded_shard_indices": sorted(
            rss_cap_exceeded_indices
        ),
        "rss_cap_unattestable_shard_indices": sorted(
            rss_cap_unattestable_indices
        ),
        "process_group_peak_resident_bytes": (
            process_group_peak_resident_bytes
        ),
        "active_memory_samples": list(active_memory_samples),
    }
    projection = dict(value)
    value["self_sha256"] = _canonical_sha256(projection)
    _atomic_json(path, value)
    return value, heartbeat_utc


def _worker_argv(
    *,
    python_executable: Path,
    worker_script: Path,
    root: Path,
    campaign: str,
    pilot_round: int,
    shard_index: int,
    binary: Path,
    build_manifest: Path,
) -> list[str]:
    return [
        str(python_executable),
        str(worker_script),
        "--root",
        str(root),
        "run-shard",
        "--campaign",
        campaign,
        "--shard-index",
        str(shard_index),
        "--binary",
        str(binary),
        "--build-manifest",
        str(build_manifest),
        "--round",
        str(pilot_round),
    ]


def _stream_binding(path: Path) -> dict[str, Any]:
    return {
        "sha256": _file_sha256(path),
        "byte_count": path.stat().st_size,
    }


def run_campaign_shards(
    *,
    root: Path,
    campaign: str,
    pilot_round: int,
    binary: Path,
    build_manifest: Path,
    workers: int,
    shard_tokens: Sequence[str] | None,
    profile_output: Path,
    max_process_rss_mib: float,
    worker_script: Path | None = None,
    python_executable: Path | None = None,
    poll_interval_seconds: float = 0.05,
    heartbeat_interval_seconds: float = 5.0,
    memory_sampler: Callable[[int], MemorySample] | None = None,
    allow_test_memory_sampler: bool = False,
) -> dict[str, Any]:
    """Execute selected immutable plan shards and atomically publish a profile."""

    _require(
        isinstance(workers, int)
        and not isinstance(workers, bool)
        and workers > 0,
        "WORKERS_MUST_BE_POSITIVE",
    )
    _require(
        math.isfinite(poll_interval_seconds)
        and 0.0 < poll_interval_seconds <= 1.0,
        "POLL_INTERVAL_OUT_OF_RANGE",
    )
    _require(
        math.isfinite(heartbeat_interval_seconds)
        and 0.0
        < heartbeat_interval_seconds
        <= MAX_HEARTBEAT_INTERVAL_SECONDS,
        "HEARTBEAT_INTERVAL_OUT_OF_PUBLICATION_RANGE",
    )
    _require(
        isinstance(max_process_rss_mib, (int, float))
        and not isinstance(max_process_rss_mib, bool)
        and math.isfinite(float(max_process_rss_mib))
        and float(max_process_rss_mib) > 0.0,
        "MAX_PROCESS_RSS_MIB_REQUIRED_POSITIVE",
    )
    _require(
        float(max_process_rss_mib)
        <= MAX_PUBLICATION_PROCESS_RSS_MIB,
        "MAX_PROCESS_RSS_MIB_EXCEEDS_PUBLICATION_LIMIT",
    )
    _require(
        isinstance(allow_test_memory_sampler, bool),
        "ALLOW_TEST_MEMORY_SAMPLER_NOT_BOOLEAN",
    )
    if memory_sampler is None:
        selected_memory_sampler = _memory_sample
        execution_mode = "PRODUCTION_NATIVE_PROCESS_TREE_RSS"
    else:
        _require(
            allow_test_memory_sampler,
            "INJECTED_MEMORY_SAMPLER_REQUIRES_EXPLICIT_TEST_MODE",
        )
        selected_memory_sampler = memory_sampler
        execution_mode = "TEST_ONLY_INJECTED_MEMORY_SAMPLER"
    max_process_rss_bytes = int(
        float(max_process_rss_mib) * 1024 * 1024
    )
    _require(
        max_process_rss_bytes > 0,
        "MAX_PROCESS_RSS_CAP_BELOW_ONE_BYTE",
    )
    root = root.resolve(strict=True)
    binary = (
        binary if binary.is_absolute() else root / binary
    ).resolve(strict=True)
    build_manifest = (
        build_manifest
        if build_manifest.is_absolute()
        else root / build_manifest
    ).resolve(strict=True)
    profile_output = (
        profile_output
        if profile_output.is_absolute()
        else root / profile_output
    ).resolve()
    worker_script = (
        worker_script
        if worker_script is not None
        else root / "scripts/eval/g4irsf15_causal_campaign.py"
    )
    worker_script = (
        worker_script
        if worker_script.is_absolute()
        else root / worker_script
    ).resolve(strict=True)
    python_executable = (
        python_executable or Path(sys.executable)
    ).resolve(strict=True)
    orchestrator_script = Path(__file__).resolve(strict=True)
    plan, plan_relative, available_indices = _load_plan(
        root, campaign, pilot_round
    )
    plan_path = root / plan_relative
    shard_inventory = [
        {
            "shard_index": shard_index,
            "shard_sha256": plan["shards"][shard_index][
                "shard_sha256"
            ],
        }
        for shard_index in available_indices
    ]
    plan_file_binding = _file_binding(plan_path, root)
    plan_binding = dict(plan_file_binding)
    plan_binding.update(
        {
            "self_sha256": plan.get("self_sha256"),
            "shard_count": len(available_indices),
            "available_shard_indices": available_indices,
            "shard_inventory": shard_inventory,
            "shard_inventory_sha256": _canonical_sha256(
                shard_inventory
            ),
        }
    )
    input_artifact_bindings: dict[str, Any] = {
        "plan": plan_file_binding,
        "binary": _file_binding(binary, root),
        "build_manifest": _file_binding(build_manifest, root),
        "worker_script": _file_binding(worker_script, root),
        "orchestrator_script": _file_binding(
            orchestrator_script, root
        ),
    }
    ending_input_artifact_bindings: dict[str, Any] = dict(
        input_artifact_bindings
    )
    input_artifact_drift: list[str] = []
    requested_indices = _parse_shard_tokens(
        shard_tokens, available_indices=available_indices
    )
    effective_workers = min(workers, len(requested_indices))
    started_utc = _utc_now()
    started_monotonic = time.perf_counter()
    pending = list(requested_indices)
    active: dict[int, _ActiveShard] = {}
    results: list[dict[str, Any]] = []
    scheduled_indices: list[int] = []
    observed_failure = False
    first_failure_shard_index: int | None = None
    process_group_peak: int | None = None
    launch_error: str | None = None
    rss_cap_exceeded_indices: set[int] = set()
    rss_cap_unattestable_indices: set[int] = set()
    heartbeat_output = _heartbeat_path(profile_output)
    heartbeat_timestamps: list[str] = []
    heartbeat_sequence = 0
    last_heartbeat_monotonic: float | None = None
    last_active_memory_samples: list[dict[str, Any]] = []
    profile_output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".g4irsf15-shard-streams-",
        dir=str(profile_output.parent),
    ) as stream_directory_text:
        stream_directory = Path(stream_directory_text)

        def launch(shard_index: int) -> None:
            nonlocal launch_error
            nonlocal observed_failure
            nonlocal first_failure_shard_index
            argv = _worker_argv(
                python_executable=python_executable,
                worker_script=worker_script,
                root=root,
                campaign=campaign,
                pilot_round=pilot_round,
                shard_index=shard_index,
                binary=binary,
                build_manifest=build_manifest,
            )
            stdout_path = stream_directory / f"{shard_index:06d}.stdout"
            stderr_path = stream_directory / f"{shard_index:06d}.stderr"
            stdout_handle = stdout_path.open("wb")
            stderr_handle = stderr_path.open("wb")
            popen_options: dict[str, Any] = {
                "cwd": root,
                "stdin": subprocess.DEVNULL,
                "stdout": stdout_handle,
                "stderr": stderr_handle,
                "shell": False,
            }
            if os.name == "nt":
                popen_options["creationflags"] = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                popen_options["start_new_session"] = True
            try:
                process = subprocess.Popen(argv, **popen_options)
            except OSError as exc:
                stdout_handle.close()
                stderr_handle.close()
                observed_failure = True
                if first_failure_shard_index is None:
                    first_failure_shard_index = shard_index
                launch_error = (
                    f"{type(exc).__name__}:{exc}"
                )
                empty_sha = hashlib.sha256(b"").hexdigest()
                results.append(
                    {
                        "shard_index": shard_index,
                        "argv": argv,
                        "pid": None,
                        "started_utc": _utc_now(),
                        "finished_utc": _utc_now(),
                        "elapsed_wall_seconds": 0.0,
                        "return_code": None,
                        "launch_error": launch_error,
                        "orchestration_failure_reason": (
                            "PROCESS_LAUNCH_FAILED"
                        ),
                        "stdout": {
                            "sha256": empty_sha,
                            "byte_count": 0,
                        },
                        "stderr": {
                            "sha256": empty_sha,
                            "byte_count": 0,
                        },
                        "peak_resident_bytes": None,
                        "rss_sample_method": "PROCESS_NOT_LAUNCHED",
                        "rss_sample_count": 0,
                        "rss_successful_sample_count": 0,
                        "memory_sampling_supported": False,
                        "termination_requested": False,
                        "forced_kill": False,
                    }
                )
                return
            scheduled_indices.append(shard_index)
            active[shard_index] = _ActiveShard(
                shard_index=shard_index,
                argv=argv,
                process=process,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
                started_utc=_utc_now(),
                started_monotonic=time.perf_counter(),
            )

        def emit_heartbeat(
            status: str,
            samples: Sequence[Mapping[str, Any]],
        ) -> None:
            nonlocal heartbeat_sequence
            nonlocal last_heartbeat_monotonic
            heartbeat_sequence += 1
            _, heartbeat_utc = _write_heartbeat(
                path=heartbeat_output,
                sequence=heartbeat_sequence,
                previous_heartbeat_utc=(
                    heartbeat_timestamps[-1]
                    if heartbeat_timestamps
                    else None
                ),
                status=status,
                campaign=campaign,
                pilot_round=pilot_round,
                started_utc=started_utc,
                requested_indices=requested_indices,
                scheduled_indices=scheduled_indices,
                pending_indices=pending,
                active=active,
                completed_results=results,
                observed_failure=observed_failure,
                input_artifact_bindings=input_artifact_bindings,
                ending_input_artifact_bindings=(
                    ending_input_artifact_bindings
                ),
                input_artifact_drift=input_artifact_drift,
                available_indices=available_indices,
                execution_mode=execution_mode,
                max_process_rss_bytes=max_process_rss_bytes,
                poll_interval_seconds=poll_interval_seconds,
                heartbeat_interval_seconds=(
                    heartbeat_interval_seconds
                ),
                rss_cap_exceeded_indices=sorted(
                    rss_cap_exceeded_indices
                ),
                rss_cap_unattestable_indices=sorted(
                    rss_cap_unattestable_indices
                ),
                process_group_peak_resident_bytes=process_group_peak,
                active_memory_samples=samples,
            )
            heartbeat_timestamps.append(heartbeat_utc)
            last_heartbeat_monotonic = time.perf_counter()

        try:
            while pending or active:
                while (
                    pending
                    and not observed_failure
                    and len(active) < effective_workers
                ):
                    launch(pending.pop(0))
                (
                    group_current,
                    cap_exceeded,
                    cap_unattestable,
                    last_active_memory_samples,
                ) = _update_memory(
                    active,
                    sampler=selected_memory_sampler,
                    max_process_rss_bytes=max_process_rss_bytes,
                )
                if group_current is not None:
                    process_group_peak = max(
                        process_group_peak or 0, group_current
                    )
                if cap_exceeded or cap_unattestable:
                    observed_failure = True
                    rss_cap_exceeded_indices.update(cap_exceeded)
                    rss_cap_unattestable_indices.update(
                        cap_unattestable
                    )
                    cap_failure_indices = sorted(
                        set(cap_exceeded) | set(cap_unattestable)
                    )
                    if first_failure_shard_index is None:
                        first_failure_shard_index = min(
                            cap_failure_indices
                        )
                    newly_failed_indices = [
                        shard_index
                        for shard_index in cap_failure_indices
                        if active[
                            shard_index
                        ].orchestration_failure_reason
                        is None
                    ]
                    for shard_index in cap_failure_indices:
                        shard = active[shard_index]
                        reason = (
                            "PROCESS_RSS_CAP_EXCEEDED"
                            if shard_index in cap_exceeded
                            else "PROCESS_RSS_CAP_UNATTESTABLE"
                        )
                        if shard.orchestration_failure_reason is None:
                            shard.orchestration_failure_reason = reason
                    for sample in last_active_memory_samples:
                        shard_index = int(sample["shard_index"])
                        sample["rss_cap_exceeded"] = (
                            shard_index in cap_exceeded
                        )
                        sample["rss_cap_unattestable"] = (
                            shard_index in cap_unattestable
                        )
                    if newly_failed_indices:
                        emit_heartbeat(
                            "RSS_CAP_VIOLATION_OBSERVED",
                            last_active_memory_samples,
                        )
                    termination_request_time = time.perf_counter()
                    for shard_index in cap_failure_indices:
                        _request_termination(
                            active[shard_index],
                            now_monotonic=termination_request_time,
                        )
                unreaped_after_kill = _advance_termination_escalation(
                    active,
                    now_monotonic=time.perf_counter(),
                    termination_grace_seconds=(
                        TERMINATION_GRACE_SECONDS
                    ),
                    kill_reap_timeout_seconds=(
                        KILL_REAP_TIMEOUT_SECONDS
                    ),
                )
                _require(
                    not unreaped_after_kill,
                    "WORKER_FAILED_TO_REAP_AFTER_KILL:"
                    f"{unreaped_after_kill}",
                )
                completed_indices: list[int] = []
                completed_failures: list[int] = []
                for shard_index, shard in sorted(active.items()):
                    return_code = shard.process.poll()
                    if return_code is None:
                        continue
                    shard.stdout_handle.close()
                    shard.stderr_handle.close()
                    finished_monotonic = time.perf_counter()
                    result = {
                        "shard_index": shard_index,
                        "argv": shard.argv,
                        "pid": shard.process.pid,
                        "started_utc": shard.started_utc,
                        "finished_utc": _utc_now(),
                        "elapsed_wall_seconds": (
                            finished_monotonic
                            - shard.started_monotonic
                        ),
                        "return_code": return_code,
                        "launch_error": None,
                        "orchestration_failure_reason": (
                            shard.orchestration_failure_reason
                        ),
                        "stdout": _stream_binding(shard.stdout_path),
                        "stderr": _stream_binding(shard.stderr_path),
                        "peak_resident_bytes": (
                            shard.peak_resident_bytes
                        ),
                        "rss_sample_method": shard.rss_sample_method,
                        "rss_sample_count": shard.rss_sample_count,
                        "rss_successful_sample_count": (
                            shard.rss_successful_sample_count
                        ),
                        "memory_sampling_supported": (
                            shard.peak_resident_bytes is not None
                        ),
                        "termination_requested": (
                            shard.termination_requested_monotonic
                            is not None
                        ),
                        "forced_kill": shard.forced_kill,
                    }
                    results.append(result)
                    completed_indices.append(shard_index)
                    if (
                        return_code != 0
                        or shard.orchestration_failure_reason is not None
                    ):
                        completed_failures.append(shard_index)
                if completed_failures:
                    observed_failure = True
                    if first_failure_shard_index is None:
                        first_failure_shard_index = min(
                            completed_failures
                        )
                for shard_index in completed_indices:
                    active.pop(shard_index)
                active_sample_rows = [
                    sample
                    for sample in last_active_memory_samples
                    if int(sample["shard_index"]) in active
                ]
                now_monotonic = time.perf_counter()
                if (
                    last_heartbeat_monotonic is None
                    or now_monotonic - last_heartbeat_monotonic
                    >= heartbeat_interval_seconds
                ):
                    emit_heartbeat(
                        (
                            "FAILURE_OBSERVED_DRAINING"
                            if observed_failure and active
                            else "RUNNING"
                        ),
                        active_sample_rows,
                    )
                if active:
                    time.sleep(poll_interval_seconds)
                elif pending and not observed_failure:
                    continue
                elif pending and observed_failure:
                    break
        except BaseException:
            cleanup_started = time.perf_counter()
            for shard in active.values():
                _request_termination(
                    shard, now_monotonic=cleanup_started
                )
            for shard in active.values():
                try:
                    shard.process.wait(
                        timeout=TERMINATION_GRACE_SECONDS
                    )
                except subprocess.TimeoutExpired:
                    try:
                        shard.process.kill()
                    except OSError:
                        pass
                    try:
                        shard.process.wait(
                            timeout=KILL_REAP_TIMEOUT_SECONDS
                        )
                    except subprocess.TimeoutExpired:
                        pass
                shard.stdout_handle.close()
                shard.stderr_handle.close()
            raise

        _require(
            not active,
            "INTERNAL_ACTIVE_PROCESS_REAP_DRIFT",
        )
        results.sort(key=lambda row: int(row["shard_index"]))
        missing_success_rss = [
            row
            for row in results
            if row["return_code"] == 0
            and row.get("orchestration_failure_reason") is None
            and row.get("peak_resident_bytes") is None
        ]
        for row in missing_success_rss:
            row["orchestration_failure_reason"] = (
                "PROCESS_RSS_CAP_UNATTESTABLE"
            )
            rss_cap_unattestable_indices.add(
                int(row["shard_index"])
            )
        if missing_success_rss:
            observed_failure = True
            if first_failure_shard_index is None:
                first_failure_shard_index = min(
                    int(row["shard_index"])
                    for row in missing_success_rss
                )
        nonproduction_success_rss = [
            row
            for row in results
            if execution_mode
            == "PRODUCTION_NATIVE_PROCESS_TREE_RSS"
            and row["return_code"] == 0
            and row.get("orchestration_failure_reason") is None
            and (
                row.get("rss_sample_method")
                not in PRODUCTION_RSS_METHODS
                or not row.get("memory_sampling_supported")
                or int(row.get("rss_successful_sample_count", 0)) <= 0
            )
        ]
        for row in nonproduction_success_rss:
            row["orchestration_failure_reason"] = (
                "PROCESS_RSS_METHOD_NOT_PRODUCTION_TREE"
            )
            rss_cap_unattestable_indices.add(
                int(row["shard_index"])
            )
        if nonproduction_success_rss:
            observed_failure = True
            if first_failure_shard_index is None:
                first_failure_shard_index = min(
                    int(row["shard_index"])
                    for row in nonproduction_success_rss
                )
        ending_input_artifact_bindings = {
            "plan": _file_binding_if_present(plan_path, root),
            "binary": _file_binding_if_present(binary, root),
            "build_manifest": _file_binding_if_present(
                build_manifest, root
            ),
            "worker_script": _file_binding_if_present(
                worker_script, root
            ),
            "orchestrator_script": _file_binding_if_present(
                orchestrator_script, root
            ),
        }
        input_artifact_drift = sorted(
            name
            for name, initial_binding in input_artifact_bindings.items()
            if ending_input_artifact_bindings[name]
            != initial_binding
        )
        if input_artifact_drift:
            observed_failure = True
        attempted_set = {
            int(row["shard_index"]) for row in results
        }
        scheduled_set = set(scheduled_indices)
        unscheduled_indices = [
            index
            for index in requested_indices
            if index not in attempted_set
        ]
        successful_count = sum(
            row["return_code"] == 0
            and row.get("orchestration_failure_reason") is None
            for row in results
        )
        failed_count = len(results) - successful_count
        status = (
            "COMPLETE"
            if not observed_failure
            and not unscheduled_indices
            and failed_count == 0
            else "FAILED_INPUT_ARTIFACT_DRIFT"
            if input_artifact_drift
            else "FAILED_PROCESS_RSS_CAP"
            if rss_cap_exceeded_indices
            or rss_cap_unattestable_indices
            else "FAILED_STOPPED_SCHEDULING"
        )
        emit_heartbeat(status, [])
        finished_monotonic = time.perf_counter()
        finished_utc = _utc_now()
        elapsed = finished_monotonic - started_monotonic
        heartbeat = _load_json(heartbeat_output)
        report: dict[str, Any] = {
            "schema": PROFILE_SCHEMA,
            "status": status,
            "formal_pass_claimed": False,
            "campaign": campaign,
            "pilot_round": pilot_round,
            "execution_mode": execution_mode,
            "resume_policy": (
                "DELEGATED_TO_IDEMPOTENT_RUN_SHARD_VALIDATION"
            ),
            "worker_process_policy": (
                "ONE_FRESH_SUBPROCESS_PER_SHARD_SHELL_FALSE"
            ),
            "failure_policy": (
                "STOP_SCHEDULING_ON_FIRST_OBSERVED_FAILURE_THEN_REAP_ALL"
            ),
            "termination_policy": (
                "TERM_THEN_BOUNDED_GRACE_THEN_KILL_THEN_BOUNDED_REAP"
            ),
            "termination_grace_seconds": TERMINATION_GRACE_SECONDS,
            "kill_reap_timeout_seconds": KILL_REAP_TIMEOUT_SECONDS,
            "publication_execution_contract": {
                "max_allowed_process_rss_mib": (
                    MAX_PUBLICATION_PROCESS_RSS_MIB
                ),
                "max_allowed_heartbeat_interval_seconds": (
                    MAX_HEARTBEAT_INTERVAL_SECONDS
                ),
                "required_memory_scope": (
                    "PER_SHARD_WORKER_PROCESS_TREE_RESIDENT_BYTES"
                ),
                "production_rss_sample_methods": sorted(
                    PRODUCTION_RSS_METHODS
                ),
            },
            "input_artifact_bindings": input_artifact_bindings,
            "ending_input_artifact_bindings": (
                ending_input_artifact_bindings
            ),
            "input_artifact_drift": input_artifact_drift,
            "plan": plan_binding,
            "binary_sha256": input_artifact_bindings["binary"][
                "file_sha256"
            ],
            "build_manifest_sha256": input_artifact_bindings[
                "build_manifest"
            ]["file_sha256"],
            "python_executable": str(python_executable),
            "worker_script": str(worker_script),
            "worker_count_requested": workers,
            "worker_count_effective": effective_workers,
            "requested_shard_indices": requested_indices,
            "launch_attempted_shard_indices": sorted(attempted_set),
            "scheduled_shard_indices": sorted(scheduled_set),
            "unscheduled_shard_indices": unscheduled_indices,
            "completed_result_count": len(results),
            "successful_shard_count": successful_count,
            "failed_shard_count": failed_count,
            "first_failure_shard_index": first_failure_shard_index,
            "launch_error": launch_error,
            "started_utc": started_utc,
            "finished_utc": finished_utc,
            "elapsed_wall_seconds": elapsed,
            "throughput": {
                "completed_shards_per_wall_second": (
                    len(results) / elapsed if elapsed > 0.0 else None
                ),
                "successful_shards_per_wall_second": (
                    successful_count / elapsed
                    if elapsed > 0.0
                    else None
                ),
            },
            "process_group_peak_resident_bytes": process_group_peak,
            "process_group_rss_scope": (
                "SUM_OF_CONCURRENT_SHARD_WORKER_PROCESS_TREE_RSS_SAMPLES"
            ),
            "rss_sampling_interval_seconds": poll_interval_seconds,
            "memory_sampling": {
                "execution_mode": execution_mode,
                "production_native_sampler": (
                    execution_mode
                    == "PRODUCTION_NATIVE_PROCESS_TREE_RSS"
                ),
                "injected_sampler": (
                    execution_mode
                    == "TEST_ONLY_INJECTED_MEMORY_SAMPLER"
                ),
                "required_complete_profile_methods": sorted(
                    PRODUCTION_RSS_METHODS
                ),
                "fail_closed_on_unavailable_process_or_child": True,
                "unavailable_sample_retry": {
                    "max_attempts_per_cycle": (
                        RSS_UNAVAILABLE_MAX_ATTEMPTS_PER_CYCLE
                    ),
                    "retry_delay_seconds": (
                        RSS_UNAVAILABLE_RETRY_DELAY_SECONDS
                    ),
                    "persistent_unavailability_is_failure": True,
                },
            },
            "process_rss_cap": {
                "configured": True,
                "required_for_publication_execution": True,
                "max_process_rss_mib": float(max_process_rss_mib),
                "max_process_rss_bytes": max_process_rss_bytes,
                "policy": (
                    "FAIL_CLOSED_STOP_SCHEDULING_TERMINATE_ONLY_"
                    "OFFENDING_WORKER;PERSISTENT_UNAVAILABLE_"
                    "LOGICAL_SAMPLE_IS_FAILURE"
                ),
                "cap_scope": (
                    "PER_SHARD_WORKER_PROCESS_TREE_RESIDENT_BYTES"
                ),
                "exceeded_shard_indices": sorted(
                    rss_cap_exceeded_indices
                ),
                "unattestable_shard_indices": sorted(
                    rss_cap_unattestable_indices
                ),
            },
            "liveness": {
                "heartbeat_path": _publication_path(
                    heartbeat_output, root
                ),
                "heartbeat_file_sha256": _file_sha256(
                    heartbeat_output
                ),
                "heartbeat_self_sha256": heartbeat.get(
                    "self_sha256"
                ),
                "heartbeat_interval_seconds": (
                    heartbeat_interval_seconds
                ),
                "poll_interval_seconds": poll_interval_seconds,
                "rss_sampling_interval_seconds": (
                    poll_interval_seconds
                ),
                "heartbeat_count": heartbeat_sequence,
                "heartbeat_timestamps_utc": heartbeat_timestamps,
                "final_heartbeat_status": heartbeat.get("status"),
                "final_heartbeat_sequence": heartbeat.get(
                    "heartbeat_sequence"
                ),
            },
            "publication_execution_attestation": {
                "profile_status_complete": status == "COMPLETE",
                "input_artifacts_stable": not input_artifact_drift,
                "rss_cap_configured": True,
                "production_native_memory_sampling": (
                    execution_mode
                    == "PRODUCTION_NATIVE_PROCESS_TREE_RSS"
                ),
                "all_successful_shards_have_peak_rss": all(
                    row["return_code"] != 0
                    or row.get("orchestration_failure_reason")
                    is not None
                    or row.get("peak_resident_bytes") is not None
                    for row in results
                ),
                "final_heartbeat_complete": (
                    heartbeat.get("status") == "COMPLETE"
                ),
                "final_heartbeat_self_hash_bound": bool(
                    heartbeat.get("self_sha256")
                ),
            },
            "shards": results,
        }
        projection = dict(report)
        report["self_sha256"] = _canonical_sha256(projection)
        _atomic_json(profile_output, report)
        return report


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "workers must be a positive integer"
        ) from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            "workers must be a positive integer"
        )
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "value must be a positive finite number"
        ) from exc
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError(
            "value must be a positive finite number"
        )
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--campaign",
        choices=("pilot", "formal"),
        required=True,
    )
    parser.add_argument(
        "--round",
        dest="pilot_round",
        type=int,
        choices=(1, 2),
        default=1,
    )
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument(
        "--build-manifest", type=Path, required=True
    )
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=1,
        help=(
            "Maximum concurrent fresh workers; 1, 2, and 4 are standard, "
            "and any positive integer is accepted."
        ),
    )
    parser.add_argument(
        "--shards",
        "--shard-indices",
        nargs="+",
        default=["all"],
        help=(
            "Use 'all' (default), indices, comma-separated indices, or "
            "inclusive ranges such as 0-3."
        ),
    )
    parser.add_argument(
        "--profile-output",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--max-process-rss-mib",
        type=_positive_float,
        required=True,
        help=(
            "Required fail-closed per-worker RSS ceiling in MiB. "
            "Scheduling stops and only an offending worker is terminated "
            "when the ceiling is exceeded; unavailable RSS is always a "
            "publication-execution failure."
        ),
    )
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=_positive_float,
        default=5.0,
        help=(
            "Atomic liveness-heartbeat publication interval "
            "(default: 5 seconds)."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    report = run_campaign_shards(
        root=arguments.root,
        campaign=arguments.campaign,
        pilot_round=arguments.pilot_round,
        binary=arguments.binary,
        build_manifest=arguments.build_manifest,
        workers=arguments.workers,
        shard_tokens=arguments.shards,
        profile_output=arguments.profile_output,
        max_process_rss_mib=arguments.max_process_rss_mib,
        heartbeat_interval_seconds=(
            arguments.heartbeat_interval_seconds
        ),
    )
    print(
        json.dumps(
            {
                "schema": report["schema"],
                "status": report["status"],
                "self_sha256": report["self_sha256"],
                "successful_shard_count": report[
                    "successful_shard_count"
                ],
                "failed_shard_count": report[
                    "failed_shard_count"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OrchestratorError as exc:
        print(
            f"G4IRSF15_SHARD_ORCHESTRATOR_ERROR:{exc}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
