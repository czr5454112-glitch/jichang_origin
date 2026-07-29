from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import g4irsf14_opportunity_census as census


def _binary_identity(path: Path) -> tuple[str, str]:
    resolved = path.resolve()
    return str(resolved), hashlib.sha256(resolved.read_bytes()).hexdigest()


def _base_summary(
    *,
    binary: Path,
    opportunity_enabled: bool,
    i2_exact_boundaries: int = 0,
    i2_losers: int = 0,
    i5_exact_prefilter: int = 1_337,
    i5_exact_applicable: int = 0,
    i5_triggers: int = 1_337,
    i5_activations: int = 0,
) -> dict[str, Any]:
    binary_path, binary_sha = _binary_identity(binary)
    summary: dict[str, Any] = {
        "requested_count": census.FULL_SEGMENT_COUNT,
        "completed_count": census.FULL_SEGMENT_COUNT,
        "failed_count": 0,
        "event_count": 5_445_012,
        "end_time": 23_884.402,
        "physical_fault_edge_entry_violation_count": 0,
        "reservation_conflicts": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "priority_global_scan_count": 0,
        "scorer_runtime_global_scan_count": 0,
        "microphase_runtime_global_scan_count": 0,
        "first_edge_credit_global_scan_count": 0,
        "priority_future_route_input_count": 0,
        "scorer_future_route_input_count": 0,
        "first_edge_credit_future_route_count": 0,
        "scorer_future_schedule_input_count": 0,
        "priority_teacher_input_count": 0,
        "scorer_teacher_input_count": 0,
        "full_future_routes_stored": 0,
        "bag_future_path_field_present": False,
        "max_edges_selected_per_bag_per_decision": 1,
        "two_step_reservation_count": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "merge_grant_stale_arbitration_count": 0,
        "stale_arbitration_event_count": 0,
        "artificial_batch_delay_seconds": 0.0,
        "merge_grant_conservation_holds": True,
        "merge_grant_active_bijection_holds": True,
        "merge_grant_runtime_owned_capability": True,
        "merge_grant_exact_slot_no_future_shift": True,
        "merge_grant_final_active_unconsumed": 0,
        "merge_grant_outstanding_request_count": 0,
        "merge_grant_lifecycle_dropped_count": 11,
        "merge_grant_lifecycle_complete": False,
        "merge_grant_protocol_integrity_pass": False,
        "resource_semantics_id": "R3_java_node_window_compatible",
        "resource_semantics_echo": "R3_java_node_window_compatible",
        "scorer_mode": "S1_frozen_g4e_legal_local_adapter",
        "scorer_mode_echo": "S1_frozen_g4e_legal_local_adapter",
        "scorer_model_sha256": census.MODEL_SHA256,
        "pibt_mode": "P2",
        "pibt_mode_echo": "P2",
        "pibt_max_depth": 2,
        "pibt_max_ready_bags": 8,
        "pibt_max_local_resources": 32,
        "pibt_max_candidates_per_bag": 8,
        "pibt_mode_diagnostic_only": False,
        "framework_mode": "event_loop_one_step",
        "framework_mode_echo": "event_loop_one_step",
        "framework_diagnostic_only": False,
        "pressure_mode": "C0_off",
        "pressure_mode_echo": "off",
        "pressure_weight": 2.0,
        "pressure_age_weight": 0.05,
        "pressure_distance_bias": 0.25,
        "admission_mode": "off",
        "admission_mode_echo": "off",
        "source_admission_enabled": False,
        "fault_policy_enabled": True,
        "legacy_pibt_lite_enabled": False,
        "credit_mode": "C0",
        "credit_validity_seconds": 1.0,
        "credit_snapshot_max_age_seconds": 1.0,
        "credit_capacity_per_edge": 1,
        "credit_lifecycle_limit": 512,
        "selective_credit_contention_threshold": 1,
        "priority_mode": "Q0",
        "priority_mode_echo": "Q0",
        "pibt_preference_mode": "current",
        "pibt_preference_mode_echo": "current",
        "pibt_regret_prior_record_count": 0,
        "event_semantics": "E4_batch_plus_destination_merge_request",
        "event_semantics_echo": "E4_batch_plus_destination_merge_request",
        "merge_grant_rule": "M0",
        "merge_grant_rule_echo": "M0",
        "merge_grant_max_pending_requests": 256,
        "merge_grant_lifecycle_limit": 8192,
        "local_queue_capacity": 32,
        "diagnostic_hops": 2,
        "trace_limit": (
            0 if opportunity_enabled else census.DECISION_TRACE_LIMIT
        ),
        "event_trace_limit": 0,
        "event_trace_limit_inherited": False,
        "trace_shard_count": 1,
        "trace_shard_index": 0,
        "entry_headway_seconds": 0.001,
        "declared_max_events": 20_000_000,
        "declared_max_simulation_time": -1.0,
        "opportunity_telemetry_enabled": opportunity_enabled,
        "decision_trace_seen_count": 4,
        "decision_trace_stored_count": 0 if opportunity_enabled else 2,
        "hold_trace_stored_count": 0 if opportunity_enabled else 1,
        "source_opportunity_total_count": 3 if opportunity_enabled else 0,
        "source_opportunity_stored_count": 3 if opportunity_enabled else 0,
        "source_opportunity_dropped_count": 0,
        "g4irsf14_i2_live_eligible_multi_request_boundary_count": (
            i2_exact_boundaries
        ),
        "g4irsf14_i5_prefilter_candidate_count": i5_exact_prefilter,
        "g4irsf14_i5_applicable_ready_slice_boundary_count": (
            i5_exact_applicable
        ),
        "merge_grant_request_count": 335_770,
        "destination_merge_arbitration_event_count": 335_770,
        "merge_grant_peak_pending_requests": 2,
        "merge_grant_contended_loser_retry_count": i2_losers,
        "merge_grant_request_expired_count": 7,
        "merge_grant_grant_expired_count": 0,
        "merge_grant_active_grant_rejection_count": 5,
        "merge_grant_exact_slot_busy_count": 3,
        "merge_grant_queue_capacity_block_count": i5_triggers,
        "merge_grant_duplicate_wakeup_prevented_count": 9,
        "merge_grant_terminal_request_count": 10,
        "bounded_local_pibt_activation_count": i5_activations,
        "bounded_local_pibt_not_applicable_count": (
            i5_triggers - i5_activations
        ),
        "bounded_local_pibt_attempt_count": i5_activations,
        "bounded_local_pibt_prepare_count": 0,
        "bounded_local_pibt_validate_count": 0,
        "bounded_local_pibt_commit_count": 0,
        "bounded_local_pibt_proposal_batch_count": 0,
        "bounded_local_pibt_proposed_action_count": 0,
        "bounded_local_pibt_committed_batch_count": 0,
        "bounded_local_pibt_committed_action_count": 0,
        "bounded_local_pibt_inherited_action_count": 0,
        "bounded_local_pibt_blocker_move_attempt_count": 0,
        "bounded_local_pibt_backtrack_count": 0,
        "bounded_local_pibt_cycle_guard_count": 0,
        "bounded_local_pibt_rollback_count": 0,
        "bounded_local_pibt_max_inheritance_depth": 0,
        "bounded_local_pibt_max_slice_bags": (
            0 if i5_activations == 0 else 2
        ),
        "bounded_local_pibt_max_slice_resources": (
            0 if i5_activations == 0 else 2
        ),
        "bounded_local_pibt_max_candidates_per_bag": (
            0 if i5_activations == 0 else 2
        ),
        "loaded_cpp_binary_path": binary_path,
        "loaded_cpp_binary_sha256": binary_sha,
    }
    return summary


