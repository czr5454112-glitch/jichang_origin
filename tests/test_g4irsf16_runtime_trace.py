from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf16_runtime_trace as trace


def _candidate(next_node: int = 11) -> dict[str, object]:
    return {
        "next_node": next_node,
        "features": {
            "target_queue_length": 3,
            "target_scheduled_incoming": 2,
            "corridor_next_available": 102.0,
            "target_next_available": 106.0,
            "travel_time": 4.0,
            "static_potential": 12.5,
            "advertised_fault": False,
            # These source fields must not pass the feature allowlist.
            "two_hop_queue_pressure": 99,
            "global_task_count": 43_603,
            "signed_label": "HARMFUL",
        },
        "model_score": -0.7,
        "scorer_raw_score": 0.7,
        "scorer_raw_bottleneck": 1.25,
        "shield_allowed": True,
        "shield_reason": "allowed",
        "delta_completion_seconds": -10.0,
    }


def _trace_row(
    *,
    event_seq: int = 55,
    runtime_bag_id: int = 1,
    decision_ordinal: int = 9,
    task_id: int = 1,
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "event_time": 100.0,
        "current_node": 7,
        "goal_node": 47,
        "candidate_records": [_candidate()],
        "model_prediction": 11,
        "selected_next": 11,
        "model_margin": 2.5,
        "risk_gate_triggered": False,
        "local_snapshot": {
            "junction_queue_length": 4,
            "next_available_time": 101.0,
            "downstream_pressure": 999,
            "global_queue_length": 43_603,
        },
        "short_history": [3, 5, 7],
        "full_astar_used": False,
        "metadata": {
            "arrive_event_seq": event_seq,
            "runtime_bag_id": runtime_bag_id,
            "decision_ordinal": decision_ordinal,
            "trace_kind": "committed_edge_action",
            "scorer_raw_margin": 1.75,
            "scorer_risk_abstain": False,
            "coverage_tags": ["top_tail"],
            "offline_sampling_metadata": {"must_not_enter": True},
        },
    }


def _hard_gate_summary(segments: int) -> dict[str, object]:
    summary: dict[str, object] = {
        field: 0 for field in trace.RAW_HARD_GATE_FIELDS
    }
    summary.update(
        requested_count=segments,
        completed_count=segments,
        failed_count=0,
        bag_future_path_field_present=False,
        event_limit_reached=False,
        time_limit_reached=False,
        merge_grant_conservation_holds=True,
        merge_grant_active_bijection_holds=True,
        merge_grant_runtime_owned_capability=True,
        merge_grant_exact_slot_no_future_shift=True,
        merge_grant_lifecycle_complete=False,
        merge_grant_protocol_integrity_pass=False,
        artificial_batch_delay_seconds=0.0,
        max_edges_selected_per_bag_per_decision=1,
    )
    for field in (
        "global_reservation_scan_count",
        "priority_global_scan_count",
        "scorer_runtime_global_scan_count",
        "microphase_runtime_global_scan_count",
        "first_edge_credit_global_scan_count",
        "priority_future_route_input_count",
        "scorer_future_route_input_count",
        "first_edge_credit_future_route_count",
        "scorer_future_schedule_input_count",
        "priority_teacher_input_count",
        "scorer_teacher_input_count",
    ):
        summary[field] = 0
    return summary


def test_formal_target_frame_reduces_to_2172_outcome_free_identities() -> None:
    pytest.importorskip("zstandard")
    frame = trace.load_formal_target_frame()

    assert len(frame.targets) == 2_172
    assert Counter(target.kind for target in frame.targets) == {
        "I3": 1_086,
        "I4": 1_086,
    }
    assert len({target.target_key for target in frame.targets}) == 2_172
    # Three H_system/H_bag records intentionally share a live runtime address.
    assert len({target.live_key for target in frame.targets}) == 2_169
    assert set(frame.targets[0].__dataclass_fields__) == {
        "target_index",
        "target_key",
        "descriptor_id",
        "kind",
        "horizon",
        "event_ordinal",
        "event_seq",
        "runtime_bag_id",
    }


def test_deployable_projection_is_strict_local_allowlist() -> None:
    target = trace.FormalTarget(
        target_index=0,
        target_key="target:H_bag",
        descriptor_id="target",
        kind="I3",
        horizon="H_bag",
        event_ordinal=44,
        event_seq=55,
        runtime_bag_id=1,
    )
    row = trace.extract_deployable_feature_row(_trace_row(), target)

    assert set(row) == {
        "schema",
        "target",
        "runtime_match",
        "action_context",
        "features",
    }
    assert set(row["features"]) == {
        "current_local_queue_length",
        "current_next_available_time",
        "current_calendar_wait_seconds",
        "short_history",
        "f2",
        "candidates",
    }
    candidate = row["features"]["candidates"][0]
    assert candidate["action_next_node"] == 11
    assert set(candidate["features"]) == {
        "target_queue_length",
        "target_scheduled_incoming",
        "corridor_next_available",
        "target_next_available",
        "corridor_wait_seconds",
        "target_calendar_delay_seconds",
        "travel_time",
        "static_potential",
        "model_score",
        "scorer_raw_score",
        "scorer_raw_bottleneck",
        "advertised_fault",
        "shield_allowed",
        "shield_reason",
    }
    encoded_features = json.dumps(row["features"], sort_keys=True)
    for forbidden in (
        "signed_label",
        "delta_completion",
        "global_task_count",
        "global_queue_length",
        "coverage_tags",
        "offline_sampling_metadata",
        "two_hop_queue_pressure",
    ):
        assert forbidden not in encoded_features


