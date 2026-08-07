from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import analyze_g4irsf18_parallelism_census as census


def _row(
    opportunity_id: int,
    *,
    event_time: float,
    destination: int,
    upstream: int,
    request_id: int,
    candidate_count: int = 1,
) -> dict[str, object]:
    return {
        "opportunity_id": opportunity_id,
        "event_time": event_time,
        "destination_node": destination,
        "upstream_node": upstream,
        "candidate_request_id": request_id,
        "candidate_count": candidate_count,
    }


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def test_census_finds_stable_local_scoring_pack(tmp_path: Path) -> None:
    trace = _write(
        tmp_path / "trace.jsonl",
        [
            _row(1, event_time=10.0, destination=10, upstream=1, request_id=101),
            _row(2, event_time=10.0, destination=20, upstream=2, request_id=201),
            _row(3, event_time=10.0, destination=30, upstream=1, request_id=301),
            _row(
                4,
                event_time=20.0,
                destination=40,
                upstream=4,
                request_id=401,
                candidate_count=2,
            ),
            _row(
                4,
                event_time=20.0,
                destination=40,
                upstream=5,
                request_id=402,
                candidate_count=2,
            ),
        ],
    )

    result = census.build_census(trace)

    all_rows = result["all_merge_opportunities"]
    assert all_rows["opportunity_count"] == 4
    assert all_rows["timestamp_bucket_count"] == 2
    assert all_rows["timestamp_bucket_size"]["max"] == 3
    assert all_rows["greedy_local_scoring_width"]["max"] == 2
    assert all_rows["local_scoring_conflict_pair_count"] == 1
    assert all_rows["opportunities_in_multi_scoring_buckets"] == 3
    eligible = result["eligible_multi_candidate_opportunities"]
    assert eligible["opportunity_count"] == 1
    assert eligible["greedy_local_scoring_width"]["max"] == 1
    assert "not a maximum independent set" in " ".join(result["claim_boundary"])


def test_local_scoring_keys_cover_declared_resource_aliases() -> None:
    def opportunity(
        destination: int,
        upstream: int,
        request_id: int,
    ) -> dict[str, object]:
        return {
            "destination_node": destination,
            "upstream_nodes": [upstream],
            "candidate_request_ids": [request_id],
        }

    base = census.resource_keys(opportunity(10, 1, 101))
    assert base.isdisjoint(census.resource_keys(opportunity(20, 2, 202)))
    assert not base.isdisjoint(census.resource_keys(opportunity(10, 2, 202)))
    assert not base.isdisjoint(census.resource_keys(opportunity(20, 1, 202)))
    assert not base.isdisjoint(census.resource_keys(opportunity(20, 2, 101)))
    assert not base.isdisjoint(census.resource_keys(opportunity(20, 10, 202)))


def test_exact_bit_timestamp_buckets_and_nearest_rank(tmp_path: Path) -> None:
    trace = _write(
        tmp_path / "bits.jsonl",
        [
            _row(1, event_time=0.0, destination=10, upstream=1, request_id=101),
            _row(2, event_time=-0.0, destination=20, upstream=2, request_id=202),
            _row(3, event_time=1.0, destination=30, upstream=3, request_id=303),
            _row(4, event_time=1.0, destination=40, upstream=4, request_id=404),
        ],
    )

    summary = census.build_census(trace)["all_merge_opportunities"]
    assert summary["timestamp_bucket_count"] == 3
    assert summary["timestamp_bucket_size"]["histogram"] == {"1": 2, "2": 1}
    assert summary["greedy_local_scoring_width"]["max"] == 2
    assert summary["opportunity_share_in_multi_scoring_buckets"] == 0.5
    assert census._nearest_rank([1] * 95 + [2] * 5, 0.95) == 1
    assert census._nearest_rank([1] * 95 + [2] * 5, 0.99) == 2


def test_companion_result_proves_complete_zero_drop_trace(tmp_path: Path) -> None:
    trace = _write(
        tmp_path / "fixture.jsonl",
        [_row(1, event_time=10.0, destination=10, upstream=1, request_id=101)],
    )
    companion = tmp_path / "fixture.json"
    companion.write_text(
        json.dumps(
            {
                "counters": {
                    "merge_grant_opportunity_trace_total_count": 1,
                    "merge_grant_opportunity_trace_stored_count": 1,
                    "merge_grant_opportunity_trace_dropped_count": 0,
                    "g4irsf18_merge_model_opportunity_count": 1,
                    "g4irsf18_merge_model_eligible_count": 0,
                }
            }
        ),
        encoding="utf-8",
    )

    completeness = census.build_census(
        trace, companion
    )["trace_completeness"]
    assert completeness["status"] == "PASS_COMPLETE_ZERO_DROPPED"
    assert completeness["trace_stored_count"] == 1


def test_census_rejects_incomplete_candidate_set(tmp_path: Path) -> None:
    trace = _write(
        tmp_path / "bad.jsonl",
        [
            _row(
                1,
                event_time=10.0,
                destination=10,
                upstream=1,
                request_id=101,
                candidate_count=2,
            )
        ],
    )

    with pytest.raises(census.ParallelismCensusError, match="declares 2 candidates"):
        census.build_census(trace)


def test_census_rejects_nonfinite_event_time(tmp_path: Path) -> None:
    trace = _write(
        tmp_path / "nonfinite.jsonl",
        [_row(1, event_time=float("inf"), destination=10, upstream=1, request_id=101)],
    )

    with pytest.raises(census.ParallelismCensusError, match="must be finite"):
        census.build_census(trace)
