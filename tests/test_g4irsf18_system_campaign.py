from __future__ import annotations

import gzip
import builtins
import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf18_system_campaign as campaign


def _fault() -> dict[str, object]:
    return {
        "scenario_id": "pending_inflight_repair",
        "category": "single_noncritical_fault",
        "edges": [[24, 32]],
        "onset_fraction": 0.35,
        "duration_seconds": 300.0,
        "message_delay_seconds": 0.0,
        "notification_dropped": False,
    }


def _plan(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    monkeypatch.setattr(campaign, "_fault_scenario", lambda _root: _fault())
    return campaign.build_plan(root=Path("unused"))


def test_plan_freezes_full_cross_product_and_separates_telemetry_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = campaign.validate_plan(_plan(monkeypatch))
    assert len(plan["jobs"]) == 39
    assert plan["learned_arm"]["reason"] == "NO_EXPLICIT_LEARNED_ARM_CONFIG"

    ladder = [row for row in plan["jobs"] if row["stage"] == "ladder"]
    assert {row["prefix_segments"] for row in ladder} == set(campaign.LADDER_SEGMENTS)
    assert {
        row["telemetry_mode"]
        for row in ladder
        if row["prefix_segments"] <= 8_192
    } == {"evidence_trace"}
    assert {
        row["telemetry_mode"]
        for row in ladder
        if row["prefix_segments"] == 43_603
    } == {"capacity"}

    scale = [row for row in plan["jobs"] if row["stage"] == "scale"]
    assert len(scale) == 18
    assert {row["scale"] for row in scale} == {1, 2, 4, 8, 16, 32}
    assert all(row["telemetry_mode"] == "capacity" for row in scale)
    assert {
        row["max_segments"] for row in scale if row["scale"] == 32
    } == {8_192}
    fault = [row for row in plan["jobs"] if row["stage"] == "fault"]
    assert len(fault) == 6
    assert {row["fault_scenario"]["scenario_id"] for row in fault} == {
        campaign.PENDING_FAULT_SCENARIO_ID,
        campaign.INFLIGHT_FAULT_SCENARIO_ID,
    }


def test_plan_validation_rejects_missing_scale_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(monkeypatch)
    plan["jobs"] = [
        row
        for row in plan["jobs"]
        if row["job_id"] != "j1_f2_jit_fifo__16x_full"
    ]
    with pytest.raises(campaign.G18SystemCampaignError, match="scale cross-product"):
        campaign.validate_plan(plan)


def test_learned_arm_is_research_only_and_never_assumed(tmp_path: Path) -> None:
    config = tmp_path / "learned.json"
    base = {
        "schema": campaign.SCHEMA_LEARNED_ARM,
        "arm_id": "J3_RESEARCH_LEARNED",
        "enabled": True,
        "research_closed_loop_authorized": True,
        "fixed_research_workload": True,
        "production_closed_loop_authorized": False,
        "timing_mode": "jit_fifo",
        "merge_rule": "M8",
        "native_controls": {"g4irsf18_merge_policy_path": "artifact.json"},
    }
    config.write_text(json.dumps(base), encoding="utf-8")
    arm, note = campaign.load_learned_arm(config)
    assert arm is not None and arm.learned is True
    assert arm.production_closed_loop_authorized is False
    assert note["reason"] == "INCLUDED_RESEARCH_ONLY"

    base["production_closed_loop_authorized"] = True
    config.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(
        campaign.G18SystemCampaignError, match="must not assert production"
    ):
        campaign.load_learned_arm(config)


def test_capacity_attribution_distinguishes_event_cap_from_algorithm_safety() -> None:
    result = {
        "status": "CAPACITY_CENSORED_EVENT_LIMIT",
        "metrics": {"requested_segments": 174_412},
        "counters": {
            "completed_count": 10_093,
            "event_count": 20_000_000,
            "declared_max_events": 20_000_000,
            "event_limit_reached": True,
            "time_limit_reached": False,
            "merge_grant_peak_pending_requests": 7,
        },
    }
    capacity = campaign._capacity_attribution(result)
    assert capacity["capacity_censored"] is True
    assert capacity["primary_cause"] == "EVENT_LIMIT"
    assert capacity["completed_segments"] == 10_093
    assert capacity["pending_peak"] == 7

    hard = {
        "gates": {
            "all_segments_completed": False,
            "event_limit_not_reached": False,
            "conflict_zero": True,
            "unsafe_zero": True,
            "deadlock_zero": True,
        }
    }
    assert campaign._algorithmic_safety(hard) is True


def test_evidence_trace_has_dependency_free_compressed_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_import = builtins.__import__

    def import_without_zstd(name: str, *args: object, **kwargs: object) -> object:
        if name == "zstandard":
            raise ImportError("fixture excludes optional codec")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_zstd)
    monkeypatch.setattr(
        campaign.jit,
        "_write_jsonl_zst",
        lambda _path, _rows: pytest.fail("zstd writer should not be selected"),
    )
    path, codec = campaign._write_opportunity_trace(
        tmp_path / "result.json",
        [{"opportunity_id": 7, "candidate_request_id": 11}],
    )
    assert codec == "gzip"
    assert path.name == "result.opportunities.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        assert json.loads(stream.readline())["opportunity_id"] == 7


