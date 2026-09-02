from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.eval import run_cie_fault_specials as runner


def _rows() -> tuple[dict[str, object], ...]:
    return (
        {
            "segment_id": "1:0",
            "task_id": 1,
            "original_entry_time": 0.0,
            "pass_time": 0.0,
            "std": 10.0,
            "start": 0,
            "goal": 1,
        },
        {
            "segment_id": "2:0",
            "task_id": 2,
            "original_entry_time": 1.0,
            "pass_time": 1.0,
            "std": 10.0,
            "start": 2,
            "goal": 1,
        },
    )


def _base_request(binary: Path) -> dict[str, object]:
    return {
        "scenario": "cie_fault_special_map2_single_4_1x",
        "node_records": [[0, 0, 0.2], [1, 0, 0.2], [2, 0, 0.2]],
        "edge_records": [[0, 1, 1.0, 1.0], [2, 1, 1.0, 1.0]],
        "heuristic_time": [[0.0, 1.2], [9.0, 0.0], [0.0, 1.2]],
        "bag_records": [
            ["1:0", 1, 0.0, 10.0, 0, 1, "node_0"],
            ["2:0", 2, 1.0, 10.0, 2, 1, "node_2"],
        ],
        "fault_windows": [[2, 1, 0.0, 1_000_000.0, 0.0, False]],
        "scorer_mode": "S4_queue_aware_rule_only",
        "s4_score_component_mask": 15,
        "merge_grant_rule": "M3",
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "g4irsf20_event_hotpath_policy": "E2",
        "g4irsf16_supervisor_mode": "off",
        "enable_s4_local_potential_descent_guard": True,
        "enable_s4_direct_neighbor_merge_calendar_visibility": True,
        "complete_on_goal_arrival": True,
        "enable_cie_component_activation": True,
        "max_simulation_time": runner.FIXED_END_EPOCH,
        "max_events": runner.MAX_EVENTS,
        "expected_binary_path": binary.resolve(),
    }


def _context(tmp_path: Path) -> runner.FaultContext:
    binary = tmp_path / "czr005_cpp.pyd"
    binary.write_bytes(b"native")
    workload = tmp_path / "canonical.jsonl"
    workload.write_text("{}\n", encoding="utf-8")
    base = _base_request(binary)
    graph = deepcopy(base)
    graph["bag_records"] = [deepcopy(base["bag_records"][0])]
    artifact = {
        "mode": "td",
        "deterministic_surviving_graph_values": True,
        "edge_residuals": [{"from": 0, "to": 1, "residual_seconds": 0.0}],
        "value_residuals": [
            {"node": 0, "goal": 1, "residual_seconds": 0.0, "support": 1}
        ],
    }
    graph["g4irsf24_dlp_artifact"] = artifact
    rows = _rows()
    return runner.FaultContext(
        rows=rows,
        raw_bag_count=2,
        segment_count=2,
        workload_source=workload,
        scenario_record={
            "scenario": "single_4",
            "fault_edges": [[2, 1]],
            "topology_upper_raw_bags": 1,
            "topology_blocked_raw_bags": 1,
        },
        base_request=base,
        graph_request=graph,
        graph_runtime_rows=(dict(rows[0]),),
        graph_rejected_rows=(dict(rows[1]),),
        graph_local={
            "artifact": artifact,
            "fault_edges": [[2, 1]],
            "protocol_scenario": {"scenario": "single_4"},
        },
    )


@pytest.fixture
def small_registered_population(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "REGISTERED_RAW_BAG_COUNT", 2)
    monkeypatch.setattr(runner, "REGISTERED_SEGMENT_COUNT", 2)


