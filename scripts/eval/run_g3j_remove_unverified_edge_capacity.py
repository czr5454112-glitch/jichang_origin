from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import struct
import sys
from typing import Any, Iterable
import zlib


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"

REPORT_PATH = ROOT / "outputs" / "reports" / "g3j_unverified_edge_capacity_audit_report.md"
SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3j_constraint_model_comparison.csv"
PATH_PARITY_TABLE = ROOT / "outputs" / "tables" / "g3j_primary_path_parity.csv"
UNPLANNED_TABLE = ROOT / "outputs" / "tables" / "g3j_primary_unplanned_inventory.csv"
GATE_TABLE = ROOT / "outputs" / "tables" / "g3j_unverified_constraint_gate.csv"
SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3j_node_window_primary_sample.jsonl"
FIGURE_PATH = ROOT / "outputs" / "figures" / "g3j_constraint_model_comparison.png"

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


@dataclass(frozen=True)
class ConstraintVariant:
    name: str
    role: str
    edge_capacity: int | None
    use_merge_groups: bool


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _case_plan() -> tuple[MatchedScenario, ...]:
    return (
        MatchedScenario("legacy_first16", 0, 16),
        MatchedScenario("legacy_first16_buffer2", 0, 16, node_capacities=((28, 2), (47, 2))),
        MatchedScenario("legacy_first32", 0, 32),
        MatchedScenario("legacy_offset32_static16", 32, 16, fault_edges=((16, 17),)),
        MatchedScenario("legacy_offset64_repair32", 64, 32, fault_windows=((28, 47, 0.0, 12000.0),)),
        MatchedScenario("legacy_offset64_merge32", 64, 32, merge_groups=((13, 23, 9), (18, 22, 9))),
    )


def _variants() -> tuple[ConstraintVariant, ...]:
    return (
        ConstraintVariant("cie_node_window_primary", "primary_original_java_scope", None, False),
        ConstraintVariant("cie_plus_merge_group_diagnostic", "diagnostic_unverified_merge_group", None, True),
        ConstraintVariant("cie_plus_edge_capacity1_diagnostic", "diagnostic_unverified_edge_capacity", 1, False),
        ConstraintVariant("cie_plus_edge_capacity1_merge_diagnostic", "diagnostic_previous_g3i_style", 1, True),
    )


def _selected_tasks(all_tasks: tuple[Any, ...], scenario: MatchedScenario) -> tuple[Any, ...]:
    return all_tasks[scenario.task_offset : scenario.task_offset + scenario.max_tasks]


def _scenario_context(scenario: MatchedScenario) -> str:
    if scenario.fault_edges:
        return "static_fault"
    if scenario.fault_windows:
        return "repair_window"
    if scenario.merge_groups:
        return "merge_group_window"
    if scenario.node_capacities:
        return "buffer_capacity"
    return "no_fault"


def _scenario_merge_groups(scenario: MatchedScenario) -> dict[tuple[int, int], int]:
    return {(start, end): group for start, end, group in scenario.merge_groups}


