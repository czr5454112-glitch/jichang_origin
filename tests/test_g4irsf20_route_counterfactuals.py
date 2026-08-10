from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf20_route_counterfactuals as runner
from scripts.eval import run_g4irsf20_route_learning as learning


FEATURE_NAMES = [
    "event_time",
    "target_queue_length",
    "target_scheduled_incoming",
    "corridor_next_available",
    "target_next_available",
    "travel_time",
    "static_potential",
    "priority_slack_seconds",
    "priority_age_seconds",
    "recent_visit_count",
    "junction_queue_length",
    "junction_next_available_time",
    "priority_local_contention",
    "current_goal_queue_length",
    "target_goal_queue_length",
    "target_goal_scheduled_incoming",
    "current_goal_max_wait",
    "goal_conditioned_differential",
    "estimated_service_rate",
    "service_weighted_pressure",
    "advertised_fault",
    "fault_message_age_seconds",
    "two_hop_queue_pressure",
]


def _observation(age: float) -> dict[str, object]:
    vectors = []
    mapped = []
    for candidate in range(2):
        values = [float(index + candidate) for index in range(len(FEATURE_NAMES))]
        values[8] = age
        values[20] = False
        vectors.append(values)
        mapped.append(dict(zip(FEATURE_NAMES, values, strict=True)))
    return {
        "schema": "czr005.g4irsf20.route_pre_action_observation_set.v1",
        "feature_names": FEATURE_NAMES,
        "candidate_observations": mapped,
        "canonical_candidate_observations": vectors,
        "candidate_next_nodes": [10, 11],
        "baseline_candidate_index": 0,
        "treatment_candidate_index": 1,
        "normal_flow": True,
        "identity_fields_are_trace_only": True,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "runtime_full_astar_call_count": 0,
    }


def _skeleton(index: int, *, with_sidecar: bool = True) -> dict[str, object]:
    return {
        "schema_id": "czr005.g4irsf20.route_census.v1",
        "skeleton_id": f"s{index}",
        "population_group_id": f"pg{index}",
        "population_selection_id": f"s{index}",
        "kind": "I3_NEXT_EDGE",
        "event_ordinal": index * 10,
        "wait_age_seconds": 50.0 if index % 2 == 0 else 5.0,
        "runtime_bag_id": index,
        "baseline_next_node": 10,
        "selected_next_node": 11,
        "legal_next_edges": [10, 11],
        "route_observation": _observation(50.0 if index % 2 == 0 else 5.0)
        if with_sidecar
        else None,
    }


def _branch(delta: float, runtime_bag_id: int, task_id: int) -> dict[str, object]:
    return {
        "horizon_complete": True,
        "blocked": False,
        "stop_reason": "HORIZON_COMPLETE",
        "elapsed_event_count": 7,
        "affected_bag_outcomes": [
            {
                "runtime_bag_id": runtime_bag_id,
                "task_id": task_id,
                "completion_seconds": 100.0 + delta,
            }
        ],
        "cohort_metrics": {"completion_mean_seconds": 100.0 + delta},
        "raw_bag_cohort_metrics": {
            "original_entry_mean_minutes": 10.0 + delta / 60.0
        },
        "invariants": {
            "live_safety_pass": True,
            "formal_hard_gate_pass": True,
            "failed_segment_count": 0,
            "unsafe_entry_count": 0,
            "reservation_conflict_count": 0,
            "unresolved_deadlock_count": 0,
        },
    }


