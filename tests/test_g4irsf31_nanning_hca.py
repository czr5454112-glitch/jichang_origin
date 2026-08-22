from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf31_nanning_hca as hca


def _workload(tmp_path: Path, scale: int = 1) -> hca.Workload:
    root = tmp_path / "tasks"
    root.mkdir(exist_ok=True)
    return hca.Workload(
        scale=scale,
        raw_input=root / f"nanning_{scale}x_raw.txt",
        canonical_input=root / f"nanning_{scale}x_canonical.jsonl",
        manifest_path=root / f"nanning_{scale}x_manifest.json",
        raw_task_count=2 * scale,
        expanded_segment_count=3 * scale,
        storage_in_goal=53,
        storage_out_start=53,
        early_threshold_seconds=4_800.0,
        storage_lead_seconds=2_700.0,
        map_id="nanning-fixture",
    )


def _args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        map_path=tmp_path / "nanning_legacy.txt",
        classes_dir=tmp_path / "classes",
        output_root=tmp_path / "hca",
        java="java",
        javac="javac",
        timeout_seconds=0,
        skip_compile=True,
        force=False,
    )


def test_default_registry_is_two_scales_by_four_speeds_and_two_repeats() -> None:
    cases = hca.hca_cases()
    assert len(cases) == 8
    assert {case.scale for case in cases} == {1, 2}
    assert {case.speed_mps for case in cases} == {1.5, 2.0, 2.5, 3.0}
    assert {case.repeats for case in cases} == {2}
    assert hca.START_EPOCH == 8_260
    assert hca.MAX_EPOCHS == 90_000
    assert hca.END_EPOCH == 98_259


