"""Python-side loader and thin wrappers for the optional C++ pybind backend."""

from __future__ import annotations

import importlib
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
    search_path: PathLike | None = None,
) -> dict[str, Any]:
    """Run the G4IRSF11 one-edge-at-arrival C++ event runtime.

    ``bag_records`` contain only identity, release/deadline, current source and
    final goal.  There is intentionally no future-route argument.
    """

    module = load_cpp_module(search_path)
    normalized_fault_windows: list[tuple[int, int, float, float, float] | tuple[int, int, float, float, float, bool]] = []
    for record in fault_windows:
        if len(record) not in (5, 6):
            raise ValueError(
                "fault window must be (start,end,fault_time,repair_time,message_delay[,drop_notification])"
            )
        base = (
            int(record[0]),
            int(record[1]),
            float(record[2]),
            float(record[3]),
            float(record[4]),
        )
        normalized_fault_windows.append(base if len(record) == 5 else (*base, bool(record[5])))
    return dict(
        module.g4irsf11_event_runtime_from_records(
            [
                (
                    int(location),
                    int(node_type),
                    float(service_time),
                    int(x),
                    int(y),
                    [int(value) for value in outgoing],
                )
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
                    float(release_time),
                    float(deadline),
                    int(start),
                    int(goal),
                    str(source),
                )
                for segment_id, task_id, release_time, deadline, start, goal, source in bag_records
            ],
            normalized_fault_windows,
            str(queue_discipline),
            float(retry_interval),
            float(minimum_service_seconds),
            float(dispatch_headway_seconds),
            int(history_limit),
            int(max_decisions_per_bag),
            int(max_events),
            float(max_simulation_time),
            int(trace_limit),
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
        )
    )
