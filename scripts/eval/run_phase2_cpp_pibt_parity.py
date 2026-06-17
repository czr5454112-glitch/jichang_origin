from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase2_cpp_pibt_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase2_cpp_pibt_parity_report.md"
FLOAT_TOLERANCE = 1.0e-9

NodeRecord = tuple[int, int, float, int, int, list[int]]
EdgeRecord = tuple[int, int, float, float]
AgentRecord = tuple[int, int, int, float, float, float]
NodeReservationRecord = tuple[int, int, float, float]
ActionRow = dict[str, float | int | str]

ACTION_FIELDS = (
    "task_id",
    "action",
    "current",
    "next_node",
    "edge_start",
    "edge_end",
    "node_start",
    "node_end",
    "reason",
    "priority_rank",
)

FLOAT_FIELDS = {"edge_start", "edge_end", "node_start", "node_end"}


@dataclass(frozen=True)
class PIBTParityCase:
    name: str
    graph: Any
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    agent_records: tuple[AgentRecord, ...]
    node_reservations: tuple[NodeReservationRecord, ...] = ()
    fault_edges: tuple[tuple[int, int], ...] = ()
    hold_seconds: float = 1.0


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _graph_from_records(
    node_records: tuple[NodeRecord, ...],
    edge_records: tuple[EdgeRecord, ...],
    heuristic_time: tuple[tuple[float, ...], ...],
) -> Any:
    from czr005.sim_py import IcsGraph, SimEdge, SimNode  # pylint: disable=import-outside-toplevel

    return IcsGraph(
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


def _merge_graph_inputs() -> tuple[
    Any,
    tuple[NodeRecord, ...],
    tuple[EdgeRecord, ...],
    tuple[tuple[float, ...], ...],
]:
    node_records = (
        (0, 1, 0.0, 0, 0, [2]),
        (1, 1, 0.0, 0, 1, [2]),
        (2, 4, 1.0, 1, 0, [3]),
        (3, 2, 0.0, 2, 0, []),
    )
    edge_records = (
        (0, 2, 5.0, 2.5),
        (1, 2, 5.0, 2.5),
        (2, 3, 5.0, 2.5),
    )
    heuristic_time = (
        (0.0, 4.0, 2.0, 4.0),
        (4.0, 0.0, 2.0, 4.0),
        (4.0, 4.0, 0.0, 2.0),
        (4.0, 4.0, 2.0, 0.0),
    )
    return _graph_from_records(node_records, edge_records, heuristic_time), node_records, edge_records, heuristic_time


def _branch_graph_inputs() -> tuple[
    Any,
    tuple[NodeRecord, ...],
    tuple[EdgeRecord, ...],
    tuple[tuple[float, ...], ...],
]:
    node_records = (
        (0, 1, 0.0, 0, 0, [1, 2]),
        (1, 4, 0.0, 1, 0, [3]),
        (2, 4, 0.0, 1, 1, [3]),
        (3, 2, 0.0, 2, 0, []),
    )
    edge_records = (
        (0, 1, 5.0, 2.5),
        (0, 2, 5.0, 2.5),
        (1, 3, 5.0, 2.5),
        (2, 3, 7.5, 2.5),
    )
    heuristic_time = (
        (0.0, 2.0, 3.0, 4.0),
        (4.0, 0.0, 4.0, 2.0),
        (4.0, 4.0, 0.0, 3.0),
        (4.0, 2.0, 3.0, 0.0),
    )
    return _graph_from_records(node_records, edge_records, heuristic_time), node_records, edge_records, heuristic_time


def _python_actions(case: PIBTParityCase) -> list[ActionRow]:
    from czr005.baselines import AgentState, PIBTStyleOneStepResolver  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import ReservationTable  # pylint: disable=import-outside-toplevel

    reservations = ReservationTable()
    for task_id, node, start, end in case.node_reservations:
        reservations.reserve(task_id, node, start, end)
    agents = [
        AgentState(
            task_id=task_id,
            current=current,
            goal=goal,
            ready_time=ready_time,
            deadline=deadline,
            waiting_time=waiting_time,
        )
        for task_id, current, goal, ready_time, deadline, waiting_time in case.agent_records
    ]
    return [
        {
            "task_id": int(action.task_id),
            "action": str(action.action),
            "current": int(action.current),
            "next_node": int(action.next_node),
            "edge_start": float(action.edge_start),
            "edge_end": float(action.edge_end),
            "node_start": float(action.node_start),
            "node_end": float(action.node_end),
            "reason": str(action.reason),
            "priority_rank": int(action.priority_rank),
        }
        for action in PIBTStyleOneStepResolver(case.graph, hold_seconds=case.hold_seconds).resolve(
            agents,
            reservations=reservations,
            fault_edges=set(case.fault_edges),
        )
    ]


def _cpp_actions(case: PIBTParityCase) -> list[ActionRow]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    return [
        {
            "task_id": int(row["task_id"]),
            "action": str(row["action"]),
            "current": int(row["current"]),
            "next_node": int(row["next_node"]),
            "edge_start": float(row["edge_start"]),
            "edge_end": float(row["edge_end"]),
            "node_start": float(row["node_start"]),
            "node_end": float(row["node_end"]),
            "reason": str(row["reason"]),
            "priority_rank": int(row["priority_rank"]),
        }
        for row in czr005_cpp.pibt_resolve_from_records(
            list(case.node_records),
            list(case.edge_records),
            [list(row) for row in case.heuristic_time],
            list(case.agent_records),
            node_reservations=list(case.node_reservations),
            fault_edges=list(case.fault_edges),
            hold_seconds=case.hold_seconds,
        )
    ]


def _values_match(field: str, python_value: float | int | str, cpp_value: float | int | str) -> bool:
    if field in FLOAT_FIELDS:
        return abs(float(python_value) - float(cpp_value)) <= FLOAT_TOLERANCE
    return python_value == cpp_value


def _first_mismatch(python_actions: list[ActionRow], cpp_actions: list[ActionRow]) -> dict[str, Any]:
    shared = min(len(python_actions), len(cpp_actions))
    for index in range(shared):
        for field in ACTION_FIELDS:
            if not _values_match(field, python_actions[index][field], cpp_actions[index][field]):
                return {
                    "status": "action_mismatch",
                    "index": index,
                    "field": field,
                    "python_value": python_actions[index][field],
                    "cpp_value": cpp_actions[index][field],
                }
    if len(python_actions) != len(cpp_actions):
        return {
            "status": "length_mismatch",
            "index": shared,
            "field": "action_count",
            "python_value": len(python_actions),
            "cpp_value": len(cpp_actions),
        }
    return {"status": "match", "index": "", "field": "none", "python_value": "", "cpp_value": ""}


def _action_summary(actions: list[ActionRow]) -> str:
    if not actions:
        return "none"
    return ";".join(
        f"{action['task_id']}:{action['action']}:{action['current']}->{action['next_node']}"
        for action in actions
    )


def _case_row(case: PIBTParityCase) -> dict[str, float | int | str | bool]:
    python = _python_actions(case)
    cpp = _cpp_actions(case)
    mismatch = _first_mismatch(python, cpp)
    return {
        "case": case.name,
        "agent_count": len(case.agent_records),
        "node_reservation_count": len(case.node_reservations),
        "fault_edge_count": len(case.fault_edges),
        "hold_seconds": case.hold_seconds,
        "python_actions": _action_summary(python),
        "cpp_actions": _action_summary(cpp),
        "python_hold_count": sum(1 for action in python if action["action"] == "hold"),
        "cpp_hold_count": sum(1 for action in cpp if action["action"] == "hold"),
        "parity_pass": mismatch["status"] == "match",
        "first_mismatch_status": mismatch["status"],
        "first_mismatch_index": mismatch["index"],
        "first_mismatch_field": mismatch["field"],
        "python_value": mismatch["python_value"],
        "cpp_value": mismatch["cpp_value"],
    }


def _synthetic_manifest_case() -> PIBTParityCase:
    from phase8_synthetic_replay_cases import (  # pylint: disable=import-outside-toplevel
        graph_from_case,
        load_manifest_cases,
    )

    manifest_case = load_manifest_cases()[0]
    agent_records = tuple(
        (
            int(task_id),
            int(start),
            int(goal),
            float(pass_time),
            float(std),
            0.0,
        )
        for (
            _segment_id,
            task_id,
            _pallet_id,
            pass_time,
            std,
            start,
            goal,
            _original_start,
            _original_goal,
            _original_entry_time,
            _leg,
            _early_bag_split,
            _source_line,
        ) in manifest_case.task_records[:4]
    )
    return PIBTParityCase(
        f"{manifest_case.spec.name}_first_four_slice",
        graph_from_case(manifest_case),
        manifest_case.node_records,
        manifest_case.edge_records,
        manifest_case.heuristic_time,
        agent_records,
        fault_edges=manifest_case.spec.fault_edges,
    )


def _cases() -> tuple[PIBTParityCase, ...]:
    merge_graph, merge_nodes, merge_edges, merge_heuristic = _merge_graph_inputs()
    branch_graph, branch_nodes, branch_edges, branch_heuristic = _branch_graph_inputs()
    return (
        PIBTParityCase(
            "merge_priority_conflict",
            merge_graph,
            merge_nodes,
            merge_edges,
            merge_heuristic,
            (
                (1, 0, 3, 0.0, 100.0, 0.0),
                (2, 1, 3, 0.0, 20.0, 0.0),
            ),
        ),
        PIBTParityCase(
            "merge_waiting_priority",
            merge_graph,
            merge_nodes,
            merge_edges,
            merge_heuristic,
            (
                (1, 0, 3, 0.0, 20.0, 5.0),
                (2, 1, 3, 0.0, 20.0, 0.0),
            ),
        ),
        PIBTParityCase(
            "merge_custom_hold_seconds",
            merge_graph,
            merge_nodes,
            merge_edges,
            merge_heuristic,
            (
                (1, 0, 3, 0.0, 100.0, 0.0),
                (2, 1, 3, 0.0, 20.0, 0.0),
            ),
            hold_seconds=2.5,
        ),
        PIBTParityCase(
            "branch_fault_alternative",
            branch_graph,
            branch_nodes,
            branch_edges,
            branch_heuristic,
            ((3, 0, 3, 0.0, 20.0, 0.0),),
            fault_edges=((0, 1),),
        ),
        PIBTParityCase(
            "branch_reservation_alternative",
            branch_graph,
            branch_nodes,
            branch_edges,
            branch_heuristic,
            ((4, 0, 3, 0.0, 20.0, 0.0),),
            node_reservations=((99, 1, 2.0, 2.0),),
        ),
        _synthetic_manifest_case(),
    )


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
        "# Phase2 C++ PIBT-Style One-Step Parity Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        (
            "This diagnostic compares the Python PIBTStyleOneStepResolver against the C++ "
            "one-step resolver exposed through pybind. It covers deterministic priority "
            "ordering, same-slice merge conflicts, fault-edge fallback, existing node "
            "reservations, custom hold duration, and one persisted synthetic manifest slice."
        ),
        "",
        "This is one-step PIBT-style shield parity, not recursive PIBT/backtracking replay.",
        "",
        "## Metrics",
        "",
        (
            "| Case | Agents | Fault edges | Node reservations | Holds Py/C++ | "
            "Python actions | C++ actions | Parity | First mismatch |"
        ),
        "|---|---:|---:|---:|---:|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {agent_count} | {fault_edge_count} | {node_reservation_count} | "
            "{python_hold_count}/{cpp_hold_count} | {python_actions} | {cpp_actions} | "
            "{parity_pass} | {first_mismatch_status}:{first_mismatch_field}@{first_mismatch_index} |".format(
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
            (
                "- C++ PIBT-style one-step Python/C++ parity: PASS"
                if strict_pass
                else "- C++ PIBT-style one-step Python/C++ parity: FAIL"
            ),
            "- merge/fault/reservation one-step shield cases: covered",
            "- persisted synthetic manifest one-step slice: covered",
            "- recursive priority inheritance/backtracking: not covered",
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
        raise AssertionError("C++ PIBT-style one-step parity failed")
    print(f"phase2_cpp_pibt_parity rows={len(rows)} strict_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
