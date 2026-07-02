from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any, Iterable
import zlib


ROOT = Path(__file__).resolve().parents[2]
INTERFACE_TABLE = ROOT / "outputs" / "tables" / "g4d_interface_decision_slices.csv"

REPORT_PATH = ROOT / "outputs" / "reports" / "g4d_risky_branch_audit.md"
CASES_TABLE = ROOT / "outputs" / "tables" / "g4d_risky_branch_cases.csv"
FEATURE_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4d_risky_branch_feature_summary.csv"
ERROR_MODES_TABLE = ROOT / "outputs" / "tables" / "g4d_risky_branch_error_modes.csv"
FIGURE_PATH = ROOT / "outputs" / "figures" / "g4d_risky_branch_heatmap.png"

RISKY_BRANCHES = {
    6: (8, 12),
    11: (13, 14),
    16: (17, 21),
    19: (18, 25),
}


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return value


def _risk_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        current = int(row["current_node"])
        if current not in RISKY_BRANCHES:
            continue
        target_pair = set(RISKY_BRANCHES[current])
        candidate_set = set(int(value) for value in row["candidate_next_nodes"])
        if not target_pair.issubset(candidate_set):
            continue
        teacher = int(row["teacher_next_node"])
        enhanced = row.get("g4d_enhanced_features", {})
        candidate_key = str(teacher)
        cases.append(
            {
                "sample_id": row["sample_id"],
                "window_name": row["window_name"],
                "context": row["context"],
                "window_size": row["window_size"],
                "task_id": row["task_id"],
                "segment_id": row["segment_id"],
                "current_node": current,
                "goal_node": row["goal_node"],
                "candidate_next_nodes": row["candidate_next_nodes"],
                "teacher_next_node": teacher,
                "time_slack": row["time_slack"],
                "local_node_time_window_pressure": row["local_node_time_window_pressure"],
                "teacher_static_remaining_hops": _enhanced(enhanced, "candidate_static_remaining_hops_to_goal", candidate_key),
                "teacher_second_best_gap": _enhanced(enhanced, "candidate_static_second_best_gap", candidate_key),
                "teacher_downstream_pressure_2hop": _enhanced(enhanced, "candidate_downstream_node_pressure_2hop", candidate_key),
                "teacher_downstream_pressure_3hop": _enhanced(enhanced, "candidate_downstream_node_pressure_3hop", candidate_key),
                "teacher_goal_direction_score": _enhanced(enhanced, "candidate_goal_direction_score", candidate_key),
                "teacher_historical_risk": _enhanced(enhanced, "candidate_historical_risk_from_training_only", candidate_key),
            }
        )
    return cases


def _enhanced(enhanced: dict[str, Any], field: str, key: str) -> float:
    value = enhanced.get(field, {})
    if isinstance(value, dict):
        return float(value.get(key, 0.0))
    return 0.0


