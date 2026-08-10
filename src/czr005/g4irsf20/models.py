"""Small G20 Route-learning utilities built on the proven G18 scorers.

No model implementation is copied here.  The module re-exports reusable G18
primitives and adds only the Route-specific data split, S4 score-direction
adapter, model summary, and offline choice metrics.  The formal G20 campaign
compares three families; the standalone primitive remains a dormant pivot.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Hashable, Sequence

import numpy as np

from ..g4irsf18.models import (
    PairwiseResidualScorer,
    SetCandidateScorer,
    StandaloneMLPScorer,
    TinyResidualScorer,
)


@dataclass(frozen=True)
class GroupedIndexSplit:
    """Row indices split by whole choice group."""

    train: tuple[int, ...]
    validation: tuple[int, ...]
    audit: tuple[int, ...]

    def as_dict(self) -> dict[str, list[int]]:
        return {
            "train": list(self.train),
            "validation": list(self.validation),
            "audit": list(self.audit),
        }


def _allocated_group_counts(group_count: int, fractions: Sequence[float]) -> list[int]:
    raw = [group_count * fraction for fraction in fractions]
    counts = [int(value) for value in raw]
    positive = [index for index, fraction in enumerate(fractions) if fraction > 0.0]
    if group_count < len(positive):
        raise ValueError("NOT_ENOUGH_GROUPS_FOR_NONEMPTY_SPLITS")
    for index in positive:
        if counts[index] == 0:
            counts[index] = 1
    while sum(counts) > group_count:
        removable = [index for index in positive if counts[index] > 1]
        if not removable:
            raise ValueError("NOT_ENOUGH_GROUPS_FOR_NONEMPTY_SPLITS")
        index = max(removable, key=lambda item: counts[item] - raw[item])
        counts[index] -= 1
    while sum(counts) < group_count:
        index = max(range(len(counts)), key=lambda item: raw[item] - counts[item])
        counts[index] += 1
    return counts


def grouped_split_indices(
    group_ids: Sequence[Hashable],
    *,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    seed: int = 20,
) -> GroupedIndexSplit:
    """Return deterministic row indices with zero cross-split group overlap."""

    if not group_ids:
        raise ValueError("GROUP_IDS_MUST_BE_NONEMPTY")
    if not (
        math.isfinite(float(train_fraction))
        and math.isfinite(float(validation_fraction))
        and 0.0 < train_fraction < 1.0
        and 0.0 < validation_fraction < 1.0
        and train_fraction + validation_fraction < 1.0
    ):
        raise ValueError("SPLIT_FRACTIONS_INVALID")

    rows_by_group: dict[Hashable, list[int]] = {}
    try:
        for row_index, group_id in enumerate(group_ids):
            rows_by_group.setdefault(group_id, []).append(row_index)
    except TypeError as exc:
        raise ValueError("GROUP_ID_MUST_BE_HASHABLE") from exc

    ordered_groups = sorted(
        rows_by_group,
        key=lambda value: (type(value).__name__, repr(value)),
    )
    rng = np.random.default_rng(int(seed))
    shuffled_groups = [ordered_groups[index] for index in rng.permutation(len(ordered_groups))]
    audit_fraction = 1.0 - train_fraction - validation_fraction
    counts = _allocated_group_counts(
        len(shuffled_groups),
        (train_fraction, validation_fraction, audit_fraction),
    )
    train_groups = set(shuffled_groups[: counts[0]])
    validation_groups = set(
        shuffled_groups[counts[0] : counts[0] + counts[1]]
    )
    audit_groups = set(shuffled_groups[counts[0] + counts[1] :])

    def indices(selected: set[Hashable]) -> tuple[int, ...]:
        return tuple(index for index, group_id in enumerate(group_ids) if group_id in selected)

    return GroupedIndexSplit(
        indices(train_groups),
        indices(validation_groups),
        indices(audit_groups),
    )


# Short public name for scripts while retaining the explicit return type name.
grouped_split = grouped_split_indices


def s4_costs_to_scores(costs: Any) -> np.ndarray:
    """Convert native S4 lower-is-better costs to scorer higher-is-better scores."""

    values = np.asarray(costs, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("S4_COSTS_MUST_BE_NONEMPTY_FINITE_1D")
    return -values


def route_model_summary(model: Any) -> dict[str, Any]:
    """Return the compact, human-auditable contract shared by reused models."""

    if not hasattr(model, "to_dict") or not hasattr(model, "feature_names"):
        raise TypeError("ROUTE_MODEL_MUST_EXPOSE_TO_DICT_AND_FEATURE_NAMES")
    artifact = model.to_dict()
    return {
        "family": artifact["family"],
        "feature_names": list(model.feature_names),
        "score_direction": "higher_is_better",
        "consumes_s4_scores": bool(artifact.get("consumes_baseline_scores", False)),
        "identity_features_used": bool(artifact.get("identity_features_used", False)),
        "outcome_features_used": bool(artifact.get("outcome_features_used", False)),
    }


@dataclass(frozen=True)
class OfflineRouteMetrics:
    """Choice-level metrics for guarded replacement of S4."""

    group_count: int
    applied_count: int
    beneficial_applied_count: int
    harmful_applied_count: int
    beneficial_precision: float
    harmful_applied_rate: float
    pairwise_accuracy: float
    pairwise_comparisons: int
    s4_preservation: float
    s4_preservation_support: int
    mean_advantage_vs_s4: float
    mean_regret: float
    max_regret: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def offline_route_metrics(
    score_sets: Sequence[Any],
    utility_sets: Sequence[Any],
    s4_indices: Sequence[int],
    *,
    legal_masks: Sequence[Sequence[bool]] | None = None,
    tolerance: float = 1e-9,
) -> OfflineRouteMetrics:
    """Evaluate higher-is-better candidate scores against offline utilities.

    ``beneficial_precision`` and ``harmful_applied_rate`` use only decisions
    that change S4.  ``s4_preservation`` is measured on groups where S4 is
    utility-optimal within ``tolerance``.  Pairwise accuracy compares every
    non-tied legal utility pair.  Regret is against the best legal candidate.
    """

    group_count = len(score_sets)
    if group_count == 0 or not (
        group_count == len(utility_sets) == len(s4_indices)
    ):
        raise ValueError("OFFLINE_GROUP_DIMENSION_MISMATCH")
    if legal_masks is not None and len(legal_masks) != group_count:
        raise ValueError("OFFLINE_LEGAL_MASK_DIMENSION_MISMATCH")
    if not math.isfinite(float(tolerance)) or tolerance < 0.0:
        raise ValueError("METRIC_TOLERANCE_INVALID")

    applied = beneficial = harmful = 0
    pairwise_correct = pairwise_total = 0
    preservation = preservation_support = 0
    advantages: list[float] = []
    regrets: list[float] = []

    for group_index, (raw_scores, raw_utility, raw_s4) in enumerate(
        zip(score_sets, utility_sets, s4_indices, strict=True)
    ):
        scores = np.asarray(raw_scores, dtype=np.float64)
        utility = np.asarray(raw_utility, dtype=np.float64)
        if scores.ndim != 1 or scores.size == 0 or utility.shape != scores.shape:
            raise ValueError("OFFLINE_CANDIDATE_SET_DIMENSION_MISMATCH")
        mask = (
            np.ones(scores.size, dtype=bool)
            if legal_masks is None
            else np.asarray(legal_masks[group_index], dtype=bool)
        )
        if mask.shape != scores.shape or not np.any(mask):
            raise ValueError("OFFLINE_LEGAL_MASK_INVALID")
        if not np.all(np.isfinite(scores[mask])) or not np.all(np.isfinite(utility[mask])):
            raise ValueError("OFFLINE_VALUES_NOT_FINITE")
        s4_index = int(raw_s4)
        if s4_index < 0 or s4_index >= scores.size or not mask[s4_index]:
            raise ValueError("OFFLINE_S4_INDEX_NOT_LEGAL")

        legal = np.flatnonzero(mask)
        chosen = int(legal[int(np.argmax(scores[legal]))])
        best_utility = float(np.max(utility[legal]))
        advantage = float(utility[chosen] - utility[s4_index])
        regret = max(0.0, best_utility - float(utility[chosen]))
        advantages.append(advantage)
        regrets.append(regret)

        if chosen != s4_index:
            applied += 1
            beneficial += int(advantage > tolerance)
            harmful += int(advantage < -tolerance)
        if float(utility[s4_index]) >= best_utility - tolerance:
            preservation_support += 1
            preservation += int(chosen == s4_index)

        for left_position, left in enumerate(legal[:-1]):
            for right in legal[left_position + 1 :]:
                utility_delta = float(utility[left] - utility[right])
                if abs(utility_delta) <= tolerance:
                    continue
                score_delta = float(scores[left] - scores[right])
                pairwise_total += 1
                pairwise_correct += int(score_delta * utility_delta > 0.0)

    return OfflineRouteMetrics(
        group_count=group_count,
        applied_count=applied,
        beneficial_applied_count=beneficial,
        harmful_applied_count=harmful,
        beneficial_precision=beneficial / applied if applied else 0.0,
        harmful_applied_rate=harmful / applied if applied else 0.0,
        pairwise_accuracy=pairwise_correct / pairwise_total if pairwise_total else 0.0,
        pairwise_comparisons=pairwise_total,
        s4_preservation=(
            preservation / preservation_support if preservation_support else 0.0
        ),
        s4_preservation_support=preservation_support,
        mean_advantage_vs_s4=float(np.mean(advantages)),
        mean_regret=float(np.mean(regrets)),
        max_regret=float(np.max(regrets)),
    )


__all__ = [
    "GroupedIndexSplit",
    "OfflineRouteMetrics",
    "PairwiseResidualScorer",
    "SetCandidateScorer",
    "StandaloneMLPScorer",
    "TinyResidualScorer",
    "grouped_split",
    "grouped_split_indices",
    "offline_route_metrics",
    "route_model_summary",
    "s4_costs_to_scores",
]
