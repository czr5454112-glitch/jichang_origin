from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUILD_PYTHON = ROOT / "build_nmake" / "python"
PARITY_TABLE = ROOT / "outputs" / "tables" / "phase1e_astar_py_cpp_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase1e_py_cpp_parity_speed_report.md"


def _prepare_imports(build_python: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(build_python))


def _path_locations(route: list[object]) -> list[int]:
    return [int(node.location) for node in route]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase1E Python/C++ A* parity and speed smoke.")
    parser.add_argument("--build-python", type=Path, default=DEFAULT_BUILD_PYTHON)
    parser.add_argument("--python-repeats", type=int, default=100)
    parser.add_argument("--cpp-repeats", type=int, default=100)
    args = parser.parse_args()

    _prepare_imports(args.build_python)

    import czr005_cpp  # pylint: disable=import-error,import-outside-toplevel
    from czr005.io.legacy_map import parse_legacy_map  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import AStarPlanner, IcsGraph  # pylint: disable=import-outside-toplevel

    map_path = ROOT / "legacy" / "jichang_origin_readonly" / "map2.txt"
    graph = IcsGraph.from_legacy_map(parse_legacy_map(map_path))
    planner = AStarPlanner(graph)
    cases = [(start, goal) for start in sorted(graph.start_nodes) for goal in sorted(graph.end_nodes)]

    python_routes: dict[tuple[int, int], list[int]] = {}
    python_start = perf_counter()
    checksum = 0
    for _ in range(args.python_repeats):
      for start, goal in cases:
        route = _path_locations(planner.plan(start, goal))
        checksum += len(route)
        python_routes[(start, goal)] = route
    python_elapsed = perf_counter() - python_start

    cpp_routes_raw = czr005_cpp.plan_legacy_map_paths(str(map_path), cases)
    cpp_routes = {case: [int(value) for value in route] for case, route in zip(cases, cpp_routes_raw)}
    cpp_benchmark = czr005_cpp.benchmark_legacy_map_paths(str(map_path), cases, args.cpp_repeats)

    rows = []
    mismatches = []
    for start, goal in cases:
      py_path = python_routes[(start, goal)]
      cpp_path = cpp_routes[(start, goal)]
      match = py_path == cpp_path
      if not match:
        mismatches.append((start, goal, py_path, cpp_path))
      rows.append(
          {
              "start": start,
              "goal": goal,
              "match": int(match),
              "path_length": len(py_path),
              "python_path": json.dumps(py_path),
              "cpp_path": json.dumps(cpp_path),
          }
      )

    PARITY_TABLE.parent.mkdir(parents=True, exist_ok=True)
    with PARITY_TABLE.open("w", encoding="utf-8", newline="") as handle:
      writer = csv.DictWriter(
          handle,
          fieldnames=["start", "goal", "match", "path_length", "python_path", "cpp_path"],
      )
      writer.writeheader()
      writer.writerows(rows)

    python_total = len(cases) * args.python_repeats
    python_rate = python_total / python_elapsed if python_elapsed > 0 else 0.0
    cpp_elapsed = float(cpp_benchmark["elapsed_seconds"])
    cpp_total = int(cpp_benchmark["total_plans"])
    cpp_rate = float(cpp_benchmark["plans_per_second"])

    report = f"""# Phase1E Python/C++ Parity and Speed Smoke

Date: 2026-06-16

## Scope

This smoke compares the Python reference A* planner and the C++ A* planner exposed through `czr005_cpp` on every `map2.txt` start/end pair:

- starts: {list(sorted(graph.start_nodes))}
- goals: {list(sorted(graph.end_nodes))}
- cases: {len(cases)}

## Parity

- matched cases: {len(cases) - len(mismatches)} / {len(cases)}
- mismatched cases: {len(mismatches)}
- table: `outputs/tables/phase1e_astar_py_cpp_parity.csv`

## Speed Smoke

Both timings parse/load the graph before the timed loop.

| Runtime | Repeats | Total plans | Elapsed seconds | Plans/second |
|---|---:|---:|---:|---:|
| Python reference | {args.python_repeats} | {python_total} | {python_elapsed:.6f} | {python_rate:.2f} |
| C++ pybind core | {args.cpp_repeats} | {cpp_total} | {cpp_elapsed:.6f} | {cpp_rate:.2f} |

Python checksum: {checksum}

C++ checksum: {int(cpp_benchmark["checksum"])}

## Gate Status

Phase1E smoke gate is {"PASS" if not mismatches else "FAIL"} for exact path parity on this case set.
"""
    if mismatches:
      report += "\n## Mismatches\n\n"
      for start, goal, py_path, cpp_path in mismatches:
        report += f"- {start} -> {goal}: Python {py_path}, C++ {cpp_path}\n"

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"cases={len(cases)} mismatches={len(mismatches)}")
    print(f"python_plans_per_second={python_rate:.2f}")
    print(f"cpp_plans_per_second={cpp_rate:.2f}")
    if mismatches:
      raise SystemExit(1)


if __name__ == "__main__":
    main()
