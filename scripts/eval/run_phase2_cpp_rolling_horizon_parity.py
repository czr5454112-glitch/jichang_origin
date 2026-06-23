from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = Path(os.environ.get("CZR005_CPP_PYTHON_PATH", ROOT / "build_nmake" / "python"))
TABLE_PATH = ROOT / "outputs" / "tables" / "phase2_cpp_rolling_horizon_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase2_cpp_rolling_horizon_parity_report.md"
FLOAT_TOLERANCE = 1.0e-9

NodeRecord = tuple[int, int, float, int, int, list[int]]
EdgeRecord = tuple[int, int, float, float]
TaskRecord = tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]
FaultWindow = tuple[int, int, float, float]

SUMMARY_FIELDS = (
    "planned_count",
    "unplanned_count",
    "reservation_conflicts",
    "edge_reservation_conflicts",
    "post_shield_conflicts",
    "mean_travel_time",
    "makespan",
)

EVENT_FIELDS = (
    "event",
    "segment_id",
    "task_id",
    "start",
    "goal",
    "entry_time",
    "finish_time",
    "horizon_start",
    "horizon_end",
    "priority_rank",
    "path",
)


@dataclass(frozen=True)
class RollingParityCase:
    name: str
    graph: Any
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    tasks: tuple[Any, ...]
    task_records: tuple[TaskRecord, ...]
    max_tasks: int
    horizon_seconds: float = 300.0
    edge_capacity: int = 1
    edge_headway_seconds: float = 0.0
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[FaultWindow, ...] = ()


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    build_candidates = (
        BUILD_PYTHON_PATH,
        ROOT / "build_vs" / "python" / "Debug",
        ROOT / "build_vs" / "python" / "Release",
        ROOT / "build_nmake" / "python",
    )
    for candidate in reversed(build_candidates):
        if candidate.exists():
            sys.path.insert(0, str(candidate))


def _task(segment_id: str, task_id: int, pass_time: float, std: float, goal: int) -> Any:
    from czr005.sim_py.task_stream import TaskLeg  # pylint: disable=import-outside-toplevel

    return TaskLeg(
        segment_id=segment_id,
        task_id=task_id,
        pallet_id=task_id,
        pass_time=pass_time,
        std=std,
        start=0,
        goal=goal,
        original_start=0,
        original_goal=goal,
        original_entry_time=pass_time,
        leg="direct",
        early_bag_split=False,
        source_line=task_id + 1,
    )


def _task_record(task: Any) -> TaskRecord:
    return (
        str(task.segment_id),
        int(task.task_id),
        int(task.pallet_id),
        float(task.pass_time),
        float(task.std),
        int(task.start),
        int(task.goal),
        int(task.original_start),
        int(task.original_goal),
        float(task.original_entry_time),
        str(task.leg),
        bool(task.early_bag_split),
        int(task.source_line),
    )


def _line_graph_inputs() -> tuple[
    Any,
    tuple[NodeRecord, ...],
    tuple[EdgeRecord, ...],
    tuple[tuple[float, ...], ...],
]:
    from czr005.sim_py import IcsGraph, SimEdge, SimNode  # pylint: disable=import-outside-toplevel

    node_records = (
        (0, 1, 0.0, 0, 0, [1]),
        (1, 4, 1.0, 1, 0, [2]),
        (2, 2, 0.0, 2, 0, []),
    )
    edge_records = ((0, 1, 5.0, 2.5), (1, 2, 5.0, 2.5))
    heuristic_time = ((0.0, 2.0, 4.0), (4.0, 0.0, 2.0), (4.0, 2.0, 0.0))
    graph = IcsGraph(
        nodes={
            location: SimNode(location, node_type, service_time, x, y, tuple(outgoing))
            for location, node_type, service_time, x, y, outgoing in node_records
        },
        edges={
            (start, end): SimEdge(start, end, length, speed)
            for start, end, length, speed in edge_records
        },
        heuristic_time=heuristic_time,
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )
    return graph, node_records, edge_records, heuristic_time


