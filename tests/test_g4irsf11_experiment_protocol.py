from __future__ import annotations

from scripts.eval.g4irsf11_experiment_protocol import (
    CAPACITY_SLO,
    EXTENSION_PROTOCOL_SCHEMA,
    EXTENSION_PROTOCOL_VERSION,
    PROTOCOL_SCHEMA,
    PROTOCOL_VERSION,
    fault_windows,
    formal_cases,
    protocol_manifest,
)
from scripts.eval.g4irsf11_workloads import FORMAL_WORKLOAD_MODES, FRONTIER_SCALES


def test_formal_frontier_is_complete_and_never_pooled() -> None:
    cases = formal_cases()
    frontier = [case for case in cases if case.category == "capacity_frontier"]
    assert len(frontier) == len(FORMAL_WORKLOAD_MODES) * len(FRONTIER_SCALES)
    assert {(case.workload_mode, case.scale) for case in frontier} == {
        (mode, scale) for mode in FORMAL_WORKLOAD_MODES for scale in FRONTIER_SCALES
    }
    assert len({case.case_id for case in cases}) == len(cases)


def test_size_ladder_contains_exact_paper_full_boundary() -> None:
    sizes = [case for case in formal_cases() if case.category == "size_ladder"]
    assert [case.segment_limit for case in sizes] == [144, 512, 1024, None]
    assert sizes[-1].case_id == "real_map_paper_full"


def test_trace_collection_is_explicitly_bounded_not_full_evidence() -> None:
    traces = [case for case in formal_cases() if case.category == "decision_trace"]
    assert traces
    assert all(case.segment_limit == 1024 and case.trace_complete for case in traces)
    assert all("not full-run evidence" in case.notes for case in traces)


def test_fault_profiles_are_temporal_repair_and_sensor_loss_is_explicit() -> None:
    delayed = fault_windows("single_delayed_30s", minimum_release=100.0, maximum_release=1100.0)
    assert delayed[0]["repair_time"] > delayed[0]["fault_time"]
    assert delayed[0]["message_delay"] == 30.0
    loss = fault_windows("sensor_loss", minimum_release=100.0, maximum_release=1100.0)
    assert loss[0]["drop_notification"] is True
    repeated = fault_windows("repeated_delayed_5s", minimum_release=100.0, maximum_release=1100.0)
    assert len(repeated) == 2
    assert repeated[0]["repair_time"] < repeated[1]["fault_time"]
    policy_off = next(case for case in formal_cases() if case.case_id == "fault_fault_policy_off")
    assert policy_off.enable_fault_policy is False
    assert policy_off.enable_deadlock_escape is True
    assert policy_off.as_dict()["enable_fault_policy"] is False
    assert "advertised-fault policy disabled" in policy_off.notes
    assert "physical interlock remains" in policy_off.notes


def test_protocol_freezes_independent_safety_queue_and_service_thresholds() -> None:
    manifest = protocol_manifest()
    assert manifest["capacity_slo"] == CAPACITY_SLO
    assert "no pooled" in manifest["claim_boundaries"]["load_modes"]
    assert CAPACITY_SLO["max_p99_service_seconds"] >= CAPACITY_SLO["max_p95_service_seconds"]
    assert PROTOCOL_SCHEMA.endswith(".v4")
    assert PROTOCOL_VERSION.endswith("-v4")
    assert EXTENSION_PROTOCOL_SCHEMA.endswith(".v3")
    assert EXTENSION_PROTOCOL_VERSION.endswith("-v3")
