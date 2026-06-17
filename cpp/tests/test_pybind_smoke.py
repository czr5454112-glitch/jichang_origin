from __future__ import annotations

from pathlib import Path

import czr005_cpp


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
RUNTIME = ROOT / "artifacts" / "runtime"


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
    assert czr005_cpp.plan_legacy_map_paths(str(LEGACY / "map2.txt"), [(0, 47), (52, 49)]) == [
        [0, 6, 12, 13, 23, 24, 27, 28, 47],
        [52, 29, 30, 31, 32, 37, 49],
    ]
    benchmark = czr005_cpp.benchmark_legacy_map_paths(str(LEGACY / "map2.txt"), [(0, 47), (52, 49)], 2)
    assert benchmark["total_plans"] == 4
    assert benchmark["checksum"] == 32

    w1 = [[0.1, -0.2], [0.3, 0.4], [-0.5, 0.25]]
    b1 = [0.01, -0.02]
    w2 = [0.7, -0.6]
    b2 = 0.05
    features = [[1.0, 0.5, -0.25], [0.0, 1.0, 0.5]]
    scores = czr005_cpp.edge_score_scores(w1, b1, w2, b2, features)
    assert len(scores) == 2
    assert czr005_cpp.edge_score_predict(w1, b1, w2, b2, features, [False, True]) == 1
    runtime_model_path = RUNTIME / "pybind_edge_score_test.txt"
    try:
        runtime_model_path.write_text(
            "\n".join(
                [
                    "czr005_edge_score_v1",
                    "feature_dim 3",
                    "hidden_dim 2",
                    "b2 0.05",
                    "w1",
                    "0.1 -0.2",
                    "0.3 0.4",
                    "-0.5 0.25",
                    "b1",
                    "0.01 -0.02",
                    "w2",
                    "0.7 -0.6",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        loaded = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(runtime_model_path))
        assert loaded.feature_dim == 3
        assert loaded.hidden_dim == 2
        assert loaded.predict(features, [False, True]) == 1
        assert loaded.predict_many([features, features], [[False, True], [True, False]]) == [1, 0]
        assert czr005_cpp.edge_score_load_summary(str(runtime_model_path))["hidden_dim"] == 2
    finally:
        runtime_model_path.unlink(missing_ok=True)

    task_summary = czr005_cpp.read_legacy_task_summary(str(LEGACY / "inputdata.txt"))
    assert task_summary["raw_task_count"] == 28506
    assert task_summary["direct_raw_task_count"] == 13409
    assert task_summary["early_split_raw_task_count"] == 15097
    assert task_summary["expanded_task_count"] == 43603
    assert task_summary["expanded_by_start"][52] == 15097


if __name__ == "__main__":
    main()
