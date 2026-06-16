from __future__ import annotations

from pathlib import Path

import czr005_cpp


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"


def main() -> None:
    map_summary = czr005_cpp.read_legacy_map_summary(str(LEGACY / "map2.txt"))
    assert map_summary["declared_node_count"] == 54
    assert map_summary["node_count"] == 54
    assert map_summary["heuristic_rows"] == 54
    assert map_summary["edge_count"] == 69
    assert map_summary["type_1_count"] == 8
    assert map_summary["type_2_count"] == 5

    assert czr005_cpp.plan_legacy_map_path(str(LEGACY / "map2.txt"), 0, 47) == [
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
    assert czr005_cpp.plan_legacy_map_path(str(LEGACY / "map2.txt"), 52, 49) == [
        52,
        29,
        30,
        31,
        32,
        37,
        49,
    ]

    task_summary = czr005_cpp.read_legacy_task_summary(str(LEGACY / "inputdata.txt"))
    assert task_summary["raw_task_count"] == 28506
    assert task_summary["direct_raw_task_count"] == 13409
    assert task_summary["early_split_raw_task_count"] == 15097
    assert task_summary["expanded_task_count"] == 43603
    assert task_summary["expanded_by_start"][52] == 15097


if __name__ == "__main__":
    main()