def _trace_context(
    *, opportunity_enabled: bool
) -> dict[str, Any]:
    return {
        "resource_semantics_id": "R3_java_node_window_compatible",
        "resource_semantics_echo": "R3_java_node_window_compatible",
        "scorer_mode_echo": "S1_frozen_g4e_legal_local_adapter",
        "scorer_model_sha256": census.MODEL_SHA256,
        "pibt_mode": "P2",
        "pibt_mode_echo": "P2",
        "pibt_max_depth": 2,
        "pibt_max_ready_bags": 8,
        "pibt_max_local_resources": 32,
        "pibt_max_candidates_per_bag": 8,
        "pibt_mode_diagnostic_only": False,
        "framework_mode": "event_loop_one_step",
        "framework_mode_echo": "event_loop_one_step",
        "framework_diagnostic_only": False,
        "pressure_mode_echo": "off",
        "admission_mode": "off",
        "admission_mode_echo": "off",
        "enable_source_admission": False,
        "enable_fault_policy": True,
        "credit_mode": "C0",
        "credit_validity_seconds": 1.0,
        "credit_snapshot_max_age_seconds": 1.0,
        "credit_capacity_per_edge": 1,
        "credit_lifecycle_limit": 512,
        "selective_credit_contention_threshold": 1,
        "priority_mode": "Q0",
        "priority_mode_echo": "Q0",
        "pibt_preference_mode": "current",
        "pibt_preference_mode_echo": "current",
        "pibt_regret_prior_record_count": 0,
        "event_semantics": "E4_batch_plus_destination_merge_request",
        "event_semantics_echo": "E4_batch_plus_destination_merge_request",
        "merge_grant_rule": "M0",
        "merge_grant_rule_echo": "M0",
        "merge_grant_max_pending_requests": 256,
        "merge_grant_lifecycle_limit": 8192,
        "local_queue_capacity": 32,
        "opportunity_telemetry_enabled": opportunity_enabled,
        "opportunity_trace_limit": (
            census.OPPORTUNITY_TRACE_LIMIT
            if opportunity_enabled
            else 0
        ),
        "diagnostic_hops": 2,
        "trace_limit": (
            0 if opportunity_enabled else census.DECISION_TRACE_LIMIT
        ),
        "event_trace_limit": 0,
        "event_trace_limit_inherited": False,
        "trace_shard_count": 1,
        "trace_shard_index": 0,
        "entry_headway_seconds": 0.001,
        "declared_max_events": 20_000_000,
        "scale": 1.0,
        "reservation_depth": 1,
        "destination_merge_grant_enabled": True,
    }


