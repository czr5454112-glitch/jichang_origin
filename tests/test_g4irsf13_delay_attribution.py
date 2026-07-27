from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf13_delay_attribution as attribution


ROOT = Path(__file__).resolve().parents[1]


def _map() -> dict[str, object]:
    return json.loads(
        (ROOT / attribution.MAP_PATH).read_text(encoding="utf-8")
    )


F2_PATHS = {
    "0:direct": [52, 40, 41, 42, 30, 31, 32, 37, 49],
    "1:storage_in": [3, 16, 17, 18, 22, 24, 27, 28, 47],
    "1:storage_out": [52, 29, 30, 31, 32, 37, 49],
}
V2_PATHS = {
    "0:direct": [52, 29, 30, 31, 32, 37, 49],
    "1:storage_in": [3, 16, 17, 18, 22, 24, 27, 28, 47],
    "1:storage_out": [52, 29, 30, 31, 32, 37, 49],
}


def _real_path_metrics(
    path: list[int],
    *,
    minimum_service_seconds: float,
) -> dict[str, float]:
    edge, service, _indegree, shortest = attribution._graph_metadata(_map())
    return attribution._path_metrics(
        path,
        edge,
        service,
        shortest,
        minimum_service_seconds=minimum_service_seconds,
    )


def _input_rows() -> list[dict[str, object]]:
    return [
        {
            "task_id": 0,
            "pallet_id": 100,
            "segment_id": "0:direct",
            "leg": "direct",
            "start": 52,
            "goal": 49,
            "original_start": 52,
            "original_goal": 49,
            "original_entry_time": 0.0,
            "pass_time": 5.0,
            "std": 100.0,
        },
        {
            "task_id": 1,
            "pallet_id": 101,
            "segment_id": "1:storage_in",
            "leg": "storage_in",
            "start": 3,
            "goal": 47,
            "original_start": 3,
            "original_goal": 49,
            "original_entry_time": 10.0,
            "pass_time": 10.0,
            "std": 100.0,
        },
        {
            "task_id": 1,
            "pallet_id": 101,
            "segment_id": "1:storage_out",
            "leg": "storage_out",
            "start": 52,
            "goal": 49,
            "original_start": 3,
            "original_goal": 49,
            "original_entry_time": 10.0,
            "pass_time": 20.0,
            "std": 100.0,
        },
    ]


def _v2_source_rows() -> list[dict[str, object]]:
    rows = deepcopy(_input_rows())
    rows[0]["pass_time"] = 4.0
    return rows


def _f2_bag(
    *,
    segment_id: str,
    task_id: int,
    runtime_bag_id: int,
    start: int,
    goal: int,
    release: float,
    source_wait: float,
    junction_wait: float,
    travel: float,
    service: float,
) -> dict[str, object]:
    completion = source_wait + junction_wait + travel + service
    return {
        "segment_id": segment_id,
        "task_id": task_id,
        "runtime_bag_id": runtime_bag_id,
        "start": start,
        "goal": goal,
        "release_time": release,
        "admitted_time": release + source_wait,
        "finish_time": release + completion,
        "source_queue_delay": source_wait,
        "total_local_wait": junction_wait,
        "junction_queue_wait_seconds": junction_wait,
        "edge_travel_time_seconds": travel,
        "node_service_time_seconds": service,
        "loop_extra_time_seconds": 0.0,
        "goal_completion_time_seconds": completion,
        "completed": True,
        "failure_reason": "",
    }


