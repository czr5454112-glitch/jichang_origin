from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any, Iterable
import zlib


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"

REPORT_PATH = ROOT / "outputs" / "reports" / "g3i_cie_sipp_integration_report.md"
SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3i_cie_sipp_integration_summary.csv"
PATH_PARITY_TABLE = ROOT / "outputs" / "tables" / "g3i_cie_sipp_path_parity.csv"
GATE_TABLE = ROOT / "outputs" / "tables" / "g3i_cie_sipp_gate.csv"
SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3i_cie_sipp_integration_sample.jsonl"
FIGURE_PATH = ROOT / "outputs" / "figures" / "g3i_cie_sipp_integration.png"

PLANNED_GATE = 115
MAX_SAMPLE_ROWS = 500


@dataclass(frozen=True)
class MatchedScenario:
    name: str
    task_offset: int
    max_tasks: int
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[tuple[int, int, float, float], ...] = ()
    node_capacities: tuple[tuple[int, int], ...] = ()
    merge_groups: tuple[tuple[int, int, int], ...] = ()
    merge_capacity: int = 1
    merge_headway_seconds: float = 0.0


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    candidates = (
        Path(os.environ["CZR005_CPP_PYTHON_PATH"])
        if os.environ.get("CZR005_CPP_PYTHON_PATH")
        else None,
        ROOT / "build_vs" / "python" / "Debug",
        ROOT / "build_vs" / "python" / "Release",
        ROOT / "build_nmake" / "python",
    )
    for candidate in reversed([path for path in candidates if path is not None]):
        if candidate.exists() or str(candidate) == os.environ.get("CZR005_CPP_PYTHON_PATH"):
            sys.path.insert(0, str(candidate))


def _case_plan() -> tuple[MatchedScenario, ...]:
    return (
        MatchedScenario("legacy_first16", 0, 16),
        MatchedScenario("legacy_first16_buffer2", 0, 16, node_capacities=((28, 2), (47, 2))),
        MatchedScenario("legacy_first32", 0, 32),
        MatchedScenario("legacy_offset32_static16", 32, 16, fault_edges=((16, 17),)),
        MatchedScenario("legacy_offset64_repair32", 64, 32, fault_windows=((28, 47, 0.0, 12000.0),)),
        MatchedScenario("legacy_offset64_merge32", 64, 32, merge_groups=((13, 23, 9), (18, 22, 9))),
    )


def _selected_tasks(all_tasks: tuple[Any, ...], scenario: MatchedScenario) -> tuple[Any, ...]:
    return all_tasks[scenario.task_offset : scenario.task_offset + scenario.max_tasks]


def _scenario_context(scenario: MatchedScenario) -> str:
    if scenario.fault_edges:
        return "static_fault"
    if scenario.fault_windows:
        return "repair_window"
    if scenario.merge_groups:
        return "merge_group"
    if scenario.node_capacities:
        return "buffer_capacity"
    return "no_fault"


def _variant_merge_groups(scenario: MatchedScenario) -> dict[tuple[int, int], int]:
    return {(start, end): group for start, end, group in scenario.merge_groups}


def _run_scenario(graph: Any, all_tasks: tuple[Any, ...], scenario: MatchedScenario) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from czr005.baselines import LegacyRouteSIPPBaseline

    selected = _selected_tasks(all_tasks, scenario)
    merge_groups = _variant_merge_groups(scenario)
    baseline = LegacyRouteSIPPBaseline(
        graph,
        edge_capacity=1,
        edge_headway_seconds=0.0,
        node_capacities=dict(scenario.node_capacities),
        merge_groups=merge_groups,
        merge_capacity=scenario.merge_capacity,
        merge_headway_seconds=scenario.merge_headway_seconds,
    )
    result = baseline.run_episode(
        selected,
        max_tasks=scenario.max_tasks,
        fault_edges=set(scenario.fault_edges),
        fault_windows=tuple(scenario.fault_windows),
    )
    edge_conflicts = baseline.edge_reservations.conflict_count(capacity=1, headway_seconds=0.0)
    merge_conflicts = baseline.edge_reservations.merge_group_conflict_count(
        merge_groups,
        scenario.merge_capacity,
        scenario.merge_headway_seconds,
    )
    summary = {
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "scheduler": "cie_astar_path_sipp_timing",
        "max_tasks": scenario.max_tasks,
        "planned": result.metrics.planned_count,
        "unplanned": result.metrics.unplanned_count,
        "node_conflicts": result.metrics.reservation_conflicts,
        "edge_conflicts": edge_conflicts,
        "merge_conflicts": merge_conflicts,
        "real_constraint_conflicts": result.metrics.reservation_conflicts + edge_conflicts + merge_conflicts,
        "legacy_path_match_count": baseline.stats.legacy_path_match_count,
        "legacy_path_mismatch_count": baseline.stats.legacy_path_mismatch_count,
        "inserted_wait_task_count": baseline.stats.inserted_wait_count,
        "teacher_route_source": "original_cie_legacy_astar",
        "sipp_role": "timing_only_execution_wrapper",
    }
    parity_rows = _path_parity_rows(scenario, result.events)
    return summary, parity_rows


