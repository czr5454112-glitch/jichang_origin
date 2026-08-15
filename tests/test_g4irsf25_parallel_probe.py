from __future__ import annotations

import csv
import copy
import io
import json
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.eval import run_g4irsf24_native_race as g24_race
from scripts.eval import run_g4irsf25_parallel_probe as probe


def _decision(index: int, *, event_time: float = 1.0) -> dict[str, Any]:
    current = index * 10 + 1
    return {
        "decision_id": f"fixture:{index}",
        "task_id": index,
        "segment_id": f"segment-{index}",
        "event_time": event_time,
        "current_node": current,
        "selected_next": current + 1,
        "fallback_selected_next": current + 1,
        "candidate_next_nodes": [current + 1],
        "metadata": {"arrive_event_seq": index},
    }


def _event(index: int, *, event_time: float = 1.0) -> dict[str, Any]:
    current = index * 10 + 1
    return {
        "seq": index,
        "event": "ARRIVE_JUNCTION",
        "time": event_time,
        "node": current,
        "from_node": current - 1,
        "to_node": current + 1,
    }


def _summary(segment_count: int = 2) -> dict[str, Any]:
    return {
        "completed_count": segment_count,
        "event_count": 200,
        "decision_count": 20,
        **{name: 0 for name in g24_race.HARD_SAFETY_ZERO_FIELDS},
        **{name: False for name in g24_race.HARD_SAFETY_FALSE_FIELDS},
        "scorer_mode": "S4_queue_aware_rule_only",
        "pibt_mode": "P2",
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "event_semantics": "E4_batch_plus_destination_merge_request",
        "g4irsf20_event_hotpath_policy": "E2",
    }


def _bags(*, mismatch: bool = False) -> list[dict[str, Any]]:
    rows = []
    for index in range(2):
        rows.append(
            {
                "segment_id": f"segment-{index}",
                "task_id": index,
                "runtime_bag_id": index,
                "start": index,
                "goal": 47,
                "final_node": 47,
                "completed": True,
                "failed": False,
                "failure_reason": "",
                "release_time": float(index),
                "admitted_time": float(index + 1),
                "finish_time": float(index + 10 + (1 if mismatch and index == 1 else 0)),
                "decision_count": 10,
                "retry_count": 0,
                "loop_count": 0,
                "junction_queue_wait_seconds": 1.0,
                "merge_grant_wait_seconds": 0.0,
                "short_history": [index, 47],
            }
        )
    return rows


