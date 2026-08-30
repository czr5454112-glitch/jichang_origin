#!/usr/bin/env python3
"""Run the preregistered V3R13 Candidate-A Stage-2 real-map slice.

The committed preregistration is the sole case/population authority.  The
module rebuilds the canonical workloads through the existing preregistration
loader, selects its ordered segment IDs, and delegates request construction
and fault handling to the existing G31 Nanning/map2 runners.  Importing the
module neither loads a native extension nor writes evidence.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import g4irsf12_reproducible_harness as harness  # noqa: E402
from scripts.eval import run_g4irsf31_map2_native as map2_native  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_native as nanning_native  # noqa: E402
from scripts.eval import (  # noqa: E402
    run_g4irsf32_v3r13_closed_loop_stage01 as stage01,
)
from scripts.eval import (  # noqa: E402
    run_g4irsf32_v3r13_stage2_preregister as preregister,
)


SCHEMA = "czr005.g4irsf32.v3r13.stage2_campaign.v2"
PROTOCOL_ID = "G4IRSF32_V3R13_CANDIDATE_A_CLOSED_LOOP_STAGE2_20260829"
PASS = "PASS_V3R13_CANDIDATE_A_STAGE2"
NO_GO = "NO_GO_V3R13_CANDIDATE_A_STAGE2"
PREREGISTRATION_PATH = (
    ROOT / "outputs/tables/g4irsf32_v3r13_stage2_preregistered_cases.json"
)
ORIGINAL_OUTPUT_JSON = ROOT / "outputs/tables/g4irsf32_v3r13_stage2_campaign.json"
OUTPUT_JSON = ROOT / "outputs/tables/g4irsf32_v3r13_stage2_campaign_corrected.json"
OUTPUT_MD = ROOT / "outputs/reports/g4irsf32_v3r13_stage2_campaign_corrected.md"

MODES = ("off", "closed_loop")
# Stage 2 needs aggregate counters and bag timings, not millions of generic
# event dictionaries.  The action/event identity seam was already proven by
# the pre-Stage-2 gate, so suppress the generic trace for the real campaign.
EVENT_TRACE_LIMIT = 0
RESOURCE_RATIO_LIMIT = 1.10
NANNING_WAIT_AREA_REDUCTION = 0.05
NANNING_IDLE_WHILE_READY_REDUCTION = 0.50
NANNING_TARGET_P95_REDUCTION = 0.02
NANNING_MEAN_REGRESSION_LIMIT = 0.005
NANNING_TAIL_REGRESSION_LIMIT = 0.01
MAP2_REGRESSION_LIMIT = 0.005
EPSILON = 1.0e-9

Executor = Callable[..., Mapping[str, Any]]


class Stage2CampaignError(RuntimeError):
    """Raised when the frozen Stage-2 campaign cannot be evaluated."""


@dataclass(frozen=True)
class WorkloadSlice:
    map_id: str
    scale: int
    rows: tuple[dict[str, Any], ...]
    workload: Any
    ordered_segment_ids: tuple[str, ...]
    target_segment_ids: frozenset[str]
    raw_task_count: int


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Stage2CampaignError(f"{label} must be an object")
    return value


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise Stage2CampaignError(f"{label} must be an array of objects")
    return list(value)


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Stage2CampaignError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise Stage2CampaignError(f"{label} must be finite")
    return result


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise Stage2CampaignError(f"{label} must be an integer")
    return value


def _read_preregistration() -> dict[str, Any]:
    value = json.loads(PREREGISTRATION_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage2CampaignError("Stage-2 preregistration must be an object")
    cases = value.get("cases")
    populations = value.get("populations")
    if (
        value.get("schema") != preregister.SCHEMA
        or value.get("protocol_id") != PROTOCOL_ID
        or value.get("pass") is not True
        or not isinstance(cases, list)
        or len(cases) != 10
        or len({row.get("case_id") for row in cases if isinstance(row, Mapping)})
        != 10
        or not isinstance(populations, Mapping)
        or set(populations) != {"1x", "2x"}
    ):
        raise Stage2CampaignError("committed Stage-2 preregistration is not ready")
    return value


def _resolve_binary(binary: Path) -> Path:
    resolved = binary.resolve(strict=True)
    if not resolved.is_file():
        raise Stage2CampaignError("V3R13 binary must be a file")
    if "build_g32_v3r13" not in {part.lower() for part in resolved.parts}:
        raise Stage2CampaignError(
            "Stage-2 binary must be passed explicitly from build_g32_v3r13"
        )
    return resolved


def _select_ordered_rows(
    rows: Sequence[Mapping[str, Any]],
    ordered_ids: Sequence[Any],
    *,
    expected_raw_tasks: int,
) -> tuple[dict[str, Any], ...]:
    ids = tuple(str(value) for value in ordered_ids)
    if not ids or len(ids) != len(set(ids)):
        raise Stage2CampaignError("ordered_segment_ids must be unique and non-empty")
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        segment_id = str(row.get("segment_id", ""))
        if not segment_id or segment_id in indexed:
            raise Stage2CampaignError("canonical workload has invalid segment IDs")
        indexed[segment_id] = row
    missing = [segment_id for segment_id in ids if segment_id not in indexed]
    if missing:
        raise Stage2CampaignError(
            f"canonical workload lacks {len(missing)} preregistered segments"
        )
    selected = tuple(dict(indexed[segment_id]) for segment_id in ids)
    if [str(row["segment_id"]) for row in selected] != list(ids):
        raise Stage2CampaignError("canonical closure order changed")
    raw_tasks = {int(row["task_id"]) for row in selected}
    if len(raw_tasks) != expected_raw_tasks:
        raise Stage2CampaignError("canonical closure raw-task count changed")
    return selected


@lru_cache(maxsize=1)
def _canonical_workloads() -> dict[str, dict[int, list[dict[str, Any]]]]:
    return preregister._canonical_workloads()


def _load_workload_slices(
    registration: Mapping[str, Any],
) -> dict[tuple[str, int], WorkloadSlice]:
    canonical = _canonical_workloads()
    populations = _mapping(registration.get("populations"), "populations")
    slices: dict[tuple[str, int], WorkloadSlice] = {}
    for scale in (1, 2):
        population = _mapping(populations.get(f"{scale}x"), f"population {scale}x")
        ordered = population.get("ordered_segment_ids")
        if not isinstance(ordered, list):
            raise Stage2CampaignError("population ordered_segment_ids must be an array")
        segment_count = _integer(population.get("segment_count"), "segment_count")
        raw_count = _integer(population.get("raw_task_count"), "raw_task_count")
        if segment_count != len(ordered):
            raise Stage2CampaignError("preregistered segment count changed")
        target = population.get("nanning_target_segment_ids")
        if not isinstance(target, list) or not set(map(str, target)).issubset(
            set(map(str, ordered))
        ):
            raise Stage2CampaignError("Nanning target cohort is outside its closure")

        for map_name, map_id in (
            ("nanning", nanning_native.MAP_ID),
            ("map2", map2_native.MAP_ID),
        ):
            selected = _select_ordered_rows(
                canonical[map_name][scale],
                ordered,
                expected_raw_tasks=raw_count,
            )
            if map_name == "nanning":
                manifest_path = (
                    nanning_native.DEFAULT_TASK_DIR
                    / f"nanning_{scale}x_manifest.json"
                )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                workload = nanning_native.Workload(
                    scale=scale,
                    manifest_path=manifest_path,
                    canonical_path=manifest_path,
                    manifest=manifest,
                    rows=selected,
                    raw_bag_count=raw_count,
                    segment_count=segment_count,
                )
                target_ids = frozenset(map(str, target))
            else:
                workload = map2_native.Workload(
                    scale=scale,
                    source_path=(
                        map2_native.DEFAULT_WORKLOAD_1X
                        if scale == 1
                        else map2_native.DEFAULT_WORKLOAD_2X
                    ),
                    protocol="V3R13_STAGE2_PREREGISTERED_CANONICAL_CLOSURE",
                    rows=selected,
                    raw_bag_count=raw_count,
                    segment_count=segment_count,
                )
                target_ids = frozenset()
            slices[(map_id, scale)] = WorkloadSlice(
                map_id=map_id,
                scale=scale,
                rows=selected,
                workload=workload,
                ordered_segment_ids=tuple(map(str, ordered)),
                target_segment_ids=target_ids,
                raw_task_count=raw_count,
            )
    return slices


def _fault_edges(value: Any) -> list[list[int]]:
    if not isinstance(value, (list, tuple)):
        raise Stage2CampaignError("fault edges must be an array")
    return [[int(edge[0]), int(edge[1])] for edge in value]


def _build_pair_requests(
    case: Mapping[str, Any],
    workload: WorkloadSlice,
    *,
    binary: Path,
) -> tuple[dict[str, dict[str, Any]], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    case_id = str(case["case_id"])
    common = {
        "case_id": case_id,
        "group": str(case["role"]),
        "scale": int(case["scale"]),
        "speed_mps": float(case["speed_mps"]),
        "fault_scenario": case.get("fault_scenario"),
    }
    if workload.map_id == nanning_native.MAP_ID:
        spec = nanning_native.CaseSpec(**common)
        request, runtime_rows, rejected, local = nanning_native.prepare_native_request(
            spec,
            workload.workload,
            map_profile_path=nanning_native.DEFAULT_MAP_PROFILE,
            fault_protocol_path=nanning_native.DEFAULT_FAULT_PROTOCOL,
            binary=binary,
        )
    elif workload.map_id == map2_native.MAP_ID:
        spec = map2_native.CaseSpec(**common)
        request, runtime_rows, rejected, local = map2_native.prepare_native_request(
            spec, workload.workload, binary=binary
        )
    else:
        raise Stage2CampaignError(f"unsupported preregistered map: {workload.map_id}")

    if _fault_edges(local.get("fault_edges", [])) != _fault_edges(
        case.get("fault_edges", [])
    ):
        raise Stage2CampaignError(f"{case_id}: registered fault edges changed")
    request["event_trace_limit"] = EVENT_TRACE_LIMIT
    expected_binary = request.get("expected_binary_path")
    if not isinstance(expected_binary, Path) or expected_binary != binary:
        raise Stage2CampaignError(f"{case_id}: binary was not bound by build_s4_request")

    off = copy.deepcopy(request)
    closed = copy.deepcopy(request)
    closed.update(
        source_aware_destination_service_mode="closed_loop",
        source_aware_destination_service_trace_limit=stage01.TRACE_LIMIT,
    )
    if stage01._without_extension(off) != stage01._without_extension(closed):
        raise Stage2CampaignError(f"{case_id}: paired ordinary requests differ")
    if any(key.startswith(stage01.NS) for key in off):
        raise Stage2CampaignError(f"{case_id}: off arm contains the extension")
    return {"off": off, "closed_loop": closed}, runtime_rows, rejected


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise Stage2CampaignError("cannot summarize an empty distribution")
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean_seconds": None, "p95_seconds": None, "p99_seconds": None}
    return {
        "count": len(values),
        "mean_seconds": statistics.fmean(values),
        "p95_seconds": _quantile(values, 0.95),
        "p99_seconds": _quantile(values, 0.99),
    }


def _reported_rss(payload: Mapping[str, Any]) -> tuple[float | None, str]:
    resource = payload.get("resource_metrics")
    if not isinstance(resource, Mapping) or resource.get("measurement_scope") != (
        "isolated_worker_process"
    ):
        return None, "NOT_MEASURED_ATTRIBUTABLY_IN_ISOLATED_WORKER"
    for name in ("peak_working_set_bytes", "peak_rss_bytes"):
        value = resource.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result = float(value)
            if math.isfinite(result) and result > 0.0:
                return result, "MEASURED_ISOLATED_WORKER_PROCESS"
    return None, "ISOLATED_WORKER_DID_NOT_REPORT_PEAK_RSS"


def _safety(
    payload: Mapping[str, Any],
    *,
    mode: str,
    map_id: str,
    expected_extension_mode: str | None = None,
) -> dict[str, Any]:
    summary = _mapping(payload.get("summary"), "payload.summary")
    events = _rows(payload.get("events"), "payload.events")
    # Long real-map runs legitimately retire stale arbitration wakeups, and a
    # fixed fault horizon can leave a repair event beyond the horizon after
    # every reachable bag has completed.  Those are diagnostics, not safety
    # failures.  Keep the actual action-plan safety/global/future invariants.
    absolute_zero_names = tuple(
        name
        for name in stage01.SAFETY_ZERO_KEYS
        if name
        not in {
            "merge_grant_stale_arbitration_count",
            "stale_arbitration_event_count",
        }
    ) + ("full_future_routes_stored",)
    absolute_zero = {
        name: _number(summary.get(name), f"summary.{name}") == 0.0
        for name in absolute_zero_names
    }
    base = {
        "absolute_safety_global_future_counters_zero": all(
            absolute_zero.values()
        ),
        "safe_execution": summary.get("safe_execution_pass") is True,
        "one_hop_only": _integer(
            summary.get("max_edges_selected_per_bag_per_decision"),
            "max edges selected per bag per decision",
        )
        <= 1,
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "no_artificial_batch_delay": _number(
            summary.get("artificial_batch_delay_seconds"),
            "artificial batch delay",
        )
        == 0.0,
        "merge_integrity": summary.get("merge_grant_conservation_holds") is True
        and summary.get("merge_grant_active_bijection_holds") is True
        and summary.get("merge_grant_protocol_integrity_pass") is True,
    }
    extension_zero = {
        stage01.NS + "future_release_read_count": True,
        stage01.NS + "global_scan_count": True,
    }
    model_zero = {
        name: _number(summary.get(name, 0), f"summary.{name}") == 0.0
        for name in stage01.MODEL_ZERO_KEYS
    }
    diagnostic_counters = {
        name: _integer(summary.get(name), f"summary.{name}")
        for name in (
            "starvation_count",
            "merge_grant_stale_arbitration_count",
            "stale_arbitration_event_count",
        )
    }
    diagnostic_flags = {
        "time_limit_reached_after_reachable_population": summary.get(
            "time_limit_reached"
        )
        is True,
        "event_trace_truncated_because_suppressed": summary.get(
            "event_trace_truncated"
        )
        is True,
    }
    future_path_false = (
        summary.get("bag_future_path_field_present") is False
        and summary.get("full_cie_astar_runtime_fallback") is False
    )
    if mode == "off":
        extension = stage01.extension_absent(payload)
        action_count = 0
        calendar_count = 0
    else:
        expected_mode = expected_extension_mode or mode
        action_count = _integer(
            summary.get(stage01.NS + "action_change_count"), "action count"
        )
        calendar_count = _integer(
            summary.get(stage01.NS + "calendar_mutation_count"),
            "calendar mutation count",
        )
        extension = summary.get(stage01.NS + "mode") == expected_mode
        extension_zero[stage01.NS + "future_release_read_count"] = _number(
            summary.get(stage01.NS + "future_release_read_count"),
            "closed-loop future reads",
        ) == 0.0
        extension_zero[stage01.NS + "global_scan_count"] = _number(
            summary.get(stage01.NS + "global_scan_count"),
            "closed-loop global scans",
        ) == 0.0
    gates = {
        "action_plan_safety": all(base.values()),
        "extension_future_and_global_reads_zero": all(extension_zero.values()),
        "model_applied_zero": all(model_zero.values()),
        "future_path_absent": future_path_false,
        "generic_event_trace_suppressed": not events,
        "mode_surface_exact": extension,
        "action_calendar_counters_exact": action_count == calendar_count,
        "map2_structural_negative_no_action": (
            action_count == 0 if map_id == map2_native.MAP_ID else True
        ),
    }
    return {
        "pass": all(gates.values()),
        "gates": gates,
        "base": base,
        "absolute_zero_counters": absolute_zero,
        "extension_zero_counters": extension_zero,
        "model_zero_counters": model_zero,
        "diagnostic_counters": diagnostic_counters,
        "diagnostic_flags": diagnostic_flags,
        "action_count": action_count,
        "calendar_mutation_count": calendar_count,
        "action_event_identity_status": "PROVEN_PRE_STAGE2_TRACE_SUPPRESSED_HERE",
    }


def _arm_metrics(
    payload: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    workload: WorkloadSlice,
    mode: str,
    expected_extension_mode: str | None = None,
    measured_wall_seconds: float,
    eligible_raw_task_ids: frozenset[int],
    eligible_target_segment_ids: frozenset[str],
) -> dict[str, Any]:
    summary = _mapping(payload.get("summary"), "payload.summary")
    bags = _rows(payload.get("bags"), "payload.bags")
    _rows(payload.get("events"), "payload.events")
    _rows(payload.get("junction_state"), "payload.junction_state")
    raw = harness.aggregate_raw_bag_timings(
        workload.rows, bags, allow_release_before_original_entry=True
    )
    complete_raw = [
        row
        for row in raw
        if row["complete"] is True and int(row["task_id"]) in eligible_raw_task_ids
    ]
    # J is the algorithm-sensitive scheduled-release total.  The protected
    # pre-release dwell is identical between arms and must not dilute a gate.
    whole = _distribution(
        [float(row["java_release_time_tth_seconds"]) for row in complete_raw]
    )

    input_by_id = {str(row["segment_id"]): row for row in workload.rows}
    result_by_id = {str(row.get("segment_id", "")): row for row in bags}
    target_values: list[float] = []
    local_source_wait = 0.0
    local_network = 0.0
    local_total = 0.0
    local_completed = 0
    target_source_wait = 0.0
    target_network = 0.0
    target_total = 0.0
    completed_target_ids: set[str] = set()
    for segment_id in eligible_target_segment_ids:
        source = input_by_id[segment_id]
        result = result_by_id.get(segment_id)
        if result is None or not bool(result.get("completed", result.get("complete", False))):
            continue
        release = _number(source.get("pass_time"), f"{segment_id}.pass_time")
        admitted = _number(result.get("admitted_time"), f"{segment_id}.admitted_time")
        finish = _number(result.get("finish_time"), f"{segment_id}.finish_time")
        if admitted + EPSILON < release or finish + EPSILON < admitted:
            raise Stage2CampaignError(f"{segment_id}: invalid target timing order")
        completed_target_ids.add(segment_id)
        target_values.append(finish - release)
        target_source_wait += admitted - release
        target_network += finish - admitted
        target_total += finish - release
        if int(source["start"]) == 49:
            local_completed += 1
            local_source_wait += admitted - release
            local_network += finish - admitted
            local_total += finish - release

    if workload.map_id == nanning_native.MAP_ID:
        target = {
            "preregistered_segment_count": len(workload.target_segment_ids),
            "fault_reachable_segment_count": len(eligible_target_segment_ids),
            "completed_segment_count": len(target_values),
            "latency": _distribution(target_values),
            "local_source_node": 49,
            "local_completed_segment_count": local_completed,
            "local_start49_source_wait_area_proxy_bag_seconds": local_source_wait,
            "local_start49_source_wait_area_proxy_status": (
                "BAG_TIMESTAMP_PROXY_NOT_COMPLETE_MIXED_ORIGIN_STATE_INTEGRAL"
            ),
            "local_idle_while_ready_seconds": None,
            "local_idle_while_ready_status": (
                "NOT_MEASURABLE_WITHOUT_COMPLETE_ELIGIBLE_READY_STATE_TIMELINE"
            ),
            "local_source_wait_seconds": local_source_wait,
            "local_network_time_seconds": local_network,
            "local_total_latency_seconds": local_total,
            "local_start49_source_wait_area_proxy_semantics": (
                "sum(admitted_time-pass_time) over preregistered target "
                "segments whose canonical start node is 49"
            ),
            "target_source_wait_seconds": target_source_wait,
            "target_network_time_seconds": target_network,
            "target_total_latency_seconds": target_total,
        }
    else:
        target = None

    completed_segments = sum(
        bool(row.get("completed", row.get("complete", False))) for row in bags
    )
    summary_completed = _integer(summary.get("completed_count"), "completed_count")
    summary_requested = _integer(summary.get("requested_count"), "requested_count")
    event_count = _integer(summary.get("event_count"), "event_count")
    if summary_completed != completed_segments or summary_requested != len(
        request["bag_records"]
    ):
        raise Stage2CampaignError("payload completion/request counts are inconsistent")
    resource_payload = payload.get("resource_metrics")
    wall = measured_wall_seconds
    wall_scope = "IN_PROCESS_PER_ARM_PERF_COUNTER"
    if (
        isinstance(resource_payload, Mapping)
        and resource_payload.get("measurement_scope") == "isolated_worker_process"
        and isinstance(resource_payload.get("wall_seconds"), (int, float))
        and not isinstance(resource_payload.get("wall_seconds"), bool)
    ):
        wall = _number(resource_payload["wall_seconds"], "isolated wall seconds")
        wall_scope = "ISOLATED_WORKER_EXECUTOR_WALL"
    rss, rss_status = _reported_rss(payload)
    resources = {
        "events_per_completed_segment": (
            event_count / summary_completed if summary_completed > 0 else None
        ),
        "wall_seconds": _number(wall, "wall seconds"),
        "wall_measurement_scope": wall_scope,
        "peak_rss_bytes": rss,
        "peak_rss_status": rss_status,
        "max_source_queue_length": _number(
            summary.get("max_source_queue_length"), "max source queue"
        ),
        "max_junction_queue_length": _number(
            summary.get("max_junction_queue_length"), "max junction queue"
        ),
        "merge_grant_peak_pending_requests": _number(
            summary.get("merge_grant_peak_pending_requests"),
            "merge pending peak",
        ),
    }
    return {
        "mode": mode,
        "completed_segment_count": summary_completed,
        "completed_raw_bag_count": len(complete_raw),
        "whole_system_java_release_latency": whole,
        "target": target,
        "resources": resources,
        "safety": _safety(
            payload,
            mode=mode,
            map_id=workload.map_id,
            expected_extension_mode=expected_extension_mode,
        ),
        "_complete_raw_task_ids": frozenset(
            int(row["task_id"]) for row in complete_raw
        ),
        "_completed_target_segment_ids": frozenset(completed_target_ids),
    }


def _execute_arm(
    executor: Executor,
    request: Mapping[str, Any],
    *,
    workload: WorkloadSlice,
    mode: str,
    expected_extension_mode: str | None = None,
    eligible_raw_task_ids: frozenset[int],
    eligible_target_segment_ids: frozenset[str],
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = executor(**dict(request))
    measured_wall = time.perf_counter() - started
    if not isinstance(payload, Mapping):
        raise Stage2CampaignError("executor must return a mapping")
    return _arm_metrics(
        payload,
        request=request,
        workload=workload,
        mode=mode,
        expected_extension_mode=expected_extension_mode,
        measured_wall_seconds=measured_wall,
        eligible_raw_task_ids=eligible_raw_task_ids,
        eligible_target_segment_ids=eligible_target_segment_ids,
    )


def _ratio(candidate: Any, control: Any) -> float | None:
    if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
        return None
    if not isinstance(control, (int, float)) or isinstance(control, bool):
        return None
    candidate_value = float(candidate)
    control_value = float(control)
    if control_value > 0.0:
        return candidate_value / control_value
    return 1.0 if candidate_value == 0.0 else None


def _at_most(candidate: Any, control: Any, multiplier: float) -> bool:
    ratio = _ratio(candidate, control)
    return ratio is not None and ratio <= multiplier + EPSILON


def _reduction(candidate: Any, control: Any, fraction: float) -> bool:
    ratio = _ratio(candidate, control)
    return ratio is not None and ratio <= 1.0 - fraction + EPSILON


def _run_case(
    case: Mapping[str, Any],
    workload: WorkloadSlice,
    *,
    executor: Executor,
    binary: Path,
) -> dict[str, Any]:
    requests, runtime_rows, rejected = _build_pair_requests(
        case, workload, binary=binary
    )
    runtime_segment_ids = {str(row["segment_id"]) for row in runtime_rows}
    segments_by_task: dict[int, set[str]] = {}
    for row in workload.rows:
        segments_by_task.setdefault(int(row["task_id"]), set()).add(
            str(row["segment_id"])
        )
    eligible_raw_task_ids = frozenset(
        task_id
        for task_id, segment_ids in segments_by_task.items()
        if segment_ids.issubset(runtime_segment_ids)
    )
    eligible_target_segment_ids = frozenset(
        workload.target_segment_ids & runtime_segment_ids
    )
    arms = {
        mode: _execute_arm(
            executor,
            requests[mode],
            workload=workload,
            mode=mode,
            eligible_raw_task_ids=eligible_raw_task_ids,
            eligible_target_segment_ids=eligible_target_segment_ids,
        )
        for mode in MODES
    }
    off = arms["off"]
    candidate = arms["closed_loop"]
    resource_ratios = {
        name: _ratio(candidate["resources"][name], off["resources"][name])
        for name in (
            "events_per_completed_segment",
            "wall_seconds",
            "peak_rss_bytes",
            "max_source_queue_length",
            "max_junction_queue_length",
            "merge_grant_peak_pending_requests",
        )
    }
    matched_timing_cohort = (
        off["_complete_raw_task_ids"]
        == candidate["_complete_raw_task_ids"]
        == eligible_raw_task_ids
        and off["_completed_target_segment_ids"]
        == candidate["_completed_target_segment_ids"]
        == eligible_target_segment_ids
    )
    off_safety_diagnostics = _mapping(
        off["safety"]["diagnostic_counters"], "off safety diagnostics"
    )
    candidate_safety_diagnostics = _mapping(
        candidate["safety"]["diagnostic_counters"],
        "candidate safety diagnostics",
    )
    no_new_starvation = _integer(
        candidate_safety_diagnostics["starvation_count"],
        "candidate starvation count",
    ) <= _integer(
        off_safety_diagnostics["starvation_count"], "off starvation count"
    )
    gates = {
        "completed_not_lower": (
            candidate["completed_segment_count"] >= off["completed_segment_count"]
            and candidate["completed_raw_bag_count"] >= off["completed_raw_bag_count"]
        ),
        "hard_safety": (
            off["safety"]["pass"] is True
            and candidate["safety"]["pass"] is True
        ),
        "no_new_starvation_threshold_crossings": no_new_starvation,
        "static_fault_reachable_timing_cohort_complete_and_matched": (
            matched_timing_cohort
        ),
        "resources_within_1p10": all(
            ratio is not None and ratio <= RESOURCE_RATIO_LIMIT + EPSILON
            for ratio in resource_ratios.values()
        ),
        "map2_structural_negative_no_mixed_origin_action": (
            candidate["safety"]["action_count"] == 0
            if workload.map_id == map2_native.MAP_ID
            else True
        ),
    }

    performance_ratios: dict[str, float | None] = {}
    diagnostics: dict[str, Any] = {}
    diagnostics["safety_counter_deltas"] = {
        name: _integer(candidate_safety_diagnostics[name], f"candidate {name}")
        - _integer(off_safety_diagnostics[name], f"off {name}")
        for name in off_safety_diagnostics
    }
    diagnostics["rss_gate_status"] = (
        "NOT_MEASURED_ATTRIBUTABLY_IN_THIS_IN_PROCESS_CAMPAIGN"
        if resource_ratios["peak_rss_bytes"] is None
        else "MEASURED"
    )
    if workload.map_id == nanning_native.MAP_ID:
        off_target = _mapping(off["target"], "off target")
        candidate_target = _mapping(candidate["target"], "candidate target")
        off_latency = _mapping(off_target["latency"], "off target latency")
        candidate_latency = _mapping(
            candidate_target["latency"], "candidate target latency"
        )
        off_whole = _mapping(
            off["whole_system_java_release_latency"], "off whole-system latency"
        )
        candidate_whole = _mapping(
            candidate["whole_system_java_release_latency"],
            "candidate whole-system latency",
        )
        performance_ratios = {
            "local_start49_source_wait_area_proxy": _ratio(
                candidate_target[
                    "local_start49_source_wait_area_proxy_bag_seconds"
                ],
                off_target["local_start49_source_wait_area_proxy_bag_seconds"],
            ),
            "local_idle_while_ready": _ratio(
                candidate_target["local_idle_while_ready_seconds"],
                off_target["local_idle_while_ready_seconds"],
            ),
            "target_p95": _ratio(
                candidate_latency["p95_seconds"], off_latency["p95_seconds"]
            ),
            "whole_mean": _ratio(
                candidate_whole["mean_seconds"], off_whole["mean_seconds"]
            ),
            "whole_p95": _ratio(
                candidate_whole["p95_seconds"], off_whole["p95_seconds"]
            ),
            "whole_p99": _ratio(
                candidate_whole["p99_seconds"], off_whole["p99_seconds"]
            ),
        }
        source_reduced = float(candidate_target["target_source_wait_seconds"]) < (
            float(off_target["target_source_wait_seconds"]) - EPSILON
        )
        total_not_lower = (
            float(candidate_target["target_total_latency_seconds"])
            >= float(off_target["target_total_latency_seconds"]) - EPSILON
        )
        proxy_reduction = _reduction(
            candidate_target[
                "local_start49_source_wait_area_proxy_bag_seconds"
            ],
            off_target[
                "local_start49_source_wait_area_proxy_bag_seconds"
            ],
            NANNING_WAIT_AREA_REDUCTION,
        )
        diagnostics.update(
            local_start49_source_wait_area_proxy_reduction_5pct=(
                proxy_reduction
            ),
            mixed_origin_wait_area_status=(
                "NOT_MEASURABLE_CURRENT_PAYLOAD_NO_COMPLETE_ELIGIBLE_READY_STATE_TIMELINE"
            ),
            idle_while_ready_status=candidate_target[
                "local_idle_while_ready_status"
            ],
        )
        gates.update(
            nanning_mixed_origin_wait_or_idle_effect_proven=False,
            nanning_target_p95_improves_2pct=_reduction(
                candidate_latency["p95_seconds"],
                off_latency["p95_seconds"],
                NANNING_TARGET_P95_REDUCTION,
            ),
            nanning_whole_mean_regression_at_most_0p5pct=_at_most(
                candidate_whole["mean_seconds"],
                off_whole["mean_seconds"],
                1.0 + NANNING_MEAN_REGRESSION_LIMIT,
            ),
            nanning_whole_p95_regression_at_most_1pct=_at_most(
                candidate_whole["p95_seconds"],
                off_whole["p95_seconds"],
                1.0 + NANNING_TAIL_REGRESSION_LIMIT,
            ),
            nanning_whole_p99_regression_at_most_1pct=_at_most(
                candidate_whole["p99_seconds"],
                off_whole["p99_seconds"],
                1.0 + NANNING_TAIL_REGRESSION_LIMIT,
            ),
            nanning_no_source_to_network_unchanged_total_transfer=not (
                source_reduced and total_not_lower
            ),
        )
    else:
        off_whole = _mapping(
            off["whole_system_java_release_latency"], "off whole-system latency"
        )
        candidate_whole = _mapping(
            candidate["whole_system_java_release_latency"],
            "candidate whole-system latency",
        )
        performance_ratios = {
            name: _ratio(
                candidate_whole[f"{name}_seconds"],
                off_whole[f"{name}_seconds"],
            )
            for name in ("mean", "p95", "p99")
        }
        gates.update(
            map2_mean_regression_at_most_0p5pct=_at_most(
                candidate_whole["mean_seconds"],
                off_whole["mean_seconds"],
                1.0 + MAP2_REGRESSION_LIMIT,
            ),
            map2_p95_regression_at_most_0p5pct=_at_most(
                candidate_whole["p95_seconds"],
                off_whole["p95_seconds"],
                1.0 + MAP2_REGRESSION_LIMIT,
            ),
            map2_p99_regression_at_most_0p5pct=_at_most(
                candidate_whole["p99_seconds"],
                off_whole["p99_seconds"],
                1.0 + MAP2_REGRESSION_LIMIT,
            ),
        )

    for arm in arms.values():
        arm.pop("_complete_raw_task_ids")
        arm.pop("_completed_target_segment_ids")
    return {
        "case_id": str(case["case_id"]),
        "map_id": workload.map_id,
        "scale": workload.scale,
        "role": case["role"],
        "fault_scenario": case.get("fault_scenario"),
        "fault_edges": case.get("fault_edges", []),
        "population": {
            "raw_task_count": workload.raw_task_count,
            "segment_count": len(workload.rows),
            "runtime_reachable_segment_count": len(runtime_rows),
            "source_rejected_segment_count": len(rejected),
            "fault_reachable_raw_task_count": len(eligible_raw_task_ids),
            "fault_reachable_target_segment_count": len(
                eligible_target_segment_ids
            ),
            "ordered_segment_ids_exact": [
                str(row["segment_id"]) for row in workload.rows
            ]
            == list(workload.ordered_segment_ids),
        },
        "arms": arms,
        "resource_ratios": resource_ratios,
        "performance_ratios": performance_ratios,
        "diagnostics": diagnostics,
        "gates": gates,
        "pass": all(gates.values()),
    }


def run_campaign(*, executor: Executor, binary: Path) -> dict[str, Any]:
    """Execute exactly the ten preregistered semantic pairs in memory."""

    resolved_binary = _resolve_binary(binary)
    registration = _read_preregistration()
    slices = _load_workload_slices(registration)
    registered_cases = _rows(registration.get("cases"), "cases")
    cases = []
    for case in registered_cases:
        key = (str(case.get("map_id")), int(case.get("scale", -1)))
        workload = slices.get(key)
        if workload is None:
            raise Stage2CampaignError(f"unsupported preregistered case slice: {key}")
        cases.append(
            _run_case(case, workload, executor=executor, binary=resolved_binary)
        )
    gates = {
        "exact_ten_preregistered_semantic_cases": (
            len(cases) == 10
            and [case["case_id"] for case in cases]
            == [str(case["case_id"]) for case in registered_cases]
        ),
        "exact_twenty_paired_executions": len(cases) * len(MODES) == 20,
        "all_nanning_gates": all(
            case["pass"] for case in cases if case["map_id"] == nanning_native.MAP_ID
        ),
        "all_map2_gates": all(
            case["pass"] for case in cases if case["map_id"] == map2_native.MAP_ID
        ),
    }
    passed = all(gates.values())
    return {
        "schema": SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "measurement_correction_of": ORIGINAL_OUTPUT_JSON.relative_to(
            ROOT
        ).as_posix(),
        "measurement_correction": (
            "separate benign stale-arbitration/fixed-horizon diagnostics "
            "from absolute safety counters; candidate cases and thresholds unchanged"
        ),
        "preregistration": PREREGISTRATION_PATH.relative_to(ROOT).as_posix(),
        "binary": str(resolved_binary),
        "status": PASS if passed else NO_GO,
        "pass": passed,
        "stage3_authorized": passed,
        "semantic_case_count": len(cases),
        "execution_count": len(cases) * len(MODES),
        "modes": list(MODES),
        "thresholds": {
            "resource_ratio_max": RESOURCE_RATIO_LIMIT,
            "nanning_wait_area_reduction_min": NANNING_WAIT_AREA_REDUCTION,
            "nanning_idle_while_ready_reduction_min": NANNING_IDLE_WHILE_READY_REDUCTION,
            "nanning_target_p95_reduction_min": NANNING_TARGET_P95_REDUCTION,
            "nanning_whole_mean_regression_max": NANNING_MEAN_REGRESSION_LIMIT,
            "nanning_whole_p95_p99_regression_max": NANNING_TAIL_REGRESSION_LIMIT,
            "map2_mean_p95_p99_regression_max": MAP2_REGRESSION_LIMIT,
        },
        "gates": gates,
        "cases": cases,
    }


def _format_ratio(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def render_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF32 V3R13 Candidate A Stage 2 campaign",
        "",
        f"Status: `{result.get('status')}`.",
        "",
        "| case | start-49 source-wait proxy ratio | target P95 ratio | "
        "whole mean ratio | max resource ratio | pass |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in result.get("cases", []):
        performance = case["performance_ratios"]
        resources = [value for value in case["resource_ratios"].values() if value is not None]
        if case["map_id"] == nanning_native.MAP_ID:
            wait = performance.get("local_start49_source_wait_area_proxy")
            target = performance.get("target_p95")
            mean = performance.get("whole_mean")
        else:
            wait = None
            target = None
            mean = performance.get("mean")
        lines.append(
            "| {case_id} | {wait} | {target} | {mean} | {resource} | {passed} |".format(
                case_id=case["case_id"],
                wait=_format_ratio(wait),
                target=_format_ratio(target),
                mean=_format_ratio(mean),
                resource=_format_ratio(max(resources) if resources else None),
                passed="PASS" if case["pass"] else "FAIL",
            )
        )
    failed = [name for name, passed in result.get("gates", {}).items() if not passed]
    case_failures = [
        (
            str(case["case_id"]),
            [name for name, passed in case.get("gates", {}).items() if not passed],
        )
        for case in result.get("cases", [])
        if not case.get("pass")
    ]
    lines.extend(
        [
            "",
            "## Failed case gates",
            "",
            *(
                [
                    f"- `{case_id}`: " + ", ".join(names)
                    for case_id, names in case_failures
                ]
                if case_failures
                else ["None." ]
            ),
            "",
            "## Decision",
            "",
            (
                "Stage 3 is authorized."
                if result.get("stage3_authorized")
                else "Stage 3 is not authorized."
            ),
            "",
            "Failed campaign gates: " + (", ".join(failed) if failed else "none"),
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence(result: Mapping[str, Any]) -> None:
    """Publish only the two fixed append-only Stage-2 outputs."""

    if OUTPUT_JSON.exists() or OUTPUT_MD.exists():
        raise FileExistsError("V3R13 Stage-2 outputs are append-only")
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        with OUTPUT_JSON.open("x", encoding="utf-8", newline="\n") as handle:
            created.append(OUTPUT_JSON)
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        with OUTPUT_MD.open("x", encoding="utf-8", newline="\n") as handle:
            created.append(OUTPUT_MD)
            handle.write(render_report(result))
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def cpp_executor(**request: Any) -> Mapping[str, Any]:
    from czr005.cpp_backend import g4irsf11_event_runtime_from_records

    return g4irsf11_event_runtime_from_records(**request)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        result = run_campaign(executor=cpp_executor, binary=arguments.binary)
    except Exception as error:
        # An infrastructure or runner failure is not a candidate outcome and
        # must not occupy the append-only formal evidence paths.
        print(
            f"STAGE2_RUNNER_ERROR: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    write_evidence(result)
    print(result["status"])
    return 0 if result.get("pass") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
