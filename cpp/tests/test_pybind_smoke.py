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

    example_map = LEGACY / "example1" / "map.txt"
    try:
        czr005_cpp.read_legacy_map_summary(str(example_map))
    except RuntimeError as exc:
        assert "heuristic row" in str(exc)
    else:
        raise AssertionError("example1 ragged heuristic map should require compatibility mode")

    example_summary = czr005_cpp.read_legacy_map_summary(
        str(example_map),
        allow_ragged_heuristic=True,
    )
    assert example_summary["declared_node_count"] == 11
    assert example_summary["node_count"] == 11
    assert example_summary["heuristic_rows"] == 11
    assert example_summary["edge_count"] == 13
    assert example_summary["type_1_count"] == 2
    assert example_summary["type_2_count"] == 1
    assert czr005_cpp.plan_legacy_map_path(
        str(example_map),
        0,
        9,
        allow_ragged_heuristic=True,
    ) == [0, 1, 3, 5, 8, 9]
    assert czr005_cpp.plan_legacy_map_paths(
        str(example_map),
        [(0, 9), (10, 9)],
        allow_ragged_heuristic=True,
    ) == [
        [0, 1, 3, 5, 8, 9],
        [10, 2, 4, 6, 7, 9],
    ]

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

    native_replay = czr005_cpp.edge_score_native_replay_summary(
        str(LEGACY / "map2.txt"),
        str(LEGACY / "inputdata.txt"),
        str(RUNTIME / "phase8_edge_score_runtime_model.txt"),
        max_tasks=2,
    )
    assert native_replay["planned_count"] + native_replay["unplanned_count"] == 2
    assert native_replay["planned_count"] >= 1
    assert native_replay["decision_count"] > 0
    assert native_replay["post_shield_conflicts"] == 0

    native_trace = czr005_cpp.edge_score_native_replay_trace(
        str(LEGACY / "map2.txt"),
        str(LEGACY / "inputdata.txt"),
        str(RUNTIME / "phase8_edge_score_runtime_model.txt"),
        max_tasks=2,
    )
    assert native_trace["summary"]["decision_count"] == len(native_trace["trace"])
    assert native_trace["trace"][0]["decision_ordinal"] == 1
    assert native_trace["trace"][0]["task_decision_ordinal"] == 1
    assert native_trace["trace"][0]["event"] == "step"
    assert native_trace["trace"][0]["executed_kind"] in {"move", "hold"}
    assert native_trace["trace"][0]["candidate_count"] >= native_trace["trace"][0]["safe_candidate_count"]

    offset_replay = czr005_cpp.edge_score_native_replay_summary(
        str(LEGACY / "map2.txt"),
        str(LEGACY / "inputdata.txt"),
        str(RUNTIME / "phase8_edge_score_runtime_model.txt"),
        max_tasks=2,
        task_offset=4,
    )
    assert offset_replay["planned_count"] + offset_replay["unplanned_count"] == 2
    assert offset_replay["post_shield_conflicts"] == 0

    fallback_replay = czr005_cpp.edge_score_native_fallback_replay_summary(
        str(LEGACY / "map2.txt"),
        str(LEGACY / "inputdata.txt"),
        max_tasks=2,
    )
    assert fallback_replay["planned_count"] + fallback_replay["unplanned_count"] == 2
    assert fallback_replay["planned_count"] >= 1
    assert fallback_replay["decision_count"] > 0
    assert fallback_replay["post_shield_conflicts"] == 0

    repair_window_replay = czr005_cpp.edge_score_native_fallback_replay_summary(
        str(LEGACY / "map2.txt"),
        str(LEGACY / "inputdata.txt"),
        max_tasks=2,
        fault_windows=[(16, 17, 0.0, 9000.0)],
    )
    assert repair_window_replay["planned_count"] + repair_window_replay["unplanned_count"] == 2
    assert repair_window_replay["decision_count"] > 0
    assert repair_window_replay["post_shield_conflicts"] == 0

    node_records = [
        (0, 1, 0.0, 0, 0, [1]),
        (1, 4, 1.0, 1, 0, [2]),
        (2, 2, 0.0, 2, 0, []),
    ]
    edge_records = [
        (0, 1, 5.0, 2.5),
        (1, 2, 5.0, 2.5),
    ]
    heuristic_time = [
        [0.0, 2.0, 4.0],
        [4.0, 0.0, 2.0],
        [4.0, 2.0, 0.0],
    ]
    task_records = [
        ("records-active", 301, 301, 0.0, 20.0, 0, 2, 0, 2, 0.0, "direct", False, 1),
        ("records-after", 302, 302, 12.0, 32.0, 0, 2, 0, 2, 12.0, "direct", False, 2),
    ]
    rolling_task_records = [
        ("loose", 401, 401, 0.1, 100.0, 0, 2, 0, 2, 0.1, "direct", False, 1),
        ("urgent", 402, 402, 0.0, 20.0, 0, 2, 0, 2, 0.0, "direct", False, 2),
    ]
    sipp_route = czr005_cpp.sipp_plan_from_records(
        node_records,
        edge_records,
        heuristic_time,
        start=0,
        goal=2,
        node_reservations=[(99, 1, 2.0, 3.0)],
        task_id=301,
    )
    assert [row["location"] for row in sipp_route] == [0, 1, 2]
    assert abs(sipp_route[1]["t1"] - 3.000000001) < 1.0e-9
    sipp_buffer_route = czr005_cpp.sipp_plan_from_records(
        node_records,
        edge_records,
        heuristic_time,
        start=0,
        goal=2,
        node_reservations=[(99, 1, 2.0, 3.0)],
        node_capacities=[(1, 2)],
        task_id=302,
    )
    assert [row["location"] for row in sipp_buffer_route] == [0, 1, 2]
    assert abs(sipp_buffer_route[1]["t1"] - 2.0) < 1.0e-9
    sipp_fault_blocked = czr005_cpp.sipp_plan_from_records(
        node_records,
        edge_records,
        heuristic_time,
        start=0,
        goal=2,
        fault_edges=[(1, 2)],
        task_id=301,
    )
    assert sipp_fault_blocked == []

    rolling_horizon = czr005_cpp.rolling_horizon_sipp_from_records(
        node_records,
        edge_records,
        heuristic_time,
        rolling_task_records,
        max_tasks=2,
        horizon_seconds=60.0,
    )
    assert rolling_horizon["summary"]["planned_count"] == 2
    assert rolling_horizon["summary"]["unplanned_count"] == 0
    assert rolling_horizon["summary"]["post_shield_conflicts"] == 0
    assert [event["segment_id"] for event in rolling_horizon["events"]] == ["urgent", "loose"]

    rolling_buffer = czr005_cpp.rolling_horizon_sipp_from_records(
        node_records,
        edge_records,
        heuristic_time,
        [
            ("buffer-first", 405, 405, 0.0, 10.0, 0, 2, 0, 2, 0.0, "direct", False, 5),
            ("buffer-second", 406, 406, 0.1, 20.0, 0, 2, 0, 2, 0.1, "direct", False, 6),
        ],
        max_tasks=2,
        horizon_seconds=60.0,
        edge_capacity=2,
        node_capacities=[(1, 2)],
    )
    assert rolling_buffer["summary"]["planned_count"] == 2
    assert rolling_buffer["summary"]["post_shield_conflicts"] == 0

    rolling_repair_active = czr005_cpp.rolling_horizon_sipp_from_records(
        node_records,
        edge_records,
        heuristic_time,
        [("repair-active", 403, 403, 5.0, 40.0, 0, 2, 0, 2, 5.0, "direct", False, 3)],
        max_tasks=1,
        horizon_seconds=60.0,
        fault_windows=[(1, 2, 0.0, 10.0)],
    )
    rolling_repaired = czr005_cpp.rolling_horizon_sipp_from_records(
        node_records,
        edge_records,
        heuristic_time,
        [("repair-after", 404, 404, 12.0, 40.0, 0, 2, 0, 2, 12.0, "direct", False, 4)],
        max_tasks=1,
        horizon_seconds=60.0,
        fault_windows=[(1, 2, 0.0, 10.0)],
    )
    assert rolling_repair_active["summary"]["planned_count"] == 0
    assert rolling_repair_active["summary"]["unplanned_count"] == 1
    assert rolling_repaired["summary"]["planned_count"] == 1
    assert rolling_repaired["summary"]["unplanned_count"] == 0

    periodic_replanning = czr005_cpp.periodic_replanning_sipp_from_records(
        node_records,
        edge_records,
        heuristic_time,
        rolling_task_records,
        max_tasks=2,
        interval_seconds=2.0,
        max_ticks=16,
    )
    assert periodic_replanning["summary"]["planned_count"] == 2
    assert periodic_replanning["summary"]["unplanned_count"] == 0
    assert periodic_replanning["summary"]["replan_count"] >= 2
    assert periodic_replanning["summary"]["peak_active_bags"] >= 1
    assert periodic_replanning["summary"]["post_shield_conflicts"] == 0
    periodic_buffer = czr005_cpp.periodic_replanning_sipp_from_records(
        node_records,
        edge_records,
        heuristic_time,
        [
            ("buffer-first", 407, 407, 0.0, 20.0, 0, 2, 0, 2, 0.0, "direct", False, 7),
            ("buffer-second", 408, 408, 0.0, 20.0, 0, 2, 0, 2, 0.0, "direct", False, 8),
        ],
        max_tasks=2,
        interval_seconds=1.0,
        max_ticks=16,
        edge_capacity=2,
        node_capacities=[(1, 2)],
    )
    assert periodic_buffer["summary"]["planned_count"] == 2
    assert periodic_buffer["summary"]["post_shield_conflicts"] == 0
    periodic_repair = czr005_cpp.periodic_replanning_sipp_from_records(
        node_records,
        edge_records,
        heuristic_time,
        [rolling_task_records[1]],
        max_tasks=1,
        interval_seconds=2.0,
        max_ticks=16,
        fault_windows=[(0, 1, 0.0, 10.0)],
    )
    assert periodic_repair["summary"]["planned_count"] == 1
    assert periodic_repair["summary"]["unplanned_count"] == 0
    assert periodic_repair["summary"]["post_shield_conflicts"] == 0

    parallel_node_records = [
        (0, 1, 0.0, 0, 0, [2]),
        (1, 1, 0.0, 0, 1, [3]),
        (2, 4, 0.0, 1, 0, [4]),
        (3, 4, 0.0, 1, 1, [5]),
        (4, 2, 0.0, 2, 0, []),
        (5, 2, 0.0, 2, 1, []),
    ]
    parallel_edge_records = [
        (0, 2, 5.0, 2.5),
        (1, 3, 5.0, 2.5),
        (2, 4, 5.0, 2.5),
        (3, 5, 5.0, 2.5),
    ]
    parallel_heuristic_time = [
        [0.0, 999.0, 2.0, 999.0, 4.0, 999.0],
        [999.0, 0.0, 999.0, 2.0, 999.0, 4.0],
        [999.0, 999.0, 0.0, 999.0, 2.0, 999.0],
        [999.0, 999.0, 999.0, 0.0, 999.0, 2.0],
        [999.0, 999.0, 999.0, 999.0, 0.0, 999.0],
        [999.0, 999.0, 999.0, 999.0, 999.0, 0.0],
    ]
    parallel_merge_groups = [(0, 2, 7), (1, 3, 7)]
    parallel_tasks = [
        ("merge-left", 601, 601, 0.0, 20.0, 0, 4, 0, 4, 0.0, "direct", False, 1),
        ("merge-right", 602, 602, 0.0, 20.0, 1, 5, 1, 5, 0.0, "direct", False, 2),
    ]
    sipp_merge_route = czr005_cpp.sipp_plan_from_records(
        parallel_node_records,
        parallel_edge_records,
        parallel_heuristic_time,
        start=0,
        goal=4,
        edge_reservations=[(99, 1, 3, 0.0, 2.0)],
        merge_groups=parallel_merge_groups,
        task_id=601,
    )
    assert [row["location"] for row in sipp_merge_route] == [0, 2, 4]
    assert abs(sipp_merge_route[1]["t1"] - 4.0) < 1.0e-9

    rolling_merge = czr005_cpp.rolling_horizon_sipp_from_records(
        parallel_node_records,
        parallel_edge_records,
        parallel_heuristic_time,
        parallel_tasks,
        max_tasks=2,
        horizon_seconds=60.0,
        merge_groups=parallel_merge_groups,
    )
    assert rolling_merge["summary"]["planned_count"] == 2
    assert rolling_merge["summary"]["post_shield_conflicts"] == 0
    assert rolling_merge["events"][1]["finish_time"] >= 6.0

    periodic_merge = czr005_cpp.periodic_replanning_sipp_from_records(
        parallel_node_records,
        parallel_edge_records,
        parallel_heuristic_time,
        parallel_tasks,
        max_tasks=2,
        interval_seconds=1.0,
        max_ticks=16,
        merge_groups=parallel_merge_groups,
    )
    assert periodic_merge["summary"]["planned_count"] == 2
    assert periodic_merge["summary"]["post_shield_conflicts"] == 0

    pibt_parallel_merge = czr005_cpp.pibt_resolve_from_records(
        parallel_node_records,
        parallel_edge_records,
        parallel_heuristic_time,
        [
            (1, 0, 4, 0.0, 10.0, 0.0),
            (2, 1, 5, 0.0, 20.0, 0.0),
        ],
        merge_groups=parallel_merge_groups,
    )
    assert [action["action"] for action in pibt_parallel_merge] == ["move", "hold"]
    assert pibt_parallel_merge[1]["reason"] == "no_safe_edge"

    pibt_parallel_replay = czr005_cpp.pibt_active_bag_replay_from_records(
        parallel_node_records,
        parallel_edge_records,
        parallel_heuristic_time,
        parallel_tasks,
        max_tasks=2,
        interval_seconds=2.0,
        max_ticks=16,
        hold_seconds=2.0,
        merge_groups=parallel_merge_groups,
    )
    assert pibt_parallel_replay["summary"]["planned_count"] == 2
    assert pibt_parallel_replay["summary"]["post_shield_conflicts"] == 0

    pibt_merge_node_records = [
        (0, 1, 0.0, 0, 0, [2]),
        (1, 1, 0.0, 0, 1, [2]),
        (2, 4, 1.0, 1, 0, [3]),
        (3, 2, 0.0, 2, 0, []),
    ]
    pibt_merge_edge_records = [
        (0, 2, 5.0, 2.5),
        (1, 2, 5.0, 2.5),
        (2, 3, 5.0, 2.5),
    ]
    pibt_merge_heuristic_time = [
        [0.0, 4.0, 2.0, 4.0],
        [4.0, 0.0, 2.0, 4.0],
        [4.0, 4.0, 0.0, 2.0],
        [4.0, 4.0, 2.0, 0.0],
    ]
    pibt_merge = czr005_cpp.pibt_resolve_from_records(
        pibt_merge_node_records,
        pibt_merge_edge_records,
        pibt_merge_heuristic_time,
        [
            (1, 0, 3, 0.0, 100.0, 0.0),
            (2, 1, 3, 0.0, 20.0, 0.0),
        ],
    )
    assert [action["task_id"] for action in pibt_merge] == [2, 1]
    assert pibt_merge[0]["action"] == "move"
    assert pibt_merge[0]["next_node"] == 2
    assert pibt_merge[1]["action"] == "hold"
    assert pibt_merge[1]["reason"] == "no_safe_edge"

    pibt_branch_node_records = [
        (0, 1, 0.0, 0, 0, [1, 2]),
        (1, 4, 0.0, 1, 0, [3]),
        (2, 4, 0.0, 1, 1, [3]),
        (3, 2, 0.0, 2, 0, []),
    ]
    pibt_branch_edge_records = [
        (0, 1, 5.0, 2.5),
        (0, 2, 5.0, 2.5),
        (1, 3, 5.0, 2.5),
        (2, 3, 7.5, 2.5),
    ]
    pibt_branch_heuristic_time = [
        [0.0, 2.0, 3.0, 4.0],
        [4.0, 0.0, 4.0, 2.0],
        [4.0, 4.0, 0.0, 3.0],
        [4.0, 2.0, 3.0, 0.0],
    ]
    pibt_branch = czr005_cpp.pibt_resolve_from_records(
        pibt_branch_node_records,
        pibt_branch_edge_records,
        pibt_branch_heuristic_time,
        [(3, 0, 3, 0.0, 20.0, 0.0)],
        fault_edges=[(0, 1)],
    )
    assert len(pibt_branch) == 1
    assert pibt_branch[0]["action"] == "move"
    assert pibt_branch[0]["next_node"] == 2

    pibt_handoff_node_records = [
        (0, 1, 0.0, 0, 0, [1, 2]),
        (1, 4, 0.0, 1, 0, [0, 3]),
        (2, 4, 0.0, 1, 1, [3]),
        (3, 2, 0.0, 2, 0, []),
    ]
    pibt_handoff_edge_records = [
        (0, 1, 5.0, 2.5),
        (0, 2, 7.5, 2.5),
        (1, 0, 5.0, 2.5),
        (1, 3, 5.0, 2.5),
        (2, 3, 5.0, 2.5),
    ]
    pibt_handoff_heuristic_time = [
        [0.0, 2.0, 3.0, 4.0],
        [2.0, 0.0, 5.0, 2.0],
        [999.0, 999.0, 0.0, 2.0],
        [999.0, 999.0, 999.0, 0.0],
    ]
    pibt_handoff = czr005_cpp.pibt_resolve_from_records(
        pibt_handoff_node_records,
        pibt_handoff_edge_records,
        pibt_handoff_heuristic_time,
        [
            (1, 0, 3, 0.0, 10.0, 0.0),
            (2, 1, 3, 0.0, 100.0, 0.0),
        ],
    )
    assert [action["task_id"] for action in pibt_handoff] == [1, 2]
    assert pibt_handoff[0]["next_node"] == 1
    assert pibt_handoff[0]["reason"] == "priority_inheritance"
    assert pibt_handoff[1]["next_node"] == 3
    assert pibt_handoff[1]["reason"] == "inherited_move"

    pibt_replay = czr005_cpp.pibt_active_bag_replay_from_records(
        pibt_handoff_node_records,
        pibt_handoff_edge_records,
        pibt_handoff_heuristic_time,
        [
            ("handoff-high", 1, 1, 0.0, 20.0, 0, 3, 0, 3, 0.0, "direct", False, 1),
            ("handoff-blocker", 2, 2, 0.0, 100.0, 1, 3, 1, 3, 0.0, "direct", False, 2),
        ],
        max_tasks=2,
        interval_seconds=2.0,
        max_ticks=16,
        hold_seconds=2.0,
    )
    assert pibt_replay["summary"]["planned_count"] == 2
    assert pibt_replay["summary"]["post_shield_conflicts"] == 0
    pibt_first_moves = [
        event for event in pibt_replay["events"] if event["event"] == "pibt_move" and event["tick_time"] == 0.0
    ]
    assert [(event["task_id"], event["next_node"], event["reason"]) for event in pibt_first_moves] == [
        (1, 1, "priority_inheritance"),
        (2, 3, "inherited_move"),
    ]

    records_replay = czr005_cpp.edge_score_native_replay_summary_from_records(
        node_records,
        edge_records,
        heuristic_time,
        task_records,
        str(RUNTIME / "phase8_edge_score_runtime_model.txt"),
        max_tasks=2,
        max_decisions_per_task=8,
    )
    assert records_replay["planned_count"] + records_replay["unplanned_count"] == 2
    assert records_replay["decision_count"] > 0
    assert records_replay["post_shield_conflicts"] == 0

    records_event_replay = czr005_cpp.edge_score_native_event_replay_summary_from_records(
        node_records,
        edge_records,
        heuristic_time,
        task_records,
        str(RUNTIME / "phase8_edge_score_runtime_model.txt"),
        max_tasks=2,
        max_decisions_per_task=8,
    )
    assert records_event_replay["planned_count"] + records_event_replay["unplanned_count"] == 2
    assert records_event_replay["decision_count"] > 0
    assert records_event_replay["post_shield_conflicts"] == 0

    records_event_trace = czr005_cpp.edge_score_native_event_replay_trace_from_records(
        node_records,
        edge_records,
        heuristic_time,
        task_records,
        str(RUNTIME / "phase8_edge_score_runtime_model.txt"),
        max_tasks=2,
        max_decisions_per_task=8,
    )
    assert records_event_trace["summary"]["decision_count"] == len(records_event_trace["trace"])
    assert records_event_trace["trace"][0]["decision_ordinal"] == 1
    assert records_event_trace["trace"][0]["candidate_count"] >= records_event_trace["trace"][0]["safe_candidate_count"]

    records_trace = czr005_cpp.edge_score_native_replay_trace_from_records(
        node_records,
        edge_records,
        heuristic_time,
        task_records,
        str(RUNTIME / "phase8_edge_score_runtime_model.txt"),
        max_tasks=1,
        max_decisions_per_task=8,
    )
    assert records_trace["summary"]["decision_count"] == len(records_trace["trace"])
    assert records_trace["trace"][0]["decision_ordinal"] == 1
    assert records_trace["trace"][0]["candidate_count"] >= records_trace["trace"][0]["safe_candidate_count"]

    records_fallback_repair = czr005_cpp.edge_score_native_fallback_replay_summary_from_records(
        node_records,
        edge_records,
        heuristic_time,
        task_records,
        max_tasks=2,
        max_decisions_per_task=4,
        fault_windows=[(0, 1, 0.0, 10.0)],
    )
    assert records_fallback_repair["planned_count"] == 1
    assert records_fallback_repair["unplanned_count"] == 1
    assert records_fallback_repair["post_shield_conflicts"] == 0

    records_event_fallback_repair = czr005_cpp.edge_score_native_event_fallback_replay_summary_from_records(
        node_records,
        edge_records,
        heuristic_time,
        task_records,
        max_tasks=2,
        max_decisions_per_task=4,
        fault_windows=[(0, 1, 0.0, 10.0)],
    )
    assert records_event_fallback_repair["planned_count"] == 1
    assert records_event_fallback_repair["unplanned_count"] == 1
    assert records_event_fallback_repair["post_shield_conflicts"] == 0

    records_event_fallback_trace = czr005_cpp.edge_score_native_event_fallback_replay_trace_from_records(
        node_records,
        edge_records,
        heuristic_time,
        task_records,
        max_tasks=2,
        max_decisions_per_task=4,
        fault_windows=[(0, 1, 0.0, 10.0)],
    )
    assert records_event_fallback_trace["summary"]["decision_count"] == len(records_event_fallback_trace["trace"])
    assert records_event_fallback_trace["summary"]["post_shield_conflicts"] == 0

    merge_buffer_node_records = [
        (0, 1, 0.0, 0, 0, [1]),
        (1, 4, 1.0, 1, 0, [2]),
        (2, 2, 0.0, 2, 0, []),
        (3, 1, 0.0, 0, 1, [1]),
    ]
    merge_buffer_edge_records = [
        (0, 1, 5.0, 2.5),
        (3, 1, 5.0, 2.5),
        (1, 2, 5.0, 2.5),
    ]
    merge_buffer_heuristic_time = [
        [0.0, 2.0, 4.0, 999.0],
        [999.0, 0.0, 2.0, 999.0],
        [999.0, 999.0, 0.0, 999.0],
        [999.0, 2.0, 4.0, 0.0],
    ]
    merge_buffer_tasks = [
        ("left-buffer", 501, 501, 0.0, 30.0, 0, 2, 0, 2, 0.0, "direct", False, 1),
        ("right-buffer", 502, 502, 0.1, 30.0, 3, 2, 3, 2, 0.1, "direct", False, 2),
    ]
    buffer_trace = czr005_cpp.edge_score_native_event_fallback_replay_trace_from_records(
        merge_buffer_node_records,
        merge_buffer_edge_records,
        merge_buffer_heuristic_time,
        merge_buffer_tasks,
        max_tasks=2,
        max_decisions_per_task=8,
        node_capacities=[(1, 2)],
    )
    assert buffer_trace["summary"]["planned_count"] == 2
    assert buffer_trace["summary"]["post_shield_conflicts"] == 0
    assert next(row for row in buffer_trace["trace"] if row["task_id"] == 502)["executed_kind"] == "move"

    merge_trace = czr005_cpp.edge_score_native_event_fallback_replay_trace_from_records(
        merge_buffer_node_records,
        merge_buffer_edge_records,
        merge_buffer_heuristic_time,
        merge_buffer_tasks,
        max_tasks=2,
        max_decisions_per_task=8,
        node_capacities=[(1, 2)],
        merge_groups=[(0, 1, 7), (3, 1, 7)],
    )
    assert merge_trace["summary"]["planned_count"] == 2
    assert merge_trace["summary"]["post_shield_conflicts"] == 0
    assert next(row for row in merge_trace["trace"] if row["task_id"] == 502)["executed_kind"] == "hold"


if __name__ == "__main__":
    main()
