from __future__ import annotations

from copy import deepcopy
import csv
import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf22_gap_episodes as runner


def _matched_rows() -> tuple[list[dict], list[dict], list[dict]]:
    inputs = [
        {
            "segment_id": "1:direct:c0",
            "task_id": 1,
            "pass_time": 0.0,
            "original_entry_time": 0.0,
            "std": 100.0,
            "start": 1,
            "goal": 4,
            "source": "node_1",
            "leg": "direct",
        },
        {
            "segment_id": "1:storage_out:c0",
            "task_id": 1,
            "pass_time": 10.0,
            "original_entry_time": 0.0,
            "std": 100.0,
            "start": 2,
            "goal": 4,
            "source": "node_2",
            "leg": "storage_out",
        },
    ]
    s4 = [
        {
            "segment_id": "1:direct:c0",
            "task_id": 1,
            "release_time": 0.0,
            "admitted_time": 2.0,
            "finish_time": 15.0,
            "junction_queue_wait_seconds": 5.0,
            "merge_grant_wait_seconds": 3.0,
            "completed": True,
        },
        {
            "segment_id": "1:storage_out:c0",
            "task_id": 1,
            "release_time": 10.0,
            "admitted_time": 10.0,
            "finish_time": 20.0,
            "junction_queue_wait_seconds": 1.0,
            "merge_grant_wait_seconds": 0.0,
            "completed": True,
        },
    ]
    v2 = [
        {
            "segment_id": "1:direct:c0",
            "task_id": 1,
            "attempt_time": 0.0,
            "finish_time": 10.0,
            "source_wait_seconds": 1.0,
            "wait_seconds": 4.0,
            "goal_reached": True,
        },
        {
            "segment_id": "1:storage_out:c0",
            "task_id": 1,
            "attempt_time": 10.0,
            "finish_time": 18.0,
            "source_wait_seconds": 0.0,
            "wait_seconds": 1.0,
            "goal_reached": True,
        },
    ]
    return inputs, s4, v2


def test_matched_segment_and_task_ledgers_do_not_double_add_merge() -> None:
    inputs, s4, v2 = _matched_rows()

    result = runner.build_matched_ledgers(inputs, s4, v2)

    direct = result["segment_rows"][0]
    storage_out = result["segment_rows"][1]
    assert direct["release_time_block"] == 0
    assert storage_out["source"] == "node_2"
    assert storage_out["release_time_block"] == 0
    assert direct["delta_total_seconds"] == pytest.approx(5.0)
    assert direct["delta_source_wait_seconds"] == pytest.approx(1.0)
    assert direct["delta_route_wait_inclusive_seconds"] == pytest.approx(2.0)
    assert direct["coordination_residual_delta_seconds"] == pytest.approx(2.0)
    assert direct["s4_merge_wait_diagnostic_seconds"] == pytest.approx(3.0)
    assert direct["v2_merge_wait_diagnostic_seconds"] is None
    assert direct["delta_merge_wait_diagnostic_seconds"] is None
    assert direct["delta_total_seconds"] == pytest.approx(
        direct["delta_source_wait_seconds"]
        + direct["delta_route_wait_inclusive_seconds"]
        + direct["coordination_residual_delta_seconds"]
    )
    # Adding the diagnostic merge again would be observably wrong.
    assert direct["delta_total_seconds"] != pytest.approx(
        direct["delta_source_wait_seconds"]
        + direct["delta_route_wait_inclusive_seconds"]
        + direct["coordination_residual_delta_seconds"]
        + direct["s4_merge_wait_diagnostic_seconds"]
    )

    task = result["task_rows"][0]
    assert task["segment_count"] == 2
    assert task["leg"] == "mixed"
    assert task["delta_total_seconds"] == pytest.approx(7.0)
    assert task["delta_source_wait_seconds"] == pytest.approx(1.0)
    assert task["delta_route_wait_inclusive_seconds"] == pytest.approx(2.0)
    assert task["coordination_residual_delta_seconds"] == pytest.approx(4.0)
    assert result["summary"]["mean_gap_seconds_per_task"] == pytest.approx(7.0)
    assert "never added" in result["summary"]["merge_semantics"]

    by_hotspot = runner.aggregate_gap_rows(
        result["segment_rows"], ("leg", "source", "release_time_block")
    )
    storage_out_cell = next(
        row for row in by_hotspot if row["leg"] == "storage_out"
    )
    assert storage_out_cell["source"] == "node_2"
    assert storage_out_cell["release_time_block"] == 0
    assert storage_out_cell["row_count"] == 1


