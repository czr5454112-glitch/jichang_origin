from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from czr005.g4irsf17.features import (
    CANDIDATE_FEATURES,
    CANONICAL_OBSERVATION_FEATURES,
    CONTEXT_FEATURES,
    PAIRWISE_FEATURES,
    pairwise_feature_vector,
)
from czr005.g4irsf17.training import load_effect_feature_rows, train_phase_d
from scripts.eval import g4irsf17_campaign as campaign


def _bag(
    task_id: int,
    *,
    source: float,
    network: float,
    tth: float | None = None,
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "source_wait_seconds": source,
        "network_time_seconds": network,
        "total_system_time_seconds": source + network if tth is None else tth,
        "complete": True,
    }


def _wait(
    task_id: int,
    reason: str,
    seconds: float,
    *,
    arm: str = "h5",
    source: int = 1,
    blocker: int = 20,
    hour: int = 8,
    leg: str = "direct",
) -> dict[str, object]:
    return {
        "arm": arm,
        "task_id": task_id,
        "runtime_bag_id": task_id * 10,
        "segment_id": f"{task_id}:{leg}",
        "reason": reason,
        "source_node": source,
        "blocker_node": blocker,
        "blocker_resource": f"node:{blocker}",
        "source_queue_generation": 7,
        "wait_start_time": hour * 3600.0,
        "wait_end_time": hour * 3600.0 + seconds,
        "event_time": hour * 3600.0,
        "wait_seconds": seconds,
        "admitted": False,
        "held": True,
        "leg_type": leg,
    }


def test_source_wait_diagnosis_uses_matched_signs_and_native_reasons(
    tmp_path: Path,
) -> None:
    off = [
        _bag(1, source=1.0, network=20.0),
        _bag(2, source=1.0, network=20.0),
        _bag(3, source=2.0, network=20.0),
    ]
    h5 = [
        _bag(1, source=5.0, network=18.0),  # +4 local, -2 network
        _bag(2, source=9.0, network=17.0),  # +8 downstream, -3 network
        _bag(3, source=1.0, network=20.0),  # -1 source improvement
    ]
    telemetry = [
        _wait(1, "SOURCE_SERVICE_NOT_READY", 5.0, source=1),
        _wait(2, "DESTINATION_MERGE_TOKEN", 9.0, source=2, blocker=40),
    ]
    off_telemetry = [
        _wait(1, "SOURCE_SERVICE_NOT_READY", 1.0, arm="off", source=1),
        _wait(2, "DESTINATION_MERGE_TOKEN", 1.0, arm="off", source=2, blocker=40),
    ]

    result = campaign.run_source_wait_diagnosis(
        root=tmp_path,
        telemetry_rows=telemetry,
        off_telemetry_rows=off_telemetry,
        h5_bag_rows=h5,
        off_bag_rows=off,
    )

    summary = result["summary"]
    assert summary["source_wait_delta_mean_seconds_per_raw_bag"] == pytest.approx(11.0 / 3.0)
    assert summary["network_time_delta_mean_seconds_per_raw_bag"] == pytest.approx(-5.0 / 3.0)
    assert summary["source_local_orderable_share"] == pytest.approx(1.0 / 3.0)
    assert summary["downstream_backpressure_share"] == pytest.approx(2.0 / 3.0)
    assert summary["same_bag_network_improvement_source_regression_count"] == 2
    assert summary["pivot_decision"] == "I1_BOUNDED_PILOT_AND_START_G2"
    assert (tmp_path / campaign.SOURCE_WAIT_LEDGER_PATH).is_file()
    assert (tmp_path / campaign.SOURCE_WAIT_TOPOLOGY_PATH).is_file()
    report = (tmp_path / campaign.SOURCE_WAIT_REPORT_PATH).read_text(encoding="utf-8")
    assert "treatment" not in report.lower() or "H5" in report
    assert "I1_BOUNDED_PILOT_AND_START_G2" in report
    assert "## Publication boundary" in report
    assert "intentionally excluded from the repository release" in report
    assert "g4irsf17_source_wait_cause_ledger.csv" in report
    assert "g4irsf17_source_wait_topology_attribution.csv" in report