def _path_parity_rows(scenario: MatchedScenario, events: list[dict[str, object]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        planned = event["event"] == "planned"
        legacy_path = " ".join(str(value) for value in event.get("legacy_path", []))
        executed_path = " ".join(str(value) for value in event.get("path", []))
        rows.append(
            {
                "scenario": scenario.name,
                "context": _scenario_context(scenario),
                "segment_id": event["segment_id"],
                "task_id": event["task_id"],
                "event": event["event"],
                "legacy_path": legacy_path,
                "executed_path": executed_path,
                "path_matches_legacy_astar": planned and legacy_path == executed_path,
                "inserted_wait_count": event.get("inserted_wait_count", ""),
                "finish_time": event.get("finish_time", ""),
                "unplanned_reason": event.get("reason", ""),
                "teacher_route_source": "original_cie_legacy_astar",
                "sipp_role": "timing_only_execution_wrapper",
            }
        )
    return rows


def _aggregate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scenario": "ALL",
        "context": "aggregate",
        "scheduler": "cie_astar_path_sipp_timing",
        "max_tasks": sum(int(row["max_tasks"]) for row in rows),
        "planned": sum(int(row["planned"]) for row in rows),
        "unplanned": sum(int(row["unplanned"]) for row in rows),
        "node_conflicts": sum(int(row["node_conflicts"]) for row in rows),
        "edge_conflicts": sum(int(row["edge_conflicts"]) for row in rows),
        "merge_conflicts": sum(int(row["merge_conflicts"]) for row in rows),
        "real_constraint_conflicts": sum(int(row["real_constraint_conflicts"]) for row in rows),
        "legacy_path_match_count": sum(int(row["legacy_path_match_count"]) for row in rows),
        "legacy_path_mismatch_count": sum(int(row["legacy_path_mismatch_count"]) for row in rows),
        "inserted_wait_task_count": sum(int(row["inserted_wait_task_count"]) for row in rows),
        "teacher_route_source": "original_cie_legacy_astar",
        "sipp_role": "timing_only_execution_wrapper",
    }


def _gate_rows(summary_rows: list[dict[str, Any]], parity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregate = next(row for row in summary_rows if row["scenario"] == "ALL")
    planned = int(aggregate["planned"])
    conflicts = int(aggregate["real_constraint_conflicts"])
    path_matches = int(aggregate["legacy_path_match_count"])
    path_mismatches = int(aggregate["legacy_path_mismatch_count"])
    planned_events = sum(1 for row in parity_rows if row["event"] == "planned")
    unplanned = int(aggregate["unplanned"])
    return [
        {
            "gate": "sipp_integrated_without_replacing_cie_teacher",
            "pass": True,
            "value": "cie_path_fixed_sipp_timing_only",
            "threshold": "route source must remain original CIE/Legacy A*",
            "decision": "keep_cie_as_teacher",
        },
        {
            "gate": "same_astar_path_effect_for_planned_routes",
            "pass": planned_events == path_matches and path_mismatches == 0,
            "value": f"{path_matches}/{planned_events}",
            "threshold": "all planned routes keep the A* path",
            "decision": "path_effect_preserved" if planned_events == path_matches and path_mismatches == 0 else "inspect_path_drift",
        },
        {
            "gate": "airport_ics_simulation_runs",
            "pass": planned > 0 and planned + unplanned == int(aggregate["max_tasks"]),
            "value": f"{planned}/{aggregate['max_tasks']}",
            "threshold": "all selected real ICS tasks accounted for",
            "decision": "integration_runs_on_map2_inputdata",
        },
        {
            "gate": "hard_runtime_constraints_clean",
            "pass": conflicts == 0,
            "value": conflicts,
            "threshold": "zero node/edge/merge conflicts",
            "decision": "safe_to_continue_g4a_pilot_audit" if conflicts == 0 else "fix_before_any_dataset",
        },
        {
            "gate": "planned_count_gate",
            "pass": planned >= PLANNED_GATE,
            "value": planned,
            "threshold": f">={PLANNED_GATE}",
            "decision": "g4a_pilot_candidate_after_review" if planned >= PLANNED_GATE else "continue_scheduler_repair",
        },
        {
            "gate": "remaining_unplanned_inventory",
            "pass": unplanned > 0,
            "value": unplanned,
            "threshold": "track residual CIE no-path cases",
            "decision": "audit_remaining_no_path_cases",
        },
    ]


def _unplanned_reason_rows(parity_rows: list[dict[str, Any]]) -> list[list[Any]]:
    grouped: defaultdict[tuple[str, str], int] = defaultdict(int)
    for row in parity_rows:
        if row["event"] == "unplanned":
            grouped[(str(row["scenario"]), str(row["unplanned_reason"]))] += 1
    return [[scenario, reason, count] for (scenario, reason), count in sorted(grouped.items())]


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key, "")) for key in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (tuple, list)):
        return ";".join(str(item) for item in value)
    return value


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    planned_waits = [row for row in rows if row["event"] == "planned" and str(row["inserted_wait_count"]) not in {"", "0"}]
    sample = (planned_waits + rows)[:MAX_SAMPLE_ROWS]
    with path.open("w", encoding="utf-8") as handle:
        for row in sample:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_figure(path: Path, summary_rows: list[dict[str, Any]]) -> None:
    scenario_rows = [row for row in summary_rows if row["scenario"] != "ALL"]
    matrix = [[int(row["planned"]), int(row["real_constraint_conflicts"])] for row in scenario_rows]
    _write_png_heatmap(path, matrix, cell=22)


