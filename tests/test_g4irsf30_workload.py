from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from czr005.io.legacy_tasks import expand_tasks, parse_legacy_tasks
from scripts.eval import run_g4irsf30_workload as g30


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "raw_output": tmp_path / "inputdata_3x.txt",
        "canonical_output": tmp_path / "inputdata_3x.jsonl",
        "manifest_output": tmp_path / "manifest.json",
        "flight_csv_output": tmp_path / "flights.csv",
    }


def test_small_timetable_inserts_two_manifest_copies_at_thirds(
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

    manifest = g30.build_workload(input_path=source, **paths)

    assert manifest["raw_task_count"] == 12
    assert manifest["direct_raw_task_count"] == 6
    assert manifest["early_split_raw_task_count"] == 6
    assert manifest["expanded_segment_count"] == 18
    assert manifest["flight_count"] == 6
    assert manifest["inserted_id_offsets"] == [4, 8]

    _, raw = parse_legacy_tasks(paths["raw_output"])
    by_id = {task.task_id: task for task in raw}
    assert set(by_id) == set(range(12))
    assert math.isclose(by_id[4].entry_time, 1_666.66666666667)
    assert math.isclose(by_id[4].std, 7_666.66666666667)
    assert math.isclose(by_id[8].entry_time, 2_333.33333333333)
    assert math.isclose(by_id[8].std, 8_333.33333333333)
    assert math.isclose(by_id[6].std, 9_666.66666666667)
    assert math.isclose(by_id[10].std, 10_333.3333333333)
    for copied_id in (4, 8):
        assert math.isclose(
            by_id[copied_id].std - by_id[copied_id].entry_time,
            by_id[0].std - by_id[0].entry_time,
            abs_tol=1.0e-9,
        )

    canonical_rows = [
        json.loads(line)
        for line in paths["canonical_output"].read_text(encoding="utf-8").splitlines()
    ]
    assert canonical_rows == [task.to_dict() for task in expand_tasks(raw)]
    inserted_early = [row for row in canonical_rows if row["task_id"] == 4]
    assert [row["leg"] for row in inserted_early] == [
        "storage_in",
        "storage_out",
    ]
    assert math.isclose(inserted_early[1]["pass_time"], 4_966.66666666667)

    with paths["flight_csv_output"].open(encoding="utf-8", newline="") as handle:
        flights = list(csv.DictReader(handle))
    assert [float(row["scheduled_std"]) for row in flights] == [
        7_000.0,
        7_666.666666666667,
        8_333.333333333334,
        9_000.0,
        9_666.666666666666,
        10_333.333333333334,
    ]
    assert [row["flight_kind"] for row in flights] == [
        "original",
        "inserted_1_of_2",
        "inserted_2_of_2",
        "original",
        "inserted_1_of_2",
        "inserted_2_of_2",
    ]
    assert json.loads(flights[1]["source_counts"]) == {"0": 1, "1": 1}
    assert json.loads(flights[2]["loader_counts"]) == {"A1": 1, "B1": 1}


def test_real_workload_matches_registered_flight_level_3x_cohort(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)

    manifest = g30.build_workload(input_path=g30.DEFAULT_INPUT, **paths)

    assert manifest["schema"] == g30.SCHEMA
    assert manifest["status"] == g30.STATUS
    assert manifest["protocol"] == g30.PROTOCOL
    assert manifest["scale"] == 3
    assert manifest["input_raw_task_count"] == 28_506
    assert manifest["input_expanded_segment_count"] == 43_603
    assert manifest["input_flight_count"] == 360
    assert manifest["stream_count"] == 13
    assert manifest["raw_task_count"] == 85_518
    assert manifest["expanded_segment_count"] == 130_809
    assert manifest["direct_raw_task_count"] == 40_227
    assert manifest["early_split_raw_task_count"] == 45_291
    assert manifest["flight_count"] == 1_080
    assert manifest["original_flight_count"] == 360
    assert manifest["inserted_flight_count"] == 720
    assert manifest["inserted_flights_per_original"] == 2
    assert manifest["inserted_id_offsets"] == [28_506, 57_012]
    assert manifest["timing"] == {
        "time_compression": 1.0,
        "rolling_days": 1,
        "day_axis_seconds": 86_400.0,
        "earliest_entry_time": 8_267.845453,
        "latest_entry_time": 82_703.72582,
        "earliest_std": 22_200.0,
        "latest_std": 85_900.0,
    }
    assert all(manifest["invariants"].values())
    assert manifest["raw_by_loader"] == {
        "A1": 3_528,
        "B1": 8_616,
        "B2": 16_632,
        "C1": 13_599,
        "C2": 22_626,
        "D1": 7_755,
        "T": 12_762,
    }
    assert manifest["raw_by_end"] == {
        "48": 18_918,
        "49": 39_903,
        "50": 26_697,
    }

    stored = json.loads(paths["manifest_output"].read_text(encoding="utf-8"))
    assert stored == manifest
    _, generated = parse_legacy_tasks(paths["raw_output"])
    assert len(generated) == 85_518
    assert len({task.task_id for task in generated}) == 85_518
    assert {task.task_id for task in generated} == set(range(85_518))
    assert sum(1 for _ in paths["canonical_output"].open(encoding="utf-8")) == 130_809
    with paths["flight_csv_output"].open(encoding="utf-8", newline="") as handle:
        flights = list(csv.DictReader(handle))
    assert len(flights) == 1_080
    assert sum(row["flight_kind"] == "original" for row in flights) == 360
    assert sum(row["flight_kind"].startswith("inserted_") for row in flights) == 720
