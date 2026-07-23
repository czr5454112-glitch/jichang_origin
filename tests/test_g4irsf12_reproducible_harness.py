from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf12_reproducible_harness as cli


ROOT = Path(__file__).resolve().parents[1]


def _safe_summary(*, requested: int, completed: int) -> dict[str, object]:
    return {
        "requested_count": requested,
        "completed_count": completed,
        "failed_count": requested - completed,
        "conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "full_future_routes_stored": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "reservation_depth": 1,
        "max_edges_selected_per_arrive": 1,
        "decision_trace_stored_count": 0,
        "event_count": requested * 10,
        "runtime_seconds": 0.25,
    }


def _successful_fake_executor(**kwargs: object) -> dict[str, object]:
    input_rows = list(kwargs["input_rows"])
    bags = []
    for index, row in enumerate(input_rows):
        release = float(row["pass_time"])
        admitted = release + 2.0
        bags.append(
            {
                "segment_id": row["segment_id"],
                "task_id": row["task_id"],
                "release_time": release,
                "admitted_time": admitted,
                "finish_time": admitted + 8.0 + index * 1.0e-6,
                "completed": True,
            }
        )
    summary = _safe_summary(requested=len(bags), completed=len(bags))
    summary.update(
        {
            "resource_semantics_id": kwargs["resource_semantics"],
            "scorer_mode": kwargs["scorer_mode"],
            "pibt_mode": kwargs["pibt_mode"],
            "pressure_mode": kwargs["pressure_mode"],
            "admission_mode": kwargs["admission_mode"],
            "pibt_max_depth": kwargs["pibt_max_depth"],
            "local_queue_capacity": kwargs.get("local_queue_capacity", 0),
            "max_events": kwargs["max_events"],
        }
    )
    if "framework_mode" in kwargs:
        summary["framework_mode"] = kwargs["framework_mode"]
    for name in harness.FROZEN_NUMERIC_RUNTIME_CONTROLS:
        summary[name] = kwargs[name]
    return {
        "summary": summary,
        "bags": bags,
        "decisions": [],
        "events": [],
    }


def _valid_prior_result(
    case: harness.CaseSpec,
    size_segments: int,
    *,
    repeat_index: int = 1,
    result_hash_character: str = "a",
    binary_sha256: str = "c" * 64,
    source_bundle_sha256: str = "b" * 64,
    executor_source_sha256: str = "d" * 64,
) -> dict[str, object]:
    prefix_hash, raw_bag_count = harness._cached_prefix_evidence(
        str(ROOT.resolve()),
        size_segments,
    )
    controls = case.runtime_controls
    row: dict[str, object] = {
        **harness.planned_result(case, size_segments),
        "repeat_index": repeat_index,
        "execution_status": "EXECUTED",
        "gate_status": "PASS",
        "evidence_status": "EXECUTED_RESULT_VALIDATED",
        "termination_reason": "DRAINED",
        "input_prefix_sha256": prefix_hash,
        "source_bundle_sha256": source_bundle_sha256,
        "binary_sha256": binary_sha256,
        "executor_source_sha256": executor_source_sha256,
        "deterministic_result_sha256": result_hash_character * 64,
        "repeat_consistency": "SINGLE_RESULT",
        "selected_segment_count": size_segments,
        "selected_raw_bag_count": raw_bag_count,
        "completed_segment_count": size_segments,
        "complete_raw_bag_count": raw_bag_count,
        "failed_segment_count": 0,
        "completion_rate": 1.0,
        "comparison_eligible": True,
        "resource_semantics_echo": controls["resource_semantics"],
        "scorer_mode_echo": controls["scorer_mode"],
        "pibt_mode_echo": controls["pibt_mode"],
        "pressure_mode_echo": controls["pressure_mode"],
        "admission_mode_echo": controls["admission_mode"],
        "framework_mode_echo": controls.get("framework_mode", ""),
        "pibt_max_depth_echo": controls["pibt_max_depth"],
        "max_events_echo": controls["max_events"],
        "conflict_count": 0,
        "unsafe_entry_count": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "future_routes_stored": 0,
        "unresolved_deadlock_count": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "reservation_depth": controls.get("reservation_depth", 1),
        "local_queue_capacity": controls.get("local_queue_capacity", 0),
        "declared_max_events": controls["max_events"],
        "max_edges_selected_per_arrive": 1,
        "event_count": size_segments * 10,
    }
    for name in harness.FROZEN_NUMERIC_RUNTIME_CONTROLS:
        row[f"{name}_echo"] = controls[name]
    if case.phase == "F" and case.pibt_label != "P0":
        row.update(
            {
                "pibt_applicability_count": 1,
                "pibt_attempt_count": 1,
                "pibt_prepare_count": 1,
                "pibt_validate_count": 1,
                "pibt_commit_count": 0,
                "pibt_rollback_count": 0,
                "pibt_backtrack_count": 0,
                "pibt_wait_for_cycle_count": 0,
                "pibt_handoff_count": 0,
            }
        )
    if case.phase == "H" and case.fault_profile != "no_fault":
        row.update(
            {
                "fault_affected_bag_count": 1,
                "fault_affected_completed_count": 1,
                "fault_recovery_seconds_available": True,
                "fault_recovery_seconds": 0.0,
                "repair_backlog_slope_available": True,
                "repair_backlog_slope": 0.0,
            }
        )
    if case.phase == "J":
        row["original_entry_mean_minutes"] = 4.0
    return row


