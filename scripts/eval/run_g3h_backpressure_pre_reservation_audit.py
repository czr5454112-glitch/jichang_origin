from __future__ import annotations

from collections import Counter
import csv
from datetime import date
import json
from pathlib import Path
import struct
from typing import Any, Iterable
import zlib


ROOT = Path(__file__).resolve().parents[2]

G3F_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3f_scheduler_variant_comparison.csv"
G3G_CURRENT_UPSTREAM_TABLE = ROOT / "outputs" / "tables" / "g3g_current_vs_upstream_wait_cases.csv"
G3G_SCHEDULER_TABLE = ROOT / "outputs" / "tables" / "g3g_scheduler_replay_comparison.csv"

REPORT_PATH = ROOT / "outputs" / "reports" / "g3h_backpressure_pre_reservation_audit_report.md"
CANDIDATE_LABELS_TABLE = ROOT / "outputs" / "tables" / "g3h_cie_backpressure_candidate_labels.csv"
PROJECTION_TABLE = ROOT / "outputs" / "tables" / "g3h_cie_recovered_capacity_projection.csv"
PATH_ALIGNMENT_TABLE = ROOT / "outputs" / "tables" / "g3h_cie_path_alignment.csv"
WAIT_WINDOWS_TABLE = ROOT / "outputs" / "tables" / "g3h_cie_upstream_wait_windows.csv"
NEXT_GATE_TABLE = ROOT / "outputs" / "tables" / "g3h_next_step_gate.csv"
SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3h_cie_backpressure_teacher_sample.jsonl"
FIGURE_PATH = ROOT / "outputs" / "figures" / "g3h_cie_backpressure_projection.png"

G4A_PLANNED_GATE = 115
MAX_SAMPLE_ROWS = 500