def test_source_wait_diagnosis_never_guesses_a_blocked_reason() -> None:
    with pytest.raises(campaign.CampaignError, match="explicit source-wait reason"):
        campaign.diagnose_source_wait(
            [{"task_id": 1, "blocked": True, "wait_seconds": 3.0}],
            [_bag(1, source=3.0, network=1.0)],
            [_bag(1, source=0.0, network=1.0)],
        )


def test_native_interval_payload_uses_wait_bag_seconds_and_selected_aliases(
    tmp_path: Path,
) -> None:
    payload = {
        "g4irsf17_source_wait_blockers": [
            {
                "interval_ordinal": 1,
                "reason": "DESTINATION_QUEUE_CAPACITY",
                "reason_precedence": 3,
                "source_node": 4,
                "blocker_node": 9,
                "blocker_resource": "node:9",
                "source_generation": 11,
                "blocker_generation": 5,
                "wait_start_time": 100.0,
                "wait_end_time": 102.0,
                "wait_seconds": 2.0,
                "affected_bag_count": 2,
                "wait_bag_seconds": 4.0,
                "selected_task_id": 1,
                "selected_runtime_bag_id": 10,
                "selected_segment_id": "1:direct",
            }
        ]
    }
    telemetry_path = tmp_path / "native.json"
    telemetry_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = campaign.read_rows(telemetry_path)
    result = campaign.run_source_wait_diagnosis(
        root=tmp_path,
        telemetry_rows=rows,
        h5_bag_rows=[
            _bag(1, source=3.0, network=1.0),
            _bag(2, source=1.0, network=1.0),
        ],
        off_bag_rows=[
            _bag(1, source=0.0, network=1.0),
            _bag(2, source=0.0, network=1.0),
        ],
    )

    assert result["summary"]["telemetry_positive_wait_coverage"] == pytest.approx(1.0)
    assert result["summary"]["downstream_backpressure_share"] == pytest.approx(1.0)
    assert result["summary"]["telemetry_attribution_scope"] == (
        "aggregate_native_cell_positive_delta_reconciliation"
    )
    assert result["ledger"][0]["h5_native_wait_seconds"] == pytest.approx(4.0)
    assert result["ledger"][0]["affected_bag_count"] == 2
    assert result["ledger"][0]["attribution_scope"] == "aggregate_native_cell"
    assert all(row["matched_bag_count"] is None for row in result["topology"])
    report = (tmp_path / campaign.SOURCE_WAIT_REPORT_PATH).read_text(
        encoding="utf-8"
    )
    assert "aggregate native cells" in report
    assert "not per-bag causal attribution" in report
    assert "distributes each bag's measured" not in report


def _target(index: int) -> dict[str, object]:
    baseline = index * 10
    source = index % 4
    hour = 6 + index % 4
    queue = 2 + (index % 6) * 7
    leg = ("direct", "storage_in", "storage_out")[index % 3]
    slack = ("tight", "medium", "ample")[index % 3]
    descriptor = f"descriptor-{index:03d}"
    return {
        "schema": "czr005.g4irsf15.causal_target_address.v1",
        "kind": "I1",
        "descriptor_id": descriptor,
        "target_address_id": descriptor,
        "event_ordinal": 1000 + index,
        "event_time": hour * 3600.0,
        "event_hour_floor": hour,
        "node": source,
        "runtime_bag_id": baseline,
        "peer_runtime_bag_id": baseline + 1,
        "source_ready_order": [baseline, baseline + 1, baseline + 2],
        "candidate_action_count": 2,
        "queued_bag_count": queue,
        "deadline": hour * 3600.0 + (100.0 if slack == "tight" else 600.0 if slack == "medium" else 1800.0),
        "segment_id": f"{index}:{leg}",
        "offline_sampling_metadata": {
            "source_node": source,
            "deadline_slack_bucket": slack,
            "bag_class": leg,
        },
        "target_address_sha256_by_horizon": {
            "H_bag": f"hbag-{index}",
            "H_system": f"hsystem-{index}",
        },
    }


