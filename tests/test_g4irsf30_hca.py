from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf30_hca as g30


def _workload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> g30.Workload:
    # Keep fixtures tiny while exercising the same fixed-count checks.
    monkeypatch.setattr(g30, "EXPECTED_RAW_TASKS", 2)
    monkeypatch.setattr(g30, "EXPECTED_SEGMENTS", 3)
    monkeypatch.setattr(g30, "EXPECTED_FLIGHTS", 3)

    raw = tmp_path / "inputdata_3x.txt"
    canonical = tmp_path / "inputdata_3x.jsonl"
    manifest = tmp_path / "manifest.json"
    raw.write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "10 8267.5 22200 3 49 1 C2\n"
        "11 8268.5 30000 4 48 2 C1\n",
        encoding="utf-8",
    )
    rows = [
        {"segment_id": "10:direct", "task_id": 10},
        {"segment_id": "11:storage_in", "task_id": 11},
        {"segment_id": "11:storage_out", "task_id": 11},
    ]
    canonical.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    manifest.write_text(
        json.dumps(
            {
                "schema": g30.WORKLOAD_SCHEMA,
                "status": "COMPLETE",
                "protocol": g30.WORKLOAD_PROTOCOL,
                "raw_task_count": 2,
                "expanded_segment_count": 3,
                "flight_count": 3,
            }
        ),
        encoding="utf-8",
    )
    return g30.load_workload(raw, canonical, manifest)


def _args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        output_root=tmp_path / "hca",
        map_path=Path("map2.txt"),
        classes_dir=tmp_path / "classes",
        java="java",
        javac="javac",
        timeout_seconds=0,
        skip_compile=True,
        force=False,
        include_archived_probe=False,
    )


def test_registry_is_reused_with_four_two_repeat_speeds_and_one_archived_fault() -> None:
    cases = g30.hca_cases()
    assert cases == g30.g29.hca_cases()

    speeds = [case for case in cases if case.case_group == "stable_speed"]
    faults = [case for case in cases if case.case_group == "all_day_line_interruption"]
    assert [case.speed_mps for case in speeds] == [1.5, 2.0, 2.5, 3.0]
    assert all(case.repeats == 2 for case in speeds)
    assert len(faults) == 16
    assert sum(not case.archived_only for case in faults) == 15
    assert [case.case_id for case in faults if case.archived_only] == [
        "t5_5_fault_pair_5_7"
    ]
    assert 4 * 2 + 15 == 23


def test_workload_requires_registered_protocol_population_and_unique_raw_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    assert workload.raw_task_count == 2
    assert workload.expanded_segment_count == 3

    manifest = json.loads(workload.manifest_path.read_text(encoding="utf-8"))
    manifest["protocol"] = "NAIVE_SEGMENT_TRIPLICATION"
    workload.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(g30.G30HcaError, match="registered COMPLETE 3x cohort"):
        g30.load_workload(
            workload.raw_input, workload.canonical_input, workload.manifest_path
        )

    manifest["protocol"] = g30.WORKLOAD_PROTOCOL
    workload.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    workload.raw_input.write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "10 8267.5 22200 3 49 1 C2\n"
        "10 8268.5 30000 4 48 2 C1\n",
        encoding="utf-8",
    )
    with pytest.raises(g30.G30HcaError, match="task_ID uniqueness"):
        g30.load_workload(
            workload.raw_input, workload.canonical_input, workload.manifest_path
        )


def test_default_contract_is_exactly_the_registered_3x_population() -> None:
    assert g30.EXPECTED_RAW_TASKS == 85_518
    assert g30.EXPECTED_SEGMENTS == 130_809
    assert g30.EXPECTED_FLIGHTS == 1_080
    assert g30.START_EPOCH == 8_260
    assert g30.MAX_EPOCHS == 90_000
    assert g30.END_EPOCH == 98_259


