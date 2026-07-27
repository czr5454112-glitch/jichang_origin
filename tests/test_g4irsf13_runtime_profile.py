from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

import pytest

from czr005 import cpp_backend
from scripts.eval import g4irsf13_runtime_profile as profile


ROOT = Path(__file__).resolve().parents[1]


def _require_cpp() -> None:
    try:
        cpp_backend.load_cpp_module(ROOT / "build_g4irsf12" / "python")
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))


def test_profile_uses_frozen_f2_case_and_append_only_controls() -> None:
    case = profile._f2_case()
    assert case.candidate_id == "J_F2"
    assert case.runtime_controls["reservation_depth"] == 1
    assert case.runtime_controls["scorer_mode"] == (
        "S1_frozen_g4e_legal_local_adapter"
    )
    controls = profile._filtered_controls()
    assert "reservation_depth" not in controls
    assert controls["pibt_mode"] == "P2"
    assert controls["scorer_mode"] == (
        "S1_frozen_g4e_legal_local_adapter"
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows process API fallback")
def test_peak_rss_has_stdlib_windows_fallback(monkeypatch) -> None:
    assert profile._windows_peak_working_set_bytes() > 0
    monkeypatch.setitem(sys.modules, "psutil", None)
    assert profile._rss_peak_bytes() > 0


def test_real_map_144_profile_repeats_are_algorithm_equivalent() -> None:
    _require_cpp()
    repeats, payload = profile.execute_repeats(
        size_segments=144,
        repeats=2,
        search_path=ROOT / "build_g4irsf12" / "python",
    )
    assert len(repeats) == 2
    assert len({row["algorithm_projection_sha256"] for row in repeats}) == 1
    assert len({row["binary_sha256"] for row in repeats}) == 1
    assert all(row["hard_gate_pass"] is True for row in repeats)
    assert all(row["completed_count"] == 144 for row in repeats)
    assert all(row["equivalent_to_repeat_0"] is True for row in repeats)
    rows = profile.build_stage_rows(repeats, payload)
    by_stage = {row["stage"]: row for row in rows}
    assert by_stage["native_event_runtime_total"]["mean_seconds"] > 0.0
    assert by_stage["event_heap"]["measurement_status"] == (
        "COUNTER_ONLY_NATIVE_TIMER_UNAVAILABLE"
    )
    assert by_stage["trace_serialization"]["measurement_status"] == (
        "NOT_MEASURED_SUMMARY_ONLY_PROFILE"
    )
    assert by_stage["input_output"]["measurement_status"] == (
        "NOT_MEASURED_PRELOADED_INPUT_SUMMARY_ONLY"
    )
    assert by_stage["fault_overlay"]["operation_count"] == 0


def test_profile_report_does_not_turn_counter_rows_into_time_claims() -> None:
    repeats = [
        {
            "size_segments": 144,
            "python_end_to_end_wall_seconds": 1.0,
            "native_runtime_seconds": 0.8,
            "pybind_wrapper_residual_seconds": 0.2,
            "decision_latency_us_p50": 1.0,
            "decision_latency_us_p95": 2.0,
            "decision_latency_us_p99": 3.0,
            "process_peak_rss_bytes": 123,
            "equivalent_to_repeat_0": True,
            "binary_equivalent_to_repeat_0": True,
            "hard_gate_pass": True,
        }
    ]
    stages = [
        {
            "stage": "event_heap",
            "measurement_status": "COUNTER_ONLY_NATIVE_TIMER_UNAVAILABLE",
        }
    ]
    decision = profile.build_kl_unlock_decision(ROOT)
    report = profile.build_report(repeats, stages, decision).decode("utf-8")
    assert "PROFILE_COMPLETE_NO_OPTIMIZATION_APPLIED" in report
    assert "event_heap" in report
    assert "no fabricated percentage" in report
    assert "Trace serialization and file I/O" in report
    assert "G4J: `CLOSED`" in report
    assert "Phase K: `UNKNOWN/CLOSED`" in report
    assert "Phase L: `NOT_RUN`" in report


def test_kl_decision_binds_canonical_sources_and_fails_closed() -> None:
    decision = profile.build_kl_unlock_decision(ROOT)
    validation = profile.validate_kl_unlock_decision(decision, root=ROOT)
    by_gate = {row["gate_id"]: row["passed"] for row in decision["gates"]}
    assert by_gate == {
        "strict_v2_win": False,
        "v3_contribution": False,
        "fault_discriminating": True,
        "numeric_demand_calibration": False,
        "original_task_generation_audit": True,
    }
    assert validation["gate_count"] == 5
    assert validation["source_count"] == 4
    assert decision["all_five_gates_pass"] is False
    assert decision["g4j_status"] == "CLOSED"
    assert decision["phase_k_status"] == "UNKNOWN/CLOSED"
    assert decision["phase_l_status"] == "NOT_RUN"
    assert decision["scale_execution_count"] == 0
    projection = dict(decision)
    self_sha = projection.pop("self_sha256")
    assert self_sha == profile._sha256(projection)
    bindings = decision["source_artifacts"]
    assert all(
        len(row["canonical_sha256"]) == 64 for row in bindings.values()
    )
    assert all(
        row["self_hash_valid"] is True
        for key, row in bindings.items()
        if key != "demand_calibration"
    )
    assert bindings["demand_calibration"]["self_hash_valid"] == (
        "NOT_APPLICABLE"
    )


def test_kl_validator_rejects_tampered_gate_even_with_new_self_hash() -> None:
    decision = profile.build_kl_unlock_decision(ROOT)
    tampered = copy.deepcopy(decision)
    tampered["gates"][0]["passed"] = True
    projection = dict(tampered)
    projection.pop("self_sha256")
    tampered["self_sha256"] = profile._sha256(projection)
    with pytest.raises(
        profile.ProfileError,
        match="differs from recomputed source gates",
    ):
        profile.validate_kl_unlock_decision(tampered, root=ROOT)


def test_kl_canonical_json_is_byte_deterministic() -> None:
    first = profile.build_kl_unlock_decision(ROOT)
    second = profile.build_kl_unlock_decision(ROOT)
    assert first == second
    encoded = profile._canonical_bytes(first)
    assert json.loads(encoded) == first
