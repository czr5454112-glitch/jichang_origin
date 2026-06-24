from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
import subprocess
import sys
from typing import Any

import run_java_cpp_legacy_window_performance as base


DEFAULT_SCHEDULE = "8268:3:16:fault;8300:3:16:repair"
JAVA_ROUTE_TABLE = base.ROOT / "outputs" / "tables" / "java_legacy_scheduled_fault_window_routes.csv"
JAVA_SUMMARY_TABLE = base.ROOT / "outputs" / "tables" / "java_legacy_scheduled_fault_window_summary.csv"
CPP_ROUTE_TABLE = base.ROOT / "outputs" / "tables" / "cpp_legacy_scheduled_fault_window_routes.csv"
PARITY_TABLE = base.ROOT / "outputs" / "tables" / "java_cpp_legacy_scheduled_fault_window_route_parity.csv"
PERFORMANCE_TABLE = base.ROOT / "outputs" / "tables" / "java_cpp_legacy_scheduled_fault_window_performance.csv"
REPORT_PATH = base.ROOT / "outputs" / "reports" / "java_cpp_legacy_scheduled_fault_window_performance_report.md"

SUMMARY_FIELDS = (
    *base.SUMMARY_FIELDS,
    "fault_event_count",
    "repair_event_count",
    "active_fault_count",
)


def _parse_schedule(spec: str) -> list[tuple[int, int, int, bool]]:
    if not spec.strip() or spec.strip().lower() == "none":
        return []
    events: list[tuple[int, int, int, bool]] = []
    for chunk in spec.split(";"):
        if not chunk.strip():
            continue
        parts = [part.strip() for part in chunk.split(":")]
        if len(parts) != 4:
            raise ValueError(f"invalid schedule event: {chunk}")
        action = parts[3].lower()
        if action in {"repair", "repaired"}:
            repair = True
        elif action in {"fault", "fail"}:
            repair = False
        else:
            raise ValueError(f"invalid schedule action: {parts[3]}")
        events.append((int(parts[0]), int(parts[1]), int(parts[2]), repair))
    return events