def test_dry_run_has_23_primary_processes_and_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    payload = g30.dry_run_payload(_args(tmp_path), workload)

    assert payload["schema"] == g30.CAMPAIGN_SCHEMA
    assert payload["status"] == "DRY_RUN_NO_CASE_STARTED"
    assert payload["workload"]["protocol"] == g30.WORKLOAD_PROTOCOL
    assert payload["protocol"]["start_epoch"] == 8_260
    assert payload["protocol"]["max_epochs"] == 90_000
    assert payload["protocol"]["end_epoch"] == 98_259
    assert payload["protocol"]["primary_executable_case_count"] == 19
    assert payload["protocol"]["primary_process_run_count"] == 23
    assert payload["protocol"]["archived_only_probe_case_ids"] == [
        "t5_5_fault_pair_5_7"
    ]
    assert len(payload["cases"]) == 20
    assert sum(len(case["commands"]) for case in payload["cases"]) == 23
    archived = next(case for case in payload["cases"] if case["archived_only"])
    assert archived["commands"] == []
    assert archived["dry_run_execution_status"] == "ARCHIVED_ONLY_NOT_EXECUTED"
    speed = next(
        case for case in payload["cases"] if case["case_id"] == "t5_2_speed_1p5"
    )
    benchmark = speed["commands"][0].index("LegacyIcsNoFaultWindowBenchmark")
    assert speed["commands"][0][benchmark + 3 : benchmark + 6] == [
        "8260",
        "90000",
        "0",
    ]


def test_case_delegates_to_g29_g24_runner_without_copying_hca(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    args = _args(tmp_path)
    captured: list[argparse.Namespace] = []
    monkeypatch.setattr(g30.g24, "run_campaign", lambda value: captured.append(value) or 0)

    case = g30.case_by_id("t5_5_fault_single_2")
    assert g30.run_case(args, workload, case) == 0
    delegated = captured[0]
    assert delegated.profile == "full"
    assert delegated.input_path == workload.raw_input
    assert delegated.canonical_input == workload.canonical_input
    assert delegated.start_epoch == 8_260
    assert delegated.max_epochs == 90_000
    assert delegated.max_new_tasks == 0
    assert delegated.repeats == 1
    assert delegated.cleanup_epoch_files is True
    assert delegated.fault_schedule == "8260:8:11:fault"

    protocol = json.loads(
        (args.output_root / case.case_id / "case_protocol.json").read_text(
            encoding="utf-8"
        )
    )
    assert protocol["schema"] == g30.CASE_PROTOCOL_SCHEMA
    assert protocol["claim_boundary"] == "G30_3X_PRIMARY_HCA_FIXED_POPULATION_CAPACITY"


def _completed_run(
    run_dir: Path, workload: g30.Workload, case: g30.HcaCase
) -> dict:
    run_dir.mkdir(parents=True)
    (run_dir / "release.csv").write_text(
        "ordinal,task_id,start,goal,release_epoch\n"
        "1,10,3,49,8268\n2,11,4,47,8269\n3,11,52,48,27300\n",
        encoding="utf-8",
    )
    (run_dir / "routes.csv").write_text(
        "ordinal,task_id,start,goal,epoch,finish_time,path\n", encoding="utf-8"
    )
    (run_dir / "summary.csv").write_text(
        "repeat,speed_mps\n1,2.5\n", encoding="utf-8"
    )
    (run_dir / "run_status.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "start_epoch": 8_260,
                "max_epochs": 90_000,
                "speed_mps": case.speed_mps,
                "fault_schedule": case.fault_schedule,
                "wall_seconds": 10.0,
            }
        ),
        encoding="utf-8",
    )
    value = {
        "comparison_eligible": True,
        "canonical_segment_count": workload.expanded_segment_count,
        "canonical_raw_bag_count": workload.raw_task_count,
        "released_segment_count": workload.expanded_segment_count,
        "planned_segment_count": workload.expanded_segment_count,
        "completed_segment_count": workload.expanded_segment_count,
        "canonical_complete_raw_bag_count": workload.raw_task_count,
        "canonical_success_rate": 1.0,
        "benchmark_summary": {
            "fault_event_count": str(len(case.seed_edges)),
            "repair_event_count": "0",
            "epochs_run": "90000",
        },
        "denominators": {
            "processed_attempt": {
                "minutes": {
                    "min": 2.0,
                    "p50": 2.5,
                    "mean": 3.0,
                    "p95": 4.0,
                    "p99": 4.5,
                    "max": 5.0,
                }
            }
        },
    }
    (run_dir / "metrics.json").write_text(json.dumps(value), encoding="utf-8")
    return value