def test_i1_selection_requires_live_top2_and_spreads_strata() -> None:
    rows = [_target(index) for index in range(24)]
    false_positive = _target(99)
    false_positive["peer_runtime_bag_id"] = 999_999
    rows.append(false_positive)

    targets, summary = campaign.select_i1_pilot_targets(
        rows,
        h_bag_count=12,
        h_system_count=4,
    )

    h_bag = [row for row in targets if row["horizon"] == "H_bag"]
    h_system = [row for row in targets if row["horizon"] == "H_system"]
    assert len(h_bag) == 12
    assert len(h_system) == 4
    assert summary["real_competitive_i1_count"] == 24
    assert summary["pilot_scale_gate_pass"] is False  # fixture scale is explicit
    assert len(summary["coverage"]["source"]) == 4
    assert len(summary["coverage"]["time"]) == 4
    assert len(summary["coverage"]["leg"]) == 3
    for row in targets:
        assert row["runtime_bag_id"] == row["source_ready_order"][0]
        assert row["peer_runtime_bag_id"] == row["source_ready_order"][1]
        assert row["target_address_sha256"] == row["target_address_sha256_by_horizon"][row["horizon"]]


def _invariants() -> dict[str, object]:
    return {
        "live_safety_pass": True,
        "unsafe_entry_count": 0,
        "reservation_conflict_count": 0,
        "runtime_full_astar_call_count": 0,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "teacher_input_count": 0,
        "two_step_reservation_count": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
    }


def _outcome(runtime_id: int, completion: float, source_wait: float) -> dict[str, object]:
    return {
        "runtime_bag_id": runtime_id,
        "task_id": runtime_id,
        "segment_id": f"{runtime_id}:direct",
        "completion_seconds": completion,
        "source_wait_seconds": source_wait,
        "network_time_seconds": completion - source_wait,
        "finish_time": 1_000.0 + completion,
        "deadline": 10_000.0,
        "completed": True,
        "failed": False,
    }


def _native_observation_pair() -> dict[str, object]:
    context = {name: 0.0 for name in CONTEXT_FEATURES}
    context.update(
        {
            "source_queue_length": 2.0,
            "source_queue_capacity": 8.0,
            "source_queue_utilization": 0.25,
            "source_queue_generation_delta": 1.0,
            "release_count_10s": 2.0,
            "release_count_30s": 2.0,
            "release_count_60s": 2.0,
            "first_edge_credit_slack_seconds": 5.0,
            "target_queue_length": 1.0,
            "target_queue_capacity": 8.0,
            "target_queue_utilization": 0.125,
            "estimated_service_rate_60s": 1.0,
            "service_weighted_pressure": 1.0,
        }
    )
    baseline_candidate = {
        "candidate_local_rank": 0.0,
        "candidate_deadline_slack_seconds": 100.0,
        "candidate_wait_age_seconds": 5.0,
        "candidate_leg_priority": 0.0,
        "candidate_repair_priority": 0.0,
        "deadline_slack_delta_to_baseline_seconds": 0.0,
        "wait_age_delta_to_baseline_seconds": 0.0,
        "leg_priority_delta_to_baseline": 0.0,
        "urgency_delta_to_granted_seconds": 0.0,
        "wait_delta_to_granted_seconds": 0.0,
    }
    treatment_candidate = {
        "candidate_local_rank": 1.0,
        "candidate_deadline_slack_seconds": 50.0,
        "candidate_wait_age_seconds": 10.0,
        "candidate_leg_priority": 1.0,
        "candidate_repair_priority": 0.0,
        "deadline_slack_delta_to_baseline_seconds": -50.0,
        "wait_age_delta_to_baseline_seconds": 5.0,
        "leg_priority_delta_to_baseline": 1.0,
        "urgency_delta_to_granted_seconds": 50.0,
        "wait_delta_to_granted_seconds": 5.0,
    }
    baseline = {**baseline_candidate, **context}
    treatment = {**treatment_candidate, **context}
    canonical = [
        [candidate[name] for name in CANONICAL_OBSERVATION_FEATURES]
        for candidate in (baseline, treatment)
    ]
    return {
        "schema": "czr005.g4irsf17.i1_pre_action_observation_pair.v1",
        "feature_names": list(CANONICAL_OBSERVATION_FEATURES),
        "pairwise_feature_names": list(PAIRWISE_FEATURES),
        "candidate_observations": [baseline, treatment],
        "canonical_candidate_observations": canonical,
        "baseline_observation": baseline,
        "treatment_observation": treatment,
        "baseline_candidate_index": 0,
        "treatment_candidate_index": 1,
        "pairwise_features": pairwise_feature_vector(
            treatment_candidate,
            baseline_candidate,
            context,
        ).tolist(),
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "runtime_full_astar_call_count": 0,
        "identity_fields_are_trace_only": True,
    }


