from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = ROOT / "outputs" / "tables" / "phase2_pibt_active_bag_replay_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase2_pibt_active_bag_replay_parity_report.md"
FLOAT_TOLERANCE = 1.0e-9

NodeRecord = tuple[int, int, float, int, int, list[int]]
EdgeRecord = tuple[int, int, float, float]
TaskRecord = tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]
FaultWindow = tuple[int, int, float, float]
NodeCapacity = tuple[int, int]

SUMMARY_FIELDS = (
    "planned_count",
    "unplanned_count",
    "decision_count",
    "tick_count",
    "peak_active_bags",
    "move_count",
    "hold_count",
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
    "current",
    "next_node",
    "start",
    "goal",
    "entry_time",
    "finish_time",
    "tick_time",
    "ready_time",
    "priority_rank",
    "decision_count",
    "reached_goal",
    "reason",
    "path",
)

FLOAT_FIELDS = {"entry_time", "finish_time", "tick_time", "ready_time", "mean_travel_time", "makespan"}


@dataclass(frozen=True)
class PIBTActiveBagParityCase:
    name: str
    graph: Any
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    tasks: tuple[Any, ...]
    task_records: tuple[TaskRecord, ...]
    max_tasks: int
    interval_seconds: float = 5.0
    max_ticks: int = 2048
    hold_seconds: float = 5.0
    edge_capacity: int = 1
    edge_headway_seconds: float = 0.0
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[FaultWindow, ...] = ()
    node_capacities: tuple[NodeCapacity, ...] = ()


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    build_candidates = (
        ROOT / "build_vs" / "python" / "Debug",
        ROOT / "build_vs" / "python" / "Release",
        ROOT / "build_nmake" / "python",
    )
    for candidate in reversed(build_candidates):
        if candidate.exists():
            sys.path.insert(0, str(candidate))
    if extra := os.environ.get("CZR005_CPP_PYTHON_PATH"):
        sys.path.insert(0, extra)


def _task(
    segment_id: str,
    task_id: int,
    pass_time: float,
    std: float,
    start: int,
    goal: int,
) -> Any:
    from czr005.sim_py.task_stream import TaskLeg  # pylint: disable=import-outside-toplevel

    return TaskLeg(
        segment_id=segment_id,
        task_id=task_id,
        pallet_id=task_id,
        pass_time=pass_time,
        std=std,
        start=start,
        goal=goal,
        original_start=start,
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


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": str(event.get("event", "")),
        "segment_id": str(event.get("segment_id", "")),
        "task_id": int(event.get("task_id", -1)),
        "current": int(event.get("current", -1)),
        "next_node": int(event.get("next_node", -1)),
        "start": int(event.get("start", -1)),
        "goal": int(event.get("goal", -1)),
        "entry_time": float(event.get("entry_time", 0.0)),
        "finish_time": float(event.get("finish_time", 0.0)),
        "tick_time": float(event.get("tick_time", 0.0)),
        "ready_time": float(event.get("ready_time", 0.0)),
        "priority_rank": int(event.get("priority_rank", -1)),
        "decision_count": int(event.get("decision_count", 0)),
        "reached_goal": bool(event.get("reached_goal", False)),
        "reason": str(event.get("reason", "")),
        "path": [int(value) for value in event.get("path", [])],
    }


def _python_payload(case: PIBTActiveBagParityCase) -> dict[str, Any]:
    from czr005.baselines import PIBTActiveBagReplayBaseline  # pylint: disable=import-outside-toplevel

    baseline = PIBTActiveBagReplayBaseline(
        case.graph,
        interval_seconds=case.interval_seconds,
        max_ticks=case.max_ticks,
        hold_seconds=case.hold_seconds,
        edge_capacity=case.edge_capacity,
        edge_headway_seconds=case.edge_headway_seconds,
        node_capacities=dict(case.node_capacities),
    )
    result = baseline.run_episode(
        case.tasks,
        max_tasks=case.max_tasks,
        fault_edges=set(case.fault_edges),
        fault_windows=case.fault_windows,
    )
    return {
        "summary": {
            **result.metrics.to_dict(),
            "decision_count": baseline.summary.decision_count,
            "tick_count": baseline.summary.tick_count,
            "peak_active_bags": baseline.summary.peak_active_bags,
            "move_count": baseline.summary.move_count,
            "hold_count": baseline.summary.hold_count,
            "edge_reservation_conflicts": baseline.summary.edge_reservation_conflicts,
            "post_shield_conflicts": baseline.summary.post_shield_conflicts,
        },
        "events": [_normalize_event(event) for event in result.events],
    }