def test_shadow_scoring_seam_returns_proposals_only() -> None:
    target = trace.FormalTarget(0, "t:H_bag", "t", "I4", "H_bag", 4, 5, 1)
    row = trace.extract_deployable_feature_row(
        _trace_row(event_seq=5), target
    )
    original = json.dumps(row, sort_keys=True)

    observed_inputs: list[dict[str, object]] = []

    def scorer(observed: dict[str, object]) -> dict[str, object]:
        observed_inputs.append(observed)
        return {"action": "HOLD", "confidence": 0.99}

    proposals = trace.score_shadow_features([row], scorer)

    assert proposals == [
        {
            "target_key": "t:H_bag",
            "proposal": {"action": "HOLD", "confidence": 0.99},
        }
    ]
    assert set(observed_inputs[0]) == {"action_context", "features"}
    encoded_input = json.dumps(observed_inputs[0], sort_keys=True)
    assert "target_key" not in encoded_input
    assert "event_ordinal" not in encoded_input
    assert "runtime_bag_id" not in encoded_input
    assert json.dumps(row, sort_keys=True) == original


def test_runtime_request_is_unlimited_exact_e4_f2_off() -> None:
    request = trace.build_runtime_request(
        node_records=[],
        edge_records=[],
        heuristic_time=[],
        bag_records=[],
        binary=Path("native.pyd"),
        search_path=Path("."),
        model_path=Path("model.json"),
        segments=144,
        trace_shards=4,
        shard_index=2,
    )

    assert request["event_semantics"] == "E4_batch_plus_destination_merge_request"
    assert request["merge_grant_rule"] == "M0"
    assert request["resource_semantics"] == "R3_java_node_window_compatible"
    assert request["scorer_mode"] == "S1_frozen_g4e_legal_local_adapter"
    assert request["pibt_mode"] == "P2"
    assert request["admission_mode"] == "off"
    assert request["priority_mode"] == "Q0"
    assert request["summary_only"] is False
    assert request["trace_limit"] == -1
    assert request["trace_shard_count"] == 4
    assert request["trace_shard_index"] == 2
    assert request["event_trace_limit"] == 0
    assert request["enable_opportunity_telemetry"] is False


def test_hard_gate_projection_accepts_safe_small_f2_run() -> None:
    projection = trace._hard_gate_projection(  # noqa: SLF001
        _hard_gate_summary(144), expected_segments=144
    )
    assert projection["all_live_hard_gates_pass"] is True
    assert projection["runtime_global_scan_count"] == 0
    assert projection["runtime_future_route_read_count"] == 0


def test_trace_validation_requires_complete_modulo_shard() -> None:
    payload = {
        "decisions": [_trace_row(runtime_bag_id=8, task_id=1)],
        "hold_attempts": [],
        "events": [],
    }
    summary = {
        "decision_trace_truncated": False,
        "decision_trace_stored_count": 1,
        "hold_trace_stored_count": 0,
        "decision_trace_shard_seen_count": 1,
    }
    rows, ordinals = trace._trace_rows(  # noqa: SLF001
        payload, summary, trace_shards=2, shard_index=1
    )
    assert len(rows) == 1
    assert ordinals == {9}

    with pytest.raises(trace.RuntimeTraceError, match="shard partition"):
        trace._trace_rows(  # noqa: SLF001
            payload, summary, trace_shards=2, shard_index=0
        )


def test_formal_capture_is_rejected_below_full_scale() -> None:
    with pytest.raises(trace.RuntimeTraceError, match="formal 2172-row capture"):
        trace.run_runtime_trace(
            binary=Path("does-not-need-to-exist.pyd"),
            segments=144,
            trace_shards=1,
            allow_full=False,
            capture_matched_features=True,
        )


def test_evidence_paths_are_repo_relative_or_explicitly_external(
    tmp_path: Path,
) -> None:
    repo_artifact = trace.ROOT / "outputs/runtime/g4irsf16/example.json"
    external_binary = tmp_path / "czr005_cpp.pyd"

    assert trace._portable_path(repo_artifact) == (  # noqa: SLF001
        "outputs/runtime/g4irsf16/example.json"
    )
    assert trace._portable_path(external_binary) == (  # noqa: SLF001
        "EXTERNAL_NATIVE_BINARY/czr005_cpp.pyd"
    )
