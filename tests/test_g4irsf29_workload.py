from __future__ import annotations

import csv
import json
from pathlib import Path

from czr005.io.legacy_tasks import expand_tasks, parse_legacy_tasks
from scripts.eval import run_g4irsf29_workload as g29


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "raw_output": tmp_path / "inputdata_2x.txt",
        "canonical_output": tmp_path / "inputdata_2x.jsonl",
        "manifest_output": tmp_path / "manifest.json",
        "flight_csv_output": tmp_path / "flights.csv",
    }


def test_small_raw_timetable_is_densified_before_legacy_expansion(
    tmp_path: Path,
) -> None:
    source = tmp_path / "inputdata.txt"
    source.write_text(
        "ID EntryTime(s) STD(s) star end Unloader Loader\n"
        "0 1000 7000 0 48 1 A1\n"
        "1 2500 7000 1 48 1 B1\n"
        "2 4000 9000 0 48 1 A1\n"
        "3 6500 9000 1 48 1 B1\n",
        encoding="utf-8",
    )
    paths = _paths(tmp_path)

    manifest = g29.build_workload(input_path=source, **paths)

    assert manifest["raw_task_count"] == 8
    assert manifest["direct_raw_task_count"] == 4
    assert manifest["early_split_raw_task_count"] == 4
    assert manifest["expanded_segment_count"] == 12
    assert manifest["flight_count"] == 4
    assert manifest["inserted_id_offset"] == 4

    _, raw = parse_legacy_tasks(paths["raw_output"])
    by_id = {task.task_id: task for task in raw}
    assert set(by_id) == set(range(8))
    assert by_id[4].entry_time == 2000.0
    assert by_id[4].std == 8000.0
    assert by_id[4].std - by_id[4].entry_time == by_id[0].std - by_id[0].entry_time
    assert by_id[6].entry_time == 5000.0
    assert by_id[6].std == 10000.0

    canonical_rows = [
        json.loads(line)
        for line in paths["canonical_output"].read_text(encoding="utf-8").splitlines()
    ]
    assert canonical_rows == [task.to_dict() for task in expand_tasks(raw)]
    inserted_early = [row for row in canonical_rows if row["task_id"] == 4]
    assert [
        (row["leg"], row["start"], row["goal"], row["pass_time"])
        for row in inserted_early
    ] == [
        ("storage_in", 0, 47, 2000.0),
        ("storage_out", 52, 48, 5300.0),
    ]

    with paths["flight_csv_output"].open(encoding="utf-8", newline="") as handle:
        flights = list(csv.DictReader(handle))
    assert [float(row["scheduled_std"]) for row in flights] == [
        7000.0,
        8000.0,
        9000.0,
        10000.0,
    ]
    assert json.loads(flights[1]["source_counts"]) == {"0": 1, "1": 1}
    assert json.loads(flights[1]["loader_counts"]) == {"A1": 1, "B1": 1}


def test_real_workload_matches_the_registered_flight_level_2x_cohort(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)

    manifest = g29.build_workload(input_path=g29.DEFAULT_INPUT, **paths)

    assert manifest["schema"] == g29.SCHEMA
    assert manifest["status"] == g29.STATUS
    assert manifest["protocol"] == g29.PROTOCOL
    assert manifest["input_raw_task_count"] == 28_506
    assert manifest["input_expanded_segment_count"] == 43_603
    assert manifest["input_flight_count"] == 360
    assert manifest["stream_count"] == 13
    assert manifest["raw_task_count"] == 57_012
    assert manifest["expanded_segment_count"] == 87_206
    assert manifest["direct_raw_task_count"] == 26_818
    assert manifest["early_split_raw_task_count"] == 30_194
    assert manifest["flight_count"] == 720
    assert manifest["original_flight_count"] == 360
    assert manifest["inserted_flight_count"] == 360
    assert manifest["timing"] == {
        "time_compression": 1.0,
        "rolling_days": 1,
        "earliest_entry_time": 8267.845453,
        "latest_entry_time": 82403.72582,
        "earliest_std": 22200.0,
        "latest_std": 85500.0,
    }
    assert all(manifest["invariants"].values())
    assert manifest["raw_by_loader"] == {
        "A1": 2352,
        "B1": 5744,
        "B2": 11088,
        "C1": 9066,
        "C2": 15084,
        "D1": 5170,
        "T": 8508,
    }

    stored = json.loads(paths["manifest_output"].read_text(encoding="utf-8"))
    assert stored == manifest
    assert sum(1 for _ in paths["canonical_output"].open(encoding="utf-8")) == 87_206
    with paths["flight_csv_output"].open(encoding="utf-8", newline="") as handle:
        flights = list(csv.DictReader(handle))
    assert len(flights) == 720
    assert sum(row["flight_kind"] == "inserted" for row in flights) == 360
