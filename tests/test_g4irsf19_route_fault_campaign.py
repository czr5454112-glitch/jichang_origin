from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from czr005 import cpp_backend
from scripts.eval import run_g4irsf19_route_fault_campaign as campaign


ROOT = Path(__file__).resolve().parents[1]


def _scenario() -> dict[str, Any]:
    return {
        "scenario_id": "test_fault",
        "edges": [[1, 2]],
        "onset_time": 0.0,
        "duration_seconds": 30.0,
        "message_delay_seconds": 0.0,
        "notification_dropped": False,
    }


def _compact_fake_result(*, treatment: bool) -> dict[str, Any]:
    shift = -5.0 if treatment else 0.0
    event_shift = -10 if treatment else 0
    return {
        "status": "COMPLETE",
        "hard_safety": {"pass": True},
        "algorithmic_safety_pass": True,
        "metrics": {
            "mean_tth_seconds": 100.0 + shift,
            "p95_tth_seconds": 125.0 + shift,
            "p99_tth_seconds": 135.0 + shift,
            "source_wait_mean_seconds": 20.0 + shift,
            "merge_grant_wait_mean_seconds": 3.0,
            "network_time_mean_seconds": 77.0,
        },
        "counters": {
            "physical_fault_edge_entry_violation_count": 0,
            "fault_event_count": 1,
            "repair_event_count": 1,
            "congestion_beacon_update_event_count": 2,
            "fault_notification_drop_count": 0,
            "fault_affected_bag_count": 4,
            "fault_affected_completed_count": 4,
            "fault_recovery_seconds_available": True,
            "fault_recovery_seconds": 12.5,
            "event_count": 1_000 + event_shift,
            "completed_count": 8_192,
            "failed_count": 0,
        },
        "resources": {"wall_seconds": 1.0, "cpu_seconds": 0.9},
        "_opportunity_rows": [{"must_not_be_persisted": True}],
    }


def test_fault_pair_freezes_8192_j2_and_changes_only_route_scorer() -> None:
    pairs = campaign.build_fault_pairs([_scenario()])
    assert len(pairs) == 1
    scenario, baseline_job, treatment_job = pairs[0]
    assert scenario["scenario_id"] == "test_fault"
    assert baseline_job.stage == treatment_job.stage == "fault"
    assert baseline_job.prefix_segments == treatment_job.prefix_segments == 8_192
    assert baseline_job.fault_scenario == treatment_job.fault_scenario
    assert baseline_job.telemetry_mode == treatment_job.telemetry_mode == "evidence_trace"
    assert {arm.timing_mode for arm in campaign.ARMS} == {
        campaign.J2_TIMING_MODE
    }
    assert {arm.merge_rule for arm in campaign.ARMS} == {campaign.J2_MERGE_RULE}
    assert campaign.BASELINE_ARM.native_controls == {
        "scorer_mode": campaign.S1_MODE
    }
    assert campaign.TREATMENT_ARM.native_controls == {
        "scorer_mode": campaign.S4_MODE
    }


