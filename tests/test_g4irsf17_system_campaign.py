from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf17_system_campaign as system


def _candidate(candidate_id: str = "D1_LOCAL") -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "policy_family": "deterministic",
        "authorization_status": "AUTHORIZED_FOR_LADDER",
        "native_controls": {"g4irsf17_source_policy_mode": "localized_rule"},
        "locality_contract": {
            "uses_global_state": False,
            "stores_future_route": False,
            "max_message_hops": 2,
            "pending_queue_bound": 4,
        },
        "requires_action_change": True,
    }


def _config() -> dict[str, object]:
    config = system.default_config()
    config["candidates"] = [_candidate()]
    config["_candidate_specs"] = [system.CandidateSpec.from_mapping(_candidate())]
    return config


def _passing_summary(segments: int = 144) -> dict[str, object]:
    return {
        "requested_count": segments,
        "completed_count": segments,
        "failed_count": 0,
        "reservation_conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "unresolved_deadlock_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "priority_global_scan_count": 0,
        "scorer_runtime_global_scan_count": 0,
        "microphase_runtime_global_scan_count": 0,
        "first_edge_credit_global_scan_count": 0,
        "priority_future_route_input_count": 0,
        "scorer_future_route_input_count": 0,
        "first_edge_credit_future_route_count": 0,
        "scorer_future_schedule_input_count": 0,
        "full_future_routes_stored": 0,
        "bag_future_path_field_present": False,
        "reservation_depth": 1,
        "max_edges_selected_per_arrive": 1,
        "max_edges_selected_per_bag_per_decision": 1,
        "event_limit_reached": False,
        "time_limit_reached": False,
    }


def _raw(task_id: int, tth: float, *, block: int = 0) -> dict[str, object]:
    return {
        "task_id": task_id,
        "complete": True,
        "tth_seconds": tth,
        "source_wait_seconds": tth * 0.25,
        "network_time_seconds": tth * 0.75,
        "time_block": block,
    }


def _capacity_scale_result(job: system.RunJob) -> dict[str, object]:
    return {
        "schema": system.SCHEMA_RESULT,
        "job": job.as_dict(),
        "status": "HARD_GATE_FAILED",
        "event_count": system.CAPACITY_CENSOR_EVENT_CAP,
        "hard_safety": {"hard_gate_pass": False},
        "input_descriptor": {
            "protocol": "g4irsf10_distribution_preserving_fixed_map_resample",
            "scale": 4,
            "segments": 174_412,
            "topology_changed": False,
        },
        "runtime_counters": {
            "requested_count": 174_412,
            "completed_count": 10_093,
            "failed_count": 164_319,
            "event_limit_reached": True,
            "time_limit_reached": False,
        },
        "resources": {
            "worker_wall_seconds": 3963.7507,
            "parent_wall_seconds": 3983.4641,
            "cpu_seconds": 3905.015625,
            "peak_rss_mb": 2328.84375,
        },
    }


def _capacity_amendment_plan() -> tuple[dict[str, object], system.RunJob, list[system.RunJob]]:
    scale = system._job(None, track="scale", scale=4, timeout_seconds=14_400.0)
    faults = [
        system._job(
            None,
            track="fault",
            scale=4,
            fault=scenario,
            timeout_seconds=7_200.0,
        )
        for scenario in system.default_fault_scenarios()
    ]
    return {"jobs": [scale.as_dict(), *(job.as_dict() for job in faults)]}, scale, faults


def test_plan_has_full_ladder_fault_loads_and_fixed_map_scale() -> None:
    faults = (
        system.FaultScenario("no_fault", "no_fault", ()),
        system.FaultScenario("critical", "single_critical_bottleneck", ((4, 17),)),
    )
    plan = system.build_run_plan(
        _config(),
        fault_scenarios=faults,
        g2_decision={"triggered": False, "causal_gate_pass": False, "decision": "G2_NOT_TRIGGERED"},
    )
    jobs = [system.RunJob.from_mapping(row) for row in plan["jobs"]]
    assert sorted({job.segments for job in jobs if job.track == "ladder"}) == list(system.LADDER_SEGMENTS)
    assert sorted({job.scale for job in jobs if job.track == "scale"}) == list(system.SCALE_FACTORS)
    assert sorted({job.scale for job in jobs if job.track == "fault"}) == [1, 4]
    assert {job.fault_scenario["category"] for job in jobs if job.track == "fault"} == {
        "no_fault",
        "single_critical_bottleneck",
    }


def test_unauthorized_and_untriggered_g2_candidates_are_not_scheduled() -> None:
    config = _config()
    g2 = _candidate("G2_LEARNED")
    g2["policy_family"] = "g2"
    unauthorized = _candidate("D3_UNAUTHORIZED")
    unauthorized["authorization_status"] = "NOT_AUTHORIZED"
    config["candidates"] = [g2, unauthorized]
    config["_candidate_specs"] = [
        system.CandidateSpec.from_mapping(g2),
        system.CandidateSpec.from_mapping(unauthorized),
    ]
    plan = system.build_run_plan(
        config,
        fault_scenarios=(system.FaultScenario("no_fault", "no_fault", ()),),
        g2_decision={"triggered": False, "causal_gate_pass": False, "decision": "G2_NOT_TRIGGERED"},
    )
    assert {row["reason"] for row in plan["excluded_candidates"]} == {
        "G2_NOT_TRIGGERED",
        "OFFLINE_NOT_AUTHORIZED",
    }
    assert all(row["candidate_id"] == system.OFF_CANDIDATE_ID for row in plan["jobs"])


