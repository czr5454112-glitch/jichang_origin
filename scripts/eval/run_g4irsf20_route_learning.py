#!/usr/bin/env python3
"""Train and audit minimal G20 one-hop Route scorers from compact JSONL.

Each JSONL row is one exact-state choice group.  Model inputs come only from
``candidates[*].native_features`` and are projected by the strict
``RICH_ROUTE_V2`` contract.  Counterfactual utility is a target only; clone,
request, and choice-group identifiers are split/report metadata only.

The runner fits every F0..F5 group with three reused G18 families, calibrates a
single mutation-margin threshold on validation, and makes promotion decisions
on audit.  A compact, inactive offline candidate is emitted only when a model
improves the recorded S4 decisions and passes all conservative offline gates.
Native closed-loop validation is a separate requirement; this runner never
activates a policy.  NO_GO is a normal, explicit result.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any, Hashable, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005.g4irsf20.features import (
    FEATURE_GROUP_CONTRACTS,
    RouteFeatureError,
    RouteFeatureGroup,
    project_rich_route_v2,
)
from czr005.g4irsf20.models import (
    PairwiseResidualScorer,
    SetCandidateScorer,
    TinyResidualScorer,
    grouped_split_indices,
    offline_route_metrics,
    route_model_summary,
    s4_costs_to_scores,
)
from czr005.g4irsf17.models import PairwiseLinearRanker
from czr005.g4irsf18.models import TinyMLPRegressor


CAMPAIGN_SCHEMA = "czr005.g4irsf20.route_learning_campaign.v1"
POLICY_SCHEMA = "czr005.g4irsf20.route_policy.v1"
COMPACT_SCHEMA = "czr005.g4irsf20.route_counterfactual.compact.v1"

DEFAULT_INPUT = ROOT / "artifacts/datasets/g4irsf20_route_primary_pairs.jsonl"
DEFAULT_REPORT = ROOT / "outputs/tables/g4irsf20_route_learning.json"
DEFAULT_POLICY = ROOT / "artifacts/policies/g4irsf20_route_policy.json"

MODEL_FAMILIES = (
    "linear_residual",
    "tiny_mlp_residual",
    "set_scorer",
)
MODEL_COMPLEXITY = {name: index for index, name in enumerate(MODEL_FAMILIES)}

DEFAULT_GATES: Mapping[str, float] = {
    "beneficial_precision_min": 0.80,
    "harmful_applied_rate_max": 0.02,
    "pairwise_accuracy_min": 0.70,
    "s4_preservation_min": 0.98,
    "mean_advantage_vs_s4_min": 0.0,
    "minimum_applied_count": 5.0,
    "mean_advantage_lcb_min": 0.0,
}


class RouteLearningCampaignError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RouteLearningCampaignError(message)


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RouteLearningCampaignError(f"{name}_MUST_BE_NUMERIC")
    number = float(value)
    if not math.isfinite(number):
        raise RouteLearningCampaignError(f"{name}_MUST_BE_FINITE")
    return number


@dataclass(frozen=True)
class RouteChoiceGroup:
    choice_group_id: str
    split_group_id: Hashable
    normal_flow: bool
    native_candidates: tuple[Mapping[str, Any], ...]
    utilities: np.ndarray
    s4_index: int
    primary_pair_labeled: bool
    full_legal_action_set_labeled: bool
    wait_action_labeled: bool
    label_scope: str


def _split_group_id(row: Mapping[str, Any], choice_group_id: str) -> Hashable:
    if "split_group" in row:
        value = row["split_group"]
        _require(isinstance(value, (str, int)), "split_group must be string or integer")
        return ("split_group", value)
    clone_group = row.get("clone_group_id")
    request_group = row.get("request_group")
    if clone_group is not None and request_group is not None:
        _require(
            isinstance(clone_group, (str, int))
            and isinstance(request_group, (str, int)),
            "clone_group_id/request_group must be string or integer",
        )
        return ("clone_request", clone_group, request_group)
    if clone_group is not None:
        _require(
            isinstance(clone_group, (str, int)),
            "clone_group_id must be string or integer",
        )
        return ("clone_group", clone_group)
    # A compact generator may already define exact independent choice groups.
    return ("choice_group", choice_group_id)


def _parse_choice_group(raw: Any, line_number: int) -> RouteChoiceGroup:
    _require(isinstance(raw, Mapping), f"line {line_number}: row must be an object")
    schema = raw.get("schema_id", COMPACT_SCHEMA)
    _require(schema == COMPACT_SCHEMA, f"line {line_number}: compact schema mismatch")
    choice_group_id = raw.get("choice_group_id")
    _require(
        isinstance(choice_group_id, str) and bool(choice_group_id),
        f"line {line_number}: choice_group_id missing",
    )
    normal_flow = raw.get("normal_flow")
    _require(type(normal_flow) is bool, f"line {line_number}: normal_flow must be boolean")
    raw_candidates = raw.get("candidates")
    _require(
        isinstance(raw_candidates, list) and len(raw_candidates) >= 2,
        f"line {line_number}: at least two candidates required",
    )
    native_candidates: list[Mapping[str, Any]] = []
    utilities: list[float] = []
    for candidate_index, candidate in enumerate(raw_candidates):
        prefix = f"line {line_number} candidate {candidate_index}"
        _require(isinstance(candidate, Mapping), f"{prefix}: must be an object")
        _require(candidate.get("legal") is True, f"{prefix}: only legal candidates allowed")
        native = candidate.get("native_features")
        _require(isinstance(native, Mapping), f"{prefix}: native_features missing")
        native_candidates.append(native)
        utilities.append(_finite(candidate.get("utility"), f"{prefix} utility"))
    s4_index = raw.get("s4_index")
    _require(
        type(s4_index) is int and 0 <= s4_index < len(native_candidates),
        f"line {line_number}: s4_index invalid",
    )
    return RouteChoiceGroup(
        choice_group_id=choice_group_id,
        split_group_id=_split_group_id(raw, choice_group_id),
        normal_flow=normal_flow,
        native_candidates=tuple(native_candidates),
        utilities=np.asarray(utilities, dtype=np.float64),
        s4_index=s4_index,
        primary_pair_labeled=raw.get("primary_pair_labeled", True) is True,
        full_legal_action_set_labeled=(
            raw.get("full_legal_action_set_labeled", True) is True
        ),
        wait_action_labeled=raw.get("wait_action_labeled", True) is True,
        label_scope=str(raw.get("label_scope", "COMPLETE_LEGAL_CHOICE_SET")),
    )


def load_compact_jsonl(path: Path) -> list[RouteChoiceGroup]:
    """Load the compact choice-group schema without retaining raw outcomes."""

    _require(path.is_file(), f"compact input not found: {path}")
    groups: list[RouteChoiceGroup] = []
    seen_choice_groups: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, text in enumerate(handle, start=1):
            if not text.strip():
                continue
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RouteLearningCampaignError(
                    f"line {line_number}: invalid JSON: {exc.msg}"
                ) from exc
            group = _parse_choice_group(raw, line_number)
            _require(
                group.choice_group_id not in seen_choice_groups,
                f"line {line_number}: duplicate choice_group_id",
            )
            seen_choice_groups.add(group.choice_group_id)
            groups.append(group)
    _require(groups, "compact input has no choice groups")
    return groups


def _feature_matrices(
    groups: Sequence[RouteChoiceGroup],
    feature_group: RouteFeatureGroup,
) -> list[np.ndarray]:
    matrices: list[np.ndarray] = []
    for group in groups:
        try:
            rows = [
                project_rich_route_v2(candidate, feature_group)
                for candidate in group.native_candidates
            ]
        except RouteFeatureError as exc:
            raise RouteLearningCampaignError(
                f"FEATURE_LEAKAGE_OR_SCHEMA_ERROR:{group.choice_group_id}:{exc}"
            ) from exc
        matrices.append(np.vstack(rows))
    return matrices


def _subset(values: Sequence[Any], indices: Sequence[int]) -> list[Any]:
    return [values[index] for index in indices]


def _baseline_score_sets(f0_features: Sequence[np.ndarray]) -> list[np.ndarray]:
    return [s4_costs_to_scores(np.sum(features, axis=1)) for features in f0_features]


def _validate_s4_indices(
    groups: Sequence[RouteChoiceGroup],
    baseline_scores: Sequence[np.ndarray],
    *,
    tolerance: float = 1e-9,
) -> None:
    for group, scores in zip(groups, baseline_scores, strict=True):
        if float(scores[group.s4_index]) < float(np.max(scores)) - tolerance:
            raise RouteLearningCampaignError(
                f"S4_INDEX_COST_MISMATCH:{group.choice_group_id}"
            )


def _fast_matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """Small deterministic matrix product that avoids broken tiny BLAS calls."""

    return np.einsum("ij,j->i", matrix, vector, optimize=False)


def _augment_candidate_set(features: np.ndarray) -> np.ndarray:
    mean = np.mean(features, axis=0)
    maximum = np.max(features, axis=0)
    return np.concatenate(
        (
            features,
            np.broadcast_to(mean, features.shape),
            np.broadcast_to(maximum, features.shape),
            features - mean,
            features - maximum,
        ),
        axis=1,
    )


def _fit_tiny_regressor(
    features: np.ndarray,
    targets: np.ndarray,
    *,
    feature_names: Sequence[str],
    hidden_dim: int,
    epochs: int,
    learning_rate: float,
    seed: int,
) -> TinyMLPRegressor:
    """Fit the reused one-hidden-layer G18 model without tiny BLAS dispatch."""

    matrix = np.asarray(features, dtype=np.float64)
    target = np.asarray(targets, dtype=np.float64)
    mean = np.mean(matrix, axis=0)
    scale = np.std(matrix, axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    normalized = (matrix - mean) / scale
    target_mean = float(np.mean(target))
    target_scale = float(np.std(target))
    if target_scale <= 1e-12:
        target_scale = 1.0
    normalized_target = (target - target_mean) / target_scale

    rng = np.random.default_rng(int(seed))
    input_weights = rng.normal(0.0, 0.08, size=(matrix.shape[1], hidden_dim))
    hidden_bias = np.zeros(hidden_dim, dtype=np.float64)
    output_weights = rng.normal(0.0, 0.08, size=hidden_dim)
    output_bias = 0.0
    inverse_count = 1.0 / matrix.shape[0]
    for _ in range(epochs):
        hidden = np.tanh(
            np.einsum("ij,jk->ik", normalized, input_weights, optimize=False)
            + hidden_bias
        )
        prediction = _fast_matvec(hidden, output_weights) + output_bias
        residual = prediction - normalized_target
        grad_output = (
            np.einsum("ij,i->j", hidden, residual, optimize=False) * inverse_count
            + 1e-4 * output_weights
        )
        hidden_gradient = residual[:, None] * output_weights[None, :]
        preactivation_gradient = hidden_gradient * (1.0 - hidden * hidden)
        grad_input = (
            np.einsum(
                "ij,ik->jk", normalized, preactivation_gradient, optimize=False
            )
            * inverse_count
            + 1e-4 * input_weights
        )
        input_weights -= learning_rate * grad_input
        hidden_bias -= learning_rate * np.mean(preactivation_gradient, axis=0)
        output_weights -= learning_rate * grad_output
        output_bias -= learning_rate * float(np.mean(residual))
    return TinyMLPRegressor(
        tuple(feature_names),
        mean,
        scale,
        input_weights,
        hidden_bias,
        output_weights,
        output_bias,
        target_mean,
        target_scale,
    )


def _predict_tiny(regressor: TinyMLPRegressor, features: np.ndarray) -> np.ndarray:
    normalized = (features - regressor.mean) / regressor.scale
    hidden = np.tanh(
        np.einsum(
            "ij,jk->ik", normalized, regressor.input_weights, optimize=False
        )
        + regressor.hidden_bias
    )
    normalized_prediction = (
        _fast_matvec(hidden, regressor.output_weights) + regressor.output_bias
    )
    return normalized_prediction * regressor.target_scale + regressor.target_mean


def _fit_model(
    family: str,
    candidate_sets: Sequence[np.ndarray],
    utility_sets: Sequence[np.ndarray],
    s4_indices: Sequence[int],
    *,
    feature_names: Sequence[str],
    epochs: int,
    seed: int,
) -> Any:
    if family == "linear_residual":
        rows: list[np.ndarray] = []
        labels: list[float] = []
        for features, utility, s4_index in zip(
            candidate_sets,
            utility_sets,
            s4_indices,
            strict=True,
        ):
            for candidate_index in range(features.shape[0]):
                if candidate_index == s4_index:
                    continue
                advantage = float(utility[candidate_index] - utility[s4_index])
                if abs(advantage) <= 1e-12:
                    continue
                delta = features[candidate_index] - features[s4_index]
                preferred = 1.0 if advantage > 0.0 else 0.0
                rows.extend((delta, -delta))
                labels.extend((preferred, 1.0 - preferred))
        if not rows:
            raise ValueError("PAIRWISE_TRAINING_REQUIRES_NONTIED_ACTIONS")
        matrix = np.asarray(rows, dtype=np.float64)
        target = np.asarray(labels, dtype=np.float64)
        mean = np.mean(matrix, axis=0)
        scale = np.std(matrix, axis=0)
        scale = np.where(scale > 1e-12, scale, 1.0)
        normalized = (matrix - mean) / scale
        weights = np.zeros(matrix.shape[1], dtype=np.float64)
        bias = 0.0
        for _ in range(epochs):
            logits = _fast_matvec(normalized, weights) + bias
            probabilities = 1.0 / (1.0 + np.exp(-np.clip(logits, -40.0, 40.0)))
            residual = probabilities - target
            gradient = (
                np.einsum("ij,i->j", normalized, residual, optimize=False)
                / matrix.shape[0]
                + 1e-3 * weights
            )
            weights -= 0.05 * gradient
            bias -= 0.05 * float(np.mean(residual))
        ranker = PairwiseLinearRanker(
            tuple(f"delta_{name}" for name in feature_names),
            mean,
            scale,
            weights,
            bias,
        )
        return PairwiseResidualScorer(tuple(feature_names), ranker)
    if family == "tiny_mlp_residual":
        features = np.concatenate(candidate_sets, axis=0)
        advantages = np.concatenate(
            [
                utility - utility[s4_index]
                for utility, s4_index in zip(utility_sets, s4_indices, strict=True)
            ],
            axis=0,
        )
        regressor = _fit_tiny_regressor(
            features,
            advantages,
            feature_names=feature_names,
            hidden_dim=8,
            epochs=epochs,
            learning_rate=0.03,
            seed=seed,
        )
        return TinyResidualScorer(regressor)
    if family == "set_scorer":
        augmented = [_augment_candidate_set(features) for features in candidate_sets]
        set_feature_names = tuple(
            f"{prefix}__{name}"
            for prefix in ("self", "set_mean", "set_max", "delta_mean", "delta_max")
            for name in feature_names
        )
        regressor = _fit_tiny_regressor(
            np.concatenate(augmented, axis=0),
            np.concatenate(utility_sets, axis=0),
            feature_names=set_feature_names,
            hidden_dim=8,
            epochs=epochs,
            learning_rate=0.03,
            seed=seed,
        )
        return SetCandidateScorer(tuple(feature_names), regressor)
    raise RouteLearningCampaignError(f"UNKNOWN_MODEL_FAMILY:{family}")


def _score_model(
    family: str,
    model: Any,
    candidate_sets: Sequence[np.ndarray],
    baseline_scores: Sequence[np.ndarray],
    s4_indices: Sequence[int],
) -> list[np.ndarray]:
    if family == "linear_residual":
        result: list[np.ndarray] = []
        for features, baseline, s4_index in zip(
            candidate_sets, baseline_scores, s4_indices, strict=True
        ):
            deltas = features - features[s4_index]
            normalized = (deltas - model.ranker.mean) / model.ranker.scale
            residual = _fast_matvec(normalized, model.ranker.weights) + model.ranker.bias
            residual[s4_index] = 0.0
            result.append(np.asarray(baseline) + model.residual_scale * residual)
        return result
    if family == "tiny_mlp_residual":
        return [
            np.asarray(baseline)
            + model.residual_scale * _predict_tiny(model.regressor, features)
            for features, baseline in zip(
                candidate_sets,
                baseline_scores,
                strict=True,
            )
        ]
    if family == "set_scorer":
        return [
            _predict_tiny(model.regressor, _augment_candidate_set(features))
            for features in candidate_sets
        ]
    raise RouteLearningCampaignError(f"UNKNOWN_MODEL_FAMILY:{family}")


def _selected_indices(score_sets: Sequence[np.ndarray]) -> list[int]:
    return [int(np.argmax(scores)) for scores in score_sets]


def _binary_auc(labels: Sequence[int], scores: Sequence[float]) -> float:
    label_array = np.asarray(labels, dtype=np.int8)
    score_array = np.asarray(scores, dtype=np.float64)
    positives = int(np.sum(label_array == 1))
    negatives = int(np.sum(label_array == 0))
    if positives == 0 or negatives == 0:
        return 0.0
    order = np.argsort(score_array, kind="mergesort")
    ranks = np.empty(score_array.size, dtype=np.float64)
    start = 0
    while start < order.size:
        end = start + 1
        while end < order.size and score_array[order[end]] == score_array[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    positive_rank_sum = float(np.sum(ranks[label_array == 1]))
    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def _pairwise_auc(
    score_sets: Sequence[np.ndarray],
    utility_sets: Sequence[np.ndarray],
    *,
    tolerance: float = 1e-9,
) -> float:
    labels: list[int] = []
    scores: list[float] = []
    for predicted, utility in zip(score_sets, utility_sets, strict=True):
        for left in range(len(predicted) - 1):
            for right in range(left + 1, len(predicted)):
                utility_delta = float(utility[left] - utility[right])
                if abs(utility_delta) <= tolerance:
                    continue
                predicted_delta = float(predicted[left] - predicted[right])
                oriented = predicted_delta if utility_delta > 0.0 else -predicted_delta
                labels.extend((1, 0))
                scores.extend((oriented, -oriented))
    return _binary_auc(labels, scores)


def _evaluate_scores(
    score_sets: Sequence[np.ndarray],
    groups: Sequence[RouteChoiceGroup],
) -> dict[str, Any]:
    utilities = [group.utilities for group in groups]
    s4_indices = [group.s4_index for group in groups]
    metrics = offline_route_metrics(score_sets, utilities, s4_indices)
    selected = _selected_indices(score_sets)
    top1 = sum(
        int(float(group.utilities[index]) >= float(np.max(group.utilities)) - 1e-9)
        for group, index in zip(groups, selected, strict=True)
    ) / len(groups)
    result = metrics.to_dict()
    advantages = np.asarray(
        [
            float(group.utilities[index] - group.utilities[group.s4_index])
            for group, index in zip(groups, selected, strict=True)
        ],
        dtype=np.float64,
    )
    standard_error = (
        float(np.std(advantages, ddof=1) / math.sqrt(advantages.size))
        if advantages.size > 1
        else math.inf
    )
    result.update(
        top1_accuracy=float(top1),
        pairwise_auc=float(_pairwise_auc(score_sets, utilities)),
        mean_advantage_lcb90=(
            float(np.mean(advantages)) - 1.645 * standard_error
        ),
    )
    return result


def _selective_score_sets(
    raw_scores: Sequence[np.ndarray],
    groups: Sequence[RouteChoiceGroup],
    threshold: float | None,
) -> list[np.ndarray]:
    selective: list[np.ndarray] = []
    for scores, group in zip(raw_scores, groups, strict=True):
        proposed = int(np.argmax(scores))
        margin = float(scores[proposed] - scores[group.s4_index])
        apply = (
            threshold is not None
            and proposed != group.s4_index
            and margin >= threshold
        )
        if apply:
            selective.append(np.asarray(scores, dtype=np.float64).copy())
            continue
        fallback = np.asarray(scores, dtype=np.float64).copy()
        spread = float(np.max(fallback) - np.min(fallback))
        fallback[group.s4_index] = float(np.max(fallback)) + max(1.0, spread + 1.0)
        selective.append(fallback)
    return selective


def _coverage(
    raw_scores: Sequence[np.ndarray],
    selective_scores: Sequence[np.ndarray],
    groups: Sequence[RouteChoiceGroup],
) -> dict[str, Any]:
    raw_selected = _selected_indices(raw_scores)
    selected = _selected_indices(selective_scores)
    proposal_count = sum(
        int(index != group.s4_index)
        for index, group in zip(raw_selected, groups, strict=True)
    )
    applied_count = sum(
        int(index != group.s4_index)
        for index, group in zip(selected, groups, strict=True)
    )
    count = len(groups)
    return {
        "group_count": count,
        "raw_mutation_proposal_count": proposal_count,
        "raw_mutation_proposal_rate": proposal_count / count,
        "applied_mutation_count": applied_count,
        "coverage": applied_count / count,
        "coverage_of_raw_proposals": (
            applied_count / proposal_count if proposal_count else 0.0
        ),
        "abstention_count": count - applied_count,
        "abstention_rate": 1.0 - applied_count / count,
    }


def _normal_flow_mutation_potential(
    raw_scores: Sequence[np.ndarray],
    selective_scores: Sequence[np.ndarray],
    groups: Sequence[RouteChoiceGroup],
) -> dict[str, Any]:
    indices = [index for index, group in enumerate(groups) if group.normal_flow]
    if not indices:
        return {
            "group_count": 0,
            "raw_mutation_proposal_count": 0,
            "applied_mutation_count": 0,
            "coverage": 0.0,
            "beneficial_applied_count": 0,
            "harmful_applied_count": 0,
            "beneficial_precision": 0.0,
            "harmful_applied_rate": 0.0,
        }
    flow_groups = _subset(groups, indices)
    flow_raw = _subset(raw_scores, indices)
    flow_selective = _subset(selective_scores, indices)
    coverage = _coverage(flow_raw, flow_selective, flow_groups)
    decision = _evaluate_scores(flow_selective, flow_groups)
    return {
        **coverage,
        "beneficial_applied_count": decision["beneficial_applied_count"],
        "harmful_applied_count": decision["harmful_applied_count"],
        "beneficial_precision": decision["beneficial_precision"],
        "harmful_applied_rate": decision["harmful_applied_rate"],
        "mean_advantage_vs_s4": decision["mean_advantage_vs_s4"],
    }


def _calibrate_threshold(
    raw_scores: Sequence[np.ndarray],
    groups: Sequence[RouteChoiceGroup],
    gates: Mapping[str, float],
) -> float | None:
    margins = sorted(
        {
            float(scores[int(np.argmax(scores))] - scores[group.s4_index])
            for scores, group in zip(raw_scores, groups, strict=True)
            if int(np.argmax(scores)) != group.s4_index
        }
    )
    feasible: list[tuple[int, float, float]] = []
    for threshold in margins:
        selective = _selective_score_sets(raw_scores, groups, threshold)
        metrics = _evaluate_scores(selective, groups)
        if (
            metrics["applied_count"] >= int(gates["minimum_applied_count"])
            and metrics["beneficial_precision"]
            >= gates["beneficial_precision_min"]
            and metrics["harmful_applied_rate"]
            <= gates["harmful_applied_rate_max"]
        ):
            feasible.append(
                (
                    int(metrics["applied_count"]),
                    float(metrics["mean_advantage_vs_s4"]),
                    float(threshold),
                )
            )
    if not feasible:
        return None
    # Maximum safe coverage, then maximum benefit, then the lower margin.
    return max(feasible, key=lambda row: (row[0], row[1], -row[2]))[2]


def _promotion_checks(
    validation: Mapping[str, Any],
    audit: Mapping[str, Any],
    audit_baseline: Mapping[str, Any],
    audit_normal_flow: Mapping[str, Any],
    data_checks: Mapping[str, bool],
    gates: Mapping[str, float],
) -> dict[str, bool]:
    minimum_applied = int(gates["minimum_applied_count"])
    return {
        "data_contract": all(data_checks.values()),
        "validation_applied_support": validation["applied_count"] >= minimum_applied,
        "validation_beneficial_precision": (
            validation["beneficial_precision"] >= gates["beneficial_precision_min"]
        ),
        "validation_harmful_applied_rate": (
            validation["harmful_applied_rate"] <= gates["harmful_applied_rate_max"]
        ),
        "audit_applied_support": audit["applied_count"] >= minimum_applied,
        "audit_beneficial_precision": (
            audit["beneficial_precision"] >= gates["beneficial_precision_min"]
        ),
        "audit_harmful_applied_rate": (
            audit["harmful_applied_rate"] <= gates["harmful_applied_rate_max"]
        ),
        "audit_normal_flow_mutation": (
            audit_normal_flow["applied_mutation_count"] >= minimum_applied
        ),
        "audit_normal_flow_beneficial_precision": (
            audit_normal_flow["beneficial_precision"]
            >= gates["beneficial_precision_min"]
        ),
        "audit_pairwise_accuracy": (
            audit["pairwise_accuracy"] >= gates["pairwise_accuracy_min"]
        ),
        "audit_s4_preservation": (
            audit["s4_preservation"] >= gates["s4_preservation_min"]
        ),
        "audit_positive_advantage": (
            audit["mean_advantage_vs_s4"] > gates["mean_advantage_vs_s4_min"]
        ),
        "audit_advantage_lcb90_positive": (
            audit["mean_advantage_lcb90"] > gates["mean_advantage_lcb_min"]
        ),
        "audit_regret_improves_s4": (
            audit["mean_regret"] < audit_baseline["mean_regret"] - 1e-9
        ),
    }


def _support_counts(groups: Sequence[RouteChoiceGroup]) -> dict[str, int]:
    beneficial = harmful = neutral = 0
    for group in groups:
        s4_utility = float(group.utilities[group.s4_index])
        for index, utility in enumerate(group.utilities):
            if index == group.s4_index:
                continue
            advantage = float(utility) - s4_utility
            beneficial += int(advantage > 1e-9)
            harmful += int(advantage < -1e-9)
            neutral += int(abs(advantage) <= 1e-9)
    return {
        "beneficial_alternative_count": beneficial,
        "harmful_alternative_count": harmful,
        "neutral_alternative_count": neutral,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_campaign(
    *,
    input_path: Path,
    report_path: Path,
    policy_path: Path,
    epochs: int = 240,
    seed: int = 20,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    gates: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    _require(epochs > 0, "epochs must be positive")
    resolved_gates = dict(DEFAULT_GATES if gates is None else gates)
    _require(set(resolved_gates) == set(DEFAULT_GATES), "gate keys mismatch")

    groups = load_compact_jsonl(input_path)
    feature_cache = {
        group: _feature_matrices(groups, group)
        for group in RouteFeatureGroup
    }
    baseline_scores = _baseline_score_sets(feature_cache[RouteFeatureGroup.F0])
    _validate_s4_indices(groups, baseline_scores)

    split = grouped_split_indices(
        [group.split_group_id for group in groups],
        train_fraction=train_fraction,
        validation_fraction=validation_fraction,
        seed=seed,
    )
    split_indices = {
        "train": split.train,
        "validation": split.validation,
        "audit": split.audit,
    }
    split_keys = {
        name: {groups[index].split_group_id for index in indices}
        for name, indices in split_indices.items()
    }
    contamination = sum(
        len(split_keys[left] & split_keys[right])
        for left, right in (
            ("train", "validation"),
            ("train", "audit"),
            ("validation", "audit"),
        )
    )
    support = _support_counts(groups)
    data_checks = {
        "group_split_contamination_zero": contamination == 0,
        "feature_leakage_zero": True,
        "primary_pair_complete": all(
            group.primary_pair_labeled and len(group.native_candidates) >= 2
            for group in groups
        ),
        "full_legal_action_set_labeled": all(
            group.full_legal_action_set_labeled for group in groups
        ),
        "wait_action_labeled": all(group.wait_action_labeled for group in groups),
        "all_actions_legal": True,
        "beneficial_support_nonzero": support["beneficial_alternative_count"] > 0,
        "harmful_support_nonzero": support["harmful_alternative_count"] > 0,
    }

    split_groups = {
        name: _subset(groups, indices)
        for name, indices in split_indices.items()
    }
    split_baselines = {
        name: _subset(baseline_scores, indices)
        for name, indices in split_indices.items()
    }
    baseline_metrics = {
        name: _evaluate_scores(
            _selective_score_sets(scores, rows, None),
            rows,
        )
        for name, scores, rows in (
            (
                split_name,
                split_baselines[split_name],
                split_groups[split_name],
            )
            for split_name in ("validation", "audit")
        )
    }

    comparisons: list[dict[str, Any]] = []
    trained_models: dict[tuple[RouteFeatureGroup, str], Any] = {}
    for feature_group in RouteFeatureGroup:
        contract = FEATURE_GROUP_CONTRACTS[feature_group]
        all_features = feature_cache[feature_group]
        train_features = _subset(all_features, split.train)
        validation_features = _subset(all_features, split.validation)
        audit_features = _subset(all_features, split.audit)
        train_groups = split_groups["train"]
        train_utilities = [group.utilities for group in train_groups]
        train_s4 = [group.s4_index for group in train_groups]

        for family in MODEL_FAMILIES:
            row: dict[str, Any] = {
                "feature_group": feature_group.value,
                "feature_dimension": contract.dimension,
                "model_family": family,
            }
            try:
                model = _fit_model(
                    family,
                    train_features,
                    train_utilities,
                    train_s4,
                    feature_names=contract.feature_names,
                    epochs=epochs,
                    seed=seed,
                )
                trained_models[(feature_group, family)] = model
                validation_raw_scores = _score_model(
                    family,
                    model,
                    validation_features,
                    split_baselines["validation"],
                    [group.s4_index for group in split_groups["validation"]],
                )
                threshold = _calibrate_threshold(
                    validation_raw_scores,
                    split_groups["validation"],
                    resolved_gates,
                )
                validation_selective_scores = _selective_score_sets(
                    validation_raw_scores,
                    split_groups["validation"],
                    threshold,
                )
                audit_raw_scores = _score_model(
                    family,
                    model,
                    audit_features,
                    split_baselines["audit"],
                    [group.s4_index for group in split_groups["audit"]],
                )
                audit_selective_scores = _selective_score_sets(
                    audit_raw_scores,
                    split_groups["audit"],
                    threshold,
                )
                validation_raw = _evaluate_scores(
                    validation_raw_scores,
                    split_groups["validation"],
                )
                validation_selective = _evaluate_scores(
                    validation_selective_scores,
                    split_groups["validation"],
                )
                audit_raw = _evaluate_scores(
                    audit_raw_scores,
                    split_groups["audit"],
                )
                audit_selective = _evaluate_scores(
                    audit_selective_scores,
                    split_groups["audit"],
                )
                audit_normal_flow = _normal_flow_mutation_potential(
                    audit_raw_scores,
                    audit_selective_scores,
                    split_groups["audit"],
                )
                checks = _promotion_checks(
                    validation_selective,
                    audit_selective,
                    baseline_metrics["audit"],
                    audit_normal_flow,
                    data_checks,
                    resolved_gates,
                )
                row.update(
                    status="EVALUATED",
                    mutation_margin_threshold=threshold,
                    model_summary=route_model_summary(model),
                    validation={
                        "raw": validation_raw,
                        "selective": validation_selective,
                        "coverage": _coverage(
                            validation_raw_scores,
                            validation_selective_scores,
                            split_groups["validation"],
                        ),
                    },
                    audit={
                        "raw": audit_raw,
                        "selective": audit_selective,
                        "coverage": _coverage(
                            audit_raw_scores,
                            audit_selective_scores,
                            split_groups["audit"],
                        ),
                        "normal_flow_mutation_potential": (
                            audit_normal_flow
                        ),
                    },
                    promotion_checks=checks,
                    promotion_pass=all(checks.values()),
                )
            except (ValueError, FloatingPointError) as exc:
                row.update(
                    status="TRAINING_FAILED",
                    error=str(exc),
                    promotion_pass=False,
                )
            comparisons.append(row)

    promoted = [row for row in comparisons if row.get("promotion_pass") is True]
    promoted.sort(
        key=lambda row: (
            int(row["feature_dimension"]),
            MODEL_COMPLEXITY[str(row["model_family"])],
            str(row["feature_group"]),
        )
    )
    selected = promoted[0] if promoted else None
    status = "OFFLINE_GO" if selected is not None else "NO_GO"
    complete_action_contract = (
        data_checks["full_legal_action_set_labeled"]
        and data_checks["wait_action_labeled"]
    )
    if selected is not None:
        selection_reason = "simplest audit-passing model is an offline candidate"
    elif not complete_action_contract:
        selection_reason = (
            "promotion blocked: exact labels cover S4 versus one primary "
            "alternative, not every legal edge and WAIT"
        )
    else:
        selection_reason = "no model improved S4 while passing all offline gates"
    selection: dict[str, Any] = {
        "status": status,
        "reason": selection_reason,
        "selected_feature_group": (
            selected["feature_group"] if selected is not None else None
        ),
        "selected_model_family": (
            selected["model_family"] if selected is not None else None
        ),
        "policy_exported": selected is not None,
    }

    report: dict[str, Any] = {
        "schema_id": CAMPAIGN_SCHEMA,
        "status": status,
        "input_schema": COMPACT_SCHEMA,
        "data": {
            "choice_group_count": len(groups),
            "candidate_count": sum(len(group.native_candidates) for group in groups),
            "unique_split_group_count": len({group.split_group_id for group in groups}),
            "split_choice_group_counts": {
                name: len(indices) for name, indices in split_indices.items()
            },
            "group_split_contamination_count": contamination,
            "support": support,
            "checks": data_checks,
        },
        "feature_groups": {
            group.value: {
                "dimension": contract.dimension,
                "feature_names": list(contract.feature_names),
                "purpose": contract.purpose,
            }
            for group, contract in FEATURE_GROUP_CONTRACTS.items()
        },
        "models_compared": list(MODEL_FAMILIES),
        "gates": resolved_gates,
        "s4_baseline": baseline_metrics,
        "comparisons": comparisons,
        "selection": selection,
    }

    if selected is not None:
        feature_group = RouteFeatureGroup(str(selected["feature_group"]))
        family = str(selected["model_family"])
        model = trained_models[(feature_group, family)]
        policy = {
            "schema_id": POLICY_SCHEMA,
            "status": "OFFLINE_CANDIDATE",
            "active": False,
            "native_closed_loop_validated": False,
            "fallback": "S4",
            "score_direction": "higher_is_better",
            "s4_native_cost_direction": "lower_is_better",
            "feature_contract": "RICH_ROUTE_V2",
            "feature_group": feature_group.value,
            "feature_names": list(FEATURE_GROUP_CONTRACTS[feature_group].feature_names),
            "model_family": family,
            "mutation_margin_threshold": selected["mutation_margin_threshold"],
            "model": model.to_dict(),
            "audit_metrics": selected["audit"],
            "promotion_checks": selected["promotion_checks"],
        }
        _write_json(policy_path, policy)
    elif policy_path.exists():
        # A failed rerun must not leave a previously active research policy
        # looking current.  The report remains the authoritative NO_GO record.
        policy_path.unlink()

    _write_json(report_path, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--epochs", type=int, default=240)
    parser.add_argument("--seed", type=int, default=20)
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = run_campaign(
        input_path=args.input,
        report_path=args.report,
        policy_path=args.policy,
        epochs=args.epochs,
        seed=args.seed,
        train_fraction=args.train_fraction,
        validation_fraction=args.validation_fraction,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(args.report),
                "policy_exported": report["selection"]["policy_exported"],
                "policy": str(args.policy) if report["selection"]["policy_exported"] else None,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