def _run_java(
    *,
    start_epoch: int,
    max_epochs: int,
    max_new_tasks: int,
    repeats: int,
    warmup_repeats: int,
    schedule_spec: str,
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
        schedule_spec,
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
        "runtime": "legacy_java_ics_scheduled_fault_window",
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
    fault_schedule: list[tuple[int, int, int, bool]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from czr005 import cpp_backend  # pylint: disable=import-outside-toplevel

    for _ in range(warmup_repeats):
        cpp_backend.legacy_scheduled_fault_window_summary(
            base.MAP2_PATH,
            base.INPUTDATA_PATH,
            start_epoch=start_epoch,
            max_epochs=max_epochs,
            max_new_tasks=max_new_tasks,
            fault_schedule=fault_schedule,
            include_routes=False,
            search_path=cpp_python_path,
        )

    runs: list[dict[str, Any]] = []
    first_routes: list[dict[str, Any]] = []
    for repeat in range(repeats):
        run = cpp_backend.legacy_scheduled_fault_window_summary(
            base.MAP2_PATH,
            base.INPUTDATA_PATH,
            start_epoch=start_epoch,
            max_epochs=max_epochs,
            max_new_tasks=max_new_tasks,
            fault_schedule=fault_schedule,
            include_routes=repeat == 0,
            search_path=cpp_python_path,
        )
        runs.append(run)
        if repeat == 0:
            first_routes = [dict(row) for row in run["planned_routes"]]

    first = runs[0]
    elapsed = sum(float(row["elapsed_seconds"]) for row in runs)
    planned_count = int(first["planned_count"])
    row = {
        "runtime": "cpp_pybind_legacy_scheduled_fault_window",
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
    schedule_spec: str,
    start_epoch: int,
    max_epochs: int,
    max_new_tasks: int,
    cpp_python_path: Path,
) -> None:
    java = next(row for row in rows if row["runtime"] == "legacy_java_ics_scheduled_fault_window")
    cpp = next(row for row in rows if row["runtime"] == "cpp_pybind_legacy_scheduled_fault_window")
    summary_match = _summary_parity(java, cpp)
    route_match = all(bool(row["match"]) for row in route_parity_rows)
    speedup = float(cpp["plans_per_second"]) / float(java["plans_per_second"])
    performance_gate = speedup >= 1.0

    lines = [
        "# Java / C++ Legacy Scheduled Fault Window Performance",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This benchmark compares the read-only legacy Java `ICS_PathFinding` scheduler against "
            "the native C++ port on a deterministic fault/repair window. The schedule is injected "
            "through an external Java harness by toggling in-memory edge fault states before the "
            "legacy `Tasks.generate_tasks` call; no legacy source file is modified. The default "
            "schedule faults the first active route after it has been planned, then repairs the edge."
        ),
        "",
        f"- map: `{base.MAP2_PATH.relative_to(base.ROOT).as_posix()}`",
        f"- tasks: `{base.INPUTDATA_PATH.relative_to(base.ROOT).as_posix()}`",
        f"- schedule: `{schedule_spec}`",
        f"- start epoch: `{start_epoch}`",
        f"- max epochs: `{max_epochs}`",
        f"- max generated tasks: `{max_new_tasks}`",
        f"- C++ pybind path: `{cpp_python_path}`",
        "",
        "## Metrics",
        "",
        (
            "| Runtime | Repeats | Elapsed seconds | Windows/s | Plans/s | Generated | Planned | "
            "Completed | Fault events | Repair events | Active faults | Route checksum |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {runtime} | {repeats} | {elapsed_seconds:.6f} | {windows_per_second:.4f} | "
            "{plans_per_second:.4f} | {generated_count} | {planned_count} | {completed_count} | "
            "{fault_event_count} | {repair_event_count} | {active_fault_count} | "
            "{route_location_checksum} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"C++/Java scheduled fault-window planner throughput ratio: `{speedup:.3f}x`.",
            "",
            f"Performance CSV: `{PERFORMANCE_TABLE.relative_to(base.ROOT).as_posix()}`",
            f"Route parity CSV: `{PARITY_TABLE.relative_to(base.ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- Java/C++ scheduled fault summary parity: PASS"
            if summary_match
            else "- Java/C++ scheduled fault summary parity: FAIL",
            "- Java/C++ scheduled fault planned route multiset parity: PASS"
            if route_match
            else "- Java/C++ scheduled fault planned route multiset parity: FAIL",
            "- C++ scheduled fault window is not slower than legacy Java: PASS"
            if performance_gate
            else "- C++ scheduled fault window is not slower than legacy Java: FAIL",
            "",
            "## Boundary",
            "",
            (
                "This covers deterministic fault activation and repair propagation through the "
                "legacy task-generation/path-finding loop, including the active-route first-edge "
                "`Handling_faults` branch. It does not yet cover random fault sampling or the "
                "Swing GUI repaint/sleep loop."
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
    parser.add_argument("--schedule", default=DEFAULT_SCHEDULE)
    parser.add_argument("--cpp-python-path", type=Path, default=base.DEFAULT_CPP_PYTHON_PATH)
    args = parser.parse_args()

    if args.repeats <= 0:
        raise ValueError("--repeats must be positive")

    fault_schedule = _parse_schedule(args.schedule)
    base._prepare_imports(args.cpp_python_path)  # pylint: disable=protected-access
    java_row = _run_java(
        start_epoch=args.start_epoch,
        max_epochs=args.max_epochs,
        max_new_tasks=args.max_new_tasks,
        repeats=args.repeats,
        warmup_repeats=args.java_warmup_repeats,
        schedule_spec=args.schedule,
    )
    cpp_row, cpp_routes = _run_cpp(
        start_epoch=args.start_epoch,
        max_epochs=args.max_epochs,
        max_new_tasks=args.max_new_tasks,
        repeats=args.repeats,
        warmup_repeats=args.cpp_warmup_repeats,
        cpp_python_path=args.cpp_python_path,
        fault_schedule=fault_schedule,
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
        schedule_spec=args.schedule,
        start_epoch=args.start_epoch,
        max_epochs=args.max_epochs,
        max_new_tasks=args.max_new_tasks,
        cpp_python_path=args.cpp_python_path,
    )

    summary_match = _summary_parity(java_row, cpp_row)
    route_match = all(bool(row["match"]) for row in route_parity_rows)
    speedup = float(cpp_row["plans_per_second"]) / float(java_row["plans_per_second"])
    if not summary_match:
        raise AssertionError("Java/C++ scheduled fault summary parity failed")
    if not route_match:
        raise AssertionError("Java/C++ scheduled fault planned route parity failed")
    if speedup < 1.0:
        raise AssertionError("C++ scheduled fault window is slower than Java")

    print(
        "java_cpp_legacy_scheduled_fault_window "
        f"generated={java_row['generated_count']} planned={java_row['planned_count']} "
        f"faults={java_row['fault_event_count']} repairs={java_row['repair_event_count']} "
        f"speedup={speedup:.3f} summary_parity={summary_match} route_parity={route_match}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