def _single_edge_inputs() -> tuple[
    Any,
    tuple[NodeRecord, ...],
    tuple[EdgeRecord, ...],
    tuple[tuple[float, ...], ...],
]:
    from czr005.sim_py import IcsGraph, SimEdge, SimNode  # pylint: disable=import-outside-toplevel

    node_records = ((0, 1, 0.0, 0, 0, [1]), (1, 2, 0.0, 1, 0, []))
    edge_records = ((0, 1, 5.0, 2.5),)
    heuristic_time = ((0.0, 2.0), (2.0, 0.0))
    graph = IcsGraph(
        nodes={
            location: SimNode(location, node_type, service_time, x, y, tuple(outgoing))
            for location, node_type, service_time, x, y, outgoing in node_records
        },
        edges={
            (start, end): SimEdge(start, end, length, speed)
            for start, end, length, speed in edge_records
        },
        heuristic_time=heuristic_time,
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )
    return graph, node_records, edge_records, heuristic_time


def _normalize_python_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": str(event["event"]),
        "segment_id": str(event["segment_id"]),
        "task_id": int(event["task_id"]),
        "start": int(event["start"]),
        "goal": int(event["goal"]),
        "entry_time": float(event["entry_time"]),
        "finish_time": float(event.get("finish_time", 0.0)),
        "horizon_start": float(event["horizon_start"]),
        "horizon_end": float(event["horizon_end"]),
        "priority_rank": int(event["priority_rank"]),
        "path": [int(value) for value in event.get("path", [])],
    }


def _python_payload(case: RollingParityCase) -> dict[str, Any]:
    from czr005.baselines import RollingHorizonBaseline  # pylint: disable=import-outside-toplevel

    baseline = RollingHorizonBaseline(
        case.graph,
        horizon_seconds=case.horizon_seconds,
        edge_capacity=case.edge_capacity,
        edge_headway_seconds=case.edge_headway_seconds,
    )
    result = baseline.run_episode(
        case.tasks,
        max_tasks=case.max_tasks,
        fault_edges=set(case.fault_edges),
        fault_windows=case.fault_windows,
    )
    edge_conflicts = baseline.edge_reservations.conflict_count(
        capacity=case.edge_capacity,
        headway_seconds=case.edge_headway_seconds,
    )
    return {
        "summary": {
            **result.metrics.to_dict(),
            "edge_reservation_conflicts": edge_conflicts,
            "post_shield_conflicts": result.metrics.reservation_conflicts + edge_conflicts,
            "decision_count": len(result.events),
        },
        "events": [_normalize_python_event(event) for event in result.events],
    }


def _cpp_payload(case: RollingParityCase) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    payload = czr005_cpp.rolling_horizon_sipp_from_records(
        list(case.node_records),
        list(case.edge_records),
        [list(row) for row in case.heuristic_time],
        list(case.task_records),
        max_tasks=case.max_tasks,
        horizon_seconds=case.horizon_seconds,
        edge_capacity=case.edge_capacity,
        edge_headway_seconds=case.edge_headway_seconds,
        fault_edges=list(case.fault_edges),
        fault_windows=list(case.fault_windows),
    )
    return {
        "summary": dict(payload["summary"]),
        "events": [dict(event) for event in payload["events"]],
    }


def _values_match(field: str, python_value: Any, cpp_value: Any) -> bool:
    if field == "path":
        return list(python_value) == list(cpp_value)
    if field in {"entry_time", "finish_time", "horizon_start", "horizon_end", "mean_travel_time", "makespan"}:
        return abs(float(python_value) - float(cpp_value)) <= FLOAT_TOLERANCE
    return python_value == cpp_value


