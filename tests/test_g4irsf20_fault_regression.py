from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.eval import run_g4irsf20_fault_regression as campaign


def _scenario(name: str = "protected_fault") -> dict[str, Any]:
    return {
        "scenario_id": name,
        "edges": [[6, 12]],
        "onset_time": 100.0,
        "duration_seconds": 30.0,
        "message_delay_seconds": 0.0,
        "notification_dropped": False,
    }


def _compact(policy: str) -> dict[str, Any]:
    return {
        "policy": policy,
        "status": "COMPLETE",
        "requested_segment_count": 8_192,
        "raw_bag_count": 4_898,
        "completed_bag_count": 4_898,
        "failed_count": 0,
        "hard_safety_pass": True,
        "physical_fault_entry_violation_count": 0,
        "fault_event_count": 1,
        "repair_event_count": 1,
        "fault_affected_bag_count": 4,
        "fault_affected_completed_count": 4,
        "all_affected_tasks_completed": True,
        "notification_update_event_count": 100 if policy == "E0" else 70,
        "notification_drop_count": 0,
        "mean_tth_seconds": 42.0,
        "event_count": 1_000 if policy == "E0" else 900,
        "wall_seconds": 1.0,
        "cpu_seconds": 0.9,
    }


def _semantic(*, action: int = 12, tth: float = 42.0) -> dict[str, Any]:
    return {
        "actions": (("bag-1", 1, 6, 47, action, True, "", 2, 0, 0, (6, action)),),
        "tth": ((1, True, tth, 0.0, tth, 0.0),),
        "hard_safety": {"physical_fault_edge_entry_violation_count_zero": True},
    }


def test_jobs_freeze_protected_8192_fault_identity() -> None:
    rows = campaign.build_fault_jobs([_scenario()])
    assert len(rows) == 1
    scenario, job = rows[0]
    assert scenario["scenario_id"] == "protected_fault"
    assert job.stage == "fault"
    assert job.arm_id == "A0_S4_J2"
    assert job.prefix_segments == 8_192
    assert job.telemetry_mode == "evidence_trace"
    assert job.fault_scenario == scenario


def test_fake_executor_passes_exact_action_tth_and_fault_gates(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def fake_executor(
        job: campaign.g18.SystemJob, policy: str
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        calls.append((job.job_id, policy))
        return _compact(policy), _semantic()

    result = campaign.execute_campaign(
        binary=tmp_path / "unused.pyd",
        root=tmp_path,
        scenarios=[_scenario()],
        executor=fake_executor,
    )
    assert calls == [
        ("g4irsf20_fault__protected_fault", "E0"),
        ("g4irsf20_fault__protected_fault", "E2"),
    ]
    assert result["status"] == "COMPLETE"
    assert result["design"]["controller"] == (
        "A0 + S4 + J2 (M3 destination-grant rule)"
    )
    row = result["scenarios"][0]
    assert all(row["paired_gates"].values())
    assert row["treatment_minus_baseline"]["event_count"] == -100
    assert result["claim_boundary"]["delayed_or_dropped_fault_notifications"] == (
        "NOT_EVALUATED_IN_G4IRSF20"
    )

    json_path, report_path = campaign.write_outputs(result, root=tmp_path)
    persisted = json_path.read_text(encoding="utf-8")
    assert "bag-1" not in persisted
    assert "actions" not in persisted
    assert json.loads(persisted)["status"] == "COMPLETE"
    report = report_path.read_text(encoding="utf-8")
    assert "Delayed and dropped notification behavior remains explicitly unevaluated" in report
    assert "Per-bag final/count/last-eight action projections" in report


@pytest.mark.parametrize(
    ("failure", "expected_gate"),
    [
        ("native", "both_complete"),
        ("physical_entry", "both_zero_physical_fault_entry_violations"),
        ("affected", "both_affected_task_sets_complete"),
        ("action", "action_semantics_equal_to_e0"),
        ("tth", "per_task_tth_equal_to_e0"),
        ("safety", "hard_safety_semantics_equal_to_e0"),
    ],
)
def test_required_regressions_fail_campaign(
    tmp_path: Path, failure: str, expected_gate: str
) -> None:
    def fake_executor(
        _job: campaign.g18.SystemJob, policy: str
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        compact = _compact(policy)
        semantic = _semantic()
        if policy == "E2":
            if failure == "native":
                compact["status"] = "FAULT_GATE_FAILED"
            elif failure == "physical_entry":
                compact["physical_fault_entry_violation_count"] = 1
            elif failure == "affected":
                compact["all_affected_tasks_completed"] = False
            elif failure == "action":
                semantic = _semantic(action=13)
            elif failure == "tth":
                semantic = _semantic(tth=42.001)
            elif failure == "safety":
                semantic["hard_safety"] = {
                    "physical_fault_edge_entry_violation_count_zero": False
                }
        return compact, semantic

    result = campaign.execute_campaign(
        binary=tmp_path / "unused.pyd",
        root=tmp_path,
        scenarios=[_scenario()],
        executor=fake_executor,
    )
    assert result["status"] == "FAILED_REQUIRED_GATE"
    assert f"protected_fault:{expected_gate}" in result["failed_requirements"]


def test_policy_is_the_only_runtime_treatment_choice(tmp_path: Path) -> None:
    def fake_executor(
        _job: campaign.g18.SystemJob, policy: str
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        return _compact(policy), _semantic()

    result = campaign.execute_campaign(
        binary=tmp_path / "unused.pyd",
        policy="E1",
        root=tmp_path,
        scenarios=[_scenario()],
        executor=fake_executor,
    )
    assert result["design"]["baseline_policy"] == "E0"
    assert result["design"]["treatment_policy"] == "E1"
    assert result["design"]["only_changed_control"] == (
        "g4irsf20_event_hotpath_policy"
    )
    with pytest.raises(campaign.FaultRegressionError, match="treatment policy"):
        campaign.execute_campaign(
            binary=tmp_path / "unused.pyd",
            policy="E0",
            root=tmp_path,
            scenarios=[_scenario()],
            executor=fake_executor,
        )


def test_main_writes_compact_json_and_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = {
        "schema": campaign.SCHEMA,
        "status": "COMPLETE",
        "failed_requirements": [],
        "design": {},
        "claim_boundary": {},
        "scenario_count": 0,
        "scenarios": [],
    }
    monkeypatch.setattr(campaign, "execute_campaign", lambda **_kwargs: fake)
    assert campaign.main(
        ["--binary", str(tmp_path / "unused.pyd"), "--root", str(tmp_path)]
    ) == 0
    assert (tmp_path / campaign.DEFAULT_JSON).is_file()
    assert (tmp_path / campaign.DEFAULT_REPORT).is_file()
