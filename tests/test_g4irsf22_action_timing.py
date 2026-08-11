from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.eval import run_g4irsf22_action_timing as runner


def _candidate(
    *, queue: float = 0.0, calendar_wait: float = 0.0, contention: float = 0.0
) -> dict[str, float]:
    return {
        "target_queue_length": queue,
        "target_wait_after_travel_seconds": calendar_wait,
        "priority_local_contention": contention,
        "target_scheduled_incoming": 0.0,
        "event_time": 0.0,
        "target_next_available": 0.0,
        "travel_time": 1.0,
    }


def _event(
    index: int,
    *,
    runtime_bag_id: int | None = None,
    event_time: float | None = None,
    event_seq: int | None = None,
    current_node: int | None = None,
    queue: float = 0.0,
    calendar_wait: float = 0.0,
    contention: float = 0.0,
    divergence: bool = False,
    legal: list[int] | None = None,
    baseline: int | None = None,
    wait_available: bool = True,
) -> dict[str, object]:
    edges = legal or [10, 11]
    baseline_node = edges[0] if baseline is None else baseline
    time = float(index) if event_time is None else event_time
    row: dict[str, object] = {
        "schema_id": "czr005.g4irsf22.route_census.v1",
        "skeleton_id": f"selection-{index}",
        "population_group_id": f"group-{index}",
        "population_selection_id": f"selection-{index}",
        "kind": "I3_NEXT_EDGE",
        "event_ordinal": index,
        "runtime_bag_id": index if runtime_bag_id is None else runtime_bag_id,
        "event_time": time,
        "event_seq": index if event_seq is None else event_seq,
        "current_node": index if current_node is None else current_node,
        "baseline_next_node": baseline_node,
        "legal_next_edges": edges,
        "wait_available": wait_available,
        "candidate_next_nodes": edges,
        "candidate_observations": [
            _candidate(
                queue=queue + candidate,
                calendar_wait=calendar_wait + candidate,
                contention=contention + candidate,
            )
            for candidate in range(len(edges))
        ],
        "baseline_candidate_index": edges.index(baseline_node),
        "normal_flow": True,
        "s4_v2_divergence": divergence,
    }
    return row


def test_complete_action_contract_preserves_event_identity_and_horizons() -> None:
    row = _event(
        20,
        runtime_bag_id=7,
        event_time=12.5,
        event_seq=91,
        current_node=4,
        legal=[8, 9, 10],
        baseline=9,
    )
    normalized = runner.normalize_route_event(row)
    actions = runner.enumerate_legal_actions(normalized)

    assert actions == [
        {"action_kind": "NEXT_EDGE", "selected_next_node": 8, "is_baseline": False},
        {"action_kind": "NEXT_EDGE", "selected_next_node": 9, "is_baseline": True},
        {"action_kind": "NEXT_EDGE", "selected_next_node": 10, "is_baseline": False},
        {"action_kind": "WAIT", "selected_next_node": None, "is_baseline": False},
    ]

    targets = runner.build_action_targets(
        {**normalized, "timing_stage": "current"},
        horizons=("H_bag", "H_system"),
    )
    assert len(targets) == 6
    assert {target["horizon"] for target in targets} == {"H_bag", "H_system"}
    assert all(target["schema"] == runner.TARGET_SCHEMA for target in targets)
    assert all(target["research_profile"] == "G22_S4_J2_E2" for target in targets)
    assert all(target["runtime_bag_id"] == 7 for target in targets)
    assert all(target["event_time"] == 12.5 for target in targets)
    assert all(target["current_node"] == 4 for target in targets)
    assert all(target["event_seq"] == 91 for target in targets)
    assert all(target["event_identity"] == runner.event_identity(normalized) for target in targets)
    assert not any(target.get("selected_next_node") == 9 for target in targets)
    assert len({runner.target_identity(target) for target in targets}) == 6


def test_wait_is_emitted_only_when_native_row_marks_it_legal() -> None:
    row = _event(3, legal=[10, 11, 12], wait_available=False)
    assert [action["action_kind"] for action in runner.enumerate_legal_actions(row)] == [
        "NEXT_EDGE",
        "NEXT_EDGE",
        "NEXT_EDGE",
    ]
    targets = runner.build_action_targets(row, horizons="H_bag")
    assert len(targets) == 2
    assert all(target["action_kind"] == "NEXT_EDGE" for target in targets)


