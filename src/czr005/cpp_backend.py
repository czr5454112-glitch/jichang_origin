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
            ROOT / "build_vs" / "python" / "Debug",
            ROOT / "build_vs" / "python" / "Release",
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
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

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