def _feature_summary(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in cases:
        groups[(int(row["current_node"]), int(row["teacher_next_node"]))].append(row)
    output: list[dict[str, Any]] = []
    for (current, teacher), items in sorted(groups.items()):
        windows = Counter(str(row["window_name"]) for row in items)
        output.append(
            {
                "current_node": current,
                "teacher_next_node": teacher,
                "case_count": len(items),
                "window_count": len(windows),
                "mean_time_slack": _mean(row["time_slack"] for row in items),
                "mean_local_node_pressure": _mean(row["local_node_time_window_pressure"] for row in items),
                "mean_teacher_static_remaining_hops": _mean(row["teacher_static_remaining_hops"] for row in items),
                "mean_teacher_second_best_gap": _mean(row["teacher_second_best_gap"] for row in items),
                "mean_teacher_downstream_pressure_2hop": _mean(row["teacher_downstream_pressure_2hop"] for row in items),
                "mean_teacher_downstream_pressure_3hop": _mean(row["teacher_downstream_pressure_3hop"] for row in items),
                "mean_teacher_goal_direction_score": _mean(row["teacher_goal_direction_score"] for row in items),
                "mean_teacher_historical_risk": _mean(row["teacher_historical_risk"] for row in items),
            }
        )
    return output


def _error_modes(cases: list[dict[str, Any]], summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_current: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_summary = {(int(row["current_node"]), int(row["teacher_next_node"])): row for row in summary_rows}
    for row in cases:
        by_current[int(row["current_node"])].append(row)
    output: list[dict[str, Any]] = []
    for current, items in sorted(by_current.items()):
        teacher_counts = Counter(int(row["teacher_next_node"]) for row in items)
        total = sum(teacher_counts.values())
        entropy = _entropy(teacher_counts)
        options = RISKY_BRANCHES[current]
        pressure_gap = _summary_gap(by_summary, current, options, "mean_teacher_downstream_pressure_2hop")
        hop_gap = _summary_gap(by_summary, current, options, "mean_teacher_static_remaining_hops")
        if total < 30:
            mode = "sample_limited"
            recommendation = "keep_fallback_until_more_large-window_samples"
        elif entropy > 0.35 and abs(pressure_gap) < 1.0 and abs(hop_gap) < 1.0:
            mode = "local_features_overlap_tie_sensitive"
            recommendation = "risk_head_or_fallback_still_needed"
        elif entropy > 0.35:
            mode = "mixed_context_branch_preference"
            recommendation = "use_enhanced_features_and_calibrated_risk_head"
        else:
            mode = "learnable_majority_branch"
            recommendation = "candidate_for_reduced_fallback"
        output.append(
            {
                "current_node": current,
                "target_candidates": list(options),
                "case_count": total,
                "teacher_distribution": dict(sorted(teacher_counts.items())),
                "entropy": entropy,
                "mean_2hop_pressure_gap_between_targets": pressure_gap,
                "mean_hop_gap_between_targets": hop_gap,
                "diagnosis": mode,
                "recommendation": recommendation,
            }
        )
    return output


def _summary_gap(summary: dict[tuple[int, int], dict[str, Any]], current: int, options: tuple[int, int], field: str) -> float:
    left = summary.get((current, options[0]), {}).get(field, 0.0)
    right = summary.get((current, options[1]), {}).get(field, 0.0)
    return float(left) - float(right)


def _mean(values: Iterable[Any]) -> float:
    data = [float(value) for value in values]
    return sum(data) / len(data) if data else 0.0


def _entropy(counts: Counter[int]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log(p, 2)
    return entropy


def _write_heatmap(path: Path, cases: list[dict[str, Any]]) -> None:
    rows = sorted(RISKY_BRANCHES)
    cols = sorted({candidate for values in RISKY_BRANCHES.values() for candidate in values})
    matrix = [[0 for _ in cols] for _ in rows]
    row_index = {value: index for index, value in enumerate(rows)}
    col_index = {value: index for index, value in enumerate(cols)}
    for item in cases:
        current = int(item["current_node"])
        teacher = int(item["teacher_next_node"])
        if current in row_index and teacher in col_index:
            matrix[row_index[current]][col_index[teacher]] += 1
    max_value = max([max(row) for row in matrix] or [1])
    cell = 28
    width = max(1, len(cols) * cell)
    height = max(1, len(rows) * cell)
    pixels: list[tuple[int, int, int]] = []
    for y in range(height):
        matrix_y = y // cell
        for x in range(width):
            matrix_x = x // cell
            value = matrix[matrix_y][matrix_x]
            intensity = int(255 * value / max_value) if max_value else 0
            pixels.append((255 - intensity // 4, 245 - intensity // 2, 255 - intensity))
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_png(path, width, height, pixels)


def _write_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int]]) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y * width + x])
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    content = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)),
            chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(content)