def _pair_for_target(
    target: dict[str, object],
    *,
    horizon: str | None = None,
    external_deltas: list[tuple[int, float]] | None = None,
) -> dict[str, object]:
    horizon = horizon or str(target["horizon"])
    first = int(target["runtime_bag_id"])
    second = int(target["peer_runtime_bag_id"])
    baseline_rows = [_outcome(first, 100.0, 20.0), _outcome(second, 100.0, 10.0)]
    treatment_rows = [_outcome(first, 90.0, 15.0), _outcome(second, 104.0, 12.0)]
    baseline: dict[str, object] = {
        "affected_bag_outcomes": baseline_rows,
        "invariants": _invariants(),
    }
    treatment: dict[str, object] = {
        "affected_bag_outcomes": treatment_rows,
        "invariants": _invariants(),
    }
    if horizon == "H_system":
        baseline["raw_bag_cohort_metrics"] = {
            "original_entry_mean_minutes": 2.0,
            "source_wait_mean_minutes": 0.5,
            "network_time_mean_minutes": 1.5,
            "original_entry_p95_seconds": 200.0,
            "original_entry_p99_seconds": 300.0,
        }
        treatment["raw_bag_cohort_metrics"] = {
            "original_entry_mean_minutes": 2.1,
            "source_wait_mean_minutes": 0.4,
            "network_time_mean_minutes": 1.7,
            "original_entry_p95_seconds": 201.0,
            "original_entry_p99_seconds": 299.0,
        }
    realized = [
        {"runtime_bag_id": first, "completion_delta_seconds": -10.0},
        {"runtime_bag_id": second, "completion_delta_seconds": 4.0},
    ]
    realized.extend(
        {"runtime_bag_id": runtime_id, "completion_delta_seconds": delta}
        for runtime_id, delta in (external_deltas or [])
    )
    return {
        "target_key": f"{target['descriptor_id']}:{horizon}",
        "descriptor_id": target["descriptor_id"],
        "kind": "I1",
        "horizon": horizon,
        "event_ordinal": target["event_ordinal"],
        "action_changed": True,
        "same_state_start": True,
        "horizon_complete": True,
        "pair_complete": True,
        "hard_gate_pass": True,
        "direct_affected_runtime_bag_ids": [first, second],
        "baseline": baseline,
        "treatment": treatment,
        "realized_outcome_deltas": realized if horizon == "H_system" else None,
        "observation_pair": _native_observation_pair(),
    }


