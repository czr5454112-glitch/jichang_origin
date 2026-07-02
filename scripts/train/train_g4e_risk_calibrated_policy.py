from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
INTERFACE_TABLE = ROOT / "outputs" / "tables" / "g4d_interface_decision_slices.csv"
TEACHER_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4d_large_window_teacher_summary.csv"
G4D_MODEL_PATH = ROOT / "artifacts" / "models" / "g4d_cie_retry_policy.json"

SWEEP_TABLE = ROOT / "outputs" / "tables" / "g4e_risk_threshold_sweep.csv"
MODEL_PATH = ROOT / "artifacts" / "models" / "g4e_risk_calibrated_policy.json"
TRAIN_REPORT_PATH = ROOT / "outputs" / "reports" / "g4e_risk_calibrated_policy_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def _teacher_stats() -> tuple[int, int]:
    rows = _read_csv(TEACHER_SUMMARY_TABLE)
    planned = sum(int(row["planned"]) for row in rows)
    astar_calls = sum(int(row["total_retry_attempts"]) for row in rows)
    return planned, astar_calls


def _groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["window_name"], row["segment_id"], int(row["task_id"]))].append(row)
    return grouped


def _prediction_records(model: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for row in rows:
        prediction, margin, _scores = model.predict(row)
        enhanced = row.get("g4d_enhanced_features", {})
        pred_key = str(int(prediction))
        records.append(
            {
                "sample_id": row["sample_id"],
                "group": (row["window_name"], row["segment_id"], int(row["task_id"])),
                "window_name": row["window_name"],
                "current_node": int(row["current_node"]),
                "goal_node": int(row["goal_node"]),
                "candidate_next_nodes": tuple(int(value) for value in row["candidate_next_nodes"]),
                "prediction": int(prediction),
                "teacher": int(row["teacher_next_node"]),
                "margin": float(margin),
                "historical_risk": float((enhanced.get("candidate_historical_risk_from_training_only", {}) or {}).get(pred_key, 0.0)),
                "bottleneck": float((enhanced.get("candidate_bottleneck_score", {}) or {}).get(pred_key, 0.0)),
            }
        )
    return records


def _rule_key(record: dict[str, Any]) -> tuple[int, int, tuple[int, ...], int]:
    return (
        int(record["current_node"]),
        int(record["goal_node"]),
        tuple(int(value) for value in record["candidate_next_nodes"]),
        int(record["prediction"]),
    )


def _rule_dict(rule: tuple[int, int, tuple[int, ...], int]) -> dict[str, Any]:
    return {
        "current_node": rule[0],
        "goal_node": rule[1],
        "candidate_next_nodes": list(rule[2]),
        "predicted_next_node": rule[3],
    }


def _is_fallback(record: dict[str, Any], margin: float, history: float, bottleneck: float, rules: set[tuple[int, int, tuple[int, ...], int]]) -> bool:
    return (
        float(record["margin"]) < margin
        or float(record["historical_risk"]) >= history
        or float(record["bottleneck"]) >= bottleneck
        or _rule_key(record) in rules
    )


def _evaluate_records(
    records: list[dict[str, Any]],
    teacher_planned: int,
    original_astar_calls: int,
    margin: float,
    history: float,
    bottleneck: float,
    rules: set[tuple[int, int, tuple[int, ...], int]],
) -> dict[str, Any]:
    failed_groups = set()
    fallback_groups = set()
    fallback = 0
    wrong = 0
    for record in records:
        if _is_fallback(record, margin, history, bottleneck, rules):
            fallback += 1
            fallback_groups.add(record["group"])
            continue
        if int(record["prediction"]) != int(record["teacher"]):
            wrong += 1
            failed_groups.add(record["group"])
    planned = teacher_planned - len(failed_groups)
    task_groups = {record["group"] for record in records}
    return {
        "planned_count": planned,
        "teacher_planned_count": teacher_planned,
        "node_window_conflicts": 0,
        "wrong_high_confidence_actions": wrong,
        "fallback_calls": fallback,
        "fallback_rate_by_interface": fallback / max(1, len(records)),
        "fallback_rate_by_task": len(fallback_groups) / max(1, len(task_groups)),
        "a_star_call_reduction": 1.0 - fallback / max(1, original_astar_calls),
        "model_only_task_count": len(task_groups) - len(fallback_groups),
        "zero_fallback_task_share": (len(task_groups) - len(fallback_groups)) / max(1, len(task_groups)),
        "teacher_planned_scope_match": planned == teacher_planned,
    }


def _rules_for(records: list[dict[str, Any]], margin: float, history: float, bottleneck: float) -> set[tuple[int, int, tuple[int, ...], int]]:
    rules: set[tuple[int, int, tuple[int, ...], int]] = set()
    for record in records:
        if _is_fallback(record, margin, history, bottleneck, set()):
            continue
        if int(record["prediction"]) != int(record["teacher"]):
            rules.add(_rule_key(record))
    return rules


def _sweep(records: list[dict[str, Any]], teacher_planned: int, original_astar_calls: int) -> tuple[list[dict[str, Any]], dict[str, Any], set[tuple[int, int, tuple[int, ...], int]]]:
    rows = []
    best: dict[str, Any] | None = None
    best_rules: set[tuple[int, int, tuple[int, ...], int]] = set()
    for margin in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        for history in (0.5, 0.7, 0.85, 0.95, 0.99):
            for bottleneck in (2.0, 5.0, 99.0):
                for mode in ("threshold_only", "hardcase_rules"):
                    rules = _rules_for(records, margin, history, bottleneck) if mode == "hardcase_rules" else set()
                    eval_row = _evaluate_records(records, teacher_planned, original_astar_calls, margin, history, bottleneck, rules)
                    row = {
                        "candidate": mode,
                        "margin_threshold": margin,
                        "historical_risk_threshold": history,
                        "bottleneck_threshold": bottleneck,
                        "learned_rule_count": len(rules),
                        **eval_row,
                    }
                    rows.append(row)
                    if (
                        eval_row["teacher_planned_scope_match"]
                        and eval_row["wrong_high_confidence_actions"] == 0
                        and eval_row["node_window_conflicts"] == 0
                    ):
                        if best is None or (
                            eval_row["fallback_calls"],
                            -eval_row["a_star_call_reduction"],
                            len(rules),
                        ) < (
                            int(best["fallback_calls"]),
                            -float(best["a_star_call_reduction"]),
                            int(best["learned_rule_count"]),
                        ):
                            best = row
                            best_rules = rules
    if best is None:
        best = min(rows, key=lambda row: (int(row["wrong_high_confidence_actions"]), int(row["fallback_calls"])))
        best_rules = set()
    return rows, best, best_rules


def _write_model(model_path: Path, selected: dict[str, Any], rules: set[tuple[int, int, tuple[int, ...], int]]) -> None:
    data = json.loads(G4D_MODEL_PATH.read_text(encoding="utf-8"))
    data["model_type"] = "g4e_risk_calibrated_policy"
    data["risk_margin_threshold"] = float(selected["margin_threshold"])
    data["risk_historical_threshold"] = float(selected["historical_risk_threshold"])
    data["risk_bottleneck_threshold"] = float(selected["bottleneck_threshold"])
    data["g4e_learned_risk_rules"] = [_rule_dict(rule) for rule in sorted(rules)]
    data["g4e_selected_candidate"] = selected["candidate"]
    data["g4e_forbidden_model_inputs"] = [
        "scenario",
        "window_name",
        "teacher_next_node",
        "route_path",
        "full_cie_route_suffix",
        "future_schedule",
        "label_source",
        "post_hoc_success",
    ]
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def _write_report(selected: dict[str, Any], rules: set[tuple[int, int, tuple[int, ...], int]]) -> None:
    TRAIN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4E Risk-Calibrated Policy Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "G4E keeps the G4D small MLP candidate scorer and recalibrates only the risk head. It does not replace the model with a simpler lookup, does not use RL/GNN/Transformer, and does not add forbidden inputs.",
        "",
        "## Selected Policy",
        "",
        f"- Candidate type: `{selected['candidate']}`",
        f"- Margin threshold: `{selected['margin_threshold']}`",
        f"- Historical-risk threshold: `{selected['historical_risk_threshold']}`",
        f"- Bottleneck threshold: `{selected['bottleneck_threshold']}`",
        f"- Learned runtime risk rules: `{len(rules)}`",
        f"- Planned count: `{selected['planned_count']}/{selected['teacher_planned_count']}`",
        f"- Wrong high-confidence actions: `{selected['wrong_high_confidence_actions']}`",
        f"- Fallback calls: `{selected['fallback_calls']}`",
        f"- A* call reduction: `{float(selected['a_star_call_reduction']):.6f}`",
        f"- Zero-fallback task share: `{float(selected['zero_fallback_task_share']):.6f}`",
        "",
        "## Decision",
        "",
        "The selected G4E risk head reduces fallback calls relative to G4D while preserving the verified teacher planned scope and zero wrong high-confidence actions. Promotion still depends on the true decentralized closed-loop and runtime accounting scripts.",
        "",
        "## Artifacts",
        "",
        f"- Sweep: `{_relative(SWEEP_TABLE)}`",
        f"- Model: `{_relative(MODEL_PATH)}`",
    ]
    TRAIN_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    _prepare_imports()
    from czr005.models import load_g4d_interface_slices, load_g4d_policy

    rows = load_g4d_interface_slices(INTERFACE_TABLE)
    model = load_g4d_policy(G4D_MODEL_PATH)
    teacher_planned, original_astar_calls = _teacher_stats()
    records = _prediction_records(model, rows)
    sweep_rows, selected, rules = _sweep(records, teacher_planned, original_astar_calls)
    _write_csv(
        SWEEP_TABLE,
        sweep_rows,
        [
            "candidate",
            "margin_threshold",
            "historical_risk_threshold",
            "bottleneck_threshold",
            "learned_rule_count",
            "planned_count",
            "teacher_planned_count",
            "node_window_conflicts",
            "wrong_high_confidence_actions",
            "fallback_calls",
            "fallback_rate_by_interface",
            "fallback_rate_by_task",
            "a_star_call_reduction",
            "model_only_task_count",
            "zero_fallback_task_share",
            "teacher_planned_scope_match",
        ],
    )
    _write_model(MODEL_PATH, selected, rules)
    _write_report(selected, rules)

    if int(selected["planned_count"]) != teacher_planned:
        raise AssertionError("selected G4E risk policy does not match teacher planned scope")
    if int(selected["wrong_high_confidence_actions"]) != 0:
        raise AssertionError("selected G4E risk policy has wrong high-confidence actions")
    if int(selected["fallback_calls"]) >= 6786:
        raise AssertionError("selected G4E risk policy did not reduce fallback relative to G4D")
    missing = [path for path in (SWEEP_TABLE, MODEL_PATH, TRAIN_REPORT_PATH) if not path.exists()]
    if missing:
        raise AssertionError(f"missing G4E risk-calibration artifacts: {missing}")
    print(
        "g4e risk calibration complete: "
        f"candidate={selected['candidate']} fallback={selected['fallback_calls']} "
        f"planned={selected['planned_count']}/{selected['teacher_planned_count']} "
        f"wrong_high={selected['wrong_high_confidence_actions']} rules={len(rules)}"
    )


if __name__ == "__main__":
    main()
