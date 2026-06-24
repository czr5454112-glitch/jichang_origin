from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
import subprocess
from typing import Any

import run_java_cpp_legacy_window_performance as base


JAVA_ROUTE_TABLE = base.ROOT / "outputs" / "tables" / "java_legacy_probability_extreme_window_routes.csv"
JAVA_SUMMARY_TABLE = base.ROOT / "outputs" / "tables" / "java_legacy_probability_extreme_window_summary.csv"
CPP_ROUTE_TABLE = base.ROOT / "outputs" / "tables" / "cpp_legacy_probability_extreme_window_routes.csv"
PARITY_TABLE = base.ROOT / "outputs" / "tables" / "java_cpp_legacy_probability_extreme_window_route_parity.csv"
PERFORMANCE_TABLE = base.ROOT / "outputs" / "tables" / "java_cpp_legacy_probability_extreme_window_performance.csv"
REPORT_PATH = base.ROOT / "outputs" / "reports" / "java_cpp_legacy_probability_extreme_window_performance_report.md"

SUMMARY_FIELDS = (
    *base.SUMMARY_FIELDS,
    "fault_event_count",
    "repair_event_count",
    "generated_fault_edge_count",
    "generated_repair_edge_count",
    "active_fault_count",
)


def _validate_probability(value: float, name: str) -> None:
    if value not in {0.0, 1.0}:
        raise ValueError(f"{name} must be 0.0 or 1.0 for a deterministic parity gate")


