from __future__ import annotations

from pathlib import Path

from scripts.eval import g4irsf13_final_joint_evaluation as final


ROOT = Path(__file__).resolve().parents[1]


def test_only_h0_h1_are_authorized_full_finalists() -> None:
    assert len(final.FINALISTS) == 2
    assert len(final.FINALISTS) <= final.MAX_FULL_FINALISTS
    by_id = {row.candidate_id: row for row in final.FINALISTS}
    assert set(by_id) == {
        "H0_F2_FROZEN",
        "H1_Q1_THESIS_NO_LEARNING",
    }
    assert by_id["H0_F2_FROZEN"].controls()["priority_mode"] == "Q0"
    h1 = by_id["H1_Q1_THESIS_NO_LEARNING"].controls()
    assert h1["priority_mode"] == "Q1"
    assert h1["resource_semantics"] == "R3_java_node_window_compatible"
    assert h1["scorer_mode"] == "S1_frozen_g4e_legal_local_adapter"
    assert h1["pibt_mode"] == "P2"
    assert h1["admission_mode"] == "off"
    assert h1["reservation_depth"] == 1
    assert h1["enable_fault_policy"] is True


def test_h1_selection_is_an_interpretable_equal_outcome_tie_break() -> None:
    evidence = final.validate_h1_tie_break(ROOT)
    assert evidence["status"] == "PASS_INTERPRETABLE_TIE_BREAK"
    assert evidence["selected_priority_mode"] == "Q1"
    assert evidence["empirical_superiority_claimed"] is False
    assert evidence["not_selected_equal_candidates"] == [
        "Q0",
        "Q3",
        "P1",
        "P3",
    ]


def test_failed_v3_gate_forces_h2_h3_not_run() -> None:
    evidence = final.validate_v3_fail_closed(ROOT)
    assert evidence["status"] == "FAIL_CLOSED"
    assert evidence["blocker"] == final.V3_BLOCKER
    assert evidence["fields"] == {
        "status": "OFFLINE_LEVEL_A_FAIL_CLOSED_LOOP_NOT_RUN",
        "offline_gate_status": "FAIL",
        "runtime_eligible": False,
        "closed_loop_status": "NOT_RUN",
    }