def _write_report(cases: list[dict[str, Any]], summary_rows: list[dict[str, Any]], error_rows: list[dict[str, Any]]) -> None:
    total = len(cases)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4D Risky Branch Audit",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This audit focuses on the four G4C risky branch families. It uses the G4D large-window CIE retry teacher slices and does not train RL or use forbidden route labels as model inputs.",
        "",
        "## Summary",
        "",
        f"- Risky branch cases: `{total}`",
        f"- Target current nodes: `{sorted(RISKY_BRANCHES)}`",
        "",
        "## Teacher Distribution",
        "",
        _markdown_table(
            ["Current", "Candidates", "Cases", "Distribution", "Diagnosis", "Recommendation"],
            [
                [
                    row["current_node"],
                    row["target_candidates"],
                    row["case_count"],
                    row["teacher_distribution"],
                    row["diagnosis"],
                    row["recommendation"],
                ]
                for row in error_rows
            ],
        ),
        "",
        "## Decision",
        "",
        "The risky branches are no longer sample-starved in the large-window slice, but several remain mixed-context or locally overlapping. G4D should use the enhanced local features plus a calibrated risk head, not a blanket claim that the branches are fully learned.",
        "",
        "## Artifacts",
        "",
        f"- Cases: `{_relative(CASES_TABLE)}`",
        f"- Feature summary: `{_relative(FEATURE_SUMMARY_TABLE)}`",
        f"- Error modes: `{_relative(ERROR_MODES_TABLE)}`",
        f"- Heatmap: `{_relative(FIGURE_PATH)}`",
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
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    _prepare_imports()
    from czr005.models import load_g4d_interface_slices

    rows = load_g4d_interface_slices(INTERFACE_TABLE)
    cases = _risk_cases(rows)
    summary_rows = _feature_summary(cases)
    error_rows = _error_modes(cases, summary_rows)
    _write_csv(
        CASES_TABLE,
        cases,
        [
            "sample_id",
            "window_name",
            "context",
            "window_size",
            "task_id",
            "segment_id",
            "current_node",
            "goal_node",
            "candidate_next_nodes",
            "teacher_next_node",
            "time_slack",
            "local_node_time_window_pressure",
            "teacher_static_remaining_hops",
            "teacher_second_best_gap",
            "teacher_downstream_pressure_2hop",
            "teacher_downstream_pressure_3hop",
            "teacher_goal_direction_score",
            "teacher_historical_risk",
        ],
    )
    _write_csv(
        FEATURE_SUMMARY_TABLE,
        summary_rows,
        [
            "current_node",
            "teacher_next_node",
            "case_count",
            "window_count",
            "mean_time_slack",
            "mean_local_node_pressure",
            "mean_teacher_static_remaining_hops",
            "mean_teacher_second_best_gap",
            "mean_teacher_downstream_pressure_2hop",
            "mean_teacher_downstream_pressure_3hop",
            "mean_teacher_goal_direction_score",
            "mean_teacher_historical_risk",
        ],
    )
    _write_csv(
        ERROR_MODES_TABLE,
        error_rows,
        [
            "current_node",
            "target_candidates",
            "case_count",
            "teacher_distribution",
            "entropy",
            "mean_2hop_pressure_gap_between_targets",
            "mean_hop_gap_between_targets",
            "diagnosis",
            "recommendation",
        ],
    )
    _write_heatmap(FIGURE_PATH, cases)
    _write_report(cases, summary_rows, error_rows)

    if not cases:
        raise AssertionError("G4D risky branch audit produced no cases")
    missing = [path for path in (REPORT_PATH, CASES_TABLE, FEATURE_SUMMARY_TABLE, ERROR_MODES_TABLE, FIGURE_PATH) if not path.exists()]
    if missing:
        raise AssertionError(f"missing G4D risky branch artifacts: {missing}")
    print(f"g4d risky branch audit complete: cases={len(cases)} current_nodes={len(error_rows)}")


if __name__ == "__main__":
    main()