def _payloads() -> tuple[dict[str, object], dict[str, object]]:
    f2_metrics = {
        segment_id: _real_path_metrics(
            path, minimum_service_seconds=1.0e-3
        )
        for segment_id, path in F2_PATHS.items()
    }
    v2_metrics = {
        segment_id: _real_path_metrics(
            path, minimum_service_seconds=0.0
        )
        for segment_id, path in V2_PATHS.items()
    }
    f2_bags = [
        _f2_bag(
            segment_id="0:direct",
            task_id=0,
            runtime_bag_id=0,
            start=52,
            goal=49,
            release=5.0,
            source_wait=1.0,
            junction_wait=2.0,
            travel=f2_metrics["0:direct"]["edge_travel_time"],
            service=f2_metrics["0:direct"]["node_service_time"],
        ),
        _f2_bag(
            segment_id="1:storage_in",
            task_id=1,
            runtime_bag_id=1,
            start=3,
            goal=47,
            release=10.0,
            source_wait=0.0,
            junction_wait=0.0,
            travel=f2_metrics["1:storage_in"]["edge_travel_time"],
            service=f2_metrics["1:storage_in"]["node_service_time"],
        ),
        _f2_bag(
            segment_id="1:storage_out",
            task_id=1,
            runtime_bag_id=2,
            start=52,
            goal=49,
            release=20.0,
            source_wait=0.0,
            junction_wait=0.0,
            travel=f2_metrics["1:storage_out"]["edge_travel_time"],
            service=f2_metrics["1:storage_out"]["node_service_time"],
        ),
    ]
    outgoing = {
        int(node["location"]): [int(value) for value in node["outgoing"]]
        for node in _map()["nodes"]
    }
    decisions: list[dict[str, object]] = []
    decision_ordinal = 0
    for segment_id, path in F2_PATHS.items():
        source = next(
            row for row in _input_rows() if row["segment_id"] == segment_id
        )
        for current, selected in zip(path, path[1:]):
            decision_ordinal += 1
            candidates = outgoing[current]
            decisions.append(
                {
                    "decision_id": f"real-map:{decision_ordinal}",
                    "task_id": source["task_id"],
                    "segment_id": segment_id,
                    "event_time": float(decision_ordinal),
                    "current_node": current,
                    "goal_node": source["goal"],
                    "candidate_next_nodes": candidates,
                    "candidate_records": [
                        {
                            "next_node": candidate,
                            "features": {
                                "static_potential": float(candidate),
                                "travel_time": 1.0,
                                "target_queue_length": 0,
                            },
                            "model_score": float(candidate),
                            "shield_allowed": True,
                            "shield_reason": "allowed",
                        }
                        for candidate in candidates
                    ],
                    "selected_next": selected,
                    "local_snapshot": {
                        "junction_queue_length": 1,
                        "downstream_pressure": 0,
                        "unapproved_future_route": path,
                    },
                }
            )
    f2 = {
        "summary": {
            "event_trace_limit": 0,
            "decision_trace_truncated": False,
        },
        "bags": f2_bags,
        "events": [],
        "decisions": decisions,
        "pibt_events": [
            {
                "trigger_runtime_bag_id": 0,
                "actions": [{"runtime_bag_id": 0}],
            }
        ],
    }
    v2 = {
        "summary": {
            "runtime_full_cie_astar_calls": 0,
            "node_window_conflicts": 0,
        },
        "tasks": [
            {
                "task_id": 0,
                "segment_id": "0:direct",
                "attempt_time": 4.0,
                "finish_time": (
                    4.0
                    + 0.5
                    + 0.2
                    + v2_metrics["0:direct"]["edge_travel_time"]
                    + v2_metrics["0:direct"]["node_service_time"]
                ),
                "goal_reached": True,
                "path": V2_PATHS["0:direct"],
                "source_wait_seconds": 0.5,
                "wait_seconds": 0.7,
            },
            {
                "task_id": 1,
                "segment_id": "1:storage_in",
                "attempt_time": 10.0,
                "finish_time": (
                    10.0
                    + 0.1
                    + v2_metrics["1:storage_in"]["edge_travel_time"]
                    + v2_metrics["1:storage_in"]["node_service_time"]
                ),
                "goal_reached": True,
                "path": V2_PATHS["1:storage_in"],
                "source_wait_seconds": 0.0,
                "wait_seconds": 0.1,
            },
            {
                "task_id": 1,
                "segment_id": "1:storage_out",
                "attempt_time": 20.0,
                "finish_time": (
                    20.0
                    + v2_metrics["1:storage_out"]["edge_travel_time"]
                    + v2_metrics["1:storage_out"]["node_service_time"]
                ),
                "goal_reached": True,
                "path": V2_PATHS["1:storage_out"],
                "source_wait_seconds": 0.0,
                "wait_seconds": 0.0,
            },
        ],
    }
    return f2, v2


def _analysis() -> attribution.AnalysisArtifacts:
    f2, v2 = _payloads()
    return attribution.build_analysis(
        _input_rows(),
        _map(),
        f2,
        v2,
        _v2_source_rows(),
        require_full=False,
        trace_sample_limit=8,
    )


