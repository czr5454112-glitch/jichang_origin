from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf25_clcr_learning as learning
from scripts.eval import run_g4irsf22_action_timing as g22
from scripts.eval import run_g4irsf25_short_horizon as campaign


def _candidate(
    *,
    queue: int,
    incoming: int,
    travel: float,
    static: float,
    corridor_wait: float = 0.0,
    target_wait: float = 0.0,
    service_pressure: float = 0.0,
    two_hop: int = 0,
) -> dict[str, object]:
    event_time = 100.0
    return {
        "event_time": event_time,
        "target_queue_length": queue,
        "target_scheduled_incoming": incoming,
        "corridor_next_available": event_time + corridor_wait,
        "target_next_available": event_time + travel + target_wait,
        "travel_time": travel,
        "static_potential": static,
        "priority_slack_seconds": 300.0,
        "priority_age_seconds": 25.0,
        "recent_visit_count": 0,
        "junction_queue_length": 4,
        "junction_next_available_time": event_time,
        "priority_local_contention": 0.0,
        "current_goal_queue_length": 2,
        "target_goal_queue_length": 1,
        "target_goal_scheduled_incoming": 0,
        "current_goal_max_wait": 3.0,
        "goal_conditioned_differential": 1.5,
        "estimated_service_rate": 0.5,
        "service_weighted_pressure": service_pressure,
        "advertised_fault": False,
        "fault_message_age_seconds": 0.0,
        "two_hop_queue_pressure": two_hop,
    }


def _event(
    *,
    branch: int = 6,
    baseline: int | None = None,
    event_ordinal: int = 10,
    event_time: float = 100.0,
    pressure: int = 3,
) -> dict[str, object]:
    edges = [int(arm["first_edge"]) for arm in campaign.CORRIDOR_ARMS[branch]]
    baseline = edges[0] if baseline is None else baseline
    candidates = [
        _candidate(
            queue=pressure + index,
            incoming=index,
            travel=2.0 + index,
            static=10.0 - index,
            corridor_wait=float(index),
            target_wait=2.0 * index,
            service_pressure=0.25 + index,
            two_hop=3 + index,
        )
        for index in range(len(edges))
    ]
    for candidate in candidates:
        candidate["event_time"] = event_time
        candidate["corridor_next_available"] = event_time + (
            0.0 if candidate is candidates[0] else 1.0
        )
        candidate["target_next_available"] = (
            event_time
            + float(candidate["travel_time"])
            + (0.0 if candidate is candidates[0] else 2.0)
        )
    return {
        "schema": g22.EVENT_SCHEMA,
        "population_group_id": f"group-{event_ordinal}",
        "population_selection_id": f"selection-{event_ordinal}",
        "event_ordinal": event_ordinal,
        "event_seq": event_ordinal + 1,
        "runtime_bag_id": event_ordinal + 1000,
        "event_time": event_time,
        "current_node": branch,
        "baseline_next_node": baseline,
        "legal_next_edges": edges,
        "wait_available": True,
        "candidate_next_nodes": edges,
        "candidate_observations": candidates,
        "baseline_candidate_index": edges.index(baseline),
        "task_id": event_ordinal,
        "segment_id": f"{event_ordinal}:storage_in",
        "start": 3,
        "goal": 47,
        "source": "node_3",
        "normal_flow": True,
        "wait_age_seconds": 25.0,
    }


def _short_summary(*, private: float, local: float, timeout: bool = False) -> dict[str, object]:
    return {
        "schema": "czr005.g4irsf25.short_horizon_branch.v1",
        "observed_seconds": 600.0 if timeout else 30.0,
        "private_cost_seconds": private,
        "local_system_cost": local,
        "local_system_cost_units": "BAG_SECONDS_QUEUE_PLUS_SCHEDULED_INCOMING",
        "safety_pass": True,
        "timeout": timeout,
        "rejoin_arrived": not timeout,
        "settle_complete": not timeout,
        "coverage_complete": True,
        "queue_area_bag_seconds": local * 0.6,
        "scheduled_incoming_area_bag_seconds": local * 0.4,
        "local_backlog_at_horizon": 2,
        "peak_local_backlog": 5,
        "affected_bag_completed": False,
        "stop_reason": "G25_MAX_HORIZON_TIMEOUT" if timeout else "G25_REJOIN_SETTLED",
    }


