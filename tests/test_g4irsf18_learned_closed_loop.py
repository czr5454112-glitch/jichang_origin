from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf18_learned_closed_loop as campaign


def _artifact(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "czr005.g4irsf18.teacher_counterfactual_linear_merge.v1",
                "family": "teacher_warm_start_counterfactual_advantage_affine",
                "feature_contract": "MERGE_TRACE_LOCAL_V1",
                "production_closed_loop_authorized": False,
                "ood_fallback": "J2",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_plan_freezes_matched_controls_and_requested_coverage_ladder(
    tmp_path: Path,
) -> None:
    plan = campaign.validate_plan(
        campaign.build_plan(
            root=tmp_path,
            artifact_path=tmp_path / "j7.json",
        )
    )
    assert len(plan["jobs"]) == 14
    assert plan["design"]["production_closed_loop_authorized"] is False
    assert plan["design"]["offline_production_gate_passed"] is False
    assert plan["design"]["score_only_is_not_ownership"] is True

    controls = [row for row in plan["jobs"] if row["kind"] == "control"]
    learned = [row for row in plan["jobs"] if row["kind"] == "learned"]
    assert {row["prefix_segments"] for row in controls} == {
        144,
        512,
        2_048,
        8_192,
        43_603,
    }
    assert {
        (row["prefix_segments"], row["coverage_cap"])
        for row in learned
    } == {
        (144, 1.0),
        (512, 0.10),
        (2_048, 0.05),
        (2_048, 0.25),
        (2_048, 0.50),
        (2_048, 0.80),
        (2_048, 1.0),
        (8_192, 1.0),
        (43_603, 1.0),
    }
    assert all(row["matched_control_job_id"] for row in learned)
    assert {
        row["telemetry_mode"]
        for row in plan["jobs"]
        if row["prefix_segments"] <= 8_192
    } == {"evidence_trace"}
    assert {
        row["telemetry_mode"]
        for row in plan["jobs"]
        if row["prefix_segments"] == 43_603
    } == {"capacity"}
    assert plan["telemetry_contract"] == {
        "evidence_trace_prefixes": [144, 512, 2_048, 8_192],
        "capacity_prefixes": [43_603],
        "evidence_trace_limit": 200_000,
        "capacity_opportunity_telemetry_enabled": False,
        "core_native_counters_retained_in_both_modes": True,
    }


def test_plan_validation_rejects_production_and_ladder_drift(
    tmp_path: Path,
) -> None:
    plan = campaign.build_plan(root=tmp_path, artifact_path=tmp_path / "j7.json")
    production = copy.deepcopy(plan)
    production["design"]["production_closed_loop_authorized"] = True
    with pytest.raises(
        campaign.G18LearnedClosedLoopError,
        match="PRODUCTION_FALSE",
    ):
        campaign.validate_plan(production)

    drift = copy.deepcopy(plan)
    learned = next(row for row in drift["jobs"] if row["kind"] == "learned")
    learned["coverage_cap"] = 0.33
    with pytest.raises(campaign.G18LearnedClosedLoopError):
        campaign.validate_plan(drift)


def test_artifact_and_native_controls_stay_research_only(tmp_path: Path) -> None:
    artifact_path = _artifact(tmp_path / "j7.json")
    assert campaign._load_artifact(artifact_path)["feature_contract"] == (
        "MERGE_TRACE_LOCAL_V1"
    )
    job = campaign.ClosedLoopJob.create(2_048, "learned", 0.25)
    controls = campaign.native_policy_controls(job, artifact_path=artifact_path)
    assert controls == {
        "g4irsf18_merge_policy_mode": "research_closed_loop",
        "g4irsf18_merge_policy_artifact": artifact_path,
        "g4irsf18_merge_research_closed_loop_authorized": True,
        "g4irsf18_merge_fixed_research_workload": True,
        "g4irsf18_merge_production_closed_loop_authorized": False,
        "g4irsf18_merge_offline_gate_passed": False,
        "g4irsf18_merge_coverage_cap": 0.25,
        "g4irsf18_merge_max_overrides_per_segment": 2,
        "g4irsf18_merge_kill_switch": False,
    }
    assert campaign.native_policy_controls(
        campaign.ClosedLoopJob.create(2_048, "control"),
        artifact_path=artifact_path,
    ) == {}

    value = json.loads(artifact_path.read_text(encoding="utf-8"))
    value["production_closed_loop_authorized"] = True
    artifact_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(
        campaign.G18LearnedClosedLoopError,
        match="MUST_NOT_AUTHORIZE_PRODUCTION",
    ):
        campaign._load_artifact(artifact_path)


def test_run_plan_supports_single_job_and_resume(tmp_path: Path) -> None:
    artifact_path = _artifact(tmp_path / "j7.json")
    plan = campaign.build_plan(root=tmp_path, artifact_path=artifact_path)
    results = tmp_path / "runtime"
    calls: list[str] = []

    def executor(
        job: campaign.ClosedLoopJob, **_kwargs: object
    ) -> dict[str, object]:
        calls.append(job.job_id)
        return {
            "schema": campaign.SCHEMA_RESULT,
            "job": job.as_dict(),
            "status": "COMPLETE",
            "native_contract": {
                "pass": True,
                "gates": {
                    "deployment_status_research_only": True,
                    "production_promotion_false": True,
                },
            },
            "native_controls": {
                "deployment_status": campaign.RESEARCH_DEPLOYMENT_STATUS,
                "production_promotion_authorized": False,
            },
        }

    job_id = "j7_learned__s2048__c025"
    first = campaign.run_plan(
        plan,
        binary=tmp_path / "native.pyd",
        results_dir=results,
        root=tmp_path,
        job_ids=[job_id],
        executor=executor,
    )
    assert first == {
        "executed": [job_id],
        "resumed": [],
        "failed": [],
        "complete": True,
    }
    second = campaign.run_plan(
        plan,
        binary=tmp_path / "native.pyd",
        results_dir=results,
        root=tmp_path,
        job_ids=[job_id],
        executor=executor,
    )
    assert second["executed"] == []
    assert second["resumed"] == [job_id]
    assert calls == [job_id]


def _fake_result(
    job: campaign.ClosedLoopJob,
    *,
    learned: bool,
    production_authorized: bool = False,
) -> dict[str, object]:
    if learned:
        tth = (9.0, 12.0)
        metrics = {
            "mean_tth_seconds": 10.5,
            "p95_tth_seconds": 11.85,
            "p99_tth_seconds": 11.97,
            "source_wait_mean_seconds": 1.5,
            "merge_grant_wait_mean_seconds": 1.2,
            "network_time_mean_seconds": 7.8,
            "events_per_requested_segment": 50.5,
        }
        counters = {
            "event_count": 101,
            "g4irsf18_merge_model_opportunity_count": 20,
            "g4irsf18_merge_model_eligible_count": 12,
            "g4irsf18_merge_model_proposal_count": 1,
            "g4irsf18_merge_model_applied_count": 1,
            "g4irsf18_merge_model_ownership_count": 1,
            "g4irsf18_merge_distinct_action_mutation_count": 1,
            "g4irsf18_merge_model_ood_count": 2,
            "g4irsf18_merge_model_invalid_count": 0,
            "g4irsf18_merge_model_fallback_count": 2,
            "g4irsf18_merge_j2_fallback_count": 11,
            "g4irsf18_merge_tie_fifo_fallback_count": 0,
            "g4irsf18_merge_shadow_fallback_count": 0,
            "g4irsf18_merge_authorization_fallback_count": 0,
            "g4irsf18_merge_coverage_cap_fallback_count": 9,
            "g4irsf18_merge_override_cap_fallback_count": 1,
            "g4irsf18_merge_starvation_guard_fallback_count": 1,
            "g4irsf18_merge_kill_switch_fallback_count": 0,
            "g4irsf18_merge_kill_switch_trip_count": 0,
        }
    else:
        tth = (10.0, 10.0)
        metrics = {
            "mean_tth_seconds": 10.0,
            "p95_tth_seconds": 10.0,
            "p99_tth_seconds": 10.0,
            "source_wait_mean_seconds": 2.0,
            "merge_grant_wait_mean_seconds": 1.0,
            "network_time_mean_seconds": 7.0,
            "events_per_requested_segment": 50.0,
        }
        counters = {"event_count": 100}
    return {
        "schema": campaign.SCHEMA_RESULT,
        "job": job.as_dict(),
        "status": "COMPLETE",
        "artifact": {"production_closed_loop_authorized": False},
        "native_controls": {
            "production_closed_loop_authorized": production_authorized,
            "offline_gate_passed": False,
            "production_promotion_authorized": False,
            "deployment_status": (
                campaign.RESEARCH_DEPLOYMENT_STATUS if learned else "off"
            ),
        },
        "hard_safety": {"pass": True},
        "native_contract": {
            "pass": True,
            "gates": {
                "artifact_valid": True,
                "production_false": True,
                "offline_gate_false": True,
                "deployment_status_research_only": learned,
                "production_promotion_false": True,
            },
        },
        "telemetry": {
            "mode": job.telemetry_mode,
            "enabled": job.telemetry_mode == "evidence_trace",
            "total_count": 20 if learned else 0,
            "stored_count": 20 if learned else 0,
            "dropped_count": 0,
        },
        "metrics": metrics,
        "counters": counters,
        "kill_switch_reason": "",
        "raw_bags": [
            {"task_id": 1, "complete": True, "tth_seconds": tth[0]},
            {"task_id": 2, "complete": True, "tth_seconds": tth[1]},
        ],
    }


def test_analysis_reports_real_ownership_all_fallbacks_and_paired_deltas(
    tmp_path: Path,
) -> None:
    plan = campaign.build_plan(root=tmp_path, artifact_path=tmp_path / "j7.json")
    results = tmp_path / "runtime"
    results.mkdir()
    control = campaign.ClosedLoopJob.create(512, "control")
    learned = campaign.ClosedLoopJob.create(512, "learned", 0.10)
    for job, is_learned in ((control, False), (learned, True)):
        (results / f"{job.job_id}.json").write_text(
            json.dumps(_fake_result(job, learned=is_learned)),
            encoding="utf-8",
        )

    analysis = campaign.analyse_plan(plan, results_dir=results, root=tmp_path)
    assert analysis["status"] == "INCREMENTAL"
    assert analysis["decision"] == "INCREMENTAL_PENDING_FULL"
    assert analysis["production_closed_loop_authorized"] is False
    row = next(row for row in analysis["rows"] if row["kind"] == "learned")
    assert row["model_opportunity_count"] == 20
    assert row["model_eligible_count"] == 12
    assert row["model_proposal_count"] == 1
    assert row["model_applied_count"] == 1
    assert row["model_ownership_count"] == 1
    assert row["distinct_action_mutation_count"] == 1
    assert row["eligible_sufficient_for_one_applied_action"] is True
    assert row["counter_order_identity_pass"] is True
    assert row["deployment_validation_source"] == "native_summary_echo"
    assert row["model_ood_count"] == 2
    assert row["model_invalid_count"] == 0
    assert row["model_fallback_count"] == 2
    assert row["coverage_cap_fallback_count"] == 9
    assert row["paired_tth_improved_count"] == 1
    assert row["paired_tth_harmed_count"] == 1
    assert row["mean_tth_delta_seconds"] == pytest.approx(0.5)
    assert row["p95_tth_delta_seconds"] == pytest.approx(1.85)
    assert row["p99_tth_delta_seconds"] == pytest.approx(1.97)
    assert row["source_wait_mean_delta_seconds"] == pytest.approx(-0.5)
    assert row["merge_grant_wait_mean_delta_seconds"] == pytest.approx(0.2)
    assert row["network_time_mean_delta_seconds"] == pytest.approx(0.8)
    assert row["event_count_delta"] == 1

    csv_text = (
        tmp_path / "outputs/tables/g4irsf18_learned_closed_loop.csv"
    ).read_text(encoding="utf-8")
    assert "model_ood_count" in csv_text
    assert "starvation_guard_fallback_count" in csv_text
    assert (
        tmp_path / "outputs/reports/g4irsf18_learned_closed_loop.md"
    ).is_file()


def test_pre_echo_results_are_revalidated_from_persisted_native_inputs(
    tmp_path: Path,
) -> None:
    plan = campaign.build_plan(root=tmp_path, artifact_path=tmp_path / "j7.json")
    results = tmp_path / "runtime"
    results.mkdir()
    control = campaign.ClosedLoopJob.create(512, "control")
    learned = campaign.ClosedLoopJob.create(512, "learned", 0.10)
    control_value = _fake_result(control, learned=False)
    learned_value = _fake_result(learned, learned=True)
    learned_value["native_contract"]["gates"].pop(
        "deployment_status_research_only"
    )
    learned_value["native_contract"]["gates"].pop(
        "production_promotion_false"
    )
    learned_value["native_controls"].pop("deployment_status")
    learned_value["native_controls"].pop("production_promotion_authorized")
    learned_value["job"].pop("telemetry_mode")
    for job, value in ((control, control_value), (learned, learned_value)):
        (results / f"{job.job_id}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )

    assert campaign._resume_result_valid(learned_value, learned) is True
    analysis = campaign.analyse_plan(plan, results_dir=results, root=tmp_path)
    row = next(row for row in analysis["rows"] if row["kind"] == "learned")
    assert row["native_contract_pass"] is True
    assert row["deployment_status"] == campaign.RESEARCH_DEPLOYMENT_STATUS
    assert row["production_promotion_authorized"] is False
    assert row["deployment_validation_source"] == (
        "deterministic_native_formula_from_persisted_inputs"
    )


def test_missing_full_is_pending_and_control_gates_do_not_fail_learned_rollup(
    tmp_path: Path,
) -> None:
    plan = campaign.build_plan(root=tmp_path, artifact_path=tmp_path / "j7.json")
    results = tmp_path / "runtime"
    results.mkdir()
    control = campaign.ClosedLoopJob.create(8_192, "control")
    learned = campaign.ClosedLoopJob.create(8_192, "learned", 1.0)
    control_value = _fake_result(control, learned=False)
    control_value["native_contract"] = {"pass": None, "gates": {}}
    control_value["hard_safety"] = {"pass": None}
    for job, value in (
        (control, control_value),
        (learned, _fake_result(learned, learned=True)),
    ):
        (results / f"{job.job_id}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )

    analysis = campaign.analyse_plan(plan, results_dir=results, root=tmp_path)
    assert analysis["status"] == "INCREMENTAL"
    assert analysis["decision"] == "INCREMENTAL_PENDING_FULL"
    assert analysis["hard_safety_pass"] is True
    assert analysis["native_contract_pass"] is True
    assert "j2_control__s43603" in analysis["missing_job_ids"]
    assert "j7_learned__s43603__c100" in analysis["missing_job_ids"]


def test_complete_plan_can_reach_research_evidence_decision(tmp_path: Path) -> None:
    plan = campaign.build_plan(root=tmp_path, artifact_path=tmp_path / "j7.json")
    results = tmp_path / "runtime"
    results.mkdir()
    for mapping in plan["jobs"]:
        job = campaign.ClosedLoopJob.from_mapping(mapping)
        value = _fake_result(job, learned=job.kind == "learned")
        (results / f"{job.job_id}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )

    analysis = campaign.analyse_plan(plan, results_dir=results, root=tmp_path)
    assert analysis["status"] == "COMPLETE"
    assert analysis["decision"] == (
        "RESEARCH_LADDER_EVIDENCE_ONLY_PRODUCTION_FALSE"
    )


def test_analysis_rejects_proposal_only_and_production_echo(tmp_path: Path) -> None:
    plan = campaign.build_plan(root=tmp_path, artifact_path=tmp_path / "j7.json")
    results = tmp_path / "runtime"
    results.mkdir()
    control = campaign.ClosedLoopJob.create(512, "control")
    learned = campaign.ClosedLoopJob.create(512, "learned", 0.10)
    control_value = _fake_result(control, learned=False)
    learned_value = _fake_result(learned, learned=True)
    learned_value["counters"].update(
        {
            "g4irsf18_merge_model_proposal_count": 5,
            "g4irsf18_merge_model_applied_count": 0,
            "g4irsf18_merge_model_ownership_count": 0,
            "g4irsf18_merge_distinct_action_mutation_count": 0,
        }
    )
    for job, value in ((control, control_value), (learned, learned_value)):
        (results / f"{job.job_id}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )
    analysis = campaign.analyse_plan(plan, results_dir=results, root=tmp_path)
    assert analysis["decision"] == "INCREMENTAL_PENDING_FULL"

    learned_value["native_controls"][
        "production_closed_loop_authorized"
    ] = True
    (results / f"{learned.job_id}.json").write_text(
        json.dumps(learned_value), encoding="utf-8"
    )
    analysis = campaign.analyse_plan(plan, results_dir=results, root=tmp_path)
    assert analysis["decision"] == "INVALID_PRODUCTION_AUTHORIZATION"
