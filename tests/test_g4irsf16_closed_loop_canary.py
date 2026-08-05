from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from czr005.g4irsf16.model import with_self_sha256
from scripts.eval import run_g4irsf16_closed_loop_canary as canary


def _passing_summary(segments: int = 512) -> dict[str, object]:
    return {
        "requested_count": segments,
        "completed_count": segments,
        "failed_count": 0,
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
        "reservation_depth": 1,
        "max_edges_selected_per_arrive": 1,
        "max_edges_selected_per_bag_per_decision": 1,
        "two_step_reservation_count": 0,
        "full_future_routes_stored": 0,
        "bag_future_path_field_present": False,
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
        "merge_grant_post_commit_expired_count": 0,
        "merge_grant_post_commit_revoked_count": 0,
        "merge_grant_post_commit_rollback_count": 0,
        "merge_grant_queue_capacity_block_count": 0,
        "merge_grant_lifecycle_transition_count": 10_000,
        "merge_grant_lifecycle_stored_count": 8_192,
        "merge_grant_lifecycle_dropped_count": 0,
        "merge_grant_lifecycle_complete": True,
        "merge_grant_protocol_integrity_pass": True,
    }


def _timing(*, p95: float, p99: float) -> dict[str, float]:
    return {
        "original_entry_mean_minutes": 1.0,
        "original_entry_p95_seconds": p95,
        "original_entry_p99_seconds": p99,
        "java_release_mean_minutes": 0.8,
        "source_wait_mean_minutes": 0.1,
        "network_time_mean_minutes": 0.7,
        "total_system_time_mean_minutes": 1.0,
    }


def test_fixed_ladder_includes_512() -> None:
    assert canary.ALLOWED_SEGMENTS == (144, 512, 2_048, 8_192)
    parsed = canary._parser().parse_args(
        ["--binary", "unused.pyd", "--segments", "512"]
    )
    assert parsed.segments == 512


def test_off_hard_gates_cover_complete_runtime_contract() -> None:
    summary = _passing_summary()
    assert canary._hard_gates(summary, 512, "off")["safety_pass"] is True

    failures = {
        "failed_count": 1,
        "physical_fault_edge_entry_violation_count": 1,
        "reservation_conflicts": 1,
        "runtime_full_astar_calls": 1,
        "global_reservation_scan_count": 1,
        "priority_future_route_input_count": 1,
        "scorer_future_schedule_input_count": 1,
        "full_future_routes_stored": 1,
        "reservation_depth": 2,
        "unresolved_deadlock_count": 1,
        "event_limit_reached": True,
        "time_limit_reached": True,
    }
    for field, value in failures.items():
        mutated = deepcopy(summary)
        mutated[field] = value
        result = canary._hard_gates(mutated, 512, "off")
        assert result["safety_pass"] is False, field

    cancellation_attempt = deepcopy(summary)
    cancellation_attempt.pop("priority_global_scan_count")
    cancellation_attempt["global_reservation_scan_count"] = 1
    assert (
        canary._hard_gates(cancellation_attempt, 512, "off")["safety_pass"]
        is False
    )


def test_bounded_merge_lifecycle_drop_is_telemetry_not_safety_failure() -> None:
    summary = _passing_summary()
    summary["merge_grant_lifecycle_dropped_count"] = 1_808
    summary["merge_grant_lifecycle_complete"] = False
    summary["merge_grant_protocol_integrity_pass"] = False
    result = canary._hard_gates(summary, 512, "off")
    assert result["safety_pass"] is True
    assert result["merge_lifecycle_telemetry"]["truncated"] is True
    assert result["merge_lifecycle_telemetry"]["safety_gate"] is False

    compensated = deepcopy(summary)
    compensated["merge_grant_post_commit_rollback_count"] = 7
    compensated["merge_grant_queue_capacity_block_count"] = 7
    compensated_result = canary._hard_gates(compensated, 512, "off")
    assert compensated_result["safety_pass"] is True
    assert compensated_result["merge_post_commit_telemetry"]["zero_required"] is False

    inconsistent = deepcopy(compensated)
    inconsistent["merge_grant_queue_capacity_block_count"] = 6
    assert canary._hard_gates(inconsistent, 512, "off")["safety_pass"] is False


