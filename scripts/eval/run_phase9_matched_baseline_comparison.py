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
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase9_matched_baseline_comparison.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase9_matched_baseline_comparison_report.md"

MAX_DECISIONS_PER_TASK = 128
FLOAT_TOLERANCE = 1.0e-9

NodeRecord = tuple[int, int, float, int, int, list[int]]
EdgeRecord = tuple[int, int, float, float]
TaskRecord = tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]
FaultWindow = tuple[int, int, float, float]

ROW_FIELDS = [
    "scenario",
    "family",
    "task_offset",
    "max_tasks",
    "fault_edges",
    "fault_windows",
    "python_planned",
    "cpp_planned",
    "python_unplanned",
    "cpp_unplanned",
    "python_decisions",
    "cpp_decisions",
    "python_replans",
    "cpp_replans",
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
    "notes",
]

SUMMARY_FIELDS_BY_FAMILY = {
    "rolling_horizon_sipp": (
        "planned_count",
        "unplanned_count",
        "decision_count",
        "post_shield_conflicts",
        "mean_travel_time",
        "makespan",
    ),
    "periodic_replanning_sipp": (
        "planned_count",
        "unplanned_count",
        "replan_count",
        "tick_count",
        "peak_active_bags",
        "post_shield_conflicts",
        "mean_travel_time",
        "makespan",
    ),
    "pibt_active_bag_replay": (
        "planned_count",
        "unplanned_count",
        "decision_count",
        "tick_count",
        "peak_active_bags",
        "hold_count",
        "post_shield_conflicts",
        "mean_travel_time",
        "makespan",
    ),
    "edge_score_event": (
        "planned_count",
        "unplanned_count",
        "decision_count",
        "post_shield_conflicts",
        "mean_travel_time",
        "makespan",
    ),
    "fallback_event": (
        "planned_count",
        "unplanned_count",
        "decision_count",
        "post_shield_conflicts",
        "mean_travel_time",
        "makespan",
    ),
}


@dataclass(frozen=True)
class MatchedScenario:
    name: str
    task_offset: int
    max_tasks: int
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[FaultWindow, ...] = ()


@dataclass(frozen=True)
class RuntimeInputs:
    graph: Any
    all_tasks: tuple[Any, ...]
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    runtime_model: Any


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
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


def _node_records(graph: Any) -> tuple[NodeRecord, ...]:
    return tuple(
        (
            int(node.location),
            int(node.node_type),
            float(node.service_time),
            int(node.x),
            int(node.y),
            [int(value) for value in node.outgoing],
        )
        for node in sorted(graph.nodes.values(), key=lambda item: item.location)
    )


def _edge_records(graph: Any) -> tuple[EdgeRecord, ...]:
    return tuple(
        (int(edge.start), int(edge.end), float(edge.length), float(edge.speed))
        for edge in sorted(graph.edges.values(), key=lambda item: (item.start, item.end))
    )


