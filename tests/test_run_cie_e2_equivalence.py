from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import run_cie_e2_equivalence as e2


def _source_rows() -> tuple[dict[str, Any], ...]:
    return (
        {"segment_id": "seg-a", "task_id": 1, "goal": 3},
        {"segment_id": "seg-b", "task_id": 2, "goal": 4},
    )


def _base_request(binary: Path) -> dict[str, Any]:
    return {
        "node_records": [{"node": 1}, {"node": 2}],
        "edge_records": [{"source": 1, "target": 2}],
        "heuristic_time": [[0.0, 1.0], [1.0, 0.0]],
        "bag_records": list(_source_rows()),
        "scenario": "source",
        "expected_binary_path": str(binary.resolve()),
        "scorer_mode": "S4_queue_aware_rule_only",
        "s4_score_component_mask": 15,
        "merge_grant_rule": "M3",
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "enable_s4_local_potential_descent_guard": True,
        "enable_s4_direct_neighbor_merge_calendar_visibility": True,
        "complete_on_goal_arrival": True,
        "enable_cie_component_activation": True,
        "max_simulation_time": e2.activation.FIXED_END_EPOCH,
        "max_events": e2.activation.MAX_EVENTS,
        "g4irsf20_event_hotpath_policy": "E2",
        "trace_limit": 0,
        "event_trace_limit": 0,
        "summary_only": False,
    }


def _patch_request_builder(monkeypatch: pytest.MonkeyPatch, binary: Path) -> None:
    def fake_prepare_runtime_request(**_kwargs: Any):
        return (
            _source_rows(),
            _base_request(binary),
            {
                "potential_contract": {
                    "mode": "SERVICE_AWARE_STATIC_LOCAL_POTENTIAL"
                }
            },
        )

    monkeypatch.setattr(
        e2.activation, "prepare_runtime_request", fake_prepare_runtime_request
    )


def _bag(
    segment_id: str, task_id: int, goal: int, finish: float
) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "task_id": task_id,
        "completed": True,
        "final_node": goal,
        "arrival_time": 10.0 + task_id,
        "release_time": 11.0 + task_id,
        "admitted_time": 12.0 + task_id,
        "finish_time": finish,
        "goal_completion_time_seconds": finish - 10.0 - task_id,
        "failure_reason": "",
        "decision_count": 1 if task_id == 2 else 2,
        "retry_count": 0,
        "loop_count": 0,
    }


def _trace(
    *,
    ordinal: int,
    segment_id: str,
    task_id: int,
    event_time: float,
    current: int,
    goal: int,
    selected: int | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "task_id": task_id,
        "event_time": event_time,
        "current_node": current,
        "goal_node": goal,
        "selected_next": selected,
        "decision_source": "S4",
        "rule_reason": reason,
        "metadata": {"decision_ordinal": ordinal},
    }