def _bags(bag_records: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [
        {
            "segment_id": str(record[0]),
            "runtime_bag_id": index,
            "completed": True,
            "failure_reason": "",
        }
        for index, record in enumerate(bag_records)
    ]


def _source_rows() -> list[dict[str, Any]]:
    return [
        {
            "timestamp_bits": 1,
            "source_node": 0,
            "event_seq": 1,
            "arbitration_generation": 1,
            "ready_set_size": 1,
            "chosen_runtime_bag_id": 10,
        },
        {
            "timestamp_bits": 2,
            "source_node": 1,
            "event_seq": 2,
            "arbitration_generation": 1,
            "ready_set_size": 2,
            "chosen_runtime_bag_id": 11,
        },
        {
            "timestamp_bits": 3,
            "source_node": 1,
            "event_seq": 3,
            "arbitration_generation": 2,
            "ready_set_size": 3,
            "chosen_runtime_bag_id": 12,
        },
    ]


def _decision_rows() -> list[dict[str, Any]]:
    return [
        {
            "event_time": 1.0,
            "current_node": 6,
            "selected_next": 8,
            "metadata": {
                "arrive_event_seq": 101,
                "runtime_bag_id": 11,
            },
            "candidate_records": [
                {"next_node": 8, "shield_allowed": True},
                {"next_node": 12, "shield_allowed": True},
            ],
        },
        {
            "event_time": 2.0,
            "current_node": 8,
            "selected_next": 11,
            "metadata": {
                "arrive_event_seq": 102,
                "runtime_bag_id": 12,
            },
            "candidate_records": [
                {"next_node": 11, "shield_allowed": True},
            ],
        },
    ]


def _event_payload(
    kwargs: dict[str, Any],
    *,
    i2_exact_boundaries: int,
    i2_losers: int,
    i5_exact_prefilter: int,
    i5_exact_applicable: int,
    i5_triggers: int,
    i5_activations: int,
) -> dict[str, Any]:
    opportunity_enabled = bool(kwargs["enable_opportunity_telemetry"])
    binary = Path(kwargs["expected_binary_path"])
    binary_path, binary_sha = _binary_identity(binary)
    decisions = [] if opportunity_enabled else _decision_rows()
    holds = (
        []
        if opportunity_enabled
        else [
            {
                "event_time": 3.0,
                "current_node": 9,
                "selected_next": None,
                "metadata": {
                    "arrive_event_seq": 103,
                    "runtime_bag_id": 13,
                },
                "candidate_records": [],
            }
        ]
    )
    return {
        "summary": _base_summary(
            binary=binary,
            opportunity_enabled=opportunity_enabled,
            i2_exact_boundaries=i2_exact_boundaries,
            i2_losers=i2_losers,
            i5_exact_prefilter=i5_exact_prefilter,
            i5_exact_applicable=i5_exact_applicable,
            i5_triggers=i5_triggers,
            i5_activations=i5_activations,
        ),
        "trace_context": _trace_context(
            opportunity_enabled=opportunity_enabled
        ),
        "loaded_cpp_binary_path": binary_path,
        "loaded_cpp_binary_sha256": binary_sha,
        "bags": _bags(list(kwargs["bag_records"])),
        "junction_state": [{"node": 0, "final_queue_length": 0}],
        "source_admission_opportunities": (
            _source_rows() if opportunity_enabled else []
        ),
        "decisions": decisions,
        "decision_trace": copy.deepcopy(decisions),
        "hold_attempts": holds,
    }


def _clone_invariants(
    *,
    i2_exact_boundaries: int,
    i5_exact_prefilter: int,
    i5_exact_applicable: int,
) -> dict[str, Any]:
    return {
        "requested_count": census.FULL_SEGMENT_COUNT,
        "completed_count": census.FULL_SEGMENT_COUNT,
        "failed_segment_count": 0,
        "event_count": 5_445_012,
        "g4irsf14_i2_live_eligible_multi_request_boundary_count": (
            i2_exact_boundaries
        ),
        "g4irsf14_i5_prefilter_candidate_count": i5_exact_prefilter,
        "g4irsf14_i5_applicable_ready_slice_boundary_count": (
            i5_exact_applicable
        ),
        "unsafe_entry_count": 0,
        "reservation_conflict_count": 0,
        "runtime_full_astar_call_count": 0,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "teacher_input_count": 0,
        "full_future_routes_stored": 0,
        "bag_future_path_field_present": False,
        "reservation_depth": 1,
        "max_selected_edges_per_bag": 1,
        "two_step_reservation_count": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "merge_grant_conservation_holds": True,
        "merge_grant_active_bijection_holds": True,
        "merge_grant_final_active_unconsumed": 0,
        "merge_grant_outstanding_request_count": 0,
        "merge_grant_stale_arbitration_count": 0,
        "merge_grant_lifecycle_dropped_count": 11,
        "merge_grant_lifecycle_complete": False,
        "merge_grant_runtime_owned_capability": True,
        "merge_grant_exact_slot_no_future_shift": True,
        "merge_grant_active_state_integrity_pass": True,
        "merge_grant_protocol_integrity_pass": False,
        "stale_arbitration_event_count": 0,
        "artificial_batch_delay_seconds": 0.0,
    }


def _clone_payload(
    kwargs: dict[str, Any],
    *,
    i2_exact_boundaries: int,
    i5_exact_prefilter: int,
    i5_exact_applicable: int,
) -> dict[str, Any]:
    hashes = {
        field: hashlib.sha256(field.encode("ascii")).hexdigest()
        for field in census.REPLAY_HASH_FIELDS
    }
    invariants = _clone_invariants(
        i2_exact_boundaries=i2_exact_boundaries,
        i5_exact_prefilter=i5_exact_prefilter,
        i5_exact_applicable=i5_exact_applicable,
    )
    binary = Path(kwargs["expected_binary_path"]).resolve()
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    return {
        "schema": "czr005.g4irsf14.exact_binary_noop_rerun.v1",
        "evidence_scope": (
            "NOOP_FIDELITY_MECHANISM_ONLY_NOT_A_CAUSAL_LABEL"
        ),
        "formal_pass_claimed": False,
        "intervention_applied": False,
        "input_request_count": census.FULL_SEGMENT_COUNT,
        "loaded_cpp_binary_path": str(binary),
        "loaded_cpp_binary_sha256": binary_sha,
        "binary": {"path": str(binary), "sha256": binary_sha},
        "frozen_controls": dict(census.CLONE_FROZEN_CONTROLS),
        "boundary": {
            "kind": "queue_top_pre_pop",
            "queue_top_not_popped": True,
            "staged_event_sink_empty": True,
            "processed_event_count": kwargs[
                "preregistered_event_ordinal"
            ],
            "runtime_state_sha256": "a" * 64,
        },
        "source_replay_hashes": hashes,
        "baseline_replay_hashes": copy.deepcopy(hashes),
        "clone_replay_hashes": copy.deepcopy(hashes),
        "source_invariants": invariants,
        "baseline_invariants": copy.deepcopy(invariants),
        "clone_invariants": copy.deepcopy(invariants),
        "native_three_way_exact_match": True,
    }


def _executors(
    *,
    i2_exact_boundaries: int = 0,
    i2_losers: int = 0,
    i5_exact_prefilter: int = 1_337,
    i5_exact_applicable: int = 0,
    i5_triggers: int = 1_337,
    i5_activations: int = 0,
    event_side_effect: Any = None,
    clone_side_effect: Any = None,
) -> tuple[Any, Any, list[dict[str, Any]]]:
    requests: list[dict[str, Any]] = []

    def event_executor(**kwargs: Any) -> dict[str, Any]:
        requests.append(dict(kwargs))
        if event_side_effect is not None:
            event_side_effect(kwargs)
        return _event_payload(
            kwargs,
            i2_exact_boundaries=i2_exact_boundaries,
            i2_losers=i2_losers,
            i5_exact_prefilter=i5_exact_prefilter,
            i5_exact_applicable=i5_exact_applicable,
            i5_triggers=i5_triggers,
            i5_activations=i5_activations,
        )

    def clone_executor(**kwargs: Any) -> dict[str, Any]:
        requests.append(dict(kwargs))
        if clone_side_effect is not None:
            clone_side_effect(kwargs)
        return _clone_payload(
            kwargs,
            i2_exact_boundaries=i2_exact_boundaries,
            i5_exact_prefilter=i5_exact_prefilter,
            i5_exact_applicable=i5_exact_applicable,
        )

    return event_executor, clone_executor, requests


def _run(
    tmp_path: Path,
    *,
    i2_exact_boundaries: int = 0,
    i2_losers: int = 0,
    i5_exact_prefilter: int = 1_337,
    i5_exact_applicable: int = 0,
    i5_triggers: int = 1_337,
    i5_activations: int = 0,
    event_side_effect: Any = None,
    clone_side_effect: Any = None,
    write: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], Path, Path, Path]:
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"exact-test-native-binary")
    source = tmp_path / "census_source.py"
    source.write_text("SOURCE_VERSION = 1\n", encoding="utf-8")
    output = tmp_path / census.OUTPUT_PATH
    event_executor, clone_executor, requests = _executors(
        i2_exact_boundaries=i2_exact_boundaries,
        i2_losers=i2_losers,
        i5_exact_prefilter=i5_exact_prefilter,
        i5_exact_applicable=i5_exact_applicable,
        i5_triggers=i5_triggers,
        i5_activations=i5_activations,
        event_side_effect=event_side_effect,
        clone_side_effect=clone_side_effect,
    )
    document = census.generate_opportunity_census(
        binary=binary,
        search_path=tmp_path,
        output_path=output,
        bundle_root=tmp_path,
        event_executor=event_executor,
        clone_executor=clone_executor,
        source_paths=(source,),
        write=write,
    )
    return document, requests, binary, source, output


