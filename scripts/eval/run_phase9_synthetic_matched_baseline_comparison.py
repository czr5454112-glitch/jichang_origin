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
TABLE_PATH = ROOT / "outputs" / "tables" / "phase9_synthetic_matched_baseline_comparison.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase9_synthetic_matched_baseline_comparison_report.md"

MAX_DECISIONS_PER_TASK = 128
FLOAT_TOLERANCE = 1.0e-9

NodeRecord = tuple[int, int, float, int, int, list[int]]
EdgeRecord = tuple[int, int, float, float]
TaskRecord = tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]

ROW_FIELDS = [
    "scenario",
    "family",
    "seed",
    "task_count",
    "node_count",
    "edge_count",
    "spacing",
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
    "python_active_steps",
    "cpp_active_steps",
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
class RuntimeInputs:
    graph: Any
    tasks: tuple[Any, ...]
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    task_records: tuple[TaskRecord, ...]
    runtime_model: Any


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


def _format_node_capacities(node_capacities: tuple[tuple[int, int], ...]) -> str:
    if not node_capacities:
        return "none"
    return ";".join(f"{node}:{capacity}" for node, capacity in sorted(node_capacities))


def _format_merge_groups(merge_groups: tuple[tuple[int, int, int], ...]) -> str:
    if not merge_groups:
        return "none"
    return ";".join(f"{start}->{end}:{group}" for start, end, group in sorted(merge_groups))


def _timed(call: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], float]:
    started = perf_counter()
    payload = call()
    return payload, perf_counter() - started