def test_component_ledger_reconstructs_gap_without_double_counting() -> None:
    result = _analysis()
    assert len(result.per_bag_rows) == 2
    storage = next(row for row in result.per_bag_rows if row["task_id"] == 1)
    assert storage["bag_class"] == "storage_in_out"
    assert storage["f2_scheduled_ebs_dwell_seconds"] == pytest.approx(10.0)
    assert storage["v2_scheduled_ebs_dwell_seconds"] == pytest.approx(10.0)
    additive = sum(
        float(row["delta_contribution_seconds_per_bag"])
        for row in result.ledger_rows
        if row["component"] in attribution.ADDITIVE_COMPONENTS
    )
    assert additive == pytest.approx(
        result.summary["mean_gap_seconds_per_bag"], abs=1.0e-9
    )
    assert result.summary["timing_unresolved_seconds_per_bag"] == pytest.approx(
        0.0, abs=1.0e-9
    )
    assert result.summary["timing_reconstruction_coverage"] == pytest.approx(
        1.0
    )
    assert result.summary["status"] == (
        "TIMING_ACCOUNTING_PASS_CAUSAL_ATTRIBUTION_PARTIAL"
    )
    assert result.summary["causal_attribution_status"] == (
        "PARTIAL_NO_MATCHED_INTERVENTION"
    )
    diagnostic = {
        row["component"]: row for row in result.ledger_rows
    }
    assert diagnostic["detour_extra_time"]["additive"] is False
    assert diagnostic["loop_extra_time"]["additive"] is False
    assert diagnostic["goal_completion_time"]["additive"] is False
    responsibility = {
        row["component"]: row
        for row in result.ledger_rows
        if row["ledger_type"] == "responsibility"
    }
    assert set(responsibility) == {
        "source_service_ordering",
        "merge_ordering",
        "route_choice",
        "p2_arbitration",
        "goal_handling",
        "storage_leg_ordering",
        "other",
    }
    assert sum(
        float(row["delta_contribution_seconds_per_bag"])
        for row in responsibility.values()
    ) == pytest.approx(result.summary["mean_gap_seconds_per_bag"])
    assert (
        responsibility["other"]["measurement_status"]
        == "UNRESOLVED_CAUSAL_RESPONSIBILITY"
    )


def test_v2_release_interface_shift_is_signed_and_not_queue_wait() -> None:
    result = _analysis()
    direct = next(row for row in result.per_bag_rows if row["task_id"] == 0)
    # The fixture deliberately models Java epoch rounding one second before
    # protected pass_time.  It must remain an explicit signed interface term,
    # not be hidden in the nonnegative source queue measurement.
    assert direct["f2_release_interface_alignment_seconds"] == 0.0
    assert direct["v2_release_interface_alignment_seconds"] == -1.0
    assert direct["v2_source_queue_wait_seconds"] == pytest.approx(0.5)
    assert direct["v2_total_seconds"] == pytest.approx(
        direct["v2_scheduled_ebs_dwell_seconds"]
        + direct["v2_time_bank_json"]["algorithm_sensitive"]
    )


def test_v2_timestamp_time_bank_retains_filtered_boundary_epsilon() -> None:
    f2, v2 = _payloads()
    v2["tasks"][0]["finish_time"] += 1.0e-6
    result = attribution.build_analysis(
        _input_rows(),
        _map(),
        f2,
        v2,
        _v2_source_rows(),
        require_full=False,
    )
    direct = next(row for row in result.per_bag_rows if row["task_id"] == 0)
    assert direct["v2_resource_calendar_wait_seconds"] == pytest.approx(
        0.200001
    )
    gate = next(
        row
        for row in result.validation_rows
        if row["gate"] == "v2_reported_wait_epsilon_crosscheck"
    )
    assert gate["status"] == "PASS"
    assert float(gate["actual"]) == pytest.approx(1.0e-6)