def test_generates_fail_closed_original_1x_blocker_with_exact_binary(
    tmp_path: Path,
) -> None:
    document, requests, binary, _, output = _run(tmp_path)

    assert not output.exists()
    relative_payloads = census.build_blocker_bundle_payloads(document)
    disk_payloads = {
        tmp_path / relative: payload
        for relative, payload in relative_payloads.items()
    }
    census._atomic_write_bundle(
        disk_payloads,
        commit_path=tmp_path / census.CLONE_MANIFEST_PATH,
    )
    assert output.is_file()
    for relative in {
        *census.BUNDLE_PATHS.values(),
        census.CLONE_MANIFEST_PATH,
    }:
        assert (tmp_path / relative).is_file()
    published = census.validate_published_blocker_bundle(tmp_path)
    assert published["document"] == document
    manifest = published["manifest"]
    assert manifest["status"] == census.STATUS
    assert manifest["formal_pass_claimed"] is False
    assert manifest["formal_v3_schema_claimed"] is False
    assert manifest["causal_label_count"] == 0
    assert manifest["bundle_files"]["clone_fidelity"]["record_count"] == 1
    assert (
        manifest["bundle_files"]["causal_interventions"]["record_count"]
        == 0
    )
    assert (
        manifest["bundle_files"]["causal_component_ledger"]["record_count"]
        == 5
    )
    intervention_text = (
        tmp_path / census.CAUSAL_INTERVENTIONS_PATH
    ).read_text(encoding="utf-8")
    assert intervention_text.splitlines() == [
        ",".join(census.CAUSAL_INTERVENTION_FIELDS)
    ]
    ledger_rows = list(
        csv.DictReader(
            io.StringIO(
                (tmp_path / census.COMPONENT_LEDGER_PATH).read_text(
                    encoding="utf-8"
                )
            )
        )
    )
    assert len(ledger_rows) == 5
    pibt_row = next(row for row in ledger_rows if row["component"] == "pibt")
    assert pibt_row["screening_support_count"] == "0"
    assert pibt_row["formal_matched_boundary_count"] == "0"
    assert (
        pibt_row["prefilter_without_applicable_slice_count"]
        == "1337"
    )
    assert all(row["causal_label_count"] == "0" for row in ledger_rows)
    assert document["status"] == census.STATUS
    assert document["formal_pass_claimed"] is False
    assert document["causal_label_count"] == 0
    assert document["binary"] == {
        "path": str(binary.resolve()),
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    }
    assert set(document["replay_hashes"]) == set(
        census.REPLAY_HASH_FIELDS
    )
    assert document["support"]["I1_source_order_swap"][
        "multi_ready_boundary_count"
    ] == 2
    assert document["support"]["I3_next_edge"][
        "safe_alternative_boundary_lower_bound"
    ] == 1
    assert document["support"]["I4_hold_release"][
        "release_to_hold_boundary_lower_bound"
    ] == 2
    assert document["support"]["I2_merge_request_order_swap"][
        "exact_zero_proven"
    ] is True
    assert document["support"]["I2_merge_request_order_swap"][
        "eligible_live_multi_request_boundary_count"
    ] == 0
    i5 = document["support"]["I5_pibt_trigger"]
    assert i5["prefilter_candidate_count"] == 1_337
    assert i5["applicable_ready_slice_boundary_count"] == 0
    assert i5["prefilter_without_applicable_slice_count"] == 1_337
    assert i5["ready_slice_intervention_opportunity_count"] == 0
    assert i5["strict_same_ready_slice_boundary_count"] == 0
    assert (
        i5["support_status"]
        == "BLOCKED_ZERO_READY_SLICE_SUPPORT_WITH_PREFILTER_ONLY"
    )
    assert document["execution"]["clone_noop"]["binary"] == document["binary"]
    assert (
        "I2_ZERO_LIVE_ELIGIBLE_MULTI_REQUEST_GRANT_BOUNDARIES"
        in document["blocker"]["reasons"]
    )
    assert (
        "I5_ZERO_P2_READY_SLICE_INTERVENTION_BOUNDARIES"
        in document["blocker"]["reasons"]
    )
    assert len(requests) == 3
    clone_request, opportunity_request, decision_request = requests
    for request in requests:
        assert Path(request["expected_binary_path"]) == binary.resolve()
        assert Path(request["search_path"]) == binary.parent.resolve()
        assert len(request["bag_records"]) == census.FULL_SEGMENT_COUNT
    assert clone_request["preregistered_event_ordinal"] == 1_000
    assert opportunity_request["event_semantics"].startswith("E4_")
    assert opportunity_request["merge_grant_rule"] == "M0"
    assert opportunity_request["enable_opportunity_telemetry"] is True
    assert opportunity_request["trace_limit"] == 0
    assert decision_request["enable_opportunity_telemetry"] is False
    assert decision_request["trace_limit"] == 100_000
    assert all(
        gates["all_live_hard_gates_pass"]
        for gates in document["raw_hard_gates"].values()
    )
    census.validate_census_document(document)


