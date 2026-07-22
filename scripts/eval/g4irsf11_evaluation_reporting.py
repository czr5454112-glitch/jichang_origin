"""Machine-readable tables and concise reports for G4IRSF11 experiments."""

from __future__ import annotations

import csv
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from scripts.eval.g4irsf11_experiment_protocol import CaseSpec, formal_cases
from scripts.eval.g4irsf11_result_validation import atomic_write_text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _value(mapping: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return default
        current = current.get(key, default)
    return current


def _finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return "INF" if value > 0.0 else "-INF"
    return value


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "pass"}:
            return True
        if normalized in {"false", "0", "no", "fail"}:
            return False
    return None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value >= 0 and value.is_integer() else None
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdigit():
            return int(normalized)
    return None


def _comparable(value: Any) -> tuple[str, Any] | None:
    if value is None or value == "":
        return None
    boolean = _boolean(value)
    if boolean is not None and (isinstance(value, bool) or str(value).strip().lower() in {"true", "false"}):
        return ("bool", boolean)
    if not isinstance(value, bool):
        try:
            number = float(value)
        except (TypeError, ValueError):
            pass
        else:
            if math.isfinite(number):
                return ("number", number)
    return ("text", str(value).strip())


def case_row(
    case: CaseSpec,
    result: Mapping[str, Any] | None,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    result = result or {}
    bag = _value(result, "raw_bag_capacity_metrics", default={})
    segment = _value(result, "segment_capacity_metrics", default={})
    summary = _value(result, "summary", default={})
    resource = _value(result, "resource_metrics", default={})
    fault_rows = _value(result, "fault_window_metrics", default=[])
    continuity = _value(result, "continuity_metrics", default={})
    if not isinstance(continuity, Mapping):
        continuity = {}
    continuity_input = _value(continuity, "input_audit", default={})
    if not isinstance(continuity_input, Mapping):
        continuity_input = {}
    if not isinstance(fault_rows, list):
        fault_rows = []
    typed_fault_rows = [row for row in fault_rows if isinstance(row, Mapping)]
    fault_pass = (
        bool(typed_fault_rows)
        and len(typed_fault_rows) == len(fault_rows)
        and all(
            row.get("fault_recovery_pass") is True for row in typed_fault_rows
        )
    )
    if case.fault_profile == "no_fault":
        fault_pass = True
    observed_recovery_times = [
        float(row["recovery_time_seconds"])
        for row in typed_fault_rows
        if row.get("recovery_observed") is True
        and isinstance(row.get("recovery_time_seconds"), (int, float))
        and not isinstance(row.get("recovery_time_seconds"), bool)
        and math.isfinite(float(row["recovery_time_seconds"]))
    ]
    fault_gate_failures = []
    for index, row in enumerate(typed_fault_rows):
        failures = row.get("fault_recovery_gate_failures")
        if isinstance(failures, list) and failures:
            fault_gate_failures.append(
                f"window_{index}:" + ",".join(str(value) for value in failures)
            )
    return {
        "case_id": case.case_id,
        "category": case.category,
        "workload_mode": case.workload_mode,
        "scale": case.scale,
        "segment_limit": "" if case.segment_limit is None else case.segment_limit,
        "execution_status": execution.get("status", "NOT_RUN"),
        "return_code": execution.get("return_code", ""),
        "run_id": execution.get("run_id", ""),
        "protocol_version": execution.get("protocol_version", ""),
        "protocol_manifest_sha256": execution.get("protocol_manifest_sha256", ""),
        "implementation_sha256": execution.get("implementation_sha256", ""),
        "map_sha256": execution.get("map_sha256", ""),
        "input_sha256": execution.get("input_sha256", ""),
        "result_sha256": _value(execution, "result_artifact", "sha256", default=""),
        "measurement_cohort": _value(execution, "measurement_cohort", "name", default=""),
        "declared_concurrent_worker_target": _value(
            execution,
            "measurement_cohort",
            "declared_concurrent_worker_target",
            default="",
        ),
        "command": execution.get("command", ""),
        "workload_segment_count": result.get("workload_segment_count", ""),
        "raw_bag_count": result.get("raw_bag_count", ""),
        "completed_segment_count": summary.get("completed_count", ""),
        "failed_segment_count": summary.get("failed_count", ""),
        "event_runtime_invariant_pass": result.get("event_runtime_invariant_pass", False),
        "completion_pass": result.get("completion_pass", False),
        "safe_execution_pass": segment.get("safe_execution_pass", False),
        "queue_stability_pass": bag.get("queue_stability_pass", False),
        "service_level_pass": bag.get("service_level_pass", False),
        "capacity_pass": bag.get("capacity_pass", False),
        "fault_recovery_pass": fault_pass,
        "fault_window_count": len(typed_fault_rows),
        "fault_recovery_observed_count": sum(
            row.get("recovery_observed") is True for row in typed_fault_rows
        ),
        "fault_recovery_unobserved_count": sum(
            row.get("recovery_observed") is False for row in typed_fault_rows
        ),
        "fault_recovery_time_seconds_max": (
            max(observed_recovery_times) if observed_recovery_times else ""
        ),
        "fault_recovery_times_seconds_json": json.dumps(
            [row.get("recovery_time_seconds") for row in typed_fault_rows],
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ),
        "fault_backlog_before_fault_json": json.dumps(
            [row.get("backlog_before_fault") for row in typed_fault_rows],
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ),
        "fault_backlog_at_repair_json": json.dumps(
            [row.get("backlog_at_repair") for row in typed_fault_rows],
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ),
        "fault_recovery_gate_failures": "; ".join(fault_gate_failures),
        "continuity_status": continuity.get("status", ""),
        "continuity_single_runtime_invocation_pass": continuity.get(
            "single_runtime_invocation_pass", ""
        ),
        "continuity_runtime_instance_id": continuity.get("runtime_instance_id", ""),
        "continuity_boundary_count": continuity.get("boundary_count", ""),
        "continuity_cross_boundary_completion_count": continuity.get(
            "cross_boundary_completion_count", ""
        ),
        "continuity_carry_over_observed": continuity.get("carry_over_observed", ""),
        "continuity_input_audit_status": continuity_input.get("status", ""),
        "continuity_input_expected_copy_count": continuity_input.get(
            "expected_copy_count", ""
        ),
        "continuity_input_workload_row_count": continuity_input.get(
            "workload_row_count", ""
        ),
        "continuity_input_base_segment_count": continuity_input.get(
            "base_segment_count", ""
        ),
        "continuity_input_coverage_sha256": continuity_input.get("coverage_sha256", ""),
        "continuity_blockers": "; ".join(
            str(value) for value in continuity.get("blockers", [])
        ),
        "backlog_slope_fraction": _finite(bag.get("backlog_slope_fraction_of_arrival_rate", "")),
        "end_backlog": bag.get("end_backlog", ""),
        "peak_backlog": bag.get("peak_backlog", ""),
        "drain_time_seconds": _finite(bag.get("drain_time_seconds", "")),
        "backlog_area_seconds": _finite(bag.get("backlog_area_seconds", "")),
        "source_peak_backlog": bag.get("source_peak_backlog", ""),
        "source_end_backlog": bag.get("source_end_backlog", ""),
        "source_backlog_area_seconds": _finite(
            bag.get("source_backlog_area_seconds", "")
        ),
        "network_peak_backlog": bag.get("network_peak_backlog", ""),
        "network_end_backlog": bag.get("network_end_backlog", ""),
        "original_entry_p95_seconds": _finite(bag.get("total_time_p95_seconds", "")),
        "original_entry_p99_seconds": _finite(bag.get("total_time_p99_seconds", "")),
        "source_delay_p95_seconds": _finite(bag.get("source_delay_p95_seconds", "")),
        "source_delay_p99_seconds": _finite(bag.get("source_delay_p99_seconds", "")),
        "network_time_p95_seconds": _finite(bag.get("network_time_p95_seconds", "")),
        "java_release_tth_p95_seconds": _finite(bag.get("java_release_tth_p95_seconds", "")),
        "java_release_tth_p99_seconds": _finite(bag.get("java_release_tth_p99_seconds", "")),
        "deadline_miss_rate": _finite(bag.get("deadline_miss_rate", "")),
        "starvation_count": bag.get("starvation_count", ""),
        "max_wait_seconds": _finite(bag.get("max_wait_seconds", "")),
        "wait_fairness_jain": _finite(bag.get("wait_fairness_jain", "")),
        "conflict_count": summary.get("reservation_conflicts", ""),
        "deadlock_count": summary.get("deadlock_count", ""),
        "resolved_deadlock_count": summary.get("resolved_deadlock_count", ""),
        "unresolved_deadlock_count": summary.get("unresolved_deadlock_count", ""),
        "loop_count": summary.get("loop_count", ""),
        "source_admission_enabled": summary.get("source_admission_enabled", ""),
        "source_admission_attempt_count": summary.get(
            "source_admission_attempt_count", ""
        ),
        "source_admission_admitted_count": summary.get(
            "source_admission_admitted_count", ""
        ),
        "source_admission_local_resource_hold_count": summary.get(
            "source_admission_local_resource_hold_count", ""
        ),
        "source_admission_downstream_pressure_hold_count": summary.get(
            "source_admission_downstream_pressure_hold_count", ""
        ),
        "source_admission_beacon_read_count": summary.get(
            "source_admission_beacon_read_count", ""
        ),
        "source_admission_max_observed_downstream_pressure": _finite(
            summary.get("source_admission_max_observed_downstream_pressure", "")
        ),
        "runtime_full_astar_calls": summary.get("runtime_full_astar_calls", ""),
        "global_reservation_scan_count": summary.get("global_reservation_scan_count", ""),
        "decision_count": summary.get("decision_count", ""),
        "event_count": summary.get("event_count", ""),
        "decision_latency_us_p50": _finite(summary.get("decision_latency_us_p50", "")),
        "decision_latency_us_p95": _finite(summary.get("decision_latency_us_p95", "")),
        "decision_latency_us_p99": _finite(summary.get("decision_latency_us_p99", "")),
        "event_throughput_per_second": _finite(summary.get("event_throughput_per_second", "")),
        "runtime_thread_count": resource.get("runtime_thread_count", ""),
        "junction_count": resource.get("junction_count", ""),
        "peak_active_bag_count": resource.get("peak_active_bag_count", ""),
        "peak_working_set_bytes": resource.get("peak_working_set_bytes", ""),
        "cpp_internal_accounted_bytes": resource.get("cpp_internal_accounted_bytes", ""),
        "peak_junction_local_state_accounted_bytes": resource.get(
            "peak_junction_local_state_accounted_bytes", ""
        ),
        "sum_final_junction_local_state_accounted_bytes": resource.get(
            "sum_final_junction_local_state_accounted_bytes", ""
        ),
        "max_junction_service_utilization": _finite(
            resource.get("max_junction_service_utilization", "")
        ),
        "bottleneck_node": resource.get("bottleneck_node", ""),
        "bottleneck_score": _finite(resource.get("bottleneck_score", "")),
        "wall_seconds": _finite(resource.get("wall_seconds_including_pybind_materialization", "")),
        "fault_profile": case.fault_profile,
        "queue_discipline": case.queue_discipline,
        "enable_source_admission": case.enable_source_admission,
        "enable_backpressure": case.enable_backpressure,
        "enable_pibt_lite": case.enable_pibt_lite,
        "enable_deadlock_escape": case.enable_deadlock_escape,
        "enable_fault_policy": case.enable_fault_policy,
        "diagnostic_hops": case.diagnostic_hops,
        "notes": case.notes,
        "blocker": execution.get("blocker", ""),
    }


def write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not fieldnames:
        raise ValueError(f"refusing to write empty CSV: {path}")
    output_fields: list[str] = list(fieldnames or ())
    if not output_fields:
        for row in rows:
            for key in row:
                if key not in output_fields:
                    output_fields.append(str(key))
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=output_fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, handle.getvalue())


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _status_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        status = str(row.get("execution_status", "NOT_RUN"))
        result[status] = result.get(status, 0) + 1
    return dict(sorted(result.items()))


