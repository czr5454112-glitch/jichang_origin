"""Python-side loader and thin wrappers for the optional C++ pybind backend."""

from __future__ import annotations

import importlib
import hashlib
import json
import math
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
) -> dict[str, Any]:
    """Run the G4IRSF11 one-edge-at-arrival C++ event runtime.

    ``bag_records`` contain only identity, release/deadline, current source and
    final goal.  There is intentionally no future-route argument.
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
