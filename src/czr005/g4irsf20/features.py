"""Minimal, ID-free route features for G4IRSF20.

The original G20 plan describes a larger ``RICH_ROUTE_V2`` state.  This
module deliberately exposes only values that the existing native
``EventCandidateRecord`` and decision trace already publish.  Planned window
statistics and ETA histograms remain explicit exclusions until they have a
real native producer; they are never silently replaced with zeros.

All exported model vectors contain relative waits rather than absolute node
identities or absolute availability timestamps.  The authoritative legality
and fault shield remains outside the learned scorer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from ..g4irsf18.features import assert_deployable_g18_feature_names


class RouteFeatureError(ValueError):
    """Raised when a native candidate cannot be projected without guessing."""


class RouteFeatureGroup(str, Enum):
    """Frozen G20 input-ablation names from the execution plan."""

    F0 = "F0"
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"
    F5 = "F5"


# Output names are ID-free and ordered.  F0 exactly reconstructs the terms
# available to S4; absolute availability timestamps are converted to waits.
S4_CORE_FEATURES: tuple[str, ...] = (
    "target_queue_length",
    "target_scheduled_incoming",
    "corridor_wait_seconds",
    "target_wait_after_travel_seconds",
    "edge_travel_time_seconds",
    "static_potential_seconds",
)

URGENCY_HISTORY_FEATURES: tuple[str, ...] = (
    "deadline_slack_seconds",
    "wait_age_seconds",
    "candidate_recent_visit_count",
)

CURRENT_LOCAL_FEATURES: tuple[str, ...] = (
    "current_queue_length",
    "current_next_service_wait_seconds",
    "priority_local_contention",
)

DOWNSTREAM_FEATURES: tuple[str, ...] = (
    "current_goal_queue_length",
    "target_goal_queue_length",
    "target_goal_scheduled_incoming",
    "current_goal_max_wait_seconds",
    "goal_conditioned_differential",
    "candidate_estimated_service_rate",
    "candidate_service_weighted_pressure",
)

LOCAL_FAULT_BEACON_FEATURES: tuple[str, ...] = (
    "candidate_advertised_fault",
    "candidate_fault_message_age_seconds",
)

TWO_HOP_FEATURES: tuple[str, ...] = (
    "candidate_two_hop_queue_pressure",
)


# The plan defines F1 and F2 as separate ablations over S4, not a cumulative
# F0 -> F1 -> F2 chain.  F4 is the full currently-observable state, while F5
# removes only the real two-hop field.
F0_FEATURES = S4_CORE_FEATURES
F1_FEATURES = S4_CORE_FEATURES + URGENCY_HISTORY_FEATURES
F2_FEATURES = S4_CORE_FEATURES + CURRENT_LOCAL_FEATURES
F3_FEATURES = F2_FEATURES + DOWNSTREAM_FEATURES
F5_FEATURES = (
    S4_CORE_FEATURES
    + URGENCY_HISTORY_FEATURES
    + CURRENT_LOCAL_FEATURES
    + DOWNSTREAM_FEATURES
    + LOCAL_FAULT_BEACON_FEATURES
)
F4_FEATURES = F5_FEATURES + TWO_HOP_FEATURES
RICH_ROUTE_V2_FEATURES = F4_FEATURES


# This flat mapping is the sole accepted projection boundary.  It contains
# only the native scalar values used by at least one group.  ``event_time`` is
# construction context and never enters the model vector directly.
NATIVE_ROUTE_CANDIDATE_FIELDS: tuple[str, ...] = (
    "event_time",
    "target_queue_length",
    "target_scheduled_incoming",
    "corridor_next_available",
    "target_next_available",
    "travel_time",
    "static_potential",
    "priority_slack_seconds",
    "priority_age_seconds",
    "recent_visit_count",
    "junction_queue_length",
    "junction_next_available_time",
    "priority_local_contention",
    "current_goal_queue_length",
    "target_goal_queue_length",
    "target_goal_scheduled_incoming",
    "current_goal_max_wait",
    "goal_conditioned_differential",
    "estimated_service_rate",
    "service_weighted_pressure",
    "advertised_fault",
    "fault_message_age_seconds",
    "two_hop_queue_pressure",
)


_FEATURE_NATIVE_SOURCES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "target_queue_length": ("target_queue_length",),
        "target_scheduled_incoming": ("target_scheduled_incoming",),
        "corridor_wait_seconds": ("event_time", "corridor_next_available"),
        "target_wait_after_travel_seconds": (
            "event_time",
            "travel_time",
            "target_next_available",
        ),
        "edge_travel_time_seconds": ("travel_time",),
        "static_potential_seconds": ("static_potential",),
        "deadline_slack_seconds": ("priority_slack_seconds",),
        "wait_age_seconds": ("priority_age_seconds",),
        "candidate_recent_visit_count": ("recent_visit_count",),
        "current_queue_length": ("junction_queue_length",),
        "current_next_service_wait_seconds": (
            "event_time",
            "junction_next_available_time",
        ),
        "priority_local_contention": ("priority_local_contention",),
        "current_goal_queue_length": ("current_goal_queue_length",),
        "target_goal_queue_length": ("target_goal_queue_length",),
        "target_goal_scheduled_incoming": (
            "target_goal_scheduled_incoming",
        ),
        "current_goal_max_wait_seconds": ("current_goal_max_wait",),
        "goal_conditioned_differential": ("goal_conditioned_differential",),
        "candidate_estimated_service_rate": ("estimated_service_rate",),
        "candidate_service_weighted_pressure": (
            "service_weighted_pressure",
        ),
        "candidate_advertised_fault": ("advertised_fault",),
        "candidate_fault_message_age_seconds": (
            "fault_message_age_seconds",
        ),
        "candidate_two_hop_queue_pressure": ("two_hop_queue_pressure",),
    }
)


def _native_sources(feature_names: Sequence[str]) -> tuple[str, ...]:
    selected = {
        source
        for feature_name in feature_names
        for source in _FEATURE_NATIVE_SOURCES[feature_name]
    }
    return tuple(name for name in NATIVE_ROUTE_CANDIDATE_FIELDS if name in selected)


@dataclass(frozen=True)
class RouteFeatureGroupContract:
    group: RouteFeatureGroup
    feature_names: tuple[str, ...]
    native_sources: tuple[str, ...]
    purpose: str
    includes_two_hop: bool = False

    @property
    def dimension(self) -> int:
        return len(self.feature_names)


RICH_ROUTE_V2: Mapping[RouteFeatureGroup, RouteFeatureGroupContract] = (
    MappingProxyType(
        {
            RouteFeatureGroup.F0: RouteFeatureGroupContract(
                RouteFeatureGroup.F0,
                F0_FEATURES,
                _native_sources(F0_FEATURES),
                "S4 core only",
            ),
            RouteFeatureGroup.F1: RouteFeatureGroupContract(
                RouteFeatureGroup.F1,
                F1_FEATURES,
                _native_sources(F1_FEATURES),
                "S4 plus currently-native urgency/history",
            ),
            RouteFeatureGroup.F2: RouteFeatureGroupContract(
                RouteFeatureGroup.F2,
                F2_FEATURES,
                _native_sources(F2_FEATURES),
                "S4 plus current owner state (window trends unavailable)",
            ),
            RouteFeatureGroup.F3: RouteFeatureGroupContract(
                RouteFeatureGroup.F3,
                F3_FEATURES,
                _native_sources(F3_FEATURES),
                "F2 plus currently-native downstream goal/pressure values",
            ),
            RouteFeatureGroup.F4: RouteFeatureGroupContract(
                RouteFeatureGroup.F4,
                F4_FEATURES,
                _native_sources(F4_FEATURES),
                "full currently-native RICH_ROUTE_V2",
                includes_two_hop=True,
            ),
            RouteFeatureGroup.F5: RouteFeatureGroupContract(
                RouteFeatureGroup.F5,
                F5_FEATURES,
                _native_sources(F5_FEATURES),
                "full currently-native state without two-hop pressure",
            ),
        }
    )
)
FEATURE_GROUP_CONTRACTS = RICH_ROUTE_V2
FEATURE_GROUP_DIMENSIONS: Mapping[RouteFeatureGroup, int] = MappingProxyType(
    {group: contract.dimension for group, contract in RICH_ROUTE_V2.items()}
)


# These planned fields have no direct producer in the current trace.  This is
# executable documentation: adding one to a model requires first adding and
# validating its native producer, then updating this list and the schema.
EXCLUDED_UNAVAILABLE_PLANNED_FEATURES: Mapping[str, tuple[str, ...]] = (
    MappingProxyType(
        {
            "urgency_history": (
                "direct_or_storage_leg",
                "reverse_edge_indicator",
                "segment_detour_count",
                "segment_wait_count",
                "segment_override_count",
            ),
            "current_owner_trend": (
                "queue_capacity",
                "queue_utilization",
                "arrivals_10s_30s_60s",
                "departures_10s_30s_60s",
                "queue_slope",
                "local_pending_count",
            ),
            "candidate_downstream": (
                "candidate_queue_utilization",
                "eta_bins_0s_5s_15s_30s_60s",
                "scheduled_incoming_slope",
                "recent_drain_rate",
                "pending_merge_oldest_age",
                "grant_imbalance",
                "capacity_block_rate",
            ),
            "two_hop_ttl": (
                "two_hop_pressure_min_mean_max",
                "two_hop_bottleneck",
                "two_hop_service_deficit",
                "two_hop_ttl_age",
                "two_hop_fault_generation",
            ),
            "static_progress": (
                "candidate_to_goal_hops",
                "second_best_static_gap",
                "candidate_out_degree",
                "candidate_node_type",
                "goal_reachability",
                "bottleneck_class",
            ),
        }
    )
)


# Values below do exist in the trace but are intentionally not model inputs.
EXCLUDED_AVAILABLE_NATIVE_FIELDS: Mapping[str, str] = MappingProxyType(
    {
        "decision/task/runtime/segment/current/goal/next node identifiers":
            "absolute identity leakage",
        "candidate model/scorer outputs": "prediction feedback leakage",
        "selected action and realized outcome": "label/outcome leakage",
        "priority_enqueue_sequence": "sequence identity surrogate",
        "short_history": "contains absolute node identifiers; only the native recent_visit_count is used",
        "local_snapshot.downstream_pressure": "candidate-set aggregate duplicates per-candidate pressure",
        "first_edge_credit_*": "source admission state is outside the Route learner",
        "shield_allowed/shield_reason": "authoritative legality remains outside the learned score",
    }
)


_FORBIDDEN_EXACT_NAMES = frozenset(
    {
        "task_id",
        "runtime_bag_id",
        "segment_id",
        "decision_id",
        "current_node",
        "goal_node",
        "next_node",
        "source_id",
        "selected_next",
        "model_prediction",
        "model_score",
        "scorer_raw_score",
        "candidate_next_nodes",
    }
)
_FORBIDDEN_FRAGMENTS = (
    "future",
    "outcome",
    "post_hoc",
    "global",
    "oracle",
    "teacher",
    "reservation",
    "realized",
)


def _assert_clean_input_names(names: Sequence[Any]) -> tuple[str, ...]:
    clean: list[str] = []
    for raw_name in names:
        if not isinstance(raw_name, str):
            raise RouteFeatureError("NATIVE_FEATURE_NAME_NOT_STRING")
        name = raw_name.lower()
        if (
            name in _FORBIDDEN_EXACT_NAMES
            or name.endswith("_id")
            or any(fragment in name for fragment in _FORBIDDEN_FRAGMENTS)
        ):
            raise RouteFeatureError(f"FORBIDDEN_FEATURE:{raw_name}")
        clean.append(raw_name)
    return tuple(clean)


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise RouteFeatureError(f"NATIVE_FEATURE_NOT_NUMERIC:{name}")
    number = float(value)
    if not math.isfinite(number):
        raise RouteFeatureError(f"NATIVE_FEATURE_NOT_FINITE:{name}")
    return number


def _boolean(value: Any, name: str) -> float:
    if not isinstance(value, (bool, np.bool_)):
        raise RouteFeatureError(f"NATIVE_FEATURE_NOT_BOOLEAN:{name}")
    return float(bool(value))


def _project_value(name: str, raw: Mapping[str, Any]) -> float:
    if name == "corridor_wait_seconds":
        return max(
            0.0,
            _finite_number(raw["corridor_next_available"], "corridor_next_available")
            - _finite_number(raw["event_time"], "event_time"),
        )
    if name == "target_wait_after_travel_seconds":
        return max(
            0.0,
            _finite_number(raw["target_next_available"], "target_next_available")
            - _finite_number(raw["event_time"], "event_time")
            - _finite_number(raw["travel_time"], "travel_time"),
        )
    if name == "current_next_service_wait_seconds":
        return max(
            0.0,
            _finite_number(
                raw["junction_next_available_time"],
                "junction_next_available_time",
            )
            - _finite_number(raw["event_time"], "event_time"),
        )
    if name == "candidate_advertised_fault":
        return _boolean(raw["advertised_fault"], "advertised_fault")

    direct_source = _FEATURE_NATIVE_SOURCES[name]
    if len(direct_source) != 1:
        raise AssertionError(f"UNHANDLED_DERIVED_FEATURE:{name}")
    return _finite_number(raw[direct_source[0]], direct_source[0])


def feature_group_contract(
    group: RouteFeatureGroup | str,
) -> RouteFeatureGroupContract:
    try:
        resolved = RouteFeatureGroup(group)
    except (TypeError, ValueError) as exc:
        raise RouteFeatureError(f"UNKNOWN_FEATURE_GROUP:{group}") from exc
    return RICH_ROUTE_V2[resolved]


def project_rich_route_v2(
    native_candidate: Mapping[str, Any],
    group: RouteFeatureGroup | str = RouteFeatureGroup.F4,
) -> np.ndarray:
    """Strictly project one flat native candidate mapping into a fixed group.

    Canonical-but-unused native fields are allowed so one mapping can serve all
    ablations.  Unknown fields are rejected, required fields are never filled,
    and only values used by the selected group must be finite.
    """

    if not isinstance(native_candidate, Mapping):
        raise RouteFeatureError("NATIVE_CANDIDATE_MUST_BE_MAPPING")
    names = _assert_clean_input_names(tuple(native_candidate.keys()))
    unknown = [name for name in names if name not in NATIVE_ROUTE_CANDIDATE_FIELDS]
    if unknown:
        raise RouteFeatureError("NATIVE_FEATURES_EXTRA:" + ",".join(unknown))
    contract = feature_group_contract(group)
    missing = [name for name in contract.native_sources if name not in native_candidate]
    if missing:
        raise RouteFeatureError("NATIVE_FEATURES_MISSING:" + ",".join(missing))
    return np.asarray(
        [_project_value(name, native_candidate) for name in contract.feature_names],
        dtype=np.float64,
    )


def project_rich_route_v2_mapping(
    native_candidate: Mapping[str, Any],
    group: RouteFeatureGroup | str = RouteFeatureGroup.F4,
) -> dict[str, float]:
    """Return the same strict projection with names attached for inspection."""

    contract = feature_group_contract(group)
    values = project_rich_route_v2(native_candidate, contract.group)
    return dict(zip(contract.feature_names, values.tolist(), strict=True))


def _nested_mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    if key not in parent:
        raise RouteFeatureError(f"NATIVE_TRACE_FIELD_MISSING:{key}")
    child = parent[key]
    if not isinstance(child, Mapping):
        raise RouteFeatureError(f"NATIVE_TRACE_FIELD_NOT_MAPPING:{key}")
    return child


def native_route_candidate_mapping(
    decision_row: Mapping[str, Any],
    candidate_row: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract the one approved flat mapping from current pybind trace rows.

    The extractor is an allow-list: identifiers, selected actions, model
    outputs, outcomes, and shield decisions in the surrounding trace cannot
    hitchhike into the returned mapping.
    """

    if not isinstance(decision_row, Mapping) or not isinstance(candidate_row, Mapping):
        raise RouteFeatureError("NATIVE_TRACE_ROWS_MUST_BE_MAPPINGS")
    metadata = _nested_mapping(decision_row, "metadata")
    local = _nested_mapping(decision_row, "local_snapshot")
    candidate = _nested_mapping(candidate_row, "features")

    source_by_name: Mapping[str, tuple[Mapping[str, Any], str, str]] = {
        "event_time": (decision_row, "event_time", "event_time"),
        "priority_slack_seconds": (
            metadata,
            "priority_slack_seconds",
            "metadata.priority_slack_seconds",
        ),
        "priority_age_seconds": (
            metadata,
            "priority_age_seconds",
            "metadata.priority_age_seconds",
        ),
        "priority_local_contention": (
            metadata,
            "priority_local_contention",
            "metadata.priority_local_contention",
        ),
        "junction_queue_length": (
            local,
            "junction_queue_length",
            "local_snapshot.junction_queue_length",
        ),
        "junction_next_available_time": (
            local,
            "next_available_time",
            "local_snapshot.next_available_time",
        ),
        **{
            name: (candidate, name, f"candidate.features.{name}")
            for name in NATIVE_ROUTE_CANDIDATE_FIELDS
            if name
            not in {
                "event_time",
                "priority_slack_seconds",
                "priority_age_seconds",
                "priority_local_contention",
                "junction_queue_length",
                "junction_next_available_time",
            }
        },
    }
    result: dict[str, Any] = {}
    for output_name in NATIVE_ROUTE_CANDIDATE_FIELDS:
        container, source_name, path = source_by_name[output_name]
        if source_name not in container:
            raise RouteFeatureError(f"NATIVE_TRACE_FIELD_MISSING:{path}")
        result[output_name] = container[source_name]
    return result