def test_current_selector_round_robins_strata_and_spreads_node_time_pairs() -> None:
    rows = [
        _event(10, current_node=1, event_time=100.0, queue=100.0),
        _event(20, current_node=2, event_time=1_000.0, calendar_wait=100.0),
        _event(30, current_node=3, event_time=2_000.0, contention=100.0),
        _event(40, current_node=4, event_time=3_000.0, divergence=True),
        _event(50, current_node=5, event_time=4_000.0, queue=1.0),
        _event(60, current_node=6, event_time=5_000.0, calendar_wait=1.0),
    ]
    selected = runner.select_current_groups(
        rows, target_groups=4, time_block_seconds=900.0
    )

    assert [row["event_ordinal"] for row in selected] == [10, 20, 30, 40]
    assert [row["selection_stratum"] for row in selected] == list(
        runner.CURRENT_STRATA
    )
    assert len({row["current_node"] for row in selected}) == 4
    assert len({row["time_block"] for row in selected}) == 4
    assert all(row["event_identity"] == runner.event_identity(row) for row in selected)


def test_current_selector_skips_unsupported_strata_and_prioritizes_score() -> None:
    def queue_only(
        index: int, *, runtime_bag_id: int, score: float, node: int
    ) -> dict[str, object]:
        row = _event(
            index,
            runtime_bag_id=runtime_bag_id,
            current_node=node,
            event_time=float(node * 1_000),
        )
        for candidate in row["candidate_observations"]:
            candidate.update(
                target_queue_length=0.0,
                target_wait_after_travel_seconds=5e-10,
                priority_local_contention=0.0,
                target_scheduled_incoming=0.0,
            )
        row["candidate_observations"][-1]["target_queue_length"] = score
        return row

    rows = [
        queue_only(1, runtime_bag_id=7, score=100.0, node=1),
        queue_only(2, runtime_bag_id=7, score=99.0, node=2),
        queue_only(3, runtime_bag_id=8, score=90.0, node=1),
        queue_only(4, runtime_bag_id=9, score=80.0, node=2),
    ]
    selected, audit = runner.select_current_groups_with_summary(
        rows, target_groups=2, time_block_seconds=900.0
    )

    # The second event cannot reuse runtime bag 7.  Score 90 wins even though
    # the score-80 event would add a new node/time block.
    assert [row["event_ordinal"] for row in selected] == [1, 3]
    assert [row["selection_stratum"] for row in selected] == [
        "high_target_queue",
        "high_target_queue",
    ]
    assert audit["selected_stratum_counts"]["high_target_queue"] == 2
    assert audit["stratum_support_counts"]["high_calendar_wait"] == 0
    assert audit["unsupported_strata"] == [
        "high_calendar_wait",
        "high_merge_contention",
        "s4_v2_divergence_or_near_tie",
    ]
    assert audit["runtime_bag_ids_are_unique"] is True


def test_current_cli_summary_reports_unsupported_strata(tmp_path: Path) -> None:
    row = _event(1, runtime_bag_id=7)
    for candidate in row["candidate_observations"]:
        candidate.update(
            target_queue_length=0.0,
            target_wait_after_travel_seconds=0.0,
            priority_local_contention=0.0,
            target_scheduled_incoming=0.0,
        )
    row["candidate_observations"][-1]["target_queue_length"] = 8.0
    census = tmp_path / "census.jsonl"
    census.write_text(json.dumps(row) + "\n", encoding="utf-8")
    targets = tmp_path / "targets.jsonl"
    summary = tmp_path / "summary.json"

    assert runner.main(
        [
            "--census",
            str(census),
            "--target-groups",
            "4",
            "--h-system-groups",
            "0",
            "--output",
            str(targets),
            "--summary",
            str(summary),
        ]
    ) == 0
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["group_count"] == 1
    assert payload["current_selection"]["selected_stratum_counts"] == {
        "high_target_queue": 1,
        "high_calendar_wait": 0,
        "high_merge_contention": 0,
        "s4_v2_divergence_or_near_tie": 0,
    }
    assert payload["current_selection"]["selection_shortfall"] == 3
    assert payload["current_selection"]["unsupported_strata"] == [
        "high_calendar_wait",
        "high_merge_contention",
        "s4_v2_divergence_or_near_tie",
    ]


