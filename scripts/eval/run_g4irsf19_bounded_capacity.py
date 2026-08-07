#!/usr/bin/env python3
"""Measure the G19 live scale frontier without an external timeout black box.

The native G19 wall bound returns an unfinalized, read-only progress snapshot.
This runner applies that seam to the real G18 distribution-preserving fixed-map
scale inputs while retaining the frozen J2 runtime controls.  It records only
compact progress and summary evidence; bag rows are discarded immediately.

This is deliberately not a checkpoint/restart implementation.  It also does
not claim a CPU-category profile: process CPU and point-in-time RSS samples are
the only host-cost observations collected here.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))


SCHEMA_JOB = "czr005.g4irsf19.bounded_capacity_job.v1"
DEFAULT_OUTPUT_DIR = ROOT / "outputs/runtime/g4irsf19_bounded_capacity"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf19_scale_capacity.csv"
DEFAULT_FRONTIER_REPORT = ROOT / "outputs/reports/g4irsf19_live_frontier_and_cost.md"
DEFAULT_CAPACITY_REPORT = ROOT / "outputs/reports/g4irsf19_scale_capacity.md"

ALLOWED_SCALES = (1, 2, 4)
SCORER_MODES = {
    "S1": "S1_frozen_g4e_legal_local_adapter",
    "S2": "S2_frozen_g4e_without_absolute_node_ids",
    "S3": "S3_shortest_potential_only",
    "S4": "S4_queue_aware_rule_only",
}
EVENT_TYPES = (
    "bag_release",
    "arrive_junction",
    "junction_service_complete",
    "edge_enter",
    "edge_exit",
    "fault",
    "repair",
    "local_queue_update",
    "congestion_beacon_update",
)

Executor = Callable[..., Mapping[str, Any]]
InputLoader = Callable[[int, Path], tuple[list[dict[str, Any]], dict[str, Any]]]
RssReader = Callable[[], tuple[float | None, str]]


class BoundedCapacityError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BoundedCapacityError(message)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_bytes(path, _json_bytes(value))


def _atomic_text(path: Path, value: str) -> None:
    _atomic_bytes(path, value.encode("utf-8"))


def _rss_sample_mb() -> tuple[float | None, str]:
    """Return one current-process RSS sample, not a peak measurement."""

    try:
        import psutil  # type: ignore[import-not-found]

        value = psutil.Process(os.getpid()).memory_info().rss
        return value / (1024.0 * 1024.0), "psutil_current_process_rss"
    except (ImportError, OSError):
        return None, "unavailable"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            value = json.loads(line)
            _require(isinstance(value, dict), f"non-object JSONL row: {path}")
            rows.append(value)
    _require(bool(rows), f"empty scale input: {path}")
    return rows


def load_g18_scale_input(
    scale: int, root: Path = ROOT
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load the exact G18/G10 fixed-map, distribution-preserving scale input."""

    del root  # The G10 generator owns its canonical cache location.
    from scripts.eval import run_g4irsf10_v2_safe_scale_hardcase_training as g10

    path, metadata = g10.ensure_source_queue_for_case(
        scale=scale,
        rolling_days=1,
        time_compression=1.0,
        label=f"g4irsf19_bounded_capacity_{scale}x",
    )
    rows = _load_jsonl(path)
    descriptor = {
        "protocol": "g4irsf10_distribution_preserving_fixed_map_resample",
        "segments": len(rows),
        "scale": scale,
        "topology_changed": bool(metadata.get("topology_changed", False)),
        "tth_denominator": "java_release_time_tth",
    }
    _require(descriptor["topology_changed"] is False, "scale input changed topology")
    return rows, descriptor