def _cpp_payload(case: PIBTActiveBagParityCase) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    payload = czr005_cpp.pibt_active_bag_replay_from_records(
        list(case.node_records),
        list(case.edge_records),
        [list(row) for row in case.heuristic_time],
        list(case.task_records),
        max_tasks=case.max_tasks,
        interval_seconds=case.interval_seconds,
        max_ticks=case.max_ticks,
        hold_seconds=case.hold_seconds,
        edge_capacity=case.edge_capacity,
        edge_headway_seconds=case.edge_headway_seconds,
        fault_edges=list(case.fault_edges),
        fault_windows=list(case.fault_windows),
        node_capacities=list(case.node_capacities),
    )
    return {
        "summary": dict(payload["summary"]),
        "events": [_normalize_event(dict(event)) for event in payload["events"]],
    }


def _values_match(field: str, python_value: Any, cpp_value: Any) -> bool:
    if field == "path":
        return list(python_value) == list(cpp_value)
    if field in FLOAT_FIELDS:
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


def _case_row(case: PIBTActiveBagParityCase) -> dict[str, float | int | str | bool]:
    python = _python_payload(case)
    cpp = _cpp_payload(case)
    mismatch = _first_mismatch(python, cpp)
    return {
        "case": case.name,
        "max_tasks": case.max_tasks,
        "interval_seconds": case.interval_seconds,
        "python_planned": int(python["summary"]["planned_count"]),
        "cpp_planned": int(cpp["summary"]["planned_count"]),
        "python_unplanned": int(python["summary"]["unplanned_count"]),
        "cpp_unplanned": int(cpp["summary"]["unplanned_count"]),
        "python_decisions": int(python["summary"]["decision_count"]),
        "cpp_decisions": int(cpp["summary"]["decision_count"]),
        "python_ticks": int(python["summary"]["tick_count"]),
        "cpp_ticks": int(cpp["summary"]["tick_count"]),
        "python_peak_active_bags": int(python["summary"]["peak_active_bags"]),
        "cpp_peak_active_bags": int(cpp["summary"]["peak_active_bags"]),
        "python_holds": int(python["summary"]["hold_count"]),
        "cpp_holds": int(cpp["summary"]["hold_count"]),
        "python_conflicts": int(python["summary"]["post_shield_conflicts"]),
        "cpp_conflicts": int(cpp["summary"]["post_shield_conflicts"]),
        "python_event_count": len(python["events"]),
        "cpp_event_count": len(cpp["events"]),
        "mean_travel_abs_diff": abs(
            float(python["summary"]["mean_travel_time"]) - float(cpp["summary"]["mean_travel_time"])
        ),
        "parity_pass": mismatch["status"] == "match",
        "first_mismatch_status": mismatch["status"],
        "first_mismatch_index": mismatch["index"],
        "first_mismatch_field": mismatch["field"],
        "python_value": mismatch["python_value"],
        "cpp_value": mismatch["cpp_value"],
    }


