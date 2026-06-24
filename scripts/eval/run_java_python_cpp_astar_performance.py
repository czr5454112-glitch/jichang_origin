from __future__ import annotations

import argparse
import csv
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
MAP2_PATH = LEGACY / "map2.txt"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
JAVA_BENCHMARK = ROOT / "benchmarks" / "java" / "LegacyAstarBenchmark.java"
JAVA_BUILD_DIR = ROOT / "build" / "java_bench"
DEFAULT_CPP_PYTHON_PATH = ROOT / "build_vs" / "python" / "Release"

CASES_TABLE = ROOT / "outputs" / "tables" / "java_python_cpp_astar_cases.csv"
JAVA_PATH_TABLE = ROOT / "outputs" / "tables" / "java_astar_paths.csv"
PERF_TABLE = ROOT / "outputs" / "tables" / "java_python_cpp_astar_performance.csv"
PARITY_TABLE = ROOT / "outputs" / "tables" / "java_python_cpp_astar_path_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "java_python_cpp_astar_performance_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _load_cases(max_cases: int) -> list[tuple[int, int]]:
    cases: list[tuple[int, int]] = []
    with TASK_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if len(cases) >= max_cases:
                break
            record = json.loads(line)
            cases.append((int(record["start"]), int(record["goal"])))
    if not cases:
        raise ValueError("no task cases loaded")
    return cases


def _write_case_table(cases: list[tuple[int, int]]) -> None:
    _write_csv(
        CASES_TABLE,
        ["start", "goal"],
        [{"start": start, "goal": goal} for start, goal in cases],
    )


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


