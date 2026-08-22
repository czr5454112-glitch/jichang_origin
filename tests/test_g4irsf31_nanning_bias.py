from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import g4irsf31_map_adapter as map_adapter
from scripts.eval import run_g4irsf31_nanning_bias as bias


def _fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[bias.g31_native.Workload, Path]:
    rows = (
        {
            "segment_id": "10:storage_in",
            "task_id": 10,
            "original_entry_time": 100.0,
            "pass_time": 100.0,
            "std": 6000.0,
            "start": 0,
            "goal": 2,
        },
        {
            "segment_id": "10:storage_out",
            "task_id": 10,
            "original_entry_time": 100.0,
            "pass_time": 3300.0,
            "std": 6000.0,
            "start": 2,
            "goal": 3,
        },
        {
            "segment_id": "11:direct",
            "task_id": 11,
            "original_entry_time": 200.0,
            "pass_time": 200.0,
            "std": 1000.0,
            "start": 0,
            "goal": 3,
        },
    )
    workload = bias.g31_native.Workload(
        scale=1,
        manifest_path=tmp_path / "manifest.json",
        canonical_path=tmp_path / "canonical.jsonl",
        manifest={"protocol": "FIXTURE_NANNING_1X"},
        rows=rows,
        raw_bag_count=2,
        segment_count=3,
    )
    monkeypatch.setattr(bias.g31_native, "SCALE_COUNTS", {1: (2, 3), 2: (2, 3)})
    monkeypatch.setattr(
        bias.g31_native,
        "load_workload",
        lambda scale, _task_dir: workload,
    )
    profile = map_adapter.RuntimeMapProfile(
        name="fixture",
        source_path=tmp_path / "profile.json",
        node_records=(
            (0, 1, 0.0, 0, 0, (1, 2)),
            (1, 4, 10.0, 1, 0, (3,)),
            (2, 1, 0.0, 0, 1, (3,)),
            (3, 2, 0.0, 1, 1, ()),
        ),
        edge_records=(
            (0, 1, 1.0, 2.0),
            (0, 2, 1.0, 2.0),
            (1, 3, 1.0, 2.0),
            (2, 3, 1.0, 2.0),
        ),
        start_nodes=(0, 2),
        goal_nodes=(2, 3),
        storage_source_nodes=(2,),
    )
    captured_base: dict[str, Any] = {}

    def prepare(
        base_case: bias.g31_native.CaseSpec,
        selected: bias.g31_native.Workload,
        *,
        map_profile_path: Path,
        fault_protocol_path: Path,
        binary: Path | None,
    ) -> tuple[
        dict[str, Any],
        tuple[dict[str, Any], ...],
        tuple[dict[str, Any], ...],
        dict[str, Any],
    ]:
        del map_profile_path, fault_protocol_path
        request, potential = map_adapter.build_s4_request(
            profile,
            selected.rows,
            binary=binary,
            scenario=f"fixture_{base_case.case_id}",
            max_events=bias.MAX_EVENTS,
            max_simulation_time=bias.FIXED_END_EPOCH,
            edge_speed_mps=base_case.speed_mps,
            enable_s4_local_potential_descent_guard=True,
            enable_s4_direct_neighbor_merge_calendar_visibility=True,
            complete_on_goal_arrival=True,
        )
        captured_base.clear()
        captured_base.update(request)
        local = {
            "activation": "FAULT_STRUCTURAL_VALUES_EXACT_OFF",
            "learned_from_runtime_data": False,
            "fault_edges": [],
            "source_rejected_unreachable_segment_count": 0,
            "runtime_reachable_segment_count": len(selected.rows),
            "artifact_contract": None,
            "artifact": None,
            "service_aware_potential": dict(potential),
            "local_potential_descent_guard": dict(
                bias.LOCAL_POTENTIAL_DESCENT_GUARD
            ),
            "direct_neighbor_merge_calendar_visibility": dict(
                bias.DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
            ),
            "goal_arrival_completion": dict(bias.GOAL_ARRIVAL_COMPLETION),
        }
        return request, tuple(selected.rows), (), local

    monkeypatch.setattr(bias.g31_native, "prepare_native_request", prepare)
    monkeypatch.setattr(bias, "_TEST_CAPTURED_BASE", captured_base, raising=False)
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.write_bytes(b"fixture")
    return workload, binary