def test_fake_executor_writes_only_compact_paired_evidence(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def fake_executor(
        job: campaign.g18.SystemJob, arm: campaign.g18.Arm
    ) -> Mapping[str, Any]:
        calls.append((job.job_id, str(arm.native_controls["scorer_mode"])))
        return _compact_fake_result(treatment=arm is campaign.TREATMENT_ARM)

    result = campaign.execute_campaign(
        binary=tmp_path / "unused.pyd",
        root=tmp_path,
        scenarios=[_scenario()],
        executor=fake_executor,
    )
    assert calls == [
        (
            "g4irsf19_route_fault__test_fault__j2_s1_route_baseline",
            campaign.S1_MODE,
        ),
        (
            "g4irsf19_route_fault__test_fault__j2_s4_route_treatment",
            campaign.S4_MODE,
        ),
    ]
    row = result["scenarios"][0]
    assert result["status"] == "COMPLETE"
    assert result["failed_requirements"] == []
    assert row["paired_gates"]["both_hard_safety_pass"] is True
    assert row["paired_gates"][
        "both_zero_physical_fault_entry_violations"
    ] is True
    assert row["treatment_minus_baseline"]["mean_tth_seconds"] == -5.0
    assert row["treatment_minus_baseline"]["event_count"] == -10.0

    paths = campaign.write_outputs(result, root=tmp_path)
    persisted = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "must_not_be_persisted" not in persisted
    persisted_json = json.loads(paths[0].read_text(encoding="utf-8"))
    assert all(
        "_opportunity_rows" not in arm
        for row in persisted_json["scenarios"]
        for arm in (row["baseline"], row["treatment"])
    )
    assert "Raw opportunity rows persisted: **0**" in paths[2].read_text(
        encoding="utf-8"
    )
    assert paths[3] == tmp_path / campaign.DEFAULT_MAINLINE_REPORT
    assert paths[3].read_text(encoding="utf-8") == paths[2].read_text(
        encoding="utf-8"
    )
    csv_text = paths[1].read_text(encoding="utf-8")
    assert "mean_tth_delta_seconds" in csv_text
    assert "-5.0" in csv_text


def test_execute_job_adapter_forwards_frozen_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_execute(
        job: campaign.g18.SystemJob,
        arm: campaign.g18.Arm,
        *,
        binary: Path,
        root: Path,
    ) -> dict[str, Any]:
        captured.update(job=job, arm=arm, binary=binary, root=root)
        return _compact_fake_result(treatment=False)

    monkeypatch.setattr(campaign.g18, "execute_job", fake_execute)
    adapter = campaign.make_execute_job_adapter(
        binary=tmp_path / "native.pyd", root=tmp_path
    )
    _, job, _ = campaign.build_fault_pairs([_scenario()])[0]
    result = adapter(job, campaign.BASELINE_ARM)
    assert result["status"] == "COMPLETE"
    assert captured == {
        "job": job,
        "arm": campaign.BASELINE_ARM,
        "binary": tmp_path / "native.pyd",
        "root": tmp_path,
    }


@pytest.mark.parametrize(
    ("failure", "expected_fragment"),
    [
        ("native", "treatment:native_status=HARD_GATE_FAILED"),
        (
            "paired_gate",
            "paired_gate:both_zero_physical_fault_entry_violations",
        ),
        ("recovery", "paired_gate:both_recovery_metrics_available"),
    ],
)
def test_campaign_status_fails_on_native_or_required_gate_regression(
    tmp_path: Path,
    failure: str,
    expected_fragment: str,
) -> None:
    def fake_executor(
        _job: campaign.g18.SystemJob, arm: campaign.g18.Arm
    ) -> Mapping[str, Any]:
        result = _compact_fake_result(treatment=arm is campaign.TREATMENT_ARM)
        if arm is campaign.TREATMENT_ARM and failure == "native":
            result["status"] = "HARD_GATE_FAILED"
        if arm is campaign.TREATMENT_ARM and failure == "paired_gate":
            result["counters"]["physical_fault_edge_entry_violation_count"] = 1
        if arm is campaign.TREATMENT_ARM and failure == "recovery":
            result["counters"]["fault_recovery_seconds_available"] = False
        return result

    result = campaign.execute_campaign(
        binary=tmp_path / "unused.pyd",
        root=tmp_path,
        scenarios=[_scenario()],
        executor=fake_executor,
    )
    assert result["status"] == "FAILED_REQUIRED_GATE"
    assert any(
        expected_fragment in failure_value
        for failure_value in result["failed_requirements"]
    )


def _runtime_payload(mode: str) -> dict[str, Any]:
    summary = {
        "merge_grant_timing_mode": campaign.J2_TIMING_MODE,
        "completed_count": 1,
        "failed_count": 0,
        "reservation_conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "unresolved_deadlock_count": 0,
        "runtime_full_astar_calls": 0,
        "runtime_full_cie_astar_calls": 0,
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
        "event_limit_reached": False,
        "time_limit_reached": False,
        "event_count": 10,
        "merge_grant_service_opportunity_count": 0,
        "merge_grant_wakeup_scheduled_count": 0,
        "merge_grant_opportunity_trace_stored_count": 0,
        "scorer_mode": mode,
    }
    return {
        "summary": summary,
        "bags": [
            {
                "segment_id": "seg-1",
                "task_id": 1,
                "release_time": 0.0,
                "admitted_time": 1.0,
                "finish_time": 5.0,
                "junction_queue_wait_seconds": 1.0,
                "merge_grant_wait_seconds": 0.5,
                "completed": True,
            }
        ],
        "merge_service_opportunities": [],
    }


@pytest.mark.parametrize(
    ("arm", "expects_model"),
    [
        (campaign.BASELINE_ARM, True),
        (campaign.TREATMENT_ARM, False),
    ],
)
def test_g18_request_adapter_passes_model_only_to_model_scorers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arm: campaign.g18.Arm,
    expects_model: bool,
) -> None:
    captured: dict[str, Any] = {}
    input_rows = [
        {
            "segment_id": "seg-1",
            "task_id": 1,
            "pass_time": 0.0,
            "original_entry_time": 0.0,
            "std": 10.0,
            "start": 3,
            "goal": 47,
            "source": "node_3",
        }
    ]
    monkeypatch.setattr(
        campaign.g18,
        "_load_input",
        lambda _job, _root: (
            input_rows,
            {
                "topology_changed": False,
                "tth_denominator": "original_entry_time_tth",
                "segments": 1,
                "scale": 1,
            },
        ),
    )

    def fake_runtime(*, scorer_mode: str, **request: Any) -> dict[str, Any]:
        captured.update(request)
        captured["scorer_mode"] = scorer_mode
        return _runtime_payload(scorer_mode)

    monkeypatch.setattr(
        cpp_backend, "g4irsf11_event_runtime_from_records", fake_runtime
    )
    binary = tmp_path / "native.pyd"
    binary.write_bytes(b"test")
    job = campaign.g18.SystemJob(
        "request_adapter",
        "fault",
        arm.arm_id,
        prefix_segments=8_192,
        fault_scenario=_scenario(),
        telemetry_mode="evidence_trace",
    )
    result = campaign.g18.execute_job(job, arm, binary=binary, root=ROOT)
    assert result["status"] == "COMPLETE"
    assert ("scorer_model_path" in captured) is expects_model
    assert captured["scorer_mode"] == arm.native_controls["scorer_mode"]


