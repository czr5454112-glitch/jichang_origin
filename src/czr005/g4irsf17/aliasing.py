"""State-sufficiency and feature-ablation audits for G4IRSF17."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .features import (
    AUGMENTED_WITH_LEGACY_FEATURES,
    CANONICAL_OBSERVATION_FEATURES,
    LEGACY_29_FEATURES,
    assert_strictly_local_feature_names,
)


@dataclass(frozen=True)
class AliasingMetrics:
    row_count: int
    feature_count: int
    pair_count: int
    coverage: float
    conditional_variance: float | None
    sign_disagreement_rate: float | None
    mean_neighbor_distance: float | None
    distance_threshold: float

    def to_dict(self) -> dict[str, int | float | None]:
        return asdict(self)


def _matrix(values: Any, *, name: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        raise ValueError(f"{name}_MUST_BE_NONEMPTY_2D")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name}_NOT_FINITE")
    return matrix


def _targets(values: Any, row_count: int) -> np.ndarray:
    targets = np.asarray(values, dtype=np.float64)
    if targets.shape != (row_count,) or not np.all(np.isfinite(targets)):
        raise ValueError("OUTCOMES_MUST_BE_FINITE_VECTOR")
    return targets


def nearest_neighbor_aliasing(
    features: Any,
    outcomes: Any,
    *,
    neighbor_count: int = 1,
    max_standardized_distance: float = 0.35,
    sign_tolerance: float = 1e-9,
) -> AliasingMetrics:
    """Measure outcome ambiguity among nearby observed local states.

    Distances are root-mean-square z distances, so adding feature dimensions
    does not mechanically increase the threshold.  Pairs are directed from
    each covered anchor to its nearest neighbours; this gives every runtime
    state equal weight rather than letting dense buckets dominate.
    """

    matrix = _matrix(features, name="FEATURES")
    row_count, feature_count = matrix.shape
    targets = _targets(outcomes, row_count)
    if row_count < 2:
        return AliasingMetrics(
            row_count=row_count,
            feature_count=feature_count,
            pair_count=0,
            coverage=0.0,
            conditional_variance=None,
            sign_disagreement_rate=None,
            mean_neighbor_distance=None,
            distance_threshold=float(max_standardized_distance),
        )
    if neighbor_count <= 0 or neighbor_count >= row_count:
        raise ValueError("NEIGHBOR_COUNT_OUT_OF_RANGE")
    if max_standardized_distance <= 0.0:
        raise ValueError("DISTANCE_THRESHOLD_MUST_BE_POSITIVE")

    mean = np.mean(matrix, axis=0)
    scale = np.std(matrix, axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    normalized = (matrix - mean) / scale

    squared_differences: list[float] = []
    sign_conflicts: list[bool] = []
    neighbor_distances: list[float] = []
    covered = 0
    for index in range(row_count):
        delta = normalized - normalized[index]
        distances = np.sqrt(np.mean(delta * delta, axis=1))
        distances[index] = np.inf
        nearest = np.argpartition(distances, neighbor_count - 1)[:neighbor_count]
        nearest = nearest[np.argsort(distances[nearest], kind="stable")]
        accepted = [
            int(other)
            for other in nearest
            if float(distances[other]) <= max_standardized_distance
        ]
        if accepted:
            covered += 1
        for other in accepted:
            outcome_delta = float(targets[index] - targets[other])
            squared_differences.append(0.5 * outcome_delta * outcome_delta)
            left = float(targets[index])
            right = float(targets[other])
            sign_conflicts.append(
                (left > sign_tolerance and right < -sign_tolerance)
                or (left < -sign_tolerance and right > sign_tolerance)
            )
            neighbor_distances.append(float(distances[other]))

    return AliasingMetrics(
        row_count=row_count,
        feature_count=feature_count,
        pair_count=len(squared_differences),
        coverage=covered / row_count,
        conditional_variance=(
            float(np.mean(squared_differences)) if squared_differences else None
        ),
        sign_disagreement_rate=(
            float(np.mean(sign_conflicts)) if sign_conflicts else None
        ),
        mean_neighbor_distance=(
            float(np.mean(neighbor_distances)) if neighbor_distances else None
        ),
        distance_threshold=float(max_standardized_distance),
    )

def compare_state_aliasing(
    legacy_features: Any,
    augmented_features: Any,
    outcomes: Any,
    *,
    neighbor_count: int = 1,
    max_standardized_distance: float = 0.35,
) -> dict[str, Any]:
    """Compare the frozen 29D representation with local temporal features."""

    legacy = _matrix(legacy_features, name="LEGACY_FEATURES")
    augmented = _matrix(augmented_features, name="AUGMENTED_FEATURES")
    if legacy.shape[0] != augmented.shape[0]:
        raise ValueError("ALIASING_ROW_COUNT_MISMATCH")
    if augmented.shape[1] <= legacy.shape[1]:
        raise ValueError("AUGMENTED_FEATURES_MUST_ADD_INFORMATION")
    target = _targets(outcomes, legacy.shape[0])
    old = nearest_neighbor_aliasing(
        legacy,
        target,
        neighbor_count=neighbor_count,
        max_standardized_distance=max_standardized_distance,
    )
    new = nearest_neighbor_aliasing(
        augmented,
        target,
        neighbor_count=neighbor_count,
        max_standardized_distance=max_standardized_distance,
    )

    def reduction(left: float | None, right: float | None) -> float | None:
        return None if left is None or right is None else float(left - right)

    return {
        "schema": "czr005.g4irsf17.state_aliasing_audit.v1",
        "legacy": old.to_dict(),
        "augmented": new.to_dict(),
        "improvement": {
            "conditional_variance_reduction": reduction(
                old.conditional_variance, new.conditional_variance
            ),
            "sign_disagreement_reduction": reduction(
                old.sign_disagreement_rate, new.sign_disagreement_rate
            ),
            "coverage_delta": new.coverage - old.coverage,
        },
    }


def _row_value(row: Mapping[str, Any], name: str) -> Any:
    if name in row:
        return row[name]
    nested = row.get("features")
    if isinstance(nested, Mapping) and name in nested:
        return nested[name]
    raise KeyError(name)


def _rows_matrix(rows: Sequence[Mapping[str, Any]], names: Sequence[str]) -> np.ndarray:
    assert_strictly_local_feature_names(names)
    return np.asarray(
        [[_row_value(row, name) for name in names] for row in rows],
        dtype=np.float64,
    )


def run_state_aliasing_audit(
    rows: Sequence[Mapping[str, Any]],
    *,
    legacy_feature_names: Sequence[str] = LEGACY_29_FEATURES,
    augmented_feature_names: Sequence[str] = AUGMENTED_WITH_LEGACY_FEATURES,
    outcome_key: str = "system_utility",
    neighbor_count: int = 1,
    max_standardized_distance: float = 0.35,
) -> dict[str, Any]:
    """Row-oriented campaign hook for the Phase-C aliasing audit."""

    if not rows:
        raise ValueError("ALIASING_ROWS_EMPTY")
    legacy_names = tuple(legacy_feature_names)
    augmented_names = tuple(augmented_feature_names)
    if not set(legacy_names).issubset(augmented_names):
        raise ValueError("AUGMENTED_SCHEMA_MUST_CONTAIN_LEGACY_SCHEMA")
    legacy = _rows_matrix(rows, legacy_names)
    augmented = _rows_matrix(rows, augmented_names)
    outcomes = np.asarray([_row_value(row, outcome_key) for row in rows], dtype=np.float64)
    result = compare_state_aliasing(
        legacy,
        augmented,
        outcomes,
        neighbor_count=neighbor_count,
        max_standardized_distance=max_standardized_distance,
    )
    result["feature_names"] = {
        "legacy": list(legacy_names),
        "augmented": list(augmented_names),
    }
    result["outcome"] = outcome_key
    return result


def feature_group_ablation(
    features: Any,
    outcomes: Any,
    feature_names: Sequence[str],
    feature_groups: Mapping[str, Sequence[str]],
    *,
    neighbor_count: int = 1,
    max_standardized_distance: float = 0.35,
) -> list[dict[str, Any]]:
    """Drop each named group and report the resulting aliasing degradation."""

    matrix = _matrix(features, name="FEATURES")
    names = tuple(feature_names)
    if matrix.shape[1] != len(names):
        raise ValueError("FEATURE_NAME_DIMENSION_MISMATCH")
    assert_strictly_local_feature_names(names)
    full = nearest_neighbor_aliasing(
        matrix,
        outcomes,
        neighbor_count=neighbor_count,
        max_standardized_distance=max_standardized_distance,
    )
    output: list[dict[str, Any]] = []
    for group_name, group_features in feature_groups.items():
        unknown = set(group_features) - set(names)
        if unknown:
            raise ValueError(f"ABLATION_UNKNOWN_FEATURE:{group_name}:{sorted(unknown)}")
        keep = [index for index, name in enumerate(names) if name not in group_features]
        if not keep:
            raise ValueError(f"ABLATION_REMOVES_ALL_FEATURES:{group_name}")
        dropped = nearest_neighbor_aliasing(
            matrix[:, keep],
            outcomes,
            neighbor_count=neighbor_count,
            max_standardized_distance=max_standardized_distance,
        )

        def delta(value: float | None, baseline: float | None) -> float | None:
            return None if value is None or baseline is None else float(value - baseline)

        output.append(
            {
                "schema": "czr005.g4irsf17.feature_ablation.v1",
                "ablated_group": str(group_name),
                "removed_features": list(group_features),
                "remaining_feature_count": len(keep),
                **dropped.to_dict(),
                "conditional_variance_delta_vs_full": delta(
                    dropped.conditional_variance, full.conditional_variance
                ),
                "sign_disagreement_delta_vs_full": delta(
                    dropped.sign_disagreement_rate, full.sign_disagreement_rate
                ),
                "coverage_delta_vs_full": dropped.coverage - full.coverage,
            }
        )
    return output


def feature_ablation(
    rows: Sequence[Mapping[str, Any]],
    *,
    outcome_key: str = "system_utility",
    feature_names: Sequence[str] = AUGMENTED_WITH_LEGACY_FEATURES,
    feature_groups: Mapping[str, Sequence[str]] | None = None,
    neighbor_count: int = 1,
    max_standardized_distance: float = 0.35,
) -> list[dict[str, Any]]:
    """Row-oriented Phase-C ablation hook."""

    names = tuple(feature_names)
    if feature_groups is None:
        temporal = tuple(
            name
            for name in CANONICAL_OBSERVATION_FEATURES
            if "_10s" in name or "_30s" in name or "_60s" in name
        )
        feature_groups = {
            "source_front_candidate": tuple(
                name for name in CANONICAL_OBSERVATION_FEATURES if name.startswith("candidate_")
            ),
            "bounded_temporal": temporal,
            "downstream_pressure": tuple(
                name
                for name in CANONICAL_OBSERVATION_FEATURES
                if name.startswith("target_") or "pressure" in name or "drain_slope" in name
            ),
            "merge": tuple(
                name
                for name in CANONICAL_OBSERVATION_FEATURES
                if name.startswith("merge_") or name.startswith("incoming_grant_")
                or name.startswith("recent_incoming_")
                or name.startswith("time_to_next_service_")
            ),
        }
    matrix = _rows_matrix(rows, names)
    outcomes = np.asarray([_row_value(row, outcome_key) for row in rows], dtype=np.float64)
    return feature_group_ablation(
        matrix,
        outcomes,
        names,
        feature_groups,
        neighbor_count=neighbor_count,
        max_standardized_distance=max_standardized_distance,
    )
