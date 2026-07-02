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