def test_load_workload_uses_frozen_same_node_storage_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = tmp_path / "tasks"
    task_dir.mkdir()
    (task_dir / "nanning_1x_raw.txt").write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "1 8261 9000 0 1 U L\n2 8262 9001 0 1 U L\n",
        encoding="utf-8",
    )
    (task_dir / "nanning_1x_canonical.jsonl").write_text(
        '{"task_id":1}\n{"task_id":2}\n{"task_id":2}\n', encoding="utf-8"
    )
    (task_dir / "nanning_1x_manifest.json").write_text(
        json.dumps(
            {
                "schema": hca.WORKLOAD_SCHEMA,
                "status": "COMPLETE",
                "scale": 1,
                "map_id": "nanning-fixture",
                "raw_task_count": 2,
                "expanded_segment_count": 3,
                "lifecycle": {
                    "storage_in_goal": 53,
                    "storage_out_start": 53,
                    "early_bag_threshold_seconds": 4_800.0,
                    "storage_out_lead_seconds": 2_700.0,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(hca.EXPECTED_POPULATIONS, 1, (2, 3))

    workload = hca.load_workload(task_dir, 1)
    assert workload.storage_in_goal == workload.storage_out_start == 53
    assert workload.raw_task_count == 2
    assert workload.expanded_segment_count == 3


def test_dry_run_has_16_processes_and_passes_nanning_roles(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path)
    workloads = {1: _workload(tmp_path, 1), 2: _workload(tmp_path, 2)}
    cases = hca.hca_cases()

    payload = hca.dry_run_payload(args, workloads, cases)
    assert payload["status"] == "DRY_RUN_NO_CASE_STARTED"
    assert payload["protocol"]["case_count"] == 8
    assert payload["protocol"]["stable_repeats_per_case"] == 2
    assert payload["protocol"]["fault_repeats_per_case"] == 1
    assert payload["protocol"]["process_count"] == 16
    assert sum(len(row["commands"]) for row in payload["cases"]) == 16
    command = payload["cases"][0]["commands"][0]
    benchmark = command.index("LegacyIcsNoFaultWindowBenchmark")
    assert command[benchmark + 3 : benchmark + 6] == ["8260", "90000", "0"]
    assert command[-5:] == ["1.5", "53", "53", "4800.0", "2700.0"]


def test_case_delegates_to_g24_with_manifest_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = _args(tmp_path)
    workload = _workload(tmp_path)
    case = hca.speed_cases((1,))[2]
    captured: list[argparse.Namespace] = []
    monkeypatch.setattr(hca.g24, "run_campaign", lambda value: captured.append(value) or 0)

    assert hca.run_case(args, workload, case) == 0
    delegated = captured[0]
    assert delegated.map_path == args.map_path
    assert delegated.input_path == workload.raw_input
    assert delegated.canonical_input == workload.canonical_input
    assert delegated.storage_in_goal == delegated.storage_out_start == 53
    assert delegated.start_epoch == 8_260
    assert delegated.max_epochs == 90_000
    assert delegated.repeats == 2
    assert delegated.speed_mps == 2.5


def _completed_run_dir(
    path: Path, case: hca.HcaCase, workload: hca.Workload
) -> None:
    path.mkdir(parents=True)
    for name in ("release.csv", "routes.csv", "summary.csv"):
        (path / name).write_text("\n", encoding="utf-8")
    (path / "run_status.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "start_epoch": hca.START_EPOCH,
                "max_epochs": hca.MAX_EPOCHS,
                "speed_mps": case.speed_mps,
                "fault_schedule": case.fault_schedule,
                "storage_in_goal": workload.storage_in_goal,
                "storage_out_start": workload.storage_out_start,
            }
        ),
        encoding="utf-8",
    )


def _metrics(
    workload: hca.Workload, *, complete_bags: int, full: bool
) -> dict:
    return {
        "canonical_segment_count": workload.expanded_segment_count,
        "canonical_raw_bag_count": workload.raw_task_count,
        "comparison_eligible": full,
        "released_segment_count": workload.expanded_segment_count if full else 2,
        "planned_segment_count": workload.expanded_segment_count if full else 1,
        "completed_segment_count": workload.expanded_segment_count if full else 1,
        "canonical_complete_raw_bag_count": complete_bags,
        "benchmark_summary": {
            "epochs_run": "90000",
            "fault_event_count": "0",
            "repair_event_count": "0",
        },
        "denominators": {
            "processed_attempt": {
                "minutes": {
                    "min": 1.0,
                    "p50": 2.0,
                    "mean": 3.0,
                    "p95": 4.0,
                    "p99": 5.0,
                    "max": 6.0,
                }
            }
        },
    }


def test_partial_release_reports_only_fixed_denominator_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path)
    case = hca.speed_cases((1,))[0]
    case_root = tmp_path / "hca" / case.case_id
    for repeat in (1, 2):
        _completed_run_dir(case_root / f"run_{repeat:02d}", case, workload)
    runs = [_metrics(workload, complete_bags=1, full=False) for _ in range(2)]
    monkeypatch.setattr(hca.g24, "aggregate_campaign", lambda *args: {"runs": runs})

    row = hca._complete_case_row(case, workload, case_root)
    assert row["protocol_status"] == "FIXED_HORIZON_CAPACITY"
    assert row["primary_capacity_eligible"] is True
    assert row["fixed_raw_bag_denominator"] == 2
    assert row["completed_raw_bag_count_by_repeat"] == [1, 1]
    assert row["fixed_denominator_completion_rate_by_repeat"] == [0.5, 0.5]
    assert row["formal_timing_comparison_allowed"] is False
    assert row["timing_scope"] == "NOT_REPORTED"
    assert row["processed_attempt_mean_minutes_by_repeat"] == [None, None]


def test_full_population_is_the_only_speed_timing_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path)
    case = hca.speed_cases((1,))[-1]
    case_root = tmp_path / "hca" / case.case_id
    for repeat in (1, 2):
        _completed_run_dir(case_root / f"run_{repeat:02d}", case, workload)
    runs = [
        _metrics(workload, complete_bags=workload.raw_task_count, full=True)
        for _ in range(2)
    ]
    monkeypatch.setattr(hca.g24, "aggregate_campaign", lambda *args: {"runs": runs})

    row = hca._complete_case_row(case, workload, case_root)
    assert row["protocol_status"] == "FULL_POPULATION_TIMING"
    assert row["full_population_completion"] is True
    assert row["formal_timing_comparison_allowed"] is True
    assert row["timing_scope"] == "FULL_POPULATION"
    assert row["processed_attempt_mean_minutes_by_repeat"] == [3.0, 3.0]


