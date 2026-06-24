from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
MAP2_PATH = LEGACY / "map2.txt"
INPUTDATA_PATH = LEGACY / "inputdata.txt"
JAVA_BENCHMARK = ROOT / "benchmarks" / "java" / "LegacyIcsNoFaultWindowBenchmark.java"
JAVA_BUILD_DIR = ROOT / "build" / "java_bench"
JAVA_WORK_DIR = ROOT / "build" / "java_legacy_window_work"
DEFAULT_CPP_PYTHON_PATH = ROOT / "build_vs" / "python" / "Release"

JAVA_ROUTE_TABLE = ROOT / "outputs" / "tables" / "java_legacy_window_routes.csv"
JAVA_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "java_legacy_window_summary.csv"
CPP_ROUTE_TABLE = ROOT / "outputs" / "tables" / "cpp_legacy_window_routes.csv"
PARITY_TABLE = ROOT / "outputs" / "tables" / "java_cpp_legacy_window_route_parity.csv"
PERFORMANCE_TABLE = ROOT / "outputs" / "tables" / "java_cpp_legacy_window_performance.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "java_cpp_legacy_window_performance_report.md"

SUMMARY_FIELDS = (
    "start_epoch",
    "max_epochs",
    "max_new_tasks",
    "epochs_run",
    "generated_count",
    "planned_count",
    "completed_count",
    "active_route_count",
    "unfinished_count",
    "route_size_checksum",
    "route_location_checksum",
    "last_epoch",
)


def _prepare_imports(cpp_python_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(cpp_python_path))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _compile_java() -> None:
    JAVA_BUILD_DIR.mkdir(parents=True, exist_ok=True)
    java_sources = [
        *sorted((LEGACY / "src" / "App").glob("*.java")),
        LEGACY / "src" / "ICS_GUI" / "ICS_GUI.java",
        JAVA_BENCHMARK,
    ]
    command = [
        "javac",
        "-encoding",
        "UTF-8",
        "-d",
        str(JAVA_BUILD_DIR),
        *[str(path) for path in java_sources],
    ]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)