def _write_result_ledger(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=harness.RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_fixed_identity_and_strict_prefix_order() -> None:
    identity = harness.assert_fixed_identity(ROOT)
    assert identity["source_row_count"] == 43_603
    assert identity["source_bag_count"] == 28_506

    prefix_144 = harness.load_input_prefix(144, root=ROOT)
    prefix_512 = harness.load_input_prefix(512, root=ROOT)
    assert prefix_144.first_segment_id == "0:storage_in"
    assert prefix_144.rows[1]["segment_id"] == "0:storage_out"
    assert [row["segment_id"] for row in prefix_512.rows[:144]] == [
        row["segment_id"] for row in prefix_144.rows
    ]
    assert [row["input_row_index"] for row in prefix_144.rows] == list(range(144))
    assert len(prefix_144.prefix_sha256) == 64
    assert prefix_144.prefix_sha256 != prefix_512.prefix_sha256

    with pytest.raises(harness.HarnessValidationError):
        harness.load_input_prefix(145, root=ROOT)


def test_raw_bag_denominators_and_wait_decomposition() -> None:
    inputs = [
        {
            "segment_id": "7:storage_in",
            "task_id": 7,
            "original_entry_time": 5.0,
            "pass_time": 5.0,
        },
        {
            "segment_id": "7:storage_out",
            "task_id": 7,
            "original_entry_time": 5.0,
            "pass_time": 20.0,
        },
        {
            "segment_id": "8:direct",
            "task_id": 8,
            "original_entry_time": 10.0,
            "pass_time": 10.0,
        },
    ]
    results = [
        {
            "segment_id": "7:storage_in",
            "release_time": 5.0,
            "admitted_time": 7.0,
            "finish_time": 15.0,
            "completed": True,
        },
        {
            "segment_id": "7:storage_out",
            "release_time": 20.0,
            "admitted_time": 22.0,
            "finish_time": 30.0,
            "completed": True,
        },
        {
            "segment_id": "8:direct",
            "release_time": 10.0,
            "admitted_time": 11.0,
            "finish_time": 14.0,
            "completed": True,
        },
    ]
    rows = harness.aggregate_raw_bag_timings(inputs, results)
    task7 = next(row for row in rows if row["task_id"] == 7)
    assert task7["original_entry_time_tth_seconds"] == pytest.approx(35.0)
    assert task7["java_release_time_tth_seconds"] == pytest.approx(20.0)
    assert task7["scheduled_pre_release_wait_seconds"] == pytest.approx(15.0)
    assert task7["source_wait_seconds"] == pytest.approx(4.0)
    assert task7["network_time_seconds"] == pytest.approx(16.0)
    assert task7["total_system_time_seconds"] == pytest.approx(35.0)

    summary = harness.summarize_raw_bag_timings(
        rows, selected_segment_count=3
    )
    assert summary["comparison_eligible"] is True
    assert summary["original_entry_mean_minutes"] == pytest.approx(
        ((35.0 + 4.0) / 2.0) / 60.0
    )

    partial = harness.aggregate_raw_bag_timings(inputs, results[:2])
    partial_summary = harness.summarize_raw_bag_timings(
        partial, selected_segment_count=3
    )
    assert partial_summary["comparison_eligible"] is False
    assert partial_summary["original_entry_mean_minutes"] is None
    assert partial_summary["survivor_metric_comparison_allowed"] is False


def test_capability_introspection_blocks_old_wrapper_without_execution(
    tmp_path: Path,
) -> None:
    called = False

    def limited_executor(
        *,
        bag_records: object,
        trace_limit: int = 0,
    ) -> dict[str, object]:
        nonlocal called
        called = True
        raise AssertionError("capability-blocked executor must not run")

    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"fake-runtime")
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B6"
    )
    row = harness.execute_case(
        case,
        144,
        executor=limited_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert called is False
    assert row["execution_status"] == "NOT_RUN"
    assert row["gate_status"] == "PENDING"
    assert "MISSING_EXECUTOR_CAPABILITY:scorer_mode" in row["blocker"]
    assert "MISSING_EXECUTOR_CAPABILITY:pibt_mode" in row["blocker"]


def test_fake_executor_hashes_summary_only_and_repeat_consistency(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"deterministic-runtime")
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    kwargs = {
        "executor": _successful_fake_executor,
        "executor_binary": binary,
        "source_paths": [
            Path("scripts/eval/g4irsf12_reproducible_harness.py"),
            Path("tests/test_g4irsf12_reproducible_harness.py"),
        ],
        "root": ROOT,
        "summary_only": True,
    }
    left = harness.execute_case(case, 144, **kwargs)
    right = harness.execute_case(case, 144, **kwargs)
    assert left["execution_status"] == "EXECUTED"
    assert left["gate_status"] == "PASS"
    assert left["completed_segment_count"] == 144
    assert left["complete_raw_bag_count"] == left["selected_raw_bag_count"]
    assert left["source_wait_mean_minutes"] > 0.0
    for field in (
        "input_prefix_sha256",
        "case_config_sha256",
        "source_bundle_sha256",
        "binary_sha256",
        "deterministic_result_sha256",
    ):
        assert len(left[field]) == 64
    assert left["deterministic_result_sha256"] == right[
        "deterministic_result_sha256"
    ]
    repeated = harness.apply_repeat_consistency([left, right])
    assert {row["repeat_consistency"] for row in repeated} == {"MATCH"}

    changed = dict(right)
    changed["deterministic_result_sha256"] = "f" * 64
    mismatch = harness.apply_repeat_consistency([left, changed])
    assert {row["gate_status"] for row in mismatch} == {"FAIL"}
    assert {row["repeat_consistency"] for row in mismatch} == {"MISMATCH"}


def test_early_abort_retains_partial_result(tmp_path: Path) -> None:
    def early_executor(**kwargs: object) -> dict[str, object]:
        input_rows = list(kwargs["input_rows"])
        bags = []
        for row in input_rows[:12]:
            release = float(row["pass_time"])
            bags.append(
                {
                    "segment_id": row["segment_id"],
                    "release_time": release,
                    "admitted_time": release + 1.0,
                    "finish_time": release + 5.0,
                    "completed": True,
                }
            )
        summary = _safe_summary(requested=len(input_rows), completed=len(bags))
        summary["termination_reason"] = harness.EARLY_ABORT_STATUS
        summary.update(
            {
                "resource_semantics_id": kwargs["resource_semantics"],
                "scorer_mode": kwargs["scorer_mode"],
                "pibt_mode": kwargs["pibt_mode"],
                "pibt_max_depth": kwargs["pibt_max_depth"],
                "pressure_mode": kwargs["pressure_mode"],
                "admission_mode": kwargs["admission_mode"],
                "local_queue_capacity": kwargs.get("local_queue_capacity", 0),
                "max_events": kwargs["max_events"],
            }
        )
        for name in harness.FROZEN_NUMERIC_RUNTIME_CONTROLS:
            summary[name] = kwargs[name]
        return {"summary": summary, "bags": bags}

    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"early-runtime")
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = harness.execute_case(
        case,
        144,
        executor=early_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["execution_status"] == harness.EARLY_ABORT_STATUS
    assert row["gate_status"] == "FAIL"
    assert row["completed_segment_count"] == 12
    assert row["original_entry_mean_minutes"] is None
    assert harness.EARLY_ABORT_STATUS in row["blocker"]


def test_control_evidence_denominators_are_explicit() -> None:
    rows = harness.load_control_evidence(ROOT)
    historical_processed = next(
        row
        for row in rows
        if row["phase"] == "B"
        and row["candidate_id"] == "historical_hca_parsed"
        and row["primary_denominator"] == "processed_segment_attempt_time_tth"
    )
    historical_original = next(
        row
        for row in rows
        if row["phase"] == "B"
        and row["candidate_id"] == "historical_hca_parsed"
        and row["primary_denominator"] == "original_entry_time_tth"
    )
    assert historical_processed["reported_mean_minutes"] == pytest.approx(
        3.9671227110082086
    )
    assert historical_original["original_entry_mean_minutes"] == pytest.approx(
        5.764936746096144
    )
    assert historical_processed["execution_status"] == "NOT_RUN"
    assert historical_processed["gate_status"] == "NOT_APPLICABLE"
    assert not any(
        row["gate_status"] == "PASS" and row["execution_status"] == "NOT_RUN"
        for row in rows
    )


def test_plan_outputs_are_pending_and_complete(tmp_path: Path) -> None:
    rows = [
        *harness.load_control_evidence(ROOT),
        *harness.planned_results(),
    ]
    paths = harness.write_harness_outputs(
        rows,
        root=tmp_path,
        identity_root=ROOT,
    )
    assert len(paths) == len(harness.OUTPUT_PATHS)
    assert all(path.is_file() for path in paths)

    framework = tmp_path / harness.OUTPUT_PATHS["framework_csv"]
    with framework.open("r", encoding="utf-8", newline="") as handle:
        framework_rows = list(csv.DictReader(handle))
    planned = [
        row
        for row in framework_rows
        if row["evidence_status"] == "PLANNED_NOT_EXECUTED"
    ]
    assert planned
    assert all(row["execution_status"] == "NOT_RUN" for row in planned)
    assert all(row["gate_status"] == "PENDING" for row in planned)

    bundle = json.loads(
        (tmp_path / harness.OUTPUT_PATHS["candidate_bundle"]).read_text(
            encoding="utf-8"
        )
    )
    assert bundle["g4j_enabled"] is False
    assert bundle["g4j_status"] == "CLOSED"
    assert bundle["phase_j_promotion_opens_g4j"] is False
    assert bundle["promotion_status"] == "PENDING"
    assert len(bundle["finalists"]) == 3
    assert all(
        finalist["promotion_status"] == "PENDING"
        for finalist in bundle["finalists"]
    )
    promotion = (
        tmp_path / harness.OUTPUT_PATHS["promotion_report"]
    ).read_text(encoding="utf-8")
    assert "A NOT_RUN/PENDING case is never PASS" in promotion
    assert "G4J remains CLOSED" in promotion

    assert (
        harness.OUTPUT_PATHS["resource_runtime_csv"]
        != "outputs/tables/g4irsf12_resource_semantics_ab.csv"
    )
    assert (
        harness.OUTPUT_PATHS["scorer_closed_loop_csv"]
        != "outputs/tables/g4irsf12_scorer_isolation_ab.csv"
    )
    assert (
        harness.OUTPUT_PATHS["pibt_wait_for_motifs_csv"]
        == "outputs/tables/g4irsf12_wait_for_cycle_motifs.csv"
    )
    assert (
        harness.OUTPUT_PATHS["pibt_atomic_commit_rollback_csv"]
        == "outputs/tables/g4irsf12_atomic_commit_rollback.csv"
    )
    for key in (
        "pibt_depth_csv",
        "pibt_wait_for_csv",
        "pibt_wait_for_motifs_csv",
        "pibt_atomic_csv",
        "pibt_atomic_commit_rollback_csv",
    ):
        with (tmp_path / harness.OUTPUT_PATHS[key]).open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            rows = list(csv.DictReader(handle))
        assert rows
        assert {row["execution_status"] for row in rows} == {"NOT_RUN"}
        assert {row["gate_status"] for row in rows} == {"PENDING"}
    assert (
        tmp_path / harness.OUTPUT_PATHS["pibt_wait_for_csv"]
    ).read_bytes() == (
        tmp_path / harness.OUTPUT_PATHS["pibt_wait_for_motifs_csv"]
    ).read_bytes()
    assert (
        tmp_path / harness.OUTPUT_PATHS["pibt_atomic_csv"]
    ).read_bytes() == (
        tmp_path / harness.OUTPUT_PATHS["pibt_atomic_commit_rollback_csv"]
    ).read_bytes()


def test_authorization_guards_large_and_fault_tiers() -> None:
    b5 = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    assert "8192 execution requires --allow-8192" in harness.authorization_blockers(
        b5, 8_192, [], allow_8192=False
    )
    assert any(
        "prior tier" in blocker
        for blocker in harness.authorization_blockers(
            b5, 8_192, [], allow_8192=True
        )
    )
    h_fault = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "single_immediate"
    )
    assert any(
        "H_stable_no_fault" in blocker
        for blocker in harness.authorization_blockers(h_fault, 2_048, [])
    )