def test_strict_pair_changes_only_guard_and_keeps_admission_cohort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    small_registered_population: None,
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(runner, "_load_fault_context", lambda **_kwargs: context)

    off = runner.prepare_special_request(
        map_name="map2",
        scenario="single_4",
        study="strict",
        arm="FULL_WITHOUT_STRICT_DESCENT",
        binary=tmp_path / "czr005_cpp.pyd",
    )
    on = runner.prepare_special_request(
        map_name="map2",
        scenario="single_4",
        study="strict",
        arm="FULL_WITH_STRICT_DESCENT",
        binary=tmp_path / "czr005_cpp.pyd",
    )

    assert off.request["enable_s4_local_potential_descent_guard"] is False
    assert on.request["enable_s4_local_potential_descent_guard"] is True
    assert off.contract["changed_request_fields_from_reference"] == []
    assert on.contract["changed_request_fields_from_reference"] == [
        "enable_s4_local_potential_descent_guard"
    ]
    assert off.runtime_rows == on.runtime_rows
    assert off.rejected_rows == on.rejected_rows
    assert on.contract["native_admission_cohort_identical_within_pair"] is True


def test_potential_pair_shares_unreachable_recognition_and_changes_only_dlp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    small_registered_population: None,
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(runner, "_load_fault_context", lambda **_kwargs: context)

    edge = runner.prepare_special_request(
        map_name="map2",
        scenario="single_4",
        study="potential",
        arm="EDGE_FILTER_ONLY",
        binary=tmp_path / "czr005_cpp.pyd",
    )
    graph = runner.prepare_special_request(
        map_name="map2",
        scenario="single_4",
        study="potential",
        arm="SURVIVING_GRAPH_SERVICE_AWARE_POTENTIAL",
        binary=tmp_path / "czr005_cpp.pyd",
    )

    assert "g4irsf24_dlp_artifact" not in edge.request
    assert len(edge.runtime_rows) == 1
    assert len(edge.rejected_rows) == 1
    assert graph.contract["changed_request_fields_from_reference"] == [
        "g4irsf24_dlp_artifact",
    ]
    assert edge.request["bag_records"] == graph.request["bag_records"]
    assert edge.runtime_rows == graph.runtime_rows
    assert edge.rejected_rows == graph.rejected_rows
    assert graph.contract["native_admission_cohort_identical_within_pair"] is True
    assert graph.contract["pure_potential_effect_identified"] is True
    assert graph.contract[
        "source_unreachable_recognition_bundled_with_graph_treatment"
    ] is False
    assert edge.request["fault_windows"] == graph.request["fault_windows"]


def _summary(binary: Path) -> dict[str, object]:
    return {
        "requested_count": 1,
        "completed_count": 1,
        "failed_count": 0,
        "event_count": 7,
        "decision_count": 2,
        "declared_max_simulation_time": runner.FIXED_END_EPOCH,
        "declared_max_events": runner.MAX_EVENTS,
        "event_limit_reached": False,
        "time_limit_reached": True,
        "fault_event_count": 1,
        "repair_event_count": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "reservation_conflicts": 0,
        "runtime_full_astar_calls": 0,
        "runtime_full_cie_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "merge_grant_conservation_holds": True,
        "merge_grant_active_bijection_holds": True,
        "loaded_cpp_binary_path": str(binary.resolve()),
        "loaded_cpp_binary_sha256": runner._file_sha256(binary.resolve()),
        "scorer_mode_echo": "S4_queue_aware_rule_only",
        "s4_score_component_mask": 15,
        "merge_grant_rule": "M3",
        "merge_grant_timing_mode": "jit_fair_aging_deadline",
        "g4irsf20_event_hotpath_policy": "E2",
        "s4_direct_neighbor_merge_calendar_visibility_enabled": True,
        "complete_on_goal_arrival_enabled": True,
        "s4_local_potential_descent_guard_enabled": True,
        "cie_component_activation": {
            "counterfactual_scope": (
                "same_state_pre_feasibility_raw_scorer;"
                "full_mask15_vs_one_term_removed"
            ),
            "strict_descent": {
                "evaluation_count": 2,
                "filtered_candidate_count": 1,
                "filtered_decision_count": 1,
                "empty_ranking_count": 0,
            },
        },
        "g4irsf24_dlp_mode": "td",
        "g4irsf24_dlp_edge_residual_count": 1,
        "g4irsf24_dlp_value_residual_count": 1,
        "g4irsf24_dlp_committed_mutation_count": 1,
        "loop_count": 0,
        "unresolved_deadlock_count": 0,
        "starvation_count": 0,
    }


