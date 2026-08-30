"""Python-side loader and thin wrappers for the optional C++ pybind backend."""

from __future__ import annotations

import importlib
import hashlib
import json
import math
from collections.abc import Mapping
from numbers import Real
import operator
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Iterable, Sequence


CPP_MODULE_NAME = "czr005_cpp"
CPP_BACKEND_PATH_ENV = "CZR005_CPP_PYTHON_PATH"
ROOT = Path(__file__).resolve().parents[2]

PathLike = str | os.PathLike[str]


def g4irsf17_pairwise_ensemble_source_policy_artifact(
    pairwise_artifact: Mapping[str, Any] | PathLike,
    gate_artifact: Mapping[str, Any] | PathLike,
    *,
    top_k: int = 2,
    supervisor_authorized: bool = False,
) -> dict[str, Any]:
    """Adapt transparent Phase-D exports to the native source-front schema.

    Offline authorization and native closed-loop authorization stay separate:
    the returned bundle copies ``runtime_closed_loop_authorized`` from the
    gate artifact and never infers or upgrades it.
    """

    def load_mapping(
        value: Mapping[str, Any] | PathLike, name: str
    ) -> dict[str, Any]:
        if isinstance(value, (str, os.PathLike)):
            with Path(value).open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError(f"{name} must contain one JSON object")
            return loaded
        if not isinstance(value, Mapping):
            raise TypeError(f"{name} must be a mapping or JSON path")
        return dict(value)

    pairwise = load_mapping(pairwise_artifact, "pairwise_artifact")
    gate = load_mapping(gate_artifact, "gate_artifact")
    if pairwise.get("schema") != "czr005.g4irsf17.i1_pairwise_ensemble.v1":
        raise ValueError("unsupported G4IRSF17 pairwise ensemble schema")
    if gate.get("schema") != "czr005.g4irsf17.i1_selective_gate.v1":
        raise ValueError("unsupported G4IRSF17 selective gate schema")
    def artifact_set_id(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value:
            raise TypeError(f"{name} must be a non-empty string")
        if len(value) > 160 or any(ord(character) <= 0x20 for character in value):
            raise ValueError(f"{name} must be a compact readable identifier")
        return value

    pairwise_set_id = artifact_set_id(
        pairwise.get("artifact_set_id"),
        "pairwise_artifact.artifact_set_id",
    )
    gate_set_id = artifact_set_id(
        gate.get("artifact_set_id"),
        "gate_artifact.artifact_set_id",
    )
    if pairwise_set_id != gate_set_id:
        raise ValueError(
            "G4IRSF17 pairwise/gate artifact_set_id mismatch; "
            "artifacts from different training runs cannot be combined"
        )
    for name in ("authorized", "runtime_closed_loop_authorized"):
        if not isinstance(gate.get(name), bool):
            raise TypeError(f"gate_artifact.{name} must be bool")
    if not isinstance(supervisor_authorized, bool):
        raise TypeError("supervisor_authorized must be bool")
    if isinstance(top_k, bool):
        raise TypeError("top_k must be an integer, not bool")
    try:
        normalized_top_k = int(operator.index(top_k))
    except TypeError as exc:
        raise TypeError("top_k must be an integer") from exc
    if normalized_top_k not in {2, 4}:
        raise ValueError("top_k must be 2 or 4")
    return {
        "schema": "czr005.g4irsf17.source_policy.v1",
        "kind": "pairwise_ensemble_selective",
        "artifact_set_id": pairwise_set_id,
        "authorized": gate["authorized"],
        "runtime_closed_loop_authorized": gate[
            "runtime_closed_loop_authorized"
        ],
        "supervisor_authorized": supervisor_authorized,
        "top_k": normalized_top_k,
        "pairwise_artifact": pairwise,
        "gate_artifact": gate,
    }


class CppBackendUnavailable(ImportError):
    """Raised when the C++ extension module cannot be imported."""


def default_search_paths(extra_path: PathLike | None = None) -> tuple[Path, ...]:
    """Return build-tree locations searched for the C++ extension module."""

    candidates: list[Path] = []
    if extra_path is not None:
        candidates.append(Path(extra_path))

    env_path = os.environ.get(CPP_BACKEND_PATH_ENV)
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
            ROOT / "build_vs" / "python" / "Release",
            ROOT / "build_vs" / "python" / "Debug",
            ROOT / "build_nmake" / "python",
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return tuple(unique)


def load_cpp_module(search_path: PathLike | None = None) -> ModuleType:
    """Import and return the `czr005_cpp` extension from known build locations."""

    search_paths = default_search_paths(search_path)
    for path in reversed(search_paths):
        path_text = str(path)
        sys.path[:] = [entry for entry in sys.path if entry != path_text]
        sys.path.insert(0, path_text)

    try:
        return importlib.import_module(CPP_MODULE_NAME)
    except ImportError as exc:
        locations = ", ".join(str(path) for path in search_paths)
        raise CppBackendUnavailable(
            f"failed to import {CPP_MODULE_NAME}; build the C++ target or set "
            f"{CPP_BACKEND_PATH_ENV}. searched: {locations}"
        ) from exc


def is_available(search_path: PathLike | None = None) -> bool:
    """Return whether the C++ extension can be imported."""

    try:
        load_cpp_module(search_path)
    except CppBackendUnavailable:
        return False
    return True


def read_legacy_map_summary(
    path: PathLike,
    *,
    allow_ragged_heuristic: bool = False,
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    module = load_cpp_module(search_path)
    return dict(
        module.read_legacy_map_summary(
            str(path),
            allow_ragged_heuristic=allow_ragged_heuristic,
        )
    )


def read_legacy_task_summary(path: PathLike, *, search_path: PathLike | None = None) -> dict[str, Any]:
    module = load_cpp_module(search_path)
    return dict(module.read_legacy_task_summary(str(path)))


def plan_legacy_map_path(
    map_path: PathLike,
    start: int,
    goal: int,
    *,
    allow_ragged_heuristic: bool = False,
    search_path: PathLike | None = None,
) -> list[int]:
    module = load_cpp_module(search_path)
    return [
        int(value)
        for value in module.plan_legacy_map_path(
            str(map_path),
            int(start),
            int(goal),
            allow_ragged_heuristic=allow_ragged_heuristic,
        )
    ]


def plan_legacy_map_paths(
    map_path: PathLike,
    cases: Iterable[tuple[int, int]],
    *,
    allow_ragged_heuristic: bool = False,
    search_path: PathLike | None = None,
) -> list[list[int]]:
    module = load_cpp_module(search_path)
    normalized_cases = [(int(start), int(goal)) for start, goal in cases]
    return [
        [int(value) for value in route]
        for route in module.plan_legacy_map_paths(
            str(map_path),
            normalized_cases,
            allow_ragged_heuristic=allow_ragged_heuristic,
        )
    ]


def benchmark_legacy_map_paths(
    map_path: PathLike,
    cases: Sequence[tuple[int, int]],
    repeats: int = 100,
    *,
    allow_ragged_heuristic: bool = False,
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    module = load_cpp_module(search_path)
    normalized_cases = [(int(start), int(goal)) for start, goal in cases]
    return dict(
        module.benchmark_legacy_map_paths(
            str(map_path),
            normalized_cases,
            int(repeats),
            allow_ragged_heuristic=allow_ragged_heuristic,
        )
    )


def legacy_no_fault_window_summary(
    map_path: PathLike,
    task_path: PathLike,
    *,
    start_epoch: int = 8260,
    max_epochs: int = 512,
    max_new_tasks: int = 128,
    include_routes: bool = False,
    fault_probability: float = 0.0,
    repair_probability: float = 0.0,
    allow_ragged_heuristic: bool = False,
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    module = load_cpp_module(search_path)
    return dict(
        module.legacy_no_fault_window_summary(
            str(map_path),
            str(task_path),
            int(start_epoch),
            int(max_epochs),
            int(max_new_tasks),
            bool(include_routes),
            float(fault_probability),
            float(repair_probability),
            allow_ragged_heuristic=allow_ragged_heuristic,
        )
    )


def legacy_scheduled_fault_window_summary(
    map_path: PathLike,
    task_path: PathLike,
    *,
    start_epoch: int = 8260,
    max_epochs: int = 512,
    max_new_tasks: int = 128,
    fault_schedule: Sequence[tuple[int, int, int, bool]] = (),
    include_routes: bool = False,
    fault_probability: float = 0.0,
    repair_probability: float = 0.0,
    allow_ragged_heuristic: bool = False,
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    module = load_cpp_module(search_path)
    return dict(
        module.legacy_scheduled_fault_window_summary(
            str(map_path),
            str(task_path),
            int(start_epoch),
            int(max_epochs),
            int(max_new_tasks),
            [
                (int(epoch), int(start), int(end), bool(repair))
                for epoch, start, end, repair in fault_schedule
            ],
            bool(include_routes),
            float(fault_probability),
            float(repair_probability),
            allow_ragged_heuristic=allow_ragged_heuristic,
        )
    )


def reference_simulator_from_records(
    node_records: Sequence[tuple[int, int, float, int, int, Sequence[int]]],
    edge_records: Sequence[tuple[int, int, float, float]],
    heuristic_time: Sequence[Sequence[float]],
    task_records: Sequence[
        tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]
    ],
    *,
    max_tasks: int = -1,
    end_time: float = -1.0,
    fault_edges: Sequence[tuple[int, int]] = (),
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    module = load_cpp_module(search_path)
    return dict(
        module.reference_simulator_from_records(
            [
                (int(location), int(node_type), float(service_time), int(x), int(y), [int(value) for value in outgoing])
                for location, node_type, service_time, x, y, outgoing in node_records
            ],
            [
                (int(start), int(end), float(length), float(speed))
                for start, end, length, speed in edge_records
            ],
            [[float(value) for value in row] for row in heuristic_time],
            [
                (
                    str(segment_id),
                    int(task_id),
                    int(pallet_id),
                    float(pass_time),
                    float(std),
                    int(start),
                    int(goal),
                    int(original_start),
                    int(original_goal),
                    float(original_entry_time),
                    str(leg),
                    bool(early_bag_split),
                    int(source_line),
                )
                for (
                    segment_id,
                    task_id,
                    pallet_id,
                    pass_time,
                    std,
                    start,
                    goal,
                    original_start,
                    original_goal,
                    original_entry_time,
                    leg,
                    early_bag_split,
                    source_line,
                ) in task_records
            ],
            max_tasks=int(max_tasks),
            end_time=float(end_time),
            fault_edges=[(int(start), int(end)) for start, end in fault_edges],
        )
    )


def g4h_no_astar_policy_decision(
    *,
    w1: Sequence[Sequence[float]],
    b1: Sequence[float],
    w2: Sequence[float],
    b2: float,
    features: Sequence[Sequence[float]],
    candidates: Sequence[int],
    historical_risk: Sequence[float],
    bottleneck_score: Sequence[float],
    risk_margin_threshold: float,
    risk_historical_threshold: float,
    risk_bottleneck_threshold: float,
    fallback_name: str,
    static_cost: Sequence[float],
    wait_seconds: Sequence[float],
    pressure: Sequence[float],
    progress: Sequence[float],
    loop_penalty: Sequence[float],
    backtrack: Sequence[float],
    traffic_penalty: Sequence[float],
    slack_pressure: Sequence[float],
    lookahead_cost: Sequence[float],
    faulted: Sequence[bool],
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    module = load_cpp_module(search_path)
    return dict(
        module.g4h_no_astar_policy_decision(
            [[float(value) for value in row] for row in w1],
            [float(value) for value in b1],
            [float(value) for value in w2],
            float(b2),
            [[float(value) for value in row] for row in features],
            [int(value) for value in candidates],
            [float(value) for value in historical_risk],
            [float(value) for value in bottleneck_score],
            float(risk_margin_threshold),
            float(risk_historical_threshold),
            float(risk_bottleneck_threshold),
            str(fallback_name),
            [float(value) for value in static_cost],
            [float(value) for value in wait_seconds],
            [float(value) for value in pressure],
            [float(value) for value in progress],
            [float(value) for value in loop_penalty],
            [float(value) for value in backtrack],
            [float(value) for value in traffic_penalty],
            [float(value) for value in slack_pressure],
            [float(value) for value in lookahead_cost],
            [bool(value) for value in faulted],
        )
    )


def g4i_no_astar_batch_replay(
    *,
    node_records: Sequence[tuple[int, int, float, int, int, Sequence[int]]],
    edge_records: Sequence[tuple[int, int, float, float]],
    heuristic_time: Sequence[Sequence[float]],
    window_records: Sequence[
        tuple[
            str,
            int,
            int,
            str,
            str,
            Sequence[tuple[int, int]],
            Sequence[tuple[int, int, float, float]],
        ]
    ],
    route_records: Sequence[
        tuple[str, str, int, str, int, int, float, float, float]
    ],
    w1: Sequence[Sequence[float]],
    b1: Sequence[float],
    w2: Sequence[float],
    b2: float,
    risk_margin_threshold: float,
    risk_historical_threshold: float,
    risk_bottleneck_threshold: float,
    historical_risk_rules: Sequence[tuple[int, Sequence[int], int]],
    fallback_rules: Sequence[tuple[int, int, Sequence[int], int]],
    policy_name: str,
    use_model: bool,
    rule_only: bool,
    risk_gated_rule: bool,
    fallback_name: str,
    bounded_depth: int = 1,
    max_steps: int = 80,
    trace_limit: int = 500,
    summary_only: bool = False,
    profile_enabled: bool = False,
    enable_edge_overlap_diagnostic: bool = True,
    audit_final_conflicts: bool = True,
    reservation_semantics: str = "baseline",
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    module = load_cpp_module(search_path)
    return dict(
        module.g4i_no_astar_batch_replay(
            [
                (int(location), int(node_type), float(service_time), int(x), int(y), [int(value) for value in outgoing])
                for location, node_type, service_time, x, y, outgoing in node_records
            ],
            [
                (int(start), int(end), float(length), float(speed))
                for start, end, length, speed in edge_records
            ],
            [[float(value) for value in row] for row in heuristic_time],
            [
                (
                    str(name),
                    int(offset),
                    int(size),
                    str(context),
                    str(source),
                    [(int(start), int(end)) for start, end in fault_edges],
                    [
                        (int(start), int(end), float(fault_start), float(repair_time))
                        for start, end, fault_start, repair_time in fault_windows
                    ],
                )
                for name, offset, size, context, source, fault_edges, fault_windows in window_records
            ],
            [
                (
                    str(scope),
                    str(window_name),
                    int(task_id),
                    str(segment_id),
                    int(start),
                    int(goal),
                    float(entry_time),
                    float(attempt_time),
                    float(std_time),
                )
                for scope, window_name, task_id, segment_id, start, goal, entry_time, attempt_time, std_time in route_records
            ],
            [[float(value) for value in row] for row in w1],
            [float(value) for value in b1],
            [float(value) for value in w2],
            float(b2),
            float(risk_margin_threshold),
            float(risk_historical_threshold),
            float(risk_bottleneck_threshold),
            [
                (int(current), [int(value) for value in candidates], int(predicted))
                for current, candidates, predicted in historical_risk_rules
            ],
            [
                (int(current), int(goal), [int(value) for value in candidates], int(predicted))
                for current, goal, candidates, predicted in fallback_rules
            ],
            str(policy_name),
            bool(use_model),
            bool(rule_only),
            bool(risk_gated_rule),
            str(fallback_name),
            int(bounded_depth),
            int(max_steps),
            int(trace_limit),
            bool(summary_only),
            bool(profile_enabled),
            bool(enable_edge_overlap_diagnostic),
            bool(audit_final_conflicts),
            str(reservation_semantics),
        )
    )


def g4irsf4_no_astar_streaming_replay_from_jsonl(
    *,
    node_records: Sequence[tuple[int, int, float, int, int, Sequence[int]]],
    edge_records: Sequence[tuple[int, int, float, float]],
    heuristic_time: Sequence[Sequence[float]],
    task_jsonl_path: PathLike,
    w1: Sequence[Sequence[float]],
    b1: Sequence[float],
    w2: Sequence[float],
    b2: float,
    risk_margin_threshold: float,
    risk_historical_threshold: float,
    risk_bottleneck_threshold: float,
    historical_risk_rules: Sequence[tuple[int, Sequence[int], int]],
    fallback_rules: Sequence[tuple[int, int, Sequence[int], int]],
    policy_name: str,
    use_model: bool,
    rule_only: bool,
    risk_gated_rule: bool,
    fallback_name: str,
    bounded_depth: int = 1,
    max_steps: int = 80,
    trace_limit: int = 500,
    summary_only: bool = True,
    profile_enabled: bool = False,
    enable_edge_overlap_diagnostic: bool = True,
    audit_final_conflicts: bool = True,
    fault_edges: Sequence[tuple[int, int]] = (),
    fault_windows: Sequence[tuple[int, int, float, float]] = (),
    max_tasks: int = -1,
    reservation_semantics: str = "baseline",
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    module = load_cpp_module(search_path)
    return dict(
        module.g4irsf4_no_astar_streaming_replay_from_jsonl(
            [
                (int(location), int(node_type), float(service_time), int(x), int(y), [int(value) for value in outgoing])
                for location, node_type, service_time, x, y, outgoing in node_records
            ],
            [
                (int(start), int(end), float(length), float(speed))
                for start, end, length, speed in edge_records
            ],
            [[float(value) for value in row] for row in heuristic_time],
            str(task_jsonl_path),
            [[float(value) for value in row] for row in w1],
            [float(value) for value in b1],
            [float(value) for value in w2],
            float(b2),
            float(risk_margin_threshold),
            float(risk_historical_threshold),
            float(risk_bottleneck_threshold),
            [
                (int(current), [int(value) for value in candidates], int(predicted))
                for current, candidates, predicted in historical_risk_rules
            ],
            [
                (int(current), int(goal), [int(value) for value in candidates], int(predicted))
                for current, goal, candidates, predicted in fallback_rules
            ],
            str(policy_name),
            bool(use_model),
            bool(rule_only),
            bool(risk_gated_rule),
            str(fallback_name),
            int(bounded_depth),
            int(max_steps),
            int(trace_limit),
            bool(summary_only),
            bool(profile_enabled),
            bool(enable_edge_overlap_diagnostic),
            bool(audit_final_conflicts),
            [(int(start), int(end)) for start, end in fault_edges],
            [
                (int(start), int(end), float(fault_start), float(repair_time))
                for start, end, fault_start, repair_time in fault_windows
            ],
            int(max_tasks),
            str(reservation_semantics),
        )
    )


def g4irsf11_event_runtime_from_records(
    *,
    node_records: Sequence[tuple[int, int, float, int, int, Sequence[int]]],
    edge_records: Sequence[tuple[int, int, float, float]],
    heuristic_time: Sequence[Sequence[float]],
    bag_records: Sequence[tuple[str, int, float, float, int, int, str]],
    fault_windows: Sequence[
        tuple[int, int, float, float, float]
        | tuple[int, int, float, float, float, bool]
    ] = (),
    queue_discipline: str = "aging",
    retry_interval: float = 0.25,
    minimum_service_seconds: float = 1.0e-3,
    dispatch_headway_seconds: float = 1.0e-3,
    history_limit: int = 8,
    max_decisions_per_bag: int = 512,
    max_events: int = 2_000_000,
    max_simulation_time: float = -1.0,
    trace_limit: int = 20_000,
    trace_shard_count: int = 1,
    trace_shard_index: int = 0,
    local_queue_capacity: int = 0,
    deadlock_retry_threshold: int = 8,
    diagnostic_hops: int = 2,
    enable_source_admission: bool = True,
    enable_backpressure: bool = True,
    enable_pibt_lite: bool = True,
    enable_deadlock_escape: bool = True,
    enable_fault_policy: bool = True,
    scenario: str = "manual",
    scale: float = 1.0,
    resource_semantics: str = "R0_current_undirected_full_travel_exclusive",
    entry_headway_seconds: float = 1.0e-3,
    pressure_mode: str = "absolute_downstream_queue_penalty",
    pressure_weight: float = 2.0,
    pressure_age_weight: float = 0.05,
    pressure_distance_bias: float = 0.25,
    admission_mode: str = "legacy_unbound",
    credit_validity_seconds: float = 1.0,
    credit_snapshot_max_age_seconds: float = 1.0,
    credit_capacity_per_edge: int = 1,
    credit_lifecycle_limit: int = 512,
    pibt_mode: str = "P0",
    pibt_max_depth: int | None = None,
    pibt_max_ready_bags: int = 8,
    pibt_max_local_resources: int = 32,
    pibt_max_candidates_per_bag: int = 8,
    scorer_mode: str = "S0_current_handwritten",
    scorer_model_path: PathLike | None = None,
    framework_mode: str = "event_loop_one_step",
    summary_only: bool = False,
    expected_binary_path: PathLike | None = None,
    search_path: PathLike | None = None,
    event_trace_limit: int | None = None,
    priority_mode: str = "Q0",
    pibt_preference_mode: str = "current",
    pibt_regret_prior_records: Sequence[
        tuple[int, int, int, float]
    ] = (),
    selective_credit_contention_threshold: int = 1,
    event_semantics: str = "E0_immediate_dispatch_f2",
    enable_opportunity_telemetry: bool = False,
    opportunity_trace_limit: int = 200_000,
    merge_grant_rule: str = "M1",
    merge_grant_max_pending_requests: int = 64,
    merge_grant_lifecycle_limit: int = 1024,
    g4irsf16_supervisor_mode: str = "off",
    g4irsf16_i3_model_artifact: Mapping[str, Any] | PathLike | None = None,
    g4irsf16_i4_model_artifact: Mapping[str, Any] | PathLike | None = None,
    g4irsf16_rule_bundle: Mapping[str, Any] | PathLike | None = None,
    enable_g4irsf17_source_wait_telemetry: bool = False,
    g4irsf17_source_wait_trace_limit: int = 200_000,
    g4irsf17_source_policy_mode: str = "off",
    g4irsf17_source_policy_artifact: Mapping[str, Any] | PathLike | None = None,
    g4irsf17_source_policy_trace_limit: int = 200_000,
    merge_grant_timing_mode: str = "eager",
    g4irsf18_merge_policy_mode: str = "off",
    g4irsf18_merge_policy_artifact: Mapping[str, Any] | PathLike | None = None,
    g4irsf18_merge_research_closed_loop_authorized: bool = False,
    g4irsf18_merge_fixed_research_workload: bool = False,
    g4irsf18_merge_production_closed_loop_authorized: bool = False,
    g4irsf18_merge_offline_gate_passed: bool = False,
    g4irsf18_merge_coverage_cap: float = 0.05,
    g4irsf18_merge_max_overrides_per_segment: int = 2,
    g4irsf18_merge_kill_switch: bool = False,
    bounded_wall_seconds: float = -1.0,
    bounded_check_every_events: int = 65_536,
    g4irsf20_event_hotpath_policy: str = "E0",
    g4irsf24_dlp_artifact: Mapping[str, Any] | PathLike | None = None,
    legacy_observation_bias_max_seconds: float = 0.0,
    legacy_observation_bias_seed: int = 0,
    storage_source_nodes: Sequence[int] | None = None,
    enable_s4_local_potential_descent_guard: bool = False,
    enable_s4_direct_neighbor_merge_calendar_visibility: bool = False,
    complete_on_goal_arrival: bool = False,
    source_aware_destination_service_mode: str = "off",
    source_aware_destination_service_trace_limit: int = 200_000,
) -> dict[str, Any]:
    """Run the G4IRSF11 one-edge-at-arrival C++ event runtime.

    ``bag_records`` contain only identity, release/deadline, current source and
    final goal.  There is intentionally no future-route argument.  G4IRSF32
    V3R2 shadow mode records fixed numeric external-commit/local-virtual rows;
    V3R13 closed-loop mode may reserve one exact next-free local service slot.
    """

    def strict_integer(value: Any, name: str) -> int:
        if isinstance(value, bool):
            raise TypeError(f"{name} must be an integer, not bool")
        try:
            return int(operator.index(value))
        except TypeError as exc:
            raise TypeError(f"{name} must be an integer") from exc

    def strict_bool(value: Any, name: str) -> bool:
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a bool")
        return value

    def strict_finite_number(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"{name} must be a numeric scalar, not bool")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{name} must be finite")
        return result

    history_limit = strict_integer(history_limit, "history_limit")
    max_decisions_per_bag = strict_integer(
        max_decisions_per_bag, "max_decisions_per_bag"
    )
    max_events = strict_integer(max_events, "max_events")
    trace_limit = strict_integer(trace_limit, "trace_limit")
    if event_trace_limit is not None:
        event_trace_limit = strict_integer(
            event_trace_limit, "event_trace_limit"
        )
    trace_shard_count = strict_integer(
        trace_shard_count, "trace_shard_count"
    )
    trace_shard_index = strict_integer(
        trace_shard_index, "trace_shard_index"
    )
    local_queue_capacity = strict_integer(
        local_queue_capacity, "local_queue_capacity"
    )
    deadlock_retry_threshold = strict_integer(
        deadlock_retry_threshold, "deadlock_retry_threshold"
    )
    diagnostic_hops = strict_integer(
        diagnostic_hops, "diagnostic_hops"
    )
    credit_capacity_per_edge = strict_integer(
        credit_capacity_per_edge, "credit_capacity_per_edge"
    )
    credit_lifecycle_limit = strict_integer(
        credit_lifecycle_limit, "credit_lifecycle_limit"
    )
    pibt_max_ready_bags = strict_integer(
        pibt_max_ready_bags, "pibt_max_ready_bags"
    )
    pibt_max_local_resources = strict_integer(
        pibt_max_local_resources, "pibt_max_local_resources"
    )
    pibt_max_candidates_per_bag = strict_integer(
        pibt_max_candidates_per_bag,
        "pibt_max_candidates_per_bag",
    )
    selective_credit_contention_threshold = strict_integer(
        selective_credit_contention_threshold,
        "selective_credit_contention_threshold",
    )
    opportunity_trace_limit = strict_integer(
        opportunity_trace_limit, "opportunity_trace_limit"
    )
    enable_g4irsf17_source_wait_telemetry = strict_bool(
        enable_g4irsf17_source_wait_telemetry,
        "enable_g4irsf17_source_wait_telemetry",
    )
    g4irsf17_source_wait_trace_limit = strict_integer(
        g4irsf17_source_wait_trace_limit,
        "g4irsf17_source_wait_trace_limit",
    )
    if g4irsf17_source_wait_trace_limit < 0:
        raise ValueError(
            "g4irsf17_source_wait_trace_limit must be non-negative"
        )
    g4irsf17_source_policy_trace_limit = strict_integer(
        g4irsf17_source_policy_trace_limit,
        "g4irsf17_source_policy_trace_limit",
    )
    if g4irsf17_source_policy_trace_limit < 0:
        raise ValueError(
            "g4irsf17_source_policy_trace_limit must be non-negative"
        )
    if g4irsf17_source_policy_mode not in {"off", "shadow", "closed_loop"}:
        raise ValueError(
            "g4irsf17_source_policy_mode must be off, shadow, or closed_loop"
        )
    if not isinstance(g4irsf18_merge_policy_mode, str):
        raise TypeError("g4irsf18_merge_policy_mode must be a string")
    if g4irsf18_merge_policy_mode not in {
        "off",
        "shadow",
        "research_closed_loop",
        "production_closed_loop",
    }:
        raise ValueError(
            "g4irsf18_merge_policy_mode must be off, shadow, "
            "research_closed_loop, or production_closed_loop"
        )
    g4irsf18_merge_research_closed_loop_authorized = strict_bool(
        g4irsf18_merge_research_closed_loop_authorized,
        "g4irsf18_merge_research_closed_loop_authorized",
    )
    g4irsf18_merge_fixed_research_workload = strict_bool(
        g4irsf18_merge_fixed_research_workload,
        "g4irsf18_merge_fixed_research_workload",
    )
    g4irsf18_merge_production_closed_loop_authorized = strict_bool(
        g4irsf18_merge_production_closed_loop_authorized,
        "g4irsf18_merge_production_closed_loop_authorized",
    )
    g4irsf18_merge_offline_gate_passed = strict_bool(
        g4irsf18_merge_offline_gate_passed,
        "g4irsf18_merge_offline_gate_passed",
    )
    g4irsf18_merge_kill_switch = strict_bool(
        g4irsf18_merge_kill_switch,
        "g4irsf18_merge_kill_switch",
    )
    g4irsf18_merge_coverage_cap = strict_finite_number(
        g4irsf18_merge_coverage_cap,
        "g4irsf18_merge_coverage_cap",
    )
    if not 0.0 <= g4irsf18_merge_coverage_cap <= 1.0:
        raise ValueError("g4irsf18_merge_coverage_cap must be in [0, 1]")
    g4irsf18_merge_max_overrides_per_segment = strict_integer(
        g4irsf18_merge_max_overrides_per_segment,
        "g4irsf18_merge_max_overrides_per_segment",
    )
    if g4irsf18_merge_max_overrides_per_segment < 0:
        raise ValueError(
            "g4irsf18_merge_max_overrides_per_segment must be non-negative"
        )
    merge_grant_max_pending_requests = strict_integer(
        merge_grant_max_pending_requests,
        "merge_grant_max_pending_requests",
    )
    merge_grant_lifecycle_limit = strict_integer(
        merge_grant_lifecycle_limit,
        "merge_grant_lifecycle_limit",
    )

    enable_source_admission = strict_bool(
        enable_source_admission, "enable_source_admission"
    )
    enable_backpressure = strict_bool(
        enable_backpressure, "enable_backpressure"
    )
    enable_pibt_lite = strict_bool(
        enable_pibt_lite, "enable_pibt_lite"
    )
    enable_deadlock_escape = strict_bool(
        enable_deadlock_escape, "enable_deadlock_escape"
    )
    enable_fault_policy = strict_bool(
        enable_fault_policy, "enable_fault_policy"
    )
    enable_s4_local_potential_descent_guard = strict_bool(
        enable_s4_local_potential_descent_guard,
        "enable_s4_local_potential_descent_guard",
    )
    enable_s4_direct_neighbor_merge_calendar_visibility = strict_bool(
        enable_s4_direct_neighbor_merge_calendar_visibility,
        "enable_s4_direct_neighbor_merge_calendar_visibility",
    )
    complete_on_goal_arrival = strict_bool(
        complete_on_goal_arrival,
        "complete_on_goal_arrival",
    )
    enable_opportunity_telemetry = strict_bool(
        enable_opportunity_telemetry,
        "enable_opportunity_telemetry",
    )
    summary_only = strict_bool(summary_only, "summary_only")

    retry_interval = strict_finite_number(
        retry_interval, "retry_interval"
    )
    minimum_service_seconds = strict_finite_number(
        minimum_service_seconds, "minimum_service_seconds"
    )
    dispatch_headway_seconds = strict_finite_number(
        dispatch_headway_seconds, "dispatch_headway_seconds"
    )
    max_simulation_time = strict_finite_number(
        max_simulation_time, "max_simulation_time"
    )
    bounded_wall_seconds = strict_finite_number(
        bounded_wall_seconds, "bounded_wall_seconds"
    )
    if bounded_wall_seconds != -1.0 and bounded_wall_seconds <= 0.0:
        raise ValueError(
            "bounded_wall_seconds must be -1 (disabled) or positive"
        )
    bounded_check_every_events = strict_integer(
        bounded_check_every_events, "bounded_check_every_events"
    )
    if bounded_check_every_events <= 0:
        raise ValueError("bounded_check_every_events must be positive")
    if not isinstance(g4irsf20_event_hotpath_policy, str):
        raise TypeError("g4irsf20_event_hotpath_policy must be a string")
    if g4irsf20_event_hotpath_policy not in {"E0", "E1", "E2"}:
        raise ValueError(
            "g4irsf20_event_hotpath_policy must be E0, E1, or E2"
        )
    legacy_observation_bias_max_seconds = strict_finite_number(
        legacy_observation_bias_max_seconds,
        "legacy_observation_bias_max_seconds",
    )
    if legacy_observation_bias_max_seconds < 0.0:
        raise ValueError(
            "legacy_observation_bias_max_seconds must be non-negative"
        )
    legacy_observation_bias_seed = strict_integer(
        legacy_observation_bias_seed,
        "legacy_observation_bias_seed",
    )
    if legacy_observation_bias_seed < 0:
        raise ValueError("legacy_observation_bias_seed must be non-negative")
    if not isinstance(source_aware_destination_service_mode, str):
        raise TypeError("source_aware_destination_service_mode must be a string")
    if source_aware_destination_service_mode not in {
        "off",
        "shadow",
        "closed_loop",
        "closed_loop_commit_recheck",
    }:
        raise ValueError(
            "source_aware_destination_service_mode must be off, shadow, or "
            "closed_loop; V3R15 also accepts closed_loop_commit_recheck"
        )
    source_aware_destination_service_trace_limit = strict_integer(
        source_aware_destination_service_trace_limit,
        "source_aware_destination_service_trace_limit",
    )
    if (
        source_aware_destination_service_mode != "off"
        and source_aware_destination_service_trace_limit <= 0
    ):
        raise ValueError(
            "source_aware_destination_service_trace_limit must be positive "
            "when G4IRSF32 is enabled"
        )
    storage_source_nodes_explicit = storage_source_nodes is not None
    if storage_source_nodes is None:
        storage_source_nodes = (52,)
    if isinstance(storage_source_nodes, (str, bytes)):
        raise TypeError("storage_source_nodes must be a sequence of integers")
    normalized_storage_source_nodes: list[int] = []
    seen_storage_source_nodes: set[int] = set()
    try:
        storage_source_node_values = enumerate(storage_source_nodes)
    except TypeError as exc:
        raise TypeError(
            "storage_source_nodes must be a sequence of integers"
        ) from exc
    for storage_index, value in storage_source_node_values:
        node = strict_integer(
            value,
            f"storage_source_nodes[{storage_index}]",
        )
        if node < 0:
            raise ValueError("storage_source_nodes must be non-negative")
        if node in seen_storage_source_nodes:
            raise ValueError("storage_source_nodes must not contain duplicates")
        seen_storage_source_nodes.add(node)
        normalized_storage_source_nodes.append(node)
    scale = strict_finite_number(scale, "scale")
    entry_headway_seconds = strict_finite_number(
        entry_headway_seconds, "entry_headway_seconds"
    )
    pressure_weight = strict_finite_number(
        pressure_weight, "pressure_weight"
    )
    pressure_age_weight = strict_finite_number(
        pressure_age_weight, "pressure_age_weight"
    )
    pressure_distance_bias = strict_finite_number(
        pressure_distance_bias, "pressure_distance_bias"
    )
    credit_validity_seconds = strict_finite_number(
        credit_validity_seconds, "credit_validity_seconds"
    )
    credit_snapshot_max_age_seconds = strict_finite_number(
        credit_snapshot_max_age_seconds,
        "credit_snapshot_max_age_seconds",
    )

    canonical_pibt_depths = {
        "P0": 0,
        "P1": 1,
        "P2": 2,
        "P3": 3,
        "P4": 4,
    }
    if pibt_mode not in canonical_pibt_depths:
        raise ValueError("pibt_mode must be one of P0, P1, P2, P3, P4")
    actual_pibt_depth = canonical_pibt_depths[pibt_mode]
    if pibt_max_depth is not None:
        pibt_max_depth = strict_integer(
            pibt_max_depth, "pibt_max_depth"
        )
        if pibt_max_depth != actual_pibt_depth:
            raise ValueError(
                "pibt_max_depth must equal the depth encoded by pibt_mode "
                f"({pibt_mode} requires {actual_pibt_depth})"
            )
    framework_modes = {
        "event_loop_one_step",
        "legacy_order_one_step_diagnostic",
        "old_scheduling_order_reservation_horizon_one",
    }
    if framework_mode not in framework_modes:
        raise ValueError(
            "framework_mode must be event_loop_one_step or "
            "legacy_order_one_step_diagnostic"
        )
    priority_modes = {
        "Q0",
        "Q1",
        "Q2",
        "Q3",
        "current_f2",
        "thesis_exact_local_projection",
        "thesis_type_slack_aging",
        "fault_slack_age_stable_id",
    }
    if priority_mode not in priority_modes:
        raise ValueError("priority_mode must be one of Q0, Q1, Q2, Q3")
    pibt_preference_modes = {
        "current",
        "dodge",
        "local_regret",
        "dodge_regret",
    }
    if pibt_preference_mode not in pibt_preference_modes:
        raise ValueError(
            "pibt_preference_mode must be current, dodge, local_regret, "
            "or dodge_regret"
        )
    if selective_credit_contention_threshold <= 0:
        raise ValueError(
            "selective_credit_contention_threshold must be positive"
        )
    event_semantics_modes = {
        "E0",
        "E1",
        "E2",
        "E3",
        "E4",
        "E0_immediate_dispatch_f2",
        "E1_batch_source_same_timestamp",
        "E2_batch_junction_same_timestamp",
        "E3_batch_source_and_junction_same_timestamp",
        "E4_batch_plus_destination_merge_request",
    }
    if not isinstance(event_semantics, str):
        raise TypeError("event_semantics must be a string")
    if event_semantics not in event_semantics_modes:
        raise ValueError(
            "event_semantics must be E0, E1, E2, E3, or E4"
        )
    if opportunity_trace_limit < 0:
        raise ValueError(
            "opportunity_trace_limit must be non-negative"
        )
    if not isinstance(merge_grant_rule, str):
        raise TypeError("merge_grant_rule must be a string")
    merge_grant_rule_aliases = {
        "M0": "M0",
        "M0_current_event_seq_earliest_known": "M0",
        "M1": "M1",
        "M1_fifo": "M1",
        "M2": "M2",
        "M2_earliest_projected_arrival": "M2",
        "M3": "M3",
        "M3_deadline_aging": "M3",
        "M4": "M4",
        "M4_fairness_progress": "M4",
        "M5": "M5",
        "M5_local_externality": "M5",
        "M6": "M6",
        "M6_thesis_local": "M6",
    }
    if merge_grant_rule == "M7":
        raise ValueError(
            "merge_grant_rule M7 is diagnostic-only and cannot run online"
        )
    if merge_grant_rule in {"M8", "M9"}:
        raise ValueError(
            "merge_grant_rule M8/M9 require a validated model artifact; "
            "runtime selection fails closed"
        )
    if merge_grant_rule not in merge_grant_rule_aliases:
        raise ValueError(
            "merge_grant_rule must be M0, M1, M2, M3, M4, M5, or M6"
        )
    if not isinstance(merge_grant_timing_mode, str):
        raise TypeError("merge_grant_timing_mode must be a string")
    merge_grant_timing_aliases = {
        "eager": "eager",
        "J0": "eager",
        "J0_F2_EAGER": "eager",
        "jit_fifo": "jit_fifo",
        "J1": "jit_fifo",
        "J1_F2_JIT_FIFO": "jit_fifo",
        "jit_fair_aging_deadline": "jit_fair_aging_deadline",
        "J2": "jit_fair_aging_deadline",
        "J2_F2_JIT_FAIR_AGING_DEADLINE": "jit_fair_aging_deadline",
    }
    if merge_grant_timing_mode not in merge_grant_timing_aliases:
        raise ValueError(
            "merge_grant_timing_mode must be eager, jit_fifo, or "
            "jit_fair_aging_deadline"
        )
    canonical_merge_grant_timing_mode = merge_grant_timing_aliases[
        merge_grant_timing_mode
    ]
    if merge_grant_max_pending_requests <= 0:
        raise ValueError(
            "merge_grant_max_pending_requests must be positive"
        )
    if merge_grant_lifecycle_limit < 0:
        raise ValueError(
            "merge_grant_lifecycle_limit must be non-negative"
        )

    if not isinstance(g4irsf16_supervisor_mode, str):
        raise TypeError("g4irsf16_supervisor_mode must be a string")
    if g4irsf16_supervisor_mode not in {"off", "shadow", "closed_loop"}:
        raise ValueError(
            "g4irsf16_supervisor_mode must be off, shadow, or closed_loop"
        )

    def normalized_g4irsf16_artifact(
        value: Mapping[str, Any] | PathLike | None,
        name: str,
    ) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, (str, os.PathLike)):
            with Path(value).open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError(f"{name} must contain one JSON object")
            return loaded
        if not isinstance(value, Mapping):
            raise TypeError(f"{name} must be a mapping, path, or None")
        return dict(value)

    normalized_g4irsf16_i3_model = normalized_g4irsf16_artifact(
        g4irsf16_i3_model_artifact,
        "g4irsf16_i3_model_artifact",
    )
    normalized_g4irsf16_i4_model = normalized_g4irsf16_artifact(
        g4irsf16_i4_model_artifact,
        "g4irsf16_i4_model_artifact",
    )
    normalized_g4irsf16_rule_bundle = normalized_g4irsf16_artifact(
        g4irsf16_rule_bundle,
        "g4irsf16_rule_bundle",
    )
    normalized_g4irsf17_source_policy = normalized_g4irsf16_artifact(
        g4irsf17_source_policy_artifact,
        "g4irsf17_source_policy_artifact",
    )
    normalized_g4irsf18_merge_policy = normalized_g4irsf16_artifact(
        g4irsf18_merge_policy_artifact,
        "g4irsf18_merge_policy_artifact",
    )
    normalized_g4irsf24_dlp = normalized_g4irsf16_artifact(
        g4irsf24_dlp_artifact,
        "g4irsf24_dlp_artifact",
    )
    if normalized_g4irsf24_dlp:
        g4irsf24_dlp_mode = normalized_g4irsf24_dlp.get("mode")
        if (
            normalized_g4irsf24_dlp.get("schema")
            != "czr005.g4irsf24.dlp.v1"
            or g4irsf24_dlp_mode not in {"off", "ewma", "td"}
        ):
            raise ValueError(
                "g4irsf24_dlp_artifact must use the "
                "czr005.g4irsf24.dlp.v1 schema and off, ewma, or td mode"
            )
        if g4irsf24_dlp_mode == "off":
            # Explicit off is semantically identical to None/{} and must keep
            # the historical positional call usable with older native ABIs.
            normalized_g4irsf24_dlp = {}
        elif scorer_mode not in {
            "S4",
            "S4_queue_aware_rule_only",
            "S4_uncovered_local_work_seconds_rule_only",
            "S4_queue_aware_plus_uncovered_local_work_seconds_rule_only",
            "S4_typed_service_dominance_rule_only",
            "S4_service_aware_static_dominance_rule_only",
        }:
            raise ValueError("G4IRSF24 DLP requires the frozen S4 scorer")
    if g4irsf17_source_policy_mode == "off":
        if normalized_g4irsf17_source_policy:
            raise ValueError(
                "G4IRSF17 source policy artifact requires shadow or "
                "closed_loop mode"
            )
    elif not normalized_g4irsf17_source_policy:
        raise ValueError(
            "G4IRSF17 shadow/closed_loop mode requires one explicit "
            "source policy artifact"
        )
    has_g4irsf16_models = bool(
        normalized_g4irsf16_i3_model or normalized_g4irsf16_i4_model
    )
    has_g4irsf16_rule = bool(normalized_g4irsf16_rule_bundle)
    if g4irsf16_supervisor_mode == "off":
        if has_g4irsf16_models or has_g4irsf16_rule:
            raise ValueError(
                "G4IRSF16 artifacts require shadow or closed_loop mode"
            )
    elif has_g4irsf16_rule:
        if has_g4irsf16_models:
            raise ValueError(
                "G4IRSF16 diagnostic rule and model artifacts are mutually exclusive"
            )
        from czr005.g4irsf16.model import validate_self_sha256

        validate_self_sha256(normalized_g4irsf16_rule_bundle)
        i4_section = normalized_g4irsf16_rule_bundle.get("i4")
        if (
            normalized_g4irsf16_rule_bundle.get("schema")
            != "czr005.g4irsf16.rule_bundle.v1"
            or not isinstance(i4_section, Mapping)
            or i4_section.get("promotion_authorized") is not False
            or i4_section.get("selected_rule") != "H0"
        ):
            raise ValueError("G4IRSF16 diagnostic bundle must preserve H0")
    else:
        if not (
            normalized_g4irsf16_i3_model
            and normalized_g4irsf16_i4_model
        ):
            raise ValueError(
                "G4IRSF16 model mode requires both I3 and I4 artifacts"
            )
        if g4irsf16_supervisor_mode == "closed_loop":
            raise ValueError(
                "G4IRSF16 learned-model closed_loop is fail-closed because "
                "the offline promotion gate is NO_GO; use shadow or the "
                "exact diagnostic-only H5 bundle"
            )
        from czr005.g4irsf16.model import SelectiveEnsembleModel

        i3_model = SelectiveEnsembleModel.from_artifact(
            normalized_g4irsf16_i3_model
        )
        i4_model = SelectiveEnsembleModel.from_artifact(
            normalized_g4irsf16_i4_model
        )
        if i3_model.kind != "I3" or i4_model.kind != "I4":
            raise ValueError("G4IRSF16 I3/I4 model hook mismatch")

    uses_destination_merge_grants = event_semantics in {
        "E4",
        "E4_batch_plus_destination_merge_request",
    }
    g4irsf18_merge_policy_enabled = g4irsf18_merge_policy_mode != "off"
    if not g4irsf18_merge_policy_enabled:
        if (
            normalized_g4irsf18_merge_policy
            or g4irsf18_merge_research_closed_loop_authorized
            or g4irsf18_merge_fixed_research_workload
            or g4irsf18_merge_production_closed_loop_authorized
            or g4irsf18_merge_offline_gate_passed
            or g4irsf18_merge_kill_switch
            or g4irsf18_merge_coverage_cap != 0.05
            or g4irsf18_merge_max_overrides_per_segment != 2
        ):
            raise ValueError(
                "G4IRSF18 merge artifact and runtime controls require "
                "shadow, research_closed_loop, or production_closed_loop"
            )
    elif (
        not uses_destination_merge_grants
        or canonical_merge_grant_timing_mode != "jit_fair_aging_deadline"
    ):
        raise ValueError(
            "G4IRSF18 learned merge policy requires E4 with "
            "jit_fair_aging_deadline (J2) timing"
        )
    if not uses_destination_merge_grants and (
        merge_grant_rule != "M1"
        or merge_grant_max_pending_requests != 64
        or merge_grant_lifecycle_limit != 1024
        or canonical_merge_grant_timing_mode != "eager"
    ):
        raise ValueError(
            "merge grant controls are only valid with E4 destination "
            "merge-request semantics"
        )
    if uses_destination_merge_grants:
        if resource_semantics not in {
            "R3",
            "R3_java_node_window_compatible",
        }:
            raise ValueError(
                "E4 destination merge grants require frozen R3 "
                "node-window semantics"
            )
        if pibt_mode != "P2":
            raise ValueError(
                "E4 destination merge grants require the frozen P2 "
                "bounded-local PIBT mode"
            )
        if scorer_mode not in {
            "S1",
            "S1_frozen_g4e_legal_local_adapter",
            "S2",
            "S2_frozen_g4e_without_absolute_node_ids",
            "S3",
            "S3_shortest_potential_only",
            "S4",
            "S4_queue_aware_rule_only",
            "S4_uncovered_local_work_seconds_rule_only",
            "S4_queue_aware_plus_uncovered_local_work_seconds_rule_only",
            "S4_typed_service_dominance_rule_only",
            "S4_service_aware_static_dominance_rule_only",
        }:
            raise ValueError(
                "E4 destination merge grants require an existing "
                "S1/S2/S3/S4 legal-local scorer"
            )
        if priority_mode not in {"Q0", "current_f2"}:
            raise ValueError(
                "E4 destination merge grants require the frozen Q0 "
                "priority mode"
            )
        valid_admission_modes = {
            "off",
            "legacy_unbound",
            "expiring_first_edge_credit",
            "merge_only_first_edge_credit",
            "contention_triggered_first_edge_credit",
        }
        if admission_mode not in valid_admission_modes:
            raise ValueError("unknown event-runtime admission_mode")
        if admission_mode not in {"off", "legacy_unbound"}:
            raise ValueError(
                "E4 vertical slice requires frozen C0 admission; "
                "first-edge credits are not destination merge capabilities"
            )

    scorer_modes = {
        "S0",
        "S0_current_handwritten",
        "S0_current_handwritten_static_score",
        "S1",
        "S1_frozen_g4e_legal_local_adapter",
        "S2",
        "S2_frozen_g4e_without_absolute_node_ids",
        "S3",
        "S3_shortest_potential_only",
        "S4",
        "S4_queue_aware_rule_only",
        "S4_uncovered_local_work_seconds_rule_only",
        "S4_queue_aware_plus_uncovered_local_work_seconds_rule_only",
        "S4_typed_service_dominance_rule_only",
        "S4_service_aware_static_dominance_rule_only",
    }
    if scorer_mode not in scorer_modes:
        raise ValueError("scorer_mode must be one of S0, S1, S2, S3, S4")
    frozen_mode = scorer_mode in {
        "S1",
        "S1_frozen_g4e_legal_local_adapter",
        "S2",
        "S2_frozen_g4e_without_absolute_node_ids",
    }
    scorer_w1: list[list[float]] = []
    scorer_b1: list[float] = []
    scorer_w2: list[float] = []
    scorer_b2 = 0.0
    scorer_risk_margin_threshold = 1.0
    scorer_risk_bottleneck_threshold = 5.0
    scorer_model_sha256 = ""
    if frozen_mode:
        model_path = (
            Path(scorer_model_path)
            if scorer_model_path is not None
            else ROOT
            / "artifacts"
            / "models"
            / "g4e_risk_calibrated_policy.json"
        )
        raw_model = model_path.read_bytes()
        scorer_model_sha256 = hashlib.sha256(raw_model).hexdigest()
        expected_sha256 = (
            "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
        )
        if scorer_model_sha256 != expected_sha256:
            raise ValueError(
                "frozen G4E model SHA256 mismatch: "
                f"expected {expected_sha256}, got {scorer_model_sha256}"
            )
        model_payload = json.loads(raw_model)
        if not isinstance(model_payload, dict):
            raise ValueError("frozen G4E model root must be an object")
        expected_feature_names = [
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
        ]
        if model_payload.get("model_type") != "g4e_risk_calibrated_policy":
            raise ValueError("unexpected frozen G4E model_type")
        if model_payload.get("feature_names") != expected_feature_names:
            raise ValueError(
                "frozen G4E feature_names/order does not match the audited adapter"
            )

        def finite_float(value: Any, name: str) -> float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite numeric scalar")
            result = float(value)
            if not math.isfinite(result):
                raise ValueError(f"{name} must be finite")
            return result

        raw_w1 = model_payload.get("w1")
        raw_b1 = model_payload.get("b1")
        raw_w2 = model_payload.get("w2")
        if (
            not isinstance(raw_w1, list)
            or len(raw_w1) != 22
            or any(not isinstance(row, list) or len(row) != 22 for row in raw_w1)
            or not isinstance(raw_b1, list)
            or len(raw_b1) != 22
            or not isinstance(raw_w2, list)
            or len(raw_w2) != 22
        ):
            raise ValueError(
                "frozen G4E dimensions must be w1=22x22, b1=22, w2=22"
            )
        scorer_w1 = [
            [
                finite_float(value, f"w1[{row_index}][{column_index}]")
                for column_index, value in enumerate(row)
            ]
            for row_index, row in enumerate(raw_w1)
        ]
        scorer_b1 = [
            finite_float(value, f"b1[{index}]")
            for index, value in enumerate(raw_b1)
        ]
        scorer_w2 = [
            finite_float(value, f"w2[{index}]")
            for index, value in enumerate(raw_w2)
        ]
        scorer_b2 = finite_float(model_payload.get("b2"), "b2")
        scorer_risk_margin_threshold = finite_float(
            model_payload.get("risk_margin_threshold"),
            "risk_margin_threshold",
        )
        scorer_risk_bottleneck_threshold = finite_float(
            model_payload.get("risk_bottleneck_threshold"),
            "risk_bottleneck_threshold",
        )
        if (
            scorer_risk_margin_threshold != 1.0
            or scorer_risk_bottleneck_threshold != 5.0
        ):
            raise ValueError(
                "frozen G4E risk thresholds do not match the audited artifact"
            )
    elif scorer_model_path is not None:
        raise ValueError(
            "scorer_model_path is only valid for S1/S2 frozen modes"
        )

    normalized_node_records: list[
        tuple[int, int, float, int, int, list[int]]
    ] = []
    for record_index, record in enumerate(node_records):
        if len(record) != 6:
            raise ValueError(
                f"node_records[{record_index}] must contain 6 fields"
            )
        location, node_type, service_time, x, y, outgoing = record
        normalized_node_records.append(
            (
                strict_integer(
                    location, f"node_records[{record_index}].location"
                ),
                strict_integer(
                    node_type,
                    f"node_records[{record_index}].node_type",
                ),
                strict_finite_number(
                    service_time,
                    f"node_records[{record_index}].service_time",
                ),
                strict_integer(x, f"node_records[{record_index}].x"),
                strict_integer(y, f"node_records[{record_index}].y"),
                [
                    strict_integer(
                        value,
                        f"node_records[{record_index}].outgoing"
                        f"[{outgoing_index}]",
                    )
                    for outgoing_index, value in enumerate(outgoing)
                ],
            )
        )
    if source_aware_destination_service_mode != "off":
        declared_start_nodes = {
            location
            for location, node_type, _service, _x, _y, _outgoing
            in normalized_node_records
            if node_type in {1, 7}
        }
        if (
            not storage_source_nodes_explicit
            or not normalized_storage_source_nodes
            or any(
                node not in declared_start_nodes
                for node in normalized_storage_source_nodes
            )
        ):
            raise ValueError(
                "G4IRSF32 requires an explicit nonempty unique "
                "storage_source_nodes subset of declared start nodes"
            )

    normalized_edge_records: list[
        tuple[int, int, float, float]
    ] = []
    for record_index, record in enumerate(edge_records):
        if len(record) != 4:
            raise ValueError(
                f"edge_records[{record_index}] must contain 4 fields"
            )
        start, end, length, speed = record
        normalized_edge_records.append(
            (
                strict_integer(
                    start, f"edge_records[{record_index}].start"
                ),
                strict_integer(
                    end, f"edge_records[{record_index}].end"
                ),
                strict_finite_number(
                    length, f"edge_records[{record_index}].length"
                ),
                strict_finite_number(
                    speed, f"edge_records[{record_index}].speed"
                ),
            )
        )

    normalized_heuristic_time = [
        [
            strict_finite_number(
                value,
                f"heuristic_time[{row_index}][{column_index}]",
            )
            for column_index, value in enumerate(row)
        ]
        for row_index, row in enumerate(heuristic_time)
    ]

    normalized_bag_records: list[
        tuple[str, int, float, float, int, int, str]
    ] = []
    for record_index, record in enumerate(bag_records):
        if len(record) != 7:
            raise ValueError(
                f"bag_records[{record_index}] must contain 7 fields"
            )
        (
            segment_id,
            task_id,
            release_time,
            deadline,
            start,
            goal,
            source,
        ) = record
        if not isinstance(segment_id, str) or not isinstance(source, str):
            raise TypeError(
                f"bag_records[{record_index}] segment_id/source must be strings"
            )
        normalized_bag_records.append(
            (
                segment_id,
                strict_integer(
                    task_id, f"bag_records[{record_index}].task_id"
                ),
                strict_finite_number(
                    release_time,
                    f"bag_records[{record_index}].release_time",
                ),
                strict_finite_number(
                    deadline,
                    f"bag_records[{record_index}].deadline",
                ),
                strict_integer(
                    start, f"bag_records[{record_index}].start"
                ),
                strict_integer(
                    goal, f"bag_records[{record_index}].goal"
                ),
                source,
            )
        )

    module = load_cpp_module(search_path)
    module_file = getattr(module, "__file__", None)
    if not module_file:
        raise CppBackendUnavailable(
            "loaded C++ module does not expose an on-disk __file__"
        )
    loaded_binary_path = Path(module_file).resolve()
    if expected_binary_path is not None:
        expected_path = Path(expected_binary_path).resolve()
        if os.path.normcase(str(loaded_binary_path)) != os.path.normcase(
            str(expected_path)
        ):
            raise CppBackendUnavailable(
                "loaded C++ binary path does not match expected_binary_path: "
                f"loaded={loaded_binary_path}, expected={expected_path}"
            )
    loaded_binary_sha256 = hashlib.sha256(
        loaded_binary_path.read_bytes()
    ).hexdigest()
    normalized_fault_windows: list[
        tuple[int, int, float, float, float]
        | tuple[int, int, float, float, float, bool]
    ] = []
    for record_index, record in enumerate(fault_windows):
        if len(record) not in (5, 6):
            raise ValueError(
                "fault window must be (start,end,fault_time,repair_time,message_delay[,drop_notification])"
            )
        base = (
            strict_integer(
                record[0], f"fault_windows[{record_index}].start"
            ),
            strict_integer(
                record[1], f"fault_windows[{record_index}].end"
            ),
            strict_finite_number(
                record[2],
                f"fault_windows[{record_index}].fault_time",
            ),
            strict_finite_number(
                record[3],
                f"fault_windows[{record_index}].repair_time",
            ),
            strict_finite_number(
                record[4],
                f"fault_windows[{record_index}].message_delay",
            ),
        )
        normalized_fault_windows.append(
            base
            if len(record) == 5
            else (
                *base,
                strict_bool(
                    record[5],
                    f"fault_windows[{record_index}].drop_notification",
                ),
            )
        )
    normalized_regret_prior_records: list[
        tuple[int, int, int, float]
    ] = []
    for record_index, record in enumerate(pibt_regret_prior_records):
        if len(record) != 4:
            raise ValueError(
                "pibt_regret_prior_records entries must be "
                "(from_node,to_node,goal_node,penalty)"
            )
        penalty = strict_finite_number(
            record[3],
            f"pibt_regret_prior_records[{record_index}].penalty",
        )
        if penalty < 0.0:
            raise ValueError(
                "pibt_regret_prior_records penalties must be non-negative"
            )
        normalized_regret_prior_records.append(
            (
                strict_integer(
                    record[0],
                    f"pibt_regret_prior_records[{record_index}].from_node",
                ),
                strict_integer(
                    record[1],
                    f"pibt_regret_prior_records[{record_index}].to_node",
                ),
                strict_integer(
                    record[2],
                    f"pibt_regret_prior_records[{record_index}].goal_node",
                ),
                penalty,
            )
        )
    native_event_tail: tuple[object, ...] = (
        str(event_semantics),
        bool(enable_opportunity_telemetry),
        int(opportunity_trace_limit),
    )
    if uses_destination_merge_grants:
        native_event_tail += (
            str(merge_grant_rule),
            int(merge_grant_max_pending_requests),
            int(merge_grant_lifecycle_limit),
        )
    merge_tail_materialized = uses_destination_merge_grants
    if g4irsf16_supervisor_mode != "off":
        if not uses_destination_merge_grants:
            # G4IRSF16 arguments are append-only after the older merge-grant
            # defaults, preserving positional compatibility in exact-off mode.
            native_event_tail += ("M1", 64, 1024)
            merge_tail_materialized = True
        native_event_tail += (
            str(g4irsf16_supervisor_mode),
            normalized_g4irsf16_i3_model,
            normalized_g4irsf16_i4_model,
            normalized_g4irsf16_rule_bundle,
        )
    if enable_g4irsf17_source_wait_telemetry:
        # G17 follows the G16 positional tail.  Materialise intervening
        # defaults only when this opt-in telemetry is requested, so calls to
        # older exact binaries and the G17 disabled path remain unchanged.
        if not merge_tail_materialized:
            native_event_tail += ("M1", 64, 1024)
            merge_tail_materialized = True
        if g4irsf16_supervisor_mode == "off":
            native_event_tail += ("off", {}, {}, {})
        native_event_tail += (
            True,
            int(g4irsf17_source_wait_trace_limit),
        )
    if g4irsf17_source_policy_mode != "off":
        # The policy follows the G17 wait-telemetry tail.  Intervening exact
        # defaults are materialized only for this opt-in path, retaining the
        # old positional call for mode=off (including older native binaries).
        if not merge_tail_materialized:
            native_event_tail += ("M1", 64, 1024)
            merge_tail_materialized = True
        if (
            g4irsf16_supervisor_mode == "off"
            and not enable_g4irsf17_source_wait_telemetry
        ):
            native_event_tail += ("off", {}, {}, {})
        if not enable_g4irsf17_source_wait_telemetry:
            native_event_tail += (False, 200_000)
        native_event_tail += (
            str(g4irsf17_source_policy_mode),
            normalized_g4irsf17_source_policy,
            int(g4irsf17_source_policy_trace_limit),
        )
    if canonical_merge_grant_timing_mode != "eager":
        # G18 follows the complete G16/G17 append-only tail.  Materialise only
        # missing exact defaults so the default eager call remains byte-for-
        # byte compatible with older native modules.
        if not merge_tail_materialized:
            native_event_tail += ("M1", 64, 1024)
            merge_tail_materialized = True
        if (
            g4irsf16_supervisor_mode == "off"
            and not enable_g4irsf17_source_wait_telemetry
            and g4irsf17_source_policy_mode == "off"
        ):
            native_event_tail += ("off", {}, {}, {})
        if (
            not enable_g4irsf17_source_wait_telemetry
            and g4irsf17_source_policy_mode == "off"
        ):
            native_event_tail += (False, 200_000)
        if g4irsf17_source_policy_mode == "off":
            native_event_tail += ("off", {}, 200_000)
        native_event_tail += (canonical_merge_grant_timing_mode,)
    if g4irsf18_merge_policy_enabled:
        native_event_tail += (
            str(g4irsf18_merge_policy_mode),
            normalized_g4irsf18_merge_policy,
            bool(g4irsf18_merge_research_closed_loop_authorized),
            bool(g4irsf18_merge_fixed_research_workload),
            bool(g4irsf18_merge_production_closed_loop_authorized),
            bool(g4irsf18_merge_offline_gate_passed),
            float(g4irsf18_merge_coverage_cap),
            int(g4irsf18_merge_max_overrides_per_segment),
            bool(g4irsf18_merge_kill_switch),
        )
    if bounded_wall_seconds > 0.0:
        # A bounded call targets the G19 ABI, so materialize the complete
        # append-only tail once.  Default unbounded calls retain their exact
        # historical positional shape and remain compatible with older pyds.
        native_event_tail = (
            str(event_semantics),
            bool(enable_opportunity_telemetry),
            int(opportunity_trace_limit),
            str(merge_grant_rule),
            int(merge_grant_max_pending_requests),
            int(merge_grant_lifecycle_limit),
            str(g4irsf16_supervisor_mode),
            normalized_g4irsf16_i3_model,
            normalized_g4irsf16_i4_model,
            normalized_g4irsf16_rule_bundle,
            bool(enable_g4irsf17_source_wait_telemetry),
            int(g4irsf17_source_wait_trace_limit),
            str(g4irsf17_source_policy_mode),
            normalized_g4irsf17_source_policy,
            int(g4irsf17_source_policy_trace_limit),
            canonical_merge_grant_timing_mode,
            str(g4irsf18_merge_policy_mode),
            normalized_g4irsf18_merge_policy,
            bool(g4irsf18_merge_research_closed_loop_authorized),
            bool(g4irsf18_merge_fixed_research_workload),
            bool(g4irsf18_merge_production_closed_loop_authorized),
            bool(g4irsf18_merge_offline_gate_passed),
            float(g4irsf18_merge_coverage_cap),
            int(g4irsf18_merge_max_overrides_per_segment),
            bool(g4irsf18_merge_kill_switch),
            float(bounded_wall_seconds),
            int(bounded_check_every_events),
        )
    if g4irsf20_event_hotpath_policy != "E0":
        # G20 is append-only after the complete G19 bounded tail. Materialize
        # that tail for unbounded opt-in calls without changing E0 calls to
        # older native binaries.
        if bounded_wall_seconds <= 0.0:
            native_event_tail = (
                str(event_semantics),
                bool(enable_opportunity_telemetry),
                int(opportunity_trace_limit),
                str(merge_grant_rule),
                int(merge_grant_max_pending_requests),
                int(merge_grant_lifecycle_limit),
                str(g4irsf16_supervisor_mode),
                normalized_g4irsf16_i3_model,
                normalized_g4irsf16_i4_model,
                normalized_g4irsf16_rule_bundle,
                bool(enable_g4irsf17_source_wait_telemetry),
                int(g4irsf17_source_wait_trace_limit),
                str(g4irsf17_source_policy_mode),
                normalized_g4irsf17_source_policy,
                int(g4irsf17_source_policy_trace_limit),
                canonical_merge_grant_timing_mode,
                str(g4irsf18_merge_policy_mode),
                normalized_g4irsf18_merge_policy,
                bool(g4irsf18_merge_research_closed_loop_authorized),
                bool(g4irsf18_merge_fixed_research_workload),
                bool(g4irsf18_merge_production_closed_loop_authorized),
                bool(g4irsf18_merge_offline_gate_passed),
                float(g4irsf18_merge_coverage_cap),
                int(g4irsf18_merge_max_overrides_per_segment),
                bool(g4irsf18_merge_kill_switch),
                float(bounded_wall_seconds),
                int(bounded_check_every_events),
            )
        native_event_tail += (str(g4irsf20_event_hotpath_policy),)
    if normalized_g4irsf24_dlp:
        # DLP is the append-only G24 tail.  Active calls target the G24 ABI,
        # so materialize every intervening default exactly once.  The empty
        # artifact path keeps the historical positional call unchanged and
        # remains compatible with older native modules.
        native_event_tail = (
            str(event_semantics),
            bool(enable_opportunity_telemetry),
            int(opportunity_trace_limit),
            str(merge_grant_rule),
            int(merge_grant_max_pending_requests),
            int(merge_grant_lifecycle_limit),
            str(g4irsf16_supervisor_mode),
            normalized_g4irsf16_i3_model,
            normalized_g4irsf16_i4_model,
            normalized_g4irsf16_rule_bundle,
            bool(enable_g4irsf17_source_wait_telemetry),
            int(g4irsf17_source_wait_trace_limit),
            str(g4irsf17_source_policy_mode),
            normalized_g4irsf17_source_policy,
            int(g4irsf17_source_policy_trace_limit),
            canonical_merge_grant_timing_mode,
            str(g4irsf18_merge_policy_mode),
            normalized_g4irsf18_merge_policy,
            bool(g4irsf18_merge_research_closed_loop_authorized),
            bool(g4irsf18_merge_fixed_research_workload),
            bool(g4irsf18_merge_production_closed_loop_authorized),
            bool(g4irsf18_merge_offline_gate_passed),
            float(g4irsf18_merge_coverage_cap),
            int(g4irsf18_merge_max_overrides_per_segment),
            bool(g4irsf18_merge_kill_switch),
            float(bounded_wall_seconds),
            int(bounded_check_every_events),
            str(g4irsf20_event_hotpath_policy),
            normalized_g4irsf24_dlp,
        )
    if legacy_observation_bias_max_seconds > 0.0:
        # The legacy observation seam follows G24.  Materialize intervening
        # exact defaults only for this opt-in call; zero keeps the historical
        # positional call unchanged.
        native_event_tail = (
            str(event_semantics),
            bool(enable_opportunity_telemetry),
            int(opportunity_trace_limit),
            str(merge_grant_rule),
            int(merge_grant_max_pending_requests),
            int(merge_grant_lifecycle_limit),
            str(g4irsf16_supervisor_mode),
            normalized_g4irsf16_i3_model,
            normalized_g4irsf16_i4_model,
            normalized_g4irsf16_rule_bundle,
            bool(enable_g4irsf17_source_wait_telemetry),
            int(g4irsf17_source_wait_trace_limit),
            str(g4irsf17_source_policy_mode),
            normalized_g4irsf17_source_policy,
            int(g4irsf17_source_policy_trace_limit),
            canonical_merge_grant_timing_mode,
            str(g4irsf18_merge_policy_mode),
            normalized_g4irsf18_merge_policy,
            bool(g4irsf18_merge_research_closed_loop_authorized),
            bool(g4irsf18_merge_fixed_research_workload),
            bool(g4irsf18_merge_production_closed_loop_authorized),
            bool(g4irsf18_merge_offline_gate_passed),
            float(g4irsf18_merge_coverage_cap),
            int(g4irsf18_merge_max_overrides_per_segment),
            bool(g4irsf18_merge_kill_switch),
            float(bounded_wall_seconds),
            int(bounded_check_every_events),
            str(g4irsf20_event_hotpath_policy),
            normalized_g4irsf24_dlp,
            float(legacy_observation_bias_max_seconds),
            int(legacy_observation_bias_seed),
        )
    append_only_map_tail_base = (
        str(event_semantics),
        bool(enable_opportunity_telemetry),
        int(opportunity_trace_limit),
        str(merge_grant_rule),
        int(merge_grant_max_pending_requests),
        int(merge_grant_lifecycle_limit),
        str(g4irsf16_supervisor_mode),
        normalized_g4irsf16_i3_model,
        normalized_g4irsf16_i4_model,
        normalized_g4irsf16_rule_bundle,
        bool(enable_g4irsf17_source_wait_telemetry),
        int(g4irsf17_source_wait_trace_limit),
        str(g4irsf17_source_policy_mode),
        normalized_g4irsf17_source_policy,
        int(g4irsf17_source_policy_trace_limit),
        canonical_merge_grant_timing_mode,
        str(g4irsf18_merge_policy_mode),
        normalized_g4irsf18_merge_policy,
        bool(g4irsf18_merge_research_closed_loop_authorized),
        bool(g4irsf18_merge_fixed_research_workload),
        bool(g4irsf18_merge_production_closed_loop_authorized),
        bool(g4irsf18_merge_offline_gate_passed),
        float(g4irsf18_merge_coverage_cap),
        int(g4irsf18_merge_max_overrides_per_segment),
        bool(g4irsf18_merge_kill_switch),
        float(bounded_wall_seconds),
        int(bounded_check_every_events),
        str(g4irsf20_event_hotpath_policy),
        normalized_g4irsf24_dlp,
        float(legacy_observation_bias_max_seconds),
        int(legacy_observation_bias_seed),
    )
    map_tail_suffix: tuple[Any, ...] = ()
    if complete_on_goal_arrival:
        map_tail_suffix = (
            normalized_storage_source_nodes,
            bool(enable_s4_local_potential_descent_guard),
            bool(enable_s4_direct_neighbor_merge_calendar_visibility),
            True,
        )
    elif enable_s4_direct_neighbor_merge_calendar_visibility:
        map_tail_suffix = (
            normalized_storage_source_nodes,
            bool(enable_s4_local_potential_descent_guard),
            True,
        )
    elif enable_s4_local_potential_descent_guard:
        map_tail_suffix = (
            normalized_storage_source_nodes,
            True,
        )
    elif tuple(normalized_storage_source_nodes) != (52,):
        map_tail_suffix = (
            normalized_storage_source_nodes,
        )
    if map_tail_suffix:
        # Append only through the last requested flag.  With every G31/map
        # option off, older native modules retain the historical call shape.
        native_event_tail = append_only_map_tail_base + map_tail_suffix
    if source_aware_destination_service_mode != "off":
        # G32 follows the complete G31 map tail.  Off keeps the historical
        # positional call shape for exact compatibility with the parent pyd.
        native_event_tail = append_only_map_tail_base + (
            normalized_storage_source_nodes,
            bool(enable_s4_local_potential_descent_guard),
            bool(enable_s4_direct_neighbor_merge_calendar_visibility),
            bool(complete_on_goal_arrival),
            source_aware_destination_service_mode,
            int(source_aware_destination_service_trace_limit),
        )
    payload = dict(
        module.g4irsf11_event_runtime_from_records(
            normalized_node_records,
            normalized_edge_records,
            normalized_heuristic_time,
            normalized_bag_records,
            normalized_fault_windows,
            str(queue_discipline),
            float(retry_interval),
            float(minimum_service_seconds),
            float(dispatch_headway_seconds),
            int(history_limit),
            int(max_decisions_per_bag),
            int(max_events),
            float(max_simulation_time),
            0 if summary_only else int(trace_limit),
            int(trace_shard_count),
            int(trace_shard_index),
            int(local_queue_capacity),
            int(deadlock_retry_threshold),
            int(diagnostic_hops),
            bool(enable_source_admission),
            bool(enable_backpressure),
            bool(enable_pibt_lite),
            bool(enable_deadlock_escape),
            bool(enable_fault_policy),
            str(scenario),
            float(scale),
            str(resource_semantics),
            float(entry_headway_seconds),
            str(pressure_mode),
            float(pressure_weight),
            float(pressure_age_weight),
            float(pressure_distance_bias),
            str(admission_mode),
            float(credit_validity_seconds),
            float(credit_snapshot_max_age_seconds),
            int(credit_capacity_per_edge),
            int(credit_lifecycle_limit),
            str(pibt_mode),
            int(pibt_max_ready_bags),
            int(pibt_max_local_resources),
            int(pibt_max_candidates_per_bag),
            str(scorer_mode),
            scorer_w1,
            scorer_b1,
            scorer_w2,
            float(scorer_b2),
            float(scorer_risk_margin_threshold),
            float(scorer_risk_bottleneck_threshold),
            scorer_model_sha256,
            str(framework_mode),
            (
                None
                if summary_only or event_trace_limit is None
                else int(event_trace_limit)
            ),
            str(priority_mode),
            str(pibt_preference_mode),
            normalized_regret_prior_records,
            int(selective_credit_contention_threshold),
            *native_event_tail,
        )
    )
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("C++ event runtime payload.summary must be a dict")
    binary_path_text = str(loaded_binary_path)
    summary["loaded_cpp_binary_path"] = binary_path_text
    summary["loaded_cpp_binary_sha256"] = loaded_binary_sha256
    payload["loaded_cpp_binary_path"] = binary_path_text
    payload["loaded_cpp_binary_sha256"] = loaded_binary_sha256
    return payload


_G4IRSF14_FROZEN_MODEL_SHA256 = (
    "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
)
_G4IRSF14_STATE_COMPONENTS = (
    "event_queue_sha256",
    "current_time_sha256",
    "bags_sha256",
    "source_queues_sha256",
    "junction_queues_sha256",
    "local_service_calendars_sha256",
    "corridor_state_sha256",
    "scheduled_incoming_sha256",
    "credits_sha256",
    "merge_grants_sha256",
    "fault_state_sha256",
    "pibt_owner_state_sha256",
    "deterministic_counters_sha256",
    "scorer_state_sha256",
    "result_accumulator_sha256",
    "current_runtime_hashes_sha256",
    "congestion_beacons_sha256",
    "microphase_state_sha256",
)
_G4IRSF14_REPLAY_HASHES = (
    "complete_bags_sha256",
    "segment_result_sha256",
    "junction_state_sha256",
    "algorithm_summary_sha256",
    "deterministic_result_sha256",
)


def g4irsf14_state_clone_noop_rerun_from_records(
    *,
    node_records: Sequence[
        tuple[int, int, float, int, int, Sequence[int]]
    ],
    edge_records: Sequence[tuple[int, int, float, float]],
    heuristic_time: Sequence[Sequence[float]],
    bag_records: Sequence[
        tuple[str, int, float, float, int, int, str]
    ],
    preregistered_event_ordinal: int,
    scorer_model_path: PathLike | None = None,
    expected_binary_path: PathLike | None = None,
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    """Run an exact-binary, production-runtime no-op checkpoint replay.

    The entrypoint is deliberately narrower than
    :func:`g4irsf11_event_runtime_from_records`: all online controls are frozen
    to the audited Stage-D/Stage-E ``R3/S1/P2/C0/Q0/E4/M0`` tuple.  It captures
    a real queue-top pre-pop checkpoint at the caller-preregistered event
    ordinal, restores two independently constructed runtimes, and drains the
    source plus both restored branches to the same terminal horizon.

    This establishes no-op clone fidelity only.  It does not apply I1--I5 and
    cannot by itself create or validate a causal training label.
    """

    def strict_integer(value: Any, name: str) -> int:
        if isinstance(value, bool):
            raise TypeError(f"{name} must be an integer, not bool")
        try:
            return int(operator.index(value))
        except TypeError as exc:
            raise TypeError(f"{name} must be an integer") from exc

    def finite_number(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"{name} must be a numeric scalar, not bool")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{name} must be finite")
        return result

    event_ordinal = strict_integer(
        preregistered_event_ordinal,
        "preregistered_event_ordinal",
    )
    if event_ordinal < 0:
        raise ValueError(
            "preregistered_event_ordinal must be non-negative"
        )
    if not bag_records:
        raise ValueError(
            "state-clone no-op rerun requires at least one original request"
        )

    normalized_nodes: list[
        tuple[int, int, float, int, int, list[int]]
    ] = []
    for record_index, record in enumerate(node_records):
        if len(record) != 6:
            raise ValueError(
                f"node_records[{record_index}] must contain 6 fields"
            )
        location, node_type, service_time, x, y, outgoing = record
        normalized_nodes.append(
            (
                strict_integer(
                    location, f"node_records[{record_index}].location"
                ),
                strict_integer(
                    node_type, f"node_records[{record_index}].node_type"
                ),
                finite_number(
                    service_time,
                    f"node_records[{record_index}].service_time",
                ),
                strict_integer(x, f"node_records[{record_index}].x"),
                strict_integer(y, f"node_records[{record_index}].y"),
                [
                    strict_integer(
                        value,
                        f"node_records[{record_index}].outgoing"
                        f"[{outgoing_index}]",
                    )
                    for outgoing_index, value in enumerate(outgoing)
                ],
            )
        )

    normalized_edges: list[tuple[int, int, float, float]] = []
    for record_index, record in enumerate(edge_records):
        if len(record) != 4:
            raise ValueError(
                f"edge_records[{record_index}] must contain 4 fields"
            )
        start, end, length, speed = record
        normalized_edges.append(
            (
                strict_integer(
                    start, f"edge_records[{record_index}].start"
                ),
                strict_integer(
                    end, f"edge_records[{record_index}].end"
                ),
                finite_number(
                    length, f"edge_records[{record_index}].length"
                ),
                finite_number(
                    speed, f"edge_records[{record_index}].speed"
                ),
            )
        )

    normalized_heuristic = [
        [
            finite_number(
                value,
                f"heuristic_time[{row_index}][{column_index}]",
            )
            for column_index, value in enumerate(row)
        ]
        for row_index, row in enumerate(heuristic_time)
    ]
    normalized_bags: list[
        tuple[str, int, float, float, int, int, str]
    ] = []
    for record_index, record in enumerate(bag_records):
        if len(record) != 7:
            raise ValueError(
                f"bag_records[{record_index}] must contain 7 fields"
            )
        segment_id, task_id, release, deadline, start, goal, source = (
            record
        )
        if not isinstance(segment_id, str) or not segment_id:
            raise TypeError(
                f"bag_records[{record_index}].segment_id must be a "
                "non-empty string"
            )
        if not isinstance(source, str) or not source:
            raise TypeError(
                f"bag_records[{record_index}].source must be a "
                "non-empty string"
            )
        normalized_bags.append(
            (
                segment_id,
                strict_integer(
                    task_id, f"bag_records[{record_index}].task_id"
                ),
                finite_number(
                    release, f"bag_records[{record_index}].release_time"
                ),
                finite_number(
                    deadline, f"bag_records[{record_index}].deadline"
                ),
                strict_integer(
                    start, f"bag_records[{record_index}].start"
                ),
                strict_integer(
                    goal, f"bag_records[{record_index}].goal"
                ),
                source,
            )
        )

    model_path = (
        Path(scorer_model_path)
        if scorer_model_path is not None
        else ROOT
        / "artifacts"
        / "models"
        / "g4e_risk_calibrated_policy.json"
    )
    model_bytes = model_path.read_bytes()
    model_sha256 = hashlib.sha256(model_bytes).hexdigest()
    if model_sha256 != _G4IRSF14_FROZEN_MODEL_SHA256:
        raise ValueError(
            "frozen G4E model SHA256 mismatch: expected "
            f"{_G4IRSF14_FROZEN_MODEL_SHA256}, got {model_sha256}"
        )
    model = json.loads(model_bytes)
    if not isinstance(model, dict):
        raise ValueError("frozen G4E model root must be an object")

    raw_w1 = model.get("w1")
    raw_b1 = model.get("b1")
    raw_w2 = model.get("w2")
    if (
        not isinstance(raw_w1, list)
        or len(raw_w1) != 22
        or any(
            not isinstance(row, list) or len(row) != 22
            for row in raw_w1
        )
        or not isinstance(raw_b1, list)
        or len(raw_b1) != 22
        or not isinstance(raw_w2, list)
        or len(raw_w2) != 22
    ):
        raise ValueError(
            "frozen G4E dimensions must be w1=22x22, b1=22, w2=22"
        )
    scorer_w1 = [
        [
            finite_number(
                value, f"model.w1[{row_index}][{column_index}]"
            )
            for column_index, value in enumerate(row)
        ]
        for row_index, row in enumerate(raw_w1)
    ]
    scorer_b1 = [
        finite_number(value, f"model.b1[{index}]")
        for index, value in enumerate(raw_b1)
    ]
    scorer_w2 = [
        finite_number(value, f"model.w2[{index}]")
        for index, value in enumerate(raw_w2)
    ]
    scorer_b2 = finite_number(model.get("b2"), "model.b2")
    risk_margin = finite_number(
        model.get("risk_margin_threshold"),
        "model.risk_margin_threshold",
    )
    risk_bottleneck = finite_number(
        model.get("risk_bottleneck_threshold"),
        "model.risk_bottleneck_threshold",
    )
    if risk_margin != 1.0 or risk_bottleneck != 5.0:
        raise ValueError(
            "frozen G4E risk thresholds do not match the audited artifact"
        )

    module = load_cpp_module(search_path)
    module_file = getattr(module, "__file__", None)
    if not module_file:
        raise CppBackendUnavailable(
            "loaded C++ module does not expose an on-disk __file__"
        )
    loaded_binary_path = Path(module_file).resolve()
    if expected_binary_path is not None:
        expected_path = Path(expected_binary_path).resolve()
        if os.path.normcase(str(loaded_binary_path)) != os.path.normcase(
            str(expected_path)
        ):
            raise CppBackendUnavailable(
                "loaded C++ binary path does not match "
                "expected_binary_path: "
                f"loaded={loaded_binary_path}, expected={expected_path}"
            )
    loaded_binary_sha256 = hashlib.sha256(
        loaded_binary_path.read_bytes()
    ).hexdigest()

    payload = dict(
        module.g4irsf14_state_clone_noop_rerun_from_records(
            normalized_nodes,
            normalized_edges,
            normalized_heuristic,
            normalized_bags,
            event_ordinal,
            scorer_w1,
            scorer_b1,
            scorer_w2,
            scorer_b2,
            risk_margin,
            risk_bottleneck,
            model_sha256,
        )
    )
    loaded_binary_sha256_after = hashlib.sha256(
        loaded_binary_path.read_bytes()
    ).hexdigest()
    if loaded_binary_sha256_after != loaded_binary_sha256:
        raise CppBackendUnavailable(
            "loaded C++ binary bytes changed during the exact no-op rerun"
        )

    if payload.get("schema") != (
        "czr005.g4irsf14.exact_binary_noop_rerun.v1"
    ):
        raise RuntimeError(
            "native no-op rerun returned an unexpected schema"
        )
    if payload.get("evidence_scope") != (
        "NOOP_FIDELITY_MECHANISM_ONLY_NOT_A_CAUSAL_LABEL"
    ):
        raise RuntimeError(
            "native no-op rerun widened its evidence scope"
        )
    if payload.get("formal_pass_claimed") is not False:
        raise RuntimeError(
            "native no-op rerun must not claim a formal Stage-E pass"
        )
    if payload.get("intervention_applied") is not False:
        raise RuntimeError(
            "native no-op rerun unexpectedly claims an intervention"
        )
    expected_controls = {
        "resource_semantics": "R3_java_node_window_compatible",
        "scorer_mode": "S1_frozen_g4e_legal_local_adapter",
        "pibt_mode": "P2",
        "admission_mode": "off",
        "pressure_mode": "off",
        "priority_mode": "Q0",
        "event_semantics": (
            "E4_batch_plus_destination_merge_request"
        ),
        "merge_grant_rule": "M0",
        "scale": 1.0,
        "reservation_depth": 1,
        "max_events": 20_000_000,
        "max_simulation_time": -1.0,
        "trace_limit": 0,
        "event_trace_limit": 0,
    }
    if payload.get("frozen_controls") != expected_controls:
        raise RuntimeError(
            "native no-op rerun drifted from the frozen controls"
        )
    state_component_keys = set(_G4IRSF14_STATE_COMPONENTS)
    source_components = payload.get("state_components")
    baseline_components = payload.get(
        "baseline_start_state_components"
    )
    clone_components = payload.get("clone_start_state_components")
    if not all(
        isinstance(value, dict)
        and set(value) == state_component_keys
        for value in (
            source_components,
            baseline_components,
            clone_components,
        )
    ):
        raise RuntimeError(
            "native no-op rerun returned an incomplete state inventory"
        )
    if any(
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        for inventory in (
            source_components,
            baseline_components,
            clone_components,
        )
        for digest in inventory.values()
    ):
        raise RuntimeError(
            "native no-op rerun returned an invalid inventory digest"
        )
    if not (
        source_components == baseline_components == clone_components
    ):
        raise RuntimeError(
            "native no-op rerun start-state inventories differ"
        )
    runtime_state_sha256 = payload.get("runtime_state_sha256")
    if (
        not isinstance(runtime_state_sha256, str)
        or len(runtime_state_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in runtime_state_sha256
        )
        or payload.get("baseline_start_state_sha256")
        != runtime_state_sha256
        or payload.get("clone_start_state_sha256")
        != runtime_state_sha256
    ):
        raise RuntimeError(
            "native no-op rerun start-state aggregate hashes differ"
        )
    boundary = payload.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("kind") != "queue_top_pre_pop"
        or boundary.get("processed_event_count") != event_ordinal
        or boundary.get("runtime_state_sha256")
        != runtime_state_sha256
        or boundary.get("queue_top_not_popped") is not True
        or boundary.get("staged_event_sink_empty") is not True
    ):
        raise RuntimeError(
            "native no-op rerun did not expose the exact pre-pop boundary"
        )

    replay_hash_keys = set(_G4IRSF14_REPLAY_HASHES)
    source_hashes = payload.get("source_replay_hashes")
    baseline_hashes = payload.get("baseline_replay_hashes")
    clone_hashes = payload.get("clone_replay_hashes")
    if not all(
        isinstance(value, dict) and set(value) == replay_hash_keys
        for value in (source_hashes, baseline_hashes, clone_hashes)
    ):
        raise RuntimeError(
            "native no-op rerun returned an incomplete replay hash set"
        )
    if any(
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        for hashes in (source_hashes, baseline_hashes, clone_hashes)
        for digest in hashes.values()
    ):
        raise RuntimeError(
            "native no-op rerun returned an invalid replay digest"
        )
    if not source_hashes == baseline_hashes == clone_hashes:
        raise RuntimeError(
            "exact no-op replay fidelity is below 100%"
        )
    if payload.get("native_three_way_exact_match") is not True:
        raise RuntimeError(
            "native no-op rerun did not attest its raw three-way match"
        )

    invariant_names = (
        "source_invariants",
        "baseline_invariants",
        "clone_invariants",
    )
    invariant_rows = [payload.get(name) for name in invariant_names]
    if not all(isinstance(row, dict) for row in invariant_rows):
        raise RuntimeError(
            "native no-op rerun omitted raw branch invariants"
        )
    source_invariants, baseline_invariants, clone_invariants = (
        invariant_rows
    )
    if not (
        source_invariants
        == baseline_invariants
        == clone_invariants
    ):
        raise RuntimeError(
            "no-op replay branches have different raw invariants"
        )
    invariants = source_invariants
    assert isinstance(invariants, dict)
    requested_count = invariants.get("requested_count")
    if (
        not isinstance(requested_count, int)
        or isinstance(requested_count, bool)
        or requested_count != len(normalized_bags)
        or invariants.get("completed_count") != requested_count
        or invariants.get("failed_segment_count") != 0
    ):
        raise RuntimeError(
            "no-op replay did not complete every requested segment"
        )
    zero_gate_fields = (
        "unsafe_entry_count",
        "reservation_conflict_count",
        "runtime_full_astar_call_count",
        "runtime_global_scan_count",
        "runtime_future_route_read_count",
        "runtime_future_schedule_read_count",
        "teacher_input_count",
        "priority_teacher_input_count",
        "scorer_teacher_input_count",
        "full_future_routes_stored",
        "two_step_reservation_count",
        "unresolved_deadlock_count",
        "merge_grant_final_active_unconsumed",
        "merge_grant_outstanding_request_count",
        "merge_grant_stale_arbitration_count",
        "stale_arbitration_event_count",
        "artificial_batch_delay_seconds",
    )
    if any(invariants.get(name) != 0 for name in zero_gate_fields):
        raise RuntimeError(
            "no-op replay violated a zero-valued production hard gate"
        )
    lifecycle_dropped_count = invariants.get(
        "merge_grant_lifecycle_dropped_count"
    )
    if (
        not isinstance(lifecycle_dropped_count, int)
        or isinstance(lifecycle_dropped_count, bool)
        or lifecycle_dropped_count < 0
    ):
        raise RuntimeError(
            "no-op replay returned an invalid merge lifecycle drop count"
        )
    lifecycle_complete = lifecycle_dropped_count == 0
    active_state_integrity = (
        invariants.get("merge_grant_conservation_holds") is True
        and invariants.get("merge_grant_active_bijection_holds") is True
        and invariants.get("merge_grant_runtime_owned_capability") is True
        and invariants.get("merge_grant_exact_slot_no_future_shift") is True
        and invariants.get("merge_grant_final_active_unconsumed") == 0
        and invariants.get("merge_grant_outstanding_request_count") == 0
    )
    if (
        invariants.get("merge_grant_lifecycle_complete")
        is not lifecycle_complete
        or invariants.get("merge_grant_active_state_integrity_pass")
        is not active_state_integrity
        or invariants.get("merge_grant_protocol_integrity_pass")
        is not (active_state_integrity and lifecycle_complete)
    ):
        raise RuntimeError(
            "no-op replay returned inconsistent merge protocol attestations"
        )
    if (
        invariants.get("bag_future_path_field_present") is not False
        or invariants.get("reservation_depth") != 1
        or invariants.get("max_selected_edges_per_bag") not in (0, 1)
        or invariants.get("event_limit_reached") is not False
        or invariants.get("time_limit_reached") is not False
        or invariants.get("merge_grant_conservation_holds") is not True
        or invariants.get("merge_grant_active_bijection_holds") is not True
        or invariants.get("merge_grant_runtime_owned_capability") is not True
        or invariants.get("merge_grant_exact_slot_no_future_shift") is not True
        or invariants.get("merge_grant_active_state_integrity_pass") is not True
    ):
        raise RuntimeError(
            "no-op replay violated a production safety/control hard gate"
        )

    binary_path_text = str(loaded_binary_path)
    payload["loaded_cpp_binary_path"] = binary_path_text
    payload["loaded_cpp_binary_sha256"] = loaded_binary_sha256
    payload["binary"] = {
        "path": binary_path_text,
        "sha256": loaded_binary_sha256,
    }
    return payload