def test_pressure_and_admission_values_match_runtime_canonical_names() -> None:
    cases = {case.control_label: case for case in harness.pressure_credit_cases()}
    assert cases["C0"].runtime_controls["pressure_mode"] == "off"
    assert cases["C0"].runtime_controls["admission_mode"] == "off"
    assert (
        cases["C1"].runtime_controls["pressure_mode"]
        == "absolute_downstream_queue_penalty"
    )
    assert (
        cases["C2"].runtime_controls["pressure_mode"]
        == "goal_conditioned_differential"
    )
    assert (
        cases["C3"].runtime_controls["pressure_mode"]
        == "distance_biased_differential"
    )
    assert (
        cases["C4"].runtime_controls["admission_mode"]
        == "expiring_first_edge_credit"
    )


def test_c_e_f_matrices_are_explicit_and_preserve_isolation_controls() -> None:
    c_cases = harness.resource_semantics_cases()
    e_cases = harness.scorer_closed_loop_cases()
    f_cases = harness.pibt_depth_cases()
    assert {case.resource_label for case in c_cases} == set(
        harness.RESOURCE_LABELS
    )
    assert all(case.sizes == (144, 512, 2_048, 8_192) for case in c_cases)
    assert {case.scorer_label for case in e_cases} == set(
        harness.SCORER_LABELS
    )
    assert all(case.sizes == (2_048, 8_192) for case in e_cases)
    assert {case.pibt_label for case in f_cases} == set(harness.PIBT_LABELS)
    assert all(case.sizes == (2_048, 8_192) for case in f_cases)
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in f_cases
    )
    assert all(
        case.runtime_controls["max_events"] == harness.FORMAL_MAX_EVENTS
        for case in harness.all_cases()
    )
    assert all(
        case.sizes == (144, 512, 2_048, 8_192)
        for case in harness.framework_delta_cases()
    )
    assert all(
        case.sizes == (2_048, 8_192)
        for case in harness.pressure_credit_cases()
    )


