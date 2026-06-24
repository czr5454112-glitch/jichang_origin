from __future__ import annotations

import csv
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase2_cpp_sipp_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase2_cpp_sipp_parity_report.md"
FLOAT_TOLERANCE = 1.0e-9

RouteRow = dict[str, float | int]
NodeReservationRecord = tuple[int, int, float, float]
EdgeReservationRecord = tuple[int, int, int, float, float]
MergeGroupRecord = tuple[int, int, int]


@dataclass(frozen=True)
class SippParityCase:
    name: str
    graph: Any
    node_records: tuple[Any, ...]
    edge_records: tuple[Any, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    start: int
    goal: int
    start_time: float = 0.0
    node_reservations: tuple[NodeReservationRecord, ...] = ()
    edge_reservations: tuple[EdgeReservationRecord, ...] = ()
    edge_capacity: int = 1
    edge_headway_seconds: float = 0.0
    merge_groups: tuple[MergeGroupRecord, ...] = ()
    merge_capacity: int = 1
    merge_headway_seconds: float = 0.0
    fault_edges: tuple[tuple[int, int], ...] = ()
    task_id: int = 1


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    build_candidates = (
        Path(os.environ["CZR005_CPP_PYTHON_PATH"])
        if os.environ.get("CZR005_CPP_PYTHON_PATH")
        else None,
        ROOT / "build_vs" / "python" / "Debug",
        ROOT / "build_vs" / "python" / "Release",
        BUILD_PYTHON_PATH,
    )
    for candidate in reversed([path for path in build_candidates if path is not None]):
        if candidate.exists() or str(candidate) == os.environ.get("CZR005_CPP_PYTHON_PATH"):
            sys.path.insert(0, str(candidate))


def _line_graph_case_inputs() -> tuple[Any, tuple[Any, ...], tuple[Any, ...], tuple[tuple[float, ...], ...]]:
    from czr005.sim_py import IcsGraph, SimEdge, SimNode  # pylint: disable=import-outside-toplevel

    node_records = (
        (0, 1, 0.0, 0, 0, [1]),
        (1, 4, 1.0, 1, 0, [2]),
        (2, 2, 0.0, 2, 0, []),
    )
    edge_records = (
        (0, 1, 5.0, 2.5),
        (1, 2, 5.0, 2.5),
    )
    heuristic_time = (
        (0.0, 2.0, 4.0),
        (4.0, 0.0, 2.0),
        (4.0, 2.0, 0.0),
    )
    graph = IcsGraph(
        nodes={
            location: SimNode(
                location=location,
                node_type=node_type,
                service_time=service_time,
                x=x,
                y=y,
                outgoing=tuple(outgoing),
            )
            for location, node_type, service_time, x, y, outgoing in node_records
        },
        edges={
            (start, end): SimEdge(start=start, end=end, length=length, speed=speed)
            for start, end, length, speed in edge_records
        },
        heuristic_time=heuristic_time,
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )
    return graph, node_records, edge_records, heuristic_time


def _parallel_merge_group_case_inputs() -> tuple[Any, tuple[Any, ...], tuple[Any, ...], tuple[tuple[float, ...], ...]]:
    from czr005.sim_py import IcsGraph, SimEdge, SimNode  # pylint: disable=import-outside-toplevel

    node_records = (
        (0, 1, 0.0, 0, 0, [2]),
        (1, 1, 0.0, 0, 1, [3]),
        (2, 4, 0.0, 1, 0, [4]),
        (3, 4, 0.0, 1, 1, [5]),
        (4, 2, 0.0, 2, 0, []),
        (5, 2, 0.0, 2, 1, []),
    )
    edge_records = (
        (0, 2, 5.0, 2.5),
        (1, 3, 5.0, 2.5),
        (2, 4, 5.0, 2.5),
        (3, 5, 5.0, 2.5),
    )
    heuristic_time = (
        (0.0, 999.0, 2.0, 999.0, 4.0, 999.0),
        (999.0, 0.0, 999.0, 2.0, 999.0, 4.0),
        (999.0, 999.0, 0.0, 999.0, 2.0, 999.0),
        (999.0, 999.0, 999.0, 0.0, 999.0, 2.0),
        (999.0, 999.0, 999.0, 999.0, 0.0, 999.0),
        (999.0, 999.0, 999.0, 999.0, 999.0, 0.0),
    )
    graph = IcsGraph(
        nodes={
            location: SimNode(
                location=location,
                node_type=node_type,
                service_time=service_time,
                x=x,
                y=y,
                outgoing=tuple(outgoing),
            )
            for location, node_type, service_time, x, y, outgoing in node_records
        },
        edges={
            (start, end): SimEdge(start=start, end=end, length=length, speed=speed)
            for start, end, length, speed in edge_records
        },
        heuristic_time=heuristic_time,
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )
    return graph, node_records, edge_records, heuristic_time


def _route_rows(route: list[Any]) -> list[RouteRow]:
    return [
        {
            "location": int(node.location),
            "t1": float(node.t1),
            "t2": float(node.t2),
            "gcost": float(node.gcost),
            "hcost": float(node.hcost),
            "fcost": float(node.fcost),
        }
        for node in route
    ]


def _python_sipp_route(case: SippParityCase) -> list[RouteRow]:
    from czr005.baselines import SIPPPlanner  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import (  # pylint: disable=import-outside-toplevel
        EdgeReservationTable,
        ReservationTable,
    )

    node_table = ReservationTable()
    for task_id, node, start, end in case.node_reservations:
        node_table.reserve(task_id, node, start, end)
    edge_table = EdgeReservationTable()
    for task_id, start_node, end_node, start, end in case.edge_reservations:
        edge_table.reserve(task_id, start_node, end_node, start, end)
    route = SIPPPlanner(case.graph).plan(
        start=case.start,
        goal=case.goal,
        start_time=case.start_time,
        reservations=node_table,
        edge_reservations=edge_table,
        edge_capacity=case.edge_capacity,
        edge_headway_seconds=case.edge_headway_seconds,
        merge_groups={(start, end): group for start, end, group in case.merge_groups},
        merge_capacity=case.merge_capacity,
        merge_headway_seconds=case.merge_headway_seconds,
        fault_edges=set(case.fault_edges),
        task_id=case.task_id,
    )
    return _route_rows(route)


def _cpp_sipp_route(case: SippParityCase) -> list[RouteRow]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    return [
        {
            "location": int(row["location"]),
            "t1": float(row["t1"]),
            "t2": float(row["t2"]),
            "gcost": float(row["gcost"]),
            "hcost": float(row["hcost"]),
            "fcost": float(row["fcost"]),
        }
        for row in czr005_cpp.sipp_plan_from_records(
            list(case.node_records),
            list(case.edge_records),
            [list(row) for row in case.heuristic_time],
            start=case.start,
            goal=case.goal,
            start_time=case.start_time,
            node_reservations=list(case.node_reservations),
            edge_reservations=list(case.edge_reservations),
            edge_capacity=case.edge_capacity,
            edge_headway_seconds=case.edge_headway_seconds,
            merge_groups=list(case.merge_groups),
            merge_capacity=case.merge_capacity,
            merge_headway_seconds=case.merge_headway_seconds,
            fault_edges=list(case.fault_edges),
            task_id=case.task_id,
        )
    ]


def _values_match(field: str, python_value: float | int, cpp_value: float | int) -> bool:
    if field == "location":
        return int(python_value) == int(cpp_value)
    return abs(float(python_value) - float(cpp_value)) <= FLOAT_TOLERANCE


def _first_mismatch(python_route: list[RouteRow], cpp_route: list[RouteRow]) -> dict[str, Any]:
    fields = ("location", "t1", "t2", "gcost", "hcost", "fcost")
    shared = min(len(python_route), len(cpp_route))
    for index in range(shared):
        for field in fields:
            if not _values_match(field, python_route[index][field], cpp_route[index][field]):
                return {
                    "status": "mismatch",
                    "node_index": index,
                    "field": field,
                    "python_value": python_route[index][field],
                    "cpp_value": cpp_route[index][field],
                }
    if len(python_route) != len(cpp_route):
        return {
            "status": "length_mismatch",
            "node_index": shared,
            "field": "route_length",
            "python_value": len(python_route),
            "cpp_value": len(cpp_route),
        }
    return {"status": "match", "node_index": "", "field": "none", "python_value": "", "cpp_value": ""}


def _case_row(case: SippParityCase) -> dict[str, float | int | str | bool]:
    python_route = _python_sipp_route(case)
    cpp_route = _cpp_sipp_route(case)
    mismatch = _first_mismatch(python_route, cpp_route)
    parity_pass = mismatch["status"] == "match"
    return {
        "case": case.name,
        "start": case.start,
        "goal": case.goal,
        "python_route": "->".join(str(row["location"]) for row in python_route) or "none",
        "cpp_route": "->".join(str(row["location"]) for row in cpp_route) or "none",
        "python_length": len(python_route),
        "cpp_length": len(cpp_route),
        "python_finish": float(python_route[-1]["t2"]) if python_route else 0.0,
        "cpp_finish": float(cpp_route[-1]["t2"]) if cpp_route else 0.0,
        "node_reservation_count": len(case.node_reservations),
        "edge_reservation_count": len(case.edge_reservations),
        "merge_group_count": len(case.merge_groups),
        "fault_edge_count": len(case.fault_edges),
        "edge_headway_seconds": case.edge_headway_seconds,
        "merge_headway_seconds": case.merge_headway_seconds,
        "parity_pass": parity_pass,
        "first_mismatch_status": mismatch["status"],
        "first_mismatch_node": mismatch["node_index"],
        "first_mismatch_field": mismatch["field"],
        "python_value": mismatch["python_value"],
        "cpp_value": mismatch["cpp_value"],
    }


def _cases() -> tuple[SippParityCase, ...]:
    from phase8_synthetic_replay_cases import (  # pylint: disable=import-outside-toplevel
        graph_from_case,
        load_manifest_cases,
    )

    line_graph, node_records, edge_records, heuristic_time = _line_graph_case_inputs()
    merge_graph, merge_nodes, merge_edges, merge_heuristic = _parallel_merge_group_case_inputs()
    cases: list[SippParityCase] = [
        SippParityCase("line_clear", line_graph, node_records, edge_records, heuristic_time, 0, 2),
        SippParityCase(
            "line_node_wait",
            line_graph,
            node_records,
            edge_records,
            heuristic_time,
            0,
            2,
            node_reservations=((99, 1, 2.0, 3.0),),
        ),
        SippParityCase(
            "line_edge_capacity_wait",
            line_graph,
            node_records,
            edge_records,
            heuristic_time,
            0,
            2,
            edge_reservations=((99, 0, 1, 0.0, 2.0),),
        ),
        SippParityCase(
            "line_edge_headway_wait",
            line_graph,
            node_records,
            edge_records,
            heuristic_time,
            0,
            2,
            edge_reservations=((99, 0, 1, 0.0, 0.5),),
            edge_headway_seconds=2.0,
        ),
        SippParityCase(
            "line_fault_blocked",
            line_graph,
            node_records,
            edge_records,
            heuristic_time,
            0,
            2,
            fault_edges=((1, 2),),
        ),
        SippParityCase(
            "parallel_merge_group_wait",
            merge_graph,
            merge_nodes,
            merge_edges,
            merge_heuristic,
            0,
            4,
            edge_reservations=((99, 1, 3, 0.0, 2.0),),
            merge_groups=((0, 2, 7), (1, 3, 7)),
        ),
    ]
    for manifest_case in load_manifest_cases():
        task = manifest_case.task_records[0]
        cases.append(
            SippParityCase(
                f"{manifest_case.spec.name}_first_task",
                graph_from_case(manifest_case),
                manifest_case.node_records,
                manifest_case.edge_records,
                manifest_case.heuristic_time,
                int(task[5]),
                int(task[6]),
                start_time=float(task[3]),
                fault_edges=manifest_case.spec.fault_edges,
                task_id=int(task[1]),
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
    lines = [
        "# Phase2 C++ SIPP Parity Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        (
            "This diagnostic compares the Python SIPP baseline against the new C++ SIPP planner "
            "through the pybind in-memory record API. It covers clear routing, node-reservation "
            "waiting, edge-capacity waiting, edge-headway waiting, fault-edge blocking, and "
            "merge-group waiting, plus first-task routes from the persisted synthetic manifest."
        ),
        "",
        "## Metrics",
        "",
        "| Case | Start | Goal | Python route | C++ route | Finish diff | Parity | First mismatch |",
        "|---|---:|---:|---|---|---:|---|---|",
    ]
    for row in rows:
        finish_diff = abs(float(row["python_finish"]) - float(row["cpp_finish"]))
        lines.append(
            "| {case} | {start} | {goal} | {python_route} | {cpp_route} | "
            f"{finish_diff:.12f} | "
            "{parity_pass} | {first_mismatch_status}:{first_mismatch_field}@{first_mismatch_node} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- C++ SIPP route/timing parity: PASS" if strict_pass else "- C++ SIPP route/timing parity: FAIL",
            "- node and edge reservation waiting cases: covered",
            "- merge-group waiting case: covered",
            "- persisted synthetic manifest first-task cases: covered",
            "- rolling-horizon C++ replay: not covered",
            "- full active-bag replay integration: not covered",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    rows = [_case_row(case) for case in _cases()]
    write_table(rows)
    write_report(rows)
    if not all(bool(row["parity_pass"]) for row in rows):
        raise AssertionError("C++ SIPP parity failed")
    print(f"phase2_cpp_sipp_parity rows={len(rows)} strict_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
