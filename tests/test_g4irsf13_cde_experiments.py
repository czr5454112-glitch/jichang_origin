from __future__ import annotations

import json
from pathlib import Path
import socket
import time

import pytest

from scripts.eval import g4irsf13_cde_experiments as cde


ROOT = Path(__file__).resolve().parents[1]


def test_declared_cde_matrix_is_exact_and_complete() -> None:
    interaction = {row.candidate_id: row for row in cde.interaction_candidates()}
    assert list(interaction) == [f"D{index}" for index in range(10)]
    assert (interaction["D0"].scorer, interaction["D0"].pibt) == (
        "S1_frozen_g4e_legal_local_adapter",
        "P2",
    )
    assert interaction["D4"].control == "C7"
    assert interaction["D5"].control == "C8"
    assert interaction["D6"].priority == "Q1"
    assert interaction["D7"].priority == "Q2"
    assert interaction["D8"].pibt == "P1"
    assert interaction["D9"].pibt == "P3"
    assert interaction["D8"].priority == "$QBEST"
    assert interaction["D9"].priority == "$QBEST"

    priority = {row.candidate_id: row for row in cde.priority_candidates()}
    assert {priority[f"C_Q{index}"].priority for index in range(4)} == {
        "Q0",
        "Q1",
        "Q2",
        "Q3",
    }
    assert priority["C_B2"].framework == "legacy_order_one_step_diagnostic"
    assert priority["C_B2"].diagnostic_only is True

    depth = cde.pibt_depth_candidates()
    assert [row.pibt for row in depth] == ["P0", "P1", "P2", "P3", "P4"]
    assert depth[-1].diagnostic_only is True
    assert [row.preference for row in cde.pibt_preference_candidates()] == [
        "current",
        "dodge",
        "local_regret",
        "dodge_regret",
    ]


def test_runtime_controls_bind_c7_c8_q_and_preference_without_route_fields() -> None:
    d4 = next(row for row in cde.interaction_candidates() if row.candidate_id == "D4")
    d5 = next(row for row in cde.interaction_candidates() if row.candidate_id == "D5")
    q3 = next(row for row in cde.priority_candidates() if row.candidate_id == "C_Q3")
    preference = next(
        row
        for row in cde.pibt_preference_candidates()
        if row.preference == "dodge_regret"
    )
    c7 = cde.candidate_runtime_controls(d4, qbest=None)
    c8 = cde.candidate_runtime_controls(d5, qbest=None)
    q3_controls = cde.candidate_runtime_controls(q3, qbest=None)
    pref_controls = cde.candidate_runtime_controls(
        preference,
        qbest="Q2",
        regret_prior_records=[(24, 27, 49, 1.25)],
    )
    assert c7["admission_mode"] == "merge_only_first_edge_credit"
    assert c8["admission_mode"] == "contention_triggered_first_edge_credit"
    assert c7["selective_credit_contention_threshold"] == 1
    assert q3_controls["priority_mode"] == "Q3"
    assert pref_controls["priority_mode"] == "Q2"
    assert pref_controls["pibt_preference_mode"] == "dodge_regret"
    assert pref_controls["pibt_regret_prior_records"] == [[24, 27, 49, 1.25]]
    forbidden = {
        "route",
        "future_route",
        "astar",
        "reservation_table",
        "global_scan",
    }
    assert forbidden.isdisjoint(c7)
    assert forbidden.isdisjoint(c8)
    assert forbidden.isdisjoint(pref_controls)


def test_real_motif_uses_unmodified_map2_and_protected_task_rows() -> None:
    motif = cde.load_real_map_motif(ROOT)
    assert motif.tier == "motif"
    assert motif.segment_count == cde.MOTIF_TARGET_SEGMENTS
    assert motif.provenance["fixed_real_map_only"] is True
    assert motif.provenance["map_raw_sha256"] == cde.CANONICAL_MAP_RAW_SHA256
    assert motif.provenance["map_topology_mutated"] is False
    assert motif.provenance["task_rows_mutated"] is False
    assert motif.provenance["merge_nodes"]
    assert len({int(row["start"]) for row in motif.rows}) >= 2

    protected = {
        str(row["segment_id"]): row for row in cde._all_task_rows(ROOT)
    }
    for selected in motif.rows:
        original = protected[str(selected["segment_id"])]
        for name in (
            "task_id",
            "pass_time",
            "std",
            "start",
            "goal",
            "original_entry_time",
        ):
            assert selected[name] == original[name]