def _parse_key_values(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _run_java(
    *,
    start_epoch: int,
    max_epochs: int,
    max_new_tasks: int,
    repeats: int,
    warmup_repeats: int,
) -> dict[str, Any]:
    _compile_java()
    JAVA_WORK_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        "java",
        "-Djava.awt.headless=true",
        "-cp",
        str(JAVA_BUILD_DIR),
        "LegacyIcsNoFaultWindowBenchmark",
        str(MAP2_PATH),
        str(INPUTDATA_PATH),
        str(start_epoch),
        str(max_epochs),
        str(max_new_tasks),
        str(repeats),
        str(warmup_repeats),
        str(JAVA_ROUTE_TABLE),
        str(JAVA_SUMMARY_TABLE),
    ]
    completed = subprocess.run(
        command,
        cwd=JAVA_WORK_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = _parse_key_values(completed.stdout)
    return {
        "runtime": "legacy_java_ics_no_fault_window",
        "repeats": int(parsed["repeats"]),
        "warmup_repeats": int(parsed["warmup_repeats"]),
        "elapsed_seconds": float(parsed["elapsed_seconds"]),
        "windows_per_second": float(parsed["windows_per_second"]),
        "plans_per_second": float(parsed["plans_per_second"]),
        **{field: _coerce_summary_value(field, parsed[field]) for field in SUMMARY_FIELDS},
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
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from czr005 import cpp_backend  # pylint: disable=import-outside-toplevel

    for _ in range(warmup_repeats):
        cpp_backend.legacy_no_fault_window_summary(
            MAP2_PATH,
            INPUTDATA_PATH,
            start_epoch=start_epoch,
            max_epochs=max_epochs,
            max_new_tasks=max_new_tasks,
            include_routes=False,
            search_path=cpp_python_path,
        )

    runs: list[dict[str, Any]] = []
    first_routes: list[dict[str, Any]] = []
    for repeat in range(repeats):
        run = cpp_backend.legacy_no_fault_window_summary(
            MAP2_PATH,
            INPUTDATA_PATH,
            start_epoch=start_epoch,
            max_epochs=max_epochs,
            max_new_tasks=max_new_tasks,
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
        "runtime": "cpp_pybind_legacy_no_fault_window",
        "repeats": repeats,
        "warmup_repeats": warmup_repeats,
        "elapsed_seconds": elapsed,
        "windows_per_second": repeats / elapsed if elapsed > 0.0 else 0.0,
        "plans_per_second": (planned_count * repeats) / elapsed if elapsed > 0.0 else 0.0,
        **{field: _coerce_summary_value(field, first[field]) for field in SUMMARY_FIELDS},
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
    _write_csv(
        CPP_ROUTE_TABLE,
        ["ordinal", "task_id", "start", "goal", "epoch", "finish_time", "path"],
        route_rows,
    )
    return row, route_rows


def _coerce_summary_value(field: str, value: Any) -> int | float:
    if field == "last_epoch":
        return float(value)
    return int(value)


def _read_java_routes() -> list[dict[str, Any]]:
    with JAVA_ROUTE_TABLE.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _route_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(int(row["task_id"])),
            str(int(row["start"])),
            str(int(row["goal"])),
            f"{float(row['epoch']):.6f}",
            str(row["path"]),
        ]
    )


def _build_route_parity_rows(
    java_routes: list[dict[str, Any]],
    cpp_routes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    java_counter = Counter(_route_key(row) for row in java_routes)
    cpp_counter = Counter(_route_key(row) for row in cpp_routes)
    rows: list[dict[str, Any]] = []
    for route_key in sorted(set(java_counter) | set(cpp_counter)):
        java_count = java_counter[route_key]
        cpp_count = cpp_counter[route_key]
        rows.append(
            {
                "route_key": route_key,
                "java_count": java_count,
                "cpp_count": cpp_count,
                "match": java_count == cpp_count,
            }
        )
    return rows


def _summary_parity(java_row: dict[str, Any], cpp_row: dict[str, Any]) -> bool:
    return all(java_row[field] == cpp_row[field] for field in SUMMARY_FIELDS)


def _format_perf_row(row: dict[str, Any]) -> dict[str, Any]:
    formatted = dict(row)
    formatted["elapsed_seconds"] = f"{float(row['elapsed_seconds']):.9f}"
    formatted["windows_per_second"] = f"{float(row['windows_per_second']):.6f}"
    formatted["plans_per_second"] = f"{float(row['plans_per_second']):.6f}"
    formatted["last_epoch"] = f"{float(row['last_epoch']):.6f}"
    return formatted


def _write_report(
    rows: list[dict[str, Any]],
    route_parity_rows: list[dict[str, Any]],
    *,
    start_epoch: int,
    max_epochs: int,
    max_new_tasks: int,
    cpp_python_path: Path,
) -> None:
    java = next(row for row in rows if row["runtime"] == "legacy_java_ics_no_fault_window")
    cpp = next(row for row in rows if row["runtime"] == "cpp_pybind_legacy_no_fault_window")
    summary_match = _summary_parity(java, cpp)
    route_match = all(bool(row["match"]) for row in route_parity_rows)
    speedup = float(cpp["plans_per_second"]) / float(java["plans_per_second"])
    performance_gate = speedup >= 1.0

    lines = [
        "# Java / C++ Legacy No-Fault Window Performance",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This benchmark compares the read-only legacy Java `ICS_PathFinding` no-fault "
            "headless scheduling window against the native C++ port on the same `map2.txt` "
            "and `inputdata.txt` task stream. GUI, sockets, random faults, and repair events "
            "are disabled; task generation, active-route advancement, node constraints, "
            "unfinished-task retries, and A* route planning are included."
        ),
        "",
        f"- map: `{MAP2_PATH.relative_to(ROOT).as_posix()}`",
        f"- tasks: `{INPUTDATA_PATH.relative_to(ROOT).as_posix()}`",
        f"- start epoch: `{start_epoch}`",
        f"- max epochs: `{max_epochs}`",
        f"- max generated tasks: `{max_new_tasks}`",
        f"- C++ pybind path: `{cpp_python_path}`",
        "",
        "## Metrics",
        "",
        (
            "| Runtime | Repeats | Elapsed seconds | Windows/s | Plans/s | "
            "Generated | Planned | Completed | Active | Unfinished | Route checksum |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {runtime} | {repeats} | {elapsed_seconds:.6f} | {windows_per_second:.4f} | "
            "{plans_per_second:.4f} | {generated_count} | {planned_count} | {completed_count} | "
            "{active_route_count} | {unfinished_count} | {route_location_checksum} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"C++/Java no-fault window planner throughput ratio: `{speedup:.3f}x`.",
            "",
            f"Performance CSV: `{PERFORMANCE_TABLE.relative_to(ROOT).as_posix()}`",
            f"Route parity CSV: `{PARITY_TABLE.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- Java/C++ summary parity: PASS" if summary_match else "- Java/C++ summary parity: FAIL",
            "- Java/C++ planned route multiset parity: PASS"
            if route_match
            else "- Java/C++ planned route multiset parity: FAIL",
            "- C++ no-fault window is not slower than legacy Java: PASS"
            if performance_gate
            else "- C++ no-fault window is not slower than legacy Java: FAIL",
            "",
            "## Boundary",
            "",
            (
                "This is a deterministic no-fault window of the legacy scheduler. It is stronger "
                "than the isolated A* benchmark because it includes task arrival, active route "
                "progression, constraint rebuilds, retry handling, and Java `ICS_PathFinding` calls. "
                "It still does not cover stochastic fault/repair branches or the Swing GUI loop."
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
    parser.add_argument("--cpp-python-path", type=Path, default=DEFAULT_CPP_PYTHON_PATH)
    args = parser.parse_args()

    if args.repeats <= 0:
        raise ValueError("--repeats must be positive")

    _prepare_imports(args.cpp_python_path)
    java_row = _run_java(
        start_epoch=args.start_epoch,
        max_epochs=args.max_epochs,
        max_new_tasks=args.max_new_tasks,
        repeats=args.repeats,
        warmup_repeats=args.java_warmup_repeats,
    )
    cpp_row, cpp_routes = _run_cpp(
        start_epoch=args.start_epoch,
        max_epochs=args.max_epochs,
        max_new_tasks=args.max_new_tasks,
        repeats=args.repeats,
        warmup_repeats=args.cpp_warmup_repeats,
        cpp_python_path=args.cpp_python_path,
    )
    java_routes = _read_java_routes()
    route_parity_rows = _build_route_parity_rows(java_routes, cpp_routes)
    rows = [java_row, cpp_row]
    _write_csv(PERFORMANCE_TABLE, list(_format_perf_row(rows[0])), [_format_perf_row(row) for row in rows])
    _write_csv(PARITY_TABLE, ["route_key", "java_count", "cpp_count", "match"], route_parity_rows)
    _write_report(
        rows,
        route_parity_rows,
        start_epoch=args.start_epoch,
        max_epochs=args.max_epochs,
        max_new_tasks=args.max_new_tasks,
        cpp_python_path=args.cpp_python_path,
    )

    summary_match = _summary_parity(java_row, cpp_row)
    route_match = all(bool(row["match"]) for row in route_parity_rows)
    speedup = float(cpp_row["plans_per_second"]) / float(java_row["plans_per_second"])
    if not summary_match:
        raise AssertionError("Java/C++ legacy no-fault window summary parity failed")
    if not route_match:
        raise AssertionError("Java/C++ legacy no-fault planned route parity failed")
    if speedup < 1.0:
        raise AssertionError("C++ legacy no-fault window is slower than Java")

    print(
        "java_cpp_legacy_window "
        f"generated={java_row['generated_count']} planned={java_row['planned_count']} "
        f"speedup={speedup:.3f} summary_parity={summary_match} route_parity={route_match}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