class FakeNative:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self.population = [_skeleton(index) for index in range(8)]

    def g4irsf15_scan_causal_skeletons_from_records(self, *arguments: object) -> dict[str, object]:
        self.calls.append(("scan", str(arguments[-1]), 0))
        return {"census_complete": True, "skeletons": copy.deepcopy(self.population)}

    def g4irsf15_run_causal_target_pairs_from_records(self, *arguments: object) -> dict[str, object]:
        targets = arguments[-2]
        self.calls.append(("pairs", str(arguments[-1]), len(targets)))
        pairs = []
        for target in targets:
            assert set(target) == {
                "schema",
                "population_group_id",
                "population_selection_id",
                "event_ordinal",
                "horizon",
            }
            assert target["schema"] == runner.DEFERRED_TARGET_SCHEMA
            runtime_bag_id = int(str(target["population_selection_id"])[1:])
            screening_false_positive = runtime_bag_id in {1, 5}
            pairs.append(
                {
                    "target_schema": target["schema"],
                    "population_group_id": target["population_group_id"],
                    "population_selection_id": target["population_selection_id"],
                    "descriptor_id": target["population_selection_id"],
                    "target_address_id": target["population_selection_id"],
                    "kind": "I3",
                    "event_ordinal": target["event_ordinal"],
                    "horizon": target["horizon"],
                    "route_observation": (
                        None
                        if screening_false_positive
                        else _observation(
                            50.0 if runtime_bag_id % 2 == 0 else 5.0
                        )
                    ),
                    "resolved_execution_descriptor": (
                        None
                        if screening_false_positive
                        else {
                            "runtime_bag_id": runtime_bag_id,
                            "baseline_next_node": 10,
                            "selected_next_node": 11,
                            "legal_next_edges": [10, 11],
                        }
                    ),
                    "pair_status": (
                        "SCREENING_FALSE_POSITIVE"
                        if screening_false_positive
                        else runner.COMPLETE_STATUS
                    ),
                    "action_changed": not screening_false_positive,
                    "same_state_start": True,
                    "pair_complete": not screening_false_positive,
                    "live_safety_pass": True,
                    "safety_equivalent": not screening_false_positive,
                    "affected_bag_deltas": (
                        []
                        if screening_false_positive
                        else [{"completion_delta_seconds": -2.0}]
                    ),
                    "baseline": (
                        None
                        if screening_false_positive
                        else _branch(0.0, runtime_bag_id, 100 + runtime_bag_id)
                    ),
                    "treatment": (
                        None
                        if screening_false_positive
                        else _branch(-2.0, runtime_bag_id, 100 + runtime_bag_id)
                    ),
                    "false_positive_reason": (
                        "NOT_APPLICABLE_ACTION_PRECONDITION_FAILED"
                        if screening_false_positive
                        else None
                    ),
                }
            )
        return {"pairs": pairs}