def test_baseline_only_summarize_publishes_terminal_ladder_artifact(
    tmp_path: Path,
) -> None:
    config = system.default_config()
    config.update(
        {
            "runstate_root": "runstate",
            "campaign_manifest": "manifest.json",
        }
    )
    jobs = [
        system._job(
            None,
            track="ladder",
            segments=segments,
            timeout_seconds=1.0,
        )
        for segments in system.LADDER_SEGMENTS
    ]
    plan = {
        "schema": system.SCHEMA_PLAN,
        "g2_decision": {
            "decision": "G2_NOT_TRIGGERED",
            "reasons": [],
        },
        "jobs": [job.as_dict() for job in jobs],
    }
    for job in jobs:
        system._write_json(
            system.result_path_for(job, config, root=tmp_path),
            {
                "schema": system.SCHEMA_RESULT,
                "job": job.as_dict(),
                "status": "COMPLETE",
            },
        )

    summary = system.summarize_campaign(plan, config, root=tmp_path)

    assert summary["ladder_rows"] == []
    table = tmp_path / system.CLOSED_LOOP_TABLE
    assert table.stat().st_size > 0
    with table.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["record_type"] == "TRACK_STATUS"
    assert rows[0]["decision"] == system.BASELINE_ONLY_LADDER_DECISION
    assert rows[0]["authorized_candidate_count"] == "0"
    assert rows[0]["matched_comparison_row_count"] == "0"

    manifest = system._read_json(tmp_path / "manifest.json")
    stage = manifest["stages"]["closed_loop_ladder"]
    assert stage["status"] == "COMPLETE"
    assert stage["decision"] == system.BASELINE_ONLY_LADDER_DECISION


def test_g2_pivot_uses_downstream_or_512_competitive_gate() -> None:
    downstream = system.decide_g2_pivot(
        {"downstream_backpressure_share": 0.71},
        {},
    )
    assert downstream["triggered"] is True
    assert downstream["decision"] == "G2_PIVOT_TRIGGERED_PILOT_REQUIRED"
    assert downstream["next_pivot"] == system.G2_NEXT_PIVOT

    support_no_go = system.decide_g2_pivot(
        {},
        {
            "attempted_h_bag_opportunity_count": 512,
            "action_changed_h_bag_count": 512,
            "support_ready": False,
        },
        causal_evidence={
            "status": "COMPLETE",
            "attempted_opportunity_count": 128,
            "support_ready": True,
            "hard_safety_pass": True,
        },
    )
    assert support_no_go["triggered"] is True
    assert support_no_go["decision"] == "G2_CAUSAL_GATE_PASS_LADDER_ALLOWED"


def test_hard_safety_is_fail_closed_and_accepts_completed_finite_waits() -> None:
    summary = _passing_summary()
    locality = _candidate()["locality_contract"]
    result = system.evaluate_hard_safety(
        summary,
        requested_segments=144,
        policy_family="deterministic",
        locality_contract=locality,
        raw_bags=[{"complete": True, "source_wait_seconds": 1.0}],
    )
    assert result["hard_gate_pass"] is True

    missing = deepcopy(summary)
    missing.pop("priority_global_scan_count")
    assert (
        system.evaluate_hard_safety(
            missing,
            requested_segments=144,
            policy_family="deterministic",
            locality_contract=locality,
            raw_bags=[{"complete": True, "source_wait_seconds": 1.0}],
        )["hard_gate_pass"]
        is False
    )


def test_paired_metrics_keep_source_network_decomposition_and_counts() -> None:
    off = [_raw(1, 10.0, block=0), _raw(2, 20.0, block=1), _raw(3, 30.0, block=1)]
    candidate = [_raw(1, 9.0, block=0), _raw(2, 18.0, block=1), _raw(3, 30.0, block=1)]
    result = system.paired_performance(
        off,
        candidate,
        bootstrap_replicates=200,
        bootstrap_seed=7,
    )
    assert result["mean_tth_delta_seconds"] == -1.0
    assert result["source_wait_delta_mean_seconds"] == -0.25
    assert result["network_time_delta_mean_seconds"] == -0.75
    assert (result["improved_bag_count"], result["degraded_bag_count"], result["unchanged_bag_count"]) == (2, 0, 1)
    assert result["bootstrap"]["method"] == "time_block_bootstrap"


def test_scale_raw_bags_use_frozen_java_release_denominator() -> None:
    inputs = [
        {
            "segment_id": "0:storage_in",
            "task_id": 0,
            "pass_time": 1.0,
            "original_entry_time": 1.8,
        }
    ]
    payload = {
        "bags": [
            {
                "segment_id": "0:storage_in",
                "complete": True,
                "admitted_time": 2.0,
                "finish_time": 4.0,
                "release_time": 1.0,
            }
        ]
    }
    with pytest.raises(Exception, match="Java release precedes raw original entry"):
        system._raw_bag_rows(inputs, payload)
    row = system._raw_bag_rows(
        inputs,
        payload,
        primary_denominator="java_release_time_tth",
    )[0]
    assert row["tth_seconds"] == 3.0
    assert row["source_wait_seconds"] == 1.0
    assert row["network_time_seconds"] == 2.0
    assert row["original_entry_time_tth_seconds"] == pytest.approx(2.2)
    assert row["tth_denominator"] == "java_release_time_tth"


def test_scale_observation_keeps_business_and_capacity_knee_metrics() -> None:
    metrics = system._scale_observation(
        {
            "requested_segments": 100,
            "p50_tth_seconds": 12.0,
            "source_wait_mean_seconds": 3.0,
            "network_time_mean_seconds": 9.0,
            "event_count": 250,
            "decision_count": 110,
            "beacon_message_count": 70,
            "pibt_activation_count": 4,
            "max_source_queue_length": 19,
            "max_source_queue_delay_seconds": 44.0,
            "max_junction_queue_length": 8,
            "resources": {"cpu_seconds": 0.5, "peak_rss_mb": 123.0},
        }
    )

    assert metrics["events_per_segment"] == pytest.approx(2.5)
    assert metrics["cpu_microseconds_per_event"] == pytest.approx(2_000.0)
    assert metrics["source_wait_mean_seconds"] == 3.0
    assert metrics["max_source_queue_length"] == 19
    assert metrics["max_source_queue_delay_seconds"] == 44.0


