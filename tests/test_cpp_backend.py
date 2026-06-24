from __future__ import annotations

from pathlib import Path

import pytest

from czr005 import cpp_backend


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"


def _require_cpp_backend() -> None:
    try:
        cpp_backend.load_cpp_module()
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))


def test_default_search_paths_include_cmake_build_trees() -> None:
    custom = ROOT / "custom_python"

    paths = cpp_backend.default_search_paths(custom)

    assert paths[0] == custom
    assert ROOT / "build_vs" / "python" / "Debug" in paths
    assert ROOT / "build_vs" / "python" / "Release" in paths
    assert ROOT / "build_nmake" / "python" in paths


def test_cpp_backend_legacy_map_astar_smoke() -> None:
    _require_cpp_backend()

    map2 = LEGACY / "map2.txt"
    summary = cpp_backend.read_legacy_map_summary(map2)

    assert summary["node_count"] == 54
    assert summary["edge_count"] == 69
    assert cpp_backend.plan_legacy_map_path(map2, 0, 47) == [
        0,
        6,
        12,
        13,
        23,
        24,
        27,
        28,
        47,
    ]
    assert cpp_backend.plan_legacy_map_paths(map2, [(0, 47), (52, 49)]) == [
        [0, 6, 12, 13, 23, 24, 27, 28, 47],
        [52, 29, 30, 31, 32, 37, 49],
    ]


def test_cpp_backend_example1_ragged_heuristic_mode() -> None:
    _require_cpp_backend()

    example_map = LEGACY / "example1" / "map.txt"
    with pytest.raises(RuntimeError, match="heuristic row"):
        cpp_backend.read_legacy_map_summary(example_map)

    summary = cpp_backend.read_legacy_map_summary(example_map, allow_ragged_heuristic=True)

    assert summary["node_count"] == 11
    assert summary["edge_count"] == 13
    assert cpp_backend.plan_legacy_map_path(
        example_map,
        10,
        9,
        allow_ragged_heuristic=True,
    ) == [10, 2, 4, 6, 7, 9]