def test_i1_effect_sign_externality_and_cvar_are_exact() -> None:
    target = campaign._with_horizon(_target(1), "H_system")
    pair = _pair_for_target(
        target,
        horizon="H_system",
        external_deltas=[(900, 2.0), (901, 30.0), (902, -5.0)],
    )

    result = campaign.analyse_i1_pairs(
        [{"target": target, "pair": pair}],
        targets=[target],
    )
    effect = result["effects"][0]

    assert effect["own_bag_tth_delta_seconds"] == pytest.approx(-10.0)
    assert effect["peer_bag_tth_delta_seconds"] == pytest.approx(4.0)
    assert effect["direct_bag_tth_sum_delta_seconds"] == pytest.approx(-6.0)
    assert effect["other_bag_sum_delta_seconds"] == pytest.approx(27.0)
    assert effect["other_bag_max_harm_seconds"] == pytest.approx(30.0)
    assert effect["other_bag_cvar95_harm_seconds"] == pytest.approx(30.0)
    assert effect["raw_bag_mean_tth_delta_seconds"] == pytest.approx(6.0)
    assert effect["raw_bag_mean_source_wait_delta_seconds"] == pytest.approx(-6.0)
    assert effect["system_cost_delta_seconds"] == pytest.approx(51.0)
    assert effect["system_utility"] == pytest.approx(-51.0)
    assert effect["effect_label"] == "HARMFUL"


def test_i1_512_address_single_stratum_is_frame_scoped_no_go() -> None:
    targets = []
    records = []
    for index in range(512):
        raw = _target(index)
        raw["node"] = 52
        raw["segment_id"] = f"{index}:storage_in_out"
        raw["offline_sampling_metadata"] = {
            "source_node": 52,
            "deadline_slack_bucket": "tight",
            "bag_class": "storage_in_out",
        }
        target = campaign._with_horizon(raw, "H_bag")
        targets.append(target)
        records.append({"target": target, "pair": _pair_for_target(target)})

    summary = campaign.analyse_i1_pairs(records, targets=targets)["summary"]

    assert summary["attempted_source_count"] == 1
    assert summary["attempted_leg_type_count"] == 1
    assert summary["attempted_coverage_ready"] is False
    assert summary["pivot_decision"] == "PIVOT_TO_G2_I1_FRAME_COVERAGE_NO_GO"


def test_i1_native_observation_pair_survives_csv_and_reaches_training(
    tmp_path: Path,
) -> None:
    target = campaign._with_horizon(_target(2), "H_bag")
    pair = _pair_for_target(target)

    analysis = campaign.write_i1_analysis(
        root=tmp_path,
        pair_records=[{"target": target, "pair": pair}],
        targets=[target],
    )
    observation = analysis["effects"][0]["observation_pair"]
    assert observation["schema"] == (
        "czr005.g4irsf17.i1_pre_action_observation_pair.v1"
    )
    assert observation["feature_names"] == list(CANONICAL_OBSERVATION_FEATURES)
    assert len(observation["canonical_candidate_observations"]) == 2
    assert all(
        len(row) == len(CANONICAL_OBSERVATION_FEATURES)
        for row in observation["canonical_candidate_observations"]
    )

    loaded = load_effect_feature_rows(tmp_path / campaign.I1_EFFECTS_PATH)
    trained = train_phase_d(loaded)
    assert trained.input_summary["valid_feature_effect_row_count"] == 1
    assert "FEATURE_ROWS_MISSING_MATCHED_CANDIDATE_PAIR" not in trained.input_summary[
        "rejection_reasons"
    ]
    assert trained.status != "NO_GO_FEATURE_EFFECT_ROWS_ABSENT"


def test_i1_observation_pair_is_native_only_and_rejects_nonlocal_counter() -> None:
    target = campaign._with_horizon(_target(3), "H_bag")
    pair = _pair_for_target(target)
    pair.pop("observation_pair")
    target["observation_pair"] = _native_observation_pair()
    effect = campaign.analyse_i1_pairs(
        [{"target": target, "pair": pair}], targets=[target]
    )["effects"][0]
    assert "observation_pair" not in effect

    invalid_pair = _pair_for_target(target)
    invalid_pair["observation_pair"]["runtime_global_scan_count"] = 1
    with pytest.raises(campaign.CampaignError, match="runtime_global_scan_count"):
        campaign.analyse_i1_pairs(
            [{"target": target, "pair": invalid_pair}], targets=[target]
        )