def test_real_map_fixture_covers_ebs_split_merge_and_bridge() -> None:
    map_data = _map()
    nodes = {
        int(node["location"]): node for node in map_data["nodes"]
    }
    edges = {
        (int(edge["start"]), int(edge["end"]))
        for edge in map_data["edges"]
    }
    indegree: dict[int, int] = {}
    undirected_degree: dict[int, int] = {}
    for start, end in edges:
        indegree[end] = indegree.get(end, 0) + 1
        undirected_degree[start] = undirected_degree.get(start, 0) + 1
        undirected_degree[end] = undirected_degree.get(end, 0) + 1
    assert int(nodes[52]["node_type"]) == 1  # real EBS/source node
    assert len(nodes[52]["outgoing"]) == 2  # real split
    assert indegree[30] == 2  # real merge used by both comparator paths
    assert (37, 49) in edges and undirected_degree[49] == 1  # bridge to goal
    for path in [*F2_PATHS.values(), *V2_PATHS.values()]:
        assert all(edge in edges for edge in zip(path, path[1:]))


def test_f2_and_v2_use_distinct_real_map_service_semantics() -> None:
    result = _analysis()
    direct = next(row for row in result.per_bag_rows if row["task_id"] == 0)
    f2_path = F2_PATHS["0:direct"]
    raw_f2_service = _real_path_metrics(
        f2_path, minimum_service_seconds=0.0
    )["node_service_time"]
    # Source 52 and goal 49 have zero raw service; F2 applies 1 ms at each.
    assert direct["f2_node_service_time_seconds"] - raw_f2_service == (
        pytest.approx(0.002)
    )
    assert direct["v2_node_service_time_seconds"] == pytest.approx(
        _real_path_metrics(
            V2_PATHS["0:direct"], minimum_service_seconds=0.0
        )["node_service_time"]
    )


def test_divergence_keeps_v2_action_offline_and_features_local_only() -> None:
    result = _analysis()
    assert len(result.divergence_rows) == 1
    row = result.divergence_rows[0]
    assert row["first_divergence_node"] == 52
    assert row["f2_next_node"] == 40
    assert row["v2_next_node_offline_only"] == 29
    assert row["v2_next_locally_feasible"] is True
    features = json.loads(row["runtime_features_json"])
    labels = json.loads(row["offline_labels_json"])
    assert "v2_next_node" not in features
    assert labels["v2_next_node"] == 29
    assert "unapproved_future_route" not in features["local_snapshot"]
    attribution._assert_no_teacher_leakage(features)
    assert result.trace_rows[0]["decision_scope"] == (
        "bounded_offline_current_action_only"
    )
    assert row["counterfactual_scope"] == (
        "OBSERVED_CURRENT_ACTION_COMPARISON_ONLY"
    )
    assert row["counterfactual_replay_status"] == (
        "NOT_RUN_NO_MATCHED_RUNTIME_STATE_CLONE"
    )


def test_missing_or_duplicate_segments_fail_closed() -> None:
    f2, v2 = _payloads()
    missing = deepcopy(v2)
    missing["tasks"] = missing["tasks"][:-1]
    with pytest.raises(attribution.AttributionError, match="alignment failed"):
        attribution.build_analysis(
            _input_rows(),
            _map(),
            f2,
            missing,
            _v2_source_rows(),
        )

    duplicated = deepcopy(f2)
    duplicated["bags"].append(deepcopy(duplicated["bags"][0]))
    with pytest.raises(attribution.AttributionError, match="duplicate"):
        attribution.build_analysis(
            _input_rows(),
            _map(),
            duplicated,
            v2,
            _v2_source_rows(),
        )


def test_seven_field_alignment_rejects_start_and_original_entry_drift() -> None:
    f2, v2 = _payloads()
    bad_f2 = deepcopy(f2)
    bad_f2["bags"][0]["start"] = 3
    with pytest.raises(attribution.AttributionError, match="start identity mismatch"):
        attribution.build_analysis(
            _input_rows(),
            _map(),
            bad_f2,
            v2,
            _v2_source_rows(),
        )
    bad_source = _v2_source_rows()
    bad_source[0]["original_entry_time"] = 1.0
    with pytest.raises(attribution.AttributionError, match="identity mismatch"):
        attribution.build_analysis(
            _input_rows(),
            _map(),
            f2,
            v2,
            bad_source,
        )