def test_finite_queue_capacity_is_frozen_for_isolated_pibt_controls() -> None:
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in harness.framework_delta_cases()
    )
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in harness.pressure_credit_cases()
    )
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in harness.fault_recovery_cases()
    )
    assert all(
        case.runtime_controls["local_queue_capacity"]
        == harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY
        for case in harness.original_scale_cases()
    )


def test_f_runtime_requires_audit_counters_and_unlimited_is_not_applicable(
    tmp_path: Path,
) -> None:
    case = next(
        case for case in harness.pibt_depth_cases() if case.pibt_label == "P2"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def pibt_executor(
        *,
        reported_capacity: int,
        **kwargs: object,
    ) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = dict(payload["summary"])
        summary.update(
                {
                    "local_queue_capacity": reported_capacity,
                    "bounded_local_pibt_applicability_count": 1,
                    "bounded_local_pibt_attempt_count": 1,
                    "bounded_local_pibt_prepare_count": 1,
                    "bounded_local_pibt_validate_count": 1,
                "bounded_local_pibt_commit_count": 0,
                "bounded_local_pibt_rollback_count": 0,
                "bounded_local_pibt_backtrack_count": 0,
                "bounded_local_pibt_wait_for_cycle_count": 0,
                "bounded_local_pibt_handoff_count": 0,
            }
        )
        return {**payload, "summary": summary}

    common = {
        "executor_binary": binary,
        "source_paths": [
            Path("scripts/eval/g4irsf12_reproducible_harness.py")
        ],
        "root": ROOT,
    }
    finite = harness.execute_case(
        case,
        2_048,
        executor=lambda **kwargs: pibt_executor(
            reported_capacity=harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY,
            **kwargs,
        ),
        **common,
    )
    assert finite["gate_status"] == "PASS"
    assert finite["pibt_handoff_count"] == 0
    assert finite["pibt_applicability_count"] == 1

    unlimited = harness.execute_case(
        case,
        2_048,
        executor=lambda **kwargs: pibt_executor(
            reported_capacity=0,
            **kwargs,
        ),
        **common,
    )
    assert unlimited["gate_status"] == "NOT_APPLICABLE"
    assert unlimited["evidence_status"] == (
        "EXECUTED_CONFIGURATION_NOT_APPLICABLE"
    )
    assert "unlimited local_queue_capacity" in unlimited["blocker"]

    def inactive_executor(**kwargs: object) -> dict[str, object]:
        payload = pibt_executor(
            reported_capacity=harness.F_RUNTIME_LOCAL_QUEUE_CAPACITY,
            **kwargs,
        )
        summary = {
            **payload["summary"],
            "bounded_local_pibt_applicability_count": 0,
            "bounded_local_pibt_attempt_count": 0,
            "bounded_local_pibt_prepare_count": 0,
            "bounded_local_pibt_validate_count": 0,
        }
        return {**payload, "summary": summary}

    inactive = harness.execute_case(
        case,
        2_048,
        executor=inactive_executor,
        **common,
    )
    assert inactive["gate_status"] == "NOT_APPLICABLE"
    assert "did not exercise positive" in inactive["blocker"]


def test_phase_j_is_independent_of_g4j_and_uses_matched_original_entry() -> None:
    fast = harness.evaluate_original_entry_performance(4.0)
    assert fast["matched_original_entry_performance_gate"] == "PASS"
    between = harness.evaluate_original_entry_performance(4.2)
    assert between["v2_safe_original_entry_gate"] == "FAIL"
    assert between["corrected_hca_original_entry_gate"] == "PASS"
    assert between["matched_original_entry_performance_gate"] == "FAIL"
    assert "not comparable" in between["processed_attempt_warning"]

    finalist = next(
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == "J_F1"
    )
    blockers = harness.authorization_blockers(
        finalist,
        harness.FULL_SIZE_SEGMENTS,
        [],
        allow_full=True,
        promoted_finalists=["J_F1"],
    )
    assert not any("G4J" in blocker for blocker in blockers)

    rows = [
        {
            "case_id": finalist.case_id,
            "size_segments": harness.FULL_SIZE_SEGMENTS,
            "repeat_index": index,
            "execution_status": "EXECUTED",
            "gate_status": "PASS",
            "deterministic_result_sha256": "a" * 64,
            "original_entry_mean_minutes": 4.0,
        }
        for index in range(1, 6)
    ]
    bundle = harness.candidate_bundle(rows)
    promoted = next(
        row for row in bundle["finalists"] if row["candidate_id"] == "J_F1"
    )
    assert bundle["g4j_status"] == "CLOSED"
    assert bundle["promotion_status"] == "READY"
    assert promoted["promotion_status"] == "PROMOTED"
    assert promoted["v2_safe_original_entry_gate"] == "PASS"
    assert promoted["corrected_hca_original_entry_gate"] == "PASS"
    assert "historical_engineering_target_minutes" not in bundle


def test_j_f3_is_reserved_and_cannot_be_called_learned() -> None:
    f3 = next(
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == "J_F3_RESERVED_NO_V3"
    )
    assert "no trained" in f3.finalist_role
    assert "not a learned v3 model" in f3.notes
    blockers = harness.authorization_blockers(
        f3,
        harness.FULL_SIZE_SEGMENTS,
        [],
        allow_full=True,
        promoted_finalists=[f3.candidate_id],
    )
    assert any("reserved" in blocker for blocker in blockers)


def test_resource_selection_and_c_e_f_prerequisites_fail_closed() -> None:
    resource = next(
        case for case in harness.resource_semantics_cases() if case.resource_label == "R3"
    )
    accepted_c_2048 = _valid_prior_result(resource, 2_048)
    blockers = harness.authorization_blockers(
        resource,
        8_192,
        [accepted_c_2048],
        allow_8192=True,
    )
    assert any("best-two selection" in blocker for blocker in blockers)
    assert harness.authorization_blockers(
        resource,
        8_192,
        [accepted_c_2048],
        allow_8192=True,
        promoted_resource_labels=["R3"],
    ) == []

    scorer = next(
        case for case in harness.scorer_closed_loop_cases() if case.scorer_label == "S0"
    )
    assert any(
        "C_R3 8192" in blocker
        for blocker in harness.authorization_blockers(scorer, 2_048, [])
    )
    pibt = next(
        case for case in harness.pibt_depth_cases() if case.pibt_label == "P0"
    )
    assert any(
        "E_S0 8192" in blocker
        for blocker in harness.authorization_blockers(pibt, 2_048, [])
    )


def test_cli_prior_evidence_is_deduped_preserved_and_atomically_replaced() -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    planned = [
        harness.planned_result(case, 144),
        harness.planned_result(case, 512),
    ]
    prior_one = {
        **harness.planned_result(case, 144),
        "repeat_index": 1,
        "execution_status": "EXECUTED",
        "gate_status": "PASS",
        "evidence_status": "EXECUTED_RESULT_VALIDATED",
        "deterministic_result_sha256": "a" * 64,
    }
    prior_two = {
        **prior_one,
        "repeat_index": 2,
    }
    merged = cli._merge_evidence_rows(
        planned,
        [prior_one, prior_one, prior_two],
        [],
    )
    tier_144 = [row for row in merged if cli._tier_key(row)[2] == 144]
    assert len(tier_144) == 2
    assert {row["repeat_index"] for row in tier_144} == {1, 2}
    assert any(
        row["size_segments"] == 512 and row["execution_status"] == "NOT_RUN"
        for row in merged
    )

    replacement = {
        **prior_one,
        "repeat_index": 1,
        "deterministic_result_sha256": "b" * 64,
    }
    replaced = cli._merge_evidence_rows(
        planned,
        [prior_one, prior_two],
        [replacement],
    )
    tier_144 = [row for row in replaced if cli._tier_key(row)[2] == 144]
    assert tier_144 == [replacement]


def test_cli_plan_only_retains_an_admitted_prior_ledger(tmp_path: Path) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    prior = _valid_prior_result(
        case,
        144,
        result_hash_character="c",
    )
    ledger = tmp_path / "prior.csv"
    _write_result_ledger(ledger, [prior])
    output_root = tmp_path / "published"
    args = cli._parser().parse_args(
        [
            "--phases",
            "B",
            "--prior-ledger",
            str(ledger),
            "--output-root",
            str(output_root),
        ]
    )
    cli.run(args)
    with (
        output_root / harness.OUTPUT_PATHS["framework_csv"]
    ).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    retained = [
        row
        for row in rows
        if row["case_id"] == case.case_id and row["size_segments"] == "144"
    ]
    assert len(retained) == 1
    assert retained[0]["execution_status"] == "EXECUTED"
    assert retained[0]["deterministic_result_sha256"] == "c" * 64


def test_cli_preserves_prior_rows_from_an_unselected_phase(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.resource_semantics_cases()
        if case.resource_label == "R3"
    )
    prior = _valid_prior_result(
        case,
        8_192,
        result_hash_character="d",
    )
    ledger = tmp_path / "prior-c.csv"
    _write_result_ledger(ledger, [prior])

    output_root = tmp_path / "published"
    args = cli._parser().parse_args(
        [
            "--phases",
            "B",
            "--prior-ledger",
            str(ledger),
            "--output-root",
            str(output_root),
        ]
    )
    cli.run(args)
    with (
        output_root / harness.OUTPUT_PATHS["resource_runtime_csv"]
    ).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["case_id"] == case.case_id
    assert rows[0]["execution_status"] == "EXECUTED"
    assert rows[0]["deterministic_result_sha256"] == "d" * 64


def test_cli_cross_phase_prior_authorizes_selected_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"current-runtime")
    source = tmp_path / "current_source.py"
    source.write_text("CURRENT = True\n", encoding="utf-8")

    def dummy_executor(**_kwargs: object) -> dict[str, object]:
        return {}

    binary_digest = harness.file_sha256(binary)
    source_digest = harness.source_bundle_sha256([source], root=ROOT)
    executor_digest = harness.inspect_executor(
        dummy_executor
    ).source_sha256
    resource = next(
        case
        for case in harness.resource_semantics_cases()
        if case.resource_label == "R3"
    )
    prior = _valid_prior_result(
        resource,
        8_192,
        result_hash_character="e",
        binary_sha256=binary_digest,
        source_bundle_sha256=source_digest,
        executor_source_sha256=executor_digest,
    )
    ledger = tmp_path / "prior-c.csv"
    _write_result_ledger(ledger, [prior])

    executed: list[tuple[str, int]] = []

    def fake_execute_case(
        case: harness.CaseSpec,
        size_segments: int,
        **_kwargs: object,
    ) -> dict[str, object]:
        executed.append((case.case_id, size_segments))
        return _valid_prior_result(
            case,
            size_segments,
            result_hash_character="f",
            binary_sha256=binary_digest,
            source_bundle_sha256=source_digest,
            executor_source_sha256=executor_digest,
        )

    monkeypatch.setattr(cli, "execute_case", fake_execute_case)
    monkeypatch.setattr(cli, "_executor", lambda _value: dummy_executor)
    monkeypatch.setattr(cli, "assert_canonical_map", lambda path: path)
    monkeypatch.setattr(
        cli,
        "canonical_graph_records",
        lambda _path: ([], [], {}),
    )
    args = cli._parser().parse_args(
        [
            "--execute",
            "--phases",
            "E",
            "--case-id",
            "E_s0",
            "--binary",
            str(binary),
            "--source-path",
            str(source),
            "--prior-ledger",
            str(ledger),
            "--output-root",
            str(tmp_path / "published"),
        ]
    )
    result = cli.run(args)
    assert executed == [("E_s0", 2_048)]
    assert result["new_execution_row_count"] == 1


