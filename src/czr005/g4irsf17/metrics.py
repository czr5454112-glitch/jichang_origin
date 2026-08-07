"""Offline ranking, selective-risk, calibration, and bucket metrics."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np

from .selection import expected_calibration_error


def system_utility(
    own_bag_effect_seconds: float,
    bounded_external_bag_effects_seconds: Sequence[float],
    *,
    tail_harm_penalty_seconds: float = 0.0,
    deadline_risk_seconds: float = 0.0,
    starvation_penalty_seconds: float = 0.0,
    max_external_bags: int = 8,
) -> float:
    """Canonical Phase-D target with a fixed local externality horizon."""

    if max_external_bags < 0:
        raise ValueError("MAX_EXTERNAL_BAGS_MUST_BE_NONNEGATIVE")
    values = [float(own_bag_effect_seconds)]
    values.extend(
        float(value)
        for value in bounded_external_bag_effects_seconds[:max_external_bags]
    )
    penalties = (
        float(tail_harm_penalty_seconds),
        float(deadline_risk_seconds),
        float(starvation_penalty_seconds),
    )
    if not all(math.isfinite(value) for value in (*values, *penalties)):
        raise ValueError("SYSTEM_UTILITY_COMPONENT_NOT_FINITE")
    if any(value < 0.0 for value in penalties):
        raise ValueError("SYSTEM_UTILITY_PENALTY_NEGATIVE")
    return math.fsum(values) - math.fsum(penalties)


def ranking_metrics(
    candidate_utilities: Sequence[Sequence[float]],
    chosen_indices: Sequence[int],
    *,
    baseline_indices: Sequence[int] | None = None,
    legal_masks: Sequence[Sequence[bool]] | None = None,
    tolerance: float = 1e-9,
) -> dict[str, float | int | None]:
    """Evaluate system-level utility rather than just the chosen bag's delay."""

    count = len(candidate_utilities)
    if len(chosen_indices) != count:
        raise ValueError("RANKING_ROW_COUNT_MISMATCH")
    if baseline_indices is not None and len(baseline_indices) != count:
        raise ValueError("BASELINE_ROW_COUNT_MISMATCH")
    if legal_masks is not None and len(legal_masks) != count:
        raise ValueError("LEGAL_MASK_ROW_COUNT_MISMATCH")
    chosen_values: list[float] = []
    regrets: list[float] = []
    top1 = 0
    advantages: list[float] = []
    for row_index, raw_values in enumerate(candidate_utilities):
        values = np.asarray(raw_values, dtype=np.float64)
        if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
            raise ValueError("CANDIDATE_UTILITIES_INVALID")
        mask = (
            np.ones(values.size, dtype=bool)
            if legal_masks is None
            else np.asarray(legal_masks[row_index], dtype=bool)
        )
        if mask.shape != values.shape or not np.any(mask):
            raise ValueError("LEGAL_MASK_INVALID")
        chosen = int(chosen_indices[row_index])
        if chosen < 0 or chosen >= values.size or not mask[chosen]:
            raise ValueError("CHOSEN_INDEX_NOT_LEGAL")
        oracle = float(np.max(values[mask]))
        chosen_value = float(values[chosen])
        chosen_values.append(chosen_value)
        regrets.append(oracle - chosen_value)
        top1 += chosen_value >= oracle - tolerance
        if baseline_indices is not None:
            baseline = int(baseline_indices[row_index])
            if baseline < 0 or baseline >= values.size or not mask[baseline]:
                raise ValueError("BASELINE_INDEX_NOT_LEGAL")
            advantages.append(chosen_value - float(values[baseline]))
    advantage_array = np.asarray(advantages, dtype=np.float64)
    return {
        "row_count": count,
        "top1_accuracy": top1 / count if count else 0.0,
        "mean_system_utility": float(np.mean(chosen_values)) if chosen_values else None,
        "mean_regret": float(np.mean(regrets)) if regrets else None,
        "p95_regret": float(np.quantile(regrets, 0.95)) if regrets else None,
        "mean_advantage_vs_baseline": (
            float(np.mean(advantage_array)) if advantage_array.size else None
        ),
        "beneficial_override_rate": (
            float(np.mean(advantage_array > tolerance)) if advantage_array.size else None
        ),
        "harmful_override_rate": (
            float(np.mean(advantage_array < -tolerance)) if advantage_array.size else None
        ),
    }


