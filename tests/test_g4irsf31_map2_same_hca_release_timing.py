from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import g4irsf31_map_adapter as map_adapter
from scripts.eval import run_g4irsf31_map2_same_hca_release_timing as paired


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def _fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    monkeypatch.setattr(
        paired.map2_native, "SCALE_COUNTS", {1: (2, 3), 2: (4, 6)}
    )
    monkeypatch.setattr(
        paired.map2_native.g31_native,
        "SCALE_COUNTS",
        {1: (2, 3), 2: (4, 6)},
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
    monkeypatch.setattr(paired.map2_native, "map2_profile", lambda: profile)
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


def _hca_case_root(
    root: Path,
    workload: paired.map2_native.Workload,
    *,
    speed: float,
    full: bool = True,
    repeat_release_mismatch: bool = False,
) -> Path:
    for repeat in (1, 2):
        run_id = f"run_{repeat:02d}"
        run = root / run_id
        run.mkdir(parents=True)
        (run / "run_status.json").write_text(
            json.dumps(
                {
                    "schema": "g4irsf24.fresh_hca.run.v1",
                    "status": "complete",
                    "returncode": 0,
                    "run_id": run_id,
                    "start_epoch": 8260,
                    "max_epochs": 90000,
                    "profile": "full",
                }
            ),
            encoding="utf-8",
        )
        lifecycle = ["segment_id,release_epoch"]
        for index, row in enumerate(workload.rows):
            release = float(row["pass_time"]) + 10.0
            if repeat == 2 and repeat_release_mismatch and index == 0:
                release += 1.0
            lifecycle.append(f"{row['segment_id']},{release}")
        (run / "segment_lifecycle.csv").write_text(
            "\n".join(lifecycle) + "\n", encoding="utf-8"
        )
        completed_segments = workload.segment_count if full else workload.segment_count - 1
        completed_raw = workload.raw_bag_count if full else workload.raw_bag_count - 1
        (run / "metrics.json").write_text(
            json.dumps(
                {
                    "schema": "g4irsf24.fresh_hca.metrics.v1",
                    "status": "complete",
                    "run_id": run_id,
                    "canonical_segment_count": workload.segment_count,
                    "canonical_raw_bag_count": workload.raw_bag_count,
                    "released_segment_count": workload.segment_count,
                    "planned_segment_count": workload.segment_count,
                    "completed_segment_count": completed_segments,
                    "canonical_complete_raw_bag_count": completed_raw,
                    "comparison_eligible": full,
                    "survivor_only": not full,
                    "scope": "canonical_full" if full else "survivor_only",
                    "benchmark_summary": {
                        "speed_mps": str(speed),
                        "active_fault_count": "0",
                        "fault_event_count": "0",
                    },
                    "denominators": {
                        "java_release": {
                            "count": workload.raw_bag_count if full else completed_raw,
                            "seconds": {
                                "min": 1.0,
                                "mean": 2.0,
                                "p95": 3.0,
                                "p99": 4.0,
                                "max": 5.0,
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
    return root


def _summary(request: dict[str, Any], *, fail_last: bool = False) -> dict[str, Any]:
    failed = int(fail_last)
    return {
        "completed_count": len(request["bag_records"]) - failed,
        "failed_count": failed,
        "event_count": 20,
        "decision_count": 4,
        "declared_max_events": paired.map2_native.MAX_EVENTS,
        "declared_max_simulation_time": paired.map2_native.FIXED_END_EPOCH,
        "event_limit_reached": False,
        "time_limit_reached": bool(failed),
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
            paired.map2_native.g31_native.GOAL_ARRIVAL_COMPLETION_CLAIM
        ),
    }


def _payload(request: dict[str, Any], *, fail_last: bool = False) -> dict[str, Any]:
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
                "finish_time": release + 0.5 if completed else -1.0,
                "completed": completed,
            }
        )
    return {"summary": _summary(request, fail_last=fail_last), "bags": bags}


def test_formal_hca_run_directories_cover_both_scales_and_four_speeds() -> None:
    assert paired.formal_hca_case_root(1, 1.5).name == "g26_hca_speed_1p5"
    assert paired.formal_hca_case_root(1, 2.5).name == "g4irsf24_fresh_hca_full"
    assert paired.formal_hca_case_root(1, 3.0).name == "g26_hca_speed_3p0"
    assert paired.formal_hca_case_root(2, 2.0).as_posix().endswith(
        "outputs/runtime/g4irsf29_hca/t5_2_speed_2"
    )


def test_formal_g24_default_run_is_identified_as_2p5_without_speed_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = paired.map2_native.case_by_id("t5_2_map2_1x_speed_2p5")
    monkeypatch.setattr(
        paired, "FORMAL_HCA_CASE_ROOTS", {(1, 2.5): tmp_path}
    )

    passed, source = paired._stable_speed_evidence(case, tmp_path, {})

    assert passed is True
    assert source == "formal_g4irsf24_default_map_speed_2p5"


def test_full_repeat_identical_hca_trace_prepares_frozen_map2_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, binary = _fixture(tmp_path, monkeypatch)
    workload = paired.map2_native.load_workload(1, workload_1x, workload_2x)
    hca_root = _hca_case_root(tmp_path / "hca", workload, speed=2.0)

    prepared = paired.prepare_case(
        "t5_2_map2_1x_speed_2",
        workload_1x=workload_1x,
        workload_2x=workload_2x,
        hca_case_root=hca_root,
        binary=binary,
    )

    assert prepared.artifact["status"] == paired.READY
    assert prepared.artifact["hca_release_trace"]["pass"] is True
    assert prepared.artifact["hca_timing"]["pass"] is True
    assert prepared.request is not None
    assert prepared.request["enable_s4_local_potential_descent_guard"] is True
    assert prepared.request[
        "enable_s4_direct_neighbor_merge_calendar_visibility"
    ] is True
    assert prepared.request["complete_on_goal_arrival"] is True
    assert prepared.request["local_queue_capacity"] == 0
    assert prepared.workload is not None
    assert prepared.workload.rows[0]["pass_time"] == 110.0


def test_repeat_release_mismatch_is_strict_na_and_never_builds_s4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, binary = _fixture(tmp_path, monkeypatch)
    workload = paired.map2_native.load_workload(1, workload_1x, workload_2x)
    hca_root = _hca_case_root(
        tmp_path / "hca", workload, speed=2.0, repeat_release_mismatch=True
    )

    prepared = paired.prepare_case(
        "t5_2_map2_1x_speed_2",
        workload_1x=workload_1x,
        workload_2x=workload_2x,
        hca_case_root=hca_root,
        binary=binary,
    )

    assert prepared.artifact["status"] == paired.N_A_REPEAT
    assert prepared.request is None
    assert prepared.artifact["comparison"]["metric_rows"] == []


def test_incomplete_2x_hca_outcome_is_na_without_common_cohort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, binary = _fixture(tmp_path, monkeypatch)
    workload = paired.map2_native.load_workload(2, workload_1x, workload_2x)
    hca_root = _hca_case_root(
        tmp_path / "hca", workload, speed=2.0, full=False
    )

    prepared = paired.prepare_case(
        "t5_2_map2_2x_speed_2",
        workload_1x=workload_1x,
        workload_2x=workload_2x,
        hca_case_root=hca_root,
        binary=binary,
    )

    assert prepared.artifact["hca_release_trace"]["pass"] is True
    assert prepared.artifact["status"] == paired.N_A_HCA_TIMING
    assert prepared.request is None
    assert prepared.artifact["comparison"][
        "survivor_or_common_cohort_comparison_allowed"
    ] is False


def test_fake_full_population_execution_outputs_exactly_five_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, binary = _fixture(tmp_path, monkeypatch)
    workload = paired.map2_native.load_workload(1, workload_1x, workload_2x)
    hca_root = _hca_case_root(tmp_path / "hca", workload, speed=2.5)

    result = paired.execute_case(
        "t5_2_map2_1x_speed_2p5",
        workload_1x=workload_1x,
        workload_2x=workload_2x,
        hca_case_root=hca_root,
        binary=binary,
        executor=lambda **request: _payload(request),
    )

    assert result["status"] == paired.COMPLETE
    assert result["safety"]["pass"] is True
    assert result["paired_s4_timing"]["raw_bag_count"] == 2
    assert set(result["paired_s4_timing"]["metrics_seconds"]) == set(
        paired.METRICS
    )
    assert len(result["comparison"]["metric_rows"]) == 5
    assert result["comparison"]["common_cohort_verdict_used"] is False


def test_incomplete_s4_is_na_and_never_compares_survivors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, binary = _fixture(tmp_path, monkeypatch)
    workload = paired.map2_native.load_workload(1, workload_1x, workload_2x)
    hca_root = _hca_case_root(tmp_path / "hca", workload, speed=3.0)

    result = paired.execute_case(
        "t5_2_map2_1x_speed_3",
        workload_1x=workload_1x,
        workload_2x=workload_2x,
        hca_case_root=hca_root,
        binary=binary,
        executor=lambda **request: _payload(request, fail_last=True),
    )

    assert result["status"] == paired.N_A_S4_TIMING
    assert result["comparison"]["metric_rows"] == []
    assert result["comparison"][
        "survivor_or_common_cohort_comparison_allowed"
    ] is False


def test_cli_dry_run_writes_ready_artifact_without_native(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload_1x, workload_2x, _binary = _fixture(tmp_path, monkeypatch)
    workload = paired.map2_native.load_workload(1, workload_1x, workload_2x)
    hca_root = _hca_case_root(tmp_path / "hca", workload, speed=1.5)
    output = tmp_path / "paired.json"

    assert (
        paired.main(
            [
                "--case-id",
                "t5_2_map2_1x_speed_1p5",
                "--workload-1x",
                str(workload_1x),
                "--workload-2x",
                str(workload_2x),
                "--hca-case-root",
                str(hca_root),
                "--output",
                str(output),
                "--dry-run",
                "--force",
            ]
        )
        == 0
    )
    artifact = json.loads(output.read_text())
    assert artifact["status"] == paired.READY
    assert artifact["native_execution_started"] is False