def test_tampered_count_or_self_hash_is_rejected(tmp_path: Path) -> None:
    document, _, _, _, _ = _run(tmp_path, write=False)
    tampered = copy.deepcopy(document)
    tampered["support"]["I1_source_order_swap"][
        "multi_ready_boundary_count"
    ] += 1
    with pytest.raises(
        census.OpportunityCensusError, match="self hash drift"
    ):
        census.validate_census_document(tampered)


def test_rehashed_false_pass_and_false_blocker_are_rejected(
    tmp_path: Path,
) -> None:
    document, _, _, _, _ = _run(tmp_path, write=False)
    tampered = copy.deepcopy(document)
    tampered["status"] = "PASS"
    tampered["formal_pass_claimed"] = True
    tampered["self_sha256"] = census._self_hash(tampered)
    with pytest.raises(
        census.OpportunityCensusError, match="status must remain partial"
    ):
        census.validate_census_document(tampered)

    tampered = copy.deepcopy(document)
    tampered["blocker"]["reasons"].remove(
        "I5_ZERO_P2_READY_SLICE_INTERVENTION_BOUNDARIES"
    )
    tampered["self_sha256"] = census._self_hash(tampered)
    with pytest.raises(
        census.OpportunityCensusError,
        match="formal blocker does not recompute",
    ):
        census.validate_census_document(tampered)


