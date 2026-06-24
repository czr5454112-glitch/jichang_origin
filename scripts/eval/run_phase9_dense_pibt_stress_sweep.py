from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
from time import perf_counter
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = Path(os.environ.get("CZR005_CPP_PYTHON_PATH", ROOT / "build_nmake" / "python"))
TABLE_PATH = ROOT / "outputs" / "tables" / "phase9_dense_pibt_stress_sweep.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase9_dense_pibt_stress_sweep_report.md"

FLOAT_TOLERANCE = 1.0e-9

NodeRecord = tuple[int, int, float, int, int, list[int]]
EdgeRecord = tuple[int, int, float, float]
TaskRecord = tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]

ROW_FIELDS = [
    "scenario",
    "seed",
    "task_count",
    "spacing",
    "node_count",
    "edge_count",
    "fault_edges",
    "fault_windows",
    "node_capacities",
    "merge_groups",
    "merge_capacity",
    "merge_headway_seconds",
    "python_planned",
    "cpp_planned",
    "python_unplanned",
    "cpp_unplanned",
    "python_decisions",
    "cpp_decisions",
    "python_ticks",
    "cpp_ticks",
    "python_peak_active_bags",
    "cpp_peak_active_bags",
    "python_holds",
    "cpp_holds",
    "python_conflicts",
    "cpp_conflicts",
    "python_mean_travel_time",
    "cpp_mean_travel_time",
    "mean_travel_abs_diff",
    "python_makespan",
    "cpp_makespan",
    "makespan_abs_diff",
    "python_elapsed_seconds",
    "cpp_elapsed_seconds",
    "cpp_speedup",
    "parity_pass",
    "first_mismatch_field",
    "python_value",
    "cpp_value",
]

SUMMARY_FIELDS = (
    "planned_count",
    "unplanned_count",
    "decision_count",
    "tick_count",
    "peak_active_bags",
    "hold_count",
    "post_shield_conflicts",
    "mean_travel_time",
    "makespan",
)


@dataclass(frozen=True)
class RuntimeInputs:
    graph: Any
    tasks: tuple[Any, ...]
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    task_records: tuple[TaskRecord, ...]


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    build_candidates = (
        Path(os.environ["CZR005_CPP_PYTHON_PATH"])
        if os.environ.get("CZR005_CPP_PYTHON_PATH")
        else None,
        ROOT / "build_vs" / "python" / "Debug",
        ROOT / "build_vs" / "python" / "Release",
        ROOT / "build_nmake" / "python",
        BUILD_PYTHON_PATH,
    )
    for candidate in reversed([path for path in build_candidates if path is not None]):
        if candidate.exists() or str(candidate) == os.environ.get("CZR005_CPP_PYTHON_PATH"):
            sys.path.insert(0, str(candidate))


def _case_specs() -> tuple[Any, ...]:
    from phase8_synthetic_replay_cases import SyntheticCaseSpec  # pylint: disable=import-outside-toplevel

    merge_groups = ((4, 7, 7), (4, 8, 7), (5, 8, 8), (6, 8, 8))
    return (
        SyntheticCaseSpec("dense_pibt_seed101_low_spacing", 101, 30, 0.85, (), ()),
        SyntheticCaseSpec("dense_pibt_seed103_low_spacing", 103, 32, 0.75, (), ()),
        SyntheticCaseSpec("dense_pibt_seed107_static", 107, 32, 0.80, ((4, 7),), ()),
        SyntheticCaseSpec("dense_pibt_seed109_static", 109, 34, 0.70, ((5, 8),), ()),
        SyntheticCaseSpec("dense_pibt_seed113_repair", 113, 34, 0.70, (), ((4, 8, 2.0, 13.0),)),
        SyntheticCaseSpec(
            "dense_pibt_seed127_multi_repair",
            127,
            36,
            0.65,
            (),
            ((4, 8, 3.0, 10.0), (8, 9, 9.0, 20.0)),
        ),
        SyntheticCaseSpec(
            "dense_pibt_seed131_merge_buffer",
            131,
            36,
            0.60,
            (),
            ((4, 8, 2.0, 13.0),),
            ((8, 2), (9, 2)),
            merge_groups,
        ),
        SyntheticCaseSpec(
            "dense_pibt_seed137_merge_buffer",
            137,
            38,
            0.55,
            (),
            ((5, 8, 3.0, 16.0),),
            ((8, 2), (9, 2)),
            merge_groups,
        ),
        SyntheticCaseSpec(
            "dense_pibt_seed139_static_repair",
            139,
            34,
            0.75,
            ((4, 7),),
            ((5, 8, 0.0, 14.0),),
        ),
        SyntheticCaseSpec(
            "dense_pibt_seed149_repeated_repair",
            149,
            36,
            0.65,
            (),
            ((4, 8, 3.0, 8.0), (4, 8, 14.0, 21.0), (8, 9, 9.0, 15.0)),
        ),
        SyntheticCaseSpec("dense_pibt_seed151_overload", 151, 40, 0.50, (), ()),
        SyntheticCaseSpec(
            "dense_pibt_seed157_overload_merge",
            157,
            40,
            0.50,
            (),
            ((4, 8, 2.0, 13.0),),
            ((8, 2), (9, 2)),
            merge_groups,
        ),
    )