def test_speed_full_release_partial_completion_remains_capacity_primary_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    case = g30.case_by_id("t5_2_speed_2p5")
    case_root = tmp_path / "hca" / case.case_id
    runs = [
        _completed_run(case_root / "run_01", workload, case),
        _completed_run(case_root / "run_02", workload, case),
    ]
    for run in runs:
        run.update(
            {
                "comparison_eligible": False,
                "completed_segment_count": workload.expanded_segment_count - 1,
                "canonical_complete_raw_bag_count": workload.raw_task_count - 1,
                "canonical_success_rate": 0.5,
            }
        )
    monkeypatch.setattr(
        g30.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": runs},
    )

    row = g30._complete_case_row(case, workload, case_root)
    assert row["protocol_status"] == "FIXED_HORIZON_END_TO_END_CAPACITY"
    assert row["primary_capacity_eligible"] is True
    assert row["counts_consistent_across_repeats"] is True
    assert row["full_release_observed"] is True
    assert row["full_completion_eligible"] is False
    assert row["fixed_raw_bag_denominator"] == 2
    assert row["formal_timing_comparison_allowed"] is False
    assert row["timing_scope"] == "CENSORED_COMPLETED_SURVIVORS_SECONDARY"
    assert row["processed_attempt_mean_minutes_by_repeat"] == [None, None]
    assert row["secondary_censored_processed_attempt_mean_minutes_by_repeat"] == [
        3.0,
        3.0,
    ]
    assert row["survivor_timing_drives_verdict"] is False


def test_speed_partial_release_is_fixed_window_capacity_when_repeat_counts_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    case = g30.case_by_id("t5_2_speed_2p5")
    case_root = tmp_path / "hca" / case.case_id
    runs = [
        _completed_run(case_root / "run_01", workload, case),
        _completed_run(case_root / "run_02", workload, case),
    ]
    for run in runs:
        run.update(
            {
                "comparison_eligible": False,
                "released_segment_count": 2,
                "planned_segment_count": 1,
                "completed_segment_count": 1,
                "canonical_complete_raw_bag_count": 1,
                "canonical_success_rate": 0.5,
            }
        )
    monkeypatch.setattr(
        g30.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": runs},
    )

    row = g30._complete_case_row(case, workload, case_root)
    assert row["protocol_status"] == "FIXED_HORIZON_END_TO_END_CAPACITY"
    assert row["primary_capacity_eligible"] is True
    assert row["released_segment_count_by_repeat"] == [2, 2]
    assert row["planned_segment_count_by_repeat"] == [1, 1]
    assert row["completed_segment_count_by_repeat"] == [1, 1]
    assert row["canonical_complete_raw_bag_count_by_repeat"] == [1, 1]
    assert row["full_release_observed"] is False
    assert row["full_completion_eligible"] is False
    assert row["formal_timing_comparison_allowed"] is False
    assert row["secondary_censored_processed_attempt_mean_minutes_by_repeat"] == [
        3.0,
        3.0,
    ]
    assert row["common_release_cohort_observed"] is True
    assert row["common_release_segment_count"] == 2
    assert row["common_release_cohort_drives_capacity_verdict"] is False


def test_release_trace_mismatch_is_diagnostic_not_a_capacity_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    case = g30.case_by_id("t5_2_speed_2")
    case_root = tmp_path / "hca" / case.case_id
    runs = [
        _completed_run(case_root / "run_01", workload, case),
        _completed_run(case_root / "run_02", workload, case),
    ]
    for run in runs:
        run.update(
            {
                "comparison_eligible": False,
                "released_segment_count": 2,
                "planned_segment_count": 1,
                "completed_segment_count": 1,
                "canonical_complete_raw_bag_count": 1,
                "canonical_success_rate": 0.5,
            }
        )
    (case_root / "run_02" / "release.csv").write_text(
        "ordinal,task_id,start,goal,release_epoch\n"
        "1,10,3,49,8270\n2,11,4,47,8269\n3,11,52,48,27300\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        g30.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": runs},
    )

    row = g30._complete_case_row(case, workload, case_root)
    assert row["release_repeat_match"] is False
    assert row["common_release_cohort_observed"] is False
    assert row["primary_capacity_eligible"] is True
    assert row["protocol_status"] == "FIXED_HORIZON_END_TO_END_CAPACITY"


