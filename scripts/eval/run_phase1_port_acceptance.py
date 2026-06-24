from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
import sys
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MAP2_PATH = ROOT / "legacy" / "jichang_origin_readonly" / "map2.txt"
EXAMPLE1_PATH = ROOT / "legacy" / "jichang_origin_readonly" / "example1" / "map.txt"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase1_python_cpp_port_report.md"
PARITY_TABLE = ROOT / "outputs" / "tables" / "phase1_parity_cases.csv"
SPEED_TABLE = ROOT / "outputs" / "tables" / "phase1_speed_benchmark.csv"

PYTHON_REPEATS = 100
CPP_REPEATS = 100

PARITY_FIELDS = [
    "fixture",
    "start",
    "goal",
    "python_path",
    "cpp_path",
    "path_length",
    "strict_parity_pass",
    "notes",
]
SPEED_FIELDS = [
    "fixture",
    "runtime",
    "repeats",
    "case_count",
    "total_plans",
    "elapsed_seconds",
    "plans_per_second",
    "checksum",
]


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _path_locations(route: list[Any]) -> list[int]:
    return [int(node.location) for node in route]


def _parity_row(
    fixture: str,
    start: int,
    goal: int,
    python_path: list[int],
    cpp_path: list[int],
    notes: str,
) -> dict[str, Any]:
    return {
        "fixture": fixture,
        "start": start,
        "goal": goal,
        "python_path": json.dumps(python_path),
        "cpp_path": json.dumps(cpp_path),
        "path_length": len(python_path),
        "strict_parity_pass": python_path == cpp_path,
        "notes": notes,
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _speed_row(
    fixture: str,
    runtime: str,
    repeats: int,
    case_count: int,
    elapsed_seconds: float,
    checksum: int,
) -> dict[str, Any]:
    total_plans = repeats * case_count
    return {
        "fixture": fixture,
        "runtime": runtime,
        "repeats": repeats,
        "case_count": case_count,
        "total_plans": total_plans,
        "elapsed_seconds": f"{elapsed_seconds:.9f}",
        "plans_per_second": f"{(total_plans / elapsed_seconds) if elapsed_seconds > 0.0 else 0.0:.6f}",
        "checksum": checksum,
    }


def build_outputs() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    _prepare_imports()

    from czr005 import cpp_backend  # pylint: disable=import-outside-toplevel
    from czr005.io.legacy_map import parse_legacy_map  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import AStarPlanner, IcsGraph  # pylint: disable=import-outside-toplevel

    map2 = parse_legacy_map(MAP2_PATH)
    map2_graph = IcsGraph.from_legacy_map(map2)
    map2_planner = AStarPlanner(map2_graph)
    map2_cases = [(start, goal) for start in sorted(map2_graph.start_nodes) for goal in sorted(map2_graph.end_nodes)]
    map2_cpp_routes = cpp_backend.plan_legacy_map_paths(MAP2_PATH, map2_cases)

    parity_rows: list[dict[str, Any]] = []
    for (start, goal), cpp_path in zip(map2_cases, map2_cpp_routes):
        python_path = _path_locations(map2_planner.plan(start, goal))
        parity_rows.append(
            _parity_row(
                "map2_start_end",
                start,
                goal,
                python_path,
                cpp_path,
                "all map2 start/end A* cases",
            )
        )

    example1 = parse_legacy_map(EXAMPLE1_PATH, allow_ragged_heuristic=True)
    example1_graph = IcsGraph.from_legacy_map(example1)
    example1_planner = AStarPlanner(example1_graph)
    example1_cases = [(start, 9) for start in [0, 1, 2, 3, 4, 5, 6, 7, 8, 10]]
    example1_cpp_routes = cpp_backend.plan_legacy_map_paths(
        EXAMPLE1_PATH,
        example1_cases,
        allow_ragged_heuristic=True,
    )
    for (start, goal), cpp_path in zip(example1_cases, example1_cpp_routes):
        python_path = _path_locations(example1_planner.plan(start, goal))
        parity_rows.append(
            _parity_row(
                "legacy_example1_ragged_heuristic",
                start,
                goal,
                python_path,
                cpp_path,
                "Java-compatible ragged heuristic fixture",
            )
        )

    checksum = 0
    python_start = perf_counter()
    for _ in range(PYTHON_REPEATS):
        for start, goal in map2_cases:
            checksum += len(map2_planner.plan(start, goal))
    python_elapsed = perf_counter() - python_start
    cpp_benchmark = cpp_backend.benchmark_legacy_map_paths(MAP2_PATH, map2_cases, CPP_REPEATS)
    speed_rows = [
        _speed_row(
            "map2_start_end",
            "python_reference_astar",
            PYTHON_REPEATS,
            len(map2_cases),
            python_elapsed,
            checksum,
        ),
        {
            "fixture": "map2_start_end",
            "runtime": "cpp_pybind_astar",
            "repeats": int(cpp_benchmark["repeats"]),
            "case_count": int(cpp_benchmark["case_count"]),
            "total_plans": int(cpp_benchmark["total_plans"]),
            "elapsed_seconds": f"{float(cpp_benchmark['elapsed_seconds']):.9f}",
            "plans_per_second": f"{float(cpp_benchmark['plans_per_second']):.6f}",
            "checksum": int(cpp_benchmark["checksum"]),
        },
    ]

    metadata = {
        "map2_cases": len(map2_cases),
        "example1_cases": len(example1_cases),
        "strict_parity_pass": all(bool(row["strict_parity_pass"]) for row in parity_rows),
        "python_speed": speed_rows[0],
        "cpp_speed": speed_rows[1],
    }
    return parity_rows, speed_rows, metadata


def write_report(
    parity_rows: list[dict[str, Any]],
    speed_rows: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pass_count = sum(1 for row in parity_rows if bool(row["strict_parity_pass"]))
    speedup = 0.0
    python_rate = float(speed_rows[0]["plans_per_second"])
    cpp_rate = float(speed_rows[1]["plans_per_second"])
    if python_rate > 0.0:
        speedup = cpp_rate / python_rate

    lines = [
        "# Phase1 Python/C++ Port Acceptance Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This non-learning acceptance report consolidates the Phase1 Python reference and C++ pybind "
            "port evidence requested by the master plan. It covers legacy parser/A* parity for `map2`, "
            "the Java-compatible ragged `example1` map fixture, and a repeated A* speed smoke."
        ),
        "",
        f"- parity table: `{PARITY_TABLE.relative_to(ROOT).as_posix()}`",
        f"- speed table: `{SPEED_TABLE.relative_to(ROOT).as_posix()}`",
        "",
        "## Parity",
        "",
        f"- map2 start/end cases: {metadata['map2_cases']}",
        f"- legacy example1 cases: {metadata['example1_cases']}",
        f"- exact Python/C++ path matches: {pass_count} / {len(parity_rows)}",
        "",
        "## Speed Smoke",
        "",
        "| Runtime | Repeats | Total plans | Elapsed seconds | Plans/second | Checksum |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in speed_rows:
        lines.append(
            f"| {row['runtime']} | {row['repeats']} | {row['total_plans']} | "
            f"{row['elapsed_seconds']} | {row['plans_per_second']} | {row['checksum']} |"
        )
    lines.extend(
        [
            "",
            f"C++/Python planner throughput ratio on this local smoke: {speedup:.3f}x.",
            "",
            "## Gate Status",
            "",
            f"Phase1 Python/C++ port acceptance gate is {'PASS' if metadata['strict_parity_pass'] else 'FAIL'}.",
            "",
            "This report intentionally excludes teacher data, BC, RL, and other learning stages.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parity_rows, speed_rows, metadata = build_outputs()
    _write_csv(PARITY_TABLE, PARITY_FIELDS, parity_rows)
    _write_csv(SPEED_TABLE, SPEED_FIELDS, speed_rows)
    write_report(parity_rows, speed_rows, metadata)
    print(
        f"phase1_parity_rows={len(parity_rows)} "
        f"strict_parity_pass={metadata['strict_parity_pass']} "
        f"speed_rows={len(speed_rows)}"
    )
    if not metadata["strict_parity_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