def test_real_aliasing_hook_flattens_native_treatment_and_filters_ineligible() -> None:
    first = campaign._with_horizon(_target(30), "H_bag")
    second = campaign._with_horizon(_target(31), "H_bag")
    first_pair = _pair_for_target(first)
    second_pair = _pair_for_target(second)
    second_pair["action_changed"] = False
    effects = campaign.analyse_i1_pairs(
        [
            {"target": first, "pair": first_pair},
            {"target": second, "pair": second_pair},
        ],
        targets=[first, second],
    )["effects"]

    result = campaign.call_state_aliasing_hooks(effects)

    assert result["status"] == "CANONICAL_ABLATION_COMPLETE_LEGACY_29_UNAVAILABLE"
    assert result["legacy_29_snapshot_available"] is False
    assert result["comparison_scope"] == "CANONICAL_STATIC_LOCAL_VS_FULL_39_ABLATION"
    assert result["input_row_count"] == 2
    assert result["eligible_feature_row_count"] == 1
    assert result["audit"]["augmented"]["row_count"] == 1


def test_i1_fixture_execution_is_chunk_resumable(tmp_path: Path) -> None:
    pytest.importorskip("zstandard")
    raw_targets = [_target(index) for index in range(4)]
    plan = campaign.create_i1_plan(raw_targets, h_bag_count=4, h_system_count=0)
    pairs = [_pair_for_target(target) for target in plan["targets"]]
    calls: list[list[str]] = []

    def executor(targets: list[dict[str, object]]) -> list[dict[str, object]]:
        calls.append([str(row["target_key"]) for row in targets])
        wanted = set(calls[-1])
        return [pair for pair in pairs if pair["target_key"] in wanted]

    journal = campaign.CampaignJournal(tmp_path)
    journal.begin("i1_paired_execution", command=["fixture"])
    first = campaign.execute_i1_pilot(
        root=tmp_path,
        plan=plan,
        pair_executor=executor,
        chunk_size=2,
        journal=journal,
    )
    assert first["summary"]["record_count"] == 4
    assert len(calls) == 2
    assert (tmp_path / campaign.I1_DATASET_PATH).is_file()
    assert (tmp_path / campaign.I1_EFFECTS_PATH).is_file()
    assert (tmp_path / campaign.I1_SUPPORT_REPORT_PATH).is_file()

    def should_not_run(_: object) -> list[dict[str, object]]:
        raise AssertionError("completed chunks must be reused")

    second = campaign.execute_i1_pilot(
        root=tmp_path,
        plan=plan,
        pair_executor=should_not_run,
        chunk_size=2,
    )
    assert second["summary"]["reused_chunk_count"] == 2
    manifest = json.loads((tmp_path / campaign.CAMPAIGN_MANIFEST_PATH).read_text(encoding="utf-8"))
    assert manifest["stages"]["i1_paired_execution"]["status"] == "COMPLETE"
    assert "EXPAND_COMPETITIVE_I1_TO_128" in (tmp_path / campaign.I1_SUPPORT_REPORT_PATH).read_text(encoding="utf-8")


