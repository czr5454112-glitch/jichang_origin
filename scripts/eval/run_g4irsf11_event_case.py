"""Isolated-process worker for one G4IRSF11 event-runtime case.

The parent matrix runner launches this file once per case so peak working set
is an OS measurement scoped to a fresh process.  Only compact metrics and a
bounded trace shard leave the worker; full bag/event payloads are not committed.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from czr005 import cpp_backend
from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_PATH,
    CANONICAL_MAP_SHA256,
    assert_canonical_map,
    canonical_graph_records,
    canonical_map_identity,
    normalised_text_sha256,
)
from scripts.eval.g4irsf11_capacity_metrics import (
    CapacityGateConfig,
    capacity_metrics,
    process_working_set_bytes,
    quantile,
)
from scripts.eval.g4irsf11_fault_metrics import FaultWindow, fault_window_metrics
from scripts.eval.g4irsf11_continuity_metrics import rolling_continuity_metrics
from scripts.eval.g4irsf11_experiment_protocol import CAPACITY_SLO, FAULT_SLO
from scripts.eval.g4irsf11_result_validation import (
    JUNCTION_BOTTLENECK_SCORE_SEMANTICS,
    JUNCTION_LOCAL_STATE_ACCOUNTING_SEMANTICS,
    JUNCTION_SERVICE_UTILIZATION_SEMANTICS,
    ResultExpectation,
    WORKER_RUNTIME_DEFAULTS,
    atomic_write_json,
    atomic_write_jsonl,
    derive_junction_evidence,
    fault_binding,
    parse_json_object,
    read_json_array,
    runtime_config_from_namespace,
    sha256_file,
    validate_event_result,
    workload_binding,
)
from scripts.eval.g4irsf11_workloads import (
    aggregate_raw_bags,
    binding_bag_records,
    load_jsonl,
)


def graph_records(map_path: Path) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], list[list[float]]]:
    return canonical_graph_records(assert_canonical_map(map_path))


def _fault_windows(path: Path | None) -> list[FaultWindow]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("fault window file must contain an array")
    return [
        FaultWindow(
            int(row["start"]),
            int(row["end"]),
            float(row["fault_time"]),
            float(row["repair_time"]),
            float(row.get("message_delay", 0.0)),
            bool(row.get("drop_notification", False)),
        )
        for row in payload
    ]


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return "INF" if value > 0.0 else ("-INF" if value < 0.0 else "NAN")
    if isinstance(value, Mapping):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(child) for child in value]
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_json(path, _json_safe(dict(value)))


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    atomic_write_jsonl(path, [_json_safe(dict(row)) for row in rows])


def _outcomes(
    decisions: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
    *,
    fault_mode: str,
    exposure_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    by_runtime_id = {int(row["runtime_bag_id"]): row for row in segment_rows}
    if len(by_runtime_id) != len(segment_rows):
        raise ValueError("runtime_bag_id must be unique for outcome linkage")
    by_source_identity = {
        (int(row["task_id"]), str(row["segment_id"])): row for row in segment_rows
    }
    if len(by_source_identity) != len(segment_rows):
        raise ValueError("(task_id, segment_id) must be unique for outcome linkage")
    durations = [
        float(row["finish_time"]) - float(row["release_time"])
        for row in segment_rows
        if bool(row.get("completed")) and float(row.get("finish_time", -1.0)) >= 0.0
    ]
    p95 = quantile(durations, 0.95)
    p99 = quantile(durations, 0.99)
    exposure_population = decisions + list(exposure_rows or [])
    exposed_runtime_ids = {
        int((decision.get("metadata") or {}).get("runtime_bag_id"))
        for decision in exposure_population
        if (decision.get("metadata") or {}).get("runtime_bag_id") is not None
        and (
            int((decision.get("local_snapshot") or {}).get("faulted_outgoing_count", 0)) > 0
            or any(
                bool(candidate.get("features", {}).get("advertised_fault", False))
                for candidate in decision.get("candidate_records", [])
            )
        )
    }
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        metadata = decision.get("metadata") or {}
        runtime_bag_id = metadata.get("runtime_bag_id", decision.get("runtime_bag_id"))
        bag = (
            by_runtime_id[int(runtime_bag_id)]
            if runtime_bag_id is not None
            else by_source_identity[(int(decision["task_id"]), str(decision["segment_id"]))]
        )
        if (
            int(bag["task_id"]) != int(decision["task_id"])
            or str(bag["segment_id"]) != str(decision["segment_id"])
        ):
            raise ValueError("decision outcome runtime/source identity mismatch")
        completed = bool(bag.get("completed"))
        duration = (
            float(bag["finish_time"]) - float(bag["release_time"])
            if completed and float(bag.get("finish_time", -1.0)) >= 0.0
            else 0.0
        )
        failure_reason = str(bag.get("failure_reason", ""))
        rows.append(
            {
                "decision_id": decision["decision_id"],
                "task_id": int(bag["task_id"]),
                "segment_id": str(bag["segment_id"]),
                "runtime_bag_id": int(bag["runtime_bag_id"]),
                "reached_goal": completed,
                "local_wait_seconds": float(bag.get("total_local_wait", 0.0)),
                "downstream_wait_seconds": float(bag.get("source_queue_delay", 0.0)),
                "loop_or_dead_end": bool(bag.get("loop_count", 0)) or bool(failure_reason),
                "bag_tth_seconds": duration,
                "tail_bucket": (
                    "failed"
                    if not completed
                    else ("p99_tail" if duration >= p99 else ("p95_tail" if duration >= p95 else "body"))
                ),
                "is_p95": completed and duration >= p95,
                "is_p99": completed and duration >= p99,
                "fault_recovery_outcome": (
                    "not_applicable"
                    if fault_mode == "no_fault"
                    else (
                        "not_exposed"
                        if int(bag["runtime_bag_id"]) not in exposed_runtime_ids
                        else ("recovered" if completed else "failed")
                    )
                ),
            }
        )
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    canonical_path = assert_canonical_map(args.map_path)
    if canonical_path != CANONICAL_MAP_PATH or args.map_sha256 != CANONICAL_MAP_SHA256:
        raise ValueError(
            "G4IRSF11 worker is fixed-real-map-only: "
            f"path={canonical_path}, declared_sha256={args.map_sha256}"
        )
    workload = load_jsonl(args.workload)
    case_spec = parse_json_object(args.case_spec_json, label="--case-spec-json")
    input_artifact = parse_json_object(
        args.input_artifact_json, label="--input-artifact-json"
    )
    fault_artifact = parse_json_object(
        args.fault_artifact_json, label="--fault-artifact-json"
    )
    actual_input_artifact = workload_binding(args.workload, workload)
    if actual_input_artifact != input_artifact:
        raise ValueError(
            f"workload artifact does not match parent declaration: "
            f"actual={actual_input_artifact}, declared={input_artifact}"
        )
    raw_fault_rows: list[dict[str, Any]] = []
    if args.fault_windows is not None:
        raw_fault_rows = read_json_array(args.fault_windows)
    actual_fault_artifact = fault_binding(args.fault_windows, raw_fault_rows)
    if actual_fault_artifact != fault_artifact:
        raise ValueError(
            f"fault artifact does not match parent declaration: "
            f"actual={actual_fault_artifact}, declared={fault_artifact}"
        )
    actual_map_sha256 = normalised_text_sha256(canonical_path)
    if actual_map_sha256 != args.map_sha256:
        raise ValueError(
            f"map sha256 mismatch: actual={actual_map_sha256}, declared={args.map_sha256}"
        )
    nodes, edges, heuristic = graph_records(canonical_path)
    windows = _fault_windows(args.fault_windows)
    memory_before, peak_before = process_working_set_bytes()
    wall_started = time.perf_counter()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=binding_bag_records(workload),
        fault_windows=[
            (
                window.start,
                window.end,
                window.fault_time,
                window.repair_time,
                window.message_delay,
                window.drop_notification,
            )
            for window in windows
        ],
        queue_discipline=args.queue_discipline,
        retry_interval=args.retry_interval,
        minimum_service_seconds=args.minimum_service_seconds,
        dispatch_headway_seconds=args.dispatch_headway_seconds,
        history_limit=args.history_limit,
        max_decisions_per_bag=args.max_decisions_per_bag,
        max_events=args.max_events,
        max_simulation_time=args.max_simulation_time,
        trace_limit=args.trace_limit,
        trace_shard_count=args.trace_shard_count,
        trace_shard_index=args.trace_shard_index,
        local_queue_capacity=args.local_queue_capacity,
        deadlock_retry_threshold=args.deadlock_retry_threshold,
        diagnostic_hops=args.diagnostic_hops,
        enable_source_admission=args.enable_source_admission,
        enable_backpressure=args.enable_backpressure,
        enable_pibt_lite=args.enable_pibt_lite,
        enable_deadlock_escape=args.enable_deadlock_escape,
        enable_fault_policy=args.enable_fault_policy,
        scenario=args.scenario,
        scale=args.scale,
        search_path=args.search_path,
    )
    wall_seconds = time.perf_counter() - wall_started
    memory_after, peak_after = process_working_set_bytes()
    summary = dict(payload["summary"])
    raw_bags, enriched_segments = aggregate_raw_bags(workload, list(payload["bags"]))
    gate = CapacityGateConfig(
        max_backlog_slope_fraction=args.max_backlog_slope_fraction,
        max_drain_seconds=args.max_drain_seconds,
        max_p95_total_seconds=args.max_p95_service_seconds,
        max_p99_total_seconds=args.max_p99_service_seconds,
        max_deadline_miss_rate=args.max_deadline_miss_rate,
        starvation_seconds=args.starvation_seconds,
    )
    bag_metrics = capacity_metrics(raw_bags, summary, gate)
    segment_metrics = capacity_metrics(enriched_segments, summary, gate)
    fault_rows = fault_window_metrics(
        enriched_segments,
        list(payload["fault_events"]),
        summary,
        windows,
        max_recovery_seconds=args.max_fault_recovery_seconds,
    ) if windows else []

    decisions = list(payload["decision_trace"])
    trace_context = dict(payload["trace_context"])
    trace_context["run_id"] = args.run_id
    trace_context["scenario"] = args.scenario
    trace_context["fault_mode"] = args.fault_mode
    trace_context["fixed_real_map_only"] = True
    trace_context["canonical_map_sha256"] = CANONICAL_MAP_SHA256
    if args.trace_output is not None:
        _write_json(
            args.trace_output,
            {
                "decision_trace": decisions,
                "trace_context": trace_context,
                "summary": summary,
            },
        )
    if args.outcome_output is not None:
        _write_jsonl(
            args.outcome_output,
            _outcomes(
                decisions,
                enriched_segments,
                fault_mode=args.fault_mode,
                exposure_rows=list(payload["hold_attempts"]),
            ),
        )
    if args.trace_task_output is not None:
        traced_identities = {
            (int(row["task_id"]), str(row["segment_id"])) for row in decisions
        }
        _write_jsonl(
            args.trace_task_output,
            [
                row
                for row in workload
                if (int(row["task_id"]), str(row["segment_id"])) in traced_identities
            ],
        )

    invariant_pass = (
        int(summary.get("reservation_conflicts", 0)) == 0
        and int(summary.get("runtime_full_astar_calls", 0)) == 0
        and int(summary.get("global_reservation_scan_count", 0)) == 0
        and int(summary.get("max_edges_selected_per_arrive", 0)) <= 1
        and int(summary.get("release_selected_edge_count", 0)) == 0
        and int(summary.get("two_step_reservation_count", 0)) == 0
        and int(summary.get("full_future_routes_stored", 0)) == 0
    )
    config = runtime_config_from_namespace(args)
    measurement_cohort = {
        "name": args.measurement_cohort,
        "declared_concurrent_worker_target": args.concurrent_worker_target,
    }
    junction_state = derive_junction_evidence(
        list(payload["junction_state"]),
    )
    peak_junction_local_bytes = max(
        (
            int(row["peak_local_state_accounted_bytes"])
            for row in junction_state
        ),
        default=0,
    )
    sum_final_junction_local_bytes = sum(
        int(row["final_local_state_accounted_bytes"]) for row in junction_state
    )
    max_junction_service_utilization = max(
        (float(row["service_utilization"]) for row in junction_state),
        default=0.0,
    )
    if junction_state:
        bottleneck = min(
            junction_state, key=lambda row: int(row["bottleneck_rank"])
        )
        bottleneck_node = int(bottleneck["node"])
        bottleneck_score = float(bottleneck["bottleneck_score"])
    else:
        bottleneck_node = -1
        bottleneck_score = 0.0
    result: dict[str, Any] = {
        "schema": "czr005.g4irsf11.event_runtime_result.v3",
        "run_id": args.run_id,
        "case": case_spec,
        "protocol_version": args.protocol_version,
        "protocol_manifest_sha256": args.protocol_manifest_sha256,
        "input_artifact": input_artifact,
        "fault_artifact": fault_artifact,
        "map_sha256": args.map_sha256,
        "map_identity": canonical_map_identity(),
        "fixed_real_map_only": True,
        "source_sha256": args.source_sha256,
        "implementation_sha256": args.implementation_sha256,
        "scenario": args.scenario,
        "scale": args.scale,
        "workload_mode": args.workload_mode,
        "workload_path": str(args.workload.resolve()),
        "workload_segment_count": len(workload),
        "raw_bag_count": len(raw_bags),
        "config": config,
        "measurement_cohort": measurement_cohort,
        "environment": {
            "python_executable": str(Path(sys.executable).resolve()),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "os_name": os.name,
            "search_path": str(args.search_path.resolve()) if args.search_path else "",
        },
        "summary": summary,
        "raw_bag_capacity_metrics": bag_metrics,
        "segment_capacity_metrics": segment_metrics,
        "fault_window_metrics": fault_rows,
        "resource_metrics": {
            "measurement_scope": "isolated_worker_process",
            "runtime_thread_count": 1,
            "junction_count": len(junction_state),
            "peak_active_bag_count": int(summary["peak_active_bag_count"]),
            "working_set_before_bytes": memory_before,
            "peak_working_set_before_bytes": peak_before,
            "working_set_after_bytes": memory_after,
            "peak_working_set_bytes": peak_after,
            "peak_working_set_growth_from_initial_current_bytes": max(0, peak_after - memory_before),
            "cpp_internal_accounted_bytes": int(summary.get("cpp_internal_accounted_bytes", 0)),
            "peak_junction_local_state_accounted_bytes": peak_junction_local_bytes,
            "sum_final_junction_local_state_accounted_bytes": sum_final_junction_local_bytes,
            "max_junction_service_utilization": max_junction_service_utilization,
            "bottleneck_node": bottleneck_node,
            "bottleneck_score": bottleneck_score,
            "junction_local_state_accounting_semantics": (
                JUNCTION_LOCAL_STATE_ACCOUNTING_SEMANTICS
            ),
            "junction_service_utilization_semantics": (
                JUNCTION_SERVICE_UTILIZATION_SEMANTICS
            ),
            "junction_bottleneck_score_semantics": (
                JUNCTION_BOTTLENECK_SCORE_SEMANTICS
            ),
            "wall_seconds_including_pybind_materialization": wall_seconds,
        },
        "trace": {
            "trace_output": str(args.trace_output) if args.trace_output else "",
            "outcome_output": str(args.outcome_output) if args.outcome_output else "",
            "trace_task_output": str(args.trace_task_output) if args.trace_task_output else "",
            "decision_rows_stored": len(decisions),
            "hold_rows_stored": len(payload["hold_attempts"]),
            "trace_context": trace_context,
        },
        "event_sample": list(payload["events"])[:100],
        "fault_event_sample": list(payload["fault_events"])[:100],
        "bag_sample": enriched_segments[:100],
        "junction_state": junction_state,
        "event_runtime_invariant_pass": invariant_pass,
        "completion_pass": (
            int(summary.get("completed_count", 0)) == len(workload)
            and int(summary.get("failed_count", 0)) == 0
            and not bool(summary.get("event_limit_reached", False))
            and not bool(summary.get("time_limit_reached", False))
        ),
    }
    if args.workload_mode == "rolling_multiday_carryover" and args.scale in {2.0, 7.0}:
        result["continuity_metrics"] = rolling_continuity_metrics(
            workload,
            enriched_segments,
            expected_copies=int(args.scale),
            runtime_instance_id=args.run_id,
        )
    expectation = ResultExpectation(
        run_id=args.run_id,
        case=case_spec,
        protocol_version=args.protocol_version,
        protocol_manifest_sha256=args.protocol_manifest_sha256,
        input_artifact=input_artifact,
        fault_artifact=fault_artifact,
        fault_rows=raw_fault_rows,
        map_sha256=args.map_sha256,
        source_sha256=args.source_sha256,
        implementation_sha256=args.implementation_sha256,
        config=config,
        measurement_cohort=measurement_cohort,
    )
    validation_errors = validate_event_result(
        result,
        expectation,
        workload_rows=workload,
    )
    if validation_errors:
        raise ValueError("strict v3 result validation failed: " + "; ".join(validation_errors))
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--run-id", required=True)
    result.add_argument("--protocol-version", required=True)
    result.add_argument("--protocol-manifest-sha256", required=True)
    result.add_argument("--case-spec-json", required=True)
    result.add_argument("--input-artifact-json", required=True)
    result.add_argument("--fault-artifact-json", required=True)
    result.add_argument("--map-sha256", required=True)
    result.add_argument("--source-sha256", required=True)
    result.add_argument("--implementation-sha256", required=True)
    result.add_argument("--measurement-cohort", required=True)
    result.add_argument("--concurrent-worker-target", type=int, required=True)
    result.add_argument("--workload", type=Path, required=True)
    result.add_argument("--map", dest="map_path", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--search-path", type=Path)
    result.add_argument("--scenario", required=True)
    result.add_argument("--scale", type=float, required=True)
    result.add_argument("--workload-mode", required=True)
    result.add_argument("--fault-mode", default="no_fault")
    result.add_argument("--fault-windows", type=Path, required=True)
    result.add_argument("--trace-output", type=Path)
    result.add_argument("--outcome-output", type=Path)
    result.add_argument("--trace-task-output", type=Path)
    result.add_argument("--queue-discipline", choices=("fifo", "deadline", "aging"), default="aging")
    result.add_argument("--retry-interval", type=float, default=WORKER_RUNTIME_DEFAULTS["retry_interval"])
    result.add_argument("--minimum-service-seconds", type=float, default=WORKER_RUNTIME_DEFAULTS["minimum_service_seconds"])
    result.add_argument("--dispatch-headway-seconds", type=float, default=WORKER_RUNTIME_DEFAULTS["dispatch_headway_seconds"])
    result.add_argument("--history-limit", type=int, default=WORKER_RUNTIME_DEFAULTS["history_limit"])
    result.add_argument("--max-decisions-per-bag", type=int, default=WORKER_RUNTIME_DEFAULTS["max_decisions_per_bag"])
    result.add_argument("--max-events", type=int, default=20_000_000)
    result.add_argument("--max-simulation-time", type=float, default=WORKER_RUNTIME_DEFAULTS["max_simulation_time"])
    result.add_argument("--trace-limit", type=int, default=0)
    result.add_argument("--trace-shard-count", type=int, default=WORKER_RUNTIME_DEFAULTS["trace_shard_count"])
    result.add_argument("--trace-shard-index", type=int, default=WORKER_RUNTIME_DEFAULTS["trace_shard_index"])
    result.add_argument("--local-queue-capacity", type=int, default=WORKER_RUNTIME_DEFAULTS["local_queue_capacity"])
    result.add_argument("--deadlock-retry-threshold", type=int, default=WORKER_RUNTIME_DEFAULTS["deadlock_retry_threshold"])
    result.add_argument("--diagnostic-hops", type=int, default=2)
    result.add_argument("--enable-source-admission", action=argparse.BooleanOptionalAction, default=True)
    result.add_argument("--enable-backpressure", action=argparse.BooleanOptionalAction, default=True)
    result.add_argument("--enable-pibt-lite", action=argparse.BooleanOptionalAction, default=True)
    result.add_argument("--enable-deadlock-escape", action=argparse.BooleanOptionalAction, default=True)
    result.add_argument("--enable-fault-policy", action=argparse.BooleanOptionalAction, default=True)
    result.add_argument("--max-backlog-slope-fraction", type=float, default=CAPACITY_SLO["max_backlog_slope_fraction"])
    result.add_argument("--max-drain-seconds", type=float, default=CAPACITY_SLO["max_drain_seconds"])
    result.add_argument("--max-p95-service-seconds", type=float, default=CAPACITY_SLO["max_p95_service_seconds"])
    result.add_argument("--max-p99-service-seconds", type=float, default=CAPACITY_SLO["max_p99_service_seconds"])
    result.add_argument("--max-deadline-miss-rate", type=float, default=CAPACITY_SLO["max_deadline_miss_rate"])
    result.add_argument("--starvation-seconds", type=float, default=CAPACITY_SLO["starvation_seconds"])
    result.add_argument("--max-fault-recovery-seconds", type=float, default=FAULT_SLO["max_fault_recovery_seconds"])
    return result


def main() -> None:
    args = parser().parse_args()
    if args.concurrent_worker_target <= 0:
        raise SystemExit("--concurrent-worker-target must be positive")
    if not args.measurement_cohort.strip():
        raise SystemExit("--measurement-cohort must be non-empty")
    output = run(args)
    _write_json(args.output, output)
    print(json.dumps({"scenario": args.scenario, "output": str(args.output), "completion_pass": output["completion_pass"]}))


if __name__ == "__main__":
    main()
