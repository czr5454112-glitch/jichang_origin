from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.eval import run_g4irsf31_nanning_hca as hca31
from scripts.eval import run_g4irsf31_nanning_native as native31
from scripts.eval import run_g4irsf31_same_hca_release_timing as paired


def _rows(count: int = 2) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "segment_id": chr(ord("a") + index),
            "task_id": index + 1,
            "original_entry_time": 10.0 + 10.0 * index,
            "pass_time": 10.0 + 10.0 * index,
            "std": 1_000.0,
            "start": index,
            "goal": 53,
        }
        for index in range(count)
    )


def _workload(tmp_path: Path, scale: int, rows=None) -> native31.Workload:
    selected = tuple(rows or _rows())
    return native31.Workload(
        scale=scale,
        manifest_path=tmp_path / "manifest.json",
        canonical_path=tmp_path / "canonical.jsonl",
        manifest={"protocol": "fixture"},
        rows=selected,
        raw_bag_count=len({int(row["task_id"]) for row in selected}),
        segment_count=len(selected),
    )


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_hca_fixture(
    root: Path,
    case: native31.CaseSpec,
    workload: native31.Workload,
    *,
    run_01_releases: dict[str, float],
    run_02_releases: dict[str, float] | None = None,
    full_timing: bool = True,
) -> Path:
    case_id = (
        f"nanning_{case.scale}x_t5_2_speed_"
        f"{native31._speed_label(case.speed_mps)}"
    )
    case_root = root / case_id
    _write_json(
        case_root / "case_protocol.json",
        {
            "schema": hca31.CASE_PROTOCOL_SCHEMA,
            "case": {
                "case_id": case_id,
                "case_group": "stable_speed",
                "scale": case.scale,
                "speed_mps": case.speed_mps,
                "repeats": 2,
                "fault_schedule": "none",
                "fault_edges": [],
            },
            "workload": {
                "map_id": native31.MAP_ID,
                "raw_task_count": workload.raw_bag_count,
                "expanded_segment_count": workload.segment_count,
            },
            "fixed_window": {
                "start_epoch": hca31.START_EPOCH,
                "max_epochs": hca31.MAX_EPOCHS,
                "end_epoch": hca31.END_EPOCH,
            },
        },
    )
    repeats = (run_01_releases, run_02_releases or run_01_releases)
    for repeat, releases in enumerate(repeats, start=1):
        run_id = f"run_{repeat:02d}"
        run_dir = case_root / run_id
        _write_json(
            run_dir / "run_status.json",
            {
                "status": "complete",
                "returncode": 0,
                "run_id": run_id,
                "speed_mps": case.speed_mps,
                "start_epoch": hca31.START_EPOCH,
                "max_epochs": hca31.MAX_EPOCHS,
                "fault_schedule": "none",
                "storage_in_goal": native31.STORAGE_NODE,
                "storage_out_start": native31.STORAGE_NODE,
            },
        )
        released = len(releases)
        complete_segments = workload.segment_count if full_timing else released - 1
        complete_raw = workload.raw_bag_count if full_timing else 0
        _write_json(
            run_dir / "metrics.json",
            {
                "schema": "g4irsf24.fresh_hca.metrics.v1",
                "status": "complete",
                "run_id": run_id,
                "comparison_eligible": full_timing,
                "survivor_only": not full_timing,
                "scope": "canonical_full" if full_timing else "released_segment_cohort",
                "canonical_segment_count": workload.segment_count,
                "canonical_raw_bag_count": workload.raw_bag_count,
                "released_segment_count": released,
                "planned_segment_count": released,
                "completed_segment_count": complete_segments,
                "canonical_complete_raw_bag_count": complete_raw,
                "denominators": {
                    "java_release": {
                        "count": complete_raw,
                        "seconds": {
                            "min": 10.0,
                            "mean": 12.0,
                            "p95": 14.0,
                            "p99": 14.8,
                            "max": 15.0,
                        },
                    }
                },
            },
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / "segment_lifecycle.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["segment_id", "release_epoch"]
            )
            writer.writeheader()
            writer.writerows(
                {"segment_id": segment_id, "release_epoch": release}
                for segment_id, release in releases.items()
            )
    return case_root


def test_exact_repeat_trace_is_applied_with_g24_helper(tmp_path: Path) -> None:
    case = native31.CaseSpec("t5_2_nanning_1x_speed_2", "stable_speed", 1, 2.0)
    workload = _workload(tmp_path, 1)
    releases = {"a": 12.0, "b": 23.0}
    _write_hca_fixture(tmp_path / "hca", case, workload, run_01_releases=releases)

    result = paired.align_to_audited_hca_release(case, workload, tmp_path / "hca")

    assert result.trace_gate["pass"] is True
    assert result.workload is not None
    assert [row["pass_time"] for row in result.workload.rows] == [12.0, 23.0]
    assert [row["original_entry_time"] for row in result.workload.rows] == [10.0, 20.0]
    assert result.trace_gate["alignment"]["only_modified_input_field"] == "pass_time"


