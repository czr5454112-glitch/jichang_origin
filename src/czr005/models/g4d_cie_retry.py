"""G4D small CIE-retry policy utilities.

The G4D policy is still a tiny candidate scorer. It adds runtime-available
local features to the G4B feature family and keeps teacher labels, scenario
keys, full routes, future schedules, and post-hoc success out of the model
input surface.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import Any


G4D_FEATURE_NAMES = (
    "candidate_shortest_time_to_goal_scaled",
    "candidate_travel_time_scaled",
    "candidate_service_time_scaled",
    "candidate_node_type_scaled",
    "candidate_faulted",
    "candidate_is_goal",
    "time_slack_scaled",
    "current_node_scaled",
    "goal_node_scaled",
    "out_degree_scaled",
    "is_branch_node",
    "local_node_pressure_scaled",
    "candidate_node_pressure_scaled",
    "candidate_downstream_node_pressure_2hop_scaled",
    "candidate_downstream_node_pressure_3hop_scaled",
    "candidate_static_remaining_hops_to_goal_scaled",
    "candidate_static_second_best_gap_scaled",
    "candidate_bottleneck_score_scaled",
    "candidate_goal_direction_score_scaled",
    "candidate_historical_risk_from_training_only_scaled",
    "source_retry_pressure_scaled",
    "unfinished_task_queue_size_near_current_source_scaled",
)

FORBIDDEN_G4D_MODEL_INPUTS = (
    "scenario",
    "teacher_next_node",
    "teacher_path",
    "full_cie_route_suffix",
    "route_path",
    "future_sipp_schedule",
    "future_schedule",
    "route_finish_time",
    "label_source",
    "post_hoc_success",
    "post_hoc_success_flag",
)


@dataclass
class G4DCieRetryPolicy:
    w1: list[list[float]]
    b1: list[float]
    w2: list[float]
    b2: float
    risk_margin_threshold: float = 0.02
    risk_historical_threshold: float = 0.95
    risk_bottleneck_threshold: float = 99.0

    def scores(self, features: list[list[float]]) -> list[float]:
        output: list[float] = []
        for row in features:
            hidden = _hidden(row, self.w1, self.b1)
            output.append(sum(value * weight for value, weight in zip(hidden, self.w2)) + self.b2)
        return output

    def predict(self, item: dict[str, Any], ablation: set[str] | None = None) -> tuple[int, float, list[float]]:
        features, candidates = featurize_g4d_slice(item, ablation=ablation)
        scores = self.scores(features)
        best_index = max(range(len(scores)), key=lambda index: scores[index])
        ordered = sorted(scores, reverse=True)
        margin = ordered[0] - ordered[1] if len(ordered) > 1 else 999.0
        return int(candidates[best_index]), margin, scores

    def risk_score(self, item: dict[str, Any], prediction: int, margin: float) -> float:
        enhanced = item.get("g4d_enhanced_features", {})
        historical = enhanced.get("candidate_historical_risk_from_training_only", {})
        bottleneck = enhanced.get("candidate_bottleneck_score", {})
        pred_key = str(int(prediction))
        history_risk = float(historical.get(pred_key, 0.0))
        bottleneck_risk = float(bottleneck.get(pred_key, 0.0))
        margin_risk = max(0.0, self.risk_margin_threshold - margin) / max(self.risk_margin_threshold, 1.0e-9)
        return max(history_risk, margin_risk, bottleneck_risk / max(self.risk_bottleneck_threshold, 1.0e-9))

    def should_fallback(self, item: dict[str, Any], prediction: int | None = None, margin: float | None = None) -> bool:
        if prediction is None or margin is None:
            prediction, margin, _ = self.predict(item)
        enhanced = item.get("g4d_enhanced_features", {})
        historical = enhanced.get("candidate_historical_risk_from_training_only", {})
        bottleneck = enhanced.get("candidate_bottleneck_score", {})
        pred_key = str(int(prediction))
        return (
            margin < self.risk_margin_threshold
            or float(historical.get(pred_key, 0.0)) >= self.risk_historical_threshold
            or float(bottleneck.get(pred_key, 0.0)) >= self.risk_bottleneck_threshold
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": "g4d_cie_retry_policy",
            "feature_names": list(G4D_FEATURE_NAMES),
            "w1": self.w1,
            "b1": self.b1,
            "w2": self.w2,
            "b2": self.b2,
            "risk_margin_threshold": self.risk_margin_threshold,
            "risk_historical_threshold": self.risk_historical_threshold,
            "risk_bottleneck_threshold": self.risk_bottleneck_threshold,
            "risk_head": {
                "type": "margin_plus_training_history_calibration",
                "fallback": "ABSTAIN_TO_SAFE_FALLBACK",
                "note": "Uses only runtime margin, static/local bottleneck features, and training-only historical risk.",
            },
            "source_retry_head": {
                "type": "verified_cie_retry_admission_rule",
                "positive_label": "WAIT_AT_SOURCE_RETRY",
            },
            "forbidden_model_inputs": list(FORBIDDEN_G4D_MODEL_INPUTS),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "G4DCieRetryPolicy":
        return cls(
            w1=[[float(value) for value in row] for row in data["w1"]],
            b1=[float(value) for value in data["b1"]],
            w2=[float(value) for value in data["w2"]],
            b2=float(data["b2"]),
            risk_margin_threshold=float(data.get("risk_margin_threshold", 0.02)),
            risk_historical_threshold=float(data.get("risk_historical_threshold", 0.95)),
            risk_bottleneck_threshold=float(data.get("risk_bottleneck_threshold", 99.0)),
        )


def load_g4d_interface_slices(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(_decode_row(row))
    return rows


def load_g4d_policy(path: str | Path) -> G4DCieRetryPolicy:
    return G4DCieRetryPolicy.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_g4d_policy(path: str | Path, model: G4DCieRetryPolicy) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model.to_dict(), ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def featurize_g4d_slice(item: dict[str, Any], ablation: set[str] | None = None) -> tuple[list[list[float]], list[int]]:
    ablation = ablation or set()
    candidates = [int(value) for value in item["candidate_next_nodes"]]
    shortest = item["candidate_shortest_time_to_goal"]
    travel = item["candidate_travel_time"]
    service = item["candidate_service_time"]
    node_type = item["candidate_node_type"]
    fault = item["candidate_fault_status"]
    pressure_summary = item.get("local_queue_or_occupancy_summary", {})
    candidate_pressure = pressure_summary.get("candidate_node_pressure", {}) if isinstance(pressure_summary, dict) else {}
    enhanced = item.get("g4d_enhanced_features", {})
    rows: list[list[float]] = []
    for candidate in candidates:
        key = str(candidate)
        values = {
            "candidate_shortest_time_to_goal_scaled": _scale(shortest.get(key, 0.0), 100.0),
            "candidate_travel_time_scaled": _scale(travel.get(key, 0.0), 50.0),
            "candidate_service_time_scaled": _scale(service.get(key, 0.0), 10.0),
            "candidate_node_type_scaled": _scale(node_type.get(key, 0.0), 10.0),
            "candidate_faulted": 1.0 if fault.get(key, False) else 0.0,
            "candidate_is_goal": 1.0 if candidate == int(item["goal_node"]) else 0.0,
            "time_slack_scaled": _scale(item["time_slack"], 10_000.0),
            "current_node_scaled": _scale(item["current_node"], 100.0),
            "goal_node_scaled": _scale(item["goal_node"], 100.0),
            "out_degree_scaled": _scale(len(candidates), 10.0),
            "is_branch_node": 1.0 if item["is_branch_node"] else 0.0,
            "local_node_pressure_scaled": _scale(item.get("local_node_time_window_pressure", 0.0) or 0.0, 10.0),
            "candidate_node_pressure_scaled": _scale(candidate_pressure.get(key, 0.0), 10.0),
            "candidate_downstream_node_pressure_2hop_scaled": _scale(_enhanced_value(enhanced, "candidate_downstream_node_pressure_2hop", key), 20.0),
            "candidate_downstream_node_pressure_3hop_scaled": _scale(_enhanced_value(enhanced, "candidate_downstream_node_pressure_3hop", key), 30.0),
            "candidate_static_remaining_hops_to_goal_scaled": _scale(_enhanced_value(enhanced, "candidate_static_remaining_hops_to_goal", key), 20.0),
            "candidate_static_second_best_gap_scaled": _scale(_enhanced_value(enhanced, "candidate_static_second_best_gap", key), 50.0),
            "candidate_bottleneck_score_scaled": _scale(_enhanced_value(enhanced, "candidate_bottleneck_score", key), 10.0),
            "candidate_goal_direction_score_scaled": _scale(_enhanced_value(enhanced, "candidate_goal_direction_score", key), 100.0),
            "candidate_historical_risk_from_training_only_scaled": _scale(_enhanced_value(enhanced, "candidate_historical_risk_from_training_only", key), 1.0),
            "source_retry_pressure_scaled": _scale(item.get("source_retry_pressure", 0.0), 20.0),
            "unfinished_task_queue_size_near_current_source_scaled": _scale(item.get("unfinished_task_queue_size_near_current_source", 0.0), 20.0),
        }
        for name in ablation:
            if name in values:
                values[name] = 0.0
        rows.append([values[name] for name in G4D_FEATURE_NAMES])
    return rows, candidates


def fit_g4d_policy(
    slices: list[dict[str, Any]],
    hidden_dim: int = 22,
    epochs: int = 90,
    learning_rate: float = 0.035,
    seed: int = 113,
) -> tuple[G4DCieRetryPolicy, list[dict[str, float | int]]]:
    if not slices:
        raise ValueError("slices must not be empty")
    rng = random.Random(seed)
    feature_dim = len(G4D_FEATURE_NAMES)
    model = G4DCieRetryPolicy(
        w1=[[rng.gauss(0.0, 0.07) for _ in range(hidden_dim)] for _ in range(feature_dim)],
        b1=[0.0 for _ in range(hidden_dim)],
        w2=[rng.gauss(0.0, 0.07) for _ in range(hidden_dim)],
        b2=0.0,
    )
    history: list[dict[str, float | int]] = []
    order = list(range(len(slices)))
    for epoch in range(1, epochs + 1):
        rng.shuffle(order)
        total_loss = 0.0
        correct = 0
        for index in order:
            item = slices[index]
            features, candidates = featurize_g4d_slice(item)
            target = _target_position(candidates, int(item["teacher_next_node"]))
            loss, is_correct, grads = _loss_and_grads(model, features, target)
            total_loss += loss
            correct += int(is_correct)
            _apply_grads(model, grads, learning_rate)
        history.append({"epoch": epoch, "loss": total_loss / len(slices), "top1": correct / len(slices)})
    return model, history


def evaluate_g4d_top1(model: Any, slices: list[dict[str, Any]], ablation: set[str] | None = None) -> float:
    if not slices:
        return 0.0
    correct = 0
    for item in slices:
        prediction, _, _ = model.predict(item, ablation=ablation)
        correct += int(prediction == int(item["teacher_next_node"]))
    return correct / len(slices)


def _decode_row(row: dict[str, str]) -> dict[str, Any]:
    decoded: dict[str, Any] = dict(row)
    for key in (
        "candidate_next_nodes",
        "candidate_shortest_time_to_goal",
        "candidate_travel_time",
        "candidate_service_time",
        "candidate_node_type",
        "candidate_fault_status",
        "local_queue_or_occupancy_summary",
        "g4d_enhanced_features",
    ):
        decoded[key] = json.loads(row[key]) if row.get(key) else {}
    for key in ("task_id", "decision_index", "current_node", "goal_node", "window_size", "window_offset"):
        decoded[key] = int(row[key]) if row.get(key) else 0
    for key in (
        "current_time",
        "task_entry_time",
        "deadline_or_std",
        "time_slack",
        "source_retry_age_seconds",
        "source_retry_pressure",
        "unfinished_task_queue_size_near_current_source",
    ):
        decoded[key] = float(row[key]) if row.get(key) else 0.0
    decoded["teacher_next_node"] = int(row["teacher_next_node"]) if row.get("teacher_next_node") else None
    decoded["is_branch_node"] = str(row.get("is_branch_node", "")).lower() == "true"
    decoded["is_source_retry"] = str(row.get("is_source_retry", "")).lower() == "true"
    decoded["edge_capacity_primary"] = str(row.get("edge_capacity_primary", "")).lower() == "true"
    decoded["local_node_time_window_pressure"] = float(row["local_node_time_window_pressure"]) if row.get("local_node_time_window_pressure") else 0.0
    return decoded


def _enhanced_value(enhanced: dict[str, Any], name: str, key: str) -> float:
    values = enhanced.get(name, {})
    if isinstance(values, dict):
        return float(values.get(key, 0.0))
    return 0.0


def _scale(value: Any, denominator: float) -> float:
    return max(-20.0, min(20.0, float(value) / denominator))


def _target_position(candidates: list[int], teacher_next: int) -> int:
    for index, candidate in enumerate(candidates):
        if candidate == teacher_next:
            return index
    raise ValueError(f"teacher_next {teacher_next} missing from candidates {candidates}")


def _loss_and_grads(
    model: G4DCieRetryPolicy,
    features: list[list[float]],
    target_position: int,
) -> tuple[float, bool, dict[str, Any]]:
    hidden_rows = [_hidden(row, model.w1, model.b1) for row in features]
    raw_scores = [
        sum(hidden_value * weight for hidden_value, weight in zip(hidden, model.w2)) + model.b2
        for hidden in hidden_rows
    ]
    probs = _softmax(raw_scores)
    loss = -math.log(max(probs[target_position], 1.0e-12))
    prediction = max(range(len(probs)), key=lambda index: probs[index])
    grad_scores = list(probs)
    grad_scores[target_position] -= 1.0

    feature_dim = len(features[0])
    hidden_dim = len(model.w2)
    grad_w1 = [[0.0 for _ in range(hidden_dim)] for _ in range(feature_dim)]
    grad_b1 = [0.0 for _ in range(hidden_dim)]
    grad_w2 = [0.0 for _ in range(hidden_dim)]
    grad_b2 = sum(grad_scores)
    for row, hidden, grad_score in zip(features, hidden_rows, grad_scores):
        for hidden_index in range(hidden_dim):
            grad_w2[hidden_index] += hidden[hidden_index] * grad_score
            grad_hidden = grad_score * model.w2[hidden_index]
            grad_z = grad_hidden * (1.0 - hidden[hidden_index] * hidden[hidden_index])
            grad_b1[hidden_index] += grad_z
            for feature_index in range(feature_dim):
                grad_w1[feature_index][hidden_index] += row[feature_index] * grad_z
    return loss, prediction == target_position, {"w1": grad_w1, "b1": grad_b1, "w2": grad_w2, "b2": grad_b2}


def _apply_grads(model: G4DCieRetryPolicy, grads: dict[str, Any], learning_rate: float) -> None:
    for feature_index, row in enumerate(model.w1):
        for hidden_index in range(len(row)):
            row[hidden_index] -= learning_rate * grads["w1"][feature_index][hidden_index]
    for index in range(len(model.b1)):
        model.b1[index] -= learning_rate * grads["b1"][index]
        model.w2[index] -= learning_rate * grads["w2"][index]
    model.b2 -= learning_rate * grads["b2"]


def _hidden(row: list[float], w1: list[list[float]], b1: list[float]) -> list[float]:
    output: list[float] = []
    for hidden_index, bias in enumerate(b1):
        value = bias
        for feature_index, feature in enumerate(row):
            value += feature * w1[feature_index][hidden_index]
        output.append(math.tanh(value))
    return output


def _softmax(scores: list[float]) -> list[float]:
    max_score = max(scores)
    exps = [math.exp(score - max_score) for score in scores]
    total = sum(exps)
    return [value / total for value in exps]