def _pair(target: dict[str, object], *, timeout: bool = False) -> dict[str, object]:
    return {
        "target_schema": target["schema"],
        "population_group_id": target["population_group_id"],
        "population_selection_id": target["population_selection_id"],
        "event_ordinal": target["event_ordinal"],
        "horizon": target["horizon"],
        "action_kind": target["action_kind"],
        "selected_next_node": target["selected_next_node"],
        "g4irsf25_rejoin_node": target["g4irsf25_rejoin_node"],
        "g4irsf25_corridor_nodes": target["g4irsf25_corridor_nodes"],
        "g4irsf25_settle_seconds": target["g4irsf25_settle_seconds"],
        "g4irsf25_max_horizon_seconds": target[
            "g4irsf25_max_horizon_seconds"
        ],
        "same_state_start": True,
        "action_changed": True,
        "pair_complete": True,
        "pair_status": "ACTION_CHANGED_HORIZON_COMPLETE",
        "baseline": {
            "elapsed_event_count": 120,
            "g4irsf25_short_horizon": _short_summary(private=12.0, local=50.0)
        },
        "treatment": {
            "elapsed_event_count": 125,
            "g4irsf25_short_horizon": _short_summary(
                private=600.0 if timeout else 10.0,
                local=600.0 if timeout else 35.0,
                timeout=timeout,
            )
        },
    }


def test_real_corridor_contract_has_two_arms_and_expected_unions() -> None:
    assert set(campaign.CORRIDOR_ARMS) == {6, 9, 16, 19}
    assert campaign.corridor_union_nodes(6) == [6, 8, 11, 13, 12, 23]
    assert campaign.corridor_union_nodes(9) == [9, 7, 8, 11, 14, 10, 15, 46]
    assert campaign.corridor_union_nodes(16) == [16, 17, 18, 22, 24, 21, 23, 27]
    assert campaign.corridor_union_nodes(19) == [19, 18, 22, 26, 25, 43]
    assert all(
        int(arm["rejoin_outgoing_nodes"][0]) in arm["corridor_nodes"]
        for arms in campaign.CORRIDOR_ARMS.values()
        for arm in arms
    )


def test_scan_accepts_only_complete_live_safe_1x_shape_mismatch() -> None:
    row = _event(branch=6)
    row["kind"] = "I3"

    class Backend:
        def g4irsf15_scan_causal_skeletons_from_records(self, *_: object) -> dict[str, object]:
            return {
                "census_complete": False,
                "protected_full_1x_shape": True,
                "terminal_finalized": True,
                "profile_expected_full_shape": False,
                "terminal_invariants": {
                    "live_safety_pass": True,
                    "hard_gate_fail_reasons": [
                        "PROFILE_EXPECTED_FULL_SHAPE_MISMATCH"
                    ],
                    "event_limit_reached": False,
                    "time_limit_reached": False,
                },
                "skeletons": [row, {**row, "node": 5, "current_node": 5}],
            }

    assert campaign.scan_scale(Backend(), []) == [row]

    class UnsafeBackend(Backend):
        def g4irsf15_scan_causal_skeletons_from_records(self, *_: object) -> dict[str, object]:
            payload = super().g4irsf15_scan_causal_skeletons_from_records()
            payload["terminal_invariants"]["live_safety_pass"] = False  # type: ignore[index]
            return payload

    with pytest.raises(campaign.ShortHorizonCampaignError, match="did not complete"):
        campaign.scan_scale(UnsafeBackend(), [])


def test_selection_balances_branch_time_and_pressure_deterministically() -> None:
    rows = []
    ordinal = 0
    for branch in campaign.CORRIDOR_ARMS:
        for index in range(12):
            rows.append(
                _event(
                    branch=branch,
                    event_ordinal=ordinal,
                    event_time=100.0 + index * 50.0,
                    pressure=index,
                )
            )
            ordinal += 1

    first = campaign.select_balanced_checkpoints(rows, target=16, load_scale=2)
    second = campaign.select_balanced_checkpoints(list(reversed(rows)), target=16, load_scale=2)

    assert [row["event_ordinal"] for row in first] == [
        row["event_ordinal"] for row in second
    ]
    assert {branch: sum(row["current_node"] == branch for row in first) for branch in campaign.CORRIDOR_ARMS} == {
        6: 4,
        9: 4,
        16: 4,
        19: 4,
    }
    assert all(row["source_scale"] == 2 for row in first)
    assert all("time=q" in str(row["selection_stratum"]) for row in first)