def _cases() -> tuple[PIBTActiveBagParityCase, ...]:
    from phase8_synthetic_replay_cases import (  # pylint: disable=import-outside-toplevel
        graph_from_case,
        load_manifest_cases,
        tasks_from_case,
    )
    from run_phase2_cpp_pibt_parity import _branch_graph_inputs, _handoff_graph_inputs  # pylint: disable=import-outside-toplevel
    from run_phase2_periodic_replanning_parity import _line_graph_inputs  # pylint: disable=import-outside-toplevel

    line_graph, line_nodes, line_edges, line_heuristic = _line_graph_inputs()
    branch_graph, branch_nodes, branch_edges, branch_heuristic = _branch_graph_inputs()
    handoff_graph, handoff_nodes, handoff_edges, handoff_heuristic = _handoff_graph_inputs()

    line_tasks = (
        _task("line-urgent", 1, 0.0, 20.0, 0, 2),
        _task("line-loose", 2, 0.1, 100.0, 0, 2),
    )
    branch_fault_tasks = (_task("branch-fault", 3, 0.0, 20.0, 0, 3),)
    branch_repaired_tasks = (_task("branch-repaired", 4, 6.0, 26.0, 0, 3),)
    handoff_tasks = (
        _task("handoff-high", 5, 0.0, 20.0, 0, 3),
        _task("handoff-blocker", 6, 0.0, 100.0, 1, 3),
    )

    cases: list[PIBTActiveBagParityCase] = [
        PIBTActiveBagParityCase(
            "line_two_active_bags",
            line_graph,
            line_nodes,
            line_edges,
            line_heuristic,
            line_tasks,
            tuple(_task_record(task) for task in line_tasks),
            max_tasks=2,
            interval_seconds=2.0,
            hold_seconds=2.0,
            max_ticks=32,
        ),
        PIBTActiveBagParityCase(
            "branch_static_fault_alternative",
            branch_graph,
            branch_nodes,
            branch_edges,
            branch_heuristic,
            branch_fault_tasks,
            tuple(_task_record(task) for task in branch_fault_tasks),
            max_tasks=1,
            interval_seconds=2.0,
            hold_seconds=2.0,
            max_ticks=32,
            fault_edges=((0, 1),),
        ),
        PIBTActiveBagParityCase(
            "branch_repaired_preferred_edge",
            branch_graph,
            branch_nodes,
            branch_edges,
            branch_heuristic,
            branch_repaired_tasks,
            tuple(_task_record(task) for task in branch_repaired_tasks),
            max_tasks=1,
            interval_seconds=2.0,
            hold_seconds=2.0,
            max_ticks=32,
            fault_windows=((0, 1, 0.0, 5.0),),
        ),
        PIBTActiveBagParityCase(
            "handoff_active_bag_slice",
            handoff_graph,
            handoff_nodes,
            handoff_edges,
            handoff_heuristic,
            handoff_tasks,
            tuple(_task_record(task) for task in handoff_tasks),
            max_tasks=2,
            interval_seconds=2.0,
            hold_seconds=2.0,
            max_ticks=32,
        ),
    ]
    for manifest_case in load_manifest_cases()[:2]:
        tasks = tasks_from_case(manifest_case)
        max_tasks = min(6, manifest_case.spec.task_count)
        cases.append(
            PIBTActiveBagParityCase(
                f"{manifest_case.spec.name}_pibt_active",
                graph_from_case(manifest_case),
                manifest_case.node_records,
                manifest_case.edge_records,
                manifest_case.heuristic_time,
                tasks[:max_tasks],
                manifest_case.task_records[:max_tasks],
                max_tasks=max_tasks,
                interval_seconds=5.0,
                hold_seconds=5.0,
                max_ticks=256,
                fault_edges=manifest_case.spec.fault_edges,
                fault_windows=manifest_case.spec.fault_windows,
                node_capacities=manifest_case.spec.node_capacities,
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
        "# Phase2 PIBT Active-Bag Replay Parity Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic compares the Python and C++ active-bag PIBT-style replay baseline. "
            "Each tick admits arrived bags, resolves all ready active bags with the bounded "
            "recursive PIBT one-step resolver, commits moves/holds, and continues until each "
            "bag is planned or the tick limit is reached."
        ),
        "",
        (
            "It covers two active bags, static-fault alternate routing, repair-window behavior, "
            "recursive handoff inside an active-bag slice, and two persisted synthetic manifest slices."
        ),
        "",
        "## Metrics",
        "",
        (
            "| Case | Tasks | Interval | Py/C++ planned | Py/C++ decisions | Py/C++ ticks | "
            "Peak active Py/C++ | Holds Py/C++ | Events Py/C++ | Parity | First mismatch |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {max_tasks} | {interval_seconds:.1f} | "
            "{python_planned}/{cpp_planned} | {python_decisions}/{cpp_decisions} | "
            "{python_ticks}/{cpp_ticks} | {python_peak_active_bags}/{cpp_peak_active_bags} | "
            "{python_holds}/{cpp_holds} | {python_event_count}/{cpp_event_count} | "
            "{parity_pass} | {first_mismatch_status}:{first_mismatch_field}@{first_mismatch_index} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            (
                "- PIBT active-bag replay Python/C++ parity: PASS"
                if strict_pass
                else "- PIBT active-bag replay Python/C++ parity: FAIL"
            ),
            "- post-shield safety: PASS" if safety_pass else "- post-shield safety: FAIL",
            "- recursive handoff inside active-bag replay: covered",
            "- persisted synthetic manifest slices: covered",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    rows = [_case_row(case) for case in _cases()]
    write_table(rows)
    write_report(rows)
    if not all(bool(row["parity_pass"]) for row in rows):
        raise AssertionError("PIBT active-bag replay parity failed")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("PIBT active-bag replay produced post-shield conflicts")
    print(f"phase2_pibt_active_bag_replay_parity rows={len(rows)} strict_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