def _payload(request: dict[str, Any]) -> dict[str, Any]:
    policy = request["g4irsf20_event_hotpath_policy"]
    summary = {
        "safe_execution_pass": True,
        "completed_count": 2,
        "failed_count": 0,
        "declared_max_simulation_time": e2.activation.FIXED_END_EPOCH,
        "declared_max_events": e2.activation.MAX_EVENTS,
        "event_limit_reached": False,
        "loaded_cpp_binary_path": request["expected_binary_path"],
        "loaded_cpp_binary_sha256": hashlib.sha256(
            Path(request["expected_binary_path"]).read_bytes()
        ).hexdigest(),
        "scorer_mode_echo": "S4_queue_aware_rule_only",
        "merge_grant_rule": "M3",
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "physical_fault_edge_entry_violation_count": 0,
        "reservation_conflicts": 0,
        "merge_grant_conservation_holds": True,
        "merge_grant_active_bijection_holds": True,
        "fault_event_count": 0,
        "repair_event_count": 0,
        "trace_shard_count": 1,
        "trace_shard_index": 0,
        "trace_limit": e2.TRACE_LIMIT,
        "decision_trace_seen_count": 3,
        "decision_trace_shard_seen_count": 3,
        "decision_trace_stored_count": 2,
        "hold_trace_stored_count": 1,
        "decision_trace_truncated": False,
        "event_count": 80 if policy == "E2" else 100,
        "decision_count": 2,
        "congestion_beacon_update_event_count": 20 if policy == "E2" else 40,
        "bag_release_event_count": 2,
        "arrive_junction_event_count": 2,
        "junction_service_complete_event_count": 2,
        "edge_enter_event_count": 2,
        "edge_exit_event_count": 2,
        "stale_arbitration_event_count": 3 if policy == "E2" else 4,
        "merge_grant_stale_arbitration_count": 2 if policy == "E2" else 3,
        "merge_grant_stale_wakeup_count": 1 if policy == "E2" else 2,
        "merge_grant_wakeup_scheduled_count": 12 if policy == "E2" else 10,
        "merge_grant_wakeup_coalesced_count": 5 if policy == "E2" else 4,
        "merge_grant_duplicate_wakeup_prevented_count": (
            5 if policy == "E2" else 4
        ),
        "max_junction_queue_length": 7,
        "max_source_queue_length": 9,
    }
    if policy == "E2":
        summary.update(
            g4irsf20_event_hotpath_policy="E2",
            g4irsf20_redundant_beacon_suppressed_count=20,
            g4irsf20_same_state_beacon_suppressed_count=5,
        )
    return {
        "summary": summary,
        "bags": [_bag("seg-a", 1, 3, 30.0), _bag("seg-b", 2, 4, 40.0)],
        "decisions": [
            _trace(
                ordinal=2,
                segment_id="seg-a",
                task_id=1,
                event_time=15.0,
                current=1,
                goal=3,
                selected=3,
                reason="move",
            ),
            _trace(
                ordinal=3,
                segment_id="seg-b",
                task_id=2,
                event_time=16.0,
                current=2,
                goal=4,
                selected=4,
                reason="move",
            ),
        ],
        "hold_attempts": [
            _trace(
                ordinal=1,
                segment_id="seg-a",
                task_id=1,
                event_time=14.0,
                current=1,
                goal=3,
                selected=None,
                reason="corridor_busy",
            )
        ],
    }


def _files(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    canonical = tmp_path / "canonical.jsonl"
    canonical.write_text("{}\n", encoding="utf-8")
    binary = tmp_path / "czr005_cpp.pyd"
    binary.write_bytes(b"binary")
    return canonical, binary


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    policy: str,
    *,
    payload_mutator=None,
    rss=(123456, "TEST_PEAK_RSS"),
) -> dict[str, Any]:
    canonical, binary = _files(tmp_path)
    _patch_request_builder(monkeypatch, binary)

    def executor(**request: Any):
        payload = _payload(request)
        if payload_mutator is not None:
            payload_mutator(payload)
        return payload

    return e2.execute_run(
        map_name="map2",
        policy=policy,
        canonical_path=canonical,
        binary=binary,
        executor=executor,
        rss_reader=lambda: rss,
    )


def test_request_pair_changes_only_existing_hotpath_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canonical, binary = _files(tmp_path)
    _patch_request_builder(monkeypatch, binary)
    _rows0, request0, contract0 = e2.prepare_e2_request(
        map_name="map2", policy="E0", canonical_path=canonical, binary=binary
    )
    _rows2, request2, contract2 = e2.prepare_e2_request(
        map_name="map2", policy="E2", canonical_path=canonical, binary=binary
    )
    differing = {key for key in request0 if request0.get(key) != request2.get(key)}
    assert differing == {"g4irsf20_event_hotpath_policy"}
    assert e2._json_sha256(e2._normalized_pair_request(request0)) == e2._json_sha256(
        e2._normalized_pair_request(request2)
    )
    assert request0["trace_limit"] == e2.activation.MAX_EVENTS
    assert request0["trace_shard_count"] == 1
    assert request0["event_trace_limit"] == 0
    assert request0["enable_cie_component_activation"] is False
    assert contract0["identity_gates"]["complete_decision_trace_budget"] is True
    assert contract2["identity_gates"]["service_aware_potential"] is True


def test_dry_run_never_calls_executor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canonical, binary = _files(tmp_path)
    _patch_request_builder(monkeypatch, binary)

    def forbidden(**_request: Any):
        raise AssertionError("executor must not be called")

    result = e2.execute_run(
        map_name="map2",
        policy="E0",
        canonical_path=canonical,
        binary=binary,
        dry_run=True,
        executor=forbidden,
    )
    assert result["status"] == "READY_CIE_E2_EQUIVALENCE_DRY_RUN"
    assert result["native_execution_started"] is False


