from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf29_hca as g29


def _workload(tmp_path: Path) -> g29.Workload:
    raw = tmp_path / "inputdata_2x.txt"
    canonical = tmp_path / "inputdata_2x.jsonl"
    manifest = tmp_path / "manifest.json"
    raw.write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "10 8267.5 22200 3 49 1 C2\n"
        "11 8268.5 30000 4 48 2 C1\n",
        encoding="utf-8",
    )
    rows = [
        {
            "segment_id": "10:direct",
            "task_id": 10,
            "leg": "direct",
            "start": 3,
            "goal": 49,
            "pass_time": 8267.5,
            "original_entry_time": 8267.5,
        },
        {
            "segment_id": "11:storage_in",
            "task_id": 11,
            "leg": "storage_in",
            "start": 4,
            "goal": 47,
            "pass_time": 8268.5,
            "original_entry_time": 8268.5,
        },
        {
            "segment_id": "11:storage_out",
            "task_id": 11,
            "leg": "storage_out",
            "start": 52,
            "goal": 48,
            "pass_time": 27300.0,
            "original_entry_time": 8268.5,
        },
    ]
    canonical.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    manifest.write_text(
        json.dumps(
            {
                "schema": g29.WORKLOAD_SCHEMA,
                "status": "COMPLETE",
                "raw_task_count": 2,
                "expanded_segment_count": 3,
            }
        ),
        encoding="utf-8",
    )
    return g29.load_workload(raw, canonical, manifest)


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


def test_registry_reuses_four_speeds_and_sixteen_fault_cases() -> None:
    cases = g29.hca_cases()
    speeds = [case for case in cases if case.case_group == "stable_speed"]
    faults = [case for case in cases if case.case_group == "all_day_line_interruption"]

    assert len(cases) == 20
    assert [case.speed_mps for case in speeds] == [1.5, 2.0, 2.5, 3.0]
    assert all(case.repeats == 2 for case in speeds)
    assert len(faults) == 16
    assert all(case.repeats == 1 and case.speed_mps == 2.5 for case in faults)
    archived = [case for case in faults if case.archived_only]
    assert [case.case_id for case in archived] == ["t5_5_fault_pair_5_7"]
    assert archived[0].seed_edges == ((33, 44), (46, 36))


def test_workload_contract_rejects_duplicate_java_task_ids(tmp_path: Path) -> None:
    workload = _workload(tmp_path)
    assert workload.raw_task_count == 2
    assert workload.expanded_segment_count == 3

    raw = workload.raw_input
    raw.write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "10 8267.5 22200 3 49 1 C2\n"
        "10 8268.5 30000 4 48 2 C1\n",
        encoding="utf-8",
    )
    with pytest.raises(g29.G29HcaError, match="task_ID uniqueness"):
        g29.load_workload(raw, workload.canonical_input, workload.manifest_path)


def test_dry_run_locks_window_cleanup_and_java_commands(tmp_path: Path) -> None:
    workload = _workload(tmp_path)
    args = _args(tmp_path)
    payload = g29.dry_run_payload(args, workload)

    assert payload["status"] == "DRY_RUN_NO_CASE_STARTED"
    assert payload["protocol"]["start_epoch"] == 8260
    assert payload["protocol"]["max_epochs"] == 90000
    assert payload["protocol"]["end_epoch"] == 98259
    assert payload["protocol"]["cleanup_epoch_files"] is True
    assert len(payload["cases"]) == 20
    speed = next(case for case in payload["cases"] if case["case_id"] == "t5_2_speed_1p5")
    assert len(speed["commands"]) == 2
    benchmark = speed["commands"][0].index("LegacyIcsNoFaultWindowBenchmark")
    assert speed["commands"][0][benchmark + 3 : benchmark + 6] == ["8260", "90000", "0"]
    assert speed["commands"][0][-1] == "1.5"


def test_case_delegates_fixed_protocol_to_g24_without_copying_hca(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path)
    args = _args(tmp_path)
    captured: list[argparse.Namespace] = []

    monkeypatch.setattr(g29.g24, "run_campaign", lambda value: captured.append(value) or 0)
    case = g29.case_by_id("t5_5_fault_single_2")
    assert g29.run_case(args, workload, case) == 0

    delegated = captured[0]
    assert delegated.profile == "full"
    assert delegated.input_path == workload.raw_input
    assert delegated.canonical_input == workload.canonical_input
    assert delegated.start_epoch == 8260
    assert delegated.max_epochs == 90000
    assert delegated.max_new_tasks == 0
    assert delegated.repeats == 1
    assert delegated.cleanup_epoch_files is True
    assert delegated.fault_schedule == "8260:8:11:fault"