def test_matched_contention_cohort_preserves_history_to_actual_f2_state() -> None:
    selection, manifest, _prior = cde.load_matched_contention_cohort(ROOT)
    prefix = cde.load_prefix_selection("8192", ROOT)
    assert selection.segment_count == 8192
    assert selection.selected_segment_ids_sha256 == (
        prefix.selected_segment_ids_sha256
    )
    assert selection.provenance["declared_prefix_segments"] == 8192
    assert (
        selection.provenance["selected_state_context_row_count"] > 0
    )
    assert (
        selection.provenance["selected_f2_pibt_involved_raw_bag_count"] > 0
    )
    assert manifest["cohort"]["history_closed"] is True
    assert manifest["cohort"]["declared_prefix_segments"] == 8192


def test_missing_append_only_runtime_capability_is_not_silently_dropped() -> None:
    def old_runtime(priority_mode: str) -> dict[str, object]:
        return {"priority_mode": priority_mode}

    capabilities = cde.inspect_runtime(old_runtime)
    candidate = cde.priority_candidates()[0]
    controls = cde.candidate_runtime_controls(candidate, qbest=None)
    blockers = cde.capability_blockers(capabilities, controls)
    assert "MISSING_EXECUTOR_CAPABILITY:pibt_preference_mode" in blockers
    assert "MISSING_EXECUTOR_CAPABILITY:admission_mode" in blockers
    assert "MISSING_EXECUTOR_CAPABILITY:expected_binary_path" in blockers


def test_current_cpp_backend_exposes_every_cde_adapter_control() -> None:
    from czr005 import cpp_backend

    capabilities = cde.inspect_runtime(
        cpp_backend.g4irsf11_event_runtime_from_records
    )
    candidate = next(
        row for row in cde.interaction_candidates() if row.candidate_id == "D5"
    )
    controls = cde.candidate_runtime_controls(candidate, qbest=None)
    assert cde.capability_blockers(capabilities, controls) == []


def _result(
    candidate_id: str,
    *,
    mean: float = 1.0,
    p95: float = 70.0,
    p99: float = 80.0,
    source: float = 0.2,
    network: float = 0.8,
    rollback: int = 1,
    gate: str = "PASS",
    cohort: str = "a" * 64,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "family": "interaction",
        "tier": "144",
        "selection_sha256": cohort,
        "cohort_sha256": cohort,
        "execution_status": "EXECUTED",
        "gate_status": gate,
        "promotion_status": "PENDING_EARLY_REJECT_REVIEW",
        "timing": {
            "comparison_eligible": gate == "PASS",
            "original_entry_mean_minutes": mean,
            "original_entry_p95_seconds": p95,
            "original_entry_p99_seconds": p99,
            "source_wait_mean_minutes": source,
            "network_time_mean_minutes": network,
        },
        "counters": {"pibt_rollback_count": rollback},
    }


def test_2048_promotion_budget_keeps_minimum_informative_8192_set() -> None:
    priority_rows = []
    for index, candidate_id in enumerate(("C_Q0", "C_Q1", "C_Q3")):
        row = _result(candidate_id, mean=1.0 + index / 100.0)
        row["family"] = "priority"
        row["promotion_status"] = "ELIGIBLE_FOR_NEXT_TIER"
        priority_rows.append(row)
    interaction_rows = []
    for index, candidate_id in enumerate(("D0", "D7", "D8", "D9")):
        row = _result(candidate_id, mean=1.0 + index / 100.0)
        row["promotion_status"] = "ELIGIBLE_FOR_NEXT_TIER"
        interaction_rows.append(row)

    assert cde.TIER_PROMOTION_LIMITS["2048"] == {
        "priority": 3,
        "interaction": 2,
    }
    assert cde.rank_survivors(
        priority_rows,
        limit=3,
        retain_ids=("C_Q0", "C_Q1", "C_Q3"),
    ) == {"C_Q0", "C_Q1", "C_Q3"}
    assert cde.rank_survivors(
        interaction_rows,
        limit=2,
        retain_ids=("D8", "D9"),
    ) == {"D8", "D9"}


