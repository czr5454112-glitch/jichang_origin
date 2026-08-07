"""Strictly local candidate-action features for G4IRSF18.

``RICH_LOCAL_V1`` deliberately extends the deployed G17 39-dimensional
source-front observation instead of inventing a second definition of those
counters.  The same candidate contract is used at source, route, and merge
decision heads; the head is typed metadata and is not an identity feature.

The historical F2/G4E 22-dimensional input is kept as an honest ablation
reference.  It contains map-coded inputs and training-only historical risk,
so this module explicitly quarantines it from new standalone deployment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np

from ..g4irsf16.model import DEPLOYMENT_FEATURES as LEGACY_29_FEATURES
from ..g4irsf17.features import (
    CANONICAL_OBSERVATION_FEATURES as G17_LOCAL_39_FEATURES,
    CANDIDATE_FEATURES as G17_CANDIDATE_FEATURES,
    CONTEXT_FEATURES as G17_CONTEXT_FEATURES,
    FeatureSpec,
    LocalFeatureError,
    assert_strictly_local_feature_names as assert_g17_local_feature_names,
    canonical_source_front_observation,
)


class DecisionHead(str, Enum):
    """Normal-flow interface at which a bounded local action is selected."""

    SOURCE = "source"
    ROUTE = "route"
    MERGE = "merge"


class FeatureAblationGroup(str, Enum):
    """Frozen names used in G18 input-value experiments."""

    F2_OLD_22 = "F2_OLD_22"
    G17_LOCAL_39 = "G17_LOCAL_39"
    RICH_LOCAL_V1 = "RICH_LOCAL_V1"
    LEGACY_PLUS_RICH = "LEGACY_PLUS_RICH"


# Exact feature order audited by the frozen G4E adapter.  Two map-coded
# fields and one training-only risk field make this unsuitable as a new
# portable standalone controller.  Preserving those facts is more honest than
# silently renaming it into a different baseline.
F2_OLD_22_FEATURES: tuple[str, ...] = (
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


# Twenty-one additions make the candidate-action contract exactly 60D.  The
# G17 block already contains deadline/wait/repair, 10/30/60s source flow,
# first-edge credit, downstream queue/service/pressure, and merge competition.
RICH_LOCAL_V1_ADDITIONAL_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec("current_interface_queue_length", 0.0, 4_096.0, "interface"),
    FeatureSpec("current_interface_queue_capacity", 1.0, 4_096.0, "interface"),
    FeatureSpec("current_interface_queue_utilization", 0.0, 1.0, "interface"),
    FeatureSpec("current_interface_service_rate_60s", 0.0, 4_096.0, "interface"),
    FeatureSpec("legal_action_count", 1.0, 64.0, "interface"),
    FeatureSpec("candidate_travel_time_seconds", 0.0, 3_600.0, "action"),
    FeatureSpec("candidate_service_time_seconds", 0.0, 3_600.0, "action"),
    FeatureSpec("candidate_static_remaining_time_seconds", 0.0, 86_400.0, "action"),
    FeatureSpec("candidate_static_remaining_hops", 0.0, 4_096.0, "action"),
    FeatureSpec("candidate_static_second_best_gap_seconds", 0.0, 86_400.0, "action"),
    FeatureSpec("candidate_bottleneck_score", 0.0, 1_000_000.0, "action"),
    FeatureSpec("candidate_goal_direction_score", -1.0, 1.0, "action"),
    FeatureSpec("candidate_is_goal", 0.0, 1.0, "action_history"),
    FeatureSpec("candidate_is_reverse_edge", 0.0, 1.0, "action_history"),
    FeatureSpec("candidate_recent_visit_count", 0.0, 64.0, "action_history"),
    FeatureSpec("candidate_short_history_repeat_count", 0.0, 64.0, "action_history"),
    FeatureSpec("candidate_segment_reroute_count", 0.0, 64.0, "action_history"),
    FeatureSpec("candidate_segment_wait_count", 0.0, 1_024.0, "action_history"),
    FeatureSpec("candidate_segment_override_count", 0.0, 64.0, "action_history"),
    FeatureSpec("candidate_consecutive_hold_count", 0.0, 64.0, "action_history"),
    FeatureSpec(
        "candidate_advertised_fault",
        0.0,
        1.0,
        "non_authoritative_announcement",
    ),
)

RICH_LOCAL_V1_ADDITIONAL_FEATURES: tuple[str, ...] = tuple(
    spec.name for spec in RICH_LOCAL_V1_ADDITIONAL_SPECS
)
RICH_LOCAL_V1_FEATURES: tuple[str, ...] = (
    tuple(G17_LOCAL_39_FEATURES) + RICH_LOCAL_V1_ADDITIONAL_FEATURES
)

# Prefixing keeps the 29D predecessor values distinguishable from same-named
# rich fields such as target_queue_length.  This group is diagnostic only.
LEGACY_PLUS_RICH_FEATURES: tuple[str, ...] = (
    tuple(f"legacy_{name}" for name in LEGACY_29_FEATURES)
    + RICH_LOCAL_V1_FEATURES
)


@dataclass(frozen=True)
class FeatureGroupContract:
    group: FeatureAblationGroup
    feature_names: tuple[str, ...]
    strictly_local: bool
    runtime_deployable: bool
    ablation_only: bool
    provenance: str

    @property
    def dimension(self) -> int:
        return len(self.feature_names)


FEATURE_GROUP_CONTRACTS: Mapping[FeatureAblationGroup, FeatureGroupContract] = {
    FeatureAblationGroup.F2_OLD_22: FeatureGroupContract(
        FeatureAblationGroup.F2_OLD_22,
        F2_OLD_22_FEATURES,
        strictly_local=False,
        runtime_deployable=False,
        ablation_only=True,
        provenance="frozen G4E/F2 comparator; contains map codes and training-only risk",
    ),
    FeatureAblationGroup.G17_LOCAL_39: FeatureGroupContract(
        FeatureAblationGroup.G17_LOCAL_39,
        tuple(G17_LOCAL_39_FEATURES),
        strictly_local=True,
        runtime_deployable=True,
        ablation_only=False,
        provenance="exact G17 canonical local observation",
    ),
    FeatureAblationGroup.RICH_LOCAL_V1: FeatureGroupContract(
        FeatureAblationGroup.RICH_LOCAL_V1,
        RICH_LOCAL_V1_FEATURES,
        strictly_local=True,
        runtime_deployable=True,
        ablation_only=False,
        provenance="G17 39D plus bounded candidate edge/history features",
    ),
    FeatureAblationGroup.LEGACY_PLUS_RICH: FeatureGroupContract(
        FeatureAblationGroup.LEGACY_PLUS_RICH,
        LEGACY_PLUS_RICH_FEATURES,
        strictly_local=True,
        runtime_deployable=False,
        ablation_only=True,
        provenance="G16 29D plus RICH_LOCAL_V1; input-value diagnostic only",
    ),
}


_ABSOLUTE_OR_TRAINING_CODED_FEATURES = frozenset(
    {
        "current_node_scaled",
        "goal_node_scaled",
        "candidate_historical_risk_from_training_only_scaled",
    }
)
_ADDITIONAL_SPEC_BY_NAME = {
    spec.name: spec for spec in RICH_LOCAL_V1_ADDITIONAL_SPECS
}

# This is a construction audit, not a second feature schema.  Every source is
# available at the native decision boundary from bounded local state, static
# precompute, or the already-existing G17 observation.  In particular,
# physical availability is not a model feature: advertised_fault is a stale-
# tolerant one-hop announcement and the shield remains authoritative.
RICH_LOCAL_V1_NATIVE_PROVENANCE: Mapping[str, str] = {
    **{
        name: "G4IRSF17SourceCandidateObservation/G4IRSF17SourceContextObservation"
        for name in G17_LOCAL_39_FEATURES
    },
    "current_interface_queue_length": "JunctionState local source/route/merge queue",
    "current_interface_queue_capacity": "EventRuntimeConfig.local_queue_capacity",
    "current_interface_queue_utilization": "local queue length / configured capacity",
    "current_interface_service_rate_60s": "bounded local service-completion counter",
    "legal_action_count": "bounded legal candidate set including optional WAIT",
    "candidate_travel_time_seconds": "EventCandidateRecord.travel_time",
    "candidate_service_time_seconds": "native service_duration(candidate)",
    "candidate_static_remaining_time_seconds": "EventCandidateRecord.static_potential",
    "candidate_static_remaining_hops": "static topology precompute; no runtime scan",
    "candidate_static_second_best_gap_seconds": "bounded candidate static costs",
    "candidate_bottleneck_score": "local/static candidate bottleneck computation",
    "candidate_goal_direction_score": "current minus candidate static potential",
    "candidate_is_goal": "candidate/goal equality reduced to a boolean",
    "candidate_is_reverse_edge": "bounded BagState.history suffix",
    "candidate_recent_visit_count": "EventCandidateRecord.recent_visit_count",
    "candidate_short_history_repeat_count": "bounded EventDecisionTraceRow.short_history",
    "candidate_segment_reroute_count": "local per-segment loop/reroute counter",
    "candidate_segment_wait_count": "local per-segment retry/hold counter",
    "candidate_segment_override_count": "local supervisor latch override counter",
    "candidate_consecutive_hold_count": "local controller consecutive-hold counter",
    "candidate_advertised_fault": "EventCandidateRecord.advertised_fault one-hop beacon",
}


def assert_deployable_g18_feature_names(feature_names: Sequence[str]) -> None:
    """Reject identity, future/outcome, teacher, and training-coded inputs."""

    names = tuple(str(name) for name in feature_names)
    assert_g17_local_feature_names(names)
    for name in names:
        lowered = name.lower()
        if lowered in _ABSOLUTE_OR_TRAINING_CODED_FEATURES:
            raise LocalFeatureError(f"NONLOCAL_OR_ID_FEATURE:{name}")
        if "outcome" in lowered or "teacher" in lowered or "full_map" in lowered:
            raise LocalFeatureError(f"NONLOCAL_OR_ID_FEATURE:{name}")


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise LocalFeatureError(f"FEATURE_NOT_NUMERIC:{name}")
    number = float(value)
    if not math.isfinite(number):
        raise LocalFeatureError(f"FEATURE_NOT_FINITE:{name}")
    return number


def _exact_numeric_projection(
    values: Mapping[str, Any],
    names: Sequence[str],
    *,
    specs: Mapping[str, FeatureSpec] | None = None,
    clip: bool = False,
) -> tuple[float, ...]:
    missing = [name for name in names if name not in values]
    extra = [name for name in values if name not in names]
    if missing:
        raise LocalFeatureError("FEATURES_MISSING:" + ",".join(missing))
    if extra:
        raise LocalFeatureError("FEATURES_EXTRA:" + ",".join(extra))
    result: list[float] = []
    for name in names:
        number = _finite_number(values[name], name)
        if specs is not None:
            spec = specs[name]
            if clip:
                number = min(max(number, spec.lower), spec.upper)
            elif number < spec.lower or number > spec.upper:
                raise LocalFeatureError(f"FEATURE_OUT_OF_BOUNDS:{name}")
        result.append(number)
    return tuple(result)


@dataclass(frozen=True)
class CandidateActionObservation:
    """One ID-free candidate at one typed local interface."""

    head: DecisionHead
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.head, DecisionHead):
            raise LocalFeatureError("UNKNOWN_DECISION_HEAD")
        if len(self.values) != len(RICH_LOCAL_V1_FEATURES):
            raise LocalFeatureError("RICH_LOCAL_V1_DIMENSION_MISMATCH")
        if any(not math.isfinite(float(value)) for value in self.values):
            raise LocalFeatureError("RICH_LOCAL_V1_VALUE_NOT_FINITE")

    def as_mapping(self) -> dict[str, float]:
        return dict(zip(RICH_LOCAL_V1_FEATURES, self.values, strict=True))

    def vector(self, group: FeatureAblationGroup | str = FeatureAblationGroup.RICH_LOCAL_V1) -> np.ndarray:
        resolved = FeatureAblationGroup(group)
        if resolved is FeatureAblationGroup.G17_LOCAL_39:
            values = self.values[: len(G17_LOCAL_39_FEATURES)]
        elif resolved is FeatureAblationGroup.RICH_LOCAL_V1:
            values = self.values
        else:
            raise LocalFeatureError(f"ABLATION_REQUIRES_EXTERNAL_FEATURES:{resolved.value}")
        return np.asarray(values, dtype=np.float64)


def build_candidate_action_observation(
    head: DecisionHead | str,
    g17_candidate: Mapping[str, Any],
    g17_context: Mapping[str, Any],
    rich_action: Mapping[str, Any],
    *,
    clip: bool = False,
) -> CandidateActionObservation:
    """Build the exact 60D source/route/merge candidate-action observation."""

    try:
        resolved_head = DecisionHead(head)
    except (TypeError, ValueError) as exc:
        raise LocalFeatureError(f"UNKNOWN_DECISION_HEAD:{head}") from exc
    base = canonical_source_front_observation(
        g17_candidate,
        g17_context,
        clip=clip,
    )
    additional = _exact_numeric_projection(
        rich_action,
        RICH_LOCAL_V1_ADDITIONAL_FEATURES,
        specs=_ADDITIONAL_SPEC_BY_NAME,
        clip=clip,
    )
    values = tuple(base[name] for name in G17_LOCAL_39_FEATURES) + additional
    return CandidateActionObservation(resolved_head, values)


def ablation_feature_vector(
    group: FeatureAblationGroup | str,
    observation: CandidateActionObservation,
    *,
    f2_old_22: Mapping[str, Any] | None = None,
    legacy_29: Mapping[str, Any] | None = None,
) -> np.ndarray:
    """Project one candidate into a frozen G18 input-ablation group.

    Historical feature blocks are supplied explicitly, which prevents labels,
    split keys, or other fields from hitchhiking in a scientific row.
    """

    resolved = FeatureAblationGroup(group)
    if resolved in {
        FeatureAblationGroup.G17_LOCAL_39,
        FeatureAblationGroup.RICH_LOCAL_V1,
    }:
        return observation.vector(resolved)
    if resolved is FeatureAblationGroup.F2_OLD_22:
        if f2_old_22 is None:
            raise LocalFeatureError("F2_OLD_22_FEATURES_REQUIRED")
        return np.asarray(
            _exact_numeric_projection(f2_old_22, F2_OLD_22_FEATURES),
            dtype=np.float64,
        )
    if legacy_29 is None:
        raise LocalFeatureError("LEGACY_29_FEATURES_REQUIRED")
    legacy = _exact_numeric_projection(legacy_29, LEGACY_29_FEATURES)
    return np.asarray(legacy + observation.values, dtype=np.float64)


def feature_group_contract(
    group: FeatureAblationGroup | str,
) -> FeatureGroupContract:
    return FEATURE_GROUP_CONTRACTS[FeatureAblationGroup(group)]


# Import-time assertions protect exported schemas from accidental leakage.
assert len(G17_LOCAL_39_FEATURES) == 39
assert len(F2_OLD_22_FEATURES) == 22
assert len(RICH_LOCAL_V1_FEATURES) == 60
assert len(LEGACY_PLUS_RICH_FEATURES) == 89
assert set(RICH_LOCAL_V1_NATIVE_PROVENANCE) == set(RICH_LOCAL_V1_FEATURES)
assert_deployable_g18_feature_names(G17_LOCAL_39_FEATURES)
assert_deployable_g18_feature_names(RICH_LOCAL_V1_FEATURES)
assert_deployable_g18_feature_names(LEGACY_PLUS_RICH_FEATURES)


__all__ = [
    "CandidateActionObservation",
    "DecisionHead",
    "F2_OLD_22_FEATURES",
    "FEATURE_GROUP_CONTRACTS",
    "FeatureAblationGroup",
    "FeatureGroupContract",
    "G17_CANDIDATE_FEATURES",
    "G17_CONTEXT_FEATURES",
    "G17_LOCAL_39_FEATURES",
    "LEGACY_29_FEATURES",
    "LEGACY_PLUS_RICH_FEATURES",
    "LocalFeatureError",
    "RICH_LOCAL_V1_ADDITIONAL_FEATURES",
    "RICH_LOCAL_V1_ADDITIONAL_SPECS",
    "RICH_LOCAL_V1_FEATURES",
    "RICH_LOCAL_V1_NATIVE_PROVENANCE",
    "ablation_feature_vector",
    "assert_deployable_g18_feature_names",
    "build_candidate_action_observation",
    "feature_group_contract",
]