def test_selection_keeps_only_earliest_bag_branch_event_without_losing_tail() -> None:
    rows = []
    ordinal = 0
    for branch in campaign.CORRIDOR_ARMS:
        for index in range(4):
            row = _event(
                branch=branch,
                event_ordinal=ordinal,
                event_time=100.0 + index * 100.0,
                pressure=index,
            )
            if branch == 6 and index == 0:
                row["runtime_bag_id"] = 777
            rows.append(row)
            ordinal += 1

    repeated_wakeup = _event(
        branch=6,
        event_ordinal=999,
        event_time=10_000.0,
        pressure=99,
    )
    repeated_wakeup["runtime_bag_id"] = 777

    eligible = campaign.eligible_corridor_events(
        [repeated_wakeup, rows[0]]
    )
    assert [row["event_ordinal"] for row in eligible] == [0]

    without_repeat = campaign.select_balanced_checkpoints(
        rows, target=16, load_scale=2
    )
    with_repeat = campaign.select_balanced_checkpoints(
        [repeated_wakeup, *reversed(rows)], target=16, load_scale=2
    )

    # A later wakeup for the same bag/branch is not a second first-edge
    # decision.  It must neither perturb the deterministic strata nor evict
    # the genuine late-time row from another bag.
    assert [row["event_ordinal"] for row in with_repeat] == [
        row["event_ordinal"] for row in without_repeat
    ]
    assert 999 not in {row["event_ordinal"] for row in with_repeat}
    assert any(
        row["current_node"] == 6 and row["event_time"] == 400.0
        for row in with_repeat
    )


def test_plan_targets_only_non_s4_corridor_arm_with_bounded_horizon() -> None:
    selected = campaign.select_balanced_checkpoints(
        [_event(branch=6)], target=1, load_scale=1
    )
    plan = campaign.build_pair_plan(selected)

    assert len(plan) == 1
    assert len(plan[0]["targets"]) == 1
    target = plan[0]["targets"][0]
    assert target["schema"] == g22.TARGET_SCHEMA
    assert target["action_kind"] == "NEXT_EDGE"
    assert target["selected_next_node"] == 12
    assert target["g4irsf25_rejoin_node"] == 13
    assert target["g4irsf25_corridor_nodes"] == [6, 8, 11, 13, 12, 23]
    assert target["g4irsf25_settle_seconds"] == 30.0
    assert target["g4irsf25_max_horizon_seconds"] == 600.0


def test_feature_vector_matches_21d_runtime_order_without_future_feedback() -> None:
    event = _event(branch=6)
    vector = campaign.build_feature_vector(event, edge=12, support=3996)

    assert tuple(vector) == learning.FEATURE_NAMES
    assert len(vector) == 21
    # Static+travel cancel.  Queue(+1), incoming(+1), corridor(+1) and
    # target-wait(+2) make the alternative S4 score five seconds larger.
    assert vector["s4_score_delta"] == pytest.approx(5.0)
    assert vector["target_queue_delta"] == 1.0
    assert vector["target_scheduled_incoming_delta"] == 1.0
    assert vector["corridor_wait_delta"] == 1.0
    assert vector["target_wait_delta"] == 2.0
    assert vector["current_bag_age_seconds"] == 25.0
    assert vector["deadline_headroom_seconds"] == 300.0
    assert vector["recent_corridor_short_ewma_seconds"] == 0.0
    assert vector["recent_corridor_long_ewma_seconds"] == 0.0
    assert vector["recent_corridor_trend_seconds"] == 0.0
    assert vector["recent_corridor_feedback_age_seconds"] == 600.0
    assert vector["recent_corridor_feedback_sample_log1p"] == 0.0
    assert vector["recent_corridor_timeout_rate"] == 0.0


def test_compaction_emits_learning_schema_and_retains_timeout() -> None:
    selected = campaign.select_balanced_checkpoints(
        [_event(branch=6)], target=1, load_scale=1
    )
    plan = campaign.build_pair_plan(selected)
    target = plan[0]["targets"][0]
    compact, failures = campaign.compact_pairs(plan, [_pair(target, timeout=True)])

    assert failures == []
    assert len(compact) == 1
    group = compact[0]
    assert group["schema"] == learning.PAIR_SCHEMA
    assert group["s4_first_edge"] == 8
    assert group["identity_metadata"]["identity_fields_are_trace_only"] is True
    assert group["feature_provenance"]["future_outcomes_used"] is False
    assert len(group["arms"]) == 2
    baseline, treatment = group["arms"]
    assert baseline["timeout"] is False
    assert treatment["timeout"] is True
    assert treatment["private_cost_seconds"] == 600.0
    assert treatment["local_system_cost_seconds"] == 600.0
    assert treatment["local_system_delta_vs_s4"] == 550.0
    assert baseline["elapsed_event_count"] == 120
    assert treatment["elapsed_event_count"] == 125

    # It is directly consumable by the only G25 learning pipeline.
    normalized = learning.normalise_paired_rows(compact)
    assert len(normalized) == 1
    assert normalized[0]["arms"][1]["timeout"] is True


