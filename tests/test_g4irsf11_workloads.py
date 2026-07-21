from __future__ import annotations

import pytest

from scripts.eval.g4irsf11_workloads import (
    FORMAL_WORKLOAD_MODES,
    FRONTIER_SCALES,
    aggregate_raw_bags,
    binding_bag_records,
    build_workload,
    namespace_workload,
    workload_manifest,
)


BASE = [
    {
        "segment_id": f"{index}:direct",
        "task_id": index,
        "pallet_id": index,
        "pass_time": float(index * 10),
        "original_entry_time": float(index * 10 - 1),
        "std": float(index * 10 + 20),
        "start": index % 2,
        "goal": 3,
        "leg": "direct",
    }
    for index in range(20)
]


def test_frontier_is_exact_fractional_protocol() -> None:
    assert FRONTIER_SCALES == (2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0)


def test_time_compression_changes_rate_without_copying_bags() -> None:
    rows = build_workload(BASE, scale=2.5, mode="time_compressed")
    manifest = workload_manifest(rows)
    assert len(rows) == len(BASE)
    assert manifest["arrival_span_seconds"] == 190.0 / 2.5
    assert manifest["original_java_rule_replay"] is False
    assert all(row["future_route_stored"] is False for row in rows)


def test_fractional_replicas_are_deterministic_and_order_independent() -> None:
    forward = build_workload(BASE, scale=2.25, mode="stratified_replicas")
    reverse = build_workload(list(reversed(BASE)), scale=2.25, mode="stratified_replicas")
    assert forward == reverse
    assert len(BASE) * 2 <= len(forward) <= len(BASE) * 3
    assert {row["task_id"] for row in forward} == set(range(len(BASE)))
    assert any(row["generation_copy_index"] == 2 for row in forward)


def test_binding_records_preserve_original_ids_and_have_unique_segments_no_route() -> None:
    rows = build_workload(BASE, scale=2.0, mode="stratified_replicas")
    records = binding_bag_records(rows)
    assert len(records) == 40
    assert len({record[0] for record in records}) == 40
    assert len({record[1] for record in records}) == 20
    assert all(len(record) == 7 for record in records)


def test_original_elapsed_and_java_release_tth_are_separate() -> None:
    workload = [
        {
            "task_id": 7,
            "segment_id": "7:in:g4irsf11_c0",
            "original_task_id": 7,
            "pallet_id": 7,
            "generation_copy_index": 0,
            "leg": "storage_in",
            "original_arrival_time": 0.0,
            "release_time": 0.0,
            "deadline": 100.0,
            "source": "node_0",
        },
        {
            "task_id": 7,
            "segment_id": "7:out:g4irsf11_c0",
            "original_task_id": 7,
            "pallet_id": 7,
            "generation_copy_index": 0,
            "leg": "storage_out",
            "original_arrival_time": 0.0,
            "release_time": 50.0,
            "deadline": 100.0,
            "source": "node_2",
        },
    ]
    segments = [
        {"runtime_bag_id": 0, "task_id": 7, "segment_id": "7:in:g4irsf11_c0", "admitted_time": 1.0, "finish_time": 11.0, "completed": True, "total_local_wait": 1.0},
        {"runtime_bag_id": 1, "task_id": 7, "segment_id": "7:out:g4irsf11_c0", "admitted_time": 51.0, "finish_time": 61.0, "completed": True, "total_local_wait": 1.0},
    ]
    bags, enriched = aggregate_raw_bags(workload, segments)
    assert len(enriched) == 2
    assert bags[0]["finish_time"] - bags[0]["original_arrival_time"] == 61.0
    assert bags[0]["java_release_tth_seconds"] == 20.0
    assert bags[0]["complete"] is True


def test_trace_workloads_can_be_namespaced_without_changing_times() -> None:
    rows = build_workload(BASE, scale=2.0, mode="time_compressed")
    namespaced = namespace_workload(rows, scenario="high_flow_2x", task_id_offset=0)
    assert namespaced[0]["task_id"] == rows[0]["task_id"]
    assert namespaced[0]["segment_id"].endswith(":high_flow_2x")
    assert namespaced[0]["release_time"] == rows[0]["release_time"]
    with pytest.raises(ValueError, match="rewrite original source identity"):
        namespace_workload(rows, scenario="bad", task_id_offset=1_000_000)


def test_all_formal_modes_are_deterministic_and_do_not_rewrite_source_ids() -> None:
    for mode in FORMAL_WORKLOAD_MODES:
        forward = build_workload(BASE, scale=2.25, mode=mode)
        reverse = build_workload(list(reversed(BASE)), scale=2.25, mode=mode)
        assert forward == reverse
        assert {int(row["task_id"]) for row in forward} <= set(range(len(BASE)))
        assert len({str(row["segment_id"]) for row in forward}) == len(forward)


def test_fractional_replica_keeps_both_storage_legs_together() -> None:
    base = [
        {
            "segment_id": f"77:{leg}",
            "task_id": 77,
            "pallet_id": 77,
            "pass_time": 10.0 if leg == "storage_in" else 50.0,
            "original_entry_time": 10.0,
            "std": 100.0,
            "start": 0,
            "goal": 3,
            "leg": leg,
        }
        for leg in ("storage_in", "storage_out")
    ]
    rows = build_workload(base, scale=2.25, mode="empirical_interarrival_jitter")
    counts: dict[int, int] = {}
    for row in rows:
        counts[int(row["generation_copy_index"])] = counts.get(int(row["generation_copy_index"]), 0) + 1
    assert set(counts.values()) == {2}