def test_i1_selected_chunk_is_isolated_then_merged_by_normal_resume(tmp_path: Path) -> None:
    pytest.importorskip("zstandard")
    plan = campaign.create_i1_plan(
        [_target(index) for index in range(4)],
        h_bag_count=4,
        h_system_count=0,
    )
    pairs = {_pair_for_target(target)["target_key"]: _pair_for_target(target) for target in plan["targets"]}
    calls: list[list[str]] = []

    def executor(targets: list[dict[str, object]]) -> list[dict[str, object]]:
        keys = [str(row["target_key"]) for row in targets]
        calls.append(keys)
        return [pairs[key] for key in keys]

    partial = campaign.execute_i1_pilot(
        root=tmp_path,
        plan=plan,
        pair_executor=executor,
        chunk_size=2,
        chunk_indices={1},
    )
    assert partial["summary"]["status"] == "SELECTED_CHUNKS_COMPLETE"
    assert partial["summary"]["completed_chunk_indices"] == [1]
    assert len(calls) == 1
    assert not (tmp_path / campaign.I1_DATASET_PATH).exists()
    assert not (tmp_path / campaign.I1_EFFECTS_PATH).exists()
    assert (tmp_path / campaign.I1_RUNSTATE_ROOT / "chunk-00001.json.zst").is_file()
    assert not (tmp_path / campaign.I1_RUNSTATE_ROOT / "chunk-00000.json.zst").exists()

    merged = campaign.execute_i1_pilot(
        root=tmp_path,
        plan=plan,
        pair_executor=executor,
        chunk_size=2,
    )
    assert merged["summary"]["record_count"] == 4
    assert merged["summary"]["reused_chunk_count"] == 1
    assert len(calls) == 2
    assert (tmp_path / campaign.I1_DATASET_PATH).is_file()


def test_i1_expansion_reuses_existing_pairs_across_new_chunk_boundaries(tmp_path: Path) -> None:
    pytest.importorskip("zstandard")
    pilot = campaign.create_i1_plan(
        [_target(index) for index in range(2)],
        h_bag_count=2,
        h_system_count=0,
    )
    pilot_pairs = {
        campaign._target_key(target): _pair_for_target(target)
        for target in pilot["targets"]
    }

    campaign.execute_i1_pilot(
        root=tmp_path,
        plan=pilot,
        pair_executor=lambda targets: [pilot_pairs[campaign._target_key(row)] for row in targets],
        chunk_size=2,
    )

    fresh = campaign.create_i1_plan(
        [_target(99)],
        h_bag_count=1,
        h_system_count=0,
    )["targets"][0]
    expansion = dict(pilot)
    expansion["targets"] = [dict(pilot["targets"][0]), fresh]
    fresh_pair = _pair_for_target(fresh)
    calls: list[list[str]] = []

    def execute_only_missing(targets: list[dict[str, object]]) -> list[dict[str, object]]:
        calls.append([campaign._target_key(row) for row in targets])
        return [fresh_pair]

    result = campaign.execute_i1_pilot(
        root=tmp_path,
        plan=expansion,
        pair_executor=execute_only_missing,
        chunk_size=2,
        chunk_indices={0},
    )

    assert calls == [[campaign._target_key(fresh)]]
    assert result["summary"]["reused_chunk_count"] == 0
    assert result["summary"]["reused_pair_count"] == 1
    assert result["summary"]["executed_pair_count"] == 1
    assert [campaign._target_key(row["pair"]) for row in result["records"]] == [
        campaign._target_key(row) for row in expansion["targets"]
    ]


def test_i1_publication_omits_redundant_dense_cohort_rows() -> None:
    target = campaign._with_horizon(_target(0), "H_system")
    pair = _pair_for_target(target)
    pair["cohort_difference_sidecar"] = {"row_count": 2, "rows": [{"delta": 0}, {"delta": 1}]}
    pair["cohort_difference_sidecar_serialized"] = True
    for branch_name in ("baseline", "treatment"):
        pair[branch_name]["raw_bag_sufficient_statistics_sidecar"] = {
            "row_count": 2,
            "rows": [{"tth": 1}, {"tth": 2}],
        }
        pair[branch_name]["raw_bag_sufficient_statistics_serialized"] = True

    compact = campaign._compact_pair_for_publication(pair)

    assert pair["cohort_difference_sidecar"]["rows"]
    assert "rows" not in compact["cohort_difference_sidecar"]
    assert compact["cohort_difference_sidecar"]["dense_rows_omitted"] is True
    assert compact["cohort_difference_sidecar_serialized"] is False
    for branch_name in ("baseline", "treatment"):
        sidecar = compact[branch_name]["raw_bag_sufficient_statistics_sidecar"]
        assert "rows" not in sidecar
        assert sidecar["row_count"] == 2
        assert compact[branch_name]["raw_bag_sufficient_statistics_serialized"] is False