def test_cli_authorization_requires_current_prior_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"current-runtime")
    source = tmp_path / "current_source.py"
    source.write_text("CURRENT = True\n", encoding="utf-8")

    def dummy_executor(**_kwargs: object) -> dict[str, object]:
        return {}

    binary_digest = harness.file_sha256(binary)
    source_digest = harness.source_bundle_sha256([source], root=ROOT)
    executor_digest = harness.inspect_executor(
        dummy_executor
    ).source_sha256
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    old_prior = _valid_prior_result(case, 144)
    matching_prior = _valid_prior_result(
        case,
        144,
        binary_sha256=binary_digest,
        source_bundle_sha256=source_digest,
        executor_source_sha256=executor_digest,
    )
    calls: list[int] = []

    def capability_blocked_low_tier(
        case: harness.CaseSpec,
        size_segments: int,
        **_kwargs: object,
    ) -> dict[str, object]:
        calls.append(size_segments)
        if size_segments == 144:
            return {
                **harness.planned_result(case, size_segments),
                "evidence_status": "EXECUTOR_CAPABILITY_BLOCKED",
            }
        return _valid_prior_result(
            case,
            size_segments,
            binary_sha256=binary_digest,
            source_bundle_sha256=source_digest,
            executor_source_sha256=executor_digest,
        )

    monkeypatch.setattr(cli, "execute_case", capability_blocked_low_tier)
    monkeypatch.setattr(cli, "_executor", lambda _value: dummy_executor)
    monkeypatch.setattr(cli, "assert_canonical_map", lambda path: path)
    monkeypatch.setattr(
        cli,
        "canonical_graph_records",
        lambda _path: ([], [], {}),
    )

    def run_with_prior(
        prior: dict[str, object],
        name: str,
    ) -> tuple[dict[str, object], Path]:
        ledger = tmp_path / f"{name}.csv"
        output_root = tmp_path / name
        _write_result_ledger(ledger, [prior])
        args = cli._parser().parse_args(
            [
                "--execute",
                "--phases",
                "B",
                "--case-id",
                case.case_id,
                "--max-segments",
                "512",
                "--binary",
                str(binary),
                "--source-path",
                str(source),
                "--prior-ledger",
                str(ledger),
                "--output-root",
                str(output_root),
            ]
        )
        return cli.run(args), output_root

    old_result, old_output = run_with_prior(old_prior, "old")
    assert calls == [144]
    assert old_result["new_execution_row_count"] == 0
    with (
        old_output / harness.OUTPUT_PATHS["framework_csv"]
    ).open("r", encoding="utf-8", newline="") as handle:
        old_rows = list(csv.DictReader(handle))
    retained = next(
        row
        for row in old_rows
        if row["case_id"] == case.case_id
        and row["size_segments"] == "144"
    )
    assert retained["binary_sha256"] == old_prior["binary_sha256"]

    calls.clear()
    matching_result, _ = run_with_prior(matching_prior, "matching")
    assert calls == [144, 512]
    assert matching_result["new_execution_row_count"] == 1


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("case_config_sha256", "0" * 64, "case_config_sha256"),
        ("map_raw_sha256", "1" * 64, "map_raw_sha256"),
        ("input_prefix_sha256", "2" * 64, "input_prefix_sha256"),
        ("binary_sha256", "", "binary_sha256"),
        ("pressure_weight_echo", "9.0", "pressure_weight"),
    ],
)
def test_prior_ledger_rejects_drift_and_forged_pass_evidence(
    tmp_path: Path,
    field: str,
    replacement: str,
    message: str,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    row = _valid_prior_result(case, 144)
    row[field] = replacement
    ledger = tmp_path / f"drift-{field}.csv"
    _write_result_ledger(ledger, [row])
    with pytest.raises(harness.HarnessValidationError, match=message):
        harness.load_result_ledger(ledger, root=ROOT)


def test_prior_not_run_never_overwrites_current_plan() -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    planned = harness.planned_result(case, 144)
    stale = {**planned, "blocker": "stale prior planning text"}
    merged = cli._merge_evidence_rows([planned], [stale], [])
    assert merged == [planned]


def test_frozen_parsed_control_remains_not_run_reference_evidence(
    tmp_path: Path,
) -> None:
    control = next(
        row
        for row in harness.load_control_evidence(ROOT)
        if row["case_id"]
        == "B_control_historical_hca_original_entry_time_tth"
    )
    ledger = tmp_path / "control.csv"
    _write_result_ledger(ledger, [control])
    admitted = harness.load_result_ledger(ledger, root=ROOT)
    assert len(admitted) == 1
    assert admitted[0]["execution_status"] == "NOT_RUN"
    assert admitted[0]["gate_status"] == "NOT_APPLICABLE"
    assert admitted[0]["evidence_status"] == (
        "PARSED_HISTORICAL_HCA_NOT_FRESH_RERUN"
    )


def test_repeat_mismatch_or_failed_repeat_cannot_authorize_next_tier() -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    first = _valid_prior_result(
        case,
        144,
        repeat_index=1,
        result_hash_character="a",
    )
    mismatched = _valid_prior_result(
        case,
        144,
        repeat_index=2,
        result_hash_character="f",
    )
    blockers = harness.authorization_blockers(
        case,
        512,
        [first, mismatched],
        required_repeat_count=2,
    )
    assert any("prior tier 144" in blocker for blocker in blockers)

    failed = {**mismatched, "gate_status": "FAIL"}
    blockers = harness.authorization_blockers(
        case,
        512,
        [first, failed],
        required_repeat_count=2,
    )
    assert any("prior tier 144" in blocker for blocker in blockers)


def test_cli_applies_repeat_consistency_before_authorizing_next_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"repeat-runtime")

    def mismatching_execute_case(
        case: harness.CaseSpec,
        size_segments: int,
        **_kwargs: object,
    ) -> dict[str, object]:
        calls.append(size_segments)
        character = "a" if len(calls) == 1 else "f"
        return _valid_prior_result(
            case,
            size_segments,
            result_hash_character=character,
        )

    monkeypatch.setattr(cli, "execute_case", mismatching_execute_case)
    monkeypatch.setattr(cli, "_executor", lambda _value: lambda **_kwargs: {})
    monkeypatch.setattr(cli, "assert_canonical_map", lambda path: path)
    monkeypatch.setattr(
        cli,
        "canonical_graph_records",
        lambda _path: ([], [], {}),
    )
    args = cli._parser().parse_args(
        [
            "--execute",
            "--phases",
            "B",
            "--case-id",
            "B5_event_corrected_handwritten",
            "--max-segments",
            "512",
            "--repeat",
            "2",
            "--binary",
            str(binary),
            "--output-root",
            str(tmp_path / "published"),
        ]
    )
    result = cli.run(args)
    assert calls == [144, 144]
    assert result["new_execution_row_count"] == 2
    with (
        tmp_path
        / "published"
        / harness.OUTPUT_PATHS["framework_csv"]
    ).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    tier_144 = [
        row
        for row in rows
        if row["case_id"] == "B5_event_corrected_handwritten"
        and row["size_segments"] == "144"
    ]
    tier_512 = [
        row
        for row in rows
        if row["case_id"] == "B5_event_corrected_handwritten"
        and row["size_segments"] == "512"
    ]
    assert {row["repeat_consistency"] for row in tier_144} == {"MISMATCH"}
    assert {row["gate_status"] for row in tier_144} == {"FAIL"}
    assert len(tier_512) == 1
    assert tier_512[0]["execution_status"] == "NOT_RUN"