# Import-time schema checks keep group dimensions and leakage rules frozen.
assert FEATURE_GROUP_DIMENSIONS == {
    RouteFeatureGroup.F0: 6,
    RouteFeatureGroup.F1: 9,
    RouteFeatureGroup.F2: 9,
    RouteFeatureGroup.F3: 16,
    RouteFeatureGroup.F4: 22,
    RouteFeatureGroup.F5: 21,
}
assert len(set(RICH_ROUTE_V2_FEATURES)) == len(RICH_ROUTE_V2_FEATURES)
assert set(_FEATURE_NATIVE_SOURCES) == set(RICH_ROUTE_V2_FEATURES)
assert_deployable_g18_feature_names(RICH_ROUTE_V2_FEATURES)


__all__ = [
    "CURRENT_LOCAL_FEATURES",
    "DOWNSTREAM_FEATURES",
    "EXCLUDED_AVAILABLE_NATIVE_FIELDS",
    "EXCLUDED_UNAVAILABLE_PLANNED_FEATURES",
    "F0_FEATURES",
    "F1_FEATURES",
    "F2_FEATURES",
    "F3_FEATURES",
    "F4_FEATURES",
    "F5_FEATURES",
    "FEATURE_GROUP_CONTRACTS",
    "FEATURE_GROUP_DIMENSIONS",
    "LOCAL_FAULT_BEACON_FEATURES",
    "NATIVE_ROUTE_CANDIDATE_FIELDS",
    "RICH_ROUTE_V2",
    "RICH_ROUTE_V2_FEATURES",
    "RouteFeatureError",
    "RouteFeatureGroup",
    "RouteFeatureGroupContract",
    "S4_CORE_FEATURES",
    "TWO_HOP_FEATURES",
    "URGENCY_HISTORY_FEATURES",
    "feature_group_contract",
    "native_route_candidate_mapping",
    "project_rich_route_v2",
    "project_rich_route_v2_mapping",
]