def test_rehashed_hard_gate_support_and_projection_tamper_are_rejected(
    tmp_path: Path,
) -> None:
    document, _, _, _, _ = _run(tmp_path)

    tampered = copy.deepcopy(document)
    tampered["raw_hard_gates"]["opportunity_run"][
        "reservation_conflicts"
    ] = 1
    tampered["self_sha256"] = census._self_hash(tampered)
    with pytest.raises(
        census.OpportunityCensusError,
        match="opportunity_run live hard gate failure",
    ):
        census.validate_census_document(tampered)

    tampered = copy.deepcopy(document)
    tampered["support"]["I2_merge_request_order_swap"][
        "support_status"
    ] = "SUPPORTED_EXACT_BOUNDARY_SCREENING_ONLY"
    tampered["self_sha256"] = census._self_hash(tampered)
    with pytest.raises(
        census.OpportunityCensusError,
        match="I2 support does not recompute",
    ):
        census.validate_census_document(tampered)

    tampered = copy.deepcopy(document)
    tampered["i2_raw_counters"][
        "g4irsf14_i2_live_eligible_multi_request_boundary_count"
    ] = 1
    tampered["self_sha256"] = census._self_hash(tampered)
    with pytest.raises(
        census.OpportunityCensusError,
        match="I2 support does not recompute",
    ):
        census.validate_census_document(tampered)

    tampered = copy.deepcopy(document)
    tampered["execution"]["decision_run"][
        "i3_safe_alternative_boundary_lower_bound"
    ] += 1
    tampered["self_sha256"] = census._self_hash(tampered)
    with pytest.raises(
        census.OpportunityCensusError,
        match="I3 support-to-execution projection drift",
    ):
        census.validate_census_document(tampered)


def test_custom_executors_cannot_publish(tmp_path: Path) -> None:
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"exact-test-native-binary")
    event_executor, clone_executor, requests = _executors()
    with pytest.raises(
        census.OpportunityCensusError,
        match="CUSTOM_EXECUTOR_PUBLICATION_FORBIDDEN",
    ):
        census.generate_opportunity_census(
            binary=binary,
            search_path=tmp_path,
            bundle_root=tmp_path,
            event_executor=event_executor,
            clone_executor=clone_executor,
            write=True,
        )
    assert requests == []
    assert not (tmp_path / census.CLONE_MANIFEST_PATH).exists()


def test_clone_binary_echoes_and_object_are_execution_bound(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"exact-test-native-binary")
    kwargs = {
        "expected_binary_path": binary,
        "preregistered_event_ordinal": census.CLONE_EVENT_ORDINAL,
    }
    expected = {
        "path": str(binary.resolve()),
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    }
    payload = _clone_payload(
        kwargs,
        i2_exact_boundaries=0,
        i5_exact_prefilter=1_337,
        i5_exact_applicable=0,
    )
    census._validate_clone_payload(
        payload,
        clone_event_ordinal=census.CLONE_EVENT_ORDINAL,
        binary=expected,
    )

    mutations = (
        ("loaded_cpp_binary_path", str(tmp_path / "other.pyd")),
        ("loaded_cpp_binary_sha256", "f" * 64),
        ("binary", {"path": expected["path"], "sha256": "e" * 64}),
    )
    for field, replacement in mutations:
        tampered = copy.deepcopy(payload)
        tampered[field] = replacement
        with pytest.raises(census.OpportunityCensusError):
            census._validate_clone_payload(
                tampered,
                clone_event_ordinal=census.CLONE_EVENT_ORDINAL,
                binary=expected,
            )