def test_cross_phase_anchors_cannot_be_bypassed_at_later_tiers() -> None:
    scorer = next(
        case
        for case in harness.scorer_closed_loop_cases()
        if case.scorer_label == "S0"
    )
    scorer_2048 = _valid_prior_result(scorer, 2_048)
    assert any(
        "C_R3 8192" in blocker
        for blocker in harness.authorization_blockers(
            scorer,
            8_192,
            [scorer_2048],
            allow_8192=True,
        )
    )

    pibt = next(
        case
        for case in harness.pibt_depth_cases()
        if case.pibt_label == "P0"
    )
    pibt_2048 = _valid_prior_result(pibt, 2_048)
    assert any(
        "E_S0 8192" in blocker
        for blocker in harness.authorization_blockers(
            pibt,
            8_192,
            [pibt_2048],
            allow_8192=True,
        )
    )

    stable = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "no_fault"
    )
    stable_2048 = _valid_prior_result(stable, 2_048)
    assert any(
        "G_c6 8192" in blocker
        for blocker in harness.authorization_blockers(
            stable,
            8_192,
            [stable_2048],
            allow_8192=True,
        )
    )

    fault = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "single_immediate"
    )
    fault_2048 = _valid_prior_result(fault, 2_048)
    assert any(
        "H_stable_no_fault" in blocker
        for blocker in harness.authorization_blockers(
            fault,
            8_192,
            [fault_2048],
            allow_8192=True,
        )
    )