def write_reports(root: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Path]:
    report_dir = root / "outputs" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    by_category: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_category.setdefault(str(row["category"]), []).append(row)

    specs = {
        "size_ladder": (
            "g4irsf11_event_runtime_correctness_report.md",
            "G4IRSF11 Event Runtime Correctness",
            "The 144/512/1024 rows are real-map correctness samples. Only `real_map_paper_full` is paper-full evidence.",
        ),
        "capacity_frontier": (
            "g4irsf11_capacity_frontier_report.md",
            "G4IRSF11 Fractional Capacity Frontier",
            "Each workload mode is an independent derived protocol. Results are never pooled into one convenient frontier.",
        ),
        "system_ablation": (
            "g4irsf11_system_ablation_report.md",
            "G4IRSF11 Local-Control System A/B",
            "A/B rows change one declared local controller component. Two-hop state is diagnostic-only; reservations remain one step.",
        ),
        "temporal_fault": (
            "g4irsf11_temporal_fault_report.md",
            "G4IRSF11 Temporal Fault/Repair",
            "These are physical fault and repair windows with explicit notification delay/loss, not static edge-removal proxies.",
        ),
    }
    written: dict[str, Path] = {}
    for category, (filename, title, boundary) in specs.items():
        category_rows = sorted(by_category.get(category, []), key=lambda row: str(row["case_id"]))
        path = report_dir / filename
        common_table = _table(
            [
                "Case", "Mode", "Scale", "Exec", "Safe", "Queue", "Service",
                "Capacity", "p99 s", "End backlog", "Blocker",
            ],
            (
                (
                    row["case_id"], row["workload_mode"], row["scale"],
                    row["execution_status"], row["safe_execution_pass"],
                    row["queue_stability_pass"], row["service_level_pass"],
                    row["capacity_pass"], row["java_release_tth_p99_seconds"],
                    row["end_backlog"], row["blocker"],
                )
                for row in category_rows
            ),
        )
        report_tables = [common_table]
        if category == "temporal_fault":
            report_tables.append(
                _table(
                    [
                        "Case", "Fault recovery", "Recovered windows",
                        "Unrecovered windows", "Recovery times s",
                        "Backlog before fault", "Backlog at repair",
                        "Fault gate failures",
                    ],
                    (
                        (
                            row["case_id"], row["fault_recovery_pass"],
                            row["fault_recovery_observed_count"],
                            row["fault_recovery_unobserved_count"],
                            row["fault_recovery_times_seconds_json"],
                            row["fault_backlog_before_fault_json"],
                            row["fault_backlog_at_repair_json"],
                            row["fault_recovery_gate_failures"],
                        )
                        for row in category_rows
                    ),
                )
            )
        content = [
            f"# {title}",
            "",
            f"Generated: `{date.today().isoformat()}`.",
            "",
            (
                boundary
                + (
                    " A null recovery time means NOT_RECOVERED_BY_RUN_END; it is explicit negative evidence and fails the recovery gate."
                    if category == "temporal_fault"
                    else ""
                )
            ),
            "",
            f"Execution status counts: `{json.dumps(_status_counts(category_rows), sort_keys=True)}`.",
            "",
            "\n\n".join(report_tables),
            "",
        ]
        atomic_write_text(path, "\n".join(content))
        written[category] = path

    resource_path = report_dir / "g4irsf11_runtime_resource_report.md"
    executed = [row for row in rows if row.get("execution_status") == "EXECUTED"]
    atomic_write_text(
        resource_path,
        "\n".join(
            [
                "# G4IRSF11 Runtime Resource Measurements",
                "",
                f"Generated: `{date.today().isoformat()}`.",
                "",
                "Peak memory is the isolated worker process peak working set. `cpp_internal_accounted_bytes` and per-junction local bytes are separately labelled C++ lower-bound accounting values; neither is a JSON-size estimate. The event runtime is the declared single-thread baseline.",
                "",
                _table(
                    [
                        "Case", "Segments", "Junctions", "Peak active bags", "Threads",
                        "Peak working set", "C++ bytes", "Peak junction bytes",
                        "Final junction byte sum", "Max junction util.", "Bottleneck node",
                        "Bottleneck score", "Decision p99 us", "Events/s", "Wall s",
                    ],
                    (
                        (
                            row["case_id"], row["workload_segment_count"], row["junction_count"],
                            row["peak_active_bag_count"], row["runtime_thread_count"],
                            row["peak_working_set_bytes"], row["cpp_internal_accounted_bytes"],
                            row["peak_junction_local_state_accounted_bytes"],
                            row["sum_final_junction_local_state_accounted_bytes"],
                            row["max_junction_service_utilization"], row["bottleneck_node"],
                            row["bottleneck_score"], row["decision_latency_us_p99"],
                            row["event_throughput_per_second"], row["wall_seconds"],
                        )
                        for row in executed
                    ),
                ),
                "",
            ]
        ),
    )
    written["resources"] = resource_path
    return written