def _first_mismatch(python_payload: dict[str, Any], cpp_payload: dict[str, Any]) -> dict[str, Any]:
    for field in SUMMARY_FIELDS:
        if not _values_match(field, python_payload["summary"][field], cpp_payload["summary"][field]):
            return {
                "status": "summary_mismatch",
                "index": "",
                "field": field,
                "python_value": python_payload["summary"][field],
                "cpp_value": cpp_payload["summary"][field],
            }
    python_events = python_payload["events"]
    cpp_events = cpp_payload["events"]
    shared = min(len(python_events), len(cpp_events))
    for index in range(shared):
        for field in EVENT_FIELDS:
            if not _values_match(field, python_events[index][field], cpp_events[index][field]):
                return {
                    "status": "event_mismatch",
                    "index": index,
                    "field": field,
                    "python_value": python_events[index][field],
                    "cpp_value": cpp_events[index][field],
                }
    if len(python_events) != len(cpp_events):
        return {
            "status": "event_length_mismatch",
            "index": shared,
            "field": "event_count",
            "python_value": len(python_events),
            "cpp_value": len(cpp_events),
        }
    return {"status": "match", "index": "", "field": "none", "python_value": "", "cpp_value": ""}


def _case_row(case: RollingParityCase) -> dict[str, float | int | str | bool]:
    python = _python_payload(case)
    cpp = _cpp_payload(case)
    mismatch = _first_mismatch(python, cpp)
    return {
        "case": case.name,
        "max_tasks": case.max_tasks,
        "horizon_seconds": case.horizon_seconds,
        "edge_capacity": case.edge_capacity,
        "edge_headway_seconds": case.edge_headway_seconds,
        "python_planned": int(python["summary"]["planned_count"]),
        "cpp_planned": int(cpp["summary"]["planned_count"]),
        "python_unplanned": int(python["summary"]["unplanned_count"]),
        "cpp_unplanned": int(cpp["summary"]["unplanned_count"]),
        "python_conflicts": int(python["summary"]["post_shield_conflicts"]),
        "cpp_conflicts": int(cpp["summary"]["post_shield_conflicts"]),
        "mean_travel_abs_diff": abs(
            float(python["summary"]["mean_travel_time"]) - float(cpp["summary"]["mean_travel_time"])
        ),
        "python_event_count": len(python["events"]),
        "cpp_event_count": len(cpp["events"]),
        "parity_pass": mismatch["status"] == "match",
        "first_mismatch_status": mismatch["status"],
        "first_mismatch_index": mismatch["index"],
        "first_mismatch_field": mismatch["field"],
        "python_value": mismatch["python_value"],
        "cpp_value": mismatch["cpp_value"],
    }