def test_fault_cases_are_optional_and_all_16_are_primary_per_scale(
    tmp_path: Path,
) -> None:
    scenarios = [
        {
            "scenario": f"scenario_{index}",
            "line_ids": [index],
            "fault_edges": [[index, index + 1]],
            "topology_upper_raw_bags": 100 - index,
        }
        for index in range(1, 17)
    ]
    protocol = tmp_path / "faults.json"
    protocol.write_text(
        json.dumps(
            {
                "schema": hca.FAULT_PROTOCOL_SCHEMA,
                "scales": {"1x": {"scenarios": scenarios}},
            }
        ),
        encoding="utf-8",
    )

    assert len(hca.hca_cases(scales=(1,))) == 4
    cases = hca.hca_cases(
        include_faults=True, fault_protocol=protocol, scales=(1,)
    )
    faults = [case for case in cases if case.case_group == "all_day_line_interruption"]
    assert len(faults) == 16
    assert all(case.repeats == 1 for case in faults)
    pair = faults[4]
    assert pair.fault_schedule.startswith("8260:")

    payload = hca.dry_run_payload(
        _args(tmp_path), {1: _workload(tmp_path)}, cases
    )
    fault_rows = [
        row
        for row in payload["cases"]
        if row["case_group"] == "all_day_line_interruption"
    ]
    assert payload["protocol"]["stable_repeats_per_case"] == 2
    assert payload["protocol"]["fault_repeats_per_case"] == 1
    assert payload["protocol"]["process_count"] == 24
    assert sum(len(row["commands"]) for row in fault_rows) == 16
    assert all(len(row["commands"]) == 1 for row in fault_rows)


def test_empty_aggregate_is_small_and_portable(tmp_path: Path) -> None:
    workload = hca.Workload(
        scale=1,
        raw_input=hca.TASK_DIR / "nanning_1x_raw.txt",
        canonical_input=hca.TASK_DIR / "nanning_1x_canonical.jsonl",
        manifest_path=hca.TASK_DIR / "nanning_1x_manifest.json",
        raw_task_count=28_506,
        expanded_segment_count=43_603,
        storage_in_goal=53,
        storage_out_start=53,
        early_threshold_seconds=4_800.0,
        storage_lead_seconds=2_700.0,
        map_id="nanning",
    )
    value = hca.aggregate_campaign(
        {1: workload}, tmp_path / "empty", hca.speed_cases((1,))
    )
    encoded = json.dumps(value)
    assert value["status"] == "PARTIAL_OR_INVALID"
    assert value["protocol"]["expected_case_count"] == 4
    assert len(value["missing_case_ids"]) == 4
    assert str(hca.ROOT) not in encoded
    assert value["workloads"]["1x"]["raw_input"].startswith(
        "artifacts/tasks/g4irsf31_nanning/"
    )


def test_resume_dispatches_selected_case_without_compiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path)
    dispatched: list[str] = []
    monkeypatch.setattr(hca, "load_workloads", lambda task_dir, scales: {1: workload})
    monkeypatch.setattr(
        hca,
        "run_case",
        lambda args, current, case, skip_compile: dispatched.append(case.case_id) or 0,
    )
    monkeypatch.setattr(
        hca,
        "aggregate_campaign",
        lambda *args: {
            "status": "PARTIAL_OR_INVALID",
            "invalid_case_ids": [],
            "rows": [],
        },
    )
    monkeypatch.setattr(hca, "write_aggregate", lambda *args: None)
    monkeypatch.setattr(
        hca.g24,
        "compile_java",
        lambda *args: pytest.fail("--skip-compile must not compile Java"),
    )

    case_id = "nanning_1x_t5_2_speed_2p5"
    assert (
        hca.main(
            [
                "resume",
                "--skip-compile",
                "--scale",
                "1",
                "--case-id",
                case_id,
                "--output-root",
                str(tmp_path / "hca"),
            ]
        )
        == 0
    )
    assert dispatched == [case_id]