def test_missing_exact_runtime_or_clone_counter_is_rejected(
    tmp_path: Path,
) -> None:
    def missing_runtime_counter(**kwargs: Any) -> dict[str, Any]:
        payload = _event_payload(
            kwargs,
            i2_exact_boundaries=0,
            i2_losers=0,
            i5_exact_prefilter=1_337,
            i5_exact_applicable=0,
            i5_triggers=1_337,
            i5_activations=0,
        )
        payload["summary"].pop(
            "g4irsf14_i2_live_eligible_multi_request_boundary_count"
        )
        return payload

    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"exact-test-native-binary")
    source = tmp_path / "census_source.py"
    source.write_text("SOURCE_VERSION = 1\n", encoding="utf-8")
    _, clone_executor, _ = _executors()
    with pytest.raises(
        census.OpportunityCensusError,
        match="missing deterministic core summary fields",
    ):
        census.generate_opportunity_census(
            binary=binary,
            search_path=tmp_path,
            event_executor=missing_runtime_counter,
            clone_executor=clone_executor,
            source_paths=(source,),
            write=False,
        )

    def missing_clone_counter(**kwargs: Any) -> dict[str, Any]:
        payload = _clone_payload(
            kwargs,
            i2_exact_boundaries=0,
            i5_exact_prefilter=1_337,
            i5_exact_applicable=0,
        )
        for branch in (
            "source_invariants",
            "baseline_invariants",
            "clone_invariants",
        ):
            payload[branch].pop(
                "g4irsf14_i5_applicable_ready_slice_boundary_count"
            )
        return payload

    event_executor, _, _ = _executors()
    with pytest.raises(
        census.OpportunityCensusError,
        match=(
            "g4irsf14_i5_applicable_ready_slice_boundary_count "
            "must be an integer"
        ),
    ):
        census.generate_opportunity_census(
            binary=binary,
            search_path=tmp_path,
            event_executor=event_executor,
            clone_executor=missing_clone_counter,
            source_paths=(source,),
            write=False,
        )


def test_bundle_sha_bindings_and_formal_claims_are_fail_closed(
    tmp_path: Path,
) -> None:
    document, _, _, _, _ = _run(tmp_path, write=False)
    payloads = census.build_blocker_bundle_payloads(document)
    validated = census.validate_blocker_bundle_payloads(payloads)
    assert validated["manifest"]["self_sha256"] == census._self_hash(
        validated["manifest"]
    )

    tampered_payloads = dict(payloads)
    tampered_payloads[census.CLONE_FIDELITY_PATH] += b"\n"
    with pytest.raises(
        census.OpportunityCensusError,
        match="clone_fidelity SHA binding drift",
    ):
        census.validate_blocker_bundle_payloads(tampered_payloads)

    tampered_payloads = dict(payloads)
    manifest = json.loads(
        payloads[census.CLONE_MANIFEST_PATH].decode("utf-8")
    )
    manifest["status"] = "PASS"
    manifest["formal_pass_claimed"] = True
    manifest["formal_v3_schema_claimed"] = True
    manifest["self_sha256"] = census._self_hash(manifest)
    tampered_payloads[census.CLONE_MANIFEST_PATH] = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    with pytest.raises(
        census.OpportunityCensusError,
        match="manifest status must remain partial",
    ):
        census.validate_blocker_bundle_payloads(tampered_payloads)