def test_fake_native_campaign_uses_g20_profile_and_resumes(tmp_path: Path) -> None:
    native = FakeNative()
    output = tmp_path / "out"
    summary = runner.run_campaign(
        root=tmp_path,
        binary=tmp_path / "unused.pyd",
        output_dir=output,
        target_groups=4,
        long_wait_target=1,
        h_system_target=1,
        long_wait_seconds=30.0,
        workers=1,
        shard_size=3,
        module=native,
        native_arguments=["frozen-input"],
    )

    assert summary["all_targets_met"] is True
    assert summary["screened_candidate_count"] == 6
    assert summary["eligible_pair_count"] == 4
    assert summary["eligible_long_wait_pair_count"] >= 1
    assert summary["eligible_h_system_pair_count"] >= 1
    assert summary["ineligible_pair_count"] == 2
    assert summary["screening_failure_reason_counts"] == {
        "NOT_APPLICABLE_ACTION_PRECONDITION_FAILED": 2
    }
    assert summary["signed_causal_label_counts"] == {
        "BENEFICIAL": 4,
        "NOT_ELIGIBLE": 2,
    }
    assert summary["execution_design"] == {
        "campaign_revision": runner.CAMPAIGN_REVISION,
        "deferred_target_schema": runner.DEFERRED_TARGET_SCHEMA,
        "descriptor_materialization_stage": "SKIPPED",
        "label_scope": "AFFECTED_RUNTIME_SEGMENT_COMPLETION_PRIMARY_PAIR",
        "source_scale": 1,
        "full_legal_action_set_labeled": False,
        "wait_action_labeled": False,
        "screening_oversample": 1.5,
    }
    assert all(call[1] == runner.RESEARCH_PROFILE for call in native.calls)
    assert not any(call[0] == "materialize" for call in native.calls)
    assert [call[0] for call in native.calls].count("pairs") == 2
    rows = runner._read_jsonl(output / "route_counterfactuals.jsonl")
    assert all(
        row["route_observation"]
        and row["baseline_outcome"]
        and row["treatment_outcome"]
        if row["eligible_causal_label"]
        else row["route_observation"] is None
        for row in rows
    )
    assert all("sha256" not in key for row in rows for key in row)
    groups = learning.load_compact_jsonl(
        output / "route_counterfactual_compact.jsonl"
    )
    assert len(groups) == 4
    assert all(group.primary_pair_labeled for group in groups)
    assert not any(group.full_legal_action_set_labeled for group in groups)
    assert not any(group.wait_action_labeled for group in groups)
    assert all(group.s4_index == 0 for group in groups)
    assert all(group.utilities.tolist() == [0.0, 2.0] for group in groups)
    assert all(group.normal_flow is True for group in groups)
    assert len({group.split_group_id for group in groups}) == 4
    h_system = next(
        row
        for row in rows
        if row["eligible_causal_label"] and row["horizon"] == "H_system"
    )
    assert h_system["segment_cohort_completion_mean_delta_seconds"] == -2.0
    assert h_system["raw_bag_system_tth_mean_delta_seconds"] == pytest.approx(-2.0)
    compact_h_system = runner.compact_training_row(h_system)
    assert compact_h_system["label_scope"] == (
        "AFFECTED_RUNTIME_SEGMENT_COMPLETION_PRIMARY_PAIR"
    )
    assert compact_h_system["system_diagnostic_delta_seconds"] == pytest.approx(-2.0)
    assert compact_h_system["system_diagnostic_scope"] == (
        "RAW_BAG_ORIGINAL_ENTRY_TTH_MEAN"
    )
    h_bag = next(
        row
        for row in rows
        if row["eligible_causal_label"] and row["horizon"] == "H_bag"
    )
    compact_h_bag = runner.compact_training_row(h_bag)
    assert compact_h_bag["system_diagnostic_delta_seconds"] is None
    assert compact_h_bag["system_diagnostic_scope"] == "NOT_APPLICABLE_H_BAG"
    same_task = copy.deepcopy(h_system)
    same_task["runtime_bag_id"] += 10_000
    assert runner.compact_training_row(same_task)["split_group"] == (
        compact_h_system["split_group"]
    )

    call_count = len(native.calls)
    # Old completed shards may carry the quota-only long_wait flag. Resume
    # must normalize it from the current planned threshold without rerunning.
    for shard in (output / "shards").glob("*.jsonl"):
        stale_rows = runner._read_jsonl(shard)
        for row in stale_rows:
            row["long_wait"] = False
        runner._atomic_jsonl(shard, stale_rows)
    resumed = runner.run_campaign(
        root=tmp_path,
        binary=tmp_path / "unused.pyd",
        output_dir=output,
        target_groups=4,
        long_wait_target=1,
        h_system_target=1,
        long_wait_seconds=30.0,
        workers=1,
        shard_size=3,
        module=native,
        native_arguments=["frozen-input"],
    )
    assert resumed == summary
    assert len(native.calls) == call_count