def _completed_run(run_dir: Path, workload: g29.Workload, case: g29.HcaCase) -> dict:
    run_dir.mkdir(parents=True)
    (run_dir / "release.csv").write_text(
        "ordinal,task_id,start,goal,release_epoch\n"
        "1,10,3,49,8268\n2,11,4,47,8269\n3,11,52,48,27300\n",
        encoding="utf-8",
    )
    (run_dir / "routes.csv").write_text("ordinal,task_id,start,goal,epoch,finish_time,path\n", encoding="utf-8")
    (run_dir / "summary.csv").write_text("repeat,speed_mps\n1,2.5\n", encoding="utf-8")
    (run_dir / "run_status.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "start_epoch": 8260,
                "max_epochs": 90000,
                "speed_mps": case.speed_mps,
                "fault_schedule": case.fault_schedule,
            }
        ),
        encoding="utf-8",
    )
    return {
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
        "denominators": {"processed_attempt": {"minutes": {"mean": 3.0}}},
    }


def test_speed_aggregate_requires_two_matching_full_repeats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path)
    case = g29.case_by_id("t5_2_speed_2p5")
    case_root = tmp_path / "hca" / case.case_id
    runs = [
        _completed_run(case_root / "run_01", workload, case),
        _completed_run(case_root / "run_02", workload, case),
    ]
    monkeypatch.setattr(
        g29.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": runs},
    )

    row = g29._complete_case_row(case, workload, case_root)
    assert row["protocol_status"] == "EXACT_FULL_COMPLETION"
    assert row["primary_capacity_eligible"] is True
    assert row["full_completion_eligible"] is True
    assert row["release_repeat_match"] is True
    assert row["timing_scope"] == "FULL_POPULATION"
    assert row["processed_attempt_mean_minutes_by_repeat"] == [3.0, 3.0]


def test_speed_full_release_partial_completion_is_primary_capacity_with_censored_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path)
    case = g29.case_by_id("t5_2_speed_2p5")
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
                "canonical_success_rate": (workload.raw_task_count - 1)
                / workload.raw_task_count,
            }
        )
    monkeypatch.setattr(
        g29.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": runs},
    )

    row = g29._complete_case_row(case, workload, case_root)
    assert row["protocol_status"] == "EXACT_RELEASE_FULL_POPULATION_FIXED_HORIZON"
    assert row["primary_capacity_eligible"] is True
    assert row["full_completion_eligible"] is False
    assert row["canonical_success_rate_by_repeat"] == [0.5, 0.5]
    assert row["timing_scope"] == "CENSORED_COMPLETED_SURVIVORS_SECONDARY"
    assert row["secondary_timing_censored"] is True
    assert row["processed_attempt_mean_minutes_by_repeat"] == [None, None]
    assert row[
        "secondary_censored_processed_attempt_mean_minutes_by_repeat"
    ] == [3.0, 3.0]


def test_fault_aggregate_accepts_fixed_horizon_partial_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workload = _workload(tmp_path)
    case = g29.case_by_id("t5_5_fault_single_2")
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
        g29.g24,
        "aggregate_campaign",
        lambda output_root, canonical_path: {"runs": [run]},
    )

    row = g29._complete_case_row(case, workload, case_root)
    assert row["protocol_status"] == "FIXED_HORIZON_CAPACITY"
    assert row["primary_capacity_eligible"] is True


def test_archived_pair_is_not_a_missing_primary_case(tmp_path: Path) -> None:
    workload = _workload(tmp_path)
    value = g29.aggregate_campaign(workload, tmp_path / "empty_hca")
    archived = next(row for row in value["rows"] if row["case_id"] == "t5_5_fault_pair_5_7")

    assert archived["protocol_status"] == "ARCHIVED_ONLY_NOT_EXECUTED"
    assert "t5_5_fault_pair_5_7" not in value["missing_primary_case_ids"]
    assert len(value["missing_primary_case_ids"]) == 19