def test_raw_bag_tail_early_gates_are_inclusive_and_fail_closed() -> None:
    baseline = _timing(p95=100.0, p99=120.0)
    at_limit = _timing(p95=102.0, p99=124.0)
    passing = canary._performance_comparison(at_limit, baseline)
    assert passing["early_gate_pass"] is True
    assert passing["candidate_minus_off"]["original_entry_p95_seconds"] == 2.0
    assert passing["candidate_minus_off"]["original_entry_p99_seconds"] == 4.0

    over_limit = _timing(p95=102.000001, p99=124.000001)
    assert (
        canary._performance_comparison(over_limit, baseline)["early_gate_pass"]
        is False
    )
    assert canary._performance_comparison(at_limit, None)["early_gate_pass"] is False


def test_repository_metadata_paths_are_relative_posix() -> None:
    path = canary._metadata_path(canary.DEFAULT_RULE_BUNDLE)
    assert path == "artifacts/policies/g4irsf16_best_rule_bundle.json"
    assert "\\" not in path


def test_rule_bundle_identity_is_canonical_across_checkout_line_endings(
    tmp_path: Path,
) -> None:
    payload = with_self_sha256(
        {"schema": "czr005.g4irsf16.rule_bundle.v1", "selected_rule": "H0"}
    )
    text = json.dumps(payload, sort_keys=True, indent=2)
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes((text + "\n").encode("utf-8"))
    crlf.write_bytes((text.replace("\n", "\r\n") + "\r\n").encode("utf-8"))

    assert canary._rule_bundle_self_sha256(lf) == payload["self_sha256"]
    assert canary._rule_bundle_self_sha256(crlf) == payload["self_sha256"]


def test_evidence_reconciliation_is_explicit_and_removes_local_binary_path(
    tmp_path: Path,
) -> None:
    segments = 512
    stem = f"g4irsf16_closed_loop_h5_{segments}"
    candidate = _passing_summary(segments)
    candidate.update(
        {
            "g4irsf16_supervisor_mode": "closed_loop",
            "g4irsf16_diagnostic_only": True,
            "g4irsf16_promotion_authorized": False,
            "g4irsf16_i4_policy_id": "H5",
            "g4irsf16_runtime_global_scan_count": 0,
            "g4irsf16_future_route_input_count": 0,
            "g4irsf16_future_schedule_input_count": 0,
            "g4irsf16_posthoc_input_count": 0,
            "g4irsf16_full_astar_call_count": 0,
            "g4irsf16_action_change_count": 1,
            "g4irsf16_i4_activation_count": 1,
            "decision_trace_truncated": False,
            "loaded_cpp_binary_path": r"C:\tmp\private\module.pyd",
        }
    )
    baseline = _passing_summary(segments)
    baseline["loaded_cpp_binary_path"] = r"C:\tmp\private\module.pyd"
    metadata = {
        "status": "FAIL_HARD_GATE",
        "binary": {"path": r"C:\tmp\private\module.pyd", "sha256": "0" * 64},
        "telemetry": {"action_change_count": 1},
        "raw_bag_performance": {
            "candidate": _timing(p95=100.0, p99=120.0),
            "off": _timing(p95=100.0, p99=120.0),
        },
        "off_comparison": {"enabled": True},
        "artifacts": {"metadata": f"{stem}.metadata.json"},
    }
    (tmp_path / f"{stem}.summary.json").write_text(json.dumps(candidate))
    (tmp_path / f"{stem}.off.summary.json").write_text(json.dumps(baseline))
    (tmp_path / f"{stem}.metadata.json").write_text(json.dumps(metadata))
    (tmp_path / f"{stem}.activations.jsonl").write_text("{}\n")

    reconciled = canary.reconcile_existing_evidence(
        segments=segments,
        mode="closed_loop",
        output_dir=tmp_path,
        compare_off=True,
    )
    assert reconciled["status"] == "PASS"
    assert reconciled["binary"]["path"] == "EXTERNAL_NATIVE_BINARY/module.pyd"
    assert reconciled["evidence_reconciliation"]["native_runtime_reexecuted"] is False
    published = (tmp_path / f"{stem}.summary.json").read_text()
    assert "C:\\tmp" not in published
    assert "EXTERNAL_NATIVE_BINARY/module.pyd" in published
