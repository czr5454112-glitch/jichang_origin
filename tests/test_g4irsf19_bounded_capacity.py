from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import run_g4irsf19_bounded_capacity as capacity


def _progress(
    wall: float,
    *,
    events: int,
    released: int,
    completed: int,
    backlog: int,
    simulated: float,
    retries: int = 0,
    coalesced: int = 0,
) -> dict[str, Any]:
    event_types = {name: 0 for name in capacity.EVENT_TYPES}
    event_types.update(
        {
            "bag_release": released,
            "arrive_junction": events - released,
        }
    )
    return {
        "schema": "czr005.g4irsf19.runtime_progress.v1",
        "phase": "READY",
        "wall_seconds": wall,
        "simulated_time": simulated,
        "requested_bags": 100,
        "released_bags": released,
        "completed_bags": completed,
        "failed_bags": 0,
        "terminal_bags": completed,
        "current_backlog": backlog,
        "event_total": events,
        "heap_size": 100 - released,
        "event_type_counts": event_types,
        "source_admission_attempt_count": 0,
        "source_admission_admitted_count": 0,
        "source_admission_hold_count": 0,
        "stale_event_count": 0,
        "retry_count_by_reason": {"merge_contended_loser": retries},
        "duplicate_wakeup_count": 0,
        "coalesced_event_count": coalesced,
    }


def test_bounded_history_drives_frontier_slopes_and_event_ratios() -> None:
    first = _progress(
        0.0, events=0, released=0, completed=0, backlog=0, simulated=0.0
    )
    last = _progress(
        10.0,
        events=1_000,
        released=100,
        completed=40,
        backlog=60,
        simulated=200.0,
        retries=50,
        coalesced=20,
    )
    payload = {
        "execution_status": "BOUNDED_PROGRESS",
        "progress_history": [first, last],
        "progress": last,
        "summary": {"requested_count": 100, "bounded_progress": True},
    }

    history, source = capacity.progress_history_from_payload(
        payload, requested=100, wall_seconds=10.1
    )
    slopes = capacity.progress_slopes(history)
    ratios = capacity.event_type_ratios(history)

    assert source == "native_bounded_progress_history"
    assert len(history) == 2
    assert slopes["events_per_wall_second"] == pytest.approx(100.0)
    assert slopes["releases_per_wall_second"] == pytest.approx(10.0)
    assert slopes["completions_per_wall_second"] == pytest.approx(4.0)
    assert slopes["backlog_change_per_wall_second"] == pytest.approx(6.0)
    assert slopes["simulated_seconds_per_wall_second"] == pytest.approx(20.0)
    assert slopes["merge_retries_per_wall_second"] == pytest.approx(5.0)
    assert ratios["bag_release"] == pytest.approx(0.1)
    assert ratios["arrive_junction"] == pytest.approx(0.9)


def test_natural_completion_discloses_synthesized_endpoint_history() -> None:
    payload = {
        "summary": {
            "requested_count": 2,
            "completed_count": 2,
            "failed_count": 0,
            "event_count": 20,
            "bag_release_event_count": 2,
            "arrive_junction_event_count": 18,
            "end_time": 50.0,
            "final_active_bag_count": 0,
            "event_limit_reached": False,
            "time_limit_reached": False,
            "stale_arbitration_event_count": 2,
            "merge_grant_stale_arbitration_count": 3,
            "merge_grant_stale_wakeup_count": 4,
        },
        "bags": [],
    }
    result = capacity.compact_job_result(
        payload,
        scale=1,
        scorer="S4",
        descriptor={"segments": 2, "scale": 1, "topology_changed": False},
        max_wall_seconds=30.0,
        check_events=10,
        native_wall_seconds=2.0,
        native_cpu_seconds=1.5,
        input_wall_seconds=0.1,
        rss_before_mb=100.0,
        rss_after_mb=120.0,
        rss_method="fixture_rss",
    )

    assert result["status"] == "COMPLETE"
    assert result["progress_history_source"] == (
        "synthesized_start_and_finalized_endpoint"
    )
    assert result["slopes"]["events_per_wall_second"] == pytest.approx(10.0)
    assert result["progress_history"][-1]["stale_event_count"] == 9
    assert result["slopes"]["stale_events_per_wall_second"] == pytest.approx(4.5)
    assert result["completion_fraction"] == 1.0
    assert result["resources"]["rss_sample_mb_max_of_endpoints"] == 120.0
    assert result["limitations"]["disk_checkpoint_implemented"] is False
    assert result["limitations"]["cpu_category_breakdown_implemented"] is False


