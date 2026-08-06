"""Strictly local, ID-free observations for G4IRSF17 source arbitration.

The schema is intentionally expressed in terms of a candidate, the other
bounded candidates at the same source front, and one/two-hop summaries that a
runtime source controller can already observe.  Split keys and scientific
labels never enter the feature vector.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ..g4irsf16.model import DEPLOYMENT_FEATURES as LEGACY_29_FEATURES


@dataclass(frozen=True)
class FeatureSpec:
    """One deployable numeric feature and its runtime clipping contract."""

    name: str
    lower: float
    upper: float
    role: str


# Candidate values are either candidate-relative already or become relative
# when :func:`pairwise_feature_vector` subtracts the right candidate.  A local
# rank of zero is the current source-front winner.  K is frozen to 2 or 4.
CANDIDATE_FEATURE_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec("candidate_local_rank", 0.0, 3.0, "candidate"),
    FeatureSpec(
        "candidate_deadline_slack_seconds", -86_400.0, 86_400.0, "candidate"
    ),
    FeatureSpec("candidate_wait_age_seconds", 0.0, 86_400.0, "candidate"),
    FeatureSpec("candidate_leg_priority", -2.0, 2.0, "candidate"),
    FeatureSpec("candidate_repair_priority", 0.0, 1.0, "candidate"),
    FeatureSpec(
        "deadline_slack_delta_to_baseline_seconds",
        -86_400.0,
        86_400.0,
        "candidate_relative",
    ),
    FeatureSpec(
        "wait_age_delta_to_baseline_seconds",
        -86_400.0,
        86_400.0,
        "candidate_relative",
    ),
    FeatureSpec(
        "leg_priority_delta_to_baseline", -4.0, 4.0, "candidate_relative"
    ),
    FeatureSpec(
        "urgency_delta_to_granted_seconds",
        -86_400.0,
        86_400.0,
        "candidate_relative",
    ),
    FeatureSpec(
        "wait_delta_to_granted_seconds",
        -86_400.0,
        86_400.0,
        "candidate_relative",
    ),
)


# These values are shared local context.  Generation values are represented as
# bounded deltas, never as absolute counters that could become a time/source
# codebook.  Pressure summaries have a two-hop maximum and require a runtime
# TTL; neither is a reservation-table scan.
CONTEXT_FEATURE_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec("source_queue_length", 0.0, 4_096.0, "source_context"),
    FeatureSpec("source_queue_capacity", 1.0, 4_096.0, "source_context"),
    FeatureSpec("source_queue_utilization", 0.0, 1.0, "source_context"),
    FeatureSpec(
        "source_queue_generation_delta", 0.0, 4_096.0, "source_context"
    ),
    FeatureSpec("release_count_10s", 0.0, 4_096.0, "source_temporal"),
    FeatureSpec("release_count_30s", 0.0, 4_096.0, "source_temporal"),
    FeatureSpec("release_count_60s", 0.0, 4_096.0, "source_temporal"),
    FeatureSpec("admission_count_10s", 0.0, 4_096.0, "source_temporal"),
    FeatureSpec("admission_count_30s", 0.0, 4_096.0, "source_temporal"),
    FeatureSpec("admission_count_60s", 0.0, 4_096.0, "source_temporal"),
    FeatureSpec("queue_slope_10s", -4_096.0, 4_096.0, "source_temporal"),
    FeatureSpec("queue_slope_30s", -4_096.0, 4_096.0, "source_temporal"),
    FeatureSpec("queue_slope_60s", -4_096.0, 4_096.0, "source_temporal"),
    FeatureSpec(
        "first_edge_credit_slack_seconds", -3_600.0, 3_600.0, "source_context"
    ),
    FeatureSpec("target_queue_length", 0.0, 4_096.0, "downstream_context"),
    FeatureSpec("target_queue_capacity", 1.0, 4_096.0, "downstream_context"),
    FeatureSpec("target_queue_utilization", 0.0, 1.0, "downstream_context"),
    FeatureSpec(
        "target_scheduled_incoming", 0.0, 4_096.0, "downstream_context"
    ),
    FeatureSpec(
        "estimated_service_rate_60s", 0.0, 4_096.0, "downstream_context"
    ),
    FeatureSpec("drain_slope_60s", -4_096.0, 4_096.0, "downstream_context"),
    FeatureSpec(
        "service_weighted_pressure", 0.0, 1_000_000.0, "downstream_context"
    ),
    FeatureSpec("one_hop_ttl_pressure", 0.0, 1_000_000.0, "downstream_context"),
    FeatureSpec("two_hop_ttl_pressure", 0.0, 1_000_000.0, "downstream_context"),
    FeatureSpec("merge_pending_count", 0.0, 4_096.0, "merge_context"),
    FeatureSpec(
        "merge_oldest_request_age_seconds", 0.0, 86_400.0, "merge_context"
    ),
    FeatureSpec(
        "merge_token_generation_delta", 0.0, 4_096.0, "merge_context"
    ),
    FeatureSpec(
        "time_to_next_service_opportunity_seconds",
        0.0,
        3_600.0,
        "merge_context",
    ),
    FeatureSpec("recent_incoming_grants_60s", 0.0, 4_096.0, "merge_context"),
    FeatureSpec(
        "incoming_grant_imbalance_60s", -4_096.0, 4_096.0, "merge_context"
    ),
)

CANDIDATE_FEATURES: tuple[str, ...] = tuple(
    spec.name for spec in CANDIDATE_FEATURE_SPECS
)
CONTEXT_FEATURES: tuple[str, ...] = tuple(spec.name for spec in CONTEXT_FEATURE_SPECS)
CANONICAL_OBSERVATION_FEATURES: tuple[str, ...] = CANDIDATE_FEATURES + CONTEXT_FEATURES
AUGMENTED_WITH_LEGACY_FEATURES: tuple[str, ...] = (
    tuple(LEGACY_29_FEATURES) + CANONICAL_OBSERVATION_FEATURES
)
PAIRWISE_FEATURES: tuple[str, ...] = (
    tuple(f"delta_{name}" for name in CANDIDATE_FEATURES) + CONTEXT_FEATURES
)

_SPECS = {
    spec.name: spec for spec in (*CANDIDATE_FEATURE_SPECS, *CONTEXT_FEATURE_SPECS)
}

# Precise leak markers are used instead of a broad ban on words such as
# ``node``: a local node *type* is valid, while an absolute node ID is not.
FORBIDDEN_FEATURE_MARKERS: tuple[str, ...] = (
    "task_id",
    "bag_id",
    "node_id",
    "source_id",
    "goal_id",
    "segment_id",
    "future_",
    "global_",
    "reservation_table",
    "completion_outcome",
    "realized_utility",
    "teacher_label",
)


class LocalFeatureError(ValueError):
    """Raised when an observation violates the local feature contract."""


def assert_strictly_local_feature_names(feature_names: Sequence[str]) -> None:
    """Reject identity, future-outcome, and global-state model inputs."""

    duplicates = len(set(feature_names)) != len(feature_names)
    if duplicates:
        raise LocalFeatureError("DUPLICATE_FEATURE_NAME")
    for raw_name in feature_names:
        name = str(raw_name).lower()
        if name.endswith("_id") or any(marker in name for marker in FORBIDDEN_FEATURE_MARKERS):
            raise LocalFeatureError(f"NONLOCAL_OR_ID_FEATURE:{raw_name}")


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise LocalFeatureError(f"FEATURE_NOT_NUMERIC:{name}")
    number = float(value)
    if not math.isfinite(number):
        raise LocalFeatureError(f"FEATURE_NOT_FINITE:{name}")
    return number


def _project_exact(
    values: Mapping[str, Any],
    names: Sequence[str],
    *,
    clip: bool,
) -> dict[str, float]:
    missing = [name for name in names if name not in values]
    extra = [name for name in values if name not in names]
    if missing:
        raise LocalFeatureError("FEATURES_MISSING:" + ",".join(missing))
    if extra:
        raise LocalFeatureError("FEATURES_EXTRA:" + ",".join(extra))
    result: dict[str, float] = {}
    for name in names:
        number = _finite_number(values[name], name)
        spec = _SPECS[name]
        if clip:
            number = min(max(number, spec.lower), spec.upper)
        elif number < spec.lower or number > spec.upper:
            raise LocalFeatureError(f"FEATURE_OUT_OF_BOUNDS:{name}")
        result[name] = number
    return result


def canonical_source_front_observation(
    candidate: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    clip: bool = False,
) -> dict[str, float]:
    """Return the exact ordered source-front observation.

    ``clip=True`` is intended for a runtime telemetry adapter whose physical
    counters may saturate.  Offline training should normally keep the default
    and surface an invalid row instead of silently changing it.
    """

    assert_strictly_local_feature_names(CANONICAL_OBSERVATION_FEATURES)
    return {
        **_project_exact(candidate, CANDIDATE_FEATURES, clip=clip),
        **_project_exact(context, CONTEXT_FEATURES, clip=clip),
    }


def canonical_feature_vector(observation: Mapping[str, Any]) -> np.ndarray:
    """Validate and vectorize an already combined canonical observation."""

    missing = [name for name in CANONICAL_OBSERVATION_FEATURES if name not in observation]
    extra = [name for name in observation if name not in CANONICAL_OBSERVATION_FEATURES]
    if missing:
        raise LocalFeatureError("FEATURES_MISSING:" + ",".join(missing))
    if extra:
        raise LocalFeatureError("FEATURES_EXTRA:" + ",".join(extra))
    candidate = {name: observation[name] for name in CANDIDATE_FEATURES}
    context = {name: observation[name] for name in CONTEXT_FEATURES}
    projected = canonical_source_front_observation(candidate, context)
    return np.asarray(
        [projected[name] for name in CANONICAL_OBSERVATION_FEATURES], dtype=np.float64
    )


def pairwise_feature_vector(
    left_candidate: Mapping[str, Any],
    right_candidate: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    clip: bool = False,
) -> np.ndarray:
    """Build ``left - right`` candidate deltas plus shared local context."""

    left = _project_exact(left_candidate, CANDIDATE_FEATURES, clip=clip)
    right = _project_exact(right_candidate, CANDIDATE_FEATURES, clip=clip)
    shared = _project_exact(context, CONTEXT_FEATURES, clip=clip)
    values = [left[name] - right[name] for name in CANDIDATE_FEATURES]
    values.extend(shared[name] for name in CONTEXT_FEATURES)
    return np.asarray(values, dtype=np.float64)


assert_strictly_local_feature_names(tuple(LEGACY_29_FEATURES))
assert_strictly_local_feature_names(CANONICAL_OBSERVATION_FEATURES)
assert_strictly_local_feature_names(PAIRWISE_FEATURES)
