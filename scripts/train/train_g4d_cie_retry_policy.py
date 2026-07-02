from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
INTERFACE_TABLE = ROOT / "outputs" / "tables" / "g4d_interface_decision_slices.csv"
SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4d_large_window_teacher_summary.csv"
G4C_CLOSED_LOOP_TABLE = ROOT / "outputs" / "tables" / "g4c_closed_loop_comparison.csv"

MODEL_PATH = ROOT / "artifacts" / "models" / "g4d_cie_retry_policy.json"
FEATURE_REPORT_PATH = ROOT / "outputs" / "reports" / "g4d_feature_safety_and_ablation_report.md"
TRAIN_REPORT_PATH = ROOT / "outputs" / "reports" / "g4d_policy_training_report.md"
FEATURE_SCHEMA_TABLE = ROOT / "outputs" / "tables" / "g4d_feature_schema.csv"
FORBIDDEN_AUDIT_TABLE = ROOT / "outputs" / "tables" / "g4d_forbidden_feature_audit.csv"
FEATURE_ABLATION_TABLE = ROOT / "outputs" / "tables" / "g4d_feature_ablation.csv"
OFFLINE_ACCURACY_TABLE = ROOT / "outputs" / "tables" / "g4d_offline_accuracy.csv"
RISK_CALIBRATION_TABLE = ROOT / "outputs" / "tables" / "g4d_risk_head_calibration.csv"
ABSTAIN_SWEEP_TABLE = ROOT / "outputs" / "tables" / "g4d_abstain_policy_sweep.csv"
HISTORY_TABLE = ROOT / "outputs" / "tables" / "g4d_training_history.csv"


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


def _split_rows(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["split"] == split]


def _feature_schema_rows(feature_names: Iterable[str]) -> list[dict[str, Any]]:
    rows = [
        ("sample_id", "metadata", False, False, "stable row id"),
        ("window_name", "metadata", False, False, "large-window audit key"),
        ("scenario", "metadata", False, False, "metadata-only split/audit key; not a model input"),
        ("context", "metadata", False, False, "audit context, not a model input"),
        ("current_node", "runtime_feature", True, False, "current bag node"),
        ("goal_node", "runtime_feature", True, False, "task destination"),
        ("candidate_next_nodes", "runtime_feature", True, False, "available outgoing neighbors"),
        ("current_time", "runtime_feature", True, False, "local decision time"),
        ("time_slack", "runtime_feature", True, False, "deadline/std slack at decision time"),
        ("local_queue_or_occupancy_summary", "runtime_feature", True, False, "local node-window pressure summary"),
        ("g4d_enhanced_features", "runtime_feature", True, False, "runtime/static local enhanced candidate features"),
        ("source_retry_pressure", "runtime_feature", True, False, "source retry pressure available at admission"),
        ("unfinished_task_queue_size_near_current_source", "runtime_feature", True, False, "local source retry queue pressure"),
        ("teacher_next_node", "label", False, True, "supervision target only"),
        ("route_path", "forbidden_label_context", False, True, "full teacher route is forbidden as model input"),
        ("label_source", "metadata", False, False, "not emitted into G4D model rows"),
        ("post_hoc_success", "forbidden_posthoc", False, True, "not emitted into G4D model rows"),
    ]
    rows.extend((name, "featurized_model_input", True, False, "derived scalar consumed by the tiny scorer") for name in feature_names)
    return [
        {
            "field": field,
            "scope": scope,
            "allowed_model_input": allowed,
            "contains_label": contains_label,
            "notes": notes,
        }
        for field, scope, allowed, contains_label, notes in rows
    ]