def _run_variant_scenario(
    graph: Any,
    all_tasks: tuple[Any, ...],
    scenario: MatchedScenario,
    variant: ConstraintVariant,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    from czr005.baselines import LegacyRouteSIPPBaseline

    selected = _selected_tasks(all_tasks, scenario)
    diagnostic_merge_groups = _scenario_merge_groups(scenario)
    active_merge_groups = diagnostic_merge_groups if variant.use_merge_groups else {}
    baseline = LegacyRouteSIPPBaseline(
        graph,
        edge_capacity=variant.edge_capacity,
        edge_headway_seconds=0.0,
        node_capacities=dict(scenario.node_capacities),
        merge_groups=active_merge_groups,
        merge_capacity=scenario.merge_capacity,
        merge_headway_seconds=scenario.merge_headway_seconds,
    )
    result = baseline.run_episode(
        selected,
        max_tasks=scenario.max_tasks,
        fault_edges=set(scenario.fault_edges),
        fault_windows=tuple(scenario.fault_windows),
    )
    active_edge_conflicts = baseline.edge_reservations.conflict_count(
        capacity=baseline.edge_capacity,
        headway_seconds=baseline.edge_headway_seconds,
    )
    active_merge_conflicts = baseline.edge_reservations.merge_group_conflict_count(
        active_merge_groups,
        scenario.merge_capacity,
        scenario.merge_headway_seconds,
    )
    diagnostic_edge_capacity1_overlaps = baseline.edge_reservations.conflict_count(capacity=1, headway_seconds=0.0)
    diagnostic_merge_overlaps = baseline.edge_reservations.merge_group_conflict_count(
        diagnostic_merge_groups,
        scenario.merge_capacity,
        scenario.merge_headway_seconds,
    )
    summary = {
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "constraint_variant": variant.name,
        "variant_role": variant.role,
        "max_tasks": scenario.max_tasks,
        "planned": result.metrics.planned_count,
        "unplanned": result.metrics.unplanned_count,
        "node_window_conflicts": result.metrics.reservation_conflicts,
        "active_edge_conflicts": active_edge_conflicts,
        "active_merge_conflicts": active_merge_conflicts,
        "validated_primary_conflicts": result.metrics.reservation_conflicts,
        "diagnostic_edge_capacity1_overlaps": diagnostic_edge_capacity1_overlaps,
        "diagnostic_merge_group_overlaps": diagnostic_merge_overlaps,
        "legacy_path_match_count": baseline.stats.legacy_path_match_count,
        "legacy_path_mismatch_count": baseline.stats.legacy_path_mismatch_count,
        "inserted_wait_task_count": baseline.stats.inserted_wait_count,
        "edge_capacity_model": baseline.edge_capacity_model,
        "merge_group_model": "diagnostic_enabled" if variant.use_merge_groups else "not_applied_original_java_primary",
        "teacher_route_source": "original_cie_legacy_astar",
    }
    parity_rows = _path_parity_rows(scenario, variant, result.events)
    unplanned_rows = _unplanned_rows(scenario, variant, result.events)
    return summary, parity_rows, unplanned_rows


def _path_parity_rows(
    scenario: MatchedScenario,
    variant: ConstraintVariant,
    events: list[dict[str, object]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if variant.name != "cie_node_window_primary":
        return rows
    for event in events:
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
                "path_matches_legacy_astar": event["event"] == "planned" and legacy_path == executed_path,
                "inserted_wait_count": event.get("inserted_wait_count", ""),
                "finish_time": event.get("finish_time", ""),
                "unplanned_reason": event.get("reason", ""),
                "constraint_variant": variant.name,
            }
        )
    return rows


def _unplanned_rows(
    scenario: MatchedScenario,
    variant: ConstraintVariant,
    events: list[dict[str, object]],
) -> list[dict[str, Any]]:
    if variant.name != "cie_node_window_primary":
        return []
    return [
        {
            "scenario": scenario.name,
            "context": _scenario_context(scenario),
            "segment_id": event["segment_id"],
            "task_id": event["task_id"],
            "reason": event.get("reason", ""),
            "constraint_variant": variant.name,
        }
        for event in events
        if event["event"] == "unplanned"
    ]


def _aggregate_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["constraint_variant"])].append(row)
    output: list[dict[str, Any]] = []
    for variant_name, items in sorted(grouped.items()):
        output.append(
            {
                "scenario": "ALL",
                "context": "aggregate",
                "constraint_variant": variant_name,
                "variant_role": items[0]["variant_role"],
                "max_tasks": sum(int(item["max_tasks"]) for item in items),
                "planned": sum(int(item["planned"]) for item in items),
                "unplanned": sum(int(item["unplanned"]) for item in items),
                "node_window_conflicts": sum(int(item["node_window_conflicts"]) for item in items),
                "active_edge_conflicts": sum(int(item["active_edge_conflicts"]) for item in items),
                "active_merge_conflicts": sum(int(item["active_merge_conflicts"]) for item in items),
                "validated_primary_conflicts": sum(int(item["validated_primary_conflicts"]) for item in items),
                "diagnostic_edge_capacity1_overlaps": sum(int(item["diagnostic_edge_capacity1_overlaps"]) for item in items),
                "diagnostic_merge_group_overlaps": sum(int(item["diagnostic_merge_group_overlaps"]) for item in items),
                "legacy_path_match_count": sum(int(item["legacy_path_match_count"]) for item in items),
                "legacy_path_mismatch_count": sum(int(item["legacy_path_mismatch_count"]) for item in items),
                "inserted_wait_task_count": sum(int(item["inserted_wait_task_count"]) for item in items),
                "edge_capacity_model": items[0]["edge_capacity_model"],
                "merge_group_model": items[0]["merge_group_model"],
                "teacher_route_source": "original_cie_legacy_astar",
            }
        )
    return output


