from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import g4irsf31_map_adapter as map_adapter
from scripts.eval import run_g4irsf31_map2_native as native


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def _fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    monkeypatch.setattr(native, "STORAGE_NODE", 2)
    monkeypatch.setattr(native, "MAP_NODE_COUNT", 4)
    monkeypatch.setattr(native, "MAP_EDGE_COUNT", 4)
    monkeypatch.setattr(native, "SCALE_COUNTS", {1: (2, 3), 2: (4, 6)})
    monkeypatch.setattr(
        native.g31_native, "SCALE_COUNTS", {1: (2, 3), 2: (4, 6)}
    )
    profile = map_adapter.RuntimeMapProfile(
        name="fixture_map2",
        source_path=tmp_path / "map2.json",
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
    monkeypatch.setattr(native, "map2_profile", lambda: profile)
    available_edges = ((0, 2), (0, 1), (1, 3), (2, 3))
    monkeypatch.setattr(
        native,
        "FAULT_SEED_EDGES",
        {
            line_id: available_edges[(line_id - 1) % len(available_edges)]
            for line_id in range(1, 9)
        },
    )

    rows_1x = [
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
    ]
    rows_2x = rows_1x + [
        {
            **row,
            "segment_id": row["segment_id"].replace("1", "2", 1),
            "task_id": row["task_id"] + 10,
        }
        for row in rows_1x
    ]
    workload_1x = tmp_path / "inputdata.jsonl"
    workload_2x = tmp_path / "inputdata_2x.jsonl"
    _write_rows(workload_1x, rows_1x)
    _write_rows(workload_2x, rows_2x)
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.write_bytes(b"fixture")
    return workload_1x, workload_2x, binary


def _summary(request: dict[str, Any]) -> dict[str, Any]:
    result = {
        "completed_count": len(request["bag_records"]),
        "failed_count": 0,
        "event_count": 20,
        "decision_count": 4,
        "declared_max_events": native.MAX_EVENTS,
        "declared_max_simulation_time": native.FIXED_END_EPOCH,
        "event_limit_reached": False,
        "time_limit_reached": False,
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
            native.g31_native.GOAL_ARRIVAL_COMPLETION_CLAIM
        ),
    }
    artifact = request.get("g4irsf24_dlp_artifact")
    if artifact is not None:
        result.update(
            g4irsf24_dlp_mode="td",
            g4irsf24_dlp_edge_residual_count=len(artifact["edge_residuals"]),
            g4irsf24_dlp_value_residual_count=len(artifact["value_residuals"]),
        )
    return result


def _fake_payload(request: dict[str, Any]) -> dict[str, Any]:
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


def test_manifest_has_38_executable_cases_and_explicit_nm() -> None:
    manifest = native.campaign_manifest()

    assert manifest["primary_case_count"] == 38
    assert manifest["stable_speed_case_count"] == 8
    assert manifest["measurable_line_interruption_case_count"] == 30
    assert manifest["not_measurable_case_count"] == 2
    assert all(
        row["status"] == "NM" and row["execution_allowed"] is False
        for row in manifest["not_measurable_cases"]
    )
    assert not any("pair_5_7" in case_id for case_id in native.CASE_IDS)
    with pytest.raises(native.Map2NativeError, match="NM.*not executable"):
        native.case_by_id("t5_5_map2_1x_fault_pair_5_7")


def test_real_map_profile_is_built_from_canonical_data_with_storage_52() -> None:
    profile = native.map2_profile()

    assert profile.source_path == native.CANONICAL_MAP_PATH
    assert len(profile.node_records) == 54
    assert len(profile.edge_records) == 69
    assert profile.storage_source_nodes == (52,)
    assert set(profile.start_nodes) == {0, 1, 2, 3, 4, 5, 52, 53}
    assert set(profile.goal_nodes) == {47, 48, 49, 50, 51}


def test_stable_dry_request_freezes_all_four_final_policy_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, _binary = _fixture(tmp_path, monkeypatch)
    result = native.execute_case(
        "t5_2_map2_1x_speed_2",
        workload_1x=workload_1x,
        workload_2x=workload_2x,
        binary=None,
        dry_run=True,
    )

    assert result["status"] == native.DRY_RUN_READY
    assert result["map_profile"]["builder"] == (
        "canonical_map_data_to_RuntimeMapProfile"
    )
    assert result["map_profile"]["storage_source_nodes"] == [2]
    request = result["request_contract"]
    assert request["edge_speeds_mps"] == [2.0]
    assert request["max_simulation_time"] == 98_259.0
    assert request["max_events"] == 60_000_000
    assert request["local_queue_capacity"] == 0
    assert request["policy"]["local_potential_descent_guard"] == (
        native.LOCAL_POTENTIAL_DESCENT_GUARD
    )
    assert request["policy"]["direct_neighbor_merge_calendar_visibility"] == (
        native.DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
    )
    assert request["policy"]["goal_arrival_completion"] == (
        native.GOAL_ARRIVAL_COMPLETION
    )
    assert request["policy"]["learning_active"] is False