def test_package_hooks_are_called_without_reimplementing_models(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    class Splits:
        def to_dict(self) -> dict[str, object]:
            return {"schema": "fixture.splits"}

    def alias(rows: object, **kwargs: object) -> dict[str, object]:
        seen["alias"] = (rows, kwargs)
        return {"legacy": {"sign_disagreement_rate": 0.5}, "augmented": {"sign_disagreement_rate": 0.1}}

    def ablation(rows: object, **kwargs: object) -> list[dict[str, object]]:
        seen["ablation"] = (rows, kwargs)
        return [{"ablated_group": "temporal", "sign_disagreement_delta_vs_full": 0.2}]

    def splits(source: object, timestamps: object, tasks: object) -> Splits:
        seen["splits"] = (source, timestamps, tasks)
        return Splits()

    def evaluate(
        candidate_utilities: object,
        chosen_indices: object,
        *,
        baseline_indices: object = None,
        legal_masks: object = None,
    ) -> dict[str, object]:
        seen["evaluate"] = (candidate_utilities, chosen_indices, baseline_indices, legal_masks)
        return {"mean_advantage_vs_baseline": 1.25}

    package = SimpleNamespace(
        LEGACY_29_FEATURES=("legacy_x",),
        AUGMENTED_WITH_LEGACY_FEATURES=("legacy_x", "local_y"),
        run_state_aliasing_audit=alias,
        feature_ablation=ablation,
        make_diagnostic_splits=splits,
        evaluate_policy=evaluate,
        PairwiseLinearRanker=object,
        TinyMLPListwiseRanker=object,
        ConservativeSelectiveOverride=object,
    )
    rows = [
        {
            "legacy_x": 0.0,
            "local_y": 1.0,
            "system_utility": 2.0,
            "source": "s1",
            "event_ordinal": 1,
            "task_id": 1,
            "effect_label": "BENEFICIAL",
        }
    ]
    alias_result = campaign.write_state_aliasing_report(
        root=tmp_path,
        rows=rows,
        package=package,
    )
    model_result = campaign.write_model_report(
        root=tmp_path,
        rows=rows,
        package=package,
        evaluation_payload={
            "candidate_sets": [[0.0, 2.0]],
            "chosen_indices": [1],
            "baseline_indices": [0],
            "legal_masks": [[True, True]],
        },
    )

    assert alias_result["status"] == "COMPLETE"
    assert model_result["status"] == "COMPLETE"
    assert seen["alias"][1]["augmented_feature_names"] == ("legacy_x", "local_y")
    assert seen["evaluate"][2] == [0]
    assert (tmp_path / campaign.ALIASING_REPORT_PATH).is_file()
    assert (tmp_path / campaign.FEATURE_ABLATION_PATH).is_file()
    assert (tmp_path / campaign.MODEL_REPORT_PATH).is_file()


def test_run_i1_dry_run_does_not_call_native(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan_path = tmp_path / campaign.I1_PLAN_PATH
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(json.dumps(campaign.create_i1_plan([_target(0)], h_bag_count=1, h_system_count=0)), encoding="utf-8")

    status = campaign.main(
        [
            "--root",
            str(tmp_path),
            "run-i1",
            "--plan",
            str(plan_path),
            "--dry-run",
        ]
    )

    assert status == 0
    assert '"status": "DRY_RUN"' in capsys.readouterr().out
    assert not (tmp_path / campaign.I1_DATASET_PATH).exists()