def test_main_writes_all_three_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        campaign,
        "execute_campaign",
        lambda **_kwargs: {
            "schema": campaign.SCHEMA,
            "status": "COMPLETE",
            "failed_requirements": [],
            "design": {},
            "scenario_count": 0,
            "scenarios": [],
        },
    )
    assert campaign.main(
        [
            "--binary",
            str(tmp_path / "unused.pyd"),
            "--root",
            str(tmp_path),
        ]
    ) == 0
    assert json.loads((tmp_path / campaign.DEFAULT_JSON).read_text(encoding="utf-8"))[
        "schema"
    ] == campaign.SCHEMA
    assert (tmp_path / campaign.DEFAULT_CSV).is_file()
    assert (tmp_path / campaign.DEFAULT_REPORT).is_file()
    assert (tmp_path / campaign.DEFAULT_MAINLINE_REPORT).is_file()


def test_main_returns_nonzero_but_still_writes_failure_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        campaign,
        "execute_campaign",
        lambda **_kwargs: {
            "schema": campaign.SCHEMA,
            "status": "FAILED_REQUIRED_GATE",
            "failed_requirements": ["fault:treatment:native_status=HARD_GATE_FAILED"],
            "design": {},
            "scenario_count": 0,
            "scenarios": [],
        },
    )
    assert campaign.main(
        [
            "--binary",
            str(tmp_path / "unused.pyd"),
            "--root",
            str(tmp_path),
        ]
    ) == 2
    persisted = json.loads(
        (tmp_path / campaign.DEFAULT_JSON).read_text(encoding="utf-8")
    )
    assert persisted["status"] == "FAILED_REQUIRED_GATE"