def test_precursor_is_nearest_strictly_earlier_event_for_same_runtime_segment() -> None:
    anchor = _event(
        30,
        runtime_bag_id=7,
        event_time=30.0,
        event_seq=30,
        current_node=9,
    )
    anchor["selection_stratum"] = "high_target_queue"
    anchor["time_block"] = 2
    same_bag_early = _event(
        10, runtime_bag_id=7, event_time=10.0, event_seq=10, current_node=1
    )
    same_bag_nearer = _event(
        25, runtime_bag_id=7, event_time=30.0, event_seq=29, current_node=3
    )
    other_runtime_segment = _event(
        29, runtime_bag_id=8, event_time=29.0, event_seq=29, current_node=8
    )
    later_same_bag = _event(
        31, runtime_bag_id=7, event_time=31.0, event_seq=31, current_node=4
    )
    lower_time_but_later_ordinal = _event(
        32, runtime_bag_id=7, event_time=29.0, event_seq=28, current_node=5
    )

    selected = runner.select_precursor_groups(
        [anchor],
        [
            other_runtime_segment,
            same_bag_early,
            later_same_bag,
            lower_time_but_later_ordinal,
            anchor,
            same_bag_nearer,
        ],
    )
    assert len(selected) == 1
    precursor = selected[0]
    assert precursor["runtime_bag_id"] == 7
    assert precursor["event_ordinal"] == 25
    assert precursor["event_seq"] == 29
    assert precursor["event_time"] == 30.0
    assert precursor["timing_stage"] == "precursor"
    assert precursor["anchor_event_identity"] == runner.event_identity(anchor)
    assert precursor["event_identity"] == runner.event_identity(same_bag_nearer)
    assert precursor["precursor_event_gap"] == 5
    assert precursor["precursor_time_gap_seconds"] == 0.0

    targets = runner.build_action_targets(precursor, horizons="H_system")
    assert all(
        target["anchor_event_identity"] == runner.event_identity(anchor)
        for target in targets
    )
    assert all(target["runtime_bag_id"] == 7 for target in targets)
    assert all(target["event_ordinal"] == 25 for target in targets)


def test_precursor_does_not_fall_back_to_another_runtime_segment() -> None:
    anchor = _event(20, runtime_bag_id=7, event_time=20.0)
    same_raw_task_but_other_segment = _event(
        10, runtime_bag_id=8, event_time=10.0
    )
    same_raw_task_but_other_segment["task_id"] = 123
    anchor["task_id"] = 123

    assert (
        runner.select_precursor_groups(
            [anchor], [same_raw_task_but_other_segment, anchor]
        )
        == []
    )


def test_streaming_precursor_selection_keeps_only_nearest_same_segment(
    tmp_path: Path,
) -> None:
    anchor = _event(30, runtime_bag_id=7, event_time=30.0)
    rows = [
        _event(10, runtime_bag_id=7, event_time=10.0),
        _event(29, runtime_bag_id=8, event_time=29.0),
        _event(25, runtime_bag_id=7, event_time=25.0),
        anchor,
    ]
    census = tmp_path / "census.jsonl"
    census.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    selected = runner.select_precursor_groups_from_jsonl([anchor], census)
    assert len(selected) == 1
    assert selected[0]["runtime_bag_id"] == 7
    assert selected[0]["event_ordinal"] == 25


def test_streaming_precursor_supports_multiple_anchors_and_keeps_metadata(
    tmp_path: Path,
) -> None:
    first = _event(30, runtime_bag_id=7, event_time=30.0)
    first.update(
        selection_stratum="high_target_queue",
        selection_score=12.0,
        time_block=2,
    )
    second = _event(50, runtime_bag_id=7, event_time=50.0)
    second.update(
        selection_stratum="high_merge_contention",
        selection_score=9.0,
        time_block=4,
    )
    rows = [
        _event(10, runtime_bag_id=7, event_time=10.0),
        _event(25, runtime_bag_id=7, event_time=25.0),
        first,
        _event(45, runtime_bag_id=7, event_time=45.0),
        second,
    ]
    census = tmp_path / "multi-anchor.jsonl"
    census.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    selected = runner.select_precursor_groups_from_jsonl([first, second], census)
    assert [row["event_ordinal"] for row in selected] == [25, 45]
    assert [row["selection_stratum"] for row in selected] == [
        "high_target_queue",
        "high_merge_contention",
    ]
    assert selected[0]["anchor_selection_metadata"] == {
        "selection_stratum": "high_target_queue",
        "selection_score": 12.0,
        "time_block": 2,
    }
    assert selected[1]["anchor_event_identity"] == runner.event_identity(second)


