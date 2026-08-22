from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import run_g4irsf31_nanning_native as native


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path, Path]:
    monkeypatch.setattr(native, "STORAGE_NODE", 2)
    monkeypatch.setattr(native, "SCALE_COUNTS", {1: (2, 3), 2: (4, 6)})
    task_dir = tmp_path / "tasks"
    task_dir.mkdir()
    canonical = task_dir / "canonical.jsonl"
    rows = [
        {
            "segment_id": "10:storage_in",
            "task_id": 10,
            "original_entry_time": 100.0,
            "pass_time": 100.0,
            "std": 6000.0,
            "start": 0,
            "goal": 2,
            "leg": "storage_in",
        },
        {
            "segment_id": "10:storage_out",
            "task_id": 10,
            "original_entry_time": 100.0,
            "pass_time": 3300.0,
            "std": 6000.0,
            "start": 2,
            "goal": 3,
            "leg": "storage_out",
        },
        {
            "segment_id": "11:direct",
            "task_id": 11,
            "original_entry_time": 200.0,
            "pass_time": 200.0,
            "std": 1000.0,
            "start": 0,
            "goal": 3,
            "leg": "direct",
        },
    ]
    canonical.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    manifest = {
        "schema": native.WORKLOAD_SCHEMA,
        "status": "COMPLETE",
        "scale": 1,
        "map_id": native.MAP_ID,
        "protocol": "FIXTURE_NANNING_1X",
        "raw_task_count": 2,
        "expanded_segment_count": 3,
        "canonical_output": str(canonical),
        "lifecycle": {"storage_in_goal": 2, "storage_out_start": 2},
    }
    (task_dir / "nanning_1x_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "name": "fixture",
                "start_nodes": [0],
                "end_nodes": [3],
                "nodes": [
                    {
                        "location": 0,
                        "node_type": 1,
                        "service_time": 0.0,
                        "outgoing": [1, 2],
                    },
                    {
                        "location": 1,
                        "node_type": 4,
                        "service_time": 10.0,
                        "outgoing": [3],
                    },
                    {
                        "location": 2,
                        "node_type": 7,
                        "service_time": 0.0,
                        "outgoing": [3],
                    },
                    {
                        "location": 3,
                        "node_type": 2,
                        "service_time": 0.0,
                        "outgoing": [],
                    },
                ],
                "edges": [
                    {"start": 0, "end": 1, "length": 1.0, "speed": 2.0},
                    {"start": 0, "end": 2, "length": 1.0, "speed": 2.0},
                    {"start": 1, "end": 3, "length": 1.0, "speed": 2.0},
                    {"start": 2, "end": 3, "length": 1.0, "speed": 2.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    protocol = tmp_path / "faults.json"
    protocol.write_text(
        json.dumps(
            {
                "schema": native.FAULT_PROTOCOL_SCHEMA,
                "map_id": native.MAP_ID,
                "scales": {
                    "1x": {
                        "scenarios": [
                            {
                                "scenario": "single_1",
                                "line_ids": [1],
                                "fault_edges": [[0, 2]],
                                "topology_upper_raw_bags": 1,
                                "topology_blocked_raw_bags": 1,
                                "topology_upper_rate": 0.5,
                            }
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.write_bytes(b"fixture")
    return task_dir, profile, protocol, binary


def _summary(request: dict[str, Any], *, completed: int, failed: int) -> dict[str, Any]:
    return {
        "completed_count": completed,
        "failed_count": failed,
        "event_count": 20,
        "decision_count": 4,
        "declared_max_events": native.MAX_EVENTS,
        "declared_max_simulation_time": native.FIXED_END_EPOCH,
        "event_limit_reached": False,
        "time_limit_reached": bool(failed),
        "fault_event_count": len(request["fault_windows"]),
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
            native.GOAL_ARRIVAL_COMPLETION_CLAIM
        ),
    }


def _fake_payload(request: dict[str, Any], *, fail_last: bool = False) -> dict[str, Any]:
    bags = []
    for index, record in enumerate(request["bag_records"]):
        segment_id, task_id, release, _deadline, _start, _goal, _source = record
        completed = not (fail_last and index == len(request["bag_records"]) - 1)
        bags.append(
            {
                "segment_id": segment_id,
                "task_id": task_id,
                "release_time": release,
                "admitted_time": release,
                "finish_time": release + 1.0 if completed else -1.0,
                "completed": completed,
            }
        )
    completed = sum(bool(row["completed"]) for row in bags)
    return {
        "summary": _summary(
            request, completed=completed, failed=len(bags) - completed
        ),
        "bags": bags,
    }


def test_campaign_manifest_separates_primary_fault_and_bias_contexts() -> None:
    manifest = native.campaign_manifest()

    assert manifest["primary_case_count"] == 40
    assert manifest["stable_speed_case_count"] == 8
    assert manifest["line_interruption_case_count"] == 32
    assert manifest["observation_bias_context_count"] == 12
    assert {
        case.case_id
        for case in native.PRIMARY_CASES
        if case.fault_scenario == "pair_5_7"
    } == {
        "t5_5_nanning_1x_fault_pair_5_7",
        "t5_5_nanning_2x_fault_pair_5_7",
    }
    contexts = native.observation_bias_contexts()
    assert {row["observation_bias"]["seed"] for row in contexts} == {
        native.g27_bias.FIXED_OBSERVATION_BIAS_SEED
    }
    assert {row["observation_bias"]["maximum_seconds"] for row in contexts} == {
        1.0,
        2.0,
        3.0,
    }
    assert all(not row["exact_paper_reproduction_claimed"] for row in contexts)


def test_bias_context_builder_changes_only_existing_delay_abi() -> None:
    source = {
        "edge_records": [(0, 1, 5.0, 2.5)],
        "scorer_mode": "S4_queue_aware_rule_only",
    }
    context = native.observation_bias_contexts()[1]

    result = native.apply_observation_bias_context(source, context)

    assert source == {
        "edge_records": [(0, 1, 5.0, 2.5)],
        "scorer_mode": "S4_queue_aware_rule_only",
    }
    assert result["edge_records"] == source["edge_records"]
    assert result["legacy_observation_bias_seed"] == (
        native.g27_bias.FIXED_OBSERVATION_BIAS_SEED
    )
    assert result["legacy_observation_bias_max_seconds"] == 2.0


def test_stable_dry_request_is_full_population_own_source_s4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir, profile, protocol, _binary = _fixture(tmp_path, monkeypatch)
    result = native.execute_case(
        "t5_2_nanning_1x_speed_1p5",
        task_dir=task_dir,
        map_profile_path=profile,
        fault_protocol_path=protocol,
        binary=None,
        dry_run=True,
    )

    assert result["status"] == native.DRY_RUN_READY
    assert result["selection"]["hca_release_trace_applied"] is False
    assert result["comparison_contract"]["capacity"][
        "comparison_allowed_after_matching_hca_cell_exists"
    ] is True
    assert result["comparison_contract"]["timing"][
        "requires_both_frameworks_complete_full_population"
    ] is True
    request = result["request_contract"]
    assert request["runtime_requested_segment_count"] == 3
    assert request["storage_source_nodes"] == [2]
    assert request["edge_speeds_mps"] == [1.5]
    assert request["max_simulation_time"] == 98_259.0
    assert request["max_events"] == 60_000_000
    assert request["local_queue_capacity"] == 0
    assert request["fault_windows"] == []
    assert request["policy"]["learning_active"] is False
    assert request["policy"]["local_potential_descent_guard"] == (
        native.LOCAL_POTENTIAL_DESCENT_GUARD
    )
    assert request["policy"]["local_software_queue_cap"] == (
        native.LOCAL_SOFTWARE_QUEUE_CAP
    )
    assert request["policy"]["local_software_queue_cap"]["semantics"] == (
        "no configured software queue cap; service calendar/R3 and E4/J2 "
        "retained; capacity-triggered PIBT relief inactive"
    )
    assert request["policy"][
        "direct_neighbor_merge_calendar_visibility"
    ] == native.DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
    assert request["policy"]["goal_arrival_completion"] == (
        native.GOAL_ARRIVAL_COMPLETION
    )


def test_fault_request_recomputes_service_aware_values_on_selected_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir, profile, protocol, binary = _fixture(tmp_path, monkeypatch)
    case = native.case_by_id("t5_5_nanning_1x_fault_single_1")
    workload = native.load_workload(1, task_dir)
    request, runtime_rows, rejected, local = native.prepare_native_request(
        case,
        workload,
        map_profile_path=profile,
        fault_protocol_path=protocol,
        binary=binary,
    )

    assert len(runtime_rows) == 2
    assert [row["segment_id"] for row in rejected] == ["10:storage_in"]
    assert request["fault_windows"] == [
        (0, 2, native.FIXED_START_EPOCH, native.FAULT_REPAIR_EPOCH, 0.0, False)
    ]
    assert request["enable_s4_local_potential_descent_guard"] is True
    assert (
        request["enable_s4_direct_neighbor_merge_calendar_visibility"]
        is True
    )
    assert request["complete_on_goal_arrival"] is True
    assert request["local_queue_capacity"] == 0
    assert request["g4irsf24_dlp_artifact"][
        "deterministic_surviving_graph_values"
    ] is True
    assert local["activation"] == "FAULT_ONLY_SERVICE_AWARE_STRUCTURAL_VALUES"
    assert local["artifact_contract"]["learned_from_runtime_data"] is False
    assert local["artifact_contract"]["dynamic_distance_semantics"] == (
        "service_aware_surviving_graph_cost"
    )
    assert local["artifact_contract"]["local_potential_descent_guard"] == (
        native.LOCAL_POTENTIAL_DESCENT_GUARD
    )
    assert local["direct_neighbor_merge_calendar_visibility"] == (
        native.DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
    )
    # Node 1's surviving cost to goal 3 is service(1)=10 plus 1/2.5 travel.
    residual = next(
        row["residual_seconds"]
        for row in request["g4irsf24_dlp_artifact"]["value_residuals"]
        if row["node"] == 1 and row["goal"] == 3
    )
    assert request["heuristic_time"][1][3] + residual == pytest.approx(10.4)


def test_complete_population_timing_stays_descriptive_until_hca_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir, profile, protocol, binary = _fixture(tmp_path, monkeypatch)

    def executor(**request: Any) -> dict[str, Any]:
        return _fake_payload(request)

    result = native.execute_case(
        "t5_2_nanning_1x_speed_2p5",
        task_dir=task_dir,
        map_profile_path=profile,
        fault_protocol_path=protocol,
        binary=binary,
        executor=executor,
    )

    assert result["status"] == native.COMPLETE
    assert result["outcome"]["completed_raw_bag_count"] == 2
    assert result["safety"]["pass"] is True
    assert result["safety"]["local_potential_descent_guard"]["pass"] is True
    assert result["safety"]["local_potential_descent_guard"][
        "learning_active"
    ] is False
    assert result["safety"]["local_software_queue_cap"]["pass"] is True
    assert result["safety"]["local_software_queue_cap"][
        "summary_local_queue_capacity"
    ] == 0.0
    assert result["safety"][
        "direct_neighbor_merge_calendar_visibility"
    ]["pass"] is True
    assert result["safety"]["goal_arrival_completion"]["pass"] is True
    assert native._artifact_admitted(result) is True
    stale = json.loads(json.dumps(result))
    stale["request_contract"]["policy"].pop(
        "direct_neighbor_merge_calendar_visibility"
    )
    assert native._artifact_admitted(stale) is False
    stale_goal = json.loads(json.dumps(result))
    stale_goal["request_contract"]["policy"].pop(
        "goal_arrival_completion"
    )
    assert native._artifact_admitted(stale_goal) is False
    assert result["timing"]["status"] == "S4_FULL_POPULATION_DESCRIPTIVE"
    assert result["timing"]["full_outcome_timing_comparison_allowed"] is False
    assert result["timing"][
        "comparison_requires_matching_full_population_hca_timing"
    ] is True


def test_missing_native_guard_echo_is_not_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir, profile, protocol, binary = _fixture(tmp_path, monkeypatch)

    def executor(**request: Any) -> dict[str, Any]:
        payload = _fake_payload(request)
        payload["summary"][
            "s4_local_potential_descent_guard_enabled"
        ] = False
        return payload

    result = native.execute_case(
        "t5_2_nanning_1x_speed_2p5",
        task_dir=task_dir,
        map_profile_path=profile,
        fault_protocol_path=protocol,
        binary=binary,
        executor=executor,
    )

    assert result["status"] == native.FAILED
    assert result["safety"]["pass"] is False
    assert result["safety"]["gates"][
        "local_potential_descent_guard"
    ] is False
    assert result["safety"]["local_potential_descent_guard"]["gates"][
        "summary_enabled"
    ] is False


def test_nonzero_native_queue_cap_echo_is_not_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir, profile, protocol, binary = _fixture(tmp_path, monkeypatch)

    def executor(**request: Any) -> dict[str, Any]:
        payload = _fake_payload(request)
        payload["summary"]["local_queue_capacity"] = 32
        return payload

    result = native.execute_case(
        "t5_2_nanning_1x_speed_2p5",
        task_dir=task_dir,
        map_profile_path=profile,
        fault_protocol_path=protocol,
        binary=binary,
        executor=executor,
    )

    assert result["status"] == native.FAILED
    assert result["safety"]["gates"]["local_software_queue_cap"] is False
    assert result["safety"]["local_software_queue_cap"]["gates"][
        "summary_zero"
    ] is False


def test_missing_merge_calendar_visibility_echo_is_not_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir, profile, protocol, binary = _fixture(tmp_path, monkeypatch)

    def executor(**request: Any) -> dict[str, Any]:
        payload = _fake_payload(request)
        payload["summary"][
            "s4_direct_neighbor_merge_calendar_visibility_enabled"
        ] = False
        return payload

    result = native.execute_case(
        "t5_2_nanning_1x_speed_2p5",
        task_dir=task_dir,
        map_profile_path=profile,
        fault_protocol_path=protocol,
        binary=binary,
        executor=executor,
    )

    assert result["status"] == native.FAILED
    assert result["safety"]["gates"][
        "direct_neighbor_merge_calendar_visibility"
    ] is False
    assert result["safety"][
        "direct_neighbor_merge_calendar_visibility"
    ]["gates"]["summary_enabled"] is False


def test_missing_goal_arrival_completion_echo_is_not_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir, profile, protocol, binary = _fixture(tmp_path, monkeypatch)

    def executor(**request: Any) -> dict[str, Any]:
        payload = _fake_payload(request)
        payload["summary"]["complete_on_goal_arrival_enabled"] = False
        return payload

    result = native.execute_case(
        "t5_2_nanning_1x_speed_2p5",
        task_dir=task_dir,
        map_profile_path=profile,
        fault_protocol_path=protocol,
        binary=binary,
        executor=executor,
    )

    assert result["status"] == native.FAILED
    assert result["safety"]["gates"]["goal_arrival_completion"] is False
    assert result["safety"]["goal_arrival_completion"]["gates"][
        "summary_enabled"
    ] is False


def test_fixed_horizon_incompletion_is_capacity_outcome_not_timing_population(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir, profile, protocol, binary = _fixture(tmp_path, monkeypatch)

    def executor(**request: Any) -> dict[str, Any]:
        return _fake_payload(request, fail_last=True)

    result = native.execute_case(
        "t5_2_nanning_1x_speed_3",
        task_dir=task_dir,
        map_profile_path=profile,
        fault_protocol_path=protocol,
        binary=binary,
        executor=executor,
    )

    assert result["status"] == native.COMPLETE
    assert result["outcome"]["completed_raw_bag_count"] == 1
    assert result["safety"]["pass"] is True
    assert result["timing"]["status"] == (
        "NOT_MEASURED_FULL_POPULATION_INCOMPLETE"
    )
    assert result["comparison_contract"]["capacity"][
        "raw_bag_denominator"
    ] == 2


def test_resume_dry_run_persists_case_and_partial_aggregate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = "t5_2_nanning_1x_speed_2"
    case_root = tmp_path / "cases"

    def fake_execute(selected: str, **_kwargs: Any) -> dict[str, Any]:
        return {
            "schema": native.SCHEMA,
            "status": native.DRY_RUN_READY,
            "case_id": selected,
        }

    monkeypatch.setattr(native, "execute_case", fake_execute)
    code = native.main(
        [
            "resume",
            "--case-id",
            case_id,
            "--case-root",
            str(case_root),
            "--dry-run",
        ]
    )

    assert code == 0
    assert (case_root / f"{case_id}.json").is_file()
    aggregate = json.loads((case_root / "aggregate.json").read_text())
    assert aggregate["status"] == "PARTIAL"
    assert aggregate["dry_run_ready_case_ids"] == [case_id]
    assert aggregate["campaign_manifest"]["primary_case_count"] == 40
    assert aggregate["campaign_manifest"]["observation_bias_context_count"] == 12