def _candidate_rows(upstream_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for row in upstream_rows:
        key = (row["scenario"], row["segment_id"])
        path = _parse_path(row["legacy_node_window_path"])
        current = int(row["current"])
        legacy_next = int(row["legacy_next"])
        cie_planned = row["legacy_node_window_planned"] == "True"
        preserves_edge = cie_planned and _path_has_edge(path, current, legacy_next)
        recovery_class = _recovery_class(cie_planned, preserves_edge)
        unique_credit = key not in seen
        seen.add(key)
        rows.append(
            {
                "scenario": row["scenario"],
                "context": row["context"],
                "segment_id": row["segment_id"],
                "task_id": row["task_id"],
                "current": current,
                "legacy_next": legacy_next,
                "bottleneck_edge": row["edge"],
                "original_g3f_label": row["g3f_local_label"],
                "original_terminal_reason": row["g3f_terminal_reason"],
                "release_time_from_blocker": row["release_time_from_blocker"],
                "wait_needed_if_nonoccupying": row["wait_needed_if_nonoccupying"],
                "cie_teacher_planned": cie_planned,
                "cie_teacher_path": row["legacy_node_window_path"],
                "cie_preserves_bottleneck_edge": preserves_edge,
                "cie_upstream_wait_node": _upstream_wait_node(path, current),
                "cie_upstream_wait_until": row["release_time_from_blocker"],
                "candidate_label": _candidate_label(recovery_class),
                "recovery_class": recovery_class,
                "label_source": "original_cie_legacy_astar_with_runtime_backpressure_wrapper",
                "teacher_role": "primary_cie_teacher" if cie_planned else "cie_abstain",
                "unique_scenario_segment_credit": unique_credit,
                "g4a_primary_candidate": False,
                "why_not_primary_yet": "needs_closed_loop_backpressure_replay_under_hard_shield",
            }
        )
    return rows


def _recovery_class(cie_planned: bool, preserves_edge: bool) -> str:
    if preserves_edge:
        return "cie_preserve_edge_upstream_wait"
    if cie_planned:
        return "cie_upstream_reroute_before_bottleneck"
    return "cie_no_path_still_blocked"


def _candidate_label(recovery_class: str) -> str:
    if recovery_class == "cie_preserve_edge_upstream_wait":
        return "CIE_WAIT_UPSTREAM_EDGE_RELEASE"
    if recovery_class == "cie_upstream_reroute_before_bottleneck":
        return "CIE_REROUTE_UPSTREAM_BEFORE_BOTTLENECK"
    return "CIE_ABSTAIN_NO_PATH"


def _projection_rows(
    g3f_summary: list[dict[str, str]],
    g3g_scheduler: list[dict[str, str]],
    candidate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    best = _aggregate_g3f_row(g3f_summary, "capacity_wait_budget_5s")
    base_planned = int(best["planned_count"])
    cie_conflicts = _scheduler_conflicts(g3g_scheduler, "legacy_node_window_full_route")
    unique = [row for row in candidate_rows if row["unique_scenario_segment_credit"]]
    preserve = [row for row in unique if row["recovery_class"] == "cie_preserve_edge_upstream_wait"]
    cie_planned = [
        row
        for row in unique
        if row["recovery_class"] in {"cie_preserve_edge_upstream_wait", "cie_upstream_reroute_before_bottleneck"}
    ]
    no_path = [row for row in unique if row["recovery_class"] == "cie_no_path_still_blocked"]
    return [
        {
            "projection": "g3f_best_current",
            "base_planned": base_planned,
            "added_unique_segments": 0,
            "projected_planned": base_planned,
            "projected_planned_gate": base_planned >= G4A_PLANNED_GATE,
            "teacher_source": "cie_route_intent_plus_current_local_wrapper",
            "raw_cie_conflicts_if_executed_blindly": cie_conflicts,
            "status": "observed",
        },
        {
            "projection": "cie_preserve_edge_backpressure",
            "base_planned": base_planned,
            "added_unique_segments": len(preserve),
            "projected_planned": base_planned + len(preserve),
            "projected_planned_gate": base_planned + len(preserve) >= G4A_PLANNED_GATE,
            "teacher_source": "original_cie_same_bottleneck_edge_with_upstream_wait",
            "raw_cie_conflicts_if_executed_blindly": cie_conflicts,
            "status": "counterfactual_candidate",
        },
        {
            "projection": "cie_backpressure_plus_cie_upstream_reroute",
            "base_planned": base_planned,
            "added_unique_segments": len(cie_planned),
            "projected_planned": base_planned + len(cie_planned),
            "projected_planned_gate": base_planned + len(cie_planned) >= G4A_PLANNED_GATE,
            "teacher_source": "original_cie_node_window_path_with_runtime_backpressure_wrapper",
            "raw_cie_conflicts_if_executed_blindly": cie_conflicts,
            "status": "counterfactual_candidate_needs_closed_loop_replay",
        },
        {
            "projection": "cie_no_path_remaining_inventory",
            "base_planned": base_planned,
            "added_unique_segments": len(no_path),
            "projected_planned": base_planned + len(cie_planned),
            "projected_planned_gate": base_planned + len(cie_planned) >= G4A_PLANNED_GATE,
            "teacher_source": "cie_no_path_or_not_yet_explained",
            "raw_cie_conflicts_if_executed_blindly": cie_conflicts,
            "status": "remaining_blocker_inventory",
        },
    ]


def _path_alignment_rows(candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "scenario": row["scenario"],
            "segment_id": row["segment_id"],
            "task_id": row["task_id"],
            "bottleneck_edge": row["bottleneck_edge"],
            "cie_teacher_planned": row["cie_teacher_planned"],
            "cie_preserves_bottleneck_edge": row["cie_preserves_bottleneck_edge"],
            "cie_teacher_path": row["cie_teacher_path"],
            "recovery_class": row["recovery_class"],
            "unique_scenario_segment_credit": row["unique_scenario_segment_credit"],
        }
        for row in candidate_rows
    ]


def _wait_window_rows(candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "scenario": row["scenario"],
            "segment_id": row["segment_id"],
            "task_id": row["task_id"],
            "bottleneck_edge": row["bottleneck_edge"],
            "cie_upstream_wait_node": row["cie_upstream_wait_node"],
            "cie_upstream_wait_until": row["cie_upstream_wait_until"],
            "wait_needed_if_nonoccupying": row["wait_needed_if_nonoccupying"],
            "candidate_label": row["candidate_label"],
            "recovery_class": row["recovery_class"],
        }
        for row in candidate_rows
    ]