def test_detour_release_gate_requires_late_current_congestion_and_shorter_alt() -> None:
    row = _event(50, legal=[10, 21], baseline=10)
    row["candidate_observations"][0].update(
        priority_age_seconds=90.0,
        junction_queue_length=12.0,
        travel_time=3.0,
        static_potential=58.0,
        target_queue_length=5.0,
        target_scheduled_incoming=3.0,
    )
    row["candidate_observations"][1].update(
        priority_age_seconds=90.0,
        junction_queue_length=12.0,
        travel_time=14.0,
        static_potential=23.0,
        target_queue_length=17.0,
        target_scheduled_incoming=15.0,
    )
    gate = runner.detour_release_gate(row)
    assert gate is not None
    assert gate["physical_saving_seconds"] == 24.0
    assert gate["target_pressure_increase"] == 24.0

    too_early = copy.deepcopy(row)
    for candidate in too_early["candidate_observations"]:
        candidate["priority_age_seconds"] = 10.0
    assert runner.detour_release_gate(too_early) is None


def test_plan_assigns_hbag_to_all_and_hsystem_to_requested_groups() -> None:
    groups = runner.select_current_groups(
        [_event(index, current_node=index) for index in range(1, 4)],
        target_groups=3,
    )
    plan = runner.build_timing_plan(groups, h_system_groups=2)

    assert plan["counts"] == {
        "group_count": 3,
        "h_bag_group_count": 3,
        "h_system_group_count": 2,
        "target_count": 10,
    }
    assert [group["assigned_horizons"] for group in plan["groups"]] == [
        ["H_bag", "H_system"],
        ["H_bag", "H_system"],
        ["H_bag"],
    ]
    assert all(len(group["legal_actions"]) == 3 for group in plan["groups"])
    assert len({runner.target_identity(target) for target in plan["targets"]}) == 10


def test_normalization_accepts_g20_style_nested_route_observation() -> None:
    row = _event(5)
    nested = copy.deepcopy(row)
    nested["route_observation"] = {
        "candidate_next_nodes": nested.pop("candidate_next_nodes"),
        "candidate_observations": nested.pop("candidate_observations"),
        "baseline_candidate_index": nested.pop("baseline_candidate_index"),
    }
    normalized = runner.normalize_route_event(nested)
    assert normalized["candidate_next_nodes"] == [10, 11]
    assert len(normalized["candidate_observations"]) == 2
    assert normalized["baseline_candidate_index"] == 0


def test_compact_action_groups_keeps_exact_local_future_for_every_action() -> None:
    event = _event(5, legal=[10, 11], baseline=10)
    event["task_id"] = 77
    event["segment_id"] = "77:direct"
    selected = runner.select_current_groups([event], target_groups=1)[0]
    targets = runner.build_action_targets(selected)

    def future(node: int) -> dict:
        return {
            "schema": "czr005.g4irsf22.local_future_summary.v1",
            "observation_node": node,
            "horizons": [],
        }

    pairs = []
    for target in targets:
        wait = target["action_kind"] == "WAIT"
        pairs.append(
            {
                "target_schema": target["schema"],
                "population_group_id": target["population_group_id"],
                "population_selection_id": target["population_selection_id"],
                "event_ordinal": target["event_ordinal"],
                "horizon": target["horizon"],
                "action_kind": target["action_kind"],
                "selected_next_node": target.get("selected_next_node"),
                "pair_status": "ACTION_CHANGED_HORIZON_COMPLETE",
                "same_state_start": True,
                "action_changed": True,
                "pair_complete": True,
                "live_safety_pass": True,
                "direct_completion_delta_seconds": 2.0 if wait else -3.0,
                "baseline": {"local_future_summary": future(10)},
                "treatment": {
                    "local_future_summary": future(5 if wait else 11)
                },
            }
        )

    groups, failures = runner.compact_action_groups(
        [selected], {"pairs": pairs}
    )
    assert failures == []
    assert len(groups) == 1
    assert groups[0]["task_id"] == 77
    assert groups[0]["segment_id"] == "77:direct"
    assert groups[0]["choice_group_id"] == runner.stable_choice_group_id(selected)
    assert [row["utility"] for row in groups[0]["candidates"]] == [0.0, 3.0, -2.0]
    assert [
        row["local_future_summary"]["observation_node"]
        for row in groups[0]["candidates"]
    ] == [10, 11, 5]