def gate_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    expected = {case.case_id: case for case in formal_cases()}
    observed = {str(row["case_id"]): row for row in rows}
    size_full = observed.get("real_map_paper_full", {})
    frontier = [observed.get(case.case_id, {}) for case in expected.values() if case.category == "capacity_frontier"]
    ablations = [observed.get(case.case_id, {}) for case in expected.values() if case.category == "system_ablation"]
    faults = [observed.get(case.case_id, {}) for case in expected.values() if case.category == "temporal_fault"]
    aging_baseline = observed.get("ablation_aging_full", {})
    source_admission_off = observed.get("ablation_source_admission_off", {})

    def all_executed(items: Sequence[Mapping[str, Any]]) -> bool:
        return bool(items) and all(item.get("execution_status") == "EXECUTED" for item in items)

    invariant_pass_count = sum(
        _boolean(row.get("event_runtime_invariant_pass")) is True for row in ablations
    )
    unresolved_deadlocks = [
        _nonnegative_int(row.get("unresolved_deadlock_count")) for row in ablations
    ]
    starvation_counts = [
        _nonnegative_int(row.get("starvation_count")) for row in ablations
    ]
    zero_unresolved_deadlock_count = sum(value == 0 for value in unresolved_deadlocks)
    zero_starvation_count = sum(value == 0 for value in starvation_counts)
    local_safety_pass = (
        all_executed(ablations)
        and invariant_pass_count == len(ablations)
        and zero_unresolved_deadlock_count == len(ablations)
        and zero_starvation_count == len(ablations)
    )

    source_counter_fields = (
        "source_admission_attempt_count",
        "source_admission_admitted_count",
        "source_admission_local_resource_hold_count",
        "source_admission_downstream_pressure_hold_count",
    )

    def source_counter_partition_pass(row: Mapping[str, Any]) -> bool:
        attempt, admitted, local_hold, pressure_hold = (
            _nonnegative_int(row.get(field)) for field in source_counter_fields
        )
        return (
            attempt is not None
            and admitted is not None
            and local_hold is not None
            and pressure_hold is not None
            and attempt == admitted + local_hold + pressure_hold
        )

    baseline_attempts = _nonnegative_int(
        aging_baseline.get("source_admission_attempt_count")
    )
    baseline_pressure_holds = _nonnegative_int(
        aging_baseline.get("source_admission_downstream_pressure_hold_count")
    )
    baseline_beacon_reads = _nonnegative_int(
        aging_baseline.get("source_admission_beacon_read_count")
    )
    baseline_max_pressure = _nonnegative_int(
        aging_baseline.get("source_admission_max_observed_downstream_pressure")
    )
    off_attempts = _nonnegative_int(
        source_admission_off.get("source_admission_attempt_count")
    )
    off_pressure_holds = _nonnegative_int(
        source_admission_off.get("source_admission_downstream_pressure_hold_count")
    )
    off_beacon_reads = _nonnegative_int(
        source_admission_off.get("source_admission_beacon_read_count")
    )
    off_max_pressure = _nonnegative_int(
        source_admission_off.get("source_admission_max_observed_downstream_pressure")
    )
    substantive_outcome_fields = (
        "completed_segment_count",
        "failed_segment_count",
        "completion_pass",
        "safe_execution_pass",
        "queue_stability_pass",
        "service_level_pass",
        "capacity_pass",
        "end_backlog",
        "peak_backlog",
        "backlog_area_seconds",
        "source_peak_backlog",
        "source_end_backlog",
        "source_backlog_area_seconds",
        "network_peak_backlog",
        "network_end_backlog",
        "original_entry_p95_seconds",
        "original_entry_p99_seconds",
        "source_delay_p95_seconds",
        "source_delay_p99_seconds",
        "network_time_p95_seconds",
        "deadline_miss_rate",
        "starvation_count",
        "max_wait_seconds",
        "wait_fairness_jain",
        "unresolved_deadlock_count",
        "loop_count",
    )
    substantive_differences = [
        field
        for field in substantive_outcome_fields
        if _comparable(aging_baseline.get(field)) is not None
        and _comparable(source_admission_off.get(field)) is not None
        and _comparable(aging_baseline.get(field))
        != _comparable(source_admission_off.get(field))
    ]
    source_partition_pass_count = sum(
        source_counter_partition_pass(row)
        for row in (aging_baseline, source_admission_off)
    )
    source_admission_operational = (
        aging_baseline.get("execution_status") == "EXECUTED"
        and source_admission_off.get("execution_status") == "EXECUTED"
        and _boolean(aging_baseline.get("source_admission_enabled")) is True
        and _boolean(source_admission_off.get("source_admission_enabled")) is False
        and baseline_attempts is not None
        and baseline_attempts > 0
        and baseline_pressure_holds is not None
        and baseline_pressure_holds > 0
        and baseline_beacon_reads is not None
        and baseline_beacon_reads > 0
        and baseline_max_pressure is not None
        and baseline_max_pressure > 0
        and off_attempts is not None
        and off_attempts > 0
        and off_pressure_holds == 0
        and off_beacon_reads == 0
        and off_max_pressure == 0
        and source_partition_pass_count == 2
        and bool(substantive_differences)
    )

    def count_evidence(value: int | None) -> str:
        return "MISSING" if value is None else str(value)

    gates = [
        {
            "gate": "paper_full_event_runtime",
            "status": "PASS" if size_full.get("execution_status") == "EXECUTED" and size_full.get("completion_pass") and size_full.get("event_runtime_invariant_pass") else "PARTIAL_WITH_EXPLICIT_BLOCKER",
            "evidence": "real_map_paper_full",
        },
        {
            "gate": "fractional_frontier_execution_complete",
            "status": "PASS" if all_executed(frontier) else "PARTIAL_WITH_EXPLICIT_BLOCKER",
            "evidence": f"executed={sum(row.get('execution_status') == 'EXECUTED' for row in frontier)}/{len(frontier)}",
        },
        {
            "gate": "local_safety_ablation",
            "status": "PASS" if local_safety_pass else "PARTIAL_WITH_EXPLICIT_BLOCKER",
            "evidence": (
                f"executed={sum(row.get('execution_status') == 'EXECUTED' for row in ablations)}/{len(ablations)}; "
                f"runtime_invariant_pass={invariant_pass_count}/{len(ablations)}; "
                f"zero_unresolved_deadlock={zero_unresolved_deadlock_count}/{len(ablations)}; "
                f"zero_starvation={zero_starvation_count}/{len(ablations)}; "
                "unresolved_deadlock_total="
                f"{sum(value for value in unresolved_deadlocks if value is not None) if all(value is not None for value in unresolved_deadlocks) else 'INCOMPLETE'}; "
                "starvation_total="
                f"{sum(value for value in starvation_counts if value is not None) if all(value is not None for value in starvation_counts) else 'INCOMPLETE'}"
            ),
        },
        {
            "gate": "source_admission_ablation_operational",
            "status": (
                "PASS"
                if source_admission_operational
                else "PARTIAL_WITH_EXPLICIT_BLOCKER"
            ),
            "evidence": (
                "aging_enabled="
                f"{_boolean(aging_baseline.get('source_admission_enabled'))}; "
                f"aging_attempts={count_evidence(baseline_attempts)}; "
                f"aging_pressure_holds={count_evidence(baseline_pressure_holds)}; "
                f"aging_beacon_reads={count_evidence(baseline_beacon_reads)}; "
                f"aging_max_pressure={count_evidence(baseline_max_pressure)}; "
                "off_enabled="
                f"{_boolean(source_admission_off.get('source_admission_enabled'))}; "
                f"off_attempts={count_evidence(off_attempts)}; "
                f"off_pressure_holds={count_evidence(off_pressure_holds)}; "
                f"off_beacon_reads={count_evidence(off_beacon_reads)}; "
                f"off_max_pressure={count_evidence(off_max_pressure)}; "
                f"counter_partition_pass={source_partition_pass_count}/2; "
                "substantive_outcome_differences="
                f"{','.join(substantive_differences) if substantive_differences else 'NONE'}"
            ),
        },
        {
            "gate": "temporal_fault_recovery",
            "status": "PASS" if all_executed(faults) and all(row.get("fault_recovery_pass") for row in faults) else "PARTIAL_WITH_EXPLICIT_BLOCKER",
            "evidence": (
                f"executed={sum(row.get('execution_status') == 'EXECUTED' for row in faults)}/{len(faults)}; "
                f"recovery_pass={sum(bool(row.get('fault_recovery_pass')) for row in faults)}/{len(faults)}; "
                "unrecovered_windows="
                f"{sum(int(row.get('fault_recovery_unobserved_count') or 0) for row in faults)}"
            ),
        },
        {
            "gate": "real_resource_instrumentation",
            "status": "PASS" if all_executed(list(observed.values())) and all(int(row.get("peak_working_set_bytes") or 0) > 0 for row in observed.values()) else "PARTIAL_WITH_EXPLICIT_BLOCKER",
            "evidence": "isolated worker OS working-set measurements",
        },
    ]
    return gates