def test_deduplicated_d0_uses_exact_c_q0_alias_as_interaction_baseline() -> None:
    q0 = _result("C_Q0")
    q0["family"] = "priority"
    q0["tier"] = "8192"
    d0 = _result("D0", gate="NOT_EVALUATED")
    d0["tier"] = "8192"
    d0["execution_status"] = "NOT_RUN"
    p1 = _result("D8")
    p1["tier"] = "8192"

    evaluated = {
        str(row["candidate_id"]): row
        for row in cde.apply_early_rejects([q0, d0, p1])
    }
    assert evaluated["D0"]["promotion_status"] == "REJECT"
    assert evaluated["D8"]["promotion_status"] == "ELIGIBLE_FOR_NEXT_TIER"
    assert evaluated["D8"]["early_reject_reasons"] == ""


def test_early_reject_catches_network_offset_and_tail_regression() -> None:
    baseline = _result("D0")
    harmful = _result(
        "D5",
        mean=1.03,
        p95=73.0,
        p99=85.0,
        source=0.1,
        network=0.93,
        rollback=20,
    )
    reasons = cde.early_reject_reasons(harmful, baseline)
    assert "MEAN_WORSE_BY_MORE_THAN_1_SECOND_PER_BAG" in reasons
    assert "P95_WORSE_BY_MORE_THAN_2_SECONDS" in reasons
    assert "P99_WORSE_BY_MORE_THAN_4_SECONDS" in reasons
    assert "SOURCE_WAIT_GAIN_MORE_THAN_OFFSET_BY_NETWORK_LOSS" in reasons
    assert "PIBT_ROLLBACK_SURGE" in reasons


def test_matched_contention_requires_every_depth_complete_on_same_hash() -> None:
    rows = []
    for depth in range(5):
        row = _result(f"E_P{depth}")
        row["family"] = "pibt_depth"
        row["timing"] = {
            **row["timing"],
            "comparison_eligible": True,
        }
        rows.append(row)
    gate = cde.matched_contention_gate(rows)
    assert gate["matched_comparison_eligible"] is True

    rows[0]["gate_status"] = "FAIL"
    rows[0]["timing"]["comparison_eligible"] = False
    failed = cde.matched_contention_gate(rows)
    assert failed["matched_comparison_eligible"] is False
    assert any("E_P0" in blocker for blocker in failed["blockers"])

    rows[0]["gate_status"] = "PASS"
    rows[0]["timing"]["comparison_eligible"] = True
    rows[-1]["cohort_sha256"] = "b" * 64
    mismatched = cde.matched_contention_gate(rows)
    assert mismatched["matched_comparison_eligible"] is False
    assert "COHORT_HASH_MISMATCH_OR_MISSING" in mismatched["blockers"]


def test_full_limit_is_hard_and_default_protocol_is_closed() -> None:
    cde.enforce_full_limit(["A", "B", "C", "D"])
    with pytest.raises(cde.ExperimentError, match="at most 4"):
        cde.enforce_full_limit(["A", "B", "C", "D", "E"])
    protocol = cde.protocol_manifest()
    assert protocol["full_default_authorized"] is False
    assert protocol["maximum_full_finalists"] == 4
    assert protocol["tier_order"] == list(cde.TIER_ORDER)