def test_case_and_aggregate_serialize_repo_paths_portably(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, _binary = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(native, "ROOT", tmp_path)
    case_id = "t5_2_map2_1x_speed_2"
    result = native.execute_case(
        case_id,
        workload_1x=workload_1x,
        workload_2x=workload_2x,
        binary=None,
        dry_run=True,
    )

    assert result["map_profile"]["source_path"] == "map2.json"
    assert result["selection"]["workload_source"] == "inputdata.jsonl"

    # Aggregation also normalizes artifacts written by an older runner.
    result["map_profile"]["source_path"] = str(tmp_path / "map2.json")
    result["selection"]["workload_source"] = str(workload_1x)
    case_root = tmp_path / "cases"
    case_root.mkdir()
    (case_root / f"{case_id}.json").write_text(
        json.dumps(result), encoding="utf-8"
    )
    aggregate = native.aggregate_results(case_root)
    assert aggregate["cases"][0]["map_profile"]["source_path"] == "map2.json"
    assert aggregate["cases"][0]["selection"]["workload_source"] == (
        "inputdata.jsonl"
    )


def test_fault_request_reuses_local_fixed_point_and_topology_upper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, binary = _fixture(tmp_path, monkeypatch)
    case = native.case_by_id("t5_5_map2_1x_fault_single_1")
    workload = native.load_workload(1, workload_1x, workload_2x)
    request, runtime_rows, rejected, local = native.prepare_native_request(
        case, workload, binary=binary
    )

    assert [row["segment_id"] for row in rejected] == ["10:storage_in"]
    assert len(runtime_rows) == 2
    assert request["fault_windows"] == [
        (
            0,
            2,
            native.g31_native.FIXED_START_EPOCH,
            native.g31_native.FAULT_REPAIR_EPOCH,
            0.0,
            False,
        )
    ]
    assert request["g4irsf24_dlp_artifact"][
        "deterministic_surviving_graph_values"
    ] is True
    assert local["learned_from_runtime_data"] is False
    assert local["protocol_scenario"]["topology_upper_raw_bags"] == 1
    assert local["protocol_scenario"]["measurement_status"].startswith(
        "MEASURABLE"
    )


def test_fake_native_echo_is_admitted_and_old_policy_artifact_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, binary = _fixture(tmp_path, monkeypatch)
    result = native.execute_case(
        "t5_2_map2_1x_speed_2p5",
        workload_1x=workload_1x,
        workload_2x=workload_2x,
        binary=binary,
        executor=lambda **request: _fake_payload(request),
    )

    assert result["status"] == native.COMPLETE
    assert result["outcome"]["completed_raw_bag_count"] == 2
    assert result["safety"]["pass"] is True
    assert native._artifact_admitted(result) is True
    stale = json.loads(json.dumps(result))
    stale["request_contract"]["policy"].pop("goal_arrival_completion")
    assert native._artifact_admitted(stale) is False


def test_resume_all_dry_cases_and_reject_stale_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, _binary = _fixture(tmp_path, monkeypatch)
    case_root = tmp_path / "cases"
    code = native.main(
        [
            "resume",
            "--workload-1x",
            str(workload_1x),
            "--workload-2x",
            str(workload_2x),
            "--case-root",
            str(case_root),
            "--dry-run",
            "--force",
        ]
    )

    assert code == 0
    aggregate = json.loads((case_root / "aggregate.json").read_text())
    assert aggregate["expected_executable_case_count"] == 38
    assert len(aggregate["dry_run_ready_case_ids"]) == 38
    assert aggregate["not_measurable_case_count"] == 2
    assert aggregate["status"] == "PARTIAL"

    case_id = native.CASE_IDS[0]
    path = case_root / f"{case_id}.json"
    stale = json.loads(path.read_text())
    stale["protocol"] = "OLD_POLICY"
    path.write_text(json.dumps(stale), encoding="utf-8")
    refreshed = native.aggregate_results(case_root)
    assert refreshed["stale_case_ids"] == [case_id]
    assert len(refreshed["dry_run_ready_case_ids"]) == 37
    with pytest.raises(native.Map2NativeError, match="stale or incompatible"):
        native.main(
            [
                "case",
                "--case-id",
                case_id,
                "--workload-1x",
                str(workload_1x),
                "--workload-2x",
                str(workload_2x),
                "--output",
                str(path),
                "--dry-run",
            ]
        )