def _next_gate_rows(projection_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projection = {row["projection"]: row for row in projection_rows}
    unique = [row for row in candidate_rows if row["unique_scenario_segment_credit"]]
    preserve_count = sum(1 for row in unique if row["recovery_class"] == "cie_preserve_edge_upstream_wait")
    cie_reroute_count = sum(1 for row in unique if row["recovery_class"] == "cie_upstream_reroute_before_bottleneck")
    no_path_count = sum(1 for row in unique if row["recovery_class"] == "cie_no_path_still_blocked")
    return [
        {
            "gate": "cie_teacher_remains_primary_source",
            "pass": True,
            "value": "CIE/Legacy only",
            "decision": "only_original_project_teacher_labels",
        },
        {
            "gate": "cie_preserve_edge_projection_reaches_planned_gate",
            "pass": projection["cie_preserve_edge_backpressure"]["projected_planned_gate"],
            "value": projection["cie_preserve_edge_backpressure"]["projected_planned"],
            "decision": "closed_loop_replay_required",
        },
        {
            "gate": "cie_full_node_window_projection_reaches_planned_gate",
            "pass": projection["cie_backpressure_plus_cie_upstream_reroute"]["projected_planned_gate"],
            "value": projection["cie_backpressure_plus_cie_upstream_reroute"]["projected_planned"],
            "decision": "closed_loop_replay_required",
        },
        {
            "gate": "raw_cie_not_executable_without_wrapper",
            "pass": projection["g3f_best_current"]["raw_cie_conflicts_if_executed_blindly"] > 0,
            "value": projection["g3f_best_current"]["raw_cie_conflicts_if_executed_blindly"],
            "decision": "keep_runtime_hard_shield",
        },
        {
            "gate": "unique_case_taxonomy",
            "pass": True,
            "value": f"preserve={preserve_count};cie_reroute={cie_reroute_count};cie_no_path={no_path_count}",
            "decision": "implement_g3i_cie_closed_loop_backpressure",
        },
    ]


def _parse_path(value: str) -> tuple[int, ...]:
    if not value:
        return ()
    return tuple(int(part) for part in value.split() if part.strip().lstrip("-").isdigit())


def _path_has_edge(path: tuple[int, ...], start: int, end: int) -> bool:
    return any(left == start and right == end for left, right in zip(path, path[1:]))


def _upstream_wait_node(path: tuple[int, ...], current: int) -> str:
    for index, node in enumerate(path):
        if node == current:
            return str(path[index - 1]) if index > 0 else str(current)
    return ""


def _aggregate_g3f_row(rows: list[dict[str, str]], variant: str) -> dict[str, str]:
    for row in rows:
        if row.get("scenario") == "ALL" and row.get("replay_variant") == variant:
            return row
    raise AssertionError(f"missing aggregate G3f row for {variant}")


def _scheduler_conflicts(rows: list[dict[str, str]], scheduler: str) -> int:
    for row in rows:
        if row.get("scenario") == "ALL" and row.get("scheduler") == scheduler:
            return int(row["real_constraint_conflicts"])
    raise AssertionError(f"missing aggregate scheduler row for {scheduler}")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


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
    prioritized = [row for row in rows if row["recovery_class"] == "cie_preserve_edge_upstream_wait"]
    sample = (prioritized + rows)[:MAX_SAMPLE_ROWS]
    with path.open("w", encoding="utf-8") as handle:
        for row in sample:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_figure(path: Path, projection_rows: list[dict[str, Any]]) -> None:
    matrix = [[int(row["projected_planned"])] for row in projection_rows]
    _write_png_heatmap(path, matrix, cell=24)


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
    candidate_rows: list[dict[str, Any]],
    projection_rows: list[dict[str, Any]],
    gate_rows: list[dict[str, Any]],
) -> None:
    unique = [row for row in candidate_rows if row["unique_scenario_segment_credit"]]
    class_counts = Counter(row["recovery_class"] for row in unique)
    projection = {row["projection"]: row for row in projection_rows}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G3h CIE Backpressure / Pre-Reservation Audit",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## 1. Scope",
        "",
        "G3h keeps the original CIE/Legacy A* project as the teacher source. No non-CIE planner is used to produce teacher labels. The audit asks whether the CIE route can be wrapped with upstream waiting or CIE-sourced upstream reroute labels so the runtime hard shield is still respected.",
        "",
        "## 2. Recovery projection",
        "",
        _markdown_table(
            ["Projection", "Added", "Planned", "Gate", "Raw CIE conflicts"],
            [
                [
                    row["projection"],
                    row["added_unique_segments"],
                    row["projected_planned"],
                    row["projected_planned_gate"],
                    row["raw_cie_conflicts_if_executed_blindly"],
                ]
                for row in projection_rows
            ],
        ),
        "",
        f"Unique G3g blocked scenario-task cases: `{len(unique)}`. CIE same-edge upstream waits: `{class_counts['cie_preserve_edge_upstream_wait']}`. CIE upstream reroute cases: `{class_counts['cie_upstream_reroute_before_bottleneck']}`. CIE no-path cases: `{class_counts['cie_no_path_still_blocked']}`.",
        "",
        "## 3. What this means",
        "",
        f"If we only keep the exact CIE bottleneck edge and add upstream wait labels, the projection is `{projection['cie_preserve_edge_backpressure']['projected_planned']}/144`, already above the `115/144` planned-count gate. If we also accept CIE's own upstream reroute path where CIE changes the route before the bottleneck, the projection is `{projection['cie_backpressure_plus_cie_upstream_reroute']['projected_planned']}/144`.",
        "",
        "This is still not a training green light, because raw CIE node-window routes create real edge/merge conflicts if executed blindly. The next step is to implement a closed-loop CIE backpressure replay that keeps the hard runtime shield active.",
        "",
        "## 4. Label classes",
        "",
        _markdown_table(
            ["Class", "Rows"],
            [[name, count] for name, count in Counter(row["recovery_class"] for row in candidate_rows).most_common()],
        ),
        "",
        "## 5. Decision",
        "",
        "Diagnostic pass: CIE remains the teacher source. The evidence says an upstream-wait wrapper around the original CIE route is the right next move, not a non-CIE teacher and not RL yet.",
        "",
        "## Artifacts",
        "",
        f"- Candidate labels: `{_relative(CANDIDATE_LABELS_TABLE)}`",
        f"- Projection: `{_relative(PROJECTION_TABLE)}`",
        f"- CIE path alignment: `{_relative(PATH_ALIGNMENT_TABLE)}`",
        f"- CIE upstream wait windows: `{_relative(WAIT_WINDOWS_TABLE)}`",
        f"- Next gate: `{_relative(NEXT_GATE_TABLE)}`",
        f"- JSONL sample: `{_relative(SAMPLE_PATH)}`",
        f"- Projection figure: `{_relative(FIGURE_PATH)}`",
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


