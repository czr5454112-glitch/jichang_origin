from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import g4irsf31_map_adapter as map_adapter
from scripts.eval import run_g4irsf31_map2_bias as bias


def _fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[bias.map2_native.Workload, Path, Path]:
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
    workload_1x = tmp_path / "inputdata.jsonl"
    workload_2x = tmp_path / "inputdata_2x.jsonl"
    workload_1x.write_text("fixture\n", encoding="utf-8")
    workload_2x.write_text("fixture\n", encoding="utf-8")
    workloads = {
        scale: bias.map2_native.Workload(
            scale=scale,
            source_path=workload_1x if scale == 1 else workload_2x,
            protocol=f"FIXTURE_MAP2_{scale}X",
            rows=rows,
            raw_bag_count=2,
            segment_count=3,
        )
        for scale in (1, 2)
    }
    monkeypatch.setattr(bias.map2_native, "SCALE_COUNTS", {1: (2, 3), 2: (2, 3)})
    monkeypatch.setattr(
        bias.map2_native.g31_native,
        "SCALE_COUNTS",
        {1: (2, 3), 2: (2, 3)},
    )
    monkeypatch.setattr(
        bias.map2_native,
        "load_workload",
        lambda scale, _one, _two: workloads[scale],
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
    monkeypatch.setattr(bias.map2_native, "map2_profile", lambda: profile)
    monkeypatch.setattr(bias.map2_native, "STORAGE_NODE", 2)
    monkeypatch.setattr(bias.map2_native, "MAP_NODE_COUNT", 4)
    monkeypatch.setattr(bias.map2_native, "MAP_EDGE_COUNT", 4)
    captured_base: dict[str, Any] = {}

    def prepare(
        base_case: bias.map2_native.CaseSpec,
        selected: bias.map2_native.Workload,
        *,
        binary: Path | None,
    ) -> tuple[
        dict[str, Any],
        tuple[dict[str, Any], ...],
        tuple[dict[str, Any], ...],
        dict[str, Any],
    ]:
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
                bias.map2_native.LOCAL_POTENTIAL_DESCENT_GUARD
            ),
            "direct_neighbor_merge_calendar_visibility": dict(
                bias.map2_native.DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
            ),
            "goal_arrival_completion": dict(
                bias.map2_native.GOAL_ARRIVAL_COMPLETION
            ),
        }
        return request, tuple(selected.rows), (), local

    monkeypatch.setattr(bias.map2_native, "prepare_native_request", prepare)
    monkeypatch.setattr(bias, "_TEST_CAPTURED_BASE", captured_base, raising=False)
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.write_bytes(b"fixture")
    return workloads[1], workload_1x, workload_2x


def test_manifest_reuses_the_24_cell_non_exact_protocol() -> None:
    manifest = bias.campaign_manifest()

    assert manifest["case_count"] == 24
    assert manifest["fixed_seed"] == 20_260_816
    assert manifest["fresh_exact_primary_target_eligible"] is False
    assert manifest["cross_map_target_eligible"] is False
    assert {
        row["observation_bias"]["maximum_seconds"] for row in manifest["cases"]
    } == {1.0, 2.0, 3.0}
    assert all(
        row["hca_reference"]["matched_disturbance_comparison"] is False
        and row["hca_reference"]["exact_table_5_4_reproduction"] is False
        for row in manifest["cases"]
    )


def test_prepare_adds_only_the_shared_bias_fields_to_map2_final_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload, _one, _two = _fixture(tmp_path, monkeypatch)
    case = bias.case_by_id("t5_4_map2_1x_std_2p5_dev_20")
    request, runtime_rows, rejected, local = bias.prepare_bias_request(
        case, workload, binary=tmp_path / "czr005_cpp.fake.pyd"
    )

    assert "legacy_observation_bias_max_seconds" not in bias._TEST_CAPTURED_BASE
    assert request["legacy_observation_bias_max_seconds"] == 2.0
    assert request["legacy_observation_bias_seed"] == 20_260_816
    assert {row[3] for row in request["edge_records"]} == {2.5}
    assert request["enable_s4_local_potential_descent_guard"] is True
    assert request["enable_s4_direct_neighbor_merge_calendar_visibility"] is True
    assert request["complete_on_goal_arrival"] is True
    assert request["local_queue_capacity"] == 0
    assert len(runtime_rows) == 3 and not rejected
    assert local["observation_bias"]["learning_active"] is False


def test_resume_dry_runs_all_24_cells_and_keeps_them_out_of_exact_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workload, workload_1x, workload_2x = _fixture(tmp_path, monkeypatch)
    case_root = tmp_path / "cases"
    code = bias.main(
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
    assert aggregate["expected_case_count"] == 24
    assert len(aggregate["dry_run_ready_case_ids"]) == 24
    assert aggregate["fresh_exact_primary_target_eligible"] is False
    assert aggregate["cross_map_target_eligible"] is False
    assert aggregate["status"] == "PARTIAL"

    case_id = bias.CASE_IDS[0]
    path = case_root / f"{case_id}.json"
    stale = json.loads(path.read_text())
    stale["cross_map_target_eligible"] = True
    path.write_text(json.dumps(stale), encoding="utf-8")
    refreshed = bias.aggregate_results(case_root)
    assert refreshed["stale_case_ids"] == [case_id]
    assert len(refreshed["dry_run_ready_case_ids"]) == 23
    with pytest.raises(bias.Map2BiasError, match="stale or incompatible"):
        bias.main(
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