def test_matched_ledger_rejects_identity_and_merge_subset_drift() -> None:
    inputs, s4, v2 = _matched_rows()
    wrong_task = deepcopy(v2)
    wrong_task[0]["task_id"] = 99
    with pytest.raises(runner.GapEpisodeError, match="task identity mismatch"):
        runner.build_matched_ledgers(inputs, s4, wrong_task)

    impossible_merge = deepcopy(s4)
    impossible_merge[0]["merge_grant_wait_seconds"] = 6.0
    with pytest.raises(runner.GapEpisodeError, match="route-wait subset"):
        runner.build_matched_ledgers(inputs, impossible_merge, v2)

    missing = v2[:-1]
    with pytest.raises(runner.GapEpisodeError, match="segment set differs"):
        runner.build_matched_ledgers(inputs, s4, missing)


def test_episode_descriptor_is_pure_and_uses_threshold_hysteresis() -> None:
    rows = [
        {"row_id": "a0", "owner": 7, "time_seconds": 0.0, "queue_length": 1.0, "leg": "direct"},
        {"row_id": "b0", "owner": 8, "time_seconds": 0.0, "queue_length": 6.0, "leg": "direct"},
        {"row_id": "a1", "owner": 7, "time_seconds": 10.0, "queue_length": 5.0, "leg": "direct", "segment_id": "s1", "task_id": 1},
        {"row_id": "a2", "owner": 7, "time_seconds": 20.0, "queue_length": 8.0, "leg": "storage_out", "segment_id": "s2", "task_id": 2, "s4_v2_diverged": True, "incoming_eta_count": 4.0, "service_rate": 0.5},
        {"row_id": "a3", "owner": 7, "time_seconds": 30.0, "queue_length": 3.0, "leg": "storage_out", "upstream_branch": 4},
        {"row_id": "a4", "owner": 7, "time_seconds": 40.0, "queue_length": 2.0, "leg": "storage_out", "merge_winner_changed": True},
    ]
    before = deepcopy(rows)

    first = runner.describe_congestion_episodes(
        rows,
        enter_threshold=5.0,
        exit_threshold=2.0,
        time_block_seconds=30.0,
    )
    second = runner.describe_congestion_episodes(
        rows,
        enter_threshold=5.0,
        exit_threshold=2.0,
        time_block_seconds=30.0,
    )

    assert rows == before
    assert first == second
    assert [(row["owner"], row["closed"]) for row in first] == [(7, True), (8, False)]
    episode = first[0]
    assert episode["start"] == {"time_seconds": 10.0, "queue_value": 5.0, "row_index": 2}
    assert episode["peak"] == {"time_seconds": 20.0, "queue_value": 8.0, "row_index": 3}
    assert episode["end"] == {"time_seconds": 40.0, "queue_value": 2.0, "row_index": 5}
    assert episode["time_block"] == 0
    assert episode["leg"] == "mixed"
    assert episode["queue_slope_to_peak_per_second"] == pytest.approx(0.3)
    assert episode["s4_v2_divergence_row_count"] == 1
    assert episode["merge_winner_change_row_count"] == 1
    assert [row["row_id"] for row in episode["affected_rows"]] == ["a1", "a2", "a3", "a4"]