def _run_java(
    *,
    start_epoch: int,
    max_epochs: int,
    max_new_tasks: int,
    repeats: int,
    warmup_repeats: int,
    fault_probability: float,
    repair_probability: float,
) -> dict[str, Any]:
    base._compile_java()  # pylint: disable=protected-access
    base.JAVA_WORK_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        "java",
        "-Djava.awt.headless=true",
        "-cp",
        str(base.JAVA_BUILD_DIR),
        "LegacyIcsNoFaultWindowBenchmark",
        str(base.MAP2_PATH),
        str(base.INPUTDATA_PATH),
        str(start_epoch),
        str(max_epochs),
        str(max_new_tasks),
        str(repeats),
        str(warmup_repeats),
        str(JAVA_ROUTE_TABLE),
        str(JAVA_SUMMARY_TABLE),
        "none",
        str(fault_probability),
        str(repair_probability),
    ]
    completed = subprocess.run(
        command,
        cwd=base.JAVA_WORK_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = base._parse_key_values(completed.stdout)  # pylint: disable=protected-access
    return {
        "runtime": "legacy_java_ics_probability_extreme_window",
        "repeats": int(parsed["repeats"]),
        "warmup_repeats": int(parsed["warmup_repeats"]),
        "elapsed_seconds": float(parsed["elapsed_seconds"]),
        "windows_per_second": float(parsed["windows_per_second"]),
        "plans_per_second": float(parsed["plans_per_second"]),
        **{field: base._coerce_summary_value(field, parsed[field]) for field in SUMMARY_FIELDS},  # pylint: disable=protected-access
    }


def _path_text(path: list[int]) -> str:
    return ";".join(str(node) for node in path)


def _run_cpp(
    *,
    start_epoch: int,
    max_epochs: int,
    max_new_tasks: int,
    repeats: int,
    warmup_repeats: int,
    cpp_python_path: Path,
    fault_probability: float,
    repair_probability: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from czr005 import cpp_backend  # pylint: disable=import-outside-toplevel

    for _ in range(warmup_repeats):
        cpp_backend.legacy_no_fault_window_summary(
            base.MAP2_PATH,
            base.INPUTDATA_PATH,
            start_epoch=start_epoch,
            max_epochs=max_epochs,
            max_new_tasks=max_new_tasks,
            include_routes=False,
            fault_probability=fault_probability,
            repair_probability=repair_probability,
            search_path=cpp_python_path,
        )

    runs: list[dict[str, Any]] = []
    first_routes: list[dict[str, Any]] = []
    for repeat in range(repeats):
        run = cpp_backend.legacy_no_fault_window_summary(
            base.MAP2_PATH,
            base.INPUTDATA_PATH,
            start_epoch=start_epoch,
            max_epochs=max_epochs,
            max_new_tasks=max_new_tasks,
            include_routes=repeat == 0,
            fault_probability=fault_probability,
            repair_probability=repair_probability,
            search_path=cpp_python_path,
        )
        runs.append(run)
        if repeat == 0:
            first_routes = [dict(row) for row in run["planned_routes"]]

    first = runs[0]
    elapsed = sum(float(row["elapsed_seconds"]) for row in runs)
    planned_count = int(first["planned_count"])
    row = {
        "runtime": "cpp_pybind_legacy_probability_extreme_window",
        "repeats": repeats,
        "warmup_repeats": warmup_repeats,
        "elapsed_seconds": elapsed,
        "windows_per_second": repeats / elapsed if elapsed > 0.0 else 0.0,
        "plans_per_second": (planned_count * repeats) / elapsed if elapsed > 0.0 else 0.0,
        **{field: base._coerce_summary_value(field, first[field]) for field in SUMMARY_FIELDS},  # pylint: disable=protected-access
    }
    route_rows = [
        {
            "ordinal": int(route["ordinal"]),
            "task_id": int(route["task_id"]),
            "start": int(route["start"]),
            "goal": int(route["goal"]),
            "epoch": f"{float(route['epoch']):.6f}",
            "finish_time": f"{float(route['finish_time']):.6f}",
            "path": _path_text([int(node) for node in route["path"]]),
        }
        for route in first_routes
    ]
    base._write_csv(  # pylint: disable=protected-access
        CPP_ROUTE_TABLE,
        ["ordinal", "task_id", "start", "goal", "epoch", "finish_time", "path"],
        route_rows,
    )
    return row, route_rows


def _read_java_routes() -> list[dict[str, Any]]:
    with JAVA_ROUTE_TABLE.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _summary_parity(java_row: dict[str, Any], cpp_row: dict[str, Any]) -> bool:
    return all(java_row[field] == cpp_row[field] for field in SUMMARY_FIELDS)


def _write_report(
    rows: list[dict[str, Any]],
    route_parity_rows: list[dict[str, Any]],
    *,
    start_epoch: int,
    max_epochs: int,
    max_new_tasks: int,
    fault_probability: float,
    repair_probability: float,
    cpp_python_path: Path,
) -> None:
    java = next(row for row in rows if row["runtime"] == "legacy_java_ics_probability_extreme_window")
    cpp = next(row for row in rows if row["runtime"] == "cpp_pybind_legacy_probability_extreme_window")
    summary_match = _summary_parity(java, cpp)
    route_match = all(bool(row["match"]) for row in route_parity_rows)
    speedup = float(cpp["plans_per_second"]) / float(java["plans_per_second"])
    performance_gate = speedup >= 1.0

    lines = [
        "# Java / C++ Legacy Probability-Extreme Window Performance",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This benchmark compares the read-only legacy Java `Tasks.generate_tasks` probability "
            "branches against the native C++ port using deterministic extreme probabilities. "
            "Only `0.0` and `1.0` are accepted because intermediate Java `Math.random()` outcomes "
            "are not reproducible without modifying the legacy project."
        ),
        "",
        f"- map: `{base.MAP2_PATH.relative_to(base.ROOT).as_posix()}`",
        f"- tasks: `{base.INPUTDATA_PATH.relative_to(base.ROOT).as_posix()}`",
        f"- fault probability: `{fault_probability}`",
        f"- repair probability: `{repair_probability}`",
        f"- start epoch: `{start_epoch}`",
        f"- max epochs: `{max_epochs}`",
        f"- max generated tasks: `{max_new_tasks}`",
        f"- C++ pybind path: `{cpp_python_path}`",
        "",
        "## Metrics",
        "",
        (
            "| Runtime | Repeats | Elapsed seconds | Windows/s | Plans/s | Generated | Planned | "
            "Generated fault edges | Generated repair edges | Active faults | Route checksum |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {runtime} | {repeats} | {elapsed_seconds:.6f} | {windows_per_second:.4f} | "
            "{plans_per_second:.4f} | {generated_count} | {planned_count} | "
            "{generated_fault_edge_count} | {generated_repair_edge_count} | "
            "{active_fault_count} | {route_location_checksum} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"C++/Java probability-extreme window planner throughput ratio: `{speedup:.3f}x`.",
            "",
            f"Performance CSV: `{PERFORMANCE_TABLE.relative_to(base.ROOT).as_posix()}`",
            f"Route parity CSV: `{PARITY_TABLE.relative_to(base.ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- Java/C++ probability-extreme summary parity: PASS"
            if summary_match
            else "- Java/C++ probability-extreme summary parity: FAIL",
            "- Java/C++ probability-extreme planned route multiset parity: PASS"
            if route_match
            else "- Java/C++ probability-extreme planned route multiset parity: FAIL",
            "- C++ probability-extreme window is not slower than legacy Java: PASS"
            if performance_gate
            else "- C++ probability-extreme window is not slower than legacy Java: FAIL",
            "",
            "## Boundary",
            "",
            (
                "This covers deterministic probability extremes in the legacy task generator. "
                "Random intermediate probabilities remain intentionally outside the gate because "
                "the read-only Java project does not expose an injectable random seed."
            ),
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-epoch", type=int, default=8260)
    parser.add_argument("--max-epochs", type=int, default=5000)
    parser.add_argument("--max-new-tasks", type=int, default=64)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--java-warmup-repeats", type=int, default=1)
    parser.add_argument("--cpp-warmup-repeats", type=int, default=1)
    parser.add_argument("--fault-probability", type=float, default=1.0)
    parser.add_argument("--repair-probability", type=float, default=0.0)
    parser.add_argument("--cpp-python-path", type=Path, default=base.DEFAULT_CPP_PYTHON_PATH)
    args = parser.parse_args()

    if args.repeats <= 0:
        raise ValueError("--repeats must be positive")
    _validate_probability(args.fault_probability, "--fault-probability")
    _validate_probability(args.repair_probability, "--repair-probability")

    base._prepare_imports(args.cpp_python_path)  # pylint: disable=protected-access
    java_row = _run_java(
        start_epoch=args.start_epoch,
        max_epochs=args.max_epochs,
        max_new_tasks=args.max_new_tasks,
        repeats=args.repeats,
        warmup_repeats=args.java_warmup_repeats,
        fault_probability=args.fault_probability,
        repair_probability=args.repair_probability,
    )
    cpp_row, cpp_routes = _run_cpp(
        start_epoch=args.start_epoch,
        max_epochs=args.max_epochs,
        max_new_tasks=args.max_new_tasks,
        repeats=args.repeats,
        warmup_repeats=args.cpp_warmup_repeats,
        cpp_python_path=args.cpp_python_path,
        fault_probability=args.fault_probability,
        repair_probability=args.repair_probability,
    )
    java_routes = _read_java_routes()
    route_parity_rows = base._build_route_parity_rows(java_routes, cpp_routes)  # pylint: disable=protected-access
    rows = [java_row, cpp_row]
    base._write_csv(  # pylint: disable=protected-access
        PERFORMANCE_TABLE,
        list(base._format_perf_row(rows[0])),  # pylint: disable=protected-access
        [base._format_perf_row(row) for row in rows],  # pylint: disable=protected-access
    )
    base._write_csv(  # pylint: disable=protected-access
        PARITY_TABLE,
        ["route_key", "java_count", "cpp_count", "match"],
        route_parity_rows,
    )
    _write_report(
        rows,
        route_parity_rows,
        start_epoch=args.start_epoch,
        max_epochs=args.max_epochs,
        max_new_tasks=args.max_new_tasks,
        fault_probability=args.fault_probability,
        repair_probability=args.repair_probability,
        cpp_python_path=args.cpp_python_path,
    )

    summary_match = _summary_parity(java_row, cpp_row)
    route_match = all(bool(row["match"]) for row in route_parity_rows)
    speedup = float(cpp_row["plans_per_second"]) / float(java_row["plans_per_second"])
    if not summary_match:
        raise AssertionError("Java/C++ probability-extreme summary parity failed")
    if not route_match:
        raise AssertionError("Java/C++ probability-extreme planned route parity failed")
    if speedup < 1.0:
        raise AssertionError("C++ probability-extreme window is slower than Java")

    print(
        "java_cpp_legacy_probability_extreme_window "
        f"generated={java_row['generated_count']} planned={java_row['planned_count']} "
        f"fault_edges={java_row['generated_fault_edge_count']} "
        f"repair_edges={java_row['generated_repair_edge_count']} "
        f"speedup={speedup:.3f} summary_parity={summary_match} route_parity={route_match}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