def _summary(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "completed_count": len(request["bag_records"]),
        "failed_count": 0,
        "event_count": 20,
        "decision_count": 4,
        "declared_max_events": bias.MAX_EVENTS,
        "declared_max_simulation_time": bias.FIXED_END_EPOCH,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "fault_event_count": 0,
        "repair_event_count": 0,
        "reservation_conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "runtime_full_astar_calls": 0,
        "runtime_full_cie_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "unresolved_deadlock_count": 0,
        "scorer_mode": "S4_queue_aware_rule_only",
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "g4irsf20_event_hotpath_policy": "E2",
        "local_queue_capacity": 0,
        "s4_local_potential_descent_guard_enabled": True,
        "s4_local_potential_descent_guard_learning_active": False,
        "s4_local_potential_descent_guard_claim_boundary": (
            "one_next_edge_at_current_junction;strict_H_eff_descent;"
            "O_outdegree;no_full_route;no_learning"
        ),
        "s4_direct_neighbor_merge_calendar_visibility_enabled": True,
        "s4_direct_neighbor_merge_calendar_visibility_learning_active": False,
        "s4_direct_neighbor_merge_calendar_visibility_claim_boundary": (
            "direct_outgoing_neighbor_calendar_scalar;"
            "existing_calendar_wait_weight;J2_authority_unchanged;"
            "O_outdegree;no_full_route;no_learning"
        ),
        "complete_on_goal_arrival_enabled": True,
        "complete_on_goal_arrival_claim_boundary": (
            bias.g31_native.GOAL_ARRIVAL_COMPLETION_CLAIM
        ),
        "legacy_observation_bias_max_seconds": request[
            "legacy_observation_bias_max_seconds"
        ],
        "legacy_observation_bias_seed": request["legacy_observation_bias_seed"],
        "legacy_observation_bias_sample_count": 8,
        "legacy_observation_bias_total_seconds": 4.0,
        "legacy_observation_bias_claim_boundary": (
            "deterministic_local_observation_delay_only"
        ),
    }


def _payload(request: dict[str, Any]) -> dict[str, Any]:
    bags = []
    for record in request["bag_records"]:
        segment_id, task_id, release, _deadline, _start, _goal, _source = record
        bags.append(
            {
                "segment_id": segment_id,
                "task_id": task_id,
                "release_time": release,
                "admitted_time": release,
                "finish_time": release + 1.0,
                "completed": True,
            }
        )
    return {"summary": _summary(request), "bags": bags}


def test_manifest_registers_24_secondary_non_exact_cells() -> None:
    manifest = bias.campaign_manifest()

    assert manifest["case_count"] == 24
    assert manifest["fixed_seed"] == 20_260_816
    assert manifest["fresh_exact_primary_target_eligible"] is False
    assert {
        row["observation_bias"]["maximum_seconds"] for row in manifest["cases"]
    } == {1.0, 2.0, 3.0}
    assert all(
        row["hca_reference"]["matched_disturbance_comparison"] is False
        and row["hca_reference"]["exact_table_5_4_reproduction"] is False
        for row in manifest["cases"]
    )