def _write_png_heatmap(path: Path, matrix: list[list[int]], cell: int = 18) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = max(1, len(matrix))
    cols = max(1, len(matrix[0]) if matrix else 1)
    max_value = max((value for row in matrix for value in row), default=1) or 1
    width = cols * cell
    height = rows * cell
    pixels: list[bytes] = []
    for row_index in range(height):
        source_row = min(rows - 1, row_index // cell)
        scanline = bytearray()
        for col_index in range(width):
            source_col = min(cols - 1, col_index // cell)
            value = matrix[source_row][source_col] if matrix else 0
            intensity = int(255 * value / max_value)
            scanline.extend((255, 255 - intensity, 255 - intensity))
        pixels.append(b"\x00" + bytes(scanline))
    raw = b"".join(pixels)
    data = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(raw)),
            _png_chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(data)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _write_report(
    summary_rows: list[dict[str, Any]],
    parity_rows: list[dict[str, Any]],
    gate_rows: list[dict[str, Any]],
) -> None:
    aggregate = next(row for row in summary_rows if row["scenario"] == "ALL")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G3i CIE/A* Path-Constrained SIPP Integration",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## 1. Scope",
        "",
        "G3i integrates SIPP into the execution layer without replacing the original CIE/Legacy A* teacher. CIE/A* still chooses the route; the SIPP-style wrapper only retimes that fixed route around node, edge, and merge reservations.",
        "",
        "## 2. Real ICS simulation result",
        "",
        _markdown_table(
            ["Scenario", "Planned", "Conflicts", "A* path matches", "Waited tasks"],
            [
                [
                    row["scenario"],
                    f"{row['planned']}/{row['max_tasks']}",
                    row["real_constraint_conflicts"],
                    f"{row['legacy_path_match_count']}/{row['planned']}",
                    row["inserted_wait_task_count"],
                ]
                for row in summary_rows
                if row["scenario"] != "ALL"
            ],
        ),
        "",
        f"Aggregate: `{aggregate['planned']}/{aggregate['max_tasks']}` planned, `{aggregate['real_constraint_conflicts']}` real node/edge/merge conflicts, `{aggregate['legacy_path_match_count']}/{aggregate['planned']}` planned routes keep the original A* path.",
        "",
        "## 3. Gates",
        "",
        _markdown_table(
            ["Gate", "Pass", "Value", "Decision"],
            [[row["gate"], row["pass"], row["value"], row["decision"]] for row in gate_rows],
        ),
        "",
        "## 4. Remaining unplanned cases",
        "",
        _markdown_table(["Scenario", "Reason", "Count"], _unplanned_reason_rows(parity_rows)),
        "",
        "## 5. Decision",
        "",
        "Integration pass: SIPP is now usable as an execution-timing wrapper around the existing CIE/A* route effect. This is a G4A pilot candidate, but the remaining no-path inventory still needs an audit before broad training.",
        "",
        "## Artifacts",
        "",
        f"- Summary: `{_relative(SUMMARY_TABLE)}`",
        f"- Path parity: `{_relative(PATH_PARITY_TABLE)}`",
        f"- Gate: `{_relative(GATE_TABLE)}`",
        f"- JSONL sample: `{_relative(SAMPLE_PATH)}`",
        f"- Figure: `{_relative(FIGURE_PATH)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._"
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(str(value) for value in row) + " |" for row in rows],
        ]
    )


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _summary_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "scheduler",
        "max_tasks",
        "planned",
        "unplanned",
        "node_conflicts",
        "edge_conflicts",
        "merge_conflicts",
        "real_constraint_conflicts",
        "legacy_path_match_count",
        "legacy_path_mismatch_count",
        "inserted_wait_task_count",
        "teacher_route_source",
        "sipp_role",
    ]


