from pathlib import Path

import pytest

from scripts.eval import run_g4irsf24_fresh_hca as fresh_hca


def test_lifecycle_alignment_and_three_denominators() -> None:
    canonical = [
        {
            "segment_id": "1:direct",
            "task_id": 1,
            "leg": "direct",
            "start": 3,
            "goal": 48,
            "pass_time": 10.0,
            "original_entry_time": 10.0,
        },
        {
            "segment_id": "2:storage_in",
            "task_id": 2,
            "leg": "storage_in",
            "start": 4,
            "goal": 47,
            "pass_time": 5.0,
            "original_entry_time": 5.0,
        },
        {
            "segment_id": "2:storage_out",
            "task_id": 2,
            "leg": "storage_out",
            "start": 52,
            "goal": 49,
            "pass_time": 20.0,
            "original_entry_time": 5.0,
        },
    ]
    releases = [
        {"ordinal": "1", "task_id": "2", "start": "4", "goal": "47", "release_epoch": "5"},
        {"ordinal": "2", "task_id": "1", "start": "3", "goal": "48", "release_epoch": "10"},
        {"ordinal": "3", "task_id": "2", "start": "52", "goal": "49", "release_epoch": "20"},
    ]
    routes = [
        {"ordinal": "1", "task_id": "2", "start": "4", "goal": "47", "epoch": "7"},
        {"ordinal": "2", "task_id": "1", "start": "3", "goal": "48", "epoch": "12"},
        {"ordinal": "3", "task_id": "2", "start": "52", "goal": "49", "epoch": "22"},
    ]
    completions = [
        {"task_id": 2, "finish_epoch": 12.0},
        {"task_id": 1, "finish_epoch": 20.0},
        {"task_id": 2, "finish_epoch": 30.0},
    ]

    lifecycle = fresh_hca._build_lifecycle(canonical, releases, routes, completions)
    bags = {row["task_id"]: row for row in fresh_hca._aggregate_raw_bags(canonical, lifecycle)}

    assert bags[1]["raw_entry_seconds"] == pytest.approx(10.0)
    assert bags[1]["java_release_seconds"] == pytest.approx(10.0)
    assert bags[1]["processed_attempt_seconds"] == pytest.approx(8.0)
    assert bags[2]["raw_entry_seconds"] == pytest.approx(32.0)
    assert bags[2]["java_release_seconds"] == pytest.approx(17.0)
    assert bags[2]["processed_attempt_seconds"] == pytest.approx(13.0)
    assert bags[2]["source_wait_seconds"] == pytest.approx(4.0)
    assert bags[2]["network_time_seconds"] == pytest.approx(13.0)

    processed = fresh_hca._describe([8.0, 13.0])
    assert processed["seconds"]["p50"] == pytest.approx(10.5)
    assert processed["seconds"]["mean"] == pytest.approx(10.5)


def test_java_command_is_one_repeat_per_working_directory() -> None:
    synthetic_root = Path("g4irsf24_synthetic_command_test")
    run_dir = synthetic_root / "run_02"
    command = fresh_hca.java_run_command(
        java="java",
        classes_dir=synthetic_root / "classes",
        map_path=synthetic_root / "map2.txt",
        input_path=synthetic_root / "inputdata.txt",
        start_epoch=8260,
        max_epochs=90000,
        max_new_tasks=0,
        run_dir=run_dir,
    )

    benchmark_index = command.index("LegacyIcsNoFaultWindowBenchmark")
    assert command[benchmark_index + 6 : benchmark_index + 8] == ["1", "0"]
    assert command[-1] == str((run_dir / "release.csv").resolve())