def test_scale_profile_does_not_turn_capacity_censoring_into_a_win() -> None:
    row = {
        "candidate_id": system.OFF_CANDIDATE_ID,
        "scale": 4,
        "status": "HARD_GATE_FAILED",
        "hard_gate_pass": False,
        "event_limit_reached": True,
        "requested_segment_count": 174_412,
        "completed_segment_count": 10_093,
        "event_count": 20_000_000,
        "events_per_segment": 20_000_000 / 174_412,
        "cpu_microseconds_per_event": 195.25,
        "decisions_per_segment": 0.46,
        "beacons_per_segment": 40.4,
        "pibt_activation_count": 111,
        "source_wait_positive_bag_share": 0.75,
        "source_wait_positive_mean_seconds": 1000.0,
        "queue_fields_available": False,
    }
    profile = system.build_scale_profile_rows([row])[0]
    assert profile["profile_classification"] == "CAPACITY_CENSORED"
    assert profile["observation_complete"] is False
    assert profile["scalability_win"] is False
    assert profile["completed_segment_count"] == 10_093


def test_scale_terminal_narrative_names_only_real_pending_loads() -> None:
    rows = [
        {"candidate_id": "E4_OFF", "scale": 1, "status": "COMPLETE"},
        {"candidate_id": "E4_OFF", "scale": 2, "status": "COMPLETE"},
        {
            "candidate_id": "E4_OFF",
            "scale": 4,
            "status": "HARD_GATE_FAILED",
            "event_limit_reached": True,
        },
        {
            "candidate_id": "E4_OFF",
            "scale": 8,
            "status": "HARD_GATE_FAILED",
            "event_limit_reached": True,
        },
        {"candidate_id": "E4_OFF", "scale": 16, "status": "NOT_RUN"},
    ]

    pending = system._scale_terminal_narrative(rows)
    assert "remain for 16x" in pending
    assert "8x/16x" not in pending

    rows[-1] = {
        "candidate_id": "E4_OFF",
        "scale": 16,
        "status": "HARD_GATE_FAILED",
        "event_limit_reached": True,
    }
    terminal = system._scale_terminal_narrative(rows)
    assert "All required fixed-map scale rows" in terminal
    assert "4x, 8x, and 16x" in terminal
    assert "remain for" not in terminal

    queue = system._scale_queue_telemetry_summary(rows)
    assert queue["queue_telemetry_status"] == "PER_NODE_QUEUE_PEAKS_UNAVAILABLE"
    assert queue["queue_fields_available_row_count"] == 0
    assert queue["required_scale_row_count"] == len(system.SCALE_FACTORS)
    assert queue["queue_peak_bound_supported"] is False


def test_scale_profile_records_verified_event_queue_reserve_parity(tmp_path: Path) -> None:
    shared = {
        "status": "COMPLETE",
        "completion_rate": 1.0,
        "mean_tth_seconds": 217.0,
        "p50_tth_seconds": 204.0,
        "p95_tth_seconds": 270.0,
        "p99_tth_seconds": 330.0,
        "source_wait_mean_seconds": 0.2,
        "network_time_mean_seconds": 216.8,
        "event_count": 5_310_155,
        "decision_count": 340_738,
        "beacon_message_count": 2_065_878,
        "pibt_activation_count": 0,
        "hard_safety": {"hard_gate_pass": True, "gates": {"complete": True}},
    }
    baseline = {
        **shared,
        "resources": {
            "cpu_seconds": 28.765625,
            "worker_wall_seconds": 28.987376,
            "peak_rss_mb": 1403.7734375,
        },
    }
    repeats = [
        {
            **shared,
            "resources": {
                "cpu_seconds": cpu,
                "worker_wall_seconds": wall,
                "peak_rss_mb": rss,
            },
        }
        for cpu, wall, rss in (
            (27.90625, 28.3256228, 1398.66796875),
            (27.734375, 28.1541604, 1398.52734375),
        )
    ]
    system._write_json(tmp_path / system.EVENT_QUEUE_RESERVE_BASELINE, baseline)
    for path, repeat in zip(system.EVENT_QUEUE_RESERVE_REPEATS, repeats, strict=True):
        system._write_json(tmp_path / path, repeat)

    profile = system.build_scale_profile_rows(
        [
            {
                "candidate_id": system.OFF_CANDIDATE_ID,
                "scale": 1,
                "status": "COMPLETE",
                "hard_gate_pass": True,
            }
        ],
        root=tmp_path,
    )[0]
    assert profile["optimization_decision"] == "VERIFIED_EVENT_QUEUE_RESERVE_MICRO_OPT"
    assert profile["semantic_parity"] is True
    assert profile["repeat_count"] == 2
    assert profile["optimized_cpu_seconds_mean"] == pytest.approx(27.8203125)
    assert profile["cpu_delta_percent"] == pytest.approx(-3.286257, abs=1e-5)
    assert profile["worker_wall_delta_percent"] == pytest.approx(-2.5787, abs=1e-4)
    assert profile["resolves_4x_event_amplification"] is False


