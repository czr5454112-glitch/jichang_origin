"""Minimal G4B CIE-retry candidate scorer.

This module is intentionally small and pure Python. It consumes only the
allowed runtime features emitted by the G4A dataset and keeps teacher labels
out of model inputs.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import Any


G4B_FEATURE_NAMES = (
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
)


@dataclass
class G4BCieRetryModel:
    w1: list[list[float]]
    b1: list[float]
    w2: list[float]
    b2: float
    margin_threshold: float = 0.15

    def scores(self, features: list[list[float]]) -> list[float]:
        output: list[float] = []
        for row in features:
            hidden = _hidden(row, self.w1, self.b1)
            output.append(sum(value * weight for value, weight in zip(hidden, self.w2)) + self.b2)
        return output

    def predict(self, item: dict[str, Any], ablation: set[str] | None = None) -> tuple[int, float, list[float]]:
        features, candidates = featurize_g4a_slice(item, ablation=ablation)
        scores = self.scores(features)
        best_index = max(range(len(scores)), key=lambda index: scores[index])
        ordered = sorted(scores, reverse=True)
        margin = ordered[0] - ordered[1] if len(ordered) > 1 else 999.0
        return int(candidates[best_index]), margin, scores

    def should_abstain(self, item: dict[str, Any]) -> bool:
        _, margin, _ = self.predict(item)
        return margin < self.margin_threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": "g4b_cie_retry_edge_ranker_smoke",
            "feature_names": list(G4B_FEATURE_NAMES),
            "w1": self.w1,
            "b1": self.b1,
            "w2": self.w2,
            "b2": self.b2,
            "margin_threshold": self.margin_threshold,
            "source_retry_head": {
                "type": "pilot_rule_head",
                "positive_label": "WAIT_AT_SOURCE_RETRY",
                "note": "G4B keeps source admission separate from junction next-hop scoring.",
            },
            "abstain_head": {
                "type": "score_margin_threshold",
                "threshold": self.margin_threshold,
                "fallback": "ABSTAIN_TO_SAFE_FALLBACK",
            },
            "forbidden_model_inputs": [
                "teacher_next_node",
                "teacher_path",
                "full_cie_route_suffix",
                "future_sipp_schedule",
                "route_finish_time",
                "label_source",
                "post_hoc_success_flag",
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "G4BCieRetryModel":
        return cls(
            w1=[[float(value) for value in row] for row in data["w1"]],
            b1=[float(value) for value in data["b1"]],
            w2=[float(value) for value in data["w2"]],
            b2=float(data["b2"]),
            margin_threshold=float(data.get("margin_threshold", 0.15)),
        )


def load_g4a_interface_slices(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(_decode_row(row))
    return rows


def load_g4b_model(path: str | Path) -> G4BCieRetryModel:
    return G4BCieRetryModel.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_g4b_model(path: str | Path, model: G4BCieRetryModel) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model.to_dict(), ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def featurize_g4a_slice(item: dict[str, Any], ablation: set[str] | None = None) -> tuple[list[list[float]], list[int]]:
    ablation = ablation or set()
    candidates = [int(value) for value in item["candidate_next_nodes"]]
    shortest = item["candidate_shortest_time_to_goal"]
    travel = item["candidate_travel_time"]
    service = item["candidate_service_time"]
    node_type = item["candidate_node_type"]
    fault = item["candidate_fault_status"]
    pressure_summary = item.get("local_queue_or_occupancy_summary", {})
    candidate_pressure = pressure_summary.get("candidate_node_pressure", {}) if isinstance(pressure_summary, dict) else {}
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
        }
        for name in ablation:
            if name in values:
                values[name] = 0.0
        rows.append([values[name] for name in G4B_FEATURE_NAMES])
    return rows, candidates


def fit_g4b_model(
    slices: list[dict[str, Any]],
    hidden_dim: int = 18,
    epochs: int = 220,
    learning_rate: float = 0.04,
    seed: int = 71,
) -> tuple[G4BCieRetryModel, list[dict[str, float | int]]]:
    if not slices:
        raise ValueError("slices must not be empty")
    rng = random.Random(seed)
    feature_dim = len(G4B_FEATURE_NAMES)
    model = G4BCieRetryModel(
        w1=[[rng.gauss(0.0, 0.08) for _ in range(hidden_dim)] for _ in range(feature_dim)],
        b1=[0.0 for _ in range(hidden_dim)],
        w2=[rng.gauss(0.0, 0.08) for _ in range(hidden_dim)],
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
            features, candidates = featurize_g4a_slice(item)
            target = _target_position(candidates, int(item["teacher_next_node"]))
            loss, is_correct, grads = _loss_and_grads(model, features, target)
            total_loss += loss
            correct += int(is_correct)
            _apply_grads(model, grads, learning_rate)
        history.append({"epoch": epoch, "loss": total_loss / len(slices), "top1": correct / len(slices)})
    return model, history


def evaluate_g4b_top1(model: G4BCieRetryModel, slices: list[dict[str, Any]], ablation: set[str] | None = None) -> float:
    if not slices:
        return 0.0
    correct = 0
    for item in slices:
        prediction, _, _ = model.predict(item, ablation=ablation)
        correct += int(prediction == int(item["teacher_next_node"]))
    return correct / len(slices)


def heuristic_shortest_time_top1(slices: list[dict[str, Any]]) -> float:
    if not slices:
        return 0.0
    correct = 0
    for item in slices:
        shortest = item["candidate_shortest_time_to_goal"]
        travel = item["candidate_travel_time"]
        candidates = [int(value) for value in item["candidate_next_nodes"]]
        prediction = min(candidates, key=lambda node: (float(shortest[str(node)]) + float(travel[str(node)]), node))
        correct += int(prediction == int(item["teacher_next_node"]))
    return correct / len(slices)


def random_safe_expected_top1(slices: list[dict[str, Any]]) -> float:
    if not slices:
        return 0.0
    total = 0.0
    for item in slices:
        candidates = item["candidate_next_nodes"]
        total += 1.0 / max(1, len(candidates))
    return total / len(slices)


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
    ):
        decoded[key] = json.loads(row[key]) if row.get(key) else {}
    for key in ("task_id", "decision_index", "current_node", "goal_node"):
        decoded[key] = int(row[key])
    for key in (
        "current_time",
        "task_entry_time",
        "deadline_or_std",
        "time_slack",
        "source_retry_age_seconds",
    ):
        decoded[key] = float(row[key]) if row.get(key) else 0.0
    decoded["teacher_next_node"] = int(row["teacher_next_node"]) if row.get("teacher_next_node") else None
    decoded["is_branch_node"] = str(row.get("is_branch_node", "")).lower() == "true"
    decoded["is_source_retry"] = str(row.get("is_source_retry", "")).lower() == "true"
    decoded["edge_capacity_primary"] = str(row.get("edge_capacity_primary", "")).lower() == "true"
    decoded["local_node_time_window_pressure"] = float(row["local_node_time_window_pressure"]) if row.get("local_node_time_window_pressure") else 0.0
    return decoded


def _scale(value: Any, denominator: float) -> float:
    return max(-20.0, min(20.0, float(value) / denominator))


def _target_position(candidates: list[int], teacher_next: int) -> int:
    for index, candidate in enumerate(candidates):
        if candidate == teacher_next:
            return index
    raise ValueError(f"teacher_next {teacher_next} missing from candidates {candidates}")


def _loss_and_grads(
    model: G4BCieRetryModel,
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


def _apply_grads(model: G4BCieRetryModel, grads: dict[str, Any], learning_rate: float) -> None:
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