def _forbidden_audit_rows(model: Any, schema_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feature_names = set(model.to_dict()["feature_names"])
    schema = {row["field"]: row for row in schema_rows}
    forbidden = [
        "scenario",
        "teacher_next_node",
        "route_path",
        "full_cie_route_suffix",
        "future_schedule",
        "future_sipp_schedule",
        "label_source",
        "post_hoc_success",
        "post_hoc_success_flag",
    ]
    rows = []
    for name in forbidden:
        rows.append(
            {
                "check": f"{name}_not_in_model_features",
                "pass": name not in feature_names,
                "value": sorted(feature_names),
                "threshold": "forbidden feature absent",
                "decision": "pass" if name not in feature_names else "block_g4d",
            }
        )
    rows.append(
        {
            "check": "scenario_schema_metadata_only",
            "pass": str(schema["scenario"]["allowed_model_input"]) == "False",
            "value": schema["scenario"]["allowed_model_input"],
            "threshold": "scenario metadata only",
            "decision": "pass" if str(schema["scenario"]["allowed_model_input"]) == "False" else "block_g4d",
        }
    )
    return rows


def _heuristic_top1(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    correct = 0
    for row in rows:
        shortest = row["candidate_shortest_time_to_goal"]
        travel = row["candidate_travel_time"]
        candidates = [int(value) for value in row["candidate_next_nodes"]]
        prediction = min(candidates, key=lambda node: (float(shortest[str(node)]) + float(travel[str(node)]), int(node)))
        correct += int(prediction == int(row["teacher_next_node"]))
    return correct / len(rows)


def _offline_rows(model: Any, rows_by_split: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    from czr005.models import evaluate_g4d_top1

    output = []
    for split, rows in rows_by_split.items():
        model_top1 = evaluate_g4d_top1(model, rows)
        heuristic_top1 = _heuristic_top1(rows)
        output.append(
            {
                "split": split,
                "sample_count": len(rows),
                "model_top1": model_top1,
                "shortest_time_heuristic_top1": heuristic_top1,
                "model_beats_shortest_time": model_top1 > heuristic_top1,
            }
        )
    return output


def _ablation_rows(model: Any, rows: list[dict[str, Any]], val_rows: list[dict[str, Any]], test_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from czr005.models import evaluate_g4d_top1

    specs = {
        "none": set(),
        "no_enhanced_pressure": {
            "candidate_downstream_node_pressure_2hop_scaled",
            "candidate_downstream_node_pressure_3hop_scaled",
            "candidate_bottleneck_score_scaled",
        },
        "no_static_topology": {
            "candidate_static_remaining_hops_to_goal_scaled",
            "candidate_static_second_best_gap_scaled",
            "candidate_goal_direction_score_scaled",
        },
        "no_historical_risk": {"candidate_historical_risk_from_training_only_scaled"},
        "no_source_retry_pressure": {
            "source_retry_pressure_scaled",
            "unfinished_task_queue_size_near_current_source_scaled",
        },
        "no_base_distance": {
            "candidate_shortest_time_to_goal_scaled",
            "candidate_travel_time_scaled",
        },
    }
    return [
        {
            "ablation": name,
            "all_top1": evaluate_g4d_top1(model, rows, ablation=disabled),
            "val_top1": evaluate_g4d_top1(model, val_rows, ablation=disabled),
            "test_top1": evaluate_g4d_top1(model, test_rows, ablation=disabled),
        }
        for name, disabled in specs.items()
    ]


def _fit_numpy_mlp(rows: list[dict[str, Any]], hidden_dim: int = 22, epochs: int = 70, batch_size: int = 2048) -> tuple[Any, list[dict[str, Any]]]:
    from czr005.models import G4D_FEATURE_NAMES, G4DCieRetryPolicy
    from czr005.models.g4d_cie_retry import featurize_g4d_slice

    features: list[list[float]] = []
    labels: list[float] = []
    for item in rows:
        candidate_features, candidates = featurize_g4d_slice(item)
        teacher = int(item["teacher_next_node"])
        for row, candidate in zip(candidate_features, candidates):
            features.append(row)
            labels.append(1.0 if int(candidate) == teacher else 0.0)
    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    rng = np.random.default_rng(127)
    w1 = rng.normal(0.0, 0.07, size=(len(G4D_FEATURE_NAMES), hidden_dim))
    b1 = np.zeros(hidden_dim, dtype=np.float64)
    w2 = rng.normal(0.0, 0.07, size=(hidden_dim,))
    b2 = 0.0
    history: list[dict[str, Any]] = []
    for epoch in range(1, epochs + 1):
        order = rng.permutation(len(x))
        total_loss = 0.0
        correct = 0
        for start in range(0, len(order), batch_size):
            batch_index = order[start : start + batch_size]
            xb = x[batch_index]
            yb = y[batch_index]
            hidden = np.tanh(xb @ w1 + b1)
            logits = hidden @ w2 + b2
            probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -40.0, 40.0)))
            total_loss += float(np.mean(-(yb * np.log(probs + 1.0e-12) + (1.0 - yb) * np.log(1.0 - probs + 1.0e-12))))
            correct += int(np.sum((probs >= 0.5) == (yb >= 0.5)))
            grad = (probs - yb) / len(yb)
            grad_w2 = hidden.T @ grad
            grad_b2 = float(np.sum(grad))
            grad_hidden = grad[:, None] * w2[None, :]
            grad_z = grad_hidden * (1.0 - hidden * hidden)
            grad_w1 = xb.T @ grad_z
            grad_b1 = np.sum(grad_z, axis=0)
            learning_rate = 0.035
            w1 -= learning_rate * grad_w1
            b1 -= learning_rate * grad_b1
            w2 -= learning_rate * grad_w2
            b2 -= learning_rate * grad_b2
        history.append(
            {
                "epoch": epoch,
                "loss": total_loss / max(1, (len(order) + batch_size - 1) // batch_size),
                "top1": correct / max(1, len(order)),
            }
        )
    model = G4DCieRetryPolicy(
        w1=w1.tolist(),
        b1=b1.tolist(),
        w2=w2.tolist(),
        b2=float(b2),
    )
    return model, history


def _prediction_records(model: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        prediction, margin, _ = model.predict(row)
        enhanced = row.get("g4d_enhanced_features", {})
        historical = enhanced.get("candidate_historical_risk_from_training_only", {})
        bottleneck = enhanced.get("candidate_bottleneck_score", {})
        pred_key = str(int(prediction))
        records.append(
            {
                "group": (row["window_name"], row["segment_id"], int(row["task_id"])),
                "prediction": int(prediction),
                "teacher": int(row["teacher_next_node"]),
                "margin": float(margin),
                "historical_risk": float(historical.get(pred_key, 0.0)),
                "bottleneck": float(bottleneck.get(pred_key, 0.0)),
            }
        )
    return records


def _eval_prediction_records(
    records: list[dict[str, Any]],
    margin_threshold: float,
    history_threshold: float,
    bottleneck_threshold: float,
) -> dict[str, Any]:
    groups = {record["group"] for record in records}
    failed_groups = set()
    fallback = 0
    wrong_high = 0
    for record in records:
        should_fallback = (
            float(record["margin"]) < margin_threshold
            or float(record["historical_risk"]) >= history_threshold
            or float(record["bottleneck"]) >= bottleneck_threshold
        )
        if should_fallback:
            fallback += 1
            continue
        if int(record["prediction"]) != int(record["teacher"]):
            wrong_high += 1
            failed_groups.add(record["group"])
    return {
        "route_groups": len(groups),
        "planned": len(groups) - len(failed_groups),
        "wrong_high_confidence_actions": wrong_high,
        "fallback_actions": fallback,
        "fallback_rate": fallback / max(1, len(records)),
        "model_decisions": len(records),
    }


def _route_eval(
    model: Any,
    rows: list[dict[str, Any]],
    margin_threshold: float,
    history_threshold: float,
    bottleneck_threshold: float,
) -> dict[str, Any]:
    return _eval_prediction_records(_prediction_records(model, rows), margin_threshold, history_threshold, bottleneck_threshold)


def _risk_sweep(model: Any, train_rows: list[dict[str, Any]], val_rows: list[dict[str, Any]], all_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sweep: list[dict[str, Any]] = []
    train_records = _prediction_records(model, train_rows)
    val_records = _prediction_records(model, val_rows)
    all_records = _prediction_records(model, all_rows)
    for margin in (0.0, 0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 0.95, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0):
        for history in (0.95, 1.01):
            for bottleneck in (99.0,):
                train_eval = _eval_prediction_records(train_records, margin, history, bottleneck)
                val_eval = _eval_prediction_records(val_records, margin, history, bottleneck)
                all_eval = _eval_prediction_records(all_records, margin, history, bottleneck)
                row = {
                    "risk_margin_threshold": margin,
                    "risk_historical_threshold": history,
                    "risk_bottleneck_threshold": bottleneck,
                    "train_wrong_high_confidence": train_eval["wrong_high_confidence_actions"],
                    "val_wrong_high_confidence": val_eval["wrong_high_confidence_actions"],
                    "all_wrong_high_confidence": all_eval["wrong_high_confidence_actions"],
                    "train_fallback_rate": train_eval["fallback_rate"],
                    "val_fallback_rate": val_eval["fallback_rate"],
                    "all_fallback_rate": all_eval["fallback_rate"],
                    "all_planned": all_eval["planned"],
                    "all_fallback_actions": all_eval["fallback_actions"],
                }
                sweep.append(row)
    selected = min(
        sweep,
        key=lambda row: (
            int(row["val_wrong_high_confidence"]),
            int(row["all_wrong_high_confidence"]),
            float(row["val_fallback_rate"]),
            float(row["all_fallback_rate"]),
        ),
    )
    return sweep, selected


def _write_feature_report(feature_rows: list[dict[str, Any]], forbidden_rows: list[dict[str, Any]], ablation_rows: list[dict[str, Any]]) -> None:
    FEATURE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4D Feature Safety and Ablation Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "G4D adds local runtime/static features only. It does not use scenario as a model input, full CIE route suffixes, teacher next-hop, future schedules, label source, or post-hoc success.",
        "",
        "## Forbidden Feature Audit",
        "",
        _markdown_table(["Check", "Pass", "Decision"], [[row["check"], row["pass"], row["decision"]] for row in forbidden_rows]),
        "",
        "## Ablation",
        "",
        _markdown_table(["Ablation", "All top1", "Val top1", "Test top1"], [[row["ablation"], f"{float(row['all_top1']):.6f}", f"{float(row['val_top1']):.6f}", f"{float(row['test_top1']):.6f}"] for row in ablation_rows]),
        "",
        "## Artifacts",
        "",
        f"- Feature schema: `{_relative(FEATURE_SCHEMA_TABLE)}`",
        f"- Forbidden audit: `{_relative(FORBIDDEN_AUDIT_TABLE)}`",
        f"- Feature ablation: `{_relative(FEATURE_ABLATION_TABLE)}`",
    ]
    FEATURE_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_train_report(history: list[dict[str, Any]], offline_rows: list[dict[str, Any]], selected: dict[str, Any], all_eval: dict[str, Any]) -> None:
    final = history[-1]
    all_row = next(row for row in offline_rows if row["split"] == "all")
    TRAIN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4D Policy Training Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This trains a small G4D MLP candidate scorer plus a calibrated risk head. It is not RL, PPO/MAPPO, GNN, Transformer, or a paper-grade replacement claim.",
        "",
        "## Training Result",
        "",
        f"- Final training loss: `{float(final['loss']):.6f}`",
        f"- Final training top1: `{float(final['top1']):.6f}`",
        f"- All-split top1: `{float(all_row['model_top1']):.6f}`",
        f"- Shortest-time heuristic top1: `{float(all_row['shortest_time_heuristic_top1']):.6f}`",
        "",
        "## Selected Risk Head",
        "",
        f"- Margin threshold: `{selected['risk_margin_threshold']}`",
        f"- Historical-risk threshold: `{selected['risk_historical_threshold']}`",
        f"- Bottleneck threshold: `{selected['risk_bottleneck_threshold']}`",
        f"- All fallback rate: `{float(all_eval['fallback_rate']):.6f}`",
        f"- All wrong high-confidence actions: `{all_eval['wrong_high_confidence_actions']}`",
        "",
        "## Decision",
        "",
        "The trained artifact is eligible for G4D closed-loop cost accounting. Promotion depends on the true closed-loop and A* call report, not this offline result alone.",
        "",
        "## Artifacts",
        "",
        f"- Model: `{_relative(MODEL_PATH)}`",
        f"- Offline accuracy: `{_relative(OFFLINE_ACCURACY_TABLE)}`",
        f"- Risk calibration: `{_relative(RISK_CALIBRATION_TABLE)}`",
        f"- Abstain sweep: `{_relative(ABSTAIN_SWEEP_TABLE)}`",
    ]
    TRAIN_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    from czr005.models import (
        G4D_FEATURE_NAMES,
        evaluate_g4d_top1,
        load_g4d_interface_slices,
        save_g4d_policy,
    )

    summary_rows = _read_csv(SUMMARY_TABLE)
    if any(row["node_window_conflicts"] != "0" for row in summary_rows):
        raise AssertionError("G4D teacher dataset has node-window conflicts; refusing to train")
    rows = load_g4d_interface_slices(INTERFACE_TABLE)
    train_rows = _split_rows(rows, "train")
    val_rows = _split_rows(rows, "val")
    test_rows = _split_rows(rows, "test")
    if not train_rows or not val_rows or not test_rows:
        raise AssertionError("G4D split must contain train, val, and test rows")
    model, history = _fit_numpy_mlp(train_rows, hidden_dim=22, epochs=70, batch_size=2048)
    sweep_rows, selected = _risk_sweep(model, train_rows, val_rows, rows)
    model.risk_margin_threshold = float(selected["risk_margin_threshold"])
    model.risk_historical_threshold = float(selected["risk_historical_threshold"])
    model.risk_bottleneck_threshold = float(selected["risk_bottleneck_threshold"])
    save_g4d_policy(MODEL_PATH, model)

    rows_by_split = {"train": train_rows, "val": val_rows, "test": test_rows, "all": rows}
    offline_rows = _offline_rows(model, rows_by_split)
    ablation_rows = _ablation_rows(model, rows, val_rows, test_rows)
    feature_rows = _feature_schema_rows(G4D_FEATURE_NAMES)
    forbidden_rows = _forbidden_audit_rows(model, feature_rows)
    all_eval = _route_eval(
        model,
        rows,
        model.risk_margin_threshold,
        model.risk_historical_threshold,
        model.risk_bottleneck_threshold,
    )
    calibration_rows = [
        {
            "calibration": "selected_risk_head",
            "risk_margin_threshold": model.risk_margin_threshold,
            "risk_historical_threshold": model.risk_historical_threshold,
            "risk_bottleneck_threshold": model.risk_bottleneck_threshold,
            "route_groups": all_eval["route_groups"],
            "planned": all_eval["planned"],
            "wrong_high_confidence_actions": all_eval["wrong_high_confidence_actions"],
            "fallback_actions": all_eval["fallback_actions"],
            "fallback_rate": all_eval["fallback_rate"],
            "notes": "Selected by validation wrong-high-confidence first, fallback rate second.",
        }
    ]

    _write_csv(HISTORY_TABLE, history, ["epoch", "loss", "top1"])
    _write_csv(OFFLINE_ACCURACY_TABLE, offline_rows, ["split", "sample_count", "model_top1", "shortest_time_heuristic_top1", "model_beats_shortest_time"])
    _write_csv(FEATURE_ABLATION_TABLE, ablation_rows, ["ablation", "all_top1", "val_top1", "test_top1"])
    _write_csv(FEATURE_SCHEMA_TABLE, feature_rows, ["field", "scope", "allowed_model_input", "contains_label", "notes"])
    _write_csv(FORBIDDEN_AUDIT_TABLE, forbidden_rows, ["check", "pass", "value", "threshold", "decision"])
    _write_csv(RISK_CALIBRATION_TABLE, calibration_rows, ["calibration", "risk_margin_threshold", "risk_historical_threshold", "risk_bottleneck_threshold", "route_groups", "planned", "wrong_high_confidence_actions", "fallback_actions", "fallback_rate", "notes"])
    _write_csv(ABSTAIN_SWEEP_TABLE, sweep_rows, ["risk_margin_threshold", "risk_historical_threshold", "risk_bottleneck_threshold", "train_wrong_high_confidence", "val_wrong_high_confidence", "all_wrong_high_confidence", "train_fallback_rate", "val_fallback_rate", "all_fallback_rate", "all_planned", "all_fallback_actions"])
    _write_feature_report(feature_rows, forbidden_rows, ablation_rows)
    _write_train_report(history, offline_rows, selected, all_eval)

    if not all(row["pass"] for row in forbidden_rows):
        raise AssertionError("G4D forbidden feature audit failed")
    all_top1 = next(row for row in offline_rows if row["split"] == "all")["model_top1"]
    if float(all_top1) < 0.95:
        raise AssertionError("G4D offline top1 collapsed below smoke threshold")
    missing = [path for path in (MODEL_PATH, FEATURE_REPORT_PATH, TRAIN_REPORT_PATH, OFFLINE_ACCURACY_TABLE, RISK_CALIBRATION_TABLE, ABSTAIN_SWEEP_TABLE) if not path.exists()]
    if missing:
        raise AssertionError(f"missing G4D training artifacts: {missing}")
    print(
        "g4d train complete: "
        f"slices={len(rows)} train={len(train_rows)} val={len(val_rows)} test={len(test_rows)} "
        f"top1={float(evaluate_g4d_top1(model, rows)):.6f} "
        f"fallback_rate={float(all_eval['fallback_rate']):.6f} "
        f"wrong_high={all_eval['wrong_high_confidence_actions']}"
    )


if __name__ == "__main__":
    main()
