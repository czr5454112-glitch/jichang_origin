from pathlib import Path

from scripts.eval import audit_cie_fixed_horizon_merge_boundary as audit


def _payload(*, false_gate: str | None = "merge_grant_active_bijection"):
    gates = {
        "terminal_partition": True,
        "exact_segment_identity": True,
        "merge_grant_active_bijection": false_gate
        != "merge_grant_active_bijection",
        "reservation_conflicts_zero": false_gate != "reservation_conflicts_zero",
    }
    return {
        "map": "nanning",
        "status": "FAILED_INTEGRITY" if false_gate else "COMPLETE",
        "algorithm": {"arm": "FULL_MINUS_Q"},
        "provenance": {
            "binary_sha256": "b" * 64,
            "canonical_workload_sha256": "w" * 64,
        },
        "ablation_contract": {"base_full_s4_request_sha256": "r" * 64},
        "execution_integrity": {"pass": false_gate is None, "gates": gates},
        "runtime": {
            "native_summary": {
                "requested_count": 87_206,
                "completed_count": 86_118,
                "failed_count": 1_088,
                "event_count": 15_035_166,
                "decision_count": 1_175_917,
                "time_limit_reached": True,
                "event_limit_reached": False,
                "final_active_bag_count": 0,
                "merge_grant_final_active_unconsumed": 43,
                "merge_grant_outstanding_request_count": 2,
                "merge_grant_conservation_holds": True,
                "merge_grant_active_bijection_holds": false_gate
                != "merge_grant_active_bijection",
                "merge_grant_exact_slot_no_future_shift": True,
                "reservation_conflicts": 0,
                "physical_fault_edge_entry_violation_count": 0,
            }
        },
    }


def test_exact_sole_gate_fixed_horizon_signature_is_classified():
    row = audit.audit_payload(_payload(), Path("nanning_2x.json"))
    assert row["first_false_gate"] == "merge_grant_active_bijection"
    assert row["false_gates"] == "merge_grant_active_bijection"
    assert row["diagnosis"] == audit.CROSS_BOUNDARY_SIGNATURE


def test_second_failed_gate_is_not_relabelled_as_boundary_signature():
    row = audit.audit_payload(
        _payload(false_gate="reservation_conflicts_zero"),
        Path("nanning_2x.json"),
    )
    assert row["diagnosis"] == audit.OTHER_FAILURE


def test_passing_artifact_is_not_reported_as_a_failure():
    row = audit.audit_payload(_payload(false_gate=None), Path("nanning_2x.json"))
    assert row["first_false_gate"] == "NA"
    assert row["diagnosis"] == audit.NO_FAILURE


def test_same_outcome_boundary_failure_to_pass_is_telemetry_repair():
    before = audit.audit_payload(_payload(), Path("before/nanning_2x.json"))
    after = audit.audit_payload(
        _payload(false_gate=None), Path("after/nanning_2x.json")
    )
    before["arm"] = "FULL_S4"
    after["arm"] = "FULL_S4"
    compared = audit.compare_repair_rows([before], [after], "baseline")
    assert len(compared) == 1
    assert compared[0]["outcome_identity_match"] is True
    assert compared[0]["current_identity_matches_full_s4"] is True
    assert compared[0]["repair_status"] == audit.REPAIRED


def test_current_identity_mismatch_is_review_required():
    full_before = audit.audit_payload(
        _payload(false_gate=None), Path("before/full.json")
    )
    full_after = audit.audit_payload(
        _payload(false_gate=None), Path("after/full.json")
    )
    full_before["arm"] = "FULL_S4"
    full_after["arm"] = "FULL_S4"

    arm_before = audit.audit_payload(
        _payload(false_gate=None), Path("before/arm.json")
    )
    arm_after_payload = _payload(false_gate=None)
    arm_after_payload["provenance"]["binary_sha256"] = "c" * 64
    arm_after = audit.audit_payload(arm_after_payload, Path("after/arm.json"))

    compared = audit.compare_repair_rows(
        [full_before, arm_before], [full_after, arm_after], "baseline"
    )
    arm = next(row for row in compared if row["arm"] == "FULL_MINUS_Q")
    assert arm["current_binary_matches_full_s4"] is False
    assert arm["current_identity_matches_full_s4"] is False
    assert arm["repair_status"] == audit.REVIEW