def evaluate_policy(
    candidate_utilities: Sequence[Sequence[float]],
    chosen_indices: Sequence[int],
    *,
    baseline_indices: Sequence[int] | None = None,
    legal_masks: Sequence[Sequence[bool]] | None = None,
) -> dict[str, float | int | None]:
    """Campaign-friendly alias for :func:`ranking_metrics`."""

    return ranking_metrics(
        candidate_utilities,
        chosen_indices,
        baseline_indices=baseline_indices,
        legal_masks=legal_masks,
    )


def evaluate_policy_families(
    candidate_utilities: Sequence[Sequence[float]],
    family_choices: Mapping[str, Sequence[int]],
    *,
    baseline_indices: Sequence[int],
    legal_masks: Sequence[Sequence[bool]] | None = None,
) -> dict[str, Any]:
    """Evaluate several Phase-D families under one identical utility panel."""

    return {
        "schema": "czr005.g4irsf17.policy_family_evaluation.v1",
        "target": (
            "own_bag_effect + bounded_external_bag_effect - tail_harm "
            "- deadline_risk - starvation_penalty"
        ),
        "families": {
            str(family): ranking_metrics(
                candidate_utilities,
                choices,
                baseline_indices=baseline_indices,
                legal_masks=legal_masks,
            )
            for family, choices in family_choices.items()
        },
    }


def selective_override_metrics(
    observed_advantages: Sequence[float],
    activations: Sequence[bool],
    *,
    tolerance: float = 1e-9,
) -> dict[str, float | int]:
    advantage = np.asarray(observed_advantages, dtype=np.float64)
    active = np.asarray(activations, dtype=bool)
    if advantage.ndim != 1 or active.shape != advantage.shape or not np.all(np.isfinite(advantage)):
        raise ValueError("SELECTIVE_METRIC_INPUT_MISMATCH")
    beneficial = advantage > tolerance
    harmful = advantage < -tolerance
    activated_beneficial = active & beneficial
    activated_harmful = active & harmful
    activation_count = int(np.sum(active))
    return {
        "row_count": int(advantage.size),
        "activation_count": activation_count,
        "activation_coverage": float(np.mean(active)) if active.size else 0.0,
        "beneficial_precision": (
            float(np.sum(activated_beneficial) / activation_count) if activation_count else 0.0
        ),
        "beneficial_recall": (
            float(np.sum(activated_beneficial) / np.sum(beneficial)) if np.any(beneficial) else 0.0
        ),
        # Harmful recall is veto recall: how often the conservative selector
        # correctly abstained on a truly harmful proposal.
        "harmful_recall": (
            float(np.sum(harmful & ~active) / np.sum(harmful)) if np.any(harmful) else 0.0
        ),
        "harmful_activation_rate": (
            float(np.mean(activated_harmful)) if active.size else 0.0
        ),
        "activated_utility_mean": (
            float(np.mean(advantage[active])) if activation_count else 0.0
        ),
    }


def bucket_generalization_metrics(
    observed_advantages: Sequence[float],
    activations: Sequence[bool],
    buckets: Sequence[Any],
) -> list[dict[str, Any]]:
    if not (len(observed_advantages) == len(activations) == len(buckets)):
        raise ValueError("BUCKET_METRIC_INPUT_MISMATCH")
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, bucket in enumerate(buckets):
        grouped[str(bucket)].append(index)
    output: list[dict[str, Any]] = []
    for bucket, indices in sorted(grouped.items()):
        metrics = selective_override_metrics(
            [observed_advantages[index] for index in indices],
            [activations[index] for index in indices],
        )
        output.append({"bucket": bucket, **metrics})
    return output


def calibration_metrics(
    benefit_probabilities: Sequence[float],
    benefit_labels: Sequence[int],
    harm_probabilities: Sequence[float] | None = None,
    harm_labels: Sequence[int] | None = None,
    *,
    bin_count: int = 10,
) -> dict[str, float]:
    result = {
        "benefit_ece": expected_calibration_error(
            benefit_probabilities, benefit_labels, bin_count=bin_count
        )
    }
    if harm_probabilities is not None or harm_labels is not None:
        if harm_probabilities is None or harm_labels is None:
            raise ValueError("HARM_CALIBRATION_INPUT_MISMATCH")
        result["harm_ece"] = expected_calibration_error(
            harm_probabilities, harm_labels, bin_count=bin_count
        )
    return result