def test_repeat_count_mismatch_blocks_stable_capacity_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    case = g30.case_by_id("t5_2_speed_1p5")
    case_root = tmp_path / "hca" / case.case_id
    runs = [
        _completed_run(case_root / "run_01", workload, case),
        _completed_run(case_root / "run_02", workload, case),
    ]
    for run in runs:
        run.update(
            {
                "comparison_eligible": False,
                "released_segment_count": 2,
                "planned_segment_count": 1,
                "completed_segment_count": 1,
                "canonical_complete_raw_bag_count": 1,
                "canonical_success_rate": 0.5,
            }
        )
    runs[1]["released_segment_count"] = 1
    monkeypatch.setattr(
        g30.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": runs},
    )

    row = g30._complete_case_row(case, workload, case_root)
    assert row["counts_consistent_across_repeats"] is False
    assert row["primary_capacity_eligible"] is False
    assert row["protocol_status"] == "INVALID_OR_PARTIAL"


def test_campaign_reinterprets_completed_partial_release_speed_as_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    case = g30.case_by_id("t5_2_speed_2p5")
    case_root = tmp_path / "hca" / case.case_id
    runs = [
        _completed_run(case_root / "run_01", workload, case),
        _completed_run(case_root / "run_02", workload, case),
    ]
    for run in runs:
        run.update(
            {
                "comparison_eligible": False,
                "released_segment_count": 2,
                "planned_segment_count": 1,
                "completed_segment_count": 1,
                "canonical_complete_raw_bag_count": 1,
                "canonical_success_rate": 0.5,
            }
        )
    monkeypatch.setattr(
        g30.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": runs},
    )

    campaign = g30.aggregate_campaign(workload, tmp_path / "hca")
    row = next(
        value for value in campaign["rows"] if value["case_id"] == case.case_id
    )
    assert row["protocol_status"] == "FIXED_HORIZON_END_TO_END_CAPACITY"
    assert row["primary_capacity_eligible"] is True
    assert case.case_id not in campaign["invalid_primary_case_ids"]
    assert campaign["primary_complete_case_count"] == 1
    assert len(campaign["missing_primary_case_ids"]) == 18


def test_speed_timing_is_formal_only_after_full_population_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    case = g30.case_by_id("t5_2_speed_3")
    case_root = tmp_path / "hca" / case.case_id
    runs = [
        _completed_run(case_root / "run_01", workload, case),
        _completed_run(case_root / "run_02", workload, case),
    ]
    monkeypatch.setattr(
        g30.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": runs},
    )

    row = g30._complete_case_row(case, workload, case_root)
    assert row["protocol_status"] == "EXACT_FULL_COMPLETION"
    assert row["full_release_observed"] is True
    assert row["full_raw_bag_completion_observed"] is True
    assert row["formal_timing_comparison_allowed"] is True
    assert row["timing_scope"] == "FULL_POPULATION"
    assert row["processed_attempt_mean_minutes_by_repeat"] == [3.0, 3.0]


def test_fault_fixed_window_capacity_accepts_partial_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    case = g30.case_by_id("t5_5_fault_single_2")
    case_root = tmp_path / "hca" / case.case_id
    run = _completed_run(case_root / "run_01", workload, case)
    run.update(
        {
            "comparison_eligible": False,
            "released_segment_count": 2,
            "planned_segment_count": 1,
            "completed_segment_count": 1,
            "canonical_complete_raw_bag_count": 0,
            "canonical_success_rate": 0.0,
        }
    )
    monkeypatch.setattr(
        g30.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": [run]},
    )

    row = g30._complete_case_row(case, workload, case_root)
    assert row["protocol_status"] == "FIXED_HORIZON_END_TO_END_CAPACITY"
    assert row["primary_capacity_eligible"] is True
    assert row["formal_timing_comparison_allowed"] is False
    assert row["timing_scope"] == "CAPACITY_ONLY_TABLE_5_5"


def test_fault_capacity_keeps_the_registered_fault_event_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    case = g30.case_by_id("t5_5_fault_single_2")
    case_root = tmp_path / "hca" / case.case_id
    run = _completed_run(case_root / "run_01", workload, case)
    run["benchmark_summary"]["fault_event_count"] = "0"
    monkeypatch.setattr(
        g30.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": [run]},
    )

    row = g30._complete_case_row(case, workload, case_root)
    assert row["primary_capacity_eligible"] is False
    assert row["protocol_status"] == "INVALID_OR_PARTIAL"