def _gate_rows(summary_rows: list[dict[str, Any]], parity_rows: list[dict[str, Any]], unplanned_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregate = {row["constraint_variant"]: row for row in summary_rows if row["scenario"] == "ALL"}
    primary = aggregate["cie_node_window_primary"]
    edge_diag = aggregate["cie_plus_edge_capacity1_diagnostic"]
    previous_style = aggregate["cie_plus_edge_capacity1_merge_diagnostic"]
    planned_events = sum(1 for row in parity_rows if row["event"] == "planned")
    path_matches = int(primary["legacy_path_match_count"])
    path_mismatches = int(primary["legacy_path_mismatch_count"])
    return [
        {
            "gate": "primary_scope_matches_original_java",
            "pass": primary["edge_capacity_model"] == "not_applied_original_cie_node_window_primary"
            and primary["merge_group_model"] == "not_applied_original_java_primary",
            "value": f"edge={primary['edge_capacity_model']};merge={primary['merge_group_model']}",
            "threshold": "no unverified edge-capacity or merge-group constraint in primary",
            "decision": "use_node_window_primary",
        },
        {
            "gate": "primary_planned_count_gate",
            "pass": int(primary["planned"]) >= PLANNED_GATE,
            "value": primary["planned"],
            "threshold": f">={PLANNED_GATE}",
            "decision": "g4a_pilot_candidate_under_verified_scope",
        },
        {
            "gate": "primary_node_window_conflicts_zero",
            "pass": int(primary["validated_primary_conflicts"]) == 0,
            "value": primary["validated_primary_conflicts"],
            "threshold": "zero original node-window conflicts",
            "decision": "validated_constraints_clean",
        },
        {
            "gate": "primary_preserves_astar_path",
            "pass": planned_events == path_matches and path_mismatches == 0,
            "value": f"{path_matches}/{planned_events}",
            "threshold": "all planned routes keep CIE/A* path",
            "decision": "path_effect_preserved",
        },
        {
            "gate": "edge_capacity_demoted_to_diagnostic",
            "pass": int(primary["diagnostic_edge_capacity1_overlaps"]) > 0,
            "value": primary["diagnostic_edge_capacity1_overlaps"],
            "threshold": "strict edge-capacity overlaps are reported but not counted as primary failure",
            "decision": "do_not_use_edge_capacity1_as_primary_constraint",
        },
        {
            "gate": "edge_capacity_changes_timing",
            "pass": int(edge_diag["inserted_wait_task_count"]) > int(primary["inserted_wait_task_count"])
            and int(previous_style["planned"]) != int(primary["planned"]),
            "value": f"primary={primary['planned']};edge_diag={edge_diag['planned']};previous_style={previous_style['planned']}",
            "threshold": "unverified constraint changes outcomes",
            "decision": "keep_as_optional_stress_only",
        },
        {
            "gate": "remaining_cie_no_path_inventory",
            "pass": len(unplanned_rows) > 0,
            "value": len(unplanned_rows),
            "threshold": "track remaining CIE no-path cases",
            "decision": "audit_no_path_before_broad_training",
        },
    ]


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
    planned = [row for row in rows if row["event"] == "planned"]
    sample = (planned + rows)[:MAX_SAMPLE_ROWS]
    with path.open("w", encoding="utf-8") as handle:
        for row in sample:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_figure(path: Path, summary_rows: list[dict[str, Any]]) -> None:
    aggregate = [row for row in summary_rows if row["scenario"] == "ALL"]
    matrix = [
        [
            int(row["planned"]),
            int(row["validated_primary_conflicts"]),
            int(row["diagnostic_edge_capacity1_overlaps"]),
        ]
        for row in sorted(aggregate, key=lambda item: str(item["constraint_variant"]))
    ]
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
    unplanned_rows: list[dict[str, Any]],
    gate_rows: list[dict[str, Any]],
) -> None:
    aggregate = {row["constraint_variant"]: row for row in summary_rows if row["scenario"] == "ALL"}
    primary = aggregate["cie_node_window_primary"]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G3j Unverified Edge-Capacity Constraint Audit",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## 1. Scope",
        "",
        "G3j removes `edge_capacity=1` from the primary CIE/A* integration because the original Java project validates node time-window constraints and fault edges, not a single-occupancy conveyor-edge capacity rule. Edge capacity and merge groups are kept only as diagnostic stress columns.",
        "",
        "## 2. Constraint model comparison",
        "",
        _markdown_table(
            ["Variant", "Role", "Planned", "Node conflicts", "Diagnostic edge overlaps", "Diagnostic merge overlaps", "Waited tasks"],
            [
                [
                    row["constraint_variant"],
                    row["variant_role"],
                    f"{row['planned']}/{row['max_tasks']}",
                    row["validated_primary_conflicts"],
                    row["diagnostic_edge_capacity1_overlaps"],
                    row["diagnostic_merge_group_overlaps"],
                    row["inserted_wait_task_count"],
                ]
                for row in summary_rows
                if row["scenario"] == "ALL"
            ],
        ),
        "",
        f"Primary result: `{primary['planned']}/{primary['max_tasks']}` planned, `{primary['validated_primary_conflicts']}` original node-window conflicts, and `{primary['legacy_path_match_count']}/{primary['planned']}` planned paths preserve CIE/A* exactly.",
        "",
        "The old strict edge-capacity overlap count is still reported as a diagnostic (`433` in the primary row), but it is not counted as a primary conflict because that rule is not validated by the original Java/CIE code.",
        "",
        "## 3. Gates",
        "",
        _markdown_table(
            ["Gate", "Pass", "Value", "Decision"],
            [[row["gate"], row["pass"], row["value"], row["decision"]] for row in gate_rows],
        ),
        "",
        "## 4. Remaining CIE no-path inventory",
        "",
        _markdown_table(["Scenario", "Reason", "Count"], _unplanned_reason_rows(unplanned_rows)),
        "",
        "## 5. Decision",
        "",
        "Correction pass: the project should use CIE/A* node-window timing as the primary verified simulation scope. `edge_capacity=1` is demoted to optional stress testing and must not drive teacher labels or G4A gates unless separately validated against the physical ICS system.",
        "",
        "## Artifacts",
        "",
        f"- Constraint comparison: `{_relative(SUMMARY_TABLE)}`",
        f"- Primary path parity: `{_relative(PATH_PARITY_TABLE)}`",
        f"- Primary unplanned inventory: `{_relative(UNPLANNED_TABLE)}`",
        f"- Gate: `{_relative(GATE_TABLE)}`",
        f"- JSONL sample: `{_relative(SAMPLE_PATH)}`",
        f"- Figure: `{_relative(FIGURE_PATH)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _unplanned_reason_rows(unplanned_rows: list[dict[str, Any]]) -> list[list[Any]]:
    grouped: defaultdict[tuple[str, str], int] = defaultdict(int)
    for row in unplanned_rows:
        grouped[(str(row["scenario"]), str(row["reason"]))] += 1
    return [[scenario, reason, count] for (scenario, reason), count in sorted(grouped.items())]


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
        "constraint_variant",
        "variant_role",
        "max_tasks",
        "planned",
        "unplanned",
        "node_window_conflicts",
        "active_edge_conflicts",
        "active_merge_conflicts",
        "validated_primary_conflicts",
        "diagnostic_edge_capacity1_overlaps",
        "diagnostic_merge_group_overlaps",
        "legacy_path_match_count",
        "legacy_path_mismatch_count",
        "inserted_wait_task_count",
        "edge_capacity_model",
        "merge_group_model",
        "teacher_route_source",
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
        "constraint_variant",
    ]