def test_execution_keeps_rejected_bag_in_fixed_denominator_and_suppresses_tht(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    small_registered_population: None,
) -> None:
    context = _context(tmp_path)
    binary = tmp_path / "czr005_cpp.pyd"
    monkeypatch.setattr(runner, "_load_fault_context", lambda **_kwargs: context)

    result = runner.execute_case(
        map_name="map2",
        scenario="single_4",
        study="strict",
        arm="FULL_WITH_STRICT_DESCENT",
        binary=binary,
        executor=lambda **_request: {
            "summary": _summary(binary),
            "bags": [
                {
                    "segment_id": "1:0",
                    "task_id": 1,
                    "completed": True,
                    "complete": True,
                    "release_time": 0.0,
                    "admitted_time": 0.0,
                    "finish_time": 5.0,
                    "final_node": 1,
                    "decision_count": 2,
                    "loop_count": 0,
                }
            ],
        },
    )

    assert result["status"] == "COMPLETE"
    business = result["fixed_denominator_business"]
    assert business["capacity"] == {"count": 1, "rate": 0.5, "definition": "all_selected_segments_completed"}
    assert business["missed_bag_count"] == 1
    assert business["detailed"]["denominator_raw_bags"] == 2
    assert business["detailed"]["backlog"]["raw_bag_total"]["end_backlog"] == 1
    assert result["full_population_timing"]["status"] == (
        "NOT_MEASURED_FULL_POPULATION_INCOMPLETE"
    )
    assert result["full_population_timing"][
        "survivor_or_common_cohort_used"
    ] is False
    assert result["outcome"]["paper_raw_bag_tth"]["distribution"] is None
    assert result["mechanism_diagnostics"]["strict_descent"]["scope"].startswith(
        "PRE_FEASIBILITY"
    )


def _minimal_artifact(
    *,
    study: str,
    arm: str,
    completion: int,
    cohort_same: bool,
    pair_identity: str = "same-reference-request",
    binary_sha256: str = "b" * 64,
    timing_mean: float | None = None,
) -> dict[str, object]:
    case_key = f"{study}:map2:1x:single_4:{arm}"
    return {
        "schema": runner.SCHEMA,
        "case_key": case_key,
        "map": "map2",
        "scale": 1,
        "scenario": "single_4",
        "study": study,
        "arm": arm,
        "status": "COMPLETE",
        "native_execution_started": True,
        "population": {"raw_bag_denominator": 2},
        "request_contract": {
            "runtime_requested_segment_count": 2,
            "source_rejected_unreachable_segment_count": 0,
        },
        "experiment_contract": {
            "canonical_release_schedule_sha256": "r" * 64,
            "reference_request_sha256": pair_identity,
            "graph_treatment_raw_bags_with_source_rejected_segment_count": 0,
            "native_admission_cohort_identical_within_pair": cohort_same,
            "admission_cohort_boundary": "SAME",
            "pure_potential_effect_identified": cohort_same,
        },
        "execution_integrity": {"pass": True},
        "provenance": {
            "git_commit": "a" * 40,
            "runner_sha256": "c" * 64,
            "binary_sha256": binary_sha256,
            "canonical_workload_sha256": "w" * 64,
        },
        "fixed_denominator_business": {
            "capacity": {"count": completion, "rate": completion / 2},
            "on_time": {"count": completion, "rate": completion / 2},
            "missed_bag_count": 2 - completion,
            "missed_bag_rate": 1.0 - completion / 2,
            "detailed": {
                "tardiness_seconds": {
                    "fixed_horizon_all_population_lower_bound": {
                        "sum": float(2 - completion)
                    }
                },
                "backlog": {
                    "raw_bag_total": {
                        "peak_backlog": 2,
                        "end_backlog": 2 - completion,
                        "backlog_area_seconds": float(2 - completion),
                    }
                },
            },
        },
        "full_population_timing": (
            {
                "status": "FULL_POPULATION_RAW_BAG_TIMING_1X",
                "distributions": {
                    "processed_attempt": {
                        "mean_seconds": timing_mean,
                        "p95_seconds": timing_mean + 5.0,
                        "p99_seconds": timing_mean + 8.0,
                        "max_seconds": timing_mean + 10.0,
                    }
                },
            }
            if timing_mean is not None
            else {
                "status": "NOT_MEASURED_FULL_POPULATION_INCOMPLETE",
                "distributions": None,
            }
        ),
        "mechanism_diagnostics": {
            "strict_descent": {},
            "fault_potential": {},
            "progress": {},
            "holds_and_reroutes": {},
        },
        "runtime": {
            "wall_seconds": 1.0,
            "cpu_seconds": 1.0,
            "event_count": 1,
            "decision_count": 1,
            "native_summary": {"loaded_cpp_binary_sha256": binary_sha256},
        },
    }