def test_legacy_compact_selection_resumes_without_materialization(
    tmp_path: Path,
) -> None:
    native = FakeNative()
    output = tmp_path / "resumed"
    output.mkdir()
    contract = {
        "campaign_revision": runner.CAMPAIGN_REVISION,
        "research_profile": runner.RESEARCH_PROFILE,
        "target_groups": 1,
        "long_wait_target": 1,
        "h_system_target": 1,
        "long_wait_seconds": 30.0,
        "screening_oversample": 1.5,
        "screened_candidate_targets": {
            "groups": 2,
            "long_wait_groups": 2,
            "h_system_groups": 2,
        },
        "shard_size": 1,
    }
    runner._atomic_json(output / "resume_contract.json", contract)
    runner._atomic_json(
        output / "census_summary.json",
        {"i3_census_count": 8, "census_complete": True},
    )
    legacy = {
        "group_index": 0,
        "event_ordinal": 0,
        "wait_age_seconds": 50.0,
        "long_wait": True,
        "planned_horizon": "H_system",
        "skeleton": {
            "schema": "czr005.g4irsf15.causal_skeleton.v1",
            "skeleton_id": "s0",
            "population_group_sha256": "pg0",
            "skeleton_selection_sha256": "s0",
            "kind": "I3",
            "event_ordinal": 0,
        },
    }
    runner._atomic_jsonl(output / "route_selection.jsonl", [legacy])
    summary = runner.run_campaign(
        root=tmp_path,
        binary=tmp_path / "unused.pyd",
        output_dir=output,
        target_groups=1,
        long_wait_target=1,
        h_system_target=1,
        workers=1,
        shard_size=1,
        module=native,
        native_arguments=["frozen-input"],
    )
    assert summary["all_targets_met"] is True
    assert [call[0] for call in native.calls] == ["pairs"]
    exact = runner._read_jsonl(output / "route_counterfactuals.jsonl")[0]
    assert exact["target_identity"] == {
        "schema": runner.DEFERRED_TARGET_SCHEMA,
        "population_group_id": "pg0",
        "population_selection_id": "s0",
        "event_ordinal": 0,
        "horizon": "H_system",
    }


def test_i3_materialized_sidecar_is_required() -> None:
    with pytest.raises(RuntimeError, match="sidecar"):
        runner._route_observation(
            {"route_observation": None},
            context="materialized I3",
        )


def test_default_screening_oversample_maps_formal_targets() -> None:
    assert runner._oversampled_target(5_000, 1.5) == 7_500
    assert runner._oversampled_target(1_000, 1.5) == 1_500
    assert runner._oversampled_target(500, 1.5) == 750
    with pytest.raises(RuntimeError, match="at least 1.0"):
        runner._oversampled_target(5_000, 0.99)


def test_extra_long_wait_selected_outside_quota_is_still_counted() -> None:
    scan = {
        "census_complete": True,
        "skeletons": [_skeleton(index) for index in range(8)],
    }
    selection = runner.select_route_skeletons(
        scan,
        target_groups=3,
        long_wait_target=1,
        h_system_target=1,
        long_wait_seconds=30.0,
    )
    # One long row satisfies the quota, while another enters via the general
    # event-order sample. Both must carry the actual threshold classification.
    assert sum(row["long_wait"] for row in selection) == 2
    stale = copy.deepcopy(selection)
    for row in stale:
        row["long_wait"] = False
    planned = runner.deferred_plan(stale, long_wait_seconds=30.0)
    assert sum(row["long_wait"] for row in planned) == 2


def test_resumed_shard_requires_every_deferred_target_identity_field(
    tmp_path: Path,
) -> None:
    plan = runner.deferred_plan(
        [
            {
                "group_index": 0,
                "event_ordinal": 10,
                "wait_age_seconds": 50.0,
                "long_wait": True,
                "planned_horizon": "H_system",
                "selection": runner._selection_identity(
                    _skeleton(1), context="test census"
                ),
            }
        ]
    )
    target = plan[0]["target"]
    row = {
        "campaign_revision": runner.CAMPAIGN_REVISION,
        "group_index": 0,
        "target_identity": copy.deepcopy(target),
        "route_observation": _observation(50.0),
        "eligible_causal_label": True,
        "pair_status": runner.COMPLETE_STATUS,
    }
    shard = tmp_path / "shard.jsonl"
    runner._atomic_jsonl(shard, [row])
    assert runner._valid_shard(shard, plan) is True

    for field in (
        "schema",
        "population_group_id",
        "population_selection_id",
        "event_ordinal",
        "horizon",
    ):
        tampered = copy.deepcopy(row)
        tampered["target_identity"][field] = f"changed-{field}"
        runner._atomic_jsonl(shard, [tampered])
        assert runner._valid_shard(shard, plan) is False
