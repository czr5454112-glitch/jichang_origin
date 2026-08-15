import json
from pathlib import Path

from scripts.eval import run_g4irsf24_fresh_hca as fresh_hca


def _command(**overrides: object) -> list[str]:
    root = Path("g4irsf26_protocol_test")
    kwargs: dict[str, object] = {
        "java": "java",
        "classes_dir": root / "classes",
        "map_path": root / "map2.txt",
        "input_path": root / "inputdata.txt",
        "start_epoch": 8260,
        "max_epochs": 100,
        "max_new_tasks": 8,
        "run_dir": root / "run_01",
    }
    kwargs.update(overrides)
    return fresh_hca.java_run_command(**kwargs)  # type: ignore[arg-type]


def test_default_direct_call_keeps_historical_java_shape() -> None:
    command = _command()
    benchmark = command.index("LegacyIcsNoFaultWindowBenchmark")

    assert command[benchmark + 10] == "none"
    assert command[-1].endswith("release.csv")


def test_speed_and_fault_schedule_use_existing_slots_and_speed_tail() -> None:
    schedule = "8260:3:8:fault;8270:3:8:repair"
    command = _command(fault_schedule=schedule, speed_mps=1.5)
    benchmark = command.index("LegacyIcsNoFaultWindowBenchmark")

    assert command[benchmark + 10] == schedule
    assert command[-2].endswith("release.csv")
    assert command[-1] == "1.5"


def test_cleanup_removes_only_exact_task_subdirectory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_01"
    task_dir = run_dir / "task"
    similarly_named = run_dir / "task_backup"
    task_dir.mkdir(parents=True)
    similarly_named.mkdir()
    (task_dir / "8260.txt").write_text("epoch", encoding="utf-8")
    (similarly_named / "keep.txt").write_text("keep", encoding="utf-8")
    (run_dir / "output.txt").write_text("1 2", encoding="utf-8")
    (run_dir / "run_status.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )

    removed = fresh_hca._cleanup_epoch_files(run_dir)
    fresh_hca._record_cleanup(run_dir, requested=True, removed=removed)

    assert removed is True
    assert not task_dir.exists()
    assert (similarly_named / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert (run_dir / "output.txt").read_text(encoding="utf-8") == "1 2"
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert status["cleanup_epoch_files_requested"] is True
    assert status["cleanup_epoch_files_removed"] is True


def test_canonical_success_rate_counts_unreleased_bags_as_failures(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.jsonl"
    canonical_rows = [
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
            "segment_id": "2:direct",
            "task_id": 2,
            "leg": "direct",
            "start": 4,
            "goal": 49,
            "pass_time": 20.0,
            "original_entry_time": 20.0,
        },
    ]
    canonical_path.write_text(
        "".join(json.dumps(row) + "\n" for row in canonical_rows), encoding="utf-8"
    )
    run_dir = tmp_path / "run_01"
    run_dir.mkdir()
    (run_dir / "release.csv").write_text(
        "ordinal,task_id,start,goal,release_epoch\n1,1,3,48,10\n", encoding="utf-8"
    )
    (run_dir / "routes.csv").write_text(
        "ordinal,task_id,start,goal,epoch,finish_time,path\n"
        "1,1,3,48,10,20,3;48\n",
        encoding="utf-8",
    )
    (run_dir / "output.txt").write_text("1 20\n", encoding="utf-8")
    (run_dir / "summary.csv").write_text("repeat,speed_mps\n1,2.5\n", encoding="utf-8")
    (run_dir / "run_status.json").write_text(
        json.dumps({"status": "complete", "profile": "full", "wall_seconds": 1.0}),
        encoding="utf-8",
    )

    metrics = fresh_hca.aggregate_run(run_dir, canonical_path)

    assert metrics["complete_raw_bag_count"] == 1
    assert metrics["canonical_complete_raw_bag_count"] == 1
    assert metrics["canonical_incomplete_raw_bag_count"] == 1
    assert metrics["canonical_success_rate"] == 0.5
    assert metrics["processed_attempt_source"] == "routes.csv_fallback"


def test_outputstarttime_recovers_delayed_retry_missing_from_routes(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.jsonl"
    canonical_rows = [
        {
            "segment_id": "2710:storage_in",
            "task_id": 2710,
            "leg": "storage_in",
            "start": 1,
            "goal": 47,
            "pass_time": 10.0,
            "original_entry_time": 10.0,
        },
        {
            "segment_id": "2710:storage_out",
            "task_id": 2710,
            "leg": "storage_out",
            "start": 52,
            "goal": 50,
            "pass_time": 20.0,
            "original_entry_time": 10.0,
        },
    ]
    canonical_path.write_text(
        "".join(json.dumps(row) + "\n" for row in canonical_rows), encoding="utf-8"
    )
    run_dir = tmp_path / "run_01"
    run_dir.mkdir()
    (run_dir / "release.csv").write_text(
        "ordinal,task_id,start,goal,release_epoch\n"
        "1,2710,1,47,10\n"
        "2,2710,52,50,20\n",
        encoding="utf-8",
    )
    # The wrapper misses the later start=1 retry and its predicted finish is
    # deliberately wrong; neither fact may control lifecycle aggregation.
    (run_dir / "routes.csv").write_text(
        "ordinal,task_id,start,goal,epoch,finish_time,path\n"
        "1,2710,52,50,22,999999,52;50\n",
        encoding="utf-8",
    )
    (run_dir / "outputstarttime.txt").write_text(
        "2710   52  0.0  22.0\n"
        "2710   1   0.0  35.0\n",
        encoding="utf-8",
    )
    (run_dir / "output.txt").write_text(
        "2710  30.0\n2710  60.0\n", encoding="utf-8"
    )
    (run_dir / "summary.csv").write_text(
        "repeat,planned_count,completed_count\n1,1,2\n", encoding="utf-8"
    )
    (run_dir / "run_status.json").write_text(
        json.dumps({"status": "complete", "profile": "full", "wall_seconds": 1.0}),
        encoding="utf-8",
    )

    metrics = fresh_hca.aggregate_run(run_dir, canonical_path)
    lifecycle = {
        row["segment_id"]: row
        for row in fresh_hca._read_csv(run_dir / "segment_lifecycle.csv")
    }

    assert metrics["processed_attempt_source"] == "outputstarttime.txt"
    assert metrics["processed_attempt_event_count"] == 2
    assert metrics["planned_segment_count"] == 2
    assert metrics["completed_segment_count"] == 2
    assert metrics["denominators"]["processed_attempt"]["seconds"]["mean"] == 33.0
    assert lifecycle["2710:storage_out"]["processed_attempt_epoch"] == "22.0"
    assert lifecycle["2710:storage_out"]["finish_epoch"] == "30.0"
    assert lifecycle["2710:storage_in"]["processed_attempt_epoch"] == "35.0"
    assert lifecycle["2710:storage_in"]["finish_epoch"] == "60.0"