def _task_records(tasks: tuple[Any, ...]) -> tuple[TaskRecord, ...]:
    return tuple(
        (
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
        for task in tasks
    )


def _format_faults(fault_edges: tuple[tuple[int, int], ...]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def _format_fault_windows(fault_windows: tuple[FaultWindow, ...]) -> str:
    if not fault_windows:
        return "none"
    return ";".join(
        f"{start}->{end}@[{fault_start:.3f},{repair_time:.3f})"
        for start, end, fault_start, repair_time in fault_windows
    )


def _case_plan() -> tuple[MatchedScenario, ...]:
    return (
        MatchedScenario("legacy_first16", 0, 16),
        MatchedScenario("legacy_first32", 0, 32),
        MatchedScenario("legacy_offset32_static16", 32, 16, fault_edges=((16, 17),)),
        MatchedScenario("legacy_offset64_repair32", 64, 32, fault_windows=((28, 47, 0.0, 12000.0),)),
    )


def _selected_tasks(inputs: RuntimeInputs, scenario: MatchedScenario) -> tuple[Any, ...]:
    return inputs.all_tasks[scenario.task_offset : scenario.task_offset + scenario.max_tasks]


def _timed(call: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], float]:
    started = perf_counter()
    payload = call()
    return payload, perf_counter() - started


def _python_rolling(inputs: RuntimeInputs, scenario: MatchedScenario) -> dict[str, Any]:
    from czr005.baselines import RollingHorizonBaseline  # pylint: disable=import-outside-toplevel

    baseline = RollingHorizonBaseline(inputs.graph, horizon_seconds=300.0)
    result = baseline.run_episode(
        _selected_tasks(inputs, scenario),
        max_tasks=scenario.max_tasks,
        fault_edges=set(scenario.fault_edges),
        fault_windows=scenario.fault_windows,
    )
    edge_conflicts = baseline.edge_reservations.conflict_count()
    return {
        **result.metrics.to_dict(),
        "decision_count": len(result.events),
        "edge_reservation_conflicts": edge_conflicts,
        "post_shield_conflicts": result.metrics.reservation_conflicts + edge_conflicts,
    }


def _cpp_rolling(inputs: RuntimeInputs, scenario: MatchedScenario) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    selected = _selected_tasks(inputs, scenario)
    payload = czr005_cpp.rolling_horizon_sipp_from_records(
        list(inputs.node_records),
        list(inputs.edge_records),
        [list(row) for row in inputs.heuristic_time],
        list(_task_records(selected)),
        max_tasks=scenario.max_tasks,
        horizon_seconds=300.0,
        edge_capacity=1,
        edge_headway_seconds=0.0,
        fault_edges=list(scenario.fault_edges),
        fault_windows=list(scenario.fault_windows),
    )
    return dict(payload["summary"])


def _python_periodic(inputs: RuntimeInputs, scenario: MatchedScenario) -> dict[str, Any]:
    from czr005.baselines import PeriodicReplanningBaseline  # pylint: disable=import-outside-toplevel

    baseline = PeriodicReplanningBaseline(inputs.graph, interval_seconds=5.0, max_ticks=2048)
    result = baseline.run_episode(
        _selected_tasks(inputs, scenario),
        max_tasks=scenario.max_tasks,
        fault_edges=set(scenario.fault_edges),
        fault_windows=scenario.fault_windows,
    )
    return {
        **result.metrics.to_dict(),
        "replan_count": baseline.summary.replan_count,
        "tick_count": baseline.summary.tick_count,
        "peak_active_bags": baseline.summary.peak_active_bags,
        "edge_reservation_conflicts": baseline.summary.edge_reservation_conflicts,
        "post_shield_conflicts": baseline.summary.post_shield_conflicts,
    }


def _cpp_periodic(inputs: RuntimeInputs, scenario: MatchedScenario) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    selected = _selected_tasks(inputs, scenario)
    payload = czr005_cpp.periodic_replanning_sipp_from_records(
        list(inputs.node_records),
        list(inputs.edge_records),
        [list(row) for row in inputs.heuristic_time],
        list(_task_records(selected)),
        max_tasks=scenario.max_tasks,
        interval_seconds=5.0,
        max_ticks=2048,
        edge_capacity=1,
        edge_headway_seconds=0.0,
        fault_edges=list(scenario.fault_edges),
        fault_windows=list(scenario.fault_windows),
    )
    return dict(payload["summary"])


def _python_pibt(inputs: RuntimeInputs, scenario: MatchedScenario) -> dict[str, Any]:
    from czr005.baselines import PIBTActiveBagReplayBaseline  # pylint: disable=import-outside-toplevel

    baseline = PIBTActiveBagReplayBaseline(
        inputs.graph,
        interval_seconds=5.0,
        max_ticks=2048,
        hold_seconds=5.0,
    )
    result = baseline.run_episode(
        _selected_tasks(inputs, scenario),
        max_tasks=scenario.max_tasks,
        fault_edges=set(scenario.fault_edges),
        fault_windows=scenario.fault_windows,
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


def _cpp_pibt(inputs: RuntimeInputs, scenario: MatchedScenario) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    selected = _selected_tasks(inputs, scenario)
    payload = czr005_cpp.pibt_active_bag_replay_from_records(
        list(inputs.node_records),
        list(inputs.edge_records),
        [list(row) for row in inputs.heuristic_time],
        list(_task_records(selected)),
        max_tasks=scenario.max_tasks,
        interval_seconds=5.0,
        max_ticks=2048,
        hold_seconds=5.0,
        edge_capacity=1,
        edge_headway_seconds=0.0,
        fault_edges=list(scenario.fault_edges),
        fault_windows=list(scenario.fault_windows),
        node_capacities=[],
    )
    return dict(payload["summary"])


def _python_event(inputs: RuntimeInputs, scenario: MatchedScenario, runtime_model: Any | None) -> dict[str, Any]:
    from czr005.eval import run_event_replay  # pylint: disable=import-outside-toplevel

    run = run_event_replay(
        inputs.graph,
        _selected_tasks(inputs, scenario),
        runtime_model=runtime_model,
        max_tasks=scenario.max_tasks,
        fault_edges=set(scenario.fault_edges),
        fault_windows=scenario.fault_windows,
        max_decisions_per_task=MAX_DECISIONS_PER_TASK,
    )
    return dict(run.summary)


def _cpp_event(inputs: RuntimeInputs, scenario: MatchedScenario, model_path: Path | None) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    selected = _selected_tasks(inputs, scenario)
    common = {
        "max_tasks": scenario.max_tasks,
        "fault_edges": list(scenario.fault_edges),
        "fault_windows": list(scenario.fault_windows),
        "max_decisions_per_task": MAX_DECISIONS_PER_TASK,
    }
    if model_path is None:
        return dict(
            czr005_cpp.edge_score_native_event_fallback_replay_summary_from_records(
                list(inputs.node_records),
                list(inputs.edge_records),
                [list(row) for row in inputs.heuristic_time],
                list(_task_records(selected)),
                **common,
            )
        )
    return dict(
        czr005_cpp.edge_score_native_event_replay_summary_from_records(
            list(inputs.node_records),
            list(inputs.edge_records),
            [list(row) for row in inputs.heuristic_time],
            list(_task_records(selected)),
            str(model_path),
            **common,
        )
    )


def _family_payloads(inputs: RuntimeInputs, scenario: MatchedScenario) -> tuple[tuple[str, dict[str, Any], float, dict[str, Any], float], ...]:
    payloads: list[tuple[str, dict[str, Any], float, dict[str, Any], float]] = []
    family_calls: tuple[
        tuple[str, Callable[[], dict[str, Any]], Callable[[], dict[str, Any]]],
        ...,
    ] = (
        ("rolling_horizon_sipp", lambda: _python_rolling(inputs, scenario), lambda: _cpp_rolling(inputs, scenario)),
        (
            "periodic_replanning_sipp",
            lambda: _python_periodic(inputs, scenario),
            lambda: _cpp_periodic(inputs, scenario),
        ),
        ("pibt_active_bag_replay", lambda: _python_pibt(inputs, scenario), lambda: _cpp_pibt(inputs, scenario)),
        (
            "edge_score_event",
            lambda: _python_event(inputs, scenario, inputs.runtime_model),
            lambda: _cpp_event(inputs, scenario, MODEL_PATH),
        ),
        ("fallback_event", lambda: _python_event(inputs, scenario, None), lambda: _cpp_event(inputs, scenario, None)),
    )
    for family, python_call, cpp_call in family_calls:
        python_payload, python_elapsed = _timed(python_call)
        cpp_payload, cpp_elapsed = _timed(cpp_call)
        payloads.append((family, python_payload, python_elapsed, cpp_payload, cpp_elapsed))
    return tuple(payloads)


def _values_match(field: str, python_value: Any, cpp_value: Any) -> bool:
    if field in {"mean_travel_time", "p95_travel_time", "p99_travel_time", "max_lateness", "makespan"}:
        return abs(float(python_value) - float(cpp_value)) <= FLOAT_TOLERANCE
    return python_value == cpp_value


def _first_mismatch(family: str, python_summary: dict[str, Any], cpp_summary: dict[str, Any]) -> dict[str, Any]:
    for field in SUMMARY_FIELDS_BY_FAMILY[family]:
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


def _active_step_count(summary: dict[str, Any]) -> int:
    if "decision_count" in summary:
        return _summary_int(summary, "decision_count")
    if "replan_count" in summary:
        return _summary_int(summary, "replan_count")
    return 0


def _row(
    scenario: MatchedScenario,
    family: str,
    python_summary: dict[str, Any],
    python_elapsed: float,
    cpp_summary: dict[str, Any],
    cpp_elapsed: float,
) -> dict[str, float | int | str | bool]:
    mismatch = _first_mismatch(family, python_summary, cpp_summary)
    return {
        "scenario": scenario.name,
        "family": family,
        "task_offset": scenario.task_offset,
        "max_tasks": scenario.max_tasks,
        "fault_edges": _format_faults(scenario.fault_edges),
        "fault_windows": _format_fault_windows(scenario.fault_windows),
        "python_planned": _summary_int(python_summary, "planned_count"),
        "cpp_planned": _summary_int(cpp_summary, "planned_count"),
        "python_unplanned": _summary_int(python_summary, "unplanned_count"),
        "cpp_unplanned": _summary_int(cpp_summary, "unplanned_count"),
        "python_decisions": _active_step_count(python_summary),
        "cpp_decisions": _active_step_count(cpp_summary),
        "python_replans": _summary_int(python_summary, "replan_count"),
        "cpp_replans": _summary_int(cpp_summary, "replan_count"),
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
        "notes": "single local timing pass; matched scenario row, not final paper-grade timing",
    }


def _fault_label(row: dict[str, float | int | str | bool]) -> str:
    fault_edges = str(row["fault_edges"])
    fault_windows = str(row["fault_windows"])
    if fault_edges != "none":
        return fault_edges
    return fault_windows


def build_rows(inputs: RuntimeInputs) -> list[dict[str, float | int | str | bool]]:
    rows: list[dict[str, float | int | str | bool]] = []
    for scenario in _case_plan():
        for family, python_summary, python_elapsed, cpp_summary, cpp_elapsed in _family_payloads(inputs, scenario):
            rows.append(_row(scenario, family, python_summary, python_elapsed, cpp_summary, cpp_elapsed))
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


def write_report(rows: list[dict[str, float | int | str | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parity_pass = all(bool(row["parity_pass"]) for row in rows)
    safety_pass = all(int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0 for row in rows)
    families = sorted({str(row["family"]) for row in rows})
    scenarios = sorted({str(row["scenario"]) for row in rows})
    speedups = [float(row["cpp_speedup"]) for row in rows if float(row["cpp_speedup"]) > 0.0]
    family_planned = {
        family: sum(int(row["cpp_planned"]) for row in rows if row["family"] == family)
        for family in families
    }
    family_tasks = {
        family: sum(int(row["max_tasks"]) for row in rows if row["family"] == family)
        for family in families
    }
    lines = [
        "# Phase9 Matched Baseline Comparison Diagnostic",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic reruns Python and C++ implementations of the main event/baseline families "
            "on the same real legacy `map2/inputdata` task windows. It covers no-fault, static-fault, and repair-window "
            "scenarios that are supported by every included family."
        ),
        "",
        f"Map: `{MAP_PATH.relative_to(ROOT).as_posix()}`",
        f"Tasks: `{TASK_PATH.relative_to(ROOT).as_posix()}`",
        f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        (
            "This is a matched diagnostic gate, not a final paper benchmark: timings are single local "
            "passes and merge-buffer variants are handled by the dedicated parity gates."
        ),
        "",
        "## Matched Rows",
        "",
        (
            "| Scenario | Family | Tasks | Faults | Py planned | C++ planned | "
            "Py/C++ active steps | Py/C++ conflicts | Mean diff | C++ speedup | Parity |"
        ),
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        decisions = f"{row['python_decisions']}/{row['cpp_decisions']}"
        conflicts = f"{row['python_conflicts']}/{row['cpp_conflicts']}"
        lines.append(
            "| {scenario} | {family} | {max_tasks} | {fault_label} | {python_planned} | {cpp_planned} | "
            f"{decisions} | {conflicts} | "
            "{mean_travel_abs_diff:.6f} | {cpp_speedup:.3f} | {parity_pass} |".format(
                **{**row, "fault_label": _fault_label(row)}
            )
        )
    lines.extend(
        [
            "",
            "## Observations",
            "",
        ]
    )
    for family in families:
        lines.append(
            f"- `{family}` planned `{family_planned[family]}/{family_tasks[family]}` matched tasks "
            "with exact Python/C++ summary parity."
        )
    lines.extend(
        [
            "",
            "## Gate Status",
            "",
            f"- scenarios: `{len(scenarios)}` ({', '.join(scenarios)})",
            f"- families: `{len(families)}` ({', '.join(families)})",
            f"- matched rows: `{len(rows)}`",
            "- Python/C++ summary parity: PASS" if parity_pass else "- Python/C++ summary parity: FAIL",
            "- post-shield safety: PASS" if safety_pass else "- post-shield safety: FAIL",
            f"- median C++ local-call speedup: `{_median(speedups):.3f}x`",
            "- repair-window common-family comparison: covered",
            "- merge/buffer common-family comparison: not covered",
            "",
            "## Remaining Work",
            "",
            "- add merge/buffer matched rows once every included family accepts the shared config",
            "- replace single local timing with repeated hardware-normalized timing across the matched table",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_inputs() -> RuntimeInputs:
    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(MAP_PATH)
    tasks = tuple(TaskStream.from_jsonl(TASK_PATH))
    return RuntimeInputs(
        graph=graph,
        all_tasks=tasks,
        node_records=_node_records(graph),
        edge_records=_edge_records(graph),
        heuristic_time=tuple(tuple(float(value) for value in row) for row in graph.heuristic_time),
        runtime_model=czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH)),
    )


def main() -> None:
    _prepare_imports()
    inputs = _load_inputs()
    rows = build_rows(inputs)
    write_table(rows)
    write_report(rows)
    if not all(bool(row["parity_pass"]) for row in rows):
        raise AssertionError("Phase9 matched baseline comparison parity failed")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("Phase9 matched baseline comparison produced post-shield conflicts")
    print(
        "phase9_matched_baseline_comparison "
        f"rows={len(rows)} scenarios={len(_case_plan())} families={len(SUMMARY_FIELDS_BY_FAMILY)}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