def test_aggregate_writes_nonempty_table_and_boundary_report(tmp_path: Path) -> None:
    paths = []
    for arm, completion in zip(runner.STUDY_ARMS["strict"], (1, 2)):
        path = tmp_path / f"{arm}.json"
        path.write_text(
            json.dumps(
                _minimal_artifact(
                    study="strict",
                    arm=arm,
                    completion=completion,
                    cohort_same=True,
                )
            ),
            encoding="utf-8",
        )
        paths.append(path)

    aggregate = runner.aggregate_results(paths)
    table = tmp_path / "table.csv"
    report = tmp_path / "report.md"
    output = tmp_path / "aggregate.json"
    runner._write_json(output, aggregate)
    runner._write_csv(table, aggregate["rows"])
    runner._write_text(report, runner.render_report(aggregate))

    assert aggregate["status"] == "PARTIAL"
    assert aggregate["pair_effects"][0]["metrics"][
        "completed_raw_bag_count"
    ]["absolute"] == 1.0
    assert output.stat().st_size > 0
    assert table.stat().st_size > 0
    text = report.read_text(encoding="utf-8")
    assert "pre-feasibility" in text
    assert "same unreachable recognition, native admission cohort" in text
    assert "survivor/common-cohort timing" in text


def test_aggregate_rejects_pair_with_different_reference_request_identity(
    tmp_path: Path,
) -> None:
    paths = []
    for index, arm in enumerate(runner.STUDY_ARMS["strict"]):
        path = tmp_path / f"{arm}.json"
        path.write_text(
            json.dumps(
                _minimal_artifact(
                    study="strict",
                    arm=arm,
                    completion=index + 1,
                    cohort_same=True,
                    pair_identity=f"reference-{index}",
                )
            ),
            encoding="utf-8",
        )
        paths.append(path)

    aggregate = runner.aggregate_results(paths)

    effect = aggregate["pair_effects"][0]
    assert effect["pair_identity_pass"] is False
    assert effect["valid_for_outcome_comparison"] is False
    assert effect["causal_interpretation"] == "INVALID_IDENTITY_NOT_COMPARABLE"
    assert effect["metrics"]["completed_raw_bag_count"]["absolute"] is None