def _run_java_benchmark(repeats: int, warmup_repeats: int) -> dict[str, Any]:
    _compile_java()
    command = [
        "java",
        "-Djava.awt.headless=true",
        "-cp",
        str(JAVA_BUILD_DIR),
        "LegacyAstarBenchmark",
        str(MAP2_PATH),
        str(CASES_TABLE),
        str(repeats),
        str(warmup_repeats),
        str(JAVA_PATH_TABLE),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    parsed = _parse_key_values(completed.stdout)
    return {
        "runtime": "legacy_java_astar",
        "repeats": int(parsed["repeats"]),
        "case_count": int(parsed["case_count"]),
        "total_plans": int(parsed["total_plans"]),
        "elapsed_seconds": float(parsed["elapsed_seconds"]),
        "plans_per_second": float(parsed["plans_per_second"]),
        "checksum": int(parsed["checksum"]),
        "warmup_repeats": int(parsed["warmup_repeats"]),
        "warmup_checksum": int(parsed["warmup_checksum"]),
    }


def _path_locations(route: list[Any]) -> list[int]:
    return [int(node.location) for node in route]


def _run_python_benchmark(cases: list[tuple[int, int]], repeats: int) -> tuple[dict[str, Any], list[list[int]]]:
    from czr005.io.legacy_map import parse_legacy_map  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import AStarPlanner, IcsGraph  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_legacy_map(parse_legacy_map(MAP2_PATH))
    planner = AStarPlanner(graph)
    paths = [_path_locations(planner.plan(start, goal)) for start, goal in cases]

    checksum = 0
    start_time = perf_counter()
    for _ in range(repeats):
        for start, goal in cases:
            checksum += len(planner.plan(start, goal))
    elapsed = perf_counter() - start_time
    return (
        {
            "runtime": "python_reference_astar",
            "repeats": repeats,
            "case_count": len(cases),
            "total_plans": repeats * len(cases),
            "elapsed_seconds": elapsed,
            "plans_per_second": (repeats * len(cases)) / elapsed if elapsed > 0.0 else 0.0,
            "checksum": checksum,
            "warmup_repeats": 0,
            "warmup_checksum": 0,
        },
        paths,
    )


def _run_cpp_benchmark(
    cases: list[tuple[int, int]],
    repeats: int,
    cpp_python_path: Path,
) -> tuple[dict[str, Any], list[list[int]]]:
    from czr005 import cpp_backend  # pylint: disable=import-outside-toplevel

    paths = cpp_backend.plan_legacy_map_paths(MAP2_PATH, cases, search_path=cpp_python_path)
    result = cpp_backend.benchmark_legacy_map_paths(MAP2_PATH, cases, repeats, search_path=cpp_python_path)
    return (
        {
            "runtime": "cpp_pybind_astar",
            "repeats": int(result["repeats"]),
            "case_count": int(result["case_count"]),
            "total_plans": int(result["total_plans"]),
            "elapsed_seconds": float(result["elapsed_seconds"]),
            "plans_per_second": float(result["plans_per_second"]),
            "checksum": int(result["checksum"]),
            "warmup_repeats": 0,
            "warmup_checksum": 0,
        },
        [[int(node) for node in path] for path in paths],
    )


def _read_java_paths() -> list[list[int]]:
    paths: list[list[int]] = []
    with JAVA_PATH_TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            path = row["path"]
            paths.append([int(item) for item in path.split(";") if item])
    return paths


def _path_text(path: list[int]) -> str:
    return ";".join(str(node) for node in path)


def _build_parity_rows(
    cases: list[tuple[int, int]],
    java_paths: list[list[int]],
    python_paths: list[list[int]],
    cpp_paths: list[list[int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, ((start, goal), java_path, python_path, cpp_path) in enumerate(
        zip(cases, java_paths, python_paths, cpp_paths)
    ):
        rows.append(
            {
                "case_index": index,
                "start": start,
                "goal": goal,
                "java_path": _path_text(java_path),
                "python_path": _path_text(python_path),
                "cpp_path": _path_text(cpp_path),
                "java_python_parity": java_path == python_path,
                "java_cpp_parity": java_path == cpp_path,
                "python_cpp_parity": python_path == cpp_path,
            }
        )
    return rows


def _format_perf_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime": row["runtime"],
        "repeats": row["repeats"],
        "case_count": row["case_count"],
        "total_plans": row["total_plans"],
        "elapsed_seconds": f"{float(row['elapsed_seconds']):.9f}",
        "plans_per_second": f"{float(row['plans_per_second']):.6f}",
        "checksum": row["checksum"],
        "warmup_repeats": row["warmup_repeats"],
        "warmup_checksum": row["warmup_checksum"],
    }


def _write_report(
    rows: list[dict[str, Any]],
    parity_rows: list[dict[str, Any]],
    max_cases: int,
    repeats: int,
    warmup_repeats: int,
    cpp_python_path: Path,
) -> None:
    java = next(row for row in rows if row["runtime"] == "legacy_java_astar")
    cpp = next(row for row in rows if row["runtime"] == "cpp_pybind_astar")
    python = next(row for row in rows if row["runtime"] == "python_reference_astar")
    java_cpp_ratio = float(cpp["plans_per_second"]) / float(java["plans_per_second"])
    java_python_ratio = float(python["plans_per_second"]) / float(java["plans_per_second"])
    checksum_match = len({int(row["checksum"]) for row in rows}) == 1
    java_cpp_parity = all(bool(row["java_cpp_parity"]) for row in parity_rows)
    java_python_parity = all(bool(row["java_python_parity"]) for row in parity_rows)
    performance_gate = java_cpp_ratio >= 1.0

    lines = [
        "# Java / Python / C++ A* Performance Baseline",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This benchmark compares the legacy Java `Astar.research` implementation against the "
            "Python reference A* and C++ pybind A* on the same `map2` task-stream `(start, goal)` cases. "
            "It is a headless planner benchmark: GUI, socket, and legacy file-output loops are not included."
        ),
        "",
        f"- map: `{MAP2_PATH.relative_to(ROOT).as_posix()}`",
        f"- task stream: `{TASK_PATH.relative_to(ROOT).as_posix()}`",
        f"- case count: `{max_cases}`",
        f"- measured repeats: `{repeats}`",
        f"- Java warmup repeats: `{warmup_repeats}`",
        f"- C++ pybind path: `{cpp_python_path}`",
        f"- performance table: `{PERF_TABLE.relative_to(ROOT).as_posix()}`",
        f"- path parity table: `{PARITY_TABLE.relative_to(ROOT).as_posix()}`",
        "",
        "## Performance",
        "",
        "| Runtime | Repeats | Total plans | Elapsed seconds | Plans/second | Checksum |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {runtime} | {repeats} | {total_plans} | {elapsed_seconds:.9f} | "
            "{plans_per_second:.6f} | {checksum} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"C++/Java planner throughput ratio: `{java_cpp_ratio:.3f}x`.",
            f"Python/Java planner throughput ratio: `{java_python_ratio:.3f}x`.",
            "",
            "## Function Parity",
            "",
            f"- checksum match across Java/Python/C++: {'PASS' if checksum_match else 'FAIL'}",
            f"- Java/Python exact path parity: {'PASS' if java_python_parity else 'FAIL'}",
            f"- Java/C++ exact path parity: {'PASS' if java_cpp_parity else 'FAIL'}",
            "",
            "## Gate Status",
            "",
            "- functionality matches legacy Java on this benchmark: PASS"
            if checksum_match and java_cpp_parity and java_python_parity
            else "- functionality matches legacy Java on this benchmark: FAIL",
            "- C++ pybind A* is not slower than legacy Java A*: PASS"
            if performance_gate
            else "- C++ pybind A* is not slower than legacy Java A*: FAIL",
            "",
            "## Notes",
            "",
            (
                "This is the first apples-to-apples Java baseline for the port. It covers the "
                "core A* planner path used by the legacy project, not the full Java GUI/event/file-output loop. "
                "Full-system Java simulation timing would require a separate headless Java event harness."
            ),
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare legacy Java, Python, and C++ A* performance.")
    parser.add_argument("--max-cases", type=int, default=8000)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--java-warmup-repeats", type=int, default=3)
    parser.add_argument("--cpp-python-path", type=Path, default=DEFAULT_CPP_PYTHON_PATH)
    args = parser.parse_args()

    _prepare_imports()
    cases = _load_cases(args.max_cases)
    _write_case_table(cases)

    java_row = _run_java_benchmark(args.repeats, args.java_warmup_repeats)
    python_row, python_paths = _run_python_benchmark(cases, args.repeats)
    cpp_row, cpp_paths = _run_cpp_benchmark(cases, args.repeats, args.cpp_python_path)
    java_paths = _read_java_paths()
    parity_rows = _build_parity_rows(cases, java_paths, python_paths, cpp_paths)
    rows = [java_row, python_row, cpp_row]

    _write_csv(
        PERF_TABLE,
        [
            "runtime",
            "repeats",
            "case_count",
            "total_plans",
            "elapsed_seconds",
            "plans_per_second",
            "checksum",
            "warmup_repeats",
            "warmup_checksum",
        ],
        [_format_perf_row(row) for row in rows],
    )
    _write_csv(
        PARITY_TABLE,
        [
            "case_index",
            "start",
            "goal",
            "java_path",
            "python_path",
            "cpp_path",
            "java_python_parity",
            "java_cpp_parity",
            "python_cpp_parity",
        ],
        parity_rows,
    )
    _write_report(rows, parity_rows, len(cases), args.repeats, args.java_warmup_repeats, args.cpp_python_path)

    java_cpp_ratio = float(cpp_row["plans_per_second"]) / float(java_row["plans_per_second"])
    parity_pass = all(bool(row["java_cpp_parity"]) and bool(row["java_python_parity"]) for row in parity_rows)
    checksum_pass = len({int(row["checksum"]) for row in rows}) == 1
    print(
        "java_python_cpp_astar cases={} repeats={} java_cpp_ratio={:.3f} parity_pass={} checksum_pass={}".format(
            len(cases),
            args.repeats,
            java_cpp_ratio,
            parity_pass,
            checksum_pass,
        )
    )
    print(f"report={REPORT_PATH}")
    if not parity_pass or not checksum_pass:
        raise SystemExit(1)
    if java_cpp_ratio < 1.0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
