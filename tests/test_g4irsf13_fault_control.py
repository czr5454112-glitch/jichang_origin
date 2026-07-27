from __future__ import annotations

import json
from pathlib import Path

import pytest

from czr005 import cpp_backend
from scripts.eval import g4irsf13_fault_control as fault
from scripts.eval import g4irsf13_thesis_priority_extraction as thesis


ROOT = Path(__file__).resolve().parents[1]


def _inputs() -> tuple[dict[str, object], list[dict[str, object]]]:
    return fault._load_inputs()


def _require_cpp() -> None:
    try:
        cpp_backend.load_cpp_module(ROOT / "build_g4irsf12" / "python")
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))


def test_thesis_scenarios_map_exactly_to_protected_real_edges() -> None:
    graph, _tasks = _inputs()
    rows = fault.build_mapping_rows(graph)
    assert len(rows) == 16
    assert [row["scenario_id"] for row in rows] == [
        row[0] for row in thesis.THESIS_FAULT_SCENARIOS
    ]
    real_edges = {
        (int(edge["start"]), int(edge["end"]))
        for edge in graph["edges"]
    }
    for row in rows:
        assert row["map_identity_pass"] is True
        assert row["mapping_status"] == "EXACT_ARC_TXT_TO_REAL_MAP2"
        assert all(
            (int(edge["start"]), int(edge["end"])) in real_edges
            for edge in row["map2_edges_json"]
        )
        assert (
            row["paper_outcome_scope"]
            == "THESIS_REPORTED_NOT_G4IRSF13_RESULT"
        )


def test_preventive_criticality_uses_real_tasks_and_declared_offline_scope() -> None:
    graph, tasks = _inputs()
    rows = fault.build_criticality_rows(graph, tasks)
    assert len(rows) == 8
    assert {int(row["maintenance_rank"]) for row in rows} == set(range(1, 9))
    assert all(row["real_map_edge_pass"] is True for row in rows)
    assert all(
        row["score_semantics"]
        == "offline_reachability_and_topology_ranking_only"
        for row in rows
    )
    # The six legacy source arcs are real weak-projection bridges and removing
    # each one disconnects actual protected task segments.
    for row in rows:
        if int(row["arc_id"]) <= 6:
            assert row["weak_projection_bridge"] is True
            assert int(row["actual_task_segments_losing_reachability"]) > 0
        else:
            assert int(row["alternate_outgoing_edge_count"]) == 1


def test_probe_manifest_contains_formal_g0_g9_and_explicit_v3_blocker() -> None:
    specs = fault.probe_specs()
    case_ids = {spec.case_id for spec in specs}
    assert {
        "G0_no_fault",
        "G1_physical_shield_only",
        "G2_ddi_local_policy",
        "G3_ddi_plus_p2",
        "G4_v3_fault_aware_plus_p2",
        "G5_delayed_message",
        "G6_dropped_message",
        "G7_repair_reopen",
        "G8_multi_fault",
        "G9_cut_isolation",
    } <= case_ids
    v3 = next(
        spec for spec in specs if spec.case_id == "G4_v3_fault_aware_plus_p2"
    )
    assert v3.execution_status == "NOT_RUN"
    assert v3.blocker == (
        "FRESH_HOLDOUT_OFFLINE_FAIL_RUNTIME_ACTIVATION_FORBIDDEN"
    )


def test_probe_task_is_an_unmodified_protected_row() -> None:
    _graph, tasks = _inputs()
    selected = fault._select_probe_task(tasks, goal=47)
    protected = next(
        row
        for row in tasks
        if row["segment_id"] == selected["segment_id"]
    )
    assert selected == protected
    assert selected["start"] == 0
    assert selected["goal"] == 47
    assert selected["segment_id"] == "8:storage_in"


def test_fault_windows_are_dynamic_overlays_not_map_mutations() -> None:
    graph, tasks = _inputs()
    before = json.dumps(graph, sort_keys=True)
    task = fault._select_probe_task(tasks, goal=47)
    spec = next(
        row for row in fault.probe_specs() if row.case_id == "G8_multi_fault"
    )
    windows = fault._fault_windows(spec, task)
    assert {(row[0], row[1]) for row in windows} == {(6, 8), (6, 12)}
    assert all(row[2] < row[3] for row in windows)
    cut = next(
        row for row in fault.probe_specs() if row.case_id == "G9_cut_isolation"
    )
    cut_window = fault._fault_windows(cut, task)
    assert cut_window[0][2] == pytest.approx(float(task["pass_time"]))
    assert json.dumps(graph, sort_keys=True) == before