def _cases() -> tuple[RollingParityCase, ...]:
    from phase8_synthetic_replay_cases import (  # pylint: disable=import-outside-toplevel
        graph_from_case,
        load_manifest_cases,
        tasks_from_case,
    )

    line_graph, line_nodes, line_edges, line_heuristic = _line_graph_inputs()
    single_graph, single_nodes, single_edges, single_heuristic = _single_edge_inputs()
    priority_tasks = (_task("loose", 1, 0.1, 100.0, 2), _task("urgent", 2, 0.0, 20.0, 2))
    edge_tasks = (_task("urgent", 1, 0.0, 10.0, 1), _task("loose", 2, 0.1, 20.0, 1))
    cases: list[RollingParityCase] = [
        RollingParityCase(
            "line_priority",
            line_graph,
            line_nodes,
            line_edges,
            line_heuristic,
            priority_tasks,
            tuple(_task_record(task) for task in priority_tasks),
            max_tasks=2,
            horizon_seconds=60.0,
        ),
        RollingParityCase(
            "line_fault_unplanned",
            line_graph,
            line_nodes,
            line_edges,
            line_heuristic,
            (_task("faulted", 3, 0.0, 20.0, 2),),
            (_task_record(_task("faulted", 3, 0.0, 20.0, 2)),),
            max_tasks=1,
            fault_edges=((1, 2),),
        ),
        RollingParityCase(
            "line_repair_window_recovered",
            line_graph,
            line_nodes,
            line_edges,
            line_heuristic,
            (_task("repair-after", 4, 12.0, 40.0, 2),),
            (_task_record(_task("repair-after", 4, 12.0, 40.0, 2)),),
            max_tasks=1,
            fault_windows=((1, 2, 0.0, 10.0),),
        ),
        RollingParityCase(
            "line_repair_window_active_unplanned",
            line_graph,
            line_nodes,
            line_edges,
            line_heuristic,
            (_task("repair-active", 5, 5.0, 40.0, 2),),
            (_task_record(_task("repair-active", 5, 5.0, 40.0, 2)),),
            max_tasks=1,
            fault_windows=((1, 2, 0.0, 10.0),),
        ),
        RollingParityCase(
            "single_edge_capacity",
            single_graph,
            single_nodes,
            single_edges,
            single_heuristic,
            edge_tasks,
            tuple(_task_record(task) for task in edge_tasks),
            max_tasks=2,
            horizon_seconds=60.0,
            edge_capacity=1,
        ),
        RollingParityCase(
            "single_edge_headway",
            single_graph,
            single_nodes,
            single_edges,
            single_heuristic,
            edge_tasks,
            tuple(_task_record(task) for task in edge_tasks),
            max_tasks=2,
            horizon_seconds=60.0,
            edge_capacity=2,
            edge_headway_seconds=2.0,
        ),
    ]
    for manifest_case in load_manifest_cases():
        tasks = tasks_from_case(manifest_case)
        cases.append(
            RollingParityCase(
                f"{manifest_case.spec.name}_rolling",
                graph_from_case(manifest_case),
                manifest_case.node_records,
                manifest_case.edge_records,
                manifest_case.heuristic_time,
                tasks,
                manifest_case.task_records,
                max_tasks=manifest_case.spec.task_count,
                horizon_seconds=6.0,
                fault_edges=manifest_case.spec.fault_edges,
                fault_windows=manifest_case.spec.fault_windows,
            )
        )
    return tuple(cases)


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    strict_pass = all(bool(row["parity_pass"]) for row in rows)
    safety_pass = all(int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0 for row in rows)
    lines = [
        "# Phase2 C++ Rolling-Horizon SIPP Parity Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic compares the Python rolling-horizon SIPP baseline against the C++ "
            "rolling-horizon SIPP replay through pybind. It checks aggregate summaries and "
            "planned/unplanned event rows across priority, static fault, repair-window fault, "
            "edge-capacity, edge-headway, and persisted synthetic-map schedules."
        ),
        "",
        "## Metrics",
        "",
        (
            "| Case | Tasks | Horizon | Py planned | C++ planned | Py unplanned | "
            "C++ unplanned | Mean diff | Events | Parity | First mismatch |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {max_tasks} | {horizon_seconds:.1f} | {python_planned} | {cpp_planned} | "
            "{python_unplanned} | {cpp_unplanned} | {mean_travel_abs_diff:.12f} | "
            "{python_event_count}/{cpp_event_count} | {parity_pass} | "
            "{first_mismatch_status}:{first_mismatch_field}@{first_mismatch_index} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            (
                "- C++ rolling-horizon Python/C++ parity: PASS"
                if strict_pass
                else "- C++ rolling-horizon Python/C++ parity: FAIL"
            ),
            (
                "- rolling-horizon post-shield safety: PASS"
                if safety_pass
                else "- rolling-horizon post-shield safety: FAIL"
            ),
            "- persisted synthetic manifest schedules: covered",
            "- repair-window rolling-horizon planning-time semantics: covered",
            "- full active-bag PIBT replay and full merge-group/buffer-capacity replay integration: not covered",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    rows = [_case_row(case) for case in _cases()]
    write_table(rows)
    write_report(rows)
    if not all(bool(row["parity_pass"]) for row in rows):
        raise AssertionError("C++ rolling-horizon parity failed")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("C++ rolling-horizon parity produced post-shield conflicts")
    print(f"phase2_cpp_rolling_horizon_parity rows={len(rows)} strict_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