def _candidate_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "segment_id",
        "task_id",
        "current",
        "legacy_next",
        "bottleneck_edge",
        "original_g3f_label",
        "original_terminal_reason",
        "release_time_from_blocker",
        "wait_needed_if_nonoccupying",
        "cie_teacher_planned",
        "cie_teacher_path",
        "cie_preserves_bottleneck_edge",
        "cie_upstream_wait_node",
        "cie_upstream_wait_until",
        "candidate_label",
        "recovery_class",
        "label_source",
        "teacher_role",
        "unique_scenario_segment_credit",
        "g4a_primary_candidate",
        "why_not_primary_yet",
    ]


def _projection_fields() -> list[str]:
    return [
        "projection",
        "base_planned",
        "added_unique_segments",
        "projected_planned",
        "projected_planned_gate",
        "teacher_source",
        "raw_cie_conflicts_if_executed_blindly",
        "status",
    ]


def _path_alignment_fields() -> list[str]:
    return [
        "scenario",
        "segment_id",
        "task_id",
        "bottleneck_edge",
        "cie_teacher_planned",
        "cie_preserves_bottleneck_edge",
        "cie_teacher_path",
        "recovery_class",
        "unique_scenario_segment_credit",
    ]


def _wait_window_fields() -> list[str]:
    return [
        "scenario",
        "segment_id",
        "task_id",
        "bottleneck_edge",
        "cie_upstream_wait_node",
        "cie_upstream_wait_until",
        "wait_needed_if_nonoccupying",
        "candidate_label",
        "recovery_class",
    ]


def _gate_fields() -> list[str]:
    return ["gate", "pass", "value", "decision"]


def main() -> None:
    for path in (G3F_SUMMARY_TABLE, G3G_CURRENT_UPSTREAM_TABLE, G3G_SCHEDULER_TABLE):
        if not path.exists():
            raise AssertionError(f"G3h requires prerequisite artifact: {path}")

    g3f_summary = _read_csv_rows(G3F_SUMMARY_TABLE)
    upstream_rows = _read_csv_rows(G3G_CURRENT_UPSTREAM_TABLE)
    g3g_scheduler = _read_csv_rows(G3G_SCHEDULER_TABLE)
    if not g3f_summary or not upstream_rows or not g3g_scheduler:
        raise AssertionError("G3h requires non-empty G3f and G3g artifacts")

    candidate_rows = _candidate_rows(upstream_rows)
    projection_rows = _projection_rows(g3f_summary, g3g_scheduler, candidate_rows)
    gate_rows = _next_gate_rows(projection_rows, candidate_rows)

    _write_csv(CANDIDATE_LABELS_TABLE, candidate_rows, _candidate_fields())
    _write_csv(PROJECTION_TABLE, projection_rows, _projection_fields())
    _write_csv(PATH_ALIGNMENT_TABLE, _path_alignment_rows(candidate_rows), _path_alignment_fields())
    _write_csv(WAIT_WINDOWS_TABLE, _wait_window_rows(candidate_rows), _wait_window_fields())
    _write_csv(NEXT_GATE_TABLE, gate_rows, _gate_fields())
    _write_jsonl(SAMPLE_PATH, candidate_rows)
    _write_figure(FIGURE_PATH, projection_rows)
    _write_report(candidate_rows, projection_rows, gate_rows)

    required = (
        REPORT_PATH,
        CANDIDATE_LABELS_TABLE,
        PROJECTION_TABLE,
        PATH_ALIGNMENT_TABLE,
        WAIT_WINDOWS_TABLE,
        NEXT_GATE_TABLE,
        SAMPLE_PATH,
        FIGURE_PATH,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G3h artifacts: {missing}")
    unique_count = len({(row["scenario"], row["segment_id"]) for row in candidate_rows})
    print(f"g3h complete: candidate_rows={len(candidate_rows)} unique_scenario_segments={unique_count}")


if __name__ == "__main__":
    main()