def test_real_runtime_fault_ab_is_informative_safe_and_discriminating() -> None:
    _require_cpp()
    graph, tasks = _inputs()
    rows = fault.execute_study(
        graph,
        tasks,
        search_path=ROOT / "build_g4irsf12" / "python",
    )
    by_case = {row["case_id"]: row for row in rows}
    executed = [
        row for row in rows if row["execution_status"] == "EXECUTED"
    ]
    assert executed
    for row in executed:
        assert row["completed"] is True
        assert row["gate_status"] == "PASS"
        assert row["unsafe_entry_count"] == 0
        assert row["reservation_conflicts"] == 0
        assert row["runtime_full_astar_calls"] == 0
        assert row["global_reservation_scan_count"] == 0
        assert row["future_routes_stored"] == 0
        assert row["unresolved_deadlock_count"] == 0
        assert row["reservation_depth"] == 1
        assert row["binary_sha256"] == fault.FROZEN_BINARY_SHA256
        assert row["frozen_binary_match"] is True
        assert row["physical_interlock_mode"] == (
            "ALWAYS_ON_NOT_POLICY_CONFIGURABLE"
        )
        assert row["physical_fault_generation_pass"] is True
        assert row["physical_fault_event_count"] == len(
            row["fault_edges_json"]
        )
        assert row["physical_repair_event_count"] == len(
            row["fault_edges_json"]
        )
        assert row["repaired_task_reentry_boost_clear_pass"] is True
    for case_id in (
        "G2_ddi_local_policy",
        "G3_ddi_plus_p2",
        "G7_repair_reopen",
    ):
        assert by_case[case_id]["causal_promotion_status"] == (
            "MATCHED_PHYSICAL_SHIELD_POLICY_CONTRIBUTION_PASS"
        )
        assert (
            float(by_case[case_id]["delay_delta_vs_comparator_seconds"])
            < 0.0
        )
        comparator = by_case[by_case[case_id]["comparator_id"]]
        assert by_case[case_id]["physical_interlock_mode"] == comparator[
            "physical_interlock_mode"
        ]
        assert by_case[case_id][
            "physical_fault_generation_sequence_json"
        ] == comparator["physical_fault_generation_sequence_json"]
    assert by_case["G8_multi_fault"]["causal_promotion_status"] == (
        "NO_POSITIVE_POLICY_CONTRIBUTION_DEMONSTRATED"
    )
    assert by_case["G9_cut_isolation"]["causal_promotion_status"] == (
        "NO_LOCAL_POLICY_ACTION_OBSERVED_PHYSICAL_FALLBACK_ONLY"
    )
    assert not str(by_case["G6_dropped_message"][
        "causal_promotion_status"
    ]).endswith("CONTRIBUTION_PASS")
    assert by_case["G6_dropped_message"][
        "fault_notification_drop_count"
    ] == 2
    for case_id in (
        "G9_cut_isolation",
        "G9_control_physical_shield_only",
    ):
        assert (
            by_case[case_id]["credit_physical_fault_rejection_count"]
            > 0
        )
        assert by_case[case_id]["credit_physical_interlock_bypass"] is False
        assert by_case[case_id]["credit_containment_status"] == (
            "FAULTED_EDGE_CREDIT_REJECTED_BY_PHYSICAL_INTERLOCK"
        )
    assert all(
        int(row["pibt_fault_batch_cancel_count"]) >= 0
        and row["pibt_containment_status"]
        in {
            "FAULT_GENERATION_BATCH_CANCEL_OBSERVED",
            "NO_STALE_BATCH_OBSERVED",
            "NO_PIBT_BATCH_IN_SINGLE_BAG_PROBE",
        }
        for row in executed
    )


def test_fault_artifacts_are_deterministic_and_policy_self_hashes() -> None:
    _require_cpp()
    search = ROOT / "build_g4irsf12" / "python"
    first = fault.build_outputs(search_path=search)
    second = fault.build_outputs(search_path=search)
    assert first == second
    bundle = json.loads(first[fault.POLICY_PATH])
    self_sha = bundle.pop("self_sha256")
    assert self_sha == fault._canonical_sha256(bundle)
    assert bundle["physical_interlock"] == (
        "ALWAYS_ON_NOT_POLICY_CONFIGURABLE"
    )
    assert bundle["v3_fault_aware_status"] == (
        "NOT_RUN_FRESH_HOLDOUT_OFFLINE_FAIL_"
        "RUNTIME_ACTIVATION_FORBIDDEN"
    )
    assert bundle["frozen_binary_sha256"] == fault.FROZEN_BINARY_SHA256
    assert bundle["frozen_binary_match_pass"] is True
    assert bundle["physical_generation_audit_pass"] is True
    assert bundle["unsafe_entry_count"] == 0
    assert (
        bundle["containment_evidence"][
            "credit_physical_fault_rejection_count"
        ]
        > 0
    )
    assert bundle["containment_evidence"][
        "credit_physical_interlock_bypass"
    ] is False