def _binding_rows(rows: Sequence[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (
            str(row["segment_id"]),
            int(row["task_id"]),
            float(row["pass_time"]),
            float(row["std"]),
            int(row["start"]),
            int(row["goal"]),
            str(row.get("source", f"node_{int(row['start'])}")),
        )
        for row in rows
    ]


def build_native_request(
    rows: Sequence[Mapping[str, Any]],
    *,
    scale: int,
    scorer: str,
    binary: Path,
    root: Path,
    max_wall_seconds: float,
    check_events: int,
) -> dict[str, Any]:
    from scripts.eval.g4irsf11_fixed_map import assert_canonical_map, canonical_graph_records
    from scripts.eval.g4irsf14_opportunity_census import FROZEN_RUNTIME_CONTROLS, MODEL_PATH

    _require(scale in ALLOWED_SCALES, f"scale must be one of {ALLOWED_SCALES}")
    _require(scorer in SCORER_MODES, f"unknown scorer: {scorer}")
    _require(max_wall_seconds > 0.0, "max wall seconds must be positive")
    _require(check_events > 0, "check events must be positive")
    resolved_binary = binary.resolve(strict=True)
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=_binding_rows(rows),
        fault_windows=(),
        scenario=f"g4irsf19_bounded_capacity_{scale}x_{scorer.lower()}",
        summary_only=True,
        trace_limit=0,
        event_trace_limit=0,
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=0,
        expected_binary_path=resolved_binary,
        search_path=resolved_binary.parent,
        g4irsf16_supervisor_mode="off",
        # G18's strongest deterministic local mainline is J2.
        merge_grant_rule="M3",
        merge_grant_timing_mode="jit_fair_aging_deadline",
        scorer_mode=SCORER_MODES[scorer],
        bounded_wall_seconds=float(max_wall_seconds),
        bounded_check_every_events=int(check_events),
    )
    if scorer in {"S1", "S2"}:
        request["scorer_model_path"] = (root / MODEL_PATH).resolve(strict=True)
    else:
        # S3/S4 are existing model-free scorers; the wrapper rejects a model
        # path for these modes, so absence is part of the request contract.
        request.pop("scorer_model_path", None)
    return request


def _zero_progress(requested: int) -> dict[str, Any]:
    return {
        "phase": "READY",
        "wall_seconds": 0.0,
        "simulated_time": 0.0,
        "requested_bags": requested,
        "released_bags": 0,
        "completed_bags": 0,
        "failed_bags": 0,
        "terminal_bags": 0,
        "current_backlog": 0,
        "event_total": 0,
        "heap_size": requested,
        "event_type_counts": {name: 0 for name in EVENT_TYPES},
        "source_admission_attempt_count": 0,
        "source_admission_admitted_count": 0,
        "source_admission_hold_count": 0,
        "stale_event_count": 0,
        "retry_count_by_reason": {"merge_contended_loser": 0},
        "duplicate_wakeup_count": 0,
        "coalesced_event_count": 0,
    }


def _compact_progress(value: Mapping[str, Any], requested: int) -> dict[str, Any]:
    event_types = value.get("event_type_counts")
    retries = value.get("retry_count_by_reason")
    return {
        "phase": str(value.get("phase", "READY")),
        "wall_seconds": _finite(value.get("wall_seconds")) or 0.0,
        "simulated_time": _finite(value.get("simulated_time")) or 0.0,
        "requested_bags": _integer(value.get("requested_bags")) or requested,
        "released_bags": _integer(value.get("released_bags")) or 0,
        "completed_bags": _integer(value.get("completed_bags")) or 0,
        "failed_bags": _integer(value.get("failed_bags")) or 0,
        "terminal_bags": _integer(value.get("terminal_bags")) or 0,
        "current_backlog": _integer(value.get("current_backlog")) or 0,
        "event_total": _integer(value.get("event_total")) or 0,
        "heap_size": _integer(value.get("heap_size")) or 0,
        "event_type_counts": {
            name: (
                _integer(event_types.get(name)) or 0
                if isinstance(event_types, Mapping)
                else 0
            )
            for name in EVENT_TYPES
        },
        "source_admission_attempt_count": (
            _integer(value.get("source_admission_attempt_count")) or 0
        ),
        "source_admission_admitted_count": (
            _integer(value.get("source_admission_admitted_count")) or 0
        ),
        "source_admission_hold_count": (
            _integer(value.get("source_admission_hold_count")) or 0
        ),
        "stale_event_count": _integer(value.get("stale_event_count")) or 0,
        "retry_count_by_reason": {
            "merge_contended_loser": (
                _integer(retries.get("merge_contended_loser")) or 0
                if isinstance(retries, Mapping)
                else 0
            )
        },
        "duplicate_wakeup_count": (
            _integer(value.get("duplicate_wakeup_count")) or 0
        ),
        "coalesced_event_count": (
            _integer(value.get("coalesced_event_count")) or 0
        ),
    }