def test_cli_rejects_more_than_two_reviewed_c_resources() -> None:
    args = cli._parser().parse_args(
        [
            "--phases",
            "C",
            "--promoted-resource",
            "R0",
            "--promoted-resource",
            "R1",
            "--promoted-resource",
            "R2",
        ]
    )
    with pytest.raises(ValueError, match="at most two"):
        cli.run(args)


def test_phase_j_requires_a_matching_8192_preflight() -> None:
    cases = {case.case_id: case for case in harness.original_scale_cases()}
    pressure = {
        case.control_label: case for case in harness.pressure_credit_cases()
    }
    framework = {
        case.framework_label: case for case in harness.framework_delta_cases()
    }

    f1 = cases["J_F1_best_rule_bounded_pibt"]
    assert any(
        "G_c6 8192" in blocker
        for blocker in harness.authorization_blockers(
            f1,
            harness.FULL_SIZE_SEGMENTS,
            [],
            allow_full=True,
            promoted_finalists=[f1.candidate_id],
        )
    )
    assert harness.authorization_blockers(
        f1,
        harness.FULL_SIZE_SEGMENTS,
        [_valid_prior_result(pressure["C6"], 8_192)],
        allow_full=True,
        promoted_finalists=[f1.candidate_id],
    ) == []

    f2 = cases["J_F2_frozen_scorer_bounded_pibt"]
    assert f2.control_label == "C0"
    assert harness.authorization_blockers(
        f2,
        harness.FULL_SIZE_SEGMENTS,
        [_valid_prior_result(framework["B6"], 8_192)],
        allow_full=True,
        promoted_finalists=[f2.candidate_id],
    ) == []

    pibt_off = cases["J_control_pibt_off"]
    assert harness.authorization_blockers(
        pibt_off,
        harness.FULL_SIZE_SEGMENTS,
        [_valid_prior_result(pressure["C5"], 8_192)],
        allow_full=True,
        promoted_finalists=[pibt_off.candidate_id],
    ) == []

    r0 = cases["J_control_resource_r0"]
    assert any(
        "lacks a fully matched 8192 preflight" in blocker
        for blocker in harness.authorization_blockers(
            r0,
            harness.FULL_SIZE_SEGMENTS,
            [],
            allow_full=True,
            promoted_finalists=[r0.candidate_id],
        )
    )