def _python_rolling(inputs: RuntimeInputs, case: Any) -> dict[str, Any]:
    from czr005.baselines import RollingHorizonBaseline  # pylint: disable=import-outside-toplevel

    baseline = RollingHorizonBaseline(
        inputs.graph,
        horizon_seconds=60.0,
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
    edge_conflicts = baseline.edge_reservations.conflict_count() + baseline.edge_reservations.merge_group_conflict_count(
        {(start, end): group for start, end, group in case.spec.merge_groups},
        case.spec.merge_capacity,
        case.spec.merge_headway_seconds,
    )
    return {
        **result.metrics.to_dict(),
        "decision_count": len(result.events),
        "edge_reservation_conflicts": edge_conflicts,
        "post_shield_conflicts": result.metrics.reservation_conflicts + edge_conflicts,
    }


def _cpp_rolling(inputs: RuntimeInputs, case: Any) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    payload = czr005_cpp.rolling_horizon_sipp_from_records(
        list(inputs.node_records),
        list(inputs.edge_records),
        [list(row) for row in inputs.heuristic_time],
        list(inputs.task_records),
        max_tasks=case.spec.task_count,
        horizon_seconds=60.0,
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


def _python_periodic(inputs: RuntimeInputs, case: Any) -> dict[str, Any]:
    from czr005.baselines import PeriodicReplanningBaseline  # pylint: disable=import-outside-toplevel

    baseline = PeriodicReplanningBaseline(
        inputs.graph,
        interval_seconds=2.0,
        max_ticks=1024,
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
        "replan_count": baseline.summary.replan_count,
        "tick_count": baseline.summary.tick_count,
        "peak_active_bags": baseline.summary.peak_active_bags,
        "edge_reservation_conflicts": baseline.summary.edge_reservation_conflicts,
        "post_shield_conflicts": baseline.summary.post_shield_conflicts,
    }


def _cpp_periodic(inputs: RuntimeInputs, case: Any) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    payload = czr005_cpp.periodic_replanning_sipp_from_records(
        list(inputs.node_records),
        list(inputs.edge_records),
        [list(row) for row in inputs.heuristic_time],
        list(inputs.task_records),
        max_tasks=case.spec.task_count,
        interval_seconds=2.0,
        max_ticks=1024,
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


def _python_pibt(inputs: RuntimeInputs, case: Any) -> dict[str, Any]:
    from czr005.baselines import PIBTActiveBagReplayBaseline  # pylint: disable=import-outside-toplevel

    baseline = PIBTActiveBagReplayBaseline(
        inputs.graph,
        interval_seconds=2.0,
        max_ticks=1024,
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
        max_ticks=1024,
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


def _python_event(inputs: RuntimeInputs, case: Any, runtime_model: Any | None) -> dict[str, Any]:
    from czr005.eval import run_event_replay  # pylint: disable=import-outside-toplevel

    run = run_event_replay(
        inputs.graph,
        inputs.tasks,
        runtime_model=runtime_model,
        max_tasks=case.spec.task_count,
        fault_edges=set(case.spec.fault_edges),
        fault_windows=case.spec.fault_windows,
        node_capacities=dict(case.spec.node_capacities),
        merge_groups={(start, end): group for start, end, group in case.spec.merge_groups},
        merge_capacity=case.spec.merge_capacity,
        merge_headway_seconds=case.spec.merge_headway_seconds,
        max_decisions_per_task=MAX_DECISIONS_PER_TASK,
    )
    return dict(run.summary)


def _cpp_event(inputs: RuntimeInputs, case: Any, model_path: Path | None) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    common = {
        "max_tasks": case.spec.task_count,
        "fault_edges": list(case.spec.fault_edges),
        "fault_windows": list(case.spec.fault_windows),
        "node_capacities": list(case.spec.node_capacities),
        "merge_groups": list(case.spec.merge_groups),
        "merge_capacity": case.spec.merge_capacity,
        "merge_headway_seconds": case.spec.merge_headway_seconds,
        "max_decisions_per_task": MAX_DECISIONS_PER_TASK,
    }
    if model_path is None:
        return dict(
            czr005_cpp.edge_score_native_event_fallback_replay_summary_from_records(
                list(inputs.node_records),
                list(inputs.edge_records),
                [list(row) for row in inputs.heuristic_time],
                list(inputs.task_records),
                **common,
            )
        )
    return dict(
        czr005_cpp.edge_score_native_event_replay_summary_from_records(
            list(inputs.node_records),
            list(inputs.edge_records),
            [list(row) for row in inputs.heuristic_time],
            list(inputs.task_records),
            str(model_path),
            **common,
        )
    )


def _family_payloads(inputs: RuntimeInputs, case: Any) -> tuple[tuple[str, dict[str, Any], float, dict[str, Any], float], ...]:
    family_calls: tuple[
        tuple[str, Callable[[], dict[str, Any]], Callable[[], dict[str, Any]]],
        ...,
    ] = (
        ("rolling_horizon_sipp", lambda: _python_rolling(inputs, case), lambda: _cpp_rolling(inputs, case)),
        ("periodic_replanning_sipp", lambda: _python_periodic(inputs, case), lambda: _cpp_periodic(inputs, case)),
        ("pibt_active_bag_replay", lambda: _python_pibt(inputs, case), lambda: _cpp_pibt(inputs, case)),
        (
            "edge_score_event",
            lambda: _python_event(inputs, case, inputs.runtime_model),
            lambda: _cpp_event(inputs, case, MODEL_PATH),
        ),
        ("fallback_event", lambda: _python_event(inputs, case, None), lambda: _cpp_event(inputs, case, None)),
    )
    payloads: list[tuple[str, dict[str, Any], float, dict[str, Any], float]] = []
    for family, python_call, cpp_call in family_calls:
        python_payload, python_elapsed = _timed(python_call)
        cpp_payload, cpp_elapsed = _timed(cpp_call)
        payloads.append((family, python_payload, python_elapsed, cpp_payload, cpp_elapsed))
    return tuple(payloads)


def _values_match(field: str, python_value: Any, cpp_value: Any) -> bool:
    if field in {"mean_travel_time", "makespan"}:
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
    case: Any,
    family: str,
    python_summary: dict[str, Any],
    python_elapsed: float,
    cpp_summary: dict[str, Any],
    cpp_elapsed: float,
) -> dict[str, float | int | str | bool]:
    mismatch = _first_mismatch(family, python_summary, cpp_summary)
    python_conflicts = _summary_int(python_summary, "post_shield_conflicts")
    cpp_conflicts = _summary_int(cpp_summary, "post_shield_conflicts")
    notes = "fixed-seed synthetic heldout-like map; not a separate real airport map"
    if family == "pibt_active_bag_replay" and (python_conflicts != 0 or cpp_conflicts != 0):
        notes = (
            "dense synthetic PIBT active-bag stress gap; parity is expected but this row is "
            "not a safety pass"
        )
    return {
        "scenario": case.spec.name,
        "family": family,
        "seed": case.spec.seed,
        "task_count": case.spec.task_count,
        "node_count": len(case.node_records),
        "edge_count": len(case.edge_records),
        "spacing": case.spec.spacing,
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
        "python_active_steps": _active_step_count(python_summary),
        "cpp_active_steps": _active_step_count(cpp_summary),
        "python_ticks": _summary_int(python_summary, "tick_count"),
        "cpp_ticks": _summary_int(cpp_summary, "tick_count"),
        "python_peak_active_bags": _summary_int(python_summary, "peak_active_bags"),
        "cpp_peak_active_bags": _summary_int(cpp_summary, "peak_active_bags"),
        "python_holds": _summary_int(python_summary, "hold_count"),
        "cpp_holds": _summary_int(cpp_summary, "hold_count"),
        "python_conflicts": python_conflicts,
        "cpp_conflicts": cpp_conflicts,
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
        "notes": notes,
    }


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


def _config_label(row: dict[str, float | int | str | bool]) -> str:
    parts = []
    if row["node_capacities"] != "none":
        parts.append(f"nodes={row['node_capacities']}")
    if row["merge_groups"] != "none":
        parts.append(f"merge={row['merge_groups']},cap={row['merge_capacity']},headway={row['merge_headway_seconds']}")
    return "; ".join(parts) if parts else "none"


def build_rows(cases: tuple[Any, ...], runtime_model: Any) -> list[dict[str, float | int | str | bool]]:
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
            runtime_model=runtime_model,
        )
        for family, python_summary, python_elapsed, cpp_summary, cpp_elapsed in _family_payloads(inputs, case):
            rows.append(_row(case, family, python_summary, python_elapsed, cpp_summary, cpp_elapsed))
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


def write_report(rows: list[dict[str, float | int | str | bool]], manifest_path: Path) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parity_pass = all(bool(row["parity_pass"]) for row in rows)
    all_family_safety_pass = all(
        int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0 for row in rows
    )
    non_pibt_safety_pass = all(
        int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0
        for row in rows
        if row["family"] != "pibt_active_bag_replay"
    )
    pibt_stress_rows = [
        row
        for row in rows
        if row["family"] == "pibt_active_bag_replay"
        and (int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0)
    ]
    families = sorted({str(row["family"]) for row in rows})
    scenarios = sorted({str(row["scenario"]) for row in rows})
    speedups = [float(row["cpp_speedup"]) for row in rows if float(row["cpp_speedup"]) > 0.0]
    lines = [
        "# Phase9 Synthetic Matched Baseline Comparison Diagnostic",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic reruns Python and C++ implementations of the main event/baseline "
            "families on fixed-seed synthetic ICS-like maps from the persisted Phase8 manifest. "
            "The rows vary density, branch structure, static faults, repair windows, buffer capacity, "
            "and merge-group capacity."
        ),
        "",
        f"Manifest: `{manifest_path.relative_to(ROOT).as_posix()}`",
        f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "This is heldout-like synthetic-map coverage, not a separate real airport-map claim.",
        "",
        "## Matched Rows",
        "",
        (
            "| Scenario | Family | Tasks | Edges | Faults | Config | Py/C++ planned | "
            "Py/C++ active steps | Py/C++ conflicts | Mean diff | C++ speedup | Parity |"
        ),
        "|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {scenario} | {family} | {task_count} | {edge_count} | {fault_edges} {fault_windows} | "
            "{config_label} | {python_planned}/{cpp_planned} | {python_active_steps}/{cpp_active_steps} | "
            "{python_conflicts}/{cpp_conflicts} | {mean_travel_abs_diff:.12f} | {cpp_speedup:.3f} | "
            "{parity_pass} |".format(**{**row, "config_label": _config_label(row)})
        )
    lines.extend(
        [
            "",
            "## Gate Status",
            "",
            f"- synthetic scenarios: `{len(scenarios)}` ({', '.join(scenarios)})",
            f"- families: `{len(families)}` ({', '.join(families)})",
            f"- matched rows: `{len(rows)}`",
            "- synthetic matched Python/C++ summary parity: PASS" if parity_pass else "- synthetic matched Python/C++ summary parity: FAIL",
            "- synthetic matched non-PIBT post-shield safety: PASS"
            if non_pibt_safety_pass
            else "- synthetic matched non-PIBT post-shield safety: FAIL",
            "- synthetic matched all-family post-shield safety: PASS"
            if all_family_safety_pass
            else "- synthetic matched all-family post-shield safety: FAIL",
            f"- PIBT active-bag dense stress conflict rows: `{len(pibt_stress_rows)}`",
            f"- median C++ local-call speedup: `{_median(speedups):.3f}x`",
            "- persisted synthetic manifest: PASS",
            "- negative dense-PIBT cases honestly reported: PASS"
            if pibt_stress_rows
            else "- negative dense-PIBT cases honestly reported: not triggered",
            "- real heldout airport map: not covered",
            "",
            "## Remaining Work",
            "",
            "- add a separate real heldout airport map when fixture data is available",
            "- harden PIBT active-bag replay against dense synthetic hold/start-node overlaps",
            "- expand randomized density/fault seeds before paper-grade claims",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from phase8_synthetic_replay_cases import MANIFEST_PATH, load_manifest_cases  # pylint: disable=import-outside-toplevel

    cases = load_manifest_cases(MANIFEST_PATH)
    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))
    rows = build_rows(cases, runtime_model)
    write_table(rows)
    write_report(rows, MANIFEST_PATH)
    if not all(bool(row["parity_pass"]) for row in rows):
        raise AssertionError("Phase9 synthetic matched baseline comparison parity failed")
    if any(
        (int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0)
        and row["family"] != "pibt_active_bag_replay"
        for row in rows
    ):
        raise AssertionError("Phase9 synthetic matched baseline comparison produced non-PIBT post-shield conflicts")
    print(
        "phase9_synthetic_matched_baseline_comparison "
        f"rows={len(rows)} scenarios={len(cases)} families={len(SUMMARY_FIELDS_BY_FAMILY)}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