def test_stable_choice_group_id_is_cross_panel_stable_and_event_specific() -> None:
    row = {**runner.normalize_route_event(_event(5)), "timing_stage": "current"}
    copied = {**row, "selection_stratum": "another_panel", "time_block": 99}
    other = {**runner.normalize_route_event(_event(6)), "timing_stage": "current"}

    assert runner.stable_choice_group_id(row) == runner.stable_choice_group_id(copied)
    assert runner.stable_choice_group_id(row) != runner.stable_choice_group_id(other)
    assert "event=5" in runner.stable_choice_group_id(row)
    assert "bag=5" in runner.stable_choice_group_id(row)


def test_hsystem_compaction_uses_raw_bag_metrics_and_not_direct_bag_delta() -> None:
    event = _event(5, legal=[10, 11], baseline=10)
    event["task_id"] = 77
    event["segment_id"] = "77:direct"
    selected = runner.select_current_groups([event], target_groups=1)[0]
    plan = runner.build_timing_plan([selected], h_system_groups=1)
    targets = [
        target for target in plan["targets"] if target["horizon"] == "H_system"
    ]

    def raw_metrics(*, treatment: bool) -> dict[str, object]:
        return {
            "comparison_eligible": True,
            "selected_raw_bag_count": 57_012,
            "primary_denominator": "original_entry_time_tth",
            "original_entry_mean_minutes": 9.0 if treatment else 10.0,
            "source_wait_mean_minutes": 1.5 if treatment else 2.0,
            "network_time_mean_minutes": 2.5 if treatment else 3.0,
            "original_entry_median_seconds": 480.0 if treatment else 500.0,
            "original_entry_p95_seconds": 900.0 if treatment else 950.0,
            "original_entry_p99_seconds": 1_200.0 if treatment else 1_300.0,
            "original_entry_max_seconds": 2_000.0 if treatment else 2_200.0,
        }

    pairs = []
    for target in targets:
        pairs.append(
            {
                "population_group_id": target["population_group_id"],
                "population_selection_id": target["population_selection_id"],
                "event_ordinal": target["event_ordinal"],
                "horizon": "H_system",
                "action_kind": target["action_kind"],
                "selected_next_node": target.get("selected_next_node"),
                "pair_status": "ACTION_CHANGED_HORIZON_COMPLETE",
                "same_state_start": True,
                "action_changed": True,
                "pair_complete": True,
                "live_safety_pass": True,
                "formal_hard_gate_evaluated": True,
                "formal_hard_gate_pass": True,
                "hard_gate_pass": True,
                "hard_gate_fail_reasons": [],
                # This deliberately disagrees with the system result.  It must
                # never enter an H_system summary.
                "direct_completion_delta_seconds": 999_999.0,
                "baseline": {"raw_bag_cohort_metrics": raw_metrics(treatment=False)},
                "treatment": {"raw_bag_cohort_metrics": raw_metrics(treatment=True)},
            }
        )

    rows, failures = runner.compact_h_system_groups(
        plan["groups"], {"pairs": pairs}
    )
    assert failures == []
    assert len(rows) == 2
    assert {row["horizon"] for row in rows} == {"H_system"}
    assert len({row["choice_group_id"] for row in rows}) == 1
    assert all(row["formal_and_live_gate_pass"] is True for row in rows)
    delta = rows[0]["raw_bag_metrics_seconds"]["treatment_minus_baseline"]
    assert delta == {
        "mean_total": -60.0,
        "mean_source": -30.0,
        "mean_network": -30.0,
        "median_total": -20.0,
        "p95_total": -50.0,
        "p99_total": -100.0,
        "max_total": -200.0,
    }
    assert "utility" not in rows[0]
    assert "direct_completion_delta_seconds" not in rows[0]


def test_cli_exposes_a_separate_hsystem_output() -> None:
    arguments = runner.parse_args(
        [
            "--output",
            "targets.jsonl",
            "--h-system-output",
            "system.jsonl",
        ]
    )
    assert arguments.dataset_output is None
    assert arguments.h_system_output == Path("system.jsonl")