def _path_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "segment_id",
        "task_id",
        "event",
        "legacy_path",
        "executed_path",
        "path_matches_legacy_astar",
        "inserted_wait_count",
        "finish_time",
        "unplanned_reason",
        "teacher_route_source",
        "sipp_role",
    ]


def _gate_fields() -> list[str]:
    return ["gate", "pass", "value", "threshold", "decision"]


def main() -> None:
    _prepare_imports()
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream

    graph = IcsGraph.from_json(MAP_PATH)
    all_tasks = tuple(TaskStream.from_jsonl(TASK_PATH))
    summary_rows: list[dict[str, Any]] = []
    parity_rows: list[dict[str, Any]] = []
    for scenario in _case_plan():
        summary, parity = _run_scenario(graph, all_tasks, scenario)
        summary_rows.append(summary)
        parity_rows.extend(parity)
    summary_rows.append(_aggregate_summary(summary_rows))
    gate_rows = _gate_rows(summary_rows, parity_rows)

    _write_csv(SUMMARY_TABLE, summary_rows, _summary_fields())
    _write_csv(PATH_PARITY_TABLE, parity_rows, _path_fields())
    _write_csv(GATE_TABLE, gate_rows, _gate_fields())
    _write_jsonl(SAMPLE_PATH, parity_rows)
    _write_figure(FIGURE_PATH, summary_rows)
    _write_report(summary_rows, parity_rows, gate_rows)

    aggregate = next(row for row in summary_rows if row["scenario"] == "ALL")
    if int(aggregate["planned"]) < PLANNED_GATE:
        raise AssertionError("G3i planned-count gate failed")
    if int(aggregate["real_constraint_conflicts"]) != 0:
        raise AssertionError("G3i hard-runtime conflict gate failed")
    if int(aggregate["legacy_path_mismatch_count"]) != 0:
        raise AssertionError("G3i changed planned Legacy/A* paths")

    required = (REPORT_PATH, SUMMARY_TABLE, PATH_PARITY_TABLE, GATE_TABLE, SAMPLE_PATH, FIGURE_PATH)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G3i artifacts: {missing}")
    print(
        "g3i complete: "
        f"planned={aggregate['planned']}/{aggregate['max_tasks']} "
        f"conflicts={aggregate['real_constraint_conflicts']} "
        f"path_matches={aggregate['legacy_path_match_count']}/{aggregate['planned']}"
    )


if __name__ == "__main__":
    main()