def _completed_progress(
    summary: Mapping[str, Any], requested: int, wall_seconds: float
) -> dict[str, Any]:
    completed = _integer(summary.get("completed_count")) or 0
    failed = _integer(summary.get("failed_count")) or 0
    event_types = {
        name: _integer(summary.get(f"{name}_event_count")) or 0
        for name in EVENT_TYPES
    }
    return _compact_progress(
        {
            "phase": "FINALIZED",
            "wall_seconds": wall_seconds,
            "simulated_time": summary.get("end_time", 0.0),
            "requested_bags": _integer(summary.get("requested_count")) or requested,
            "released_bags": summary.get("bag_release_event_count", requested),
            "completed_bags": completed,
            "failed_bags": failed,
            "terminal_bags": completed + failed,
            "current_backlog": summary.get("final_active_bag_count", 0),
            "event_total": summary.get("event_count", 0),
            "heap_size": 0,
            "event_type_counts": event_types,
            "source_admission_attempt_count": summary.get(
                "source_admission_attempt_count", 0
            ),
            "source_admission_admitted_count": summary.get(
                "source_admission_admitted_count", 0
            ),
            "source_admission_hold_count": (
                (_integer(summary.get("source_admission_local_resource_hold_count")) or 0)
                + (
                    _integer(
                        summary.get("source_admission_downstream_pressure_hold_count")
                    )
                    or 0
                )
            ),
            "stale_event_count": sum(
                _integer(summary.get(name)) or 0
                for name in (
                    "stale_arbitration_event_count",
                    "merge_grant_stale_arbitration_count",
                    "merge_grant_stale_wakeup_count",
                )
            ),
            "retry_count_by_reason": {
                "merge_contended_loser": summary.get(
                    "merge_grant_contended_loser_retry_count", 0
                )
            },
            "duplicate_wakeup_count": summary.get(
                "merge_grant_duplicate_wakeup_prevented_count", 0
            ),
            "coalesced_event_count": summary.get(
                "merge_grant_wakeup_coalesced_count", 0
            ),
        },
        requested,
    )


def progress_history_from_payload(
    payload: Mapping[str, Any], *, requested: int, wall_seconds: float
) -> tuple[list[dict[str, Any]], str]:
    """Return compact samples and disclose whether native history existed."""

    if payload.get("execution_status") == "BOUNDED_PROGRESS":
        raw = payload.get("progress_history")
        samples = [
            _compact_progress(row, requested)
            for row in raw
            if isinstance(row, Mapping)
        ] if isinstance(raw, list) else []
        final = payload.get("progress")
        if isinstance(final, Mapping):
            compact_final = _compact_progress(final, requested)
            if not samples or (
                samples[-1]["wall_seconds"], samples[-1]["event_total"]
            ) != (
                compact_final["wall_seconds"], compact_final["event_total"]
            ):
                samples.append(compact_final)
        samples.sort(key=lambda row: float(row["wall_seconds"]))
        if not samples:
            samples = [_zero_progress(requested)]
        return samples, "native_bounded_progress_history"

    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    return [
        _zero_progress(requested),
        _completed_progress(summary, requested, wall_seconds),
    ], "synthesized_start_and_finalized_endpoint"


def _nested_number(row: Mapping[str, Any], *keys: str) -> float:
    value: Any = row
    for key in keys:
        if not isinstance(value, Mapping):
            return 0.0
        value = value.get(key)
    return _finite(value) or 0.0


def _endpoint_slope(
    history: Sequence[Mapping[str, Any]], *keys: str
) -> float | None:
    if len(history) < 2:
        return None
    first, last = history[0], history[-1]
    elapsed = _nested_number(last, "wall_seconds") - _nested_number(
        first, "wall_seconds"
    )
    if elapsed <= 0.0:
        return None
    return (_nested_number(last, *keys) - _nested_number(first, *keys)) / elapsed