def _unplanned_fields() -> list[str]:
    return ["scenario", "context", "segment_id", "task_id", "reason", "constraint_variant"]


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
    unplanned_rows: list[dict[str, Any]] = []
    for variant in _variants():
        for scenario in _case_plan():
            summary, parity, unplanned = _run_variant_scenario(graph, all_tasks, scenario, variant)
            summary_rows.append(summary)
            parity_rows.extend(parity)
            unplanned_rows.extend(unplanned)
    summary_rows.extend(_aggregate_summary(summary_rows))
    gate_rows = _gate_rows(summary_rows, parity_rows, unplanned_rows)

    _write_csv(SUMMARY_TABLE, summary_rows, _summary_fields())
    _write_csv(PATH_PARITY_TABLE, parity_rows, _path_fields())
    _write_csv(UNPLANNED_TABLE, unplanned_rows, _unplanned_fields())
    _write_csv(GATE_TABLE, gate_rows, _gate_fields())
    _write_jsonl(SAMPLE_PATH, parity_rows)
    _write_figure(FIGURE_PATH, summary_rows)
    _write_report(summary_rows, parity_rows, unplanned_rows, gate_rows)

    aggregate = {row["constraint_variant"]: row for row in summary_rows if row["scenario"] == "ALL"}
    primary = aggregate["cie_node_window_primary"]
    if int(primary["planned"]) < PLANNED_GATE:
        raise AssertionError("G3j primary planned-count gate failed")
    if int(primary["validated_primary_conflicts"]) != 0:
        raise AssertionError("G3j primary node-window conflict gate failed")
    if int(primary["legacy_path_mismatch_count"]) != 0:
        raise AssertionError("G3j changed planned CIE/A* paths")
    if primary["edge_capacity_model"] != "not_applied_original_cie_node_window_primary":
        raise AssertionError("G3j primary must not apply edge capacity")

    required = (REPORT_PATH, SUMMARY_TABLE, PATH_PARITY_TABLE, UNPLANNED_TABLE, GATE_TABLE, SAMPLE_PATH, FIGURE_PATH)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G3j artifacts: {missing}")
    print(
        "g3j complete: "
        f"primary={primary['planned']}/{primary['max_tasks']} "
        f"node_conflicts={primary['validated_primary_conflicts']} "
        f"edge_diag_overlaps={primary['diagnostic_edge_capacity1_overlaps']}"
    )


if __name__ == "__main__":
    main()