def write_claim_boundary(root: Path, rows: Sequence[Mapping[str, Any]], gates: Sequence[Mapping[str, Any]]) -> Path:
    path = root / "outputs" / "reports" / "g4irsf11_claim_boundary_report.md"
    failed_capacity = [row for row in rows if row.get("category") == "capacity_frontier" and row.get("execution_status") == "EXECUTED" and not row.get("capacity_pass")]
    blockers = [row for row in rows if row.get("execution_status") != "EXECUTED"]
    overall = "PASS" if all(gate.get("status") == "PASS" for gate in gates) else "PARTIAL_WITH_EXPLICIT_BLOCKER"
    atomic_write_text(
        path,
        "\n".join(
            [
                "# G4IRSF11 Claim Boundary",
                "",
                f"Status: `{overall}`.",
                "",
                "G4IRSF10 16x remains a safe-execution result and an operational-capacity failure (mean 1551.371367 min, p99 3773.31410471 min, maximum source-queue delay 179743 s).",
                "",
                "The new event runtime selects at most one edge at ARRIVE_JUNCTION, stores no future route, uses local one-step calendars, and reports zero runtime full A* only when measured. Completion alone is never a capacity PASS.",
                "",
                f"Formal negative capacity rows retained: `{len(failed_capacity)}`.",
                f"Unexecuted/failed formal rows retained: `{len(blockers)}`.",
                "",
                _table(["Gate", "Status", "Evidence"], ((row["gate"], row["status"], row["evidence"]) for row in gates)),
                "",
                "G4J remains closed unless a separately accepted Java/CIE boundary report says otherwise. Remote GitHub Actions are not claimed from local pytest output.",
                "",
            ]
        ),
    )
    return path