def _result(job: campaign.SystemJob, *, capacity: bool = False, fault: bool = False) -> dict[str, object]:
    counters: dict[str, object] = {
        "requested_count": 8_192,
        "completed_count": 8_192,
        "failed_count": 0,
        "event_count": 82_000,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "merge_grant_service_opportunity_count": 100,
        "merge_grant_multi_candidate_opportunity_count": 4,
        "merge_grant_order_mutation_count": 2,
        "merge_grant_peak_pending_requests": 3,
        "merge_grant_wakeup_scheduled_count": 20,
        "merge_grant_wakeup_coalesced_count": 5,
        "merge_grant_stale_wakeup_count": 0,
        "merge_grant_outstanding_request_count": 0,
    }
    requested = 8_192
    status = "COMPLETE"
    if capacity:
        requested = 43_603
        counters.update(
            completed_count=10_000,
            event_count=20_000_000,
            event_limit_reached=True,
            declared_max_events=20_000_000,
        )
        status = "CAPACITY_CENSORED_EVENT_LIMIT"
    if fault:
        counters.update(
            fault_event_count=1,
            repair_event_count=1,
            fault_affected_bag_count=9,
            fault_affected_completed_count=9,
            merge_grant_inflight_fault_generation_recovery_count=1,
        )
    return {
        "schema": campaign.SCHEMA_RESULT,
        "job": job.as_dict(),
        "status": status,
        "hard_safety": {
            "pass": not capacity,
            "gates": {
                "all_segments_completed": not capacity,
                "event_limit_not_reached": not capacity,
                "conflict_zero": True,
                "unsafe_zero": True,
                "deadlock_zero": True,
            },
        },
        "algorithmic_safety_pass": True,
        "telemetry": {
            "mode": job.telemetry_mode,
            "enabled": job.telemetry_mode == "evidence_trace",
            "trace_limit": campaign.EVIDENCE_TRACE_LIMIT
            if job.telemetry_mode == "evidence_trace"
            else 0,
            "core_counters_retained": True,
        },
        "metrics": {
            "requested_segments": requested,
            "raw_bag_count": requested,
            "mean_tth_seconds": None if capacity else 123.0,
            "p95_tth_seconds": None if capacity else 180.0,
            "source_wait_mean_seconds": None if capacity else 20.0,
            "merge_grant_wait_mean_seconds": None if capacity else 3.0,
            "network_time_mean_seconds": None if capacity else 100.0,
            "events_per_requested_segment": 10.0,
            "wakeups_per_service_opportunity": 0.2,
        },
        "counters": counters,
    }