def _timed(call: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], float]:
    started = perf_counter()
    payload = call()
    return payload, perf_counter() - started


def _python_pibt(inputs: RuntimeInputs, case: Any) -> dict[str, Any]:
    from czr005.baselines import PIBTActiveBagReplayBaseline  # pylint: disable=import-outside-toplevel

    baseline = PIBTActiveBagReplayBaseline(
        inputs.graph,
        interval_seconds=2.0,
        max_ticks=4096,
        hold_seconds=2.0,
        node_capacities=dict(case.spec.node_capacities),
        merge_groups={(start, end): group for start, end, group in case.spec.merge_groups},
        merge_capacity=case.spec.merge_capacity,
        merge_headway_seconds=case.spec.merge_headway_seconds,
    )
    result = baseline.run_episode(
        inputs.tasks,
        max_tasks=case.spec.task_count,
        fault_edges=set(case.spec.fault_edges),
        fault_windows=case.spec.fault_windows,
    )
    return {
        **result.metrics.to_dict(),
        "decision_count": baseline.summary.decision_count,
        "tick_count": baseline.summary.tick_count,
        "peak_active_bags": baseline.summary.peak_active_bags,
        "move_count": baseline.summary.move_count,
        "hold_count": baseline.summary.hold_count,
        "edge_reservation_conflicts": baseline.summary.edge_reservation_conflicts,
        "post_shield_conflicts": baseline.summary.post_shield_conflicts,
    }


def _cpp_pibt(inputs: RuntimeInputs, case: Any) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    payload = czr005_cpp.pibt_active_bag_replay_from_records(
        list(inputs.node_records),
        list(inputs.edge_records),
        [list(row) for row in inputs.heuristic_time],
        list(inputs.task_records),
        max_tasks=case.spec.task_count,
        interval_seconds=2.0,
        max_ticks=4096,
        hold_seconds=2.0,
        edge_capacity=1,
        edge_headway_seconds=0.0,
        fault_edges=list(case.spec.fault_edges),
        fault_windows=list(case.spec.fault_windows),
        node_capacities=list(case.spec.node_capacities),
        merge_groups=list(case.spec.merge_groups),
        merge_capacity=case.spec.merge_capacity,
        merge_headway_seconds=case.spec.merge_headway_seconds,
    )
    return dict(payload["summary"])


def _values_match(field: str, python_value: Any, cpp_value: Any) -> bool:
    if field in {"mean_travel_time", "makespan"}:
        return abs(float(python_value) - float(cpp_value)) <= FLOAT_TOLERANCE
    return python_value == cpp_value


def _first_mismatch(python_summary: dict[str, Any], cpp_summary: dict[str, Any]) -> dict[str, Any]:
    for field in SUMMARY_FIELDS:
        if not _values_match(field, python_summary.get(field, ""), cpp_summary.get(field, "")):
            return {
                "field": field,
                "python_value": python_summary.get(field, ""),
                "cpp_value": cpp_summary.get(field, ""),
            }
    return {"field": "none", "python_value": "", "cpp_value": ""}


def _summary_int(summary: dict[str, Any], field: str) -> int:
    value = summary.get(field, "")
    if value == "":
        return 0
    return int(value)


