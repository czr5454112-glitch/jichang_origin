"""Minimal pure-Python MLP edge scorer for behavior-cloning smoke tests."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import Any


FEATURE_NAMES = (
    "is_move",
    "is_hold",
    "is_safe",
    "travel_time_scaled",
    "service_time_scaled",
    "heuristic_to_goal_scaled",
    "is_goal_edge",
    "slack_scaled",
    "waiting_time_scaled",
    "out_degree_scaled",
    "blocked_reason_count",
    "edge_wait_scaled",
    "node_elapsed_scaled",
)


@dataclass
class EdgeScoreModel:
    w1: list[list[float]]
    b1: list[float]
    w2: list[float]
    b2: float

    def scores(self, features: list[list[float]]) -> list[float]:
        values: list[float] = []
        for row in features:
            hidden = _hidden(row, self.w1, self.b1)
            values.append(sum(value * weight for value, weight in zip(hidden, self.w2)) + self.b2)
        return values

    def predict_action(self, item: dict[str, Any], safe_only: bool = True) -> int:
        features, candidate_indices, mask = featurize_slice(item)
        scores = self.scores(features)
        if safe_only:
            scores = [score if allowed else -1.0e9 for score, allowed in zip(scores, mask)]
        best_position = max(range(len(scores)), key=lambda index: scores[index])
        return candidate_indices[best_position]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(FEATURE_NAMES),
            "w1": self.w1,
            "b1": self.b1,
            "w2": self.w2,
            "b2": self.b2,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EdgeScoreModel":
        return cls(
            w1=[[float(value) for value in row] for row in data["w1"]],
            b1=[float(value) for value in data["b1"]],
            w2=[float(value) for value in data["w2"]],
            b2=float(data["b2"]),
        )


def load_teacher_manifest(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def save_edge_score_model(path: str | Path, model: EdgeScoreModel) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model.to_dict(), ensure_ascii=True, indent=2), encoding="utf-8")


def load_edge_score_model(path: str | Path) -> EdgeScoreModel:
    return EdgeScoreModel.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def featurize_slice(item: dict[str, Any]) -> tuple[list[list[float]], list[int], list[bool]]:
    task = item["obs"]
    rows = [
        _candidate_features(task, candidate, int(item["goal"]))
        for candidate in item["candidate_edges"]
    ]
    candidate_indices = [int(candidate["index"]) for candidate in item["candidate_edges"]]
    mask = [bool(value) for value in item["action_mask"]]
    return rows, candidate_indices, mask


def fit_edge_score_model(
    slices: list[dict[str, Any]],
    hidden_dim: int = 16,
    epochs: int = 200,
    learning_rate: float = 0.05,
    seed: int = 17,
) -> tuple[EdgeScoreModel, list[dict[str, float | int]]]:
    if not slices:
        raise ValueError("slices must not be empty")
    rng = random.Random(seed)
    feature_dim = len(FEATURE_NAMES)
    model = EdgeScoreModel(
        w1=[
            [rng.gauss(0.0, 0.08) for _ in range(hidden_dim)]
            for _ in range(feature_dim)
        ],
        b1=[0.0 for _ in range(hidden_dim)],
        w2=[rng.gauss(0.0, 0.08) for _ in range(hidden_dim)],
        b2=0.0,
    )
    history: list[dict[str, float | int]] = []

    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        correct = 0
        order = list(range(len(slices)))
        rng.shuffle(order)
        for index in order:
            item = slices[index]
            features, candidate_indices, mask = featurize_slice(item)
            target_position = _target_position(candidate_indices, int(item["expert_action"]))
            loss, is_correct, grads = _loss_and_grads(model, features, mask, target_position)
            total_loss += loss
            correct += int(is_correct)
            _apply_grads(model, grads, learning_rate)
        history.append(
            {
                "epoch": epoch,
                "loss": total_loss / len(slices),
                "top1": correct / len(slices),
            }
        )
    return model, history


def evaluate_top1(model: EdgeScoreModel, slices: list[dict[str, Any]], safe_only: bool = True) -> float:
    if not slices:
        return 0.0
    correct = sum(1 for item in slices if model.predict_action(item, safe_only=safe_only) == item["expert_action"])
    return correct / len(slices)


def _candidate_features(task: dict[str, Any], candidate: dict[str, Any], goal: int) -> list[float]:
    blocked_reasons = candidate.get("blocked_reasons", ())
    decision_time = float(task["ready_time"])
    return [
        1.0 if candidate["kind"] == "move" else 0.0,
        1.0 if candidate["kind"] == "hold" else 0.0,
        1.0 if candidate["safe"] else 0.0,
        _clip_scale(candidate["travel_time"], 100.0, 50.0),
        _clip_scale(candidate["service_time"], 10.0, 20.0),
        _clip_scale(candidate["heuristic_to_goal"], 100.0, 50.0),
        1.0 if int(candidate["next_node"]) == goal else 0.0,
        _clip_scale(task["slack"], 10_000.0, 20.0),
        _clip_scale(task["waiting_time"], 100.0, 50.0),
        _clip_scale(task["out_degree"], 10.0, 10.0),
        min(len(blocked_reasons), 4) / 4.0,
        _clip_scale(float(candidate["edge_start"]) - decision_time, 100.0, 50.0),
        _clip_scale(float(candidate["node_end"]) - decision_time, 100.0, 50.0),
    ]


def _clip_scale(value: object, scale: float, limit: float) -> float:
    scaled = float(value) / scale
    return max(-limit, min(limit, scaled))


def _target_position(candidate_indices: list[int], expert_action: int) -> int:
    for index, candidate_index in enumerate(candidate_indices):
        if candidate_index == expert_action:
            return index
    raise ValueError(f"expert_action {expert_action} not in candidate indices")


def _loss_and_grads(
    model: EdgeScoreModel,
    features: list[list[float]],
    mask: list[bool],
    target_position: int,
) -> tuple[float, bool, dict[str, Any]]:
    hidden_rows = [_hidden(row, model.w1, model.b1) for row in features]
    raw_scores = [
        sum(hidden_value * weight for hidden_value, weight in zip(hidden, model.w2)) + model.b2
        for hidden in hidden_rows
    ]
    scores = [score if allowed else -1.0e9 for score, allowed in zip(raw_scores, mask)]
    probs = _softmax(scores)
    loss = -math.log(max(probs[target_position], 1.0e-12))
    prediction = max(range(len(probs)), key=lambda index: probs[index])

    grad_scores = list(probs)
    grad_scores[target_position] -= 1.0
    grad_scores = [grad if allowed else 0.0 for grad, allowed in zip(grad_scores, mask)]

    hidden_dim = len(model.w2)
    feature_dim = len(features[0])
    grad_w2 = [0.0 for _ in range(hidden_dim)]
    grad_b2 = sum(grad_scores)
    grad_w1 = [[0.0 for _ in range(hidden_dim)] for _ in range(feature_dim)]
    grad_b1 = [0.0 for _ in range(hidden_dim)]

    for row, hidden, grad_score in zip(features, hidden_rows, grad_scores):
        for hidden_index in range(hidden_dim):
            grad_w2[hidden_index] += hidden[hidden_index] * grad_score
            grad_hidden = grad_score * model.w2[hidden_index]
            grad_z = grad_hidden * (1.0 - hidden[hidden_index] * hidden[hidden_index])
            grad_b1[hidden_index] += grad_z
            for feature_index in range(feature_dim):
                grad_w1[feature_index][hidden_index] += row[feature_index] * grad_z

    return (
        loss,
        prediction == target_position,
        {
            "w1": grad_w1,
            "b1": grad_b1,
            "w2": grad_w2,
            "b2": grad_b2,
        },
    )


def _apply_grads(model: EdgeScoreModel, grads: dict[str, Any], learning_rate: float) -> None:
    for feature_index, row in enumerate(model.w1):
        for hidden_index in range(len(row)):
            row[hidden_index] -= learning_rate * grads["w1"][feature_index][hidden_index]
    for index in range(len(model.b1)):
        model.b1[index] -= learning_rate * grads["b1"][index]
        model.w2[index] -= learning_rate * grads["w2"][index]
    model.b2 -= learning_rate * grads["b2"]


def _hidden(row: list[float], w1: list[list[float]], b1: list[float]) -> list[float]:
    hidden: list[float] = []
    for hidden_index, bias in enumerate(b1):
        value = bias
        for feature_index, feature in enumerate(row):
            value += feature * w1[feature_index][hidden_index]
        hidden.append(math.tanh(value))
    return hidden


def _softmax(scores: list[float]) -> list[float]:
    max_score = max(scores)
    exp_scores = [math.exp(score - max_score) if score > -1.0e8 else 0.0 for score in scores]
    total = sum(exp_scores)
    if total <= 0.0:
        return [1.0 / len(scores) for _ in scores]
    return [value / total for value in exp_scores]
