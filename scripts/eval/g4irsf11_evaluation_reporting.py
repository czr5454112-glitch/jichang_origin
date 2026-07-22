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
    fault_pass = bool(fault_rows) and all(
        bool(row.get("fault_recovery_pass")) for row in fault_rows if isinstance(row, Mapping)
    )
    if case.fault_profile == "no_fault":
        fault_pass = True
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
        "drain_time_seconds": _finite(bag.get("drain_time_seconds", "")),
        "backlog_area_seconds": _finite(bag.get("backlog_area_seconds", "")),
        "original_entry_p95_seconds": _finite(bag.get("total_time_p95_seconds", "")),
        "original_entry_p99_seconds": _finite(bag.get("total_time_p99_seconds", "")),
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
        content = [
            f"# {title}",
            "",
            f"Generated: `{date.today().isoformat()}`.",
            "",
            boundary,
            "",
            f"Execution status counts: `{json.dumps(_status_counts(category_rows), sort_keys=True)}`.",
            "",
            _table(
                ["Case", "Mode", "Scale", "Exec", "Safe", "Queue", "Service", "Capacity", "p99 s", "End backlog", "Blocker"],
                (
                    (
                        row["case_id"], row["workload_mode"], row["scale"], row["execution_status"],
                        row["safe_execution_pass"], row["queue_stability_pass"], row["service_level_pass"],
                        row["capacity_pass"], row["java_release_tth_p99_seconds"], row["end_backlog"], row["blocker"],
                    )
                    for row in category_rows
                ),
            ),
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

    def all_executed(items: Sequence[Mapping[str, Any]]) -> bool:
        return bool(items) and all(item.get("execution_status") == "EXECUTED" for item in items)

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
            "status": "PASS" if all_executed(ablations) and all(row.get("event_runtime_invariant_pass") for row in ablations) else "PARTIAL_WITH_EXPLICIT_BLOCKER",
            "evidence": f"executed={sum(row.get('execution_status') == 'EXECUTED' for row in ablations)}/{len(ablations)}",
        },
        {
            "gate": "temporal_fault_recovery",
            "status": "PASS" if all_executed(faults) and all(row.get("fault_recovery_pass") for row in faults) else "PARTIAL_WITH_EXPLICIT_BLOCKER",
            "evidence": f"executed={sum(row.get('execution_status') == 'EXECUTED' for row in faults)}/{len(faults)}",
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