def test_analyze_stage_reuses_cache_and_keeps_episode_census_pending(tmp_path: Path) -> None:
    inputs, s4, v2 = _matched_rows()
    cache = runner.make_raw_cache(inputs, s4, v2, input_descriptor={"scale": 2})
    cache_path = tmp_path / "cache.json"
    segment_path = tmp_path / "segments.csv"
    task_path = tmp_path / "tasks.csv"
    summary_path = tmp_path / "summary.json"
    by_leg_path = tmp_path / "by_leg.csv"
    by_source_time_path = tmp_path / "by_source_time.csv"
    by_hotspot_time_leg_path = tmp_path / "by_hotspot_time_leg.csv"
    gap_report_path = tmp_path / "gap_report.md"
    episodes_path = tmp_path / runner.DEFAULT_EPISODE_STATUS
    cache_path.write_text(json.dumps(cache), encoding="utf-8")

    code = runner.main(
        [
            "--stage",
            "analyze",
            "--root",
            str(tmp_path),
            "--cache",
            str(cache_path),
            "--segment-ledger",
            str(segment_path),
            "--task-ledger",
            str(task_path),
            "--summary",
            str(summary_path),
            "--by-leg",
            str(by_leg_path),
            "--by-source-time",
            str(by_source_time_path),
            "--by-hotspot-time-leg",
            str(by_hotspot_time_leg_path),
            "--gap-report",
            str(gap_report_path),
        ]
    )

    assert code == 0
    assert segment_path.exists() and task_path.exists() and summary_path.exists()
    assert by_leg_path.exists() and by_source_time_path.exists()
    assert by_hotspot_time_leg_path.exists()
    assert gap_report_path.exists()
    with by_hotspot_time_leg_path.open(newline="", encoding="utf-8") as handle:
        hotspot_rows = list(csv.DictReader(handle))
    storage_out_cell = next(
        row for row in hotspot_rows if row["leg"] == "storage_out"
    )
    assert storage_out_cell["source"] == "node_2"
    assert storage_out_cell["release_time_block"] == "0"
    assert storage_out_cell["row_count"] == "1"
    report = gap_report_path.read_text(encoding="utf-8")
    assert "true `storage_out` admission seam is `node_52`" in report
    assert "raw-task origin rows" in report
    episode_artifact = json.loads(episodes_path.read_text(encoding="utf-8"))
    assert episode_artifact["status"] == "PENDING_ACTION_CENSUS"
    assert episode_artifact["episodes"] == []


def test_episode_threshold_contract_is_explicit() -> None:
    with pytest.raises(runner.GapEpisodeError, match="enter > exit"):
        runner.describe_congestion_episodes(
            [{"owner": 1, "time_seconds": 0.0, "queue_length": 2.0}],
            enter_threshold=2.0,
            exit_threshold=2.0,
        )

    inputs, s4, v2 = _matched_rows()
    cache = runner.make_raw_cache(inputs, s4, v2)
    with pytest.raises(runner.GapEpisodeError, match="thresholds are required"):
        runner.analyze_raw_cache(
            cache,
            episode_rows=[{"owner": 1, "time_seconds": 0.0, "queue_length": 2.0}],
        )


def test_streamed_route_census_uses_only_candidate_consistent_current_signal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "census.jsonl"
    rows = [
        {
            "candidate_observations": [
                {"junction_queue_length": 4.0, "priority_local_contention": 17.0},
                {"junction_queue_length": 4.0, "priority_local_contention": 17.0},
            ],
            "current_node": 9,
            "event_ordinal": 10,
            "event_time": 100.0,
            "segment_id": "1:storage_in:g4irsf10_c0",
            "task_id": 1,
        },
        {
            "candidate_observations": [
                {"junction_queue_length": 3.0, "priority_local_contention": 7.0},
                {"junction_queue_length": 3.0, "priority_local_contention": 7.0},
            ],
            "current_node": 9,
            "event_ordinal": 11,
            "event_time": 110.0,
            "segment_id": "2:direct:g4irsf10_c0",
            "task_id": 2,
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    compact, audit = runner.stream_route_census_episode_rows(path)
    artifact = runner.analyze_route_census_episodes(
        path,
        enter_threshold=16.0,
        exit_threshold=8.0,
        affected_row_limit=3,
    )

    assert [row["local_contention_signal"] for row in compact] == [17.0, 7.0]
    assert audit["candidate_current_field_consistency"] == "PASS"
    assert audit["target_candidate_queue_fields_used"] is False
    assert artifact["sampling_basis"] == "route_decision_sampled"
    assert artifact["status"] == "DETECTION_COMPLETE"
    assert artifact["coverage"]["episode_count"] == 1
    assert artifact["coverage"]["owners"] == [9]
    assert artifact["coverage"]["legs"] == ["direct", "storage_in"]

    drift = deepcopy(rows)
    drift[0]["candidate_observations"][1]["priority_local_contention"] = 18.0
    path.write_text("\n".join(json.dumps(row) for row in drift) + "\n", encoding="utf-8")
    with pytest.raises(runner.GapEpisodeError, match="candidate copies disagree"):
        runner.stream_route_census_episode_rows(path)