def test_exact_lifecycle_loader_returns_validated_full_prefix(
    tmp_path, monkeypatch
) -> None:
    prefix = SimpleNamespace(
        size_segments=2,
        rows=(
            {"segment_id": "a", "task_id": 1, "start": 3, "goal": 47},
            {"segment_id": "b", "task_id": 2, "start": 4, "goal": 47},
        ),
        raw_bag_count=2,
        first_segment_id="a",
        last_segment_id="b",
    )
    release_csv = tmp_path / "release.csv"
    release_csv.write_text(
        "segment_id,task_id,start,goal,release_epoch\n"
        "a,1,3,47,1.0\n"
        "b,2,4,47,2.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(probe.harness, "FULL_SIZE_SEGMENTS", 2)
    monkeypatch.setattr(
        probe.harness,
        "load_input_prefix",
        lambda size_segments, root: prefix,
    )
    monkeypatch.setattr(
        probe.g24_race,
        "apply_exact_hca_releases",
        lambda selected, path: (selected, {}),
    )

    adjusted, metadata = probe.load_exact_lifecycle(release_csv)

    assert adjusted is prefix
    assert metadata["release_row_count"] == 2
    assert metadata["gates"]["release_segment_id_set_exact"] is True
    assert metadata["gates"]["release_task_start_goal_match_canonical"] is True
    assert metadata["gates"]["release_epochs_finite"] is True
    assert metadata["pass"] is True


def test_exact_lifecycle_loader_rejects_mismatched_route_metadata(
    tmp_path, monkeypatch
) -> None:
    prefix = SimpleNamespace(
        size_segments=1,
        rows=(
            {"segment_id": "a", "task_id": 1, "start": 3, "goal": 47},
        ),
        raw_bag_count=1,
        first_segment_id="a",
        last_segment_id="a",
    )
    release_csv = tmp_path / "release.csv"
    release_csv.write_text(
        "segment_id,task_id,start,goal,release_epoch\n"
        "a,1,4,47,1.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(probe.harness, "FULL_SIZE_SEGMENTS", 1)
    monkeypatch.setattr(
        probe.harness,
        "load_input_prefix",
        lambda size_segments, root: prefix,
    )

    with pytest.raises(probe.ParallelProbeError, match="release contract failed"):
        probe.load_exact_lifecycle(release_csv)


def test_densest_release_window_selects_the_minimum_span_cluster() -> None:
    rows = tuple(
        {
            "segment_id": segment_id,
            "task_id": ordinal,
            "pass_time": release,
            "input_row_index": ordinal,
        }
        for ordinal, (segment_id, release) in enumerate(
            (
                ("prefix-a", 0.0),
                ("prefix-b", 100.0),
                ("prefix-c", 200.0),
                ("dense-a", 50.0),
                ("dense-b", 51.0),
                ("dense-c", 52.0),
            )
        )
    )
    full = SimpleNamespace(rows=rows)

    prefix, prefix_metadata = probe.select_prefix_release_window(
        full, window_size=3
    )
    dense, dense_metadata = probe.select_densest_release_window(
        full, window_size=3
    )

    assert [row["segment_id"] for row in prefix.rows] == [
        "prefix-a",
        "prefix-b",
        "prefix-c",
    ]
    assert [row["segment_id"] for row in dense.rows] == [
        "dense-a",
        "dense-b",
        "dense-c",
    ]
    assert dense_metadata["release_span_seconds"] == 2.0
    assert dense_metadata["release_span_seconds"] < prefix_metadata[
        "release_span_seconds"
    ]


def test_densest_release_window_tie_break_is_input_order_independent() -> None:
    rows = [
        {
            "segment_id": segment_id,
            "task_id": ordinal,
            "pass_time": release,
            "input_row_index": ordinal,
        }
        for ordinal, (segment_id, release) in enumerate(
            (
                ("z-first", 0.0),
                ("z-last", 1.0),
                ("a-first", 10.0),
                ("a-last", 11.0),
            )
        )
    ]

    selected_a, metadata_a = probe.select_densest_release_window(
        SimpleNamespace(rows=tuple(rows)), window_size=2
    )
    selected_b, metadata_b = probe.select_densest_release_window(
        SimpleNamespace(rows=tuple(reversed(rows))), window_size=2
    )

    expected = ["a-first", "a-last"]
    assert [row["segment_id"] for row in selected_a.rows] == expected
    assert [row["segment_id"] for row in selected_b.rows] == expected
    assert metadata_a["release_sorted_start_index"] == metadata_b[
        "release_sorted_start_index"
    ]


def test_trace_analysis_finds_disjoint_same_phase_width() -> None:
    events = [_event(index) for index in range(4)]
    decisions = [_decision(index) for index in range(4)]

    result = probe.analyze_trace_parallelism(
        events,
        decisions,
        event_semantics="E4_batch_plus_destination_merge_request",
    )

    assert result["go"] is True
    assert result["status"] == "GO"
    assert result["event"]["effective_width"] == 4.0
    assert result["decision"]["effective_width"] == 4.0
    assert result["event"]["max_conflict_free_width"] == 4


def test_trace_analysis_reconstructs_monotone_same_time_floor() -> None:
    events = [
        {
            "seq": 1,
            "event": "LOCAL_QUEUE_UPDATE",
            "time": 5.0,
            "node": 1,
            "from_node": -1,
            "to_node": -1,
        },
        {
            "seq": 2,
            "event": "BAG_RELEASE",
            "time": 5.0,
            "node": 3,
            "from_node": -1,
            "to_node": 4,
        },
    ]

    result = probe.analyze_trace_parallelism(
        events,
        [_decision(0), _decision(1)],
        event_semantics="E4_batch_plus_destination_merge_request",
    )

    assert len(result["event"]["groups"]) == 1
    assert result["event"]["groups"][0]["microphase"] == 3


def test_trace_analysis_rejects_singleton_width() -> None:
    events = [_event(index, event_time=float(index)) for index in range(4)]
    decisions = [_decision(index, event_time=float(index)) for index in range(4)]

    result = probe.analyze_trace_parallelism(
        events,
        decisions,
        event_semantics="E4_batch_plus_destination_merge_request",
    )

    assert result["go"] is False
    assert result["status"] == "NO_GO"
    assert result["event"]["effective_width"] == 1.0


def test_trace_analysis_requires_complete_canary_traces() -> None:
    result = probe.analyze_trace_parallelism(
        [_event(index) for index in range(4)],
        [_decision(index) for index in range(4)],
        event_semantics="E4_batch_plus_destination_merge_request",
        event_trace_complete=False,
    )

    assert result["opportunity_gates"]["event_effective_width_at_least_1_7"] is True
    assert result["sample_gates"]["event_trace_complete"] is False
    assert result["status"] == "NO_GO"


def test_fake_threadpool_executor_meets_throughput_and_equivalence_gate() -> None:
    active = 0
    max_active = 0
    lock = threading.Lock()

    def executor(**_: Any) -> dict[str, Any]:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.04)
        with lock:
            active -= 1
        return {"summary": _summary(), "bags": _bags()}

    result = probe.run_throughput_probe(
        executor=executor,
        request_factory=lambda lane, mode, round_index: {
            "scenario": f"{mode}-{round_index}-{lane}"
        },
        expected_segments=2,
        rounds=2,
    )

    assert max_active == 2
    assert result["aggregate_speedup"] >= 1.7
    assert result["equivalence_pass"] is True
    assert result["status"] == "GO"
    assert result["latency_guard_pass"] is True
    assert result["parallel_individual_wall_regression_fraction"] <= 0.10
    assert "not the default" in result["claim_scope"]
    assert [pair["lane_order"] for pair in result["pairs"] if pair["mode"] == "sequential"] == [
        ["A", "B"],
        ["B", "A"],
    ]
    assert all(not any(key.startswith("_") for key in run) for run in result["runs"])


def test_latency_regression_limits_promotion_to_batch_throughput() -> None:
    def executor(**request: Any) -> dict[str, Any]:
        delay = 0.056 if str(request["scenario"]).startswith("parallel") else 0.050
        time.sleep(delay)
        return {"summary": _summary(), "bags": _bags()}

    result = probe.run_throughput_probe(
        executor=executor,
        request_factory=lambda lane, mode, round_index: {
            "scenario": f"{mode}-{round_index}-{lane}"
        },
        expected_segments=2,
        rounds=2,
    )

    assert result["aggregate_speedup"] >= 1.7
    assert result["parallel_individual_wall_regression_fraction"] > 0.10
    assert result["latency_guard_pass"] is False
    assert result["batch_throughput_go"] is True
    assert result["go"] is False
    assert result["status"] == "GO_BATCH_THROUGHPUT_ONLY"
    assert result["deployment_scope"] == "offline_or_independent_runtime_batch_only"


def test_missing_full_cie_count_remains_fail_closed() -> None:
    summary = _summary()
    summary.pop("runtime_full_cie_astar_calls")

    reduced = probe._reduce_payload(
        {"summary": summary, "bags": _bags()},
        expected_segments=2,
    )

    assert reduced["safety_pass"] is False


def test_parallel_business_drift_fails_equivalence_gate() -> None:
    def executor(**request: Any) -> dict[str, Any]:
        mismatch = request["scenario"] == "parallel-0-B"
        time.sleep(0.01)
        return {"summary": _summary(), "bags": _bags(mismatch=mismatch)}

    result = probe.run_throughput_probe(
        executor=executor,
        request_factory=lambda lane, mode, round_index: {
            "scenario": f"{mode}-{round_index}-{lane}"
        },
        expected_segments=2,
        rounds=1,
        throughput_gate=1.0,
    )

    assert result["equivalence_pass"] is False
    assert result["gates"]["every_run_business_equivalent"] is False
    assert result["status"] == "NO_GO"


def test_csv_and_report_keep_claim_scope_explicit() -> None:
    analysis = probe.analyze_trace_parallelism(
        [_event(index) for index in range(4)],
        [_decision(index) for index in range(4)],
        event_semantics="E4_batch_plus_destination_merge_request",
    )

    def executor(**request: Any) -> dict[str, Any]:
        delay = 0.025 if str(request["scenario"]).startswith("parallel") else 0.020
        time.sleep(delay)
        return {"summary": _summary(), "bags": _bags()}

    throughput = probe.run_throughput_probe(
        executor=executor,
        request_factory=lambda lane, mode, round_index: {
            "scenario": f"{mode}-{round_index}-{lane}"
        },
        expected_segments=2,
        rounds=1,
        throughput_gate=1.0,
    )
    event_observation = {
        "coverage_fraction": 1.0,
        "untraced_event_count": 0,
        "event_trace_untruncated": True,
        "untraced_destination_merge_arbitration_count": 0,
        "untraced_stale_arbitration_count": 0,
        "untraced_other_event_count": 0,
        "optimistic_effective_width_if_all_untraced_pack_existing_waves": analysis[
            "event"
        ]["effective_width"],
        "optimistic_parallel_item_fraction_if_all_untraced_are_parallel": analysis[
            "event"
        ]["conflict_free_parallel_item_fraction"],
    }
    trace_run = {
        "stored_event_trace_rows": 4,
        "full_run_event_count": 4,
        "stored_decision_or_hold_trace_rows": 4,
        "safety_pass": True,
    }
    windows = {}
    for key, kind, release_min, release_max in (
        ("prefix", "canonical_prefix", 0.0, 100.0),
        (
            "peak_release_density",
            "densest_release_sorted_contiguous",
            10.0,
            11.0,
        ),
    ):
        window_analysis = copy.deepcopy(analysis)
        window_analysis["event_trace_observation"] = copy.deepcopy(
            event_observation
        )
        label = "PREFIX" if key == "prefix" else "PEAK_RELEASE"
        windows[key] = {
            "selection": {
                "window_kind": kind,
                "segment_count": 2,
                "release_epoch_min": release_min,
                "release_epoch_max": release_max,
                "release_span_seconds": release_max - release_min,
                "release_density_segments_per_second": 2.0
                / (release_max - release_min),
            },
            "analysis": window_analysis,
            "trace_run": copy.deepcopy(trace_run),
            "opportunity_assessment": probe._assess_same_stream_window(
                window_analysis,
                trace_run,
                window_label=label,
                window_size=2,
            ),
        }
    combined = {
        "status": "OPPORTUNITY_NOT_EXCLUDED_ON_TESTED_2_WINDOWS",
        "window_size_segments": 2,
        "both_tested_windows_definitively_fail_any_required_width_or_fraction_gate": False,
        "implementation_recommendation": "DEFER_SAME_STREAM_PARALLEL_IMPLEMENTATION",
    }
    payload = {
        "protocol": {
            "lifecycle": {
                "segment_count": 2,
                "release_csv": "fixture.csv",
            },
            "trace_canary": {"segment_count": 2},
            "binary": {"path": "Release/fixture.pyd", "size_bytes": 1234},
        },
        "same_stream": {
            "analysis": windows["prefix"]["analysis"],
            "trace_run": windows["prefix"]["trace_run"],
            "windows": windows,
            "combined_assessment": combined,
        },
        "independent_runs": throughput,
        "decision": {
            "same_stream_node_parallel": combined["status"],
            "independent_run_parallel_throughput": throughput["status"],
            "independent_run_deployment_scope": throughput["deployment_scope"],
        },
    }
    for window in payload["same_stream"]["windows"].values():
        probe._compact_trace_groups(window["analysis"])

    csv_rows = list(csv.DictReader(io.StringIO(probe._csv_bytes(payload).decode("utf-8"))))
    report = probe._report(payload)

    assert {row["record_type"] for row in csv_rows} == {
        "trace_window",
        "trace_summary",
        "trace_width_histogram",
        "trace_microphase_summary",
        "throughput_pair",
        "throughput_run",
        "throughput_mode_summary",
    }
    trace_window_rows = [
        row for row in csv_rows if row["record_type"] == "trace_window"
    ]
    assert {row["window"] for row in trace_window_rows} == {
        "prefix",
        "peak_release_density",
    }
    assert all(row["event_trace_coverage_fraction"] == "1.0" for row in trace_window_rows)
    assert all(
        row["event_optimistic_effective_width_upper_bound"] == "4.0"
        for row in trace_window_rows
    )
    assert all(
        "groups" not in window["analysis"]["event"]
        for window in payload["same_stream"]["windows"].values()
    )
    assert all(
        len(window["analysis"]["event"]["top_anomalous_groups"]) <= 20
        for window in payload["same_stream"]["windows"].values()
    )
    assert len(json.dumps(payload)) < 200_000
    assert "not a default for one live order stream" in report
    assert "Individual-wall latency guard" in report
    assert "supports only offline batch work" in report
    assert "does not implement order-stream routing" in report
    assert "one serial event loop" in report
    assert "cannot be extrapolated to a larger map or a new" in report