def test_run_captures_complete_trace_terminal_times_safety_and_compute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run(monkeypatch, tmp_path, "E2")
    assert result["status"] == "COMPLETE_TRACE_CAPTURE"
    assert result["execution_integrity"]["safety"]["pass"] is True
    assert result["full_action_attempt_trace"]["complete_capture"] is True
    assert result["full_action_attempt_trace"]["stored_hold_count"] == 1
    assert result["per_segment_terminal_timing"][0]["finish_time"] == 30.0
    assert result["runtime_compute"]["event_count"] == 80
    assert result["runtime_compute"]["physical_causal_event_count_total"] == 10
    assert result["runtime_compute"]["stale_event_count_total"] == 6
    assert result["runtime_compute"]["merge_grant_wakeup_scheduled_count"] == 12
    assert result["runtime_compute"]["merge_grant_wakeup_coalesced_count"] == 5
    assert (
        result["runtime_compute"]["merge_grant_duplicate_wakeup_prevented_count"]
        == 5
    )
    assert result["runtime_compute"]["peak_rss_bytes"] == 123456
    assert result["runtime_compute"]["event_queue_peak"] == "N/M"
    assert (
        result["runtime_compute"]["event_queue_peak_not_measured_reason"]
        == "CURRENT_PUBLIC_RESPONSE_DOES_NOT_EXPOSE_EVENT_QUEUE_PEAK"
    )


