from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = Path(os.environ.get("CZR005_CPP_PYTHON_PATH", ROOT / "build_nmake" / "python"))
EXAMPLE_DIR = ROOT / "legacy" / "jichang_origin_readonly" / "example1"
MAP_PATH = EXAMPLE_DIR / "map.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase1_legacy_example1_astar_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase1_legacy_example1_astar_parity_report.md"

LEGACY_OUTPUT_ANCHORS = {
    (0, 9): [0, 1, 3, 5, 8, 9],
    (10, 9): [10, 2, 4, 6, 7, 9],
}

FIELDNAMES = [
    "case_id",
    "start",
    "goal",
    "source_count",
    "source_samples",
    "python_path",
    "cpp_path",
    "path_length",
    "strict_parity_pass",
    "legacy_output_anchor_path",
    "legacy_output_anchor_match",
]


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


def _task_index(path: Path) -> int:
    return int(path.stem.removeprefix("task"))


def _add_case(cases: dict[tuple[int, int], set[str]], start: int, goal: int, source: str) -> None:
    if start == goal:
        return
    cases.setdefault((start, goal), set()).add(source)


def _task_route_cases() -> dict[tuple[int, int], set[str]]:
    cases: dict[tuple[int, int], set[str]] = {}
    _add_case(cases, 0, 9, "map_start_end")
    _add_case(cases, 10, 9, "map_start_end")

    for path in sorted(EXAMPLE_DIR.glob("task*.txt"), key=_task_index):
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            continue
        for offset, line in enumerate(lines[1:], start=2):
            parts = line.split()
            source = f"{path.name}:{offset}"
            if len(parts) == 3:
                continue
            if len(parts) == 4:
                _, _, start, goal = (int(value) for value in parts)
                _add_case(cases, start, goal, f"{source}:new_task")
                continue
            if len(parts) >= 7:
                _, _, start, goal, passed_vertex, pass_vertex, _ = parts[:7]
                start_i = int(start)
                goal_i = int(goal)
                passed_i = int(passed_vertex)
                pass_i = int(pass_vertex)
                _add_case(cases, start_i, goal_i, f"{source}:onpath_full")
                _add_case(cases, passed_i, goal_i, f"{source}:onpath_from_passed_vertex")
                _add_case(cases, pass_i, goal_i, f"{source}:onpath_from_pass_vertex")
                continue
            raise ValueError(f"unexpected task row width in {path}:{offset}: {line}")
    return cases


def _path_locations(route: list[Any]) -> list[int]:
    return [int(node.location) for node in route]


def _source_samples(sources: set[str], limit: int = 8) -> str:
    ordered = sorted(sources)
    suffix = "" if len(ordered) <= limit else f";...(+{len(ordered) - limit})"
    return ";".join(ordered[:limit]) + suffix


def _strict_parse_error() -> str:
    from czr005.io.legacy_map import parse_legacy_map

    try:
        parse_legacy_map(MAP_PATH)
    except ValueError as exc:
        return str(exc)
    raise AssertionError("example1 map parsed without Java-compatible ragged heuristic mode")