def test_fault_full_completion_remains_a_capacity_not_timing_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path, monkeypatch)
    case = g30.case_by_id("t5_5_fault_single_2")
    case_root = tmp_path / "hca" / case.case_id
    run = _completed_run(case_root / "run_01", workload, case)
    monkeypatch.setattr(
        g30.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": [run]},
    )

    row = g30._complete_case_row(case, workload, case_root)
    assert row["full_release_observed"] is True
    assert row["full_raw_bag_completion_observed"] is True
    assert row["primary_capacity_eligible"] is True
    assert row["full_completion_eligible"] is False
    assert row["formal_timing_comparison_allowed"] is False
    assert row["protocol_status"] == "FIXED_HORIZON_END_TO_END_CAPACITY"
    assert row["timing_scope"] == "CAPACITY_ONLY_TABLE_5_5"
    assert row["secondary_timing_censored"] is False


def test_empty_aggregate_is_portable_and_pair_5_7_is_not_a_missing_primary(
    tmp_path: Path,
) -> None:
    workload = g30.Workload(
        raw_input=g30.DEFAULT_RAW_INPUT,
        canonical_input=g30.DEFAULT_CANONICAL_INPUT,
        manifest_path=g30.DEFAULT_WORKLOAD_MANIFEST,
        raw_task_count=g30.EXPECTED_RAW_TASKS,
        expanded_segment_count=g30.EXPECTED_SEGMENTS,
        manifest={"flight_count": g30.EXPECTED_FLIGHTS},
    )
    value = g30.aggregate_campaign(workload, tmp_path / "empty")
    archived = next(
        row for row in value["rows"] if row["case_id"] == "t5_5_fault_pair_5_7"
    )

    assert value["schema"] == g30.CAMPAIGN_SCHEMA
    assert value["protocol"]["fixed_raw_bag_denominator"] == 85_518
    assert value["protocol"]["fixed_segment_population"] == 130_809
    assert value["protocol"]["timing_claim"] == "FULL_POPULATION_ONLY"
    assert value["workload"]["raw_input"].startswith("artifacts/tasks/g4irsf30/")
    assert str(g30.ROOT) not in json.dumps(value)
    assert archived["protocol_status"] == "ARCHIVED_ONLY_NOT_EXECUTED"
    assert "t5_5_fault_pair_5_7" not in value["missing_primary_case_ids"]
    assert len(value["missing_primary_case_ids"]) == 19


def test_resume_dispatches_selected_case_without_compiling_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = g30.Workload(
        raw_input=tmp_path / "raw.txt",
        canonical_input=tmp_path / "canonical.jsonl",
        manifest_path=tmp_path / "manifest.json",
        raw_task_count=85_518,
        expanded_segment_count=130_809,
        manifest={"flight_count": 1_080},
    )
    dispatched: list[str] = []
    monkeypatch.setattr(g30, "_workload_from_args", lambda args: workload)
    monkeypatch.setattr(
        g30,
        "run_case",
        lambda args, current, case, skip_compile: dispatched.append(case.case_id) or 0,
    )
    monkeypatch.setattr(
        g30,
        "aggregate_campaign",
        lambda current, root: {
            "status": "PARTIAL_OR_INVALID",
            "missing_primary_case_ids": [],
            "invalid_primary_case_ids": [],
            "rows": [],
        },
    )
    monkeypatch.setattr(g30, "write_aggregate", lambda *args: None)
    monkeypatch.setattr(
        g30.g24,
        "compile_java",
        lambda *args: pytest.fail("--skip-compile must not compile Java"),
    )

    code = g30.main(
        [
            "resume",
            "--skip-compile",
            "--case-id",
            "t5_2_speed_2p5",
            "--output-root",
            str(tmp_path / "hca"),
            "--aggregate-json",
            str(tmp_path / "aggregate.json"),
            "--aggregate-csv",
            str(tmp_path / "aggregate.csv"),
        ]
    )
    assert code == 0
    assert dispatched == ["t5_2_speed_2p5"]