def _summary_float(summary: dict[str, Any], field: str) -> float:
    value = summary.get(field, "")
    if value == "":
        return 0.0
    return float(value)


def _format_faults(fault_edges: tuple[tuple[int, int], ...]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def _format_fault_windows(fault_windows: tuple[tuple[int, int, float, float], ...]) -> str:
    if not fault_windows:
        return "none"
    return ";".join(
        f"{start}->{end}@[{fault_start:.3f},{repair_time:.3f})"
        for start, end, fault_start, repair_time in fault_windows
    )


def _format_node_capacities(node_capacities: tuple[tuple[int, int], ...]) -> str:
    if not node_capacities:
        return "none"
    return ";".join(f"{node}:{capacity}" for node, capacity in sorted(node_capacities))


def _format_merge_groups(merge_groups: tuple[tuple[int, int, int], ...]) -> str:
    if not merge_groups:
        return "none"
    return ";".join(f"{start}->{end}:{group}" for start, end, group in sorted(merge_groups))


def _row(
    case: Any,
    python_summary: dict[str, Any],
    python_elapsed: float,
    cpp_summary: dict[str, Any],
    cpp_elapsed: float,
) -> dict[str, float | int | str | bool]:
    mismatch = _first_mismatch(python_summary, cpp_summary)
    return {
        "scenario": case.spec.name,
        "seed": case.spec.seed,
        "task_count": case.spec.task_count,
        "spacing": case.spec.spacing,
        "node_count": len(case.node_records),
        "edge_count": len(case.edge_records),
        "fault_edges": _format_faults(case.spec.fault_edges),
        "fault_windows": _format_fault_windows(case.spec.fault_windows),
        "node_capacities": _format_node_capacities(case.spec.node_capacities),
        "merge_groups": _format_merge_groups(case.spec.merge_groups),
        "merge_capacity": case.spec.merge_capacity,
        "merge_headway_seconds": case.spec.merge_headway_seconds,
        "python_planned": _summary_int(python_summary, "planned_count"),
        "cpp_planned": _summary_int(cpp_summary, "planned_count"),
        "python_unplanned": _summary_int(python_summary, "unplanned_count"),
        "cpp_unplanned": _summary_int(cpp_summary, "unplanned_count"),
        "python_decisions": _summary_int(python_summary, "decision_count"),
        "cpp_decisions": _summary_int(cpp_summary, "decision_count"),
        "python_ticks": _summary_int(python_summary, "tick_count"),
        "cpp_ticks": _summary_int(cpp_summary, "tick_count"),
        "python_peak_active_bags": _summary_int(python_summary, "peak_active_bags"),
        "cpp_peak_active_bags": _summary_int(cpp_summary, "peak_active_bags"),
        "python_holds": _summary_int(python_summary, "hold_count"),
        "cpp_holds": _summary_int(cpp_summary, "hold_count"),
        "python_conflicts": _summary_int(python_summary, "post_shield_conflicts"),
        "cpp_conflicts": _summary_int(cpp_summary, "post_shield_conflicts"),
        "python_mean_travel_time": _summary_float(python_summary, "mean_travel_time"),
        "cpp_mean_travel_time": _summary_float(cpp_summary, "mean_travel_time"),
        "mean_travel_abs_diff": abs(
            _summary_float(python_summary, "mean_travel_time") - _summary_float(cpp_summary, "mean_travel_time")
        ),
        "python_makespan": _summary_float(python_summary, "makespan"),
        "cpp_makespan": _summary_float(cpp_summary, "makespan"),
        "makespan_abs_diff": abs(_summary_float(python_summary, "makespan") - _summary_float(cpp_summary, "makespan")),
        "python_elapsed_seconds": python_elapsed,
        "cpp_elapsed_seconds": cpp_elapsed,
        "cpp_speedup": python_elapsed / cpp_elapsed if cpp_elapsed > 0.0 else 0.0,
        "parity_pass": mismatch["field"] == "none",
        "first_mismatch_field": mismatch["field"],
        "python_value": mismatch["python_value"],
        "cpp_value": mismatch["cpp_value"],
    }


def build_rows(cases: tuple[Any, ...]) -> list[dict[str, float | int | str | bool]]:
    from phase8_synthetic_replay_cases import graph_from_case, tasks_from_case  # pylint: disable=import-outside-toplevel

    rows: list[dict[str, float | int | str | bool]] = []
    for case in cases:
        inputs = RuntimeInputs(
            graph=graph_from_case(case),
            tasks=tasks_from_case(case),
            node_records=case.node_records,
            edge_records=case.edge_records,
            heuristic_time=case.heuristic_time,
            task_records=case.task_records,
        )
        python_summary, python_elapsed = _timed(lambda: _python_pibt(inputs, case))
        cpp_summary, cpp_elapsed = _timed(lambda: _cpp_pibt(inputs, case))
        rows.append(_row(case, python_summary, python_elapsed, cpp_summary, cpp_elapsed))
    return rows


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ROW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _config_label(row: dict[str, float | int | str | bool]) -> str:
    parts = []
    if row["node_capacities"] != "none":
        parts.append(f"nodes={row['node_capacities']}")
    if row["merge_groups"] != "none":
        parts.append(f"merge={row['merge_groups']},cap={row['merge_capacity']},headway={row['merge_headway_seconds']}")
    return "; ".join(parts) if parts else "none"


def write_report(rows: list[dict[str, float | int | str | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parity_pass = all(bool(row["parity_pass"]) for row in rows)
    safety_pass = all(int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0 for row in rows)
    planned_rates = [float(row["cpp_planned"]) / float(row["task_count"]) for row in rows]
    speedups = [float(row["cpp_speedup"]) for row in rows if float(row["cpp_speedup"]) > 0.0]
    lines = [
        "# Phase9 Dense PIBT Stress Sweep",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic runs Python and C++ active-bag PIBT replay on additional fixed random "
            "synthetic ICS-like dense task streams. It focuses on the dense node-occupancy corner cases "
            "that previously produced post-shield conflicts in Phase9 synthetic matched rows."
        ),
        "",
        f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "These are randomized synthetic stress seeds, not separate real airport maps.",
        "",
        "## Stress Rows",
        "",
        (
            "| Scenario | Tasks | Spacing | Faults | Config | Py/C++ planned | Py/C++ decisions | "
            "Py/C++ peak | Py/C++ conflicts | Mean diff | C++ speedup | Parity |"
        ),
        "|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        faults = row["fault_edges"] if row["fault_edges"] != "none" else row["fault_windows"]
        lines.append(
            "| {scenario} | {task_count} | {spacing} | {faults} | {config} | "
            "{python_planned}/{cpp_planned} | {python_decisions}/{cpp_decisions} | "
            "{python_peak_active_bags}/{cpp_peak_active_bags} | {python_conflicts}/{cpp_conflicts} | "
            "{mean_travel_abs_diff:.12f} | {cpp_speedup:.3f} | {parity_pass} |".format(
                **{**row, "faults": faults, "config": _config_label(row)}
            )
        )
    lines.extend(
        [
            "",
            "## Gate Status",
            "",
            f"- stress rows: `{len(rows)}`",
            f"- total tasks: `{sum(int(row['task_count']) for row in rows)}`",
            f"- median planned rate: `{_median(planned_rates):.3f}`",
            f"- median C++ local-call speedup: `{_median(speedups):.3f}x`",
            "- dense PIBT stress Python/C++ summary parity: PASS" if parity_pass else "- dense PIBT stress Python/C++ summary parity: FAIL",
            "- dense PIBT stress post-shield safety: PASS" if safety_pass else "- dense PIBT stress post-shield safety: FAIL",
            "- real heldout airport map: not covered",
            "",
            "## Remaining Work",
            "",
            "- add broader randomized graph topologies and task-source distributions",
            "- add a separate real heldout airport map when fixture data is available",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()
    from phase8_synthetic_replay_cases import make_replay_case  # pylint: disable=import-outside-toplevel

    cases = tuple(make_replay_case(spec) for spec in _case_specs())
    rows = build_rows(cases)
    write_table(rows)
    write_report(rows)
    if not all(bool(row["parity_pass"]) for row in rows):
        raise AssertionError("Phase9 dense PIBT stress parity failed")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("Phase9 dense PIBT stress produced post-shield conflicts")
    print(f"phase9_dense_pibt_stress_sweep rows={len(rows)} tasks={sum(int(row['task_count']) for row in rows)}")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
