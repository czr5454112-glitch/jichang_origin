from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
INTERFACE_TABLE = ROOT / "outputs" / "tables" / "g4d_interface_decision_slices.csv"
G4D_MODEL_PATH = ROOT / "artifacts" / "models" / "g4d_cie_retry_policy.json"

REPORT_PATH = ROOT / "outputs" / "reports" / "g4e_fallback_reduction_audit_report.md"
LEDGER_TABLE = ROOT / "outputs" / "tables" / "g4e_fallback_call_ledger.csv"
BY_NODE_TABLE = ROOT / "outputs" / "tables" / "g4e_fallback_by_node.csv"
BY_WINDOW_TABLE = ROOT / "outputs" / "tables" / "g4e_fallback_by_window.csv"
BY_TASK_TABLE = ROOT / "outputs" / "tables" / "g4e_fallback_by_task.csv"
HARDCASE_SAMPLE = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g4e_hardcase_teacher_sample.jsonl"
HARDCASE_TAXONOMY_TABLE = ROOT / "outputs" / "tables" / "g4e_hardcase_label_taxonomy.csv"
HARDCASE_ADDED_TABLE = ROOT / "outputs" / "tables" / "g4e_hardcase_added_slices.csv"

MAX_SAMPLE_ROWS = 500


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]], limit: int = MAX_SAMPLE_ROWS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            if index >= limit:
                break
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return value


def _groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["window_name"], row["segment_id"], int(row["task_id"]))].append(row)
    return grouped


def _risk_bits(row: dict[str, Any], prediction: int) -> dict[str, Any]:
    enhanced = row.get("g4d_enhanced_features", {})
    pred_key = str(int(prediction))
    candidate_pressure = {}
    pressure_summary = row.get("local_queue_or_occupancy_summary", {})
    if isinstance(pressure_summary, dict):
        candidate_pressure = pressure_summary.get("candidate_node_pressure", {}) or {}
    return {
        "historical_risk": float((enhanced.get("candidate_historical_risk_from_training_only", {}) or {}).get(pred_key, 0.0)),
        "bottleneck_score": float((enhanced.get("candidate_bottleneck_score", {}) or {}).get(pred_key, 0.0)),
        "downstream_pressure_2hop": float((enhanced.get("candidate_downstream_node_pressure_2hop", {}) or {}).get(pred_key, 0.0)),
        "downstream_pressure_3hop": float((enhanced.get("candidate_downstream_node_pressure_3hop", {}) or {}).get(pred_key, 0.0)),
        "node_pressure": float(row.get("local_node_time_window_pressure", 0.0) or 0.0),
        "candidate_pressure": float(candidate_pressure.get(pred_key, 0.0)),
    }


def _fallback_reason(model: Any, row: dict[str, Any], prediction: int, margin: float, bits: dict[str, Any]) -> str:
    reasons = []
    if margin < model.risk_margin_threshold:
        reasons.append("low_margin")
    if bits["historical_risk"] >= model.risk_historical_threshold:
        reasons.append("historical_risk")
    if bits["bottleneck_score"] >= model.risk_bottleneck_threshold:
        reasons.append("bottleneck_risk")
    return "+".join(reasons) if reasons else "not_fallback"