def test_validate_bundle_cli_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document, _, _, _, _ = _run(tmp_path)
    payloads = census.build_blocker_bundle_payloads(document)
    census._atomic_write_bundle(
        {
            tmp_path / relative: payload
            for relative, payload in payloads.items()
        },
        commit_path=tmp_path / census.CLONE_MANIFEST_PATH,
    )
    assert (
        census.main(
            ["--validate-bundle", "--bundle-root", str(tmp_path)]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == census.STATUS
    assert output["causal_label_count"] == 0

    forged = copy.deepcopy(document)
    forged["source_bundle"]["files"][0]["semantic_sha256"] = "f" * 64
    forged["source_bundle"]["bundle_sha256"] = census.canonical_sha256(
        forged["source_bundle"]["files"]
    )
    forged["self_sha256"] = census._self_hash(forged)
    forged_payloads = census.build_blocker_bundle_payloads(forged)
    forged_root = tmp_path / "forged"
    census._atomic_write_bundle(
        {
            forged_root / relative: payload
            for relative, payload in forged_payloads.items()
        },
        commit_path=forged_root / census.CLONE_MANIFEST_PATH,
    )
    with pytest.raises(
        census.OpportunityCensusError,
        match="source bundle current-disk identity drift",
    ):
        census.validate_published_blocker_bundle(forged_root)


def test_atomic_bundle_publication_rolls_back_before_manifest_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _, _, _, _ = _run(tmp_path, write=False)
    relative_payloads = census.build_blocker_bundle_payloads(document)
    disk_payloads = {
        tmp_path / relative: payload
        for relative, payload in relative_payloads.items()
    }
    prior: dict[Path, bytes] = {}
    for target in disk_payloads:
        target.parent.mkdir(parents=True, exist_ok=True)
        prior[target] = f"old:{target.name}\n".encode("ascii")
        target.write_bytes(prior[target])

    real_replace = os.replace
    call_count = 0

    def fail_once(source: Any, destination: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise OSError("injected publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(census.os, "replace", fail_once)
    with pytest.raises(
        census.OpportunityCensusError,
        match="BUNDLE_PUBLICATION_FAILED:OSError",
    ):
        census._atomic_write_bundle(
            disk_payloads,
            commit_path=tmp_path / census.CLONE_MANIFEST_PATH,
        )
    assert call_count >= 5
    assert all(target.read_bytes() == prior[target] for target in disk_payloads)


def test_binary_drift_during_execution_is_rejected(tmp_path: Path) -> None:
    mutated = False

    def mutate_binary(kwargs: dict[str, Any]) -> None:
        nonlocal mutated
        if not mutated:
            Path(kwargs["expected_binary_path"]).write_bytes(b"drift")
            mutated = True

    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"exact-test-native-binary")
    source = tmp_path / "census_source.py"
    source.write_text("SOURCE_VERSION = 1\n", encoding="utf-8")
    event_executor, clone_executor, _ = _executors(
        clone_side_effect=mutate_binary
    )
    with pytest.raises(
        census.OpportunityCensusError,
        match="EXECUTION_IDENTITY_DRIFT:clone_noop:after",
    ):
        census.generate_opportunity_census(
            binary=binary,
            search_path=tmp_path,
            event_executor=event_executor,
            clone_executor=clone_executor,
            source_paths=(source,),
            write=False,
        )


def test_source_drift_during_execution_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "census_source.py"
    source.write_text("SOURCE_VERSION = 1\n", encoding="utf-8")
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"exact-test-native-binary")
    mutated = False

    def mutate_source(_: dict[str, Any]) -> None:
        nonlocal mutated
        if not mutated:
            source.write_text("SOURCE_VERSION = 2\n", encoding="utf-8")
            mutated = True

    event_executor, clone_executor, _ = _executors(
        event_side_effect=mutate_source
    )
    with pytest.raises(
        census.OpportunityCensusError,
        match="EXECUTION_IDENTITY_DRIFT:opportunity_run:after",
    ):
        census.generate_opportunity_census(
            binary=binary,
            search_path=tmp_path,
            event_executor=event_executor,
            clone_executor=clone_executor,
            source_paths=(source,),
            write=False,
        )


def test_unsafe_runtime_or_frozen_echo_drift_aborts_publication(
    tmp_path: Path,
) -> None:
    def unsafe_executor(**kwargs: Any) -> dict[str, Any]:
        payload = _event_payload(
            kwargs,
            i2_exact_boundaries=0,
            i2_losers=0,
            i5_exact_prefilter=1_337,
            i5_exact_applicable=0,
            i5_triggers=1_337,
            i5_activations=0,
        )
        payload["summary"]["reservation_conflicts"] = 1
        return payload

    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"exact-test-native-binary")
    source = tmp_path / "census_source.py"
    source.write_text("SOURCE_VERSION = 1\n", encoding="utf-8")
    output = tmp_path / "must_not_exist.json"
    _, clone_executor, _ = _executors()
    with pytest.raises(
        census.OpportunityCensusError,
        match="opportunity_run live hard gate failure",
    ):
        census.generate_opportunity_census(
            binary=binary,
            search_path=tmp_path,
            output_path=output,
            event_executor=unsafe_executor,
            clone_executor=clone_executor,
            source_paths=(source,),
            write=False,
        )
    assert not output.exists()

    def wrong_control_executor(**kwargs: Any) -> dict[str, Any]:
        payload = _event_payload(
            kwargs,
            i2_exact_boundaries=0,
            i2_losers=0,
            i5_exact_prefilter=1_337,
            i5_exact_applicable=0,
            i5_triggers=1_337,
            i5_activations=0,
        )
        payload["summary"]["priority_mode_echo"] = "Q1"
        return payload

    with pytest.raises(
        census.OpportunityCensusError,
        match="frozen summary echo drift: priority_mode_echo",
    ):
        census.generate_opportunity_census(
            binary=binary,
            search_path=tmp_path,
            output_path=output,
            event_executor=wrong_control_executor,
            clone_executor=clone_executor,
            source_paths=(source,),
            write=False,
        )
    assert not output.exists()


def test_nonzero_i2_and_i5_support_does_not_create_false_zero_blocker(
    tmp_path: Path,
) -> None:
    document, _, _, _, _ = _run(
        tmp_path,
        i2_exact_boundaries=4,
        i2_losers=0,
        i5_exact_prefilter=5,
        i5_exact_applicable=3,
        i5_triggers=17,
        i5_activations=0,
        write=False,
    )
    i2 = document["support"]["I2_merge_request_order_swap"]
    i5 = document["support"]["I5_pibt_trigger"]
    assert i2["exact_zero_proven"] is False
    assert i2["eligible_live_multi_request_boundary_count"] == 4
    assert i5["prefilter_candidate_count"] == 5
    assert i5["applicable_ready_slice_boundary_count"] == 3
    assert i5["prefilter_without_applicable_slice_count"] == 2
    assert i5["ready_slice_intervention_opportunity_count"] == 3
    assert i5["strict_same_ready_slice_boundary_count"] == 3
    assert not any(
        reason.startswith("I2_ZERO") or reason.startswith("I5_ZERO")
        for reason in document["blocker"]["reasons"]
    )
    assert document["status"] == census.STATUS
    assert document["blocker"][
        "unique_complete_h_bag_h_system_intervention_count"
    ] == 0
    assert document["blocker"]["formal_pass_allowed"] is False