def test_fault_metrics_require_true_availability_flags(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "single_immediate"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"fault-runtime")

    def unavailable_fault_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "fault_affected_bag_count": 1,
            "fault_affected_completed_count": 1,
            "fault_recovery_seconds": 0.0,
            "fault_recovery_seconds_available": False,
            "repair_backlog_slope": 0.0,
            "repair_backlog_slope_available": False,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=unavailable_fault_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "fault recovery availability is missing or false" in row["blocker"]
    assert "backlog slope availability is missing or false" in row["blocker"]


def test_fault_recovery_and_backlog_metrics_must_be_finite_and_bounded(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.fault_recovery_cases()
        if case.fault_profile == "single_immediate"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"fault-runtime")

    def invalid_fault_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "fault_affected_bag_count": 1,
            "fault_affected_completed_count": 1,
            "fault_recovery_seconds": -1.0,
            "fault_recovery_seconds_available": True,
            "repair_backlog_slope": float("inf"),
            "repair_backlog_slope_available": True,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=invalid_fault_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "fault recovery seconds must be >=0" in row["blocker"]
    assert "repair backlog slope must be finite" in row["blocker"]
    assert row["repair_backlog_slope"] == ""


def test_f_requires_every_published_audit_counter(
    tmp_path: Path,
) -> None:
    case = next(
        case for case in harness.pibt_depth_cases() if case.pibt_label == "P2"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"pibt-runtime")

    def missing_handoff_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "bounded_local_pibt_applicability_count": 1,
            "bounded_local_pibt_attempt_count": 1,
            "bounded_local_pibt_prepare_count": 1,
            "bounded_local_pibt_validate_count": 1,
            "bounded_local_pibt_commit_count": 0,
            "bounded_local_pibt_rollback_count": 0,
            "bounded_local_pibt_backtrack_count": 0,
            "bounded_local_pibt_wait_for_cycle_count": 0,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        2_048,
        executor=missing_handoff_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "missing required F runtime audit metric: pibt_handoff_count" in row[
        "blocker"
    ]


def test_event_count_cannot_exceed_echoed_max_events(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"event-runtime")

    def over_limit_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        summary = {
            **payload["summary"],
            "event_count": harness.FORMAL_MAX_EVENTS + 1,
        }
        return {**payload, "summary": summary}

    row = harness.execute_case(
        case,
        144,
        executor=over_limit_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
    )
    assert row["gate_status"] == "FAIL"
    assert "exceeds max_events" in row["blocker"]


def test_summary_only_rejects_fault_and_pibt_trace_arrays(
    tmp_path: Path,
) -> None:
    case = next(
        case
        for case in harness.framework_delta_cases()
        if case.framework_label == "B5"
    )
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"trace-runtime")

    def trace_leaking_executor(**kwargs: object) -> dict[str, object]:
        payload = _successful_fake_executor(**kwargs)
        return {
            **payload,
            "fault_events": [{"kind": "fault"}],
            "pibt_events": [{"kind": "pibt"}],
        }

    row = harness.execute_case(
        case,
        144,
        executor=trace_leaking_executor,
        executor_binary=binary,
        source_paths=[Path("scripts/eval/g4irsf12_reproducible_harness.py")],
        root=ROOT,
        summary_only=True,
    )
    assert row["gate_status"] == "FAIL"
    assert "SUMMARY_ONLY_PAYLOAD_CONTAINS:fault_events" in row["blocker"]
    assert "SUMMARY_ONLY_PAYLOAD_CONTAINS:pibt_events" in row["blocker"]


def test_numeric_runtime_controls_and_source_bundle_are_frozen() -> None:
    for case in harness.all_cases():
        assert {
            name: case.runtime_controls[name]
            for name in harness.FROZEN_NUMERIC_RUNTIME_CONTROLS
        } == dict(harness.FROZEN_NUMERIC_RUNTIME_CONTROLS)
    required_sources = {
        Path("scripts/eval/g4irsf11_experiment_protocol.py"),
        Path("src/czr005/datasets/decision_trace.py"),
        Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
        Path("cpp/ics_core/runtime/expiring_first_edge_credit.hpp"),
        Path("cpp/ics_core/graph/graph.hpp"),
        Path("artifacts/models/g4e_risk_calibrated_policy.json"),
    }
    assert required_sources <= set(cli.DEFAULT_SOURCE_PATHS)
    assert len(
        harness.source_bundle_sha256(cli.DEFAULT_SOURCE_PATHS, root=ROOT)
    ) == 64


def test_cli_surface_includes_all_planned_phases_and_keeps_g4j_closed() -> None:
    args = cli._parser().parse_args([])
    assert args.phases == "B,C,E,F,G,H,J"
    assert not hasattr(args, "enable_g4j")
    assert len(harness.planned_results()) == 94