def test_incomplete_native_pair_is_reported_not_silently_dropped() -> None:
    selected = campaign.select_balanced_checkpoints(
        [_event(branch=6)], target=1, load_scale=1
    )
    plan = campaign.build_pair_plan(selected)
    target = plan[0]["targets"][0]
    pair = _pair(target)
    pair["pair_complete"] = False
    pair["pair_status"] = "ACTION_CHANGED_HORIZON_BLOCKED"

    compact, failures = campaign.compact_pairs(plan, [pair])

    assert compact == []
    assert len(failures) == 1
    assert failures[0]["reasons"] == [
        "edge=12:ACTION_CHANGED_HORIZON_BLOCKED"
    ]


def test_successful_oversample_is_rebalanced_instead_of_dropping_time_tail() -> None:
    groups = []
    for time_bin in range(4):
        for pressure_bin in range(4):
            groups.append(
                {
                    "checkpoint_id": f"cp-t{time_bin}-p{pressure_bin}",
                    "checkpoint_time_seconds": float(time_bin * 100 + pressure_bin),
                    "branch_node": 6,
                    "selection_metadata": {
                        "time_quantile": time_bin,
                        "pressure_quantile": pressure_bin,
                    },
                }
            )

    selected = campaign.select_balanced_successes(groups, target=4)

    # A chronological prefix would be q0/q0..q3 and contain no late-time
    # checkpoint.  The diagonal round robin covers every time and pressure
    # quantile before taking a second row from either dimension.
    assert {
        row["selection_metadata"]["time_quantile"] for row in selected
    } == {0, 1, 2, 3}
    assert {
        row["selection_metadata"]["pressure_quantile"] for row in selected
    } == {0, 1, 2, 3}
    assert any(row["checkpoint_time_seconds"] >= 300.0 for row in selected)


def test_resumable_shard_requires_same_targets_and_binary_stamp(tmp_path: Path) -> None:
    target = campaign.build_pair_plan(
        campaign.select_balanced_checkpoints(
            [_event(branch=6)], target=1, load_scale=1
        )
    )[0]["targets"][0]
    path = tmp_path / "shard.json"
    payload = {
        "campaign_revision": campaign.CAMPAIGN_REVISION,
        "binary": {"name": "x.pyd", "size": 10, "mtime_ns": 20},
        "target_keys": [campaign._target_key_list(target)],
        "pairs": [_pair(target)],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert campaign._read_shard(
        path,
        expected_keys=[campaign._target_key_list(target)],
        binary_stamp=payload["binary"],
    ) is not None
    assert campaign._read_shard(
        path,
        expected_keys=[campaign._target_key_list(target)],
        binary_stamp={"name": "x.pyd", "size": 11, "mtime_ns": 20},
    ) is None


def test_semantic_target_key_changes_with_short_horizon_contract() -> None:
    target = campaign.build_pair_plan(
        campaign.select_balanced_checkpoints(
            [_event(branch=6)], target=1, load_scale=1
        )
    )[0]["targets"][0]
    changed = dict(target)
    changed["g4irsf25_max_horizon_seconds"] = 60.0

    assert campaign._target_key_list(target) != campaign._target_key_list(changed)


def test_infrastructure_wall_timeout_is_explicitly_ineligible() -> None:
    target = campaign.build_pair_plan(
        campaign.select_balanced_checkpoints(
            [_event(branch=6)], target=1, load_scale=1
        )
    )[0]["targets"][0]
    pair = campaign._wall_timeout_pair(target, 12.5)

    assert pair["pair_complete"] is False
    assert pair["pair_status"] == "G25_SHARD_WALL_TIMEOUT"
    assert campaign._pair_failure(pair) == (
        "G25_SHARD_WALL_TIMEOUT_AFTER_12.5_SECONDS"
    )
    assert campaign._target_key_list(pair) == campaign._target_key_list(target)