def test_repeat_release_mismatch_is_na_without_alignment(tmp_path: Path) -> None:
    case = native31.CaseSpec("t5_2_nanning_1x_speed_2", "stable_speed", 1, 2.0)
    workload = _workload(tmp_path, 1)
    _write_hca_fixture(
        tmp_path / "hca",
        case,
        workload,
        run_01_releases={"a": 12.0, "b": 23.0},
        run_02_releases={"a": 12.0, "b": 24.0},
    )

    result = paired.align_to_audited_hca_release(case, workload, tmp_path / "hca")

    assert result.workload is None
    assert result.trace_gate["status"] == paired.N_A_REPEAT
    assert result.trace_gate["gates"]["repeat_segment_release_values_identical"] is False


def test_2x_incomplete_release_is_na_not_common_cohort(tmp_path: Path) -> None:
    case = native31.CaseSpec("t5_2_nanning_2x_speed_2", "stable_speed", 2, 2.0)
    workload = _workload(tmp_path, 2, _rows(3))
    _write_hca_fixture(
        tmp_path / "hca",
        case,
        workload,
        run_01_releases={"a": 12.0, "b": 23.0},
    )

    result = paired.align_to_audited_hca_release(case, workload, tmp_path / "hca")

    assert result.workload is None
    assert result.trace_gate["status"] == paired.N_A_RELEASE
    assert result.hca_timing["survivor_or_common_cohort_comparison_allowed"] is False


def test_compare_five_full_population_metrics() -> None:
    comparison = paired.compare_five_metrics(
        {"min": 10.0, "mean": 12.0, "p95": 14.0, "p99": 14.8, "max": 15.0},
        {
            "min_seconds": 8.0,
            "mean_seconds": 9.0,
            "p95_seconds": 10.0,
            "p99_seconds": 10.5,
            "max_seconds": 11.0,
        },
    )

    assert [row["metric"] for row in comparison["metric_rows"]] == list(paired.METRICS)
    assert comparison["all_five_s4_strictly_lower"] is True
    assert comparison["common_cohort_verdict_used"] is False


def test_default_binary_resolution_uses_current_release_directory(
    tmp_path: Path, monkeypatch
) -> None:
    release_dir = tmp_path / "g4irsf24_dlp_release" / "python"
    release_dir.mkdir(parents=True)
    expected = release_dir / "czr005_cpp.cp311-win_amd64.pyd"
    expected.write_bytes(b"fixture")
    monkeypatch.setattr(paired, "DEFAULT_BINARY_DIR", release_dir)

    assert paired._resolve_binary(None) == expected.resolve()


def test_fake_executor_produces_full_same_release_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    case = native31.case_by_id("t5_2_nanning_1x_speed_2")
    workload = _workload(tmp_path, 1)
    _write_hca_fixture(
        tmp_path / "hca",
        case,
        workload,
        run_01_releases={"a": 12.0, "b": 23.0},
    )
    observed_pass_times: list[float] = []

    monkeypatch.setattr(native31, "load_workload", lambda scale, task_dir: workload)

    def fake_prepare(case, adjusted, **kwargs):
        observed_pass_times.extend(float(row["pass_time"]) for row in adjusted.rows)
        return (
            {
                "rows": adjusted.rows,
                "complete_on_goal_arrival": True,
            },
            adjusted.rows,
            (),
            {"fault_edges": []},
        )

    monkeypatch.setattr(native31, "prepare_native_request", fake_prepare)

    def fake_executor(rows, complete_on_goal_arrival):
        assert complete_on_goal_arrival is True
        bags = []
        for index, row in enumerate(rows):
            release = float(row["pass_time"])
            bags.append(
                {
                    "segment_id": row["segment_id"],
                    "completed": True,
                    "release_time": release,
                    "admitted_time": release + 1.0,
                    "finish_time": release + 5.0 + index,
                }
            )
        return {"summary": {"completed_count": len(bags)}, "bags": bags}

    result = paired.execute_case(
        case.case_id,
        task_dir=tmp_path,
        hca_root=tmp_path / "hca",
        map_profile_path=tmp_path / "unused.json",
        binary=tmp_path / "fake.pyd",
        executor=fake_executor,
        admission_checker=lambda *args: {"pass": True},
    )

    assert observed_pass_times == [12.0, 23.0]
    assert result["status"] == paired.COMPLETE
    assert result["algorithm_contract"]["completion_semantics"] == (
        native31.GOAL_ARRIVAL_COMPLETION
    )
    assert result["paired_s4_timing"]["raw_bag_count"] == 2
    assert len(result["comparison"]["metric_rows"]) == 5
    assert result["comparison"]["common_cohort_verdict_used"] is False