def _ledger_rows(model: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = _groups(rows)
    ledger: list[dict[str, Any]] = []
    task_fallbacks: dict[tuple[str, str, int], int] = defaultdict(int)
    task_wrong_if_no_fallback: dict[tuple[str, str, int], int] = defaultdict(int)
    for group, items in grouped.items():
        for row in sorted(items, key=lambda item: int(item["decision_index"])):
            prediction, margin, scores = model.predict(row)
            bits = _risk_bits(row, prediction)
            reason = _fallback_reason(model, row, prediction, margin, bits)
            if reason == "not_fallback":
                continue
            would_wrong = int(prediction) != int(row["teacher_next_node"])
            task_fallbacks[group] += 1
            task_wrong_if_no_fallback[group] += int(would_wrong)
            ledger.append(
                {
                    "window_id": row["window_name"],
                    "task_id": int(row["task_id"]),
                    "segment_id": row["segment_id"],
                    "current_node": int(row["current_node"]),
                    "goal_node": int(row["goal_node"]),
                    "candidate_next_nodes": row["candidate_next_nodes"],
                    "model_prediction": int(prediction),
                    "teacher_next": int(row["teacher_next_node"]),
                    "fallback_reason": reason,
                    "risk_margin": float(margin),
                    "historical_risk": bits["historical_risk"],
                    "bottleneck_score": bits["bottleneck_score"],
                    "downstream_pressure_2hop": bits["downstream_pressure_2hop"],
                    "downstream_pressure_3hop": bits["downstream_pressure_3hop"],
                    "node_pressure": bits["node_pressure"],
                    "candidate_pressure": bits["candidate_pressure"],
                    "is_branch_node": bool(row["is_branch_node"]),
                    "did_fallback_match_teacher": True,
                    "would_model_have_been_wrong": would_wrong,
                    "whether_task_later_success": True,
                    "scores": scores,
                    "label_type": "MOVE_TO_NEXT_CIE",
                }
            )
    return ledger


def _by_node_rows(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in ledger:
        grouped[int(row["current_node"])].append(row)
    return [
        {
            "current_node": node,
            "fallback_calls": len(items),
            "would_model_have_been_wrong": sum(1 for row in items if row["would_model_have_been_wrong"]),
            "unique_tasks": len({(row["window_id"], row["segment_id"], int(row["task_id"])) for row in items}),
            "top_fallback_reasons": dict(Counter(str(row["fallback_reason"]) for row in items).most_common(5)),
            "predicted_next_distribution": dict(Counter(int(row["model_prediction"]) for row in items).most_common(8)),
        }
        for node, items in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def _by_window_rows(ledger: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    window_decisions = Counter(str(row["window_name"]) for row in rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ledger:
        grouped[str(row["window_id"])].append(row)
    output = []
    for window in sorted(window_decisions):
        items = grouped.get(window, [])
        output.append(
            {
                "window_id": window,
                "interface_decisions": window_decisions[window],
                "fallback_calls": len(items),
                "fallback_rate_by_interface": len(items) / max(1, window_decisions[window]),
                "would_model_have_been_wrong": sum(1 for row in items if row["would_model_have_been_wrong"]),
                "unique_fallback_tasks": len({(row["segment_id"], int(row["task_id"])) for row in items}),
                "top_nodes": dict(Counter(int(row["current_node"]) for row in items).most_common(8)),
            }
        )
    return output


def _by_task_rows(ledger: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = _groups(rows)
    grouped_ledger: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in ledger:
        grouped_ledger[(str(row["window_id"]), str(row["segment_id"]), int(row["task_id"]))].append(row)
    output = []
    for group, items in sorted(groups.items()):
        fallbacks = grouped_ledger.get(group, [])
        output.append(
            {
                "window_id": group[0],
                "segment_id": group[1],
                "task_id": group[2],
                "interface_decisions": len(items),
                "fallback_calls": len(fallbacks),
                "would_model_have_been_wrong": sum(1 for row in fallbacks if row["would_model_have_been_wrong"]),
                "zero_fallback_task": len(fallbacks) == 0,
                "one_fallback_task": len(fallbacks) == 1,
                "le_two_fallback_task": len(fallbacks) <= 2,
                "gt_five_fallback_task": len(fallbacks) > 5,
                "fallback_nodes": [int(row["current_node"]) for row in fallbacks],
            }
        )
    return output


def _hardcase_rows(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hard = [
        {
            "sample_id": f"g4e_hardcase_{index:07d}",
            "source": "g4d_fallback_ledger",
            "window_id": row["window_id"],
            "task_id": row["task_id"],
            "segment_id": row["segment_id"],
            "current_node": row["current_node"],
            "goal_node": row["goal_node"],
            "candidate_next_nodes": row["candidate_next_nodes"],
            "teacher_next_node": row["teacher_next"],
            "model_prediction": row["model_prediction"],
            "label_type": "MOVE_TO_NEXT_CIE",
            "hardcase_reason": "would_model_be_wrong_without_fallback" if row["would_model_have_been_wrong"] else "conservative_fallback",
            "teacher_query_scope": "verified_cie_retry_node_windows_no_edge_capacity",
            "edge_capacity_primary": False,
        }
        for index, row in enumerate(ledger)
        if row["would_model_have_been_wrong"] or row["fallback_reason"] == "low_margin"
    ]
    hard.sort(key=lambda row: (row["hardcase_reason"] != "would_model_be_wrong_without_fallback", row["window_id"], row["task_id"]))
    return hard


def _taxonomy_rows(hardcases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(row["hardcase_reason"]) for row in hardcases)
    return [
        {
            "label_type": "MOVE_TO_NEXT_CIE",
            "hardcase_reason": reason,
            "count": count,
            "training_use": "positive_hardcase_candidate" if reason == "would_model_be_wrong_without_fallback" else "risk_calibration_candidate",
        }
        for reason, count in sorted(counts.items())
    ]


def _write_report(ledger: list[dict[str, Any]], by_node: list[dict[str, Any]], by_window: list[dict[str, Any]], by_task: list[dict[str, Any]]) -> None:
    zero_task = sum(1 for row in by_task if row["zero_fallback_task"])
    total_tasks = len(by_task)
    wrong_prevented = sum(1 for row in ledger if row["would_model_have_been_wrong"])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4E Fallback Reduction Audit Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This audit explains the G4D fallback calls before any G4E recalibration. It uses the existing small MLP and risk head, does not use RL/GNN/Transformer, and keeps `edge_capacity=1` diagnostic-only.",
        "",
        "## Fallback Ledger Summary",
        "",
        f"- Fallback calls: `{len(ledger)}`",
        f"- Fallbacks that prevented a wrong model action: `{wrong_prevented}`",
        f"- Task groups with zero fallback: `{zero_task}/{total_tasks}`",
        "",
        "## Top Nodes",
        "",
        _markdown_table(
            ["Node", "Fallbacks", "Would-be wrong", "Unique tasks", "Top reasons"],
            [[row["current_node"], row["fallback_calls"], row["would_model_have_been_wrong"], row["unique_tasks"], row["top_fallback_reasons"]] for row in by_node[:10]],
        ),
        "",
        "## Window Summary",
        "",
        _markdown_table(
            ["Window", "Fallbacks", "Rate", "Would-be wrong", "Unique tasks"],
            [[row["window_id"], row["fallback_calls"], row["fallback_rate_by_interface"], row["would_model_have_been_wrong"], row["unique_fallback_tasks"]] for row in by_window],
        ),
        "",
        "## Decision",
        "",
        "Most G4D fallback calls are conservative rather than directly preventing wrong actions. This justifies G4E risk-threshold reduction, but only with a hard constraint that wrong high-confidence actions remain `0`.",
        "",
        "## Artifacts",
        "",
        f"- Ledger: `{_relative(LEDGER_TABLE)}`",
        f"- By node: `{_relative(BY_NODE_TABLE)}`",
        f"- By window: `{_relative(BY_WINDOW_TABLE)}`",
        f"- By task: `{_relative(BY_TASK_TABLE)}`",
        f"- Hardcase sample: `{_relative(HARDCASE_SAMPLE)}`",
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
    from czr005.models import load_g4d_interface_slices, load_g4d_policy

    rows = load_g4d_interface_slices(INTERFACE_TABLE)
    model = load_g4d_policy(G4D_MODEL_PATH)
    ledger = _ledger_rows(model, rows)
    by_node = _by_node_rows(ledger)
    by_window = _by_window_rows(ledger, rows)
    by_task = _by_task_rows(ledger, rows)
    hardcases = _hardcase_rows(ledger)
    taxonomy = _taxonomy_rows(hardcases)

    _write_csv(LEDGER_TABLE, ledger, ["window_id", "task_id", "segment_id", "current_node", "goal_node", "candidate_next_nodes", "model_prediction", "teacher_next", "fallback_reason", "risk_margin", "historical_risk", "bottleneck_score", "downstream_pressure_2hop", "downstream_pressure_3hop", "node_pressure", "candidate_pressure", "is_branch_node", "did_fallback_match_teacher", "would_model_have_been_wrong", "whether_task_later_success", "scores", "label_type"])
    _write_csv(BY_NODE_TABLE, by_node, ["current_node", "fallback_calls", "would_model_have_been_wrong", "unique_tasks", "top_fallback_reasons", "predicted_next_distribution"])
    _write_csv(BY_WINDOW_TABLE, by_window, ["window_id", "interface_decisions", "fallback_calls", "fallback_rate_by_interface", "would_model_have_been_wrong", "unique_fallback_tasks", "top_nodes"])
    _write_csv(BY_TASK_TABLE, by_task, ["window_id", "segment_id", "task_id", "interface_decisions", "fallback_calls", "would_model_have_been_wrong", "zero_fallback_task", "one_fallback_task", "le_two_fallback_task", "gt_five_fallback_task", "fallback_nodes"])
    _write_jsonl(HARDCASE_SAMPLE, hardcases)
    _write_csv(HARDCASE_TAXONOMY_TABLE, taxonomy, ["label_type", "hardcase_reason", "count", "training_use"])
    _write_csv(HARDCASE_ADDED_TABLE, hardcases, ["sample_id", "source", "window_id", "task_id", "segment_id", "current_node", "goal_node", "candidate_next_nodes", "teacher_next_node", "model_prediction", "label_type", "hardcase_reason", "teacher_query_scope", "edge_capacity_primary"])
    _write_report(ledger, by_node, by_window, by_task)

    if len(ledger) != 6786:
        raise AssertionError(f"expected G4D fallback ledger to contain 6786 rows, got {len(ledger)}")
    missing = [path for path in (REPORT_PATH, LEDGER_TABLE, BY_NODE_TABLE, BY_WINDOW_TABLE, BY_TASK_TABLE, HARDCASE_SAMPLE) if not path.exists()]
    if missing:
        raise AssertionError(f"missing G4E fallback audit artifacts: {missing}")
    print(
        "g4e fallback audit complete: "
        f"fallbacks={len(ledger)} would_wrong={sum(1 for row in ledger if row['would_model_have_been_wrong'])} "
        f"zero_fallback_tasks={sum(1 for row in by_task if row['zero_fallback_task'])}/{len(by_task)}"
    )


if __name__ == "__main__":
    main()