def _raw(
    task_id: int,
    *,
    entry: float,
    source: int,
    goal: int,
    original: float,
    dwell: float,
    source_wait: float,
    network: float,
    ebs: bool = False,
    contention: bool = False,
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "complete": True,
        "original_entry_time_tth_seconds": original,
        "scheduled_pre_release_wait_seconds": dwell,
        "source_wait_seconds": source_wait,
        "network_time_seconds": network,
        "original_start": source,
        "original_goal": goal,
        "original_entry_time": entry,
        "clock_hour": int(entry // 3600) % 24,
        "continuous_block_index": int(
            entry // final.CONTINUOUS_BLOCK_SECONDS
        ),
        "has_ebs_release": ebs,
        "f2_contention_involved": contention,
        "path_edge_count": 8,
        "edge_travel_time_seconds": 42.0,
        "loop_detour_time_seconds": 0.0,
        "loop_count": 0,
        "deadline_miss": False,
    }


def test_real_slice_builder_uses_fixed_input_semantics() -> None:
    rows = [
        _raw(
            1,
            entry=3600.0,
            source=3,
            goal=48,
            original=120.0,
            dwell=60.0,
            source_wait=10.0,
            network=50.0,
            ebs=True,
            contention=True,
        ),
        _raw(
            2,
            entry=3700.0,
            source=4,
            goal=49,
            original=180.0,
            dwell=60.0,
            source_wait=20.0,
            network=100.0,
        ),
        _raw(
            3,
            entry=25_000.0,
            source=3,
            goal=48,
            original=240.0,
            dwell=120.0,
            source_wait=20.0,
            network=100.0,
            ebs=True,
        ),
    ]
    summary = final.summarize_rows(rows)
    assert summary["selected_raw_bag_count"] == 3
    assert summary["original_entry_mean_minutes"] == 3.0
    assert summary["original_entry_median_seconds"] == 180.0
    assert summary["decision_sensitive_mean_minutes"] == 100.0 / 60.0
    slices = final.build_slice_rows(rows)
    types = {row["slice_type"] for row in slices}
    assert types == {
        "continuous_6h_block",
        "source",
        "goal",
        "clock_hour",
        "storage_lifecycle",
        "busy_hour",
        "ebs_release",
        "contention",
    }
    contention = next(
        row for row in slices if row["slice_type"] == "contention"
    )
    assert contention["selected_raw_bag_count"] == 1
    ebs = next(row for row in slices if row["slice_type"] == "ebs_release")
    assert ebs["selected_raw_bag_count"] == 2


def test_algorithm_hash_excludes_only_explicit_host_timing_fields() -> None:
    assert final.NONALGORITHM_RUNTIME_FIELDS == {
        "wall_seconds",
        "runtime_seconds",
        "event_throughput_per_second",
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
        "peak_working_set_bytes",
        "working_set_bytes",
        "peak_rss_bytes",
        "rss_bytes",
    }
    base = {
        "bags": [{"segment_id": "a", "finish_time": 1.0}],
        "junction_state": [{"node": 24, "owner": 1}],
        "summary": {
            "completed_count": 1,
            "unsafe_entry_count": 0,
            "bounded_local_pibt_commit_count": 1,
            "priority_mode_echo": "Q1",
            "fault_event_count": 0,
            "runtime_seconds": 1.0,
            "event_throughput_per_second": 10.0,
            "decision_latency_us_p50": 2.0,
            "decision_latency_us_p95": 3.0,
            "decision_latency_us_p99": 4.0,
        },
        "trace_context": {"summary_only": True},
        "events": [],
        "decisions": [],
        "decision_trace": [],
        "hold_attempts": [],
        "pibt_events": [],
        "credit_events": [],
        "fault_events": [],
        "loaded_cpp_binary_path": "x",
        "loaded_cpp_binary_sha256": "b" * 64,
    }
    timing_only = {
        **base,
        "summary": {
            **base["summary"],
            "runtime_seconds": 9.0,
            "event_throughput_per_second": 99.0,
            "decision_latency_us_p50": 8.0,
            "decision_latency_us_p95": 9.0,
            "decision_latency_us_p99": 10.0,
        },
    }
    first = final.algorithm_projection_hashes(base)
    second = final.algorithm_projection_hashes(timing_only)
    for field in (
        "runtime_algorithm_sha256",
        "bags_sha256",
        "junction_state_sha256",
        "algorithm_summary_sha256",
        "trace_context_sha256",
    ):
        assert first[field] == second[field]

    safety_drift = {
        **base,
        "summary": {**base["summary"], "unsafe_entry_count": 1},
    }
    assert (
        final.algorithm_projection_hashes(safety_drift)[
            "algorithm_summary_sha256"
        ]
        != first["algorithm_summary_sha256"]
    )
    bag_drift = {**base, "bags": [{"segment_id": "a", "finish_time": 2.0}]}
    assert (
        final.algorithm_projection_hashes(bag_drift)["bags_sha256"]
        != first["bags_sha256"]
    )
    junction_drift = {
        **base,
        "junction_state": [{"node": 24, "owner": 2}],
    }
    assert (
        final.algorithm_projection_hashes(junction_drift)[
            "junction_state_sha256"
        ]
        != first["junction_state_sha256"]
    )


def test_failed_projection_audit_is_bound_but_never_reused() -> None:
    binding = final.bind_failed_projection_audit(ROOT)
    assert binding["status"] == "FAILED_PROJECTION_AUDIT"
    assert binding["reused_for_final_equivalence"] is False
    descriptor = final._read_json(ROOT / final.PROJECTION_AUDIT_PATH)
    assert descriptor["repeat_count"] == final.REPEAT_COUNT
    assert descriptor["all_runtime_hard_gates_pass"] is True
    assert descriptor["legacy_runner_source_sha256"] == (
        final.LEGACY_FAILED_H_RUNNER_SHA256
    )
    assert descriptor["replacement_protocol"][
        "complete_bags_hash_required"
    ] is True
    assert descriptor["replacement_protocol"][
        "junction_state_hash_required"
    ] is True
    assert descriptor["replacement_protocol"][
        "full_algorithm_summary_hash_required"
    ] is True
    validator_failure = final.bind_projection_validator_failure_audit(ROOT)
    assert validator_failure["status"] == "PROJECTION_VALIDATOR_FAILURE"
    assert validator_failure["total_repeat_count"] == 10
    assert validator_failure["reused_for_final_equivalence"] is False
    encoding_failure = (
        final.bind_report_encoding_validator_failure_audit(ROOT)
    )
    assert (
        encoding_failure["status"]
        == "REPORT_ENCODING_VALIDATOR_FAILURE"
    )
    assert encoding_failure["total_repeat_count"] == 10
    assert encoding_failure["reused_for_final_equivalence"] is False


def _fake_repeat(
    candidate_id: str,
    repeat_index: int,
    *,
    mean: float,
) -> dict[str, object]:
    metrics = {
        "selected_raw_bag_count": final.FULL_RAW_BAGS,
        "complete_raw_bag_count": final.FULL_RAW_BAGS,
        "completion_rate": 1.0,
        "comparison_eligible": True,
        "original_entry_mean_minutes": mean,
        "original_entry_median_seconds": 100.0,
        "original_entry_p95_seconds": 200.0,
        "original_entry_p99_seconds": 300.0,
        "original_entry_max_seconds": 400.0,
        "scheduled_dwell_mean_minutes": final.SCHEDULED_DWELL_MINUTES,
        "source_wait_mean_minutes": 0.3,
        "network_time_mean_minutes": 3.8,
        "decision_sensitive_mean_minutes": 4.1,
        "path_edge_count_mean": 8.0,
        "edge_travel_time_mean_seconds": 42.0,
        "loop_detour_time_mean_seconds": 0.0,
        "loop_count": 0,
        "deadline_miss_raw_bag_count": 0,
    }
    counters = {
        "selected_segment_count": final.FULL_SEGMENTS,
        "completed_segment_count": final.FULL_SEGMENTS,
        "failed_segment_count": 0,
        "conflict_count": 0,
        "unsafe_entry_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "future_routes_stored": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "reservation_depth": 1,
        "pibt_applicability_count": 1,
        "pibt_attempt_count": 1,
        "pibt_commit_count": 1,
        "pibt_rollback_count": 0,
        "pibt_backtrack_count": 0,
        "pibt_handoff_count": 1,
        "pibt_max_observed_depth": 1,
    }
    slice_row = {
        "slice_type": "busy_hour",
        "slice_id": "01",
        "slice_definition": "test",
        **metrics,
    }
    return {
        "candidate_id": candidate_id,
        "candidate_role": "test",
        "repeat_index": repeat_index,
        "execution_status": "EXECUTED",
        "gate_status": "PASS",
        "hard_blockers": [],
        "metrics": metrics,
        "counters": counters,
        "runtime_summary": {
            "shield_rejection_count": 0,
            "physical_fault_interlock_rejection_count": 0,
            "priority_mode_echo": "Q1" if candidate_id.startswith("H1") else "Q0",
        },
        "slices": [slice_row],
        "runtime_deterministic_sha256": candidate_id + "-runtime",
        "legacy_runtime_projection_sha256": candidate_id + "-legacy",
        "bags_sha256": candidate_id + "-bags",
        "junction_state_sha256": candidate_id + "-junction",
        "algorithm_summary_sha256": candidate_id + "-summary",
        "trace_context_sha256": candidate_id + "-trace-context",
        "segment_result_sha256": candidate_id + "-segments",
        "slice_projection_sha256": candidate_id + "-slices",
        "repeat_result_file_sha256": f"{candidate_id}-{repeat_index}",
        "binary_sha256": "b" * 64,
        "source_bundle_sha256": "s" * 64,
        "repository_base_head": "a" * 40,
        "map_raw_sha256": final.cde.CANONICAL_MAP_RAW_SHA256,
        "task_raw_sha256": final.cde.CANONICAL_SOURCE_RAW_SHA256,
        "input_selection_sha256": "i" * 64,
        "archive_reused": False,
        "wall_seconds": 1.0,
    }


def test_joint_decision_keeps_raw_entry_v2_gate_and_not_run_rows() -> None:
    results = {
        candidate_id: [
            _fake_repeat(
                candidate_id,
                index,
                mean=final.F2_RECONCILED_RAW_ENTRY_MINUTES,
            )
            for index in range(1, final.REPEAT_COUNT + 1)
        ]
        for candidate_id in (
            "H0_F2_FROZEN",
            "H1_Q1_THESIS_NO_LEARNING",
        )
    }
    rows, decision = final.build_table_rows(results, root=ROOT)
    assert decision["decision_status"] == "HISTORICAL_ONLY_PASS"
    assert decision["strict_win_vs_v2_safe"] is False
    assert decision["strict_win_vs_f2"] is False
    assert decision["all_1x_hard_gates_pass"] is True
    v2 = next(
        row
        for row in rows
        if row.get("candidate_id") == "FROZEN_V2_SAFE"
    )
    assert (
        v2["original_entry_mean_minutes"]
        == final.FROZEN_V2_SAFE_RAW_ENTRY_MINUTES
    )
    reference_ids = {
        row["candidate_id"]
        for row in rows
        if row.get("row_type") == "REFERENCE_CONTROL"
    }
    assert {
        "HISTORICAL_PARSED_HCA",
        "CORRECTED_MATCHED_HCA_TARGET",
        "FROZEN_V2_SAFE",
        "F1_RULE_BASELINE",
        "F2_FROZEN_RECONCILED",
        "PIBT_OFF_CENSORED",
        "NO_PIBT_ABLATION",
        "BEST_NEW_CANDIDATE",
        "NO_LEARNING_ABLATION",
        "FAULT_POLICY_ABLATION",
    } <= reference_ids
    blocked = [
        row for row in rows if row.get("row_type") == "FINALIST_NOT_RUN"
    ]
    assert len(blocked) == 2
    assert all(row["blocker"] == final.V3_BLOCKER for row in blocked)
    assert all("original_entry_mean_minutes" not in row for row in blocked)
    repeat = next(row for row in rows if row["row_type"] == "FINAL_REPEAT")
    assert repeat["selected_segment_count"] == final.FULL_SEGMENTS
    assert repeat["completed_segment_count"] == final.FULL_SEGMENTS
    report = final._report(
        results,
        rows,
        decision,
        {"status": "PASS_INTERPRETABLE_TIE_BREAK"},
        {"blocker": final.V3_BLOCKER},
    ).decode("ascii")
    assert "\u0431\u043a" not in report
    assert "P1\u0438CP4" not in report
    assert "P1-P4" in report
    assert "| N/A | N/A | N/A | N/A |" in report

    failed_audit = {
        "status": "FAILED_PROJECTION_AUDIT",
        "path": final.PROJECTION_AUDIT_PATH.as_posix(),
        "file_sha256": "a" * 64,
        "legacy_experiment_identity_sha256": "b" * 64,
        "reused_for_final_equivalence": False,
    }
    validator_failure_audit = {
        "status": "PROJECTION_VALIDATOR_FAILURE",
        "path": final.VALIDATOR_FAILURE_AUDIT_PATH.as_posix(),
        "file_sha256": "e" * 64,
        "reused_for_final_equivalence": False,
        "total_repeat_count": 10,
    }
    report_encoding_audit = {
        "status": "REPORT_ENCODING_VALIDATOR_FAILURE",
        "path": final.REPORT_ENCODING_AUDIT_PATH.as_posix(),
        "file_sha256": "f" * 64,
        "reused_for_final_equivalence": False,
        "total_repeat_count": 10,
    }
    bundle = final.build_bundle(
        results,
        decision,
        table_sha256="c" * 64,
        report_sha256="d" * 64,
        selection_evidence={
            "failed_projection_audit": failed_audit,
            "projection_validator_failure_audit": (
                validator_failure_audit
            ),
            "report_encoding_validator_failure_audit": (
                report_encoding_audit
            ),
        },
        v3_dependency={},
        root=ROOT,
    )
    assert bundle["failed_projection_audit"] == failed_audit
    assert (
        bundle["projection_validator_failure_audit"]
        == validator_failure_audit
    )
    assert (
        bundle["report_encoding_validator_failure_audit"]
        == report_encoding_audit
    )
    assert bundle["h2_execution_status"] == "NOT_RUN"
    assert bundle["h2_not_run_reason"] == final.V3_BLOCKER
    assert bundle["h3_execution_status"] == "NOT_RUN"
    assert bundle["h3_not_run_reason"] == final.V3_BLOCKER
    assert bundle["source_bundle"]["bundle_sha256"]
    assert bundle["algorithm_equivalence_protocol"][
        "excluded_nonalgorithm_fields"
    ] == sorted(final.NONALGORITHM_RUNTIME_FIELDS)


def test_committed_original_scale_outputs_validate() -> None:
    validation = final.validate_committed_outputs(ROOT)
    assert validation["status"] == "PASS"
    assert validation["decision_status"] == "HISTORICAL_ONLY_PASS"
    assert validation["repeat_count"] == 2 * final.REPEAT_COUNT