def test_failed_segment_diagnostics_preserve_native_reason_and_local_history() -> None:
    payload = {
        "bags": [
            {
                "runtime_bag_id": 7,
                "task_id": 10472,
                "segment_id": "10472:storage_in",
                "start": 0,
                "goal": 47,
                "final_node": 6,
                "release_time": 34042.0,
                "admitted_time": 34042.5,
                "finish_time": -1.0,
                "total_local_wait": 300.0,
                "decision_count": 2,
                "retry_count": 1200,
                "completed": False,
                "failure_reason": "event_queue_exhausted",
                "short_history": [0, 6],
            },
            {"runtime_bag_id": 8, "completed": True},
        ]
    }
    count, rows = system._failed_segment_diagnostics(payload)
    assert count == 1
    assert rows == [
        {
            "runtime_bag_id": 7,
            "task_id": 10472,
            "segment_id": "10472:storage_in",
            "start": 0,
            "goal": 47,
            "final_node": 6,
            "release_time": 34042.0,
            "admitted_time": 34042.5,
            "finish_time": -1.0,
            "total_local_wait": 300.0,
            "decision_count": 2,
            "retry_count": 1200,
            "failure_reason": "event_queue_exhausted",
            "short_history": [0, 6],
        }
    ]


def test_full_gate_requires_ci_and_strict_tail_non_regression() -> None:
    comparison = {
        "matched_raw_bag_count": 10,
        "paired_complete_count": 10,
        "off_incomplete_count": 0,
        "candidate_incomplete_count": 0,
        "mean_tth_delta_seconds": -1.0,
        "p95_tth_delta_seconds": 0.0,
        "p99_tth_delta_seconds": -0.1,
        "bootstrap": {"ci95_upper_seconds": -0.2},
    }
    gate = system.evaluate_ladder_gate(
        comparison,
        segments=43_603,
        candidate_hard_gate_pass=True,
        off_hard_gate_pass=True,
        action_change_count=4,
        requires_action_change=True,
    )
    assert gate["pass"] is True

    regressed_tail = deepcopy(comparison)
    regressed_tail["p99_tth_delta_seconds"] = 0.001
    assert (
        system.evaluate_ladder_gate(
            regressed_tail,
            segments=43_603,
            candidate_hard_gate_pass=True,
            off_hard_gate_pass=True,
            action_change_count=4,
            requires_action_change=True,
        )["pass"]
        is False
    )


def test_timeout_checkpoint_is_terminal_but_worker_error_is_resumable(tmp_path: Path) -> None:
    timeout = tmp_path / "timeout.json"
    system._write_json(timeout, {"status": "CENSORED_TIMEOUT"})
    assert system.result_is_resumable(timeout, root=tmp_path) is True

    skipped = tmp_path / "skipped.json"
    system._write_json(skipped, {"status": "NOT_RUN_PREDECESSOR_GATE"})
    assert system.result_is_resumable(skipped, root=tmp_path) is True

    failed = tmp_path / "failed.json"
    system._write_json(failed, {"status": "FAILED_RESUMABLE"})
    assert system.result_is_resumable(failed, root=tmp_path) is False


def test_censored_job_is_terminal_for_resume_but_not_complete_evidence() -> None:
    job = system._job(None, track="ladder", segments=144, timeout_seconds=1.0)
    plan = {"jobs": [job.as_dict()]}
    results = {job.job_id: {"status": "CENSORED_TIMEOUT"}}
    assert system._track_complete(plan, results, "ladder") is False


def test_4x_fault_protocol_reuses_capacity_control_without_faking_treatments() -> None:
    plan, scale_job, fault_jobs = _capacity_amendment_plan()
    results = {scale_job.job_id: _capacity_scale_result(scale_job)}

    rows = system.build_fault_rows(plan, results, system.default_config())
    assert len(rows) == 11
    control = next(row for row in rows if row["fault_category"] == "no_fault")
    treatments = [row for row in rows if row["fault_category"] != "no_fault"]

    assert control["status"] == system.CAPACITY_CENSOR_CONTROL_STATUS
    assert control["execution_status"] == "EVIDENCE_REUSED"
    assert control["evidence_job_id"] == scale_job.job_id
    assert control["capacity_event_cap"] == 20_000_000
    assert control["capacity_completed_segment_count"] == 10_093
    assert control["capacity_requested_segment_count"] == 174_412
    assert control["capacity_worker_wall_seconds"] == pytest.approx(3963.7507)
    assert control["capacity_peak_rss_mb"] == pytest.approx(2328.84375)
    assert control["terminal"] is True
    assert control["evaluable"] is False
    assert all(row["status"] == system.CAPACITY_CENSOR_TREATMENT_STATUS for row in treatments)
    assert all(row["execution_status"] == "NOT_RUN" for row in treatments)
    assert all(row["terminal"] is True and row["evaluable"] is False for row in treatments)
    assert all(row["fault_gate_pass"] is None for row in treatments)
    assert not ({job.job_id for job in fault_jobs} & set(results))


def test_4x_capacity_amendment_is_an_honest_terminal_fault_track() -> None:
    plan, scale_job, fault_jobs = _capacity_amendment_plan()
    one_x_jobs = [
        system._job(
            None,
            track="fault",
            scale=1,
            fault=system.FaultScenario.from_mapping(job.fault_scenario or {}),
            timeout_seconds=7_200.0,
        )
        for job in fault_jobs
    ]
    plan["jobs"] = [
        scale_job.as_dict(),
        *(job.as_dict() for job in one_x_jobs),
        *(job.as_dict() for job in fault_jobs),
    ]
    results: dict[str, dict[str, object]] = {
        scale_job.job_id: _capacity_scale_result(scale_job)
    }
    for job in one_x_jobs:
        results[job.job_id] = {
            "status": "COMPLETE",
            "hard_safety": {"hard_gate_pass": True},
            "fault_affected_bag_count": 1,
            "fault_affected_completed_count": 1,
            "stranded_bag_count": 0,
            "fault_recovery_seconds_available": True,
            "fault_recovery_time_seconds": 1.0,
            "fault_event_count": 1,
            "repair_event_count": 1,
        }

    rows = system.build_fault_rows(plan, results, system.default_config())
    protocol = system._fault_protocol_summary(plan, results, rows)
    assert protocol["track"] == system.CAPACITY_CENSOR_TRACK_STATUS
    assert protocol["protocol_status"] == "AMENDED"
    assert protocol["terminal"] is True
    assert protocol["workflow_terminal"] is True
    assert protocol["scientific_matrix_complete"] is False
    assert protocol["original_1x_matrix_complete"] is True
    assert protocol["original_4x_matrix_complete"] is False
    assert protocol["fault_advantage_4x"] == "NOT_ESTIMABLE"
    assert protocol["executed_row_count"] == 11
    assert protocol["evaluable_row_count"] == 11
    assert protocol["evidence_reused_count"] == 1
    assert protocol["not_run_control_censored_count"] == 10
    assert protocol["evaluable_pass_count"] + protocol["evaluable_fail_count"] == 11