def build_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-error,import-outside-toplevel
    from czr005.io.legacy_map import parse_legacy_map  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import AStarPlanner, IcsGraph  # pylint: disable=import-outside-toplevel

    strict_error = _strict_parse_error()
    parsed = parse_legacy_map(MAP_PATH, allow_ragged_heuristic=True)
    graph = IcsGraph.from_legacy_map(parsed)
    planner = AStarPlanner(graph)
    cases = _task_route_cases()

    rows: list[dict[str, Any]] = []
    for case_id, (start, goal) in enumerate(sorted(cases), start=1):
        python_path = _path_locations(planner.plan(start, goal))
        cpp_path = [
            int(value)
            for value in czr005_cpp.plan_legacy_map_path(
                str(MAP_PATH),
                start,
                goal,
                allow_ragged_heuristic=True,
            )
        ]
        anchor_path = LEGACY_OUTPUT_ANCHORS.get((start, goal))
        rows.append(
            {
                "case_id": case_id,
                "start": start,
                "goal": goal,
                "source_count": len(cases[(start, goal)]),
                "source_samples": _source_samples(cases[(start, goal)]),
                "python_path": json.dumps(python_path),
                "cpp_path": json.dumps(cpp_path),
                "path_length": len(python_path),
                "strict_parity_pass": python_path == cpp_path,
                "legacy_output_anchor_path": json.dumps(anchor_path) if anchor_path is not None else "",
                "legacy_output_anchor_match": (
                    python_path == anchor_path and cpp_path == anchor_path if anchor_path is not None else ""
                ),
            }
        )

    metadata = {
        "strict_error": strict_error,
        "node_count": parsed.header.node_count,
        "edge_count": len(parsed.edges),
        "start_nodes": parsed.start_nodes,
        "end_nodes": parsed.end_nodes,
        "task_file_count": len(list(EXAMPLE_DIR.glob("task*.txt"))),
        "last_heuristic_row": parsed.heuristic_raw[-1],
    }
    return rows, metadata


def write_table(rows: list[dict[str, Any]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parity_pass_count = sum(1 for row in rows if row["strict_parity_pass"])
    anchor_rows = [row for row in rows if row["legacy_output_anchor_path"]]
    anchor_pass_count = sum(1 for row in anchor_rows if row["legacy_output_anchor_match"])
    gate_pass = parity_pass_count == len(rows) and anchor_pass_count == len(anchor_rows)

    lines = [
        "# Phase1 Legacy Example1 A* Parity Diagnostic",
        "",
        "## Scope",
        "",
        (
            "This non-learning diagnostic checks the Python reference A* planner and the C++ pybind A* planner "
            "on the legacy `example1` topology. The map has a ragged final heuristic row that Java accepts by "
            "leaving the missing double-array cell at `0.0`; the Python and C++ parsers keep strict mode by "
            "default and require an explicit Java-compatible flag for this fixture."
        ),
        "",
        f"- map: `{MAP_PATH.relative_to(ROOT).as_posix()}`",
        f"- task snapshots: {metadata['task_file_count']}",
        f"- nodes: {metadata['node_count']}",
        f"- edges: {metadata['edge_count']}",
        f"- starts: {list(metadata['start_nodes'])}",
        f"- goals: {list(metadata['end_nodes'])}",
        f"- strict parser check: `{metadata['strict_error']}`",
        f"- compatibility padding check: final heuristic row tail `{list(metadata['last_heuristic_row'][-3:])}`",
        f"- table: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "## Results",
        "",
        f"- route cases from task snapshots and start/end anchors: {len(rows)}",
        f"- Python/C++ exact path matches: {parity_pass_count} / {len(rows)}",
        f"- legacy output anchor matches: {anchor_pass_count} / {len(anchor_rows)}",
        "",
        "| Start | Goal | Python path | C++ path | Parity | Legacy anchor |",
        "|---:|---:|---|---|---|---|",
    ]
    for row in rows:
        anchor = row["legacy_output_anchor_match"] if row["legacy_output_anchor_path"] else ""
        lines.append(
            f"| {row['start']} | {row['goal']} | `{row['python_path']}` | `{row['cpp_path']}` | "
            f"{row['strict_parity_pass']} | {anchor} |"
        )

    lines.extend(
        [
            "",
            "## Gate Status",
            "",
            f"Phase1 legacy `example1` A* parity gate is {'PASS' if gate_pass else 'FAIL'}.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows, metadata = build_rows()
    write_table(rows)
    write_report(rows, metadata)

    parity_pass = all(bool(row["strict_parity_pass"]) for row in rows)
    anchor_pass = all(bool(row["legacy_output_anchor_match"]) for row in rows if row["legacy_output_anchor_path"])
    print(f"example1_cases={len(rows)} parity_pass={parity_pass} anchor_pass={anchor_pass}")
    if not parity_pass or not anchor_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