def test_fake_executor_runs_campaign_and_s4_omits_model(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.touch()
    captured: list[dict[str, Any]] = []

    def input_loader(
        scale: int, root: Path
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        del root
        rows = [
            {
                "segment_id": f"fixture-{scale}-{index}",
                "task_id": scale * 100 + index,
                "pass_time": float(index),
                "std": 100.0,
                "start": 3,
                "goal": 47,
                "source": "fixture",
            }
            for index in range(2)
        ]
        return rows, {
            "protocol": "fixture_fixed_map",
            "segments": 2,
            "scale": scale,
            "topology_changed": False,
        }

    def executor(**request: Any) -> dict[str, Any]:
        captured.append(request)
        initial = _progress(
            0.0, events=0, released=0, completed=0, backlog=0, simulated=0.0
        )
        final = _progress(
            5.0,
            events=500,
            released=2,
            completed=1,
            backlog=1,
            simulated=80.0,
            retries=25,
            coalesced=10,
        )
        final["requested_bags"] = 2
        initial["requested_bags"] = 2
        return {
            "execution_status": "BOUNDED_PROGRESS",
            "stop_reason": "WALL_LIMIT",
            "progress_history": [initial, final],
            "progress": final,
            "summary": {
                "requested_count": 2,
                "completed_count": 1,
                "failed_count": 0,
                "event_count": 500,
                "bounded_progress": True,
                "merge_grant_timing_mode": "jit_fair_aging_deadline",
            },
        }

    results = capacity.run_campaign(
        scales=[1],
        scorer="S4",
        binary=binary,
        root=tmp_path,
        max_wall_seconds=5.0,
        check_events=100,
        output_dir=tmp_path / "jobs",
        csv_path=tmp_path / "capacity.csv",
        frontier_report=tmp_path / "frontier.md",
        capacity_report=tmp_path / "scale.md",
        executor=executor,
        input_loader=input_loader,
        rss_reader=lambda: (64.0, "fixture_rss"),
    )

    assert [result["status"] for result in results] == ["BOUNDED_PROGRESS"]
    assert captured[0]["scorer_mode"] == capacity.SCORER_MODES["S4"]
    assert "scorer_model_path" not in captured[0]
    assert captured[0]["bounded_wall_seconds"] == 5.0
    assert captured[0]["bounded_check_every_events"] == 100
    assert captured[0]["merge_grant_timing_mode"] == "jit_fair_aging_deadline"
    assert (tmp_path / "jobs/scale_1x__s4.json").is_file()

    csv_rows = list(csv.DictReader(io.StringIO((tmp_path / "capacity.csv").read_text())))
    assert len(csv_rows) == 1
    assert csv_rows[0]["status"] == "BOUNDED_PROGRESS"
    frontier = (tmp_path / "frontier.md").read_text(encoding="utf-8")
    scale = (tmp_path / "scale.md").read_text(encoding="utf-8")
    assert "does not implement disk checkpoints" in frontier
    assert "not completed capacity claims" in scale


def test_model_free_and_model_backed_request_contracts(tmp_path: Path) -> None:
    binary = tmp_path / "czr005_cpp.fake.pyd"
    binary.touch()
    rows = [
        {
            "segment_id": "fixture",
            "task_id": 1,
            "pass_time": 0.0,
            "std": 100.0,
            "start": 3,
            "goal": 47,
        }
    ]
    model_free = capacity.build_native_request(
        rows,
        scale=1,
        scorer="S3",
        binary=binary,
        root=tmp_path,
        max_wall_seconds=1.0,
        check_events=1,
    )
    model_backed = capacity.build_native_request(
        rows,
        scale=1,
        scorer="S1",
        binary=binary,
        root=capacity.ROOT,
        max_wall_seconds=1.0,
        check_events=1,
    )

    assert "scorer_model_path" not in model_free
    assert Path(model_backed["scorer_model_path"]).is_file()
