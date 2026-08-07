from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf19_rollout_farm as farm


def _run_fixture(
    plan: dict[str, object],
    tmp_path: Path,
    *,
    workers: int,
    repeat: int = 1,
    force: bool = False,
) -> dict[str, object]:
    return farm.run_configuration(
        plan,
        workers=workers,
        repeat=repeat,
        binary=tmp_path / "unused-native.pyd",
        root=tmp_path,
        runstate_root=tmp_path / "runstate",
        force=force,
        worker=farm._fixture_execute_pair_job,
    )


def test_default_plan_is_a_fixed_complete_j2_s1_s2_replica_plan() -> None:
    plan = farm.validate_plan(farm.build_plan())

    assert plan["prefix_segments"] == 2_048
    assert plan["replica_count"] == 8
    assert plan["design"]["pair_order"] == ["J2/S1", "J2/S2"]
    assert plan["design"]["worker_count_does_not_change_jobs"] is True
    assert plan["design"]["one_fresh_process_per_pair_job"] is True
    assert plan["design"]["independent_learning_support_claimed"] is False
    assert [job["plan_index"] for job in plan["jobs"]] == list(range(8))

    for job in plan["jobs"]:
        assert job["prefix_segments"] == 2_048
        assert job["baseline"]["label"] == "J2/S1"
        assert job["treatment"]["label"] == "J2/S2"
        assert (
            job["baseline"]["arm"]["native_controls"]["scorer_mode"]
            == farm.S1_MODE
        )
        assert (
            job["treatment"]["arm"]["native_controls"]["scorer_mode"]
            == farm.S2_MODE
        )
        assert job["baseline"]["job"]["prefix_segments"] == 2_048
        assert job["treatment"]["job"]["prefix_segments"] == 2_048

    drifted = deepcopy(plan)
    drifted["jobs"][0]["treatment"]["job"]["prefix_segments"] = 512
    with pytest.raises(farm.RolloutFarmError, match="prefix drift"):
        farm.validate_plan(drifted)


def test_process_jobs_merge_in_plan_order_retry_once_and_resume(tmp_path: Path) -> None:
    plan = farm.build_plan(replica_count=3, prefix_segments=144)
    for index, job in enumerate(plan["jobs"]):
        job["_fixture_delay_seconds"] = (3 - index) * 0.02
    plan["jobs"][1]["_fixture_fail_first"] = True

    first = _run_fixture(plan, tmp_path, workers=2)
    summary = first["summary"]

    assert summary["status"] == "COMPLETE"
    assert summary["scheduled_job_count"] == 3
    assert summary["resumed_job_count"] == 0
    assert summary["retry_count"] == 1
    assert summary["failure_count"] == 0
    assert summary["fresh_full_plan_timing"] is False
    assert summary["groups_per_hour"] is None
    assert summary["segments_per_hour"] is None
    expected_ids = [job["job_id"] for job in plan["jobs"]]
    assert summary["ordered_job_ids"] == expected_ids
    assert [row["pair_job"]["job_id"] for row in first["job_results"]] == expected_ids

    worker_pids = [row["resources"]["worker_pid"] for row in first["job_results"]]
    assert all(pid != os.getpid() for pid in worker_pids)
    assert len(set(worker_pids)) == len(plan["jobs"])

    job_directory = tmp_path / "runstate" / "p2" / "r1" / "jobs"
    mtimes = {path.name: path.stat().st_mtime_ns for path in job_directory.glob("*.json")}
    second = _run_fixture(plan, tmp_path, workers=2)

    assert second["summary"]["status"] == "COMPLETE"
    assert second["summary"]["scheduled_job_count"] == 0
    assert second["summary"]["resumed_job_count"] == 3
    assert second["summary"]["retry_count"] == 0
    assert {
        path.name: path.stat().st_mtime_ns for path in job_directory.glob("*.json")
    } == mtimes