def test_incremental_analysis_writes_real_rows_and_marks_unrun_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(monkeypatch)
    jobs = [campaign.SystemJob.from_mapping(row) for row in plan["jobs"]]
    results = tmp_path / "runtime"
    results.mkdir()
    chosen = {
        "j0_f2_eager__s8192": _result,
        "j0_f2_eager__1x_full": _result,
        "j1_f2_jit_fifo__fault__pending_inflight_repair__s8192": _result,
    }
    for job in jobs:
        factory = chosen.get(job.job_id)
        if factory is None:
            continue
        value = factory(
            job,
            capacity=job.stage == "scale",
            fault=job.stage == "fault",
        )
        (results / f"{job.job_id}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )

    analysis = campaign.analyse_campaign(plan, results_dir=results, root=tmp_path)
    assert analysis["status"] == "INCREMENTAL"
    assert analysis["stages"]["ladder"]["available_job_count"] == 1
    assert analysis["stages"]["scale"]["available_job_count"] == 1
    assert analysis["scale_rows"][0]["capacity_primary_cause"] == "EVENT_LIMIT"
    assert analysis["scale_rows"][0]["telemetry_mode"] == "capacity"
    assert analysis["fault_rows"][0]["fault_pass"] is True

    ladder_report = tmp_path / "outputs/reports/g4irsf18_closed_loop_ladder.md"
    scale_report = tmp_path / "outputs/reports/g4irsf18_scale_capacity.md"
    fault_report = tmp_path / "outputs/reports/g4irsf18_fault_campaign.md"
    assert "No row or metric is synthesized" in ladder_report.read_text(encoding="utf-8")
    assert "EVENT_LIMIT" in scale_report.read_text(encoding="utf-8")
    assert "| True |" in fault_report.read_text(encoding="utf-8")


def test_external_timeout_is_censored_without_fabricated_business_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(monkeypatch)
    results = tmp_path / "runtime"
    observations = {
        "j0_f2_eager__4x_full": (1199.84375, 807_878_656, 6128, "09:54:22"),
        "j1_f2_jit_fifo__4x_full": (1154.875, 807_763_968, 15960, "09:55:08"),
        "j2_f2_jit_fair_aging_deadline__4x_full": (
            1151.96875,
            777_506_816,
            17076,
            "09:55:10",
        ),
    }
    for job_id, (cpu_lower, rss, pid, started) in observations.items():
        result = campaign.record_timeout_observation(
            plan,
            job_id=job_id,
            results_dir=results,
            wrapper_wall_limit_seconds=1200.0,
            observation_window_return_seconds=1204.0,
            observed_cpu_lower_bound_seconds=cpu_lower,
            observed_rss_bytes=rss,
            observed_pid=pid,
            started_at_local=started,
            root=tmp_path,
        )
        assert result["status"] == "WORKER_TIMEOUT_CENSORED"
        assert result["capacity"]["primary_cause"] == "WORKER_WALL_TIMEOUT"
        assert result["capacity"]["completed_segments"] is None
        assert result["algorithmic_safety_pass"] is None
        assert result["hard_safety"]["pass"] is None
        assert "mean_tth_seconds" not in result["metrics"]

    analysis = campaign.analyse_campaign(plan, results_dir=results, root=tmp_path)
    scale = analysis["stages"]["scale"]
    assert len(scale["blocked_job_ids"]) == 9
    assert scale["blocked_reason"] == "BLOCKED_BY_4X_WALL_BOUNDARY"
    assert set(row["status"] for row in analysis["scale_rows"]) == {
        "WORKER_TIMEOUT_CENSORED"
    }
    assert all(row["algorithmic_safety_pass"] is None for row in analysis["scale_rows"])
    with pytest.raises(
        campaign.G18SystemCampaignError, match="blocked by matched 4x"
    ):
        campaign.run_stage(
            plan,
            stage="scale",
            binary=tmp_path / "native-not-needed.pyd",
            results_dir=results,
            root=tmp_path,
            only_job="j0_f2_eager__8x_full",
        )