def test_missing_cpp_instrumentation_fails_with_compatible_field_contract() -> None:
    f2, v2 = _payloads()
    del f2["bags"][0]["junction_queue_wait_seconds"]
    with pytest.raises(
        attribution.AttributionError,
        match="MISSING_F2_INSTRUMENTATION:junction_queue_wait",
    ):
        attribution.build_analysis(
            _input_rows(),
            _map(),
            f2,
            v2,
            _v2_source_rows(),
        )


def test_component_mismatch_fails_before_artifact_render() -> None:
    f2, v2 = _payloads()
    f2["bags"][0]["goal_completion_time_seconds"] = 99.0
    with pytest.raises(attribution.AttributionError, match="does not reconstruct"):
        attribution.build_analysis(
            _input_rows(),
            _map(),
            f2,
            v2,
            _v2_source_rows(),
        )


def test_atomic_gzip_descriptor_cache_resumes_and_detects_tampering(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / ".local_archives"
    calls = 0

    def producer() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"summary": {"ok": True}, "bags": [{"segment_id": "x"}]}

    identity = {"config": "synthetic", "sha256": "a" * 64}
    first = attribution.collect_cached(
        case_id="fixture",
        identity=identity,
        producer=producer,
        validator=lambda payload: {
            "bag_count": len(payload["bags"]),
            "validated": True,
        },
        archive_root=archive_root,
    )
    assert first["status"] == "COLLECTED"
    second = attribution.collect_cached(
        case_id="fixture",
        identity=identity,
        producer=producer,
        validator=lambda _payload: {"validated": True},
        archive_root=archive_root,
    )
    assert second["status"] == "REUSED"
    assert calls == 1

    descriptor_path = Path(first["descriptor_path"])
    bundle = attribution.load_archive(
        descriptor_path,
        archive_root=archive_root,
        expected_case_id="fixture",
    )
    assert bundle.payload["runtime_payload"]["summary"]["ok"] is True
    assert not list(descriptor_path.parent.glob("*.tmp"))

    archive_path = archive_root / bundle.descriptor["archive"]["relative_path"]
    archive_path.write_bytes(archive_path.read_bytes() + b"tamper")
    with pytest.raises(attribution.ArchiveError, match="SHA-256"):
        attribution.load_archive(
            descriptor_path,
            archive_root=archive_root,
            expected_case_id="fixture",
        )


def test_stale_lock_requires_explicit_recovery(tmp_path: Path) -> None:
    archive_root = tmp_path / ".local_archives"
    lock = archive_root / "locks" / "stale_case.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps(
            {
                "case_id": "stale_case",
                "pid": 2_000_000_000,
                "hostname": attribution.socket.gethostname(),
                "nonce": "dead",
            }
        ),
        encoding="utf-8",
    )
    kwargs = {
        "case_id": "stale_case",
        "identity": {"x": 1},
        "producer": lambda: {"value": 1},
        "validator": lambda _payload: {"validated": True},
        "archive_root": archive_root,
    }
    with pytest.raises(attribution.StaleWorkerError):
        attribution.collect_cached(**kwargs)
    result = attribution.collect_cached(**kwargs, recover_stale=True)
    assert result["status"] == "COLLECTED"
    assert list((lock.parent / "stale_locks").glob("*.json"))


def test_outputs_include_fifth_observed_validation_table() -> None:
    result = _analysis()
    payloads = attribution.build_output_payloads(result)
    assert set(payloads) == {
        attribution.PER_BAG_PATH,
        attribution.LEDGER_PATH,
        attribution.DIVERGENCE_PATH,
        attribution.HOTSPOT_PATH,
        attribution.VALIDATION_PATH,
        attribution.TRACE_SAMPLE_PATH,
        attribution.REPORT_PATH,
    }
    validation = payloads[attribution.VALIDATION_PATH].decode("utf-8")
    assert "f2_segment_component_reconstruction" in validation
    assert "bounded_responsibility_localization_coverage" in validation
    report = payloads[attribution.REPORT_PATH].decode("utf-8")
    assert "auditable supplement" in report


def test_real_protected_input_hashes_and_counts_are_frozen() -> None:
    _map_data, rows = attribution.load_protected_inputs(ROOT)
    assert len(rows) == attribution.FULL_SEGMENTS
    assert len({int(row["task_id"]) for row in rows}) == attribution.FULL_BAGS