def progress_slopes(history: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    return {
        "events_per_wall_second": _endpoint_slope(history, "event_total"),
        "releases_per_wall_second": _endpoint_slope(history, "released_bags"),
        "completions_per_wall_second": _endpoint_slope(history, "completed_bags"),
        "backlog_change_per_wall_second": _endpoint_slope(
            history, "current_backlog"
        ),
        "simulated_seconds_per_wall_second": _endpoint_slope(
            history, "simulated_time"
        ),
        "merge_retries_per_wall_second": _endpoint_slope(
            history, "retry_count_by_reason", "merge_contended_loser"
        ),
        "duplicate_wakeups_per_wall_second": _endpoint_slope(
            history, "duplicate_wakeup_count"
        ),
        "coalesced_events_per_wall_second": _endpoint_slope(
            history, "coalesced_event_count"
        ),
        "stale_events_per_wall_second": _endpoint_slope(
            history, "stale_event_count"
        ),
    }


def event_type_ratios(
    history: Sequence[Mapping[str, Any]],
) -> dict[str, float | None]:
    if len(history) < 2:
        return {name: None for name in EVENT_TYPES}
    first, last = history[0], history[-1]
    event_delta = _nested_number(last, "event_total") - _nested_number(
        first, "event_total"
    )
    if event_delta <= 0.0:
        return {name: None for name in EVENT_TYPES}
    return {
        name: (
            _nested_number(last, "event_type_counts", name)
            - _nested_number(first, "event_type_counts", name)
        )
        / event_delta
        for name in EVENT_TYPES
    }


def preliminary_attribution(
    frontier: Mapping[str, Any],
    slopes: Mapping[str, float | None],
    ratios: Mapping[str, float | None],
) -> dict[str, Any]:
    """Describe counter association only; do not claim causal attribution."""

    completion = slopes.get("completions_per_wall_second")
    retry = slopes.get("merge_retries_per_wall_second")
    coalesced = slopes.get("coalesced_events_per_wall_second")
    valid_ratios = {
        name: value for name, value in ratios.items() if value is not None
    }
    dominant = (
        max(valid_ratios, key=valid_ratios.get)  # type: ignore[arg-type]
        if valid_ratios
        else None
    )
    if (completion is None or completion <= 0.0) and (
        (retry or 0.0) > 0.0 or (coalesced or 0.0) > 0.0
    ):
        label = "RETRY_WAKEUP_PRESSURE_ASSOCIATED_WITH_NO_COMPLETION_PROGRESS"
    elif (completion is None or completion <= 0.0) and (
        _integer(frontier.get("current_backlog")) or 0
    ) > 0:
        label = "BACKLOG_WITH_NO_COMPLETION_PROGRESS_WITHIN_BOUND"
    elif dominant is not None and (valid_ratios[dominant] or 0.0) >= 0.5:
        label = f"EVENT_MIX_DOMINATED_BY_{dominant.upper()}"
    else:
        label = "MIXED_EVENT_LOAD_NO_SINGLE_COUNTER_DOMINATES"
    return {
        "label": label,
        "dominant_event_type": dominant,
        "dominant_event_ratio": (
            valid_ratios.get(dominant) if dominant is not None else None
        ),
        "claim_boundary": (
            "Preliminary counter association only. Event-type ratios and "
            "wakeup/retry slopes do not establish a causal CPU category."
        ),
    }


def _native_status(payload: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    if payload.get("execution_status") == "BOUNDED_PROGRESS":
        return "BOUNDED_PROGRESS"
    if summary.get("event_limit_reached") is True:
        return "CAPACITY_CENSORED_EVENT_LIMIT"
    if summary.get("time_limit_reached") is True:
        return "CAPACITY_CENSORED_SIMULATION_TIME"
    requested = _integer(summary.get("requested_count")) or 0
    completed = _integer(summary.get("completed_count")) or 0
    failed = _integer(summary.get("failed_count")) or 0
    if completed == requested and failed == 0:
        return "COMPLETE"
    if completed + failed == requested:
        return "FINALIZED_WITH_FAILURES"
    return "INCOMPLETE_NATIVE_RETURN"


SUMMARY_FIELDS = (
    "requested_count",
    "completed_count",
    "failed_count",
    "event_count",
    "end_time",
    "event_limit_reached",
    "time_limit_reached",
    "reservation_conflicts",
    "physical_fault_edge_entry_violation_count",
    "unresolved_deadlock_count",
    "runtime_full_astar_calls",
    "runtime_full_cie_astar_calls",
    "global_reservation_scan_count",
    "priority_global_scan_count",
    "scorer_runtime_global_scan_count",
    "microphase_runtime_global_scan_count",
    "first_edge_credit_global_scan_count",
    "merge_grant_timing_mode",
    "scorer_mode",
    "scorer_id",
)


def compact_job_result(
    payload: Mapping[str, Any],
    *,
    scale: int,
    scorer: str,
    descriptor: Mapping[str, Any],
    max_wall_seconds: float,
    check_events: int,
    native_wall_seconds: float,
    native_cpu_seconds: float,
    input_wall_seconds: float,
    rss_before_mb: float | None,
    rss_after_mb: float | None,
    rss_method: str,
) -> dict[str, Any]:
    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native payload lacks summary")
    requested = _integer(descriptor.get("segments")) or len(payload.get("bags", []))
    history, history_source = progress_history_from_payload(
        payload, requested=requested, wall_seconds=native_wall_seconds
    )
    slopes = progress_slopes(history)
    ratios = event_type_ratios(history)
    frontier = history[-1]
    completed = _integer(frontier.get("completed_bags")) or 0
    return {
        "schema": SCHEMA_JOB,
        "status": _native_status(payload, summary),
        "scale": scale,
        "scorer": scorer,
        "scorer_mode": SCORER_MODES[scorer],
        "runtime_control": {
            "merge": "J2_jit_fair_aging_deadline",
            "frozen_control_source": (
                "g4irsf14_opportunity_census.FROZEN_RUNTIME_CONTROLS"
            ),
            "bounded_wall_seconds": max_wall_seconds,
            "bounded_check_every_events": check_events,
        },
        "input": dict(descriptor),
        "frontier": frontier,
        "completion_fraction": completed / requested if requested > 0 else None,
        "progress_history_source": history_source,
        "progress_history": history,
        "slopes": slopes,
        "event_type_ratios": ratios,
        "preliminary_attribution": preliminary_attribution(
            frontier, slopes, ratios
        ),
        "resources": {
            "input_preparation_wall_seconds": input_wall_seconds,
            "native_wall_seconds": native_wall_seconds,
            "native_process_cpu_seconds": native_cpu_seconds,
            "native_cpu_to_wall_ratio": (
                native_cpu_seconds / native_wall_seconds
                if native_wall_seconds > 0.0
                else None
            ),
            "rss_sample_mb_before_native": rss_before_mb,
            "rss_sample_mb_after_native": rss_after_mb,
            "rss_sample_mb_max_of_endpoints": (
                max(value for value in (rss_before_mb, rss_after_mb) if value is not None)
                if rss_before_mb is not None or rss_after_mb is not None
                else None
            ),
            "rss_sample_method": rss_method,
        },
        "selected_summary": {
            name: summary.get(name) for name in SUMMARY_FIELDS
        },
        "limitations": {
            "disk_checkpoint_implemented": False,
            "checkpoint_restart_claimed": False,
            "cpu_category_breakdown_implemented": False,
            "rss_is_point_sample_not_peak": True,
            "bounded_progress_is_unfinalized": (
                payload.get("execution_status") == "BOUNDED_PROGRESS"
            ),
        },
    }


def execute_scale(
    scale: int,
    *,
    scorer: str,
    binary: Path,
    root: Path = ROOT,
    max_wall_seconds: float,
    check_events: int,
    executor: Executor | None = None,
    input_loader: InputLoader = load_g18_scale_input,
    rss_reader: RssReader = _rss_sample_mb,
) -> dict[str, Any]:
    if executor is None:
        from czr005.cpp_backend import g4irsf11_event_runtime_from_records

        executor = g4irsf11_event_runtime_from_records
    input_started = time.perf_counter()
    rows, descriptor = input_loader(scale, root)
    input_wall_seconds = time.perf_counter() - input_started
    _require(bool(rows), "input loader returned no rows")
    _require(descriptor.get("topology_changed") is False, "scale input changed topology")
    _require(
        _integer(descriptor.get("segments")) == len(rows),
        "input descriptor segment count drift",
    )
    request = build_native_request(
        rows,
        scale=scale,
        scorer=scorer,
        binary=binary,
        root=root,
        max_wall_seconds=max_wall_seconds,
        check_events=check_events,
    )
    rss_before, rss_method_before = rss_reader()
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = executor(**request)
    native_cpu_seconds = time.process_time() - cpu_started
    native_wall_seconds = time.perf_counter() - wall_started
    rss_after, rss_method_after = rss_reader()
    _require(isinstance(payload, Mapping), "native payload is not an object")
    rss_method = (
        rss_method_before
        if rss_method_before == rss_method_after
        else f"before={rss_method_before};after={rss_method_after}"
    )
    return compact_job_result(
        payload,
        scale=scale,
        scorer=scorer,
        descriptor=descriptor,
        max_wall_seconds=max_wall_seconds,
        check_events=check_events,
        native_wall_seconds=native_wall_seconds,
        native_cpu_seconds=native_cpu_seconds,
        input_wall_seconds=input_wall_seconds,
        rss_before_mb=rss_before,
        rss_after_mb=rss_after,
        rss_method=rss_method,
    )


CSV_FIELDS = (
    "scale",
    "scorer",
    "status",
    "requested_bags",
    "released_bags",
    "completed_bags",
    "failed_bags",
    "current_backlog",
    "completion_fraction",
    "event_total",
    "simulated_time",
    "native_wall_seconds",
    "native_process_cpu_seconds",
    "native_cpu_to_wall_ratio",
    "rss_sample_mb",
    "events_per_wall_second",
    "releases_per_wall_second",
    "completions_per_wall_second",
    "backlog_change_per_wall_second",
    "simulated_seconds_per_wall_second",
    "merge_retries_per_wall_second",
    "duplicate_wakeups_per_wall_second",
    "coalesced_events_per_wall_second",
    "dominant_event_type",
    "dominant_event_ratio",
    "preliminary_attribution",
)


def csv_row(result: Mapping[str, Any]) -> dict[str, Any]:
    frontier = result["frontier"]
    resources = result["resources"]
    slopes = result["slopes"]
    attribution = result["preliminary_attribution"]
    return {
        "scale": result["scale"],
        "scorer": result["scorer"],
        "status": result["status"],
        "requested_bags": frontier["requested_bags"],
        "released_bags": frontier["released_bags"],
        "completed_bags": frontier["completed_bags"],
        "failed_bags": frontier["failed_bags"],
        "current_backlog": frontier["current_backlog"],
        "completion_fraction": result["completion_fraction"],
        "event_total": frontier["event_total"],
        "simulated_time": frontier["simulated_time"],
        "native_wall_seconds": resources["native_wall_seconds"],
        "native_process_cpu_seconds": resources["native_process_cpu_seconds"],
        "native_cpu_to_wall_ratio": resources["native_cpu_to_wall_ratio"],
        "rss_sample_mb": resources["rss_sample_mb_max_of_endpoints"],
        **{name: slopes.get(name) for name in CSV_FIELDS if name in slopes},
        "dominant_event_type": attribution["dominant_event_type"],
        "dominant_event_ratio": attribution["dominant_event_ratio"],
        "preliminary_attribution": attribution["label"],
    }


def render_csv(results: Sequence[Mapping[str, Any]]) -> str:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(csv_row(result) for result in results)
    return handle.getvalue()


def _fmt(value: Any, digits: int = 3) -> str:
    number = _finite(value)
    return "—" if number is None else f"{number:.{digits}f}"


def render_frontier_report(results: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# G4IRSF19 live frontier and cost",
        "",
        "This report replaces the 4× external-timeout black box with native, "
        "unfinalized progress snapshots. All rows use the real G18 fixed-map "
        "scale stream, frozen local controls, and J2 merge timing.",
        "",
        "| scale | scorer | status | events/s | complete/s | sim/wall | "
        "retry/s | coalesced/s | CPU/wall | RSS sample MiB | preliminary signal |",
        "|---:|:---:|:---|---:|---:|---:|---:|---:|---:|---:|:---|",
    ]
    for result in results:
        slope = result["slopes"]
        resource = result["resources"]
        lines.append(
            "| {scale}× | {scorer} | {status} | {events} | {complete} | "
            "{sim} | {retry} | {coalesced} | {cpu} | {rss} | {signal} |".format(
                scale=result["scale"],
                scorer=result["scorer"],
                status=result["status"],
                events=_fmt(slope["events_per_wall_second"]),
                complete=_fmt(slope["completions_per_wall_second"]),
                sim=_fmt(slope["simulated_seconds_per_wall_second"]),
                retry=_fmt(slope["merge_retries_per_wall_second"]),
                coalesced=_fmt(slope["coalesced_events_per_wall_second"]),
                cpu=_fmt(resource["native_cpu_to_wall_ratio"]),
                rss=_fmt(resource["rss_sample_mb_max_of_endpoints"]),
                signal=result["preliminary_attribution"]["label"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Event-type ratios plus retry/wakeup slopes are preliminary "
            "associations, not a causal CPU attribution. This runner does not "
            "implement disk checkpoints or restart, and it does not expose "
            "CPU categories. RSS values are endpoint samples, not peaks. A "
            "BOUNDED_PROGRESS row is intentionally not finalized and must not "
            "be ranked as a completed performance win.",
            "",
        ]
    )
    return "\n".join(lines)


def render_capacity_report(results: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# G4IRSF19 scale capacity",
        "",
        "| scale | scorer | status | requested | released | completed | failed | "
        "backlog | completion | events | simulated time | wall s |",
        "|---:|:---:|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    completed_scales: list[int] = []
    for result in results:
        frontier = result["frontier"]
        if result["status"] == "COMPLETE":
            completed_scales.append(int(result["scale"]))
        lines.append(
            "| {scale}× | {scorer} | {status} | {requested} | {released} | "
            "{completed} | {failed} | {backlog} | {fraction} | {events} | "
            "{sim} | {wall} |".format(
                scale=result["scale"],
                scorer=result["scorer"],
                status=result["status"],
                requested=frontier["requested_bags"],
                released=frontier["released_bags"],
                completed=frontier["completed_bags"],
                failed=frontier["failed_bags"],
                backlog=frontier["current_backlog"],
                fraction=_fmt(result["completion_fraction"], 6),
                events=frontier["event_total"],
                sim=_fmt(frontier["simulated_time"]),
                wall=_fmt(result["resources"]["native_wall_seconds"]),
            )
        )
    if completed_scales:
        conclusion = f"Largest naturally completed tested scale: {max(completed_scales)}×."
    else:
        conclusion = "No tested scale naturally completed within this run."
    lines.extend(
        [
            "",
            conclusion,
            "Rows stopped at the wall boundary are live-frontier observations, "
            "not failures and not completed capacity claims. No conclusion is "
            "made beyond the tested scales or configured wall bound.",
            "",
        ]
    )
    return "\n".join(lines)


def run_campaign(
    *,
    scales: Sequence[int],
    scorer: str,
    binary: Path,
    root: Path = ROOT,
    max_wall_seconds: float,
    check_events: int,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    csv_path: Path = DEFAULT_CSV,
    frontier_report: Path = DEFAULT_FRONTIER_REPORT,
    capacity_report: Path = DEFAULT_CAPACITY_REPORT,
    executor: Executor | None = None,
    input_loader: InputLoader = load_g18_scale_input,
    rss_reader: RssReader = _rss_sample_mb,
) -> list[dict[str, Any]]:
    normalized = tuple(int(scale) for scale in scales)
    _require(bool(normalized), "at least one scale is required")
    _require(len(set(normalized)) == len(normalized), "duplicate scale")
    _require(all(scale in ALLOWED_SCALES for scale in normalized), "unsupported scale")
    results: list[dict[str, Any]] = []
    for scale in normalized:
        result = execute_scale(
            scale,
            scorer=scorer,
            binary=binary,
            root=root,
            max_wall_seconds=max_wall_seconds,
            check_events=check_events,
            executor=executor,
            input_loader=input_loader,
            rss_reader=rss_reader,
        )
        _atomic_json(output_dir / f"scale_{scale}x__{scorer.lower()}.json", result)
        results.append(result)
    _atomic_text(csv_path, render_csv(results))
    _atomic_text(frontier_report, render_frontier_report(results))
    _atomic_text(capacity_report, render_capacity_report(results))
    return results


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument(
        "--scales", type=int, nargs="+", default=list(ALLOWED_SCALES)
    )
    parser.add_argument("--max-wall-s", type=float, default=300.0)
    parser.add_argument("--check-events", type=int, default=65_536)
    parser.add_argument("--scorer", choices=tuple(SCORER_MODES), default="S1")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--frontier-report", type=Path, default=DEFAULT_FRONTIER_REPORT
    )
    parser.add_argument(
        "--capacity-report", type=Path, default=DEFAULT_CAPACITY_REPORT
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    results = run_campaign(
        scales=args.scales,
        scorer=args.scorer,
        binary=args.binary,
        root=args.root,
        max_wall_seconds=args.max_wall_s,
        check_events=args.check_events,
        output_dir=args.output_dir,
        csv_path=args.csv,
        frontier_report=args.frontier_report,
        capacity_report=args.capacity_report,
    )
    print(
        json.dumps(
            {
                "rows": len(results),
                "statuses": [result["status"] for result in results],
                "csv": str(args.csv),
                "frontier_report": str(args.frontier_report),
                "capacity_report": str(args.capacity_report),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