def test_wrong_loaded_binary_sha_fails_execution_integrity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    small_registered_population: None,
) -> None:
    context = _context(tmp_path)
    binary = tmp_path / "czr005_cpp.pyd"
    monkeypatch.setattr(runner, "_load_fault_context", lambda **_kwargs: context)
    summary = _summary(binary)
    summary["loaded_cpp_binary_sha256"] = "wrong"

    result = runner.execute_case(
        map_name="map2",
        scenario="single_4",
        study="strict",
        arm="FULL_WITH_STRICT_DESCENT",
        binary=binary,
        executor=lambda **_request: {
            "summary": summary,
            "bags": [
                {
                    "segment_id": "1:0",
                    "task_id": 1,
                    "completed": True,
                    "complete": True,
                    "release_time": 0.0,
                    "admitted_time": 0.0,
                    "finish_time": 5.0,
                    "final_node": 1,
                    "decision_count": 2,
                    "loop_count": 0,
                }
            ],
        },
    )

    assert result["status"] == "FAILED_INTEGRITY"
    assert result["execution_integrity"]["gates"][
        "loaded_expected_binary_sha256"
    ] is False


def test_summary_terminal_counts_must_match_returned_bag_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    small_registered_population: None,
) -> None:
    context = _context(tmp_path)
    binary = tmp_path / "czr005_cpp.pyd"
    monkeypatch.setattr(runner, "_load_fault_context", lambda **_kwargs: context)
    summary = _summary(binary)
    summary["completed_count"] = 0
    summary["failed_count"] = 1

    result = runner.execute_case(
        map_name="map2",
        scenario="single_4",
        study="strict",
        arm="FULL_WITH_STRICT_DESCENT",
        binary=binary,
        executor=lambda **_request: {
            "summary": summary,
            "bags": [
                {
                    "segment_id": "1:0",
                    "task_id": 1,
                    "completed": True,
                    "complete": True,
                    "release_time": 0.0,
                    "admitted_time": 0.0,
                    "finish_time": 5.0,
                    "final_node": 1,
                    "decision_count": 2,
                    "loop_count": 0,
                }
            ],
        },
    )

    assert result["status"] == "FAILED_INTEGRITY"
    assert result["execution_integrity"]["gates"][
        "runtime_summary_counts_match_returned_bag_states"
    ] is False


def test_aggregate_includes_full_population_mean_and_tail_effects(
    tmp_path: Path,
) -> None:
    paths = []
    for arm, mean in zip(runner.STUDY_ARMS["strict"], (100.0, 90.0)):
        path = tmp_path / f"timing_{arm}.json"
        path.write_text(
            json.dumps(
                _minimal_artifact(
                    study="strict",
                    arm=arm,
                    completion=2,
                    cohort_same=True,
                    timing_mean=mean,
                )
            ),
            encoding="utf-8",
        )
        paths.append(path)

    aggregate = runner.aggregate_results(paths)

    effect = aggregate["pair_effects"][0]
    assert effect["valid_for_outcome_comparison"] is True
    assert effect["metrics"]["population_latency_mean_seconds"]["absolute"] == -10.0
    assert effect["metrics"]["population_latency_p95_seconds"]["absolute"] == -10.0
    assert "Δ mean/P95/P99/max" in runner.render_report(aggregate)


def test_fault_table_uses_corrected_legacy_incomplete_backlog_area() -> None:
    payload = _minimal_artifact(
        study="strict",
        arm="FULL_WITH_STRICT_DESCENT",
        completion=1,
        cohort_same=True,
        timing_mean=None,
    )
    detailed = payload["fixed_denominator_business"]["detailed"]
    detailed["fixed_horizon_seconds"] = 98_259.0
    backlog = detailed["backlog"]["raw_bag_total"]
    backlog.update(
        arrival_count=2,
        departure_count=1,
        end_backlog=1,
        drain_time_seconds=5.0,
    )

    row = runner.result_table_row(payload)
    expected = 1.0 + 98_259.0 - (81_503.72582 + 5.0)

    assert row["raw_bag_backlog_area_seconds"] == pytest.approx(expected)
    assert row["raw_bag_backlog_area_legacy_seconds"] == 1.0
    assert row["raw_bag_backlog_area_status"] == (
        "EXACT_LEGACY_TAIL_CORRECTED_V1"
    )