def test_attempt_lock_archives_stale_worker_without_losing_evidence(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "attempt.lock"
    cde.atomic_write_json(
        lock_path,
        {
            "schema": "czr005.g4irsf13.cde_attempt_lock.v1",
            "cache_key": "x" * 64,
            "hostname": socket.gethostname(),
            "pid": 2_147_000_000,
            "started_unix_time": time.time() - 10_000,
        },
    )
    with cde.AttemptLock(
        lock_path,
        cache_key_value="y" * 64,
        stale_seconds=1.0,
    ):
        assert lock_path.is_file()
        assert list(tmp_path.glob("attempt.lock.stale.*"))
    assert not lock_path.exists()
    assert list(tmp_path.glob("attempt.lock.stale.*"))


def _fake_runtime(**kwargs: object) -> dict[str, object]:
    bag_records = kwargs["bag_records"]
    bags = []
    for record in bag_records:
        segment_id, _task_id, release, _deadline, _start, goal, _source = record
        bags.append(
            {
                "segment_id": segment_id,
                "completed": True,
                "release_time": float(release),
                "admitted_time": float(release),
                "finish_time": float(release) + 1.0,
                "final_node": int(goal),
                "failure_reason": "",
            }
        )
    summary = {
        "priority_mode_echo": kwargs["priority_mode"],
        "framework_mode_echo": kwargs["framework_mode"],
        "resource_semantics_echo": kwargs["resource_semantics"],
        "scorer_mode_echo": kwargs["scorer_mode"],
        "pressure_mode_echo": kwargs["pressure_mode"],
        "admission_mode_echo": kwargs["admission_mode"],
        "pibt_mode_echo": kwargs["pibt_mode"],
        "pibt_max_depth_echo": kwargs["pibt_max_depth"],
        "pibt_preference_mode_echo": kwargs["pibt_preference_mode"],
        "selective_credit_contention_threshold_echo": kwargs[
            "selective_credit_contention_threshold"
        ],
        "failed_count": 0,
        "reservation_conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "full_future_routes_stored": 0,
        "unresolved_deadlock_count": 0,
        "priority_teacher_input_count": 0,
        "priority_future_route_input_count": 0,
        "priority_global_scan_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "reservation_depth": 1,
        "max_edges_selected_per_arrive": 1,
        "event_count": len(bags),
        "credit_issued_count": 0,
        "credit_consumed_count": 0,
        "credit_expired_count": 0,
        "credit_local_hold_count": 0,
        "pibt_applicability_count": 0,
        "pibt_attempt_count": 0,
        "pibt_prepare_count": 0,
        "pibt_validate_count": 0,
        "pibt_commit_count": 0,
        "pibt_rollback_count": 0,
        "pibt_backtrack_count": 0,
        "pibt_wait_for_cycle_count": 0,
        "pibt_handoff_count": 0,
        "pibt_max_observed_depth": 0,
        "pibt_state_read_count": 0,
        "pibt_message_count": 0,
        "pibt_decision_latency_seconds": 0.0,
        "pibt_dodge_selected_count": 0,
        "pibt_unique_exit_protection_count": 0,
        "pibt_regret_prior_applied_count": 0,
    }
    binary_path = Path(str(kwargs["expected_binary_path"]))
    return {
        "summary": summary,
        "bags": bags,
        "loaded_cpp_binary_path": str(binary_path.resolve()),
        "loaded_cpp_binary_sha256": cde.file_sha256(binary_path),
        "events": [],
        "decisions": [],
        "pibt_events": [],
        "credit_events": [],
        "hold_attempts": [],
    }


def test_hash_bound_attempt_resumes_from_atomic_complete_pointer(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "czr005_cpp.test.pyd"
    binary.write_bytes(b"real-test-binary-identity")
    archive = tmp_path / "archive"
    motif = cde.load_real_map_motif(ROOT)
    candidate = cde.priority_candidates()[0]
    first = cde.execute_candidate(
        candidate,
        motif,
        executor=_fake_runtime,
        binary=binary,
        search_path=tmp_path,
        qbest=None,
        regret_prior_records=(),
        root=ROOT,
        archive_root=archive,
    )
    assert first["execution_status"] == "EXECUTED"
    assert first["gate_status"] == "PASS"
    assert len(first["cache_key"]) == 64
    assert len(first["result_file_sha256"]) == 64

    second = cde.execute_candidate(
        candidate,
        motif,
        executor=_fake_runtime,
        binary=binary,
        search_path=tmp_path,
        qbest=None,
        regret_prior_records=(),
        root=ROOT,
        archive_root=archive,
    )
    assert second["execution_status"] == "CACHED"
    assert second["attempt_id"] == first["attempt_id"]
    assert second["runtime_deterministic_sha256"] == first[
        "runtime_deterministic_sha256"
    ]


def test_committed_plan_is_truthful_and_valid() -> None:
    validation = cde.validate_committed_outputs(ROOT)
    assert validation["status"] == "PASS"
    assert validation["full_executed_candidate_count"] <= 4