def test_run_plan_does_not_create_amended_fault_result_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = system.default_config()
    config["runstate_root"] = "runstate"
    plan, scale_job, fault_jobs = _capacity_amendment_plan()
    scale_path = system.result_path_for(scale_job, config, root=tmp_path)
    system._write_json(scale_path, _capacity_scale_result(scale_job))

    def unexpected_execution(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("capacity-censored fault job must not execute")

    monkeypatch.setattr(system, "run_job_subprocess", unexpected_execution)
    returned = system.run_plan(
        plan,
        config,
        config_path=tmp_path / "config.json",
        root=tmp_path,
        tracks={"fault"},
    )
    assert returned == []
    assert all(
        not system.result_path_for(job, config, root=tmp_path).exists()
        for job in fault_jobs
    )


def test_fault_gate_requires_observed_native_recovery() -> None:
    fault = system.FaultScenario(
        "repair",
        "repair_after_fault",
        ((4, 17),),
        duration_seconds=97.0,
    )
    job = system._job(None, track="fault", scale=1, fault=fault, timeout_seconds=1.0)
    plan = {"jobs": [job.as_dict()]}
    result = {
        "status": "COMPLETE",
        "hard_safety": {"hard_gate_pass": True},
        "fault_affected_bag_count": 2,
        "fault_affected_completed_count": 2,
        "stranded_bag_count": 0,
        "fault_recovery_seconds_available": False,
        "fault_recovery_time_seconds": None,
        "fault_event_count": 1,
        "repair_event_count": 1,
    }
    row = system.build_fault_rows(plan, {job.job_id: result}, system.default_config())[0]
    assert row["recovery_evidence_pass"] is False
    assert row["fault_gate_pass"] is False

    result["fault_recovery_seconds_available"] = True
    result["fault_recovery_time_seconds"] = 12.5
    row = system.build_fault_rows(plan, {job.job_id: result}, system.default_config())[0]
    assert row["recovery_evidence_pass"] is True
    assert row["fault_gate_pass"] is True


def test_inflight_merge_recovery_counter_is_persisted_without_faking_legacy_evidence() -> None:
    counter = system.INFLIGHT_MERGE_RECOVERY_COUNTER
    assert system._nonnegative_counter_evidence({}, counter) == (0, False)
    assert system._nonnegative_counter_evidence({counter: 0}, counter) == (0, True)
    assert system._nonnegative_counter_evidence({counter: 2}, counter) == (2, True)
    assert system._nonnegative_counter_evidence(
        {counter: 2, f"{counter}_available": False}, counter
    ) == (0, False)

    fault = system.FaultScenario(
        "merge_incoming_edge",
        "merge_edge_or_node",
        ((6, 8),),
    )
    job = system._job(
        None, track="fault", scale=1, fault=fault, timeout_seconds=1.0
    )
    plan = {"jobs": [job.as_dict()]}
    result = {
        "status": "COMPLETE",
        "hard_safety": {"hard_gate_pass": True},
        "fault_affected_bag_count": 1,
        "fault_affected_completed_count": 1,
        "stranded_bag_count": 0,
        "fault_recovery_seconds_available": True,
        "fault_recovery_time_seconds": 3.0,
        "fault_event_count": 1,
        "repair_event_count": 1,
    }

    legacy = system.build_fault_rows(
        plan, {job.job_id: result}, system.default_config()
    )[0]
    assert legacy[counter] == 0
    assert legacy[f"{counter}_available"] is False
    assert legacy["inflight_merge_recovery_evidence_status"] == "UNAVAILABLE"

    result[counter] = 0
    result[f"{counter}_available"] = True
    zero = system.build_fault_rows(
        plan, {job.job_id: result}, system.default_config()
    )[0]
    assert zero[counter] == 0
    assert zero[f"{counter}_available"] is True
    assert zero["inflight_merge_recovery_evidence_status"] == "ZERO_OBSERVED"

    result[counter] = 1
    observed = system.build_fault_rows(
        plan, {job.job_id: result}, system.default_config()
    )[0]
    assert observed[counter] == 1
    assert observed[f"{counter}_available"] is True
    assert observed["inflight_merge_recovery_evidence_status"] == "OBSERVED"


def test_candidate_promotion_requires_fault_matrix_pass() -> None:
    ladder = [
        {
            "candidate_id": "D1",
            "policy_family": "deterministic",
            "segments": 43_603,
            "ladder_gate_pass": True,
        }
    ]
    scale = [
        {"candidate_id": "D1", "policy_family": "deterministic", "scale": 2, "high_load_non_regression": True},
        {"candidate_id": "D1", "policy_family": "deterministic", "scale": 4, "high_load_non_regression": True},
    ]
    decision = system._candidate_decisions(ladder, scale, [])["D1"]
    assert decision["scale_gate_pass"] is True
    assert decision["fault_matrix_pass"] is False
    assert decision["performance_promoted"] is False


def test_real_fault_catalog_covers_required_native_categories() -> None:
    scenarios = system.default_fault_scenarios()
    categories = {scenario.category for scenario in scenarios}
    assert {
        "single_noncritical_edge",
        "single_critical_bottleneck",
        "merge_edge_or_node",
        "source_first_edge",
        "ebs_related_edge",
        "two_nonadjacent_faults",
        "two_propagating_faults",
        "delayed_beacon",
        "dropped_intermediate_beacon",
        "repair_after_fault",
    } <= categories
    structural = {
        scenario.scenario_id: scenario.edges
        for scenario in scenarios
        if scenario.scenario_id
        in {
            "noncritical_edge",
            "critical_bottleneck",
            "merge_incoming_edge",
            "source_first_edge",
            "ebs_outgoing_edge",
        }
    }
    assert len(set(structural.values())) == len(structural)


def test_final_decision_never_promotes_incomplete_campaign() -> None:
    candidate = {
        "D1": {
            "candidate_id": "D1",
            "policy_family": "deterministic",
            "performance_promoted": True,
        }
    }
    pending = system.decide_final_joint(candidate, campaign_complete=False, g2_decision={})
    assert pending["decision"] == "IN_PROGRESS_EVIDENCE_NOT_COMPLETE"
    complete = system.decide_final_joint(candidate, campaign_complete=True, g2_decision={})
    assert complete["decision"].startswith("B.")

    capacity_terminal = system.decide_final_joint(
        candidate,
        campaign_complete=False,
        g2_decision={"next_pivot": "bounded-local pivot"},
        capacity_censored_terminal=True,
    )
    assert capacity_terminal["decision"] == system.CAPACITY_CENSOR_FINAL_DECISION
    assert capacity_terminal["terminal"] is True
    assert capacity_terminal["protocol_amended"] is True
    assert capacity_terminal["scientific_matrix_complete"] is False
    assert "FULL_NO_GO" not in capacity_terminal["decision"]


def test_completed_g2_screen_overrides_stale_plan_snapshot(tmp_path: Path) -> None:
    artifact = {
        "status": "COMPLETE_MATCHED_SCREEN",
        "comparison_count": 20,
        "comparisons": [
            {"hard_safety_pass": True, "same_state_causal_opportunity_count": 0}
            for _ in range(20)
        ],
        "causal_authorization": {
            "authorized": False,
            "same_state_causal_opportunity_count": 0,
        },
        "recommended_for_same_state_causal_followup": [],
    }
    system._write_json(tmp_path / system.G2_MATCHED_PILOT, artifact)
    manifest = {
        "stages": {
            "i1_analysis": {
                "summary": {
                    "attempted_h_bag_opportunity_count": 512,
                    "action_changed_h_bag_count": 248,
                    "support_ready": False,
                }
            }
        }
    }
    decision = system._current_g2_decision(
        tmp_path,
        {"g2_decision": {"decision": "G2_PIVOT_TRIGGERED_PILOT_REQUIRED", "causal_evidence_status": "MISSING"}},
        manifest,
    )
    assert decision["decision"] == "CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT"
    assert decision["next_pivot"] == system.G2_NEXT_PIVOT
    assert decision["scope_status"] == system.G2_EAGER_DIAGNOSTIC_STATUS
    assert decision["global_g2_scientific_no_go"] is False
    assert decision["jit_choice_seam_status"] == "NOT_IMPLEMENTED"
    assert decision["causal_evidence_status"] == "COMPLETE_MATCHED_SCREEN_NOT_SAME_STATE_CAUSAL"
    assert decision["causal_gate_pass"] is False
    assert decision["i1_attempted_competitive_count"] == 512
    assert decision["i1_changed_count"] == 248
    assert decision["hard_safety_pass_count"] == 20


def test_manifest_phase_sync_uses_terminal_i1_gate_and_aggregate_eh(tmp_path: Path) -> None:
    for path in (
        system.I1_CAUSAL_DATASET,
        Path("artifacts/datasets/g4irsf17_i1_pilot_plan.json"),
        Path("artifacts/datasets/g4irsf17_i1_expansion_plan.json"),
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"evidence")
    system._write_json(
        tmp_path / system.I1_SELECTIVE_GATE,
        {"status": "TRAINED_NOT_AUTHORIZED", "authorized": False},
    )
    manifest = {
        "phases": [
            {"phase": "0", "status": "IN_PROGRESS", "result_paths": []},
            {
                "phase": "B-D",
                "status": "IN_PROGRESS",
                "decision": "STALE",
                "result_paths": ["artifacts/datasets/g4irsf17_i1_causal_pairs.jsonl.zst"],
            },
            {"phase": "E-H", "status": "PLANNED", "decision": "PENDING", "result_paths": []},
        ],
        "stages": {
            name: {"status": "COMPLETE"}
            for name in ("i1_paired_execution", "i1_analysis", "state_aliasing")
        },
    }
    final = {"decision": "IN_PROGRESS_EVIDENCE_NOT_COMPLETE"}
    system._sync_manifest_phases(
        manifest,
        root=tmp_path,
        g2={"decision": "CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT"},
        final=final,
        ladder_complete=True,
        fault_terminal=True,
        fault_scientific_complete=True,
        fault_protocol_amended=False,
        scale_complete=False,
    )
    phases = {row["phase"]: row for row in manifest["phases"]}
    assert manifest["stages"]["phase0_validation"]["summary"]["pytest_passed_test_count"] == 112
    assert phases["0"]["status"] == "COMPLETE"
    assert phases["B-D"]["status"] == "COMPLETE"
    assert phases["B-D"]["decision"] == "TRAINED_NOT_AUTHORIZED"
    assert system.I1_CAUSAL_DATASET.as_posix() in phases["B-D"]["result_paths"]
    assert "artifacts/datasets/g4irsf17_i1_causal_pairs.jsonl.zst" not in phases["B-D"]["result_paths"]
    assert phases["E-H"]["status"] == "IN_PROGRESS"
    assert phases["E-H"]["decision"] == final["decision"]
    assert len(phases["E-H"]["result_paths"]) == len(set(phases["E-H"]["result_paths"]))


def test_manifest_phase_sync_keeps_capacity_terminal_distinct_from_complete(
    tmp_path: Path,
) -> None:
    manifest = {
        "phases": [
            {"phase": "E-H", "status": "PLANNED", "result_paths": []}
        ],
        "stages": {},
    }
    final = {"decision": system.CAPACITY_CENSOR_FINAL_DECISION}
    system._sync_manifest_phases(
        manifest,
        root=tmp_path,
        g2={},
        final=final,
        ladder_complete=True,
        fault_terminal=True,
        fault_scientific_complete=False,
        fault_protocol_amended=True,
        scale_complete=True,
    )

    phase = manifest["phases"][0]
    assert phase["status"] == system.CAPACITY_CENSOR_FINAL_DECISION
    assert phase["decision"] == system.CAPACITY_CENSOR_FINAL_DECISION
    assert phase["workflow_terminal"] is True
    assert phase["protocol_amended"] is True
    assert phase["scientific_matrix_complete"] is False


def test_parser_exposes_plan_run_summarize_and_status() -> None:
    parser = system.build_parser()
    assert parser.parse_args(["plan"]).command == "plan"
    assert parser.parse_args(["run", "--track", "ladder"]).track == ["ladder"]
    assert parser.parse_args(["summarize"]).command == "summarize"
    assert parser.parse_args(["status"]).command == "status"


def test_summarize_rebuilds_reports_and_preserves_manifest(tmp_path: Path) -> None:
    config = _config()
    config.update(
        {
            "runstate_root": "runstate",
            "campaign_manifest": "manifest.json",
            "bootstrap_replicates": 100,
            "bootstrap_seed": 3,
        }
    )
    candidate = system.CandidateSpec.from_mapping(_candidate())
    jobs: list[system.RunJob] = []
    for segments in system.LADDER_SEGMENTS:
        jobs.append(system._job(None, track="ladder", segments=segments, timeout_seconds=1.0))
        jobs.append(system._job(candidate, track="ladder", segments=segments, timeout_seconds=1.0))
    plan = {
        "schema": system.SCHEMA_PLAN,
        "g2_decision": {"decision": "G2_NOT_TRIGGERED", "reasons": []},
        "jobs": [job.as_dict() for job in jobs],
    }
    descriptor = {"protocol": "synthetic_test_only", "segments": 2, "topology_changed": False}
    for job in jobs:
        result_path = system.result_path_for(job, config, root=tmp_path)
        raw_path = result_path.with_suffix(".raw_bags.jsonl.zst")
        rows = [_raw(1, 10.0), _raw(2, 20.0)]
        if job.candidate_id != system.OFF_CANDIDATE_ID:
            rows = [_raw(1, 9.0), _raw(2, 19.0)]
        system._write_raw_bags(raw_path, rows)
        system._write_json(
            result_path,
            {
                "schema": system.SCHEMA_RESULT,
                "job": job.as_dict(),
                "status": "COMPLETE",
                "input_descriptor": descriptor,
                "fault_descriptor": {"scenario_id": "no_fault", "edges": [], "fault_onset": None, "repair_time": None},
                "raw_bag_artifact": system._relative(raw_path, tmp_path),
                "action_change_count": 2 if job.candidate_id != system.OFF_CANDIDATE_ID else 0,
                "hard_safety": {"hard_gate_pass": True},
                "resources": {"parent_wall_seconds": 1.0, "cpu_seconds": 0.8, "peak_rss_mb": 100.0},
            },
        )
    system._write_json(tmp_path / "manifest.json", {"schema": "existing", "custom": "keep", "stages": {}})
    summary = system.summarize_campaign(plan, config, root=tmp_path)
    assert summary["complete"] is True
    assert (tmp_path / system.CLOSED_LOOP_REPORT).is_file()
    assert (tmp_path / system.FINAL_REPORT).is_file()
    manifest = system._read_json(tmp_path / "manifest.json")
    assert manifest["custom"] == "keep"
    assert manifest["stages"]["closed_loop_ladder"]["status"] == "COMPLETE"


def test_capacity_terminal_summarize_and_status_are_protocol_aware(
    tmp_path: Path,
) -> None:
    config = system.default_config()
    config.update(
        {
            "runstate_root": "runstate",
            "campaign_manifest": "manifest.json",
        }
    )
    ladder_job = system._job(
        None,
        track="ladder",
        segments=system.LADDER_SEGMENTS[-1],
        timeout_seconds=1.0,
    )
    scale_jobs = [
        system._job(None, track="scale", scale=scale, timeout_seconds=14_400.0)
        for scale in system.SCALE_FACTORS
    ]
    fault_1x = [
        system._job(
            None,
            track="fault",
            scale=1,
            fault=scenario,
            timeout_seconds=7_200.0,
        )
        for scenario in system.default_fault_scenarios()
    ]
    fault_4x = [
        system._job(
            None,
            track="fault",
            scale=4,
            fault=scenario,
            timeout_seconds=7_200.0,
        )
        for scenario in system.default_fault_scenarios()
    ]
    jobs = [ladder_job, *scale_jobs, *fault_1x, *fault_4x]
    plan = {
        "schema": system.SCHEMA_PLAN,
        "g2_decision": {
            "decision": "CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT",
            "next_pivot": system.G2_NEXT_PIVOT,
            "reasons": [],
        },
        "jobs": [job.as_dict() for job in jobs],
    }

    complete_result = {
        "schema": system.SCHEMA_RESULT,
        "status": "COMPLETE",
        "completion_rate": 1.0,
        "hard_safety": {"hard_gate_pass": True},
        "resources": {
            "worker_wall_seconds": 1.0,
            "parent_wall_seconds": 1.1,
            "cpu_seconds": 0.8,
            "peak_rss_mb": 100.0,
        },
    }
    system._write_json(
        system.result_path_for(ladder_job, config, root=tmp_path),
        {**complete_result, "job": ladder_job.as_dict()},
    )
    for job in scale_jobs:
        if job.scale == 4:
            result = _capacity_scale_result(job)
        elif job.scale in {8, 16}:
            requested = 43_603 * int(job.scale)
            result = {
                "schema": system.SCHEMA_RESULT,
                "job": job.as_dict(),
                "status": "HARD_GATE_FAILED",
                "event_count": system.CAPACITY_CENSOR_EVENT_CAP,
                "hard_safety": {"hard_gate_pass": False},
                "input_descriptor": {
                    "protocol": "g4irsf10_distribution_preserving_fixed_map_resample",
                    "scale": job.scale,
                    "segments": requested,
                    "topology_changed": False,
                },
                "runtime_counters": {
                    "requested_count": requested,
                    "completed_count": 1_000,
                    "failed_count": requested - 1_000,
                    "event_limit_reached": True,
                    "time_limit_reached": False,
                },
                "resources": complete_result["resources"],
            }
        else:
            result = {
                **complete_result,
                "job": job.as_dict(),
                "runtime_counters": {
                    "requested_count": 43_603 * int(job.scale),
                    "completed_count": 43_603 * int(job.scale),
                    "failed_count": 0,
                    "event_limit_reached": False,
                    "time_limit_reached": False,
                },
            }
        system._write_json(
            system.result_path_for(job, config, root=tmp_path), result
        )

    for job in fault_1x:
        scenario = system.FaultScenario.from_mapping(job.fault_scenario or {})
        affected = 0 if scenario.category == "no_fault" else 1
        system._write_json(
            system.result_path_for(job, config, root=tmp_path),
            {
                **complete_result,
                "job": job.as_dict(),
                "fault_affected_bag_count": affected,
                "fault_affected_completed_count": affected,
                "stranded_bag_count": 0,
                "fault_recovery_seconds_available": affected > 0,
                "fault_recovery_time_seconds": 1.0 if affected else None,
                "fault_event_count": affected,
                "repair_event_count": affected,
            },
        )

    system._write_json(
        tmp_path / "manifest.json",
        {
            "schema": "existing",
            "phases": [
                {
                    "phase": "E-H",
                    "status": "IN_PROGRESS",
                    "result_paths": [],
                }
            ],
            "stages": {},
        },
    )
    system._write_json(
        tmp_path / system.G2_MATCHED_PILOT,
        {
            "status": "COMPLETE_MATCHED_SCREEN",
            "comparisons": [],
            "causal_authorization": {
                "authorized": False,
                "same_state_causal_opportunity_count": 0,
            },
            "recommended_for_same_state_causal_followup": [],
        },
    )

    summary = system.summarize_campaign(plan, config, root=tmp_path)
    assert summary["complete"] is False
    assert summary["workflow_terminal"] is True
    assert summary["final_decision"]["decision"] == system.CAPACITY_CENSOR_FINAL_DECISION
    assert summary["final_decision"]["next_pivot"] == system.G2_NEXT_PIVOT

    manifest = system._read_json(tmp_path / "manifest.json")
    phase = manifest["phases"][0]
    assert manifest["stages"]["scale_benchmark"]["status"] == "COMPLETE"
    assert (
        manifest["stages"]["scale_benchmark"]["summary"][
            "queue_telemetry_status"
        ]
        == "PER_NODE_QUEUE_PEAKS_UNAVAILABLE"
    )
    assert (
        manifest["stages"]["scale_benchmark"]["summary"][
            "queue_peak_bound_supported"
        ]
        is False
    )
    assert (
        manifest["stages"]["g2_decision"]["status"]
        == system.G2_EAGER_DIAGNOSTIC_STATUS
    )
    assert manifest["stages"]["g2_decision"]["diagnostic_terminal"] is True
    assert (
        manifest["stages"]["g2_decision"]["global_g2_scientific_complete"]
        is False
    )
    assert (
        manifest["stages"]["native_fault_campaign"]["status"]
        == system.CAPACITY_CENSOR_TRACK_STATUS
    )
    assert phase["status"] == system.CAPACITY_CENSOR_FINAL_DECISION
    assert phase["workflow_terminal"] is True
    assert phase["scientific_matrix_complete"] is False
    assert manifest["final_joint_decision"]["next_pivot"] == system.G2_NEXT_PIVOT

    results = system.load_results(plan, config, root=tmp_path)
    status = system._campaign_status_summary(plan, results, config)
    assert status["planned_jobs"] == len(jobs)
    assert status["checkpointed_jobs"] == len(jobs) - len(fault_4x)
    assert status["missing_checkpoint_jobs"] == len(fault_4x)
    assert status["amended_terminal_jobs"] == len(fault_4x)
    assert status["effective_terminal_jobs"] == len(jobs)
    assert status["pending_jobs"] == 0
    assert status["pending_job_ids"] == []
    assert status["workflow_terminal"] is True
    assert status["scientific_complete"] is False
    assert status["protocol_amended"] is True
    assert status["amended_status_counts"] == {
        system.CAPACITY_CENSOR_CONTROL_STATUS: 1,
        system.CAPACITY_CENSOR_TREATMENT_STATUS: len(fault_4x) - 1,
    }

    scale_report = (tmp_path / system.SCALE_REPORT).read_text(encoding="utf-8")
    g2_report = (tmp_path / system.G2_REPORT).read_text(encoding="utf-8")
    final_report = (tmp_path / system.FINAL_REPORT).read_text(encoding="utf-8")
    assert "does not establish a per-node queue-peak bound" in scale_report
    assert system.G2_EAGER_DIAGNOSTIC_STATUS in g2_report
    assert "not a global G2 scientific no-go" in g2_report
    assert system.G2_NEXT_PIVOT in g2_report
    assert system.G2_NEXT_PIVOT in final_report