def test_persistent_failure_gets_exactly_one_retry_and_is_not_resumed(
    tmp_path: Path,
) -> None:
    plan = farm.build_plan(replica_count=1, prefix_segments=144)
    plan["jobs"][0]["_fixture_fail_always"] = True

    first = _run_fixture(plan, tmp_path, workers=1)
    assert first["summary"]["status"] == "INCOMPLETE"
    assert first["summary"]["scheduled_job_count"] == 1
    assert first["summary"]["completed_job_count"] == 0
    assert first["summary"]["retry_count"] == 1
    assert first["summary"]["failure_count"] == 1

    result_path = next(
        (tmp_path / "runstate" / "p1" / "r1" / "jobs").glob("*.json")
    )
    failure = json.loads(result_path.read_text(encoding="utf-8"))
    assert failure["status"] == "FAILED"
    assert failure["attempts"] == 2

    second = _run_fixture(plan, tmp_path, workers=1)
    assert second["summary"]["scheduled_job_count"] == 1
    assert second["summary"]["resumed_job_count"] == 0
    assert second["summary"]["retry_count"] == 1


def test_semantic_projection_recursively_excludes_resources() -> None:
    left = {
        "pair_job": {"job_id": "pair", "resources": {"planner": "left"}},
        "native_pair_complete": True,
        "native_pair_terminal": True,
        "baseline": {
            "metrics": {"value": 1},
            "nested": [{"resources": {"wall_seconds": 1.0}, "value": 2}],
            "resources": {"worker_pid": 10},
        },
        "treatment": {"metrics": {"value": 3}, "resources": {"rss": 4}},
        "resources": {"attempt": 1},
    }
    right = deepcopy(left)
    right["pair_job"]["resources"] = {"planner": "right"}
    right["baseline"]["nested"][0]["resources"] = {"wall_seconds": 9.0}
    right["baseline"]["resources"] = {"worker_pid": 99}
    right["treatment"]["resources"] = {"rss": 400}
    right["resources"] = {"attempt": 2}

    assert farm.semantic_job_result(left) == farm.semantic_job_result(right)


def test_benchmark_compares_p1_p2_semantics_and_writes_compact_outputs(
    tmp_path: Path,
) -> None:
    plan = farm.build_plan(replica_count=2, prefix_segments=144)
    for job in plan["jobs"]:
        job["_fixture_delay_seconds"] = 0.02
    json_output = tmp_path / "tables" / "parallelism.json"
    csv_output = tmp_path / "tables" / "parallelism.csv"
    report_output = tmp_path / "reports" / "parallelism.md"

    result = farm.benchmark_plan(
        plan,
        binary=tmp_path / "unused-native.pyd",
        root=tmp_path,
        workers=(1, 2),
        repeats=1,
        runstate_root=tmp_path / "benchmark-runstate",
        json_output=json_output,
        csv_output=csv_output,
        report_output=report_output,
        worker=farm._fixture_execute_pair_job,
    )

    assert result["status"] == "COMPLETE_DETERMINISTIC"
    assert [row["workers"] for row in result["runs"]] == [1, 2]
    assert all(row["semantic_equal_to_p1"] for row in result["runs"])
    assert all(row["semantic_mismatch_job_ids"] == [] for row in result["runs"])
    assert result["runs"][0]["speedup_vs_p1"] == pytest.approx(1.0)
    assert all(row["fresh_full_plan_timing"] for row in result["runs"])

    persisted = json.loads(json_output.read_text(encoding="utf-8"))
    assert persisted == result
    assert "job_results" not in json_output.read_text(encoding="utf-8")
    assert "semantic_by_job" not in json_output.read_text(encoding="utf-8")
    assert csv_output.read_text(encoding="utf-8").splitlines()[0].startswith(
        "workers,effective_workers,repeat"
    )
    report = report_output.read_text(encoding="utf-8")
    assert "not independent learning support" in report
    assert "No production policy promotion is implied" in report
