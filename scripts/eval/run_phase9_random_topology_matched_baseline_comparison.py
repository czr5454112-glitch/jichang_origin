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
TABLE_PATH = ROOT / "outputs" / "tables" / "phase9_random_topology_matched_baseline_comparison.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase9_random_topology_matched_baseline_comparison_report.md"


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


@dataclass(frozen=True)
class MatchedSpec:
    name: str
    seed: int
    task_count: int
    spacing: float
    fault_edges: tuple[tuple[int, int], ...]
    fault_windows: tuple[tuple[int, int, float, float], ...]
    node_capacities: tuple[tuple[int, int], ...]
    merge_groups: tuple[tuple[int, int, int], ...]
    merge_capacity: int
    merge_headway_seconds: float


@dataclass(frozen=True)
class MatchedCase:
    spec: MatchedSpec
    node_records: tuple[Any, ...]
    edge_records: tuple[Any, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    task_records: tuple[Any, ...]
    layers: str
    source_mode: str
    goal_mode: str
    branch_probability: float
    shortcut_probability: float
    source_histogram: str
    goal_histogram: str


def _layers_label(layers: tuple[int, ...]) -> str:
    return "-".join(str(width) for width in layers)


def _histogram(task_records: tuple[Any, ...], index: int) -> str:
    counts: dict[int, int] = {}
    for record in task_records:
        key = int(record[index])
        counts[key] = counts.get(key, 0) + 1
    return ";".join(f"{key}:{counts[key]}" for key in sorted(counts))


def _adapt_case(case: Any) -> MatchedCase:
    spec = MatchedSpec(
        name=case.spec.name,
        seed=case.spec.seed,
        task_count=case.spec.task_count,
        spacing=case.spec.spacing,
        fault_edges=case.fault_edges,
        fault_windows=case.fault_windows,
        node_capacities=case.node_capacities,
        merge_groups=case.merge_groups,
        merge_capacity=case.merge_capacity,
        merge_headway_seconds=case.merge_headway_seconds,
    )
    return MatchedCase(
        spec=spec,
        node_records=case.node_records,
        edge_records=case.edge_records,
        heuristic_time=case.heuristic_time,
        task_records=case.task_records,
        layers=_layers_label(case.spec.layers),
        source_mode=case.spec.source_mode,
        goal_mode=case.spec.goal_mode,
        branch_probability=case.spec.branch_probability,
        shortcut_probability=case.spec.shortcut_probability,
        source_histogram=_histogram(case.task_records, 5),
        goal_histogram=_histogram(case.task_records, 6),
    )


def _build_rows(cases: tuple[Any, ...], runtime_model: Any) -> list[dict[str, float | int | str | bool]]:
    import run_phase9_random_topology_pibt_stress_sweep as random_topology
    import run_phase9_synthetic_matched_baseline_comparison as synthetic_matched

    rows: list[dict[str, float | int | str | bool]] = []
    for original_case in cases:
        case = _adapt_case(original_case)
        inputs = synthetic_matched.RuntimeInputs(
            graph=random_topology._graph_from_case(original_case),  # pylint: disable=protected-access
            tasks=random_topology._tasks_from_case(original_case),  # pylint: disable=protected-access
            node_records=case.node_records,
            edge_records=case.edge_records,
            heuristic_time=case.heuristic_time,
            task_records=case.task_records,
            runtime_model=runtime_model,
        )
        for family, python_summary, python_elapsed, cpp_summary, cpp_elapsed in synthetic_matched._family_payloads(  # pylint: disable=protected-access
            inputs,
            case,
        ):
            row = synthetic_matched._row(  # pylint: disable=protected-access
                case,
                family,
                python_summary,
                python_elapsed,
                cpp_summary,
                cpp_elapsed,
            )
            row.update(
                {
                    "layers": case.layers,
                    "source_mode": case.source_mode,
                    "goal_mode": case.goal_mode,
                    "branch_probability": case.branch_probability,
                    "shortcut_probability": case.shortcut_probability,
                    "source_histogram": case.source_histogram,
                    "goal_histogram": case.goal_histogram,
                    "notes": (
                        "random DAG-like synthetic topology; "
                        f"layers={case.layers}; source_mode={case.source_mode}; "
                        f"goal_mode={case.goal_mode}; sources={case.source_histogram}; goals={case.goal_histogram}"
                    ),
                }
            )
            rows.append(row)
    return rows


def _fieldnames() -> list[str]:
    import run_phase9_synthetic_matched_baseline_comparison as synthetic_matched

    extras = [
        "layers",
        "source_mode",
        "goal_mode",
        "branch_probability",
        "shortcut_probability",
        "source_histogram",
        "goal_histogram",
    ]
    return list(synthetic_matched.ROW_FIELDS) + extras


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_fieldnames())
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
    scenarios = sorted({str(row["scenario"]) for row in rows})
    families = sorted({str(row["family"]) for row in rows})
    layer_layouts = sorted({str(row["layers"]) for row in rows})
    speedups = [float(row["cpp_speedup"]) for row in rows if float(row["cpp_speedup"]) > 0.0]
    lines = [
        "# Phase9 Random Topology Matched Baseline Comparison",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic reruns the main Python/C++ baseline and event families on generated "
            "random DAG-like ICS topologies. It reuses the Phase9 random-topology case generator "
            "but expands coverage beyond PIBT-only stress to rolling-horizon SIPP, periodic "
            "replanning SIPP, PIBT active-bag replay, EdgeScore event replay, and fallback event replay."
        ),
        "",
        f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "These are synthetic topology/task-source stress rows, not separate real airport maps.",
        "",
        "## Matched Rows",
        "",
        (
            "| Scenario | Layers | Family | Tasks | Edges | Faults | Config | Py/C++ planned | "
            "Py/C++ active steps | Py/C++ conflicts | Mean diff | C++ speedup | Parity |"
        ),
        "|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {scenario} | {layers} | {family} | {task_count} | {edge_count} | {fault_edges} {fault_windows} | "
            "{config_label} | {python_planned}/{cpp_planned} | {python_active_steps}/{cpp_active_steps} | "
            "{python_conflicts}/{cpp_conflicts} | {mean_travel_abs_diff:.12f} | {cpp_speedup:.3f} | "
            "{parity_pass} |".format(**{**row, "config_label": _config_label(row)})
        )
    lines.extend(
        [
            "",
            "## Gate Status",
            "",
            f"- random topology scenarios: `{len(scenarios)}` ({', '.join(scenarios)})",
            f"- distinct layer layouts: `{len(layer_layouts)}` ({', '.join(layer_layouts)})",
            f"- families: `{len(families)}` ({', '.join(families)})",
            f"- matched rows: `{len(rows)}`",
            "- random topology matched Python/C++ summary parity: PASS"
            if parity_pass
            else "- random topology matched Python/C++ summary parity: FAIL",
            "- random topology matched post-shield safety: PASS"
            if safety_pass
            else "- random topology matched post-shield safety: FAIL",
            f"- median C++ local-call speedup: `{_median(speedups):.3f}x`",
            "- real heldout airport map: not covered",
            "",
            "## Remaining Work",
            "",
            "- add a separate real heldout airport map when fixture data is available",
            "- expand timing to multi-machine hardware-normalized runs before paper-grade claims",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    import run_phase9_random_topology_pibt_stress_sweep as random_topology
    import run_phase9_synthetic_matched_baseline_comparison as synthetic_matched

    cases = tuple(random_topology._build_case(spec) for spec in random_topology._case_specs())  # pylint: disable=protected-access
    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(synthetic_matched.MODEL_PATH))
    rows = _build_rows(cases, runtime_model)
    write_table(rows)
    write_report(rows)
    if not all(bool(row["parity_pass"]) for row in rows):
        raise AssertionError("Phase9 random topology matched baseline comparison parity failed")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("Phase9 random topology matched baseline comparison produced post-shield conflicts")
    print(
        "phase9_random_topology_matched_baseline_comparison "
        f"rows={len(rows)} scenarios={len(cases)} families={len(synthetic_matched.SUMMARY_FIELDS_BY_FAMILY)}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