def test_prepare_reuses_final_policy_and_adds_only_frozen_bias_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload, binary = _fixture(tmp_path, monkeypatch)
    case = bias.case_by_id("t5_4_nanning_1x_std_2p5_dev_20")
    request, runtime_rows, rejected, local = bias.prepare_bias_request(
        case,
        workload,
        map_profile_path=tmp_path / "profile.json",
        fault_protocol_path=tmp_path / "faults.json",
        binary=binary,
    )

    base = bias._TEST_CAPTURED_BASE
    assert "legacy_observation_bias_max_seconds" not in base
    assert request["legacy_observation_bias_max_seconds"] == 2.0
    assert request["legacy_observation_bias_seed"] == 20_260_816
    assert {row[3] for row in request["edge_records"]} == {2.5}
    assert request["enable_s4_local_potential_descent_guard"] is True
    assert request["enable_s4_direct_neighbor_merge_calendar_visibility"] is True
    assert request["complete_on_goal_arrival"] is True
    assert request["local_queue_capacity"] == 0
    assert len(runtime_rows) == 3 and not rejected
    assert local["observation_bias"]["learning_active"] is False


def test_fake_native_echo_is_admitted_with_conservative_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workload, binary = _fixture(tmp_path, monkeypatch)
    result = bias.execute_case(
        "t5_4_nanning_1x_std_2_dev_30",
        task_dir=tmp_path,
        map_profile_path=tmp_path / "profile.json",
        fault_protocol_path=tmp_path / "faults.json",
        binary=binary,
        executor=lambda **request: _payload(request),
    )

    assert result["status"] == bias.COMPLETE
    assert result["safety"]["pass"] is True
    assert result["safety"]["observation_bias_echo"]["pass"] is True
    reference = result["comparison_contract"]["hca_reference"]
    assert reference["role"] == "CONSERVATIVE_UNPERTURBED_REFERENCE_ONLY"
    assert reference["observation_disturbance_present"] is False
    assert reference["fresh_exact_primary_target_driver"] is False
    assert bias._artifact_admitted(result) is True


def test_missing_bias_echo_fails_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workload, binary = _fixture(tmp_path, monkeypatch)

    def executor(**request: Any) -> dict[str, Any]:
        result = _payload(request)
        result["summary"].pop("legacy_observation_bias_seed")
        return result

    result = bias.execute_case(
        "t5_4_nanning_1x_std_3_dev_10",
        task_dir=tmp_path,
        map_profile_path=tmp_path / "profile.json",
        fault_protocol_path=tmp_path / "faults.json",
        binary=binary,
        executor=executor,
    )

    assert result["status"] == bias.FAILED
    assert result["safety"]["pass"] is False
    assert result["safety"]["observation_bias_echo"]["gates"][
        "seed_echo"
    ] is False


def test_resume_24_dry_cells_and_reject_stale_claim_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workload, _binary = _fixture(tmp_path, monkeypatch)
    case_root = tmp_path / "cases"
    code = bias.main(
        [
            "resume",
            "--task-dir",
            str(tmp_path),
            "--map-profile",
            str(tmp_path / "profile.json"),
            "--fault-protocol",
            str(tmp_path / "faults.json"),
            "--case-root",
            str(case_root),
            "--dry-run",
            "--force",
        ]
    )

    assert code == 0
    aggregate = json.loads((case_root / "aggregate.json").read_text())
    assert aggregate["expected_case_count"] == 24
    assert len(aggregate["dry_run_ready_case_ids"]) == 24
    assert aggregate["fresh_exact_primary_target_eligible"] is False
    assert aggregate["status"] == "PARTIAL"

    case_id = bias.CASE_IDS[0]
    path = case_root / f"{case_id}.json"
    stale = json.loads(path.read_text())
    stale["fresh_exact_primary_target_eligible"] = True
    path.write_text(json.dumps(stale), encoding="utf-8")
    refreshed = bias.aggregate_results(case_root)
    assert refreshed["stale_case_ids"] == [case_id]
    assert len(refreshed["dry_run_ready_case_ids"]) == 23
    with pytest.raises(bias.NanningBiasError, match="stale or incompatible"):
        bias.main(
            [
                "case",
                "--case-id",
                case_id,
                "--task-dir",
                str(tmp_path),
                "--map-profile",
                str(tmp_path / "profile.json"),
                "--fault-protocol",
                str(tmp_path / "faults.json"),
                "--output",
                str(path),
                "--dry-run",
            ]
        )