def test_aggregate_passes_only_for_matching_complete_physical_pair(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    e0 = _run(monkeypatch, tmp_path, "E0")
    e2_run = _run(monkeypatch, tmp_path, "E2")
    aggregate = e2.aggregate_results([e0, e2_run], expected_maps=("map2",))
    assert aggregate["status"] == "COMPLETE_STRICT_PHYSICAL_EQUIVALENCE"
    pair = aggregate["pairs"][0]
    assert pair["strict_physical_equivalence"] is True
    assert pair["compute_comparison"]["event_count"]["E2_reduction_fraction"] == pytest.approx(
        0.2
    )
    assert pair["compute_comparison"]["event_queue_peak"]["E2_minus_E0"] == "N/M"
    assert pair["gates"]["physical_causal_event_counts_equal"] is True
    assert pair["physical_causal_event_comparison"]["pass"] is True
    assert pair["compute_comparison"]["stale_event_count_total"][
        "E2_minus_E0"
    ] == -3.0
    assert aggregate["rows"][0]["redundant_beacon_suppressed_count"] == 0
    assert aggregate["rows"][0]["same_state_beacon_suppressed_count"] == 0
    assert aggregate["rows"][0]["beacon_suppression_count_semantics"] == (
        "DEFINITIONALLY_ZERO_UNDER_E0_POLICY;NATIVE_BINDING_OMITS_COUNTERS"
    )


def test_physical_event_count_mismatch_fails_equivalence_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    e0 = _run(monkeypatch, tmp_path, "E0")
    e2_run = deepcopy(_run(monkeypatch, tmp_path, "E2"))
    e2_run["runtime_compute"]["edge_enter_event_count"] += 1

    aggregate = e2.aggregate_results([e0, e2_run], expected_maps=("map2",))

    assert aggregate["status"] == "PHYSICAL_EQUIVALENCE_FAILED"
    pair = aggregate["pairs"][0]
    assert pair["gates"]["physical_causal_event_counts_equal"] is False
    assert "edge_enter_event_count" in pair[
        "physical_causal_event_comparison"
    ]["mismatched_fields"]


def test_stale_and_wakeup_differences_are_compute_diagnostics_not_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    e0 = _run(monkeypatch, tmp_path, "E0")
    e2_run = deepcopy(_run(monkeypatch, tmp_path, "E2"))
    e2_run["runtime_compute"]["stale_arbitration_event_count"] += 100
    e2_run["runtime_compute"]["stale_event_count_total"] += 100
    e2_run["runtime_compute"]["merge_grant_wakeup_scheduled_count"] += 100

    aggregate = e2.aggregate_results([e0, e2_run], expected_maps=("map2",))

    assert aggregate["status"] == "COMPLETE_STRICT_PHYSICAL_EQUIVALENCE"
    pair = aggregate["pairs"][0]
    assert pair["strict_physical_equivalence"] is True
    assert pair["compute_comparison"]["stale_event_count_total"][
        "E2_minus_E0"
    ] == 97.0


def test_report_presents_physical_stale_wakeup_and_e0_zero_semantics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    aggregate = e2.aggregate_results(
        [_run(monkeypatch, tmp_path, "E0"), _run(monkeypatch, tmp_path, "E2")],
        expected_maps=("map2",),
    )

    report = e2._report_text(aggregate)

    assert "Physical-causal event count audit" in report
    assert "Stale arbitration" in report
    assert "Wakeup coalesced" in report
    assert "definitionally zero" in report
    assert "not physical-equivalence gates" in report


@pytest.mark.parametrize(
    "field",
    ["git_commit", "binary_sha256", "canonical_sha256"],
)
def test_aggregate_rejects_cross_identity_pair(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str
) -> None:
    e0 = _run(monkeypatch, tmp_path, "E0")
    e2_run = deepcopy(_run(monkeypatch, tmp_path, "E2"))
    e2_run["provenance"][field] = "f" * 64

    aggregate = e2.aggregate_results([e0, e2_run], expected_maps=("map2",))

    assert aggregate["status"] == "PHYSICAL_EQUIVALENCE_FAILED"
    pair = aggregate["pairs"][0]
    assert pair["strict_physical_equivalence"] is False
    assert f"same_{field}" in pair["blockers"]


def test_loaded_binary_content_mismatch_fails_single_run_integrity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def change_loaded_sha(payload: dict[str, Any]) -> None:
        payload["summary"]["loaded_cpp_binary_sha256"] = "0" * 64

    result = _run(
        monkeypatch, tmp_path, "E2", payload_mutator=change_loaded_sha
    )

    assert result["status"] == "FAILED_EXECUTION_INTEGRITY"
    assert result["execution_integrity"]["identity_gates"][
        "loaded_expected_binary_sha256"
    ] is False


@pytest.mark.parametrize("change", ["selected_next", "completion_time"])
def test_aggregate_fails_on_physical_or_completion_time_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    e0 = _run(monkeypatch, tmp_path, "E0")
    e2_run = _run(monkeypatch, tmp_path, "E2")
    changed = deepcopy(e2_run)
    if change == "selected_next":
        changed["full_action_attempt_trace"]["per_segment"][0][
            "physical_sequence_sha256"
        ] = "changed"
    else:
        changed["per_segment_terminal_timing"][0]["finish_time"] += 0.01
    aggregate = e2.aggregate_results([e0, changed], expected_maps=("map2",))
    assert aggregate["status"] == "PHYSICAL_EQUIVALENCE_FAILED"
    assert aggregate["pairs"][0]["strict_physical_equivalence"] is False


def test_truncated_trace_is_an_explicit_blocker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def truncate(payload: dict[str, Any]) -> None:
        payload["summary"]["decision_trace_truncated"] = True

    result = _run(
        monkeypatch, tmp_path, "E2", payload_mutator=truncate
    )
    assert result["status"] == "BLOCKED_INSUFFICIENT_TRACE"
    assert "TRACE_GATE_FAILED:decision_trace_not_truncated" in result["blockers"]


def test_missing_rss_is_not_rewritten_as_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _run(
        monkeypatch,
        tmp_path,
        "E2",
        rss=("N/M", "WINDOWS_PEAK_RSS_READER_UNAVAILABLE"),
    )
    assert result["status"] == "COMPLETE_TRACE_CAPTURE"
    assert result["runtime_compute"]["peak_rss_bytes"] == "N/M"
    assert result["runtime_compute"]["peak_rss_method"] == (
        "WINDOWS_PEAK_RSS_READER_UNAVAILABLE"
    )


def test_missing_safety_field_is_nm_and_cannot_pass_integrity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def remove_safety(payload: dict[str, Any]) -> None:
        payload["summary"].pop("reservation_conflicts")

    result = _run(
        monkeypatch, tmp_path, "E2", payload_mutator=remove_safety
    )
    assert result["status"] == "FAILED_EXECUTION_INTEGRITY"
    safety = result["execution_integrity"]["safety"]
    assert safety["measurements"]["reservation_conflicts"] == "N/M"
    assert "reservation_conflicts" in safety["not_measured"]
