from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf26_paper_experiments as g26


def _prefix(rows: list[dict]) -> harness.InputPrefix:
    return harness.InputPrefix(
        size_segments=len(rows),
        rows=tuple(rows),
        prefix_sha256="unused-in-fake-test",
        raw_bag_count=len({int(row["task_id"]) for row in rows}),
        first_segment_id=str(rows[0]["segment_id"]),
        last_segment_id=str(rows[-1]["segment_id"]),
    )


def _input_rows() -> list[dict]:
    return [
        {
            "segment_id": "1:in",
            "task_id": 1,
            "original_entry_time": 0.0,
            "pass_time": 0.0,
            "std": 3_000.0,
            "start": 0,
            "goal": 1,
        },
        {
            "segment_id": "1:out",
            "task_id": 1,
            "original_entry_time": 0.0,
            "pass_time": 20.0,
            "std": 3_000.0,
            "start": 1,
            "goal": 2,
        },
        {
            "segment_id": "2:only",
            "task_id": 2,
            "original_entry_time": 40.0,
            "pass_time": 40.0,
            "std": 3_000.0,
            "start": 0,
            "goal": 2,
        },
    ]


def test_frozen_matrix_covers_all_requested_chapter_5_cases() -> None:
    cases = g26.paper_cases()
    assert len(cases) == 32
    assert len({case["case_id"] for case in cases}) == 32
    assert sum(case["case_group"] == "stable_speed" for case in cases) == 4
    assert sum(case["case_group"] == "speed_deviation" for case in cases) == 12
    assert sum(
        case["case_group"] == "all_day_line_interruption" for case in cases
    ) == 16

    degraded = g26.case_by_id("t5_4_std_2p5_dev_20")
    assert degraded["case_role"] == "degraded_actual_dual_speed_reconstruction"
    assert degraded["comparison_reference_case_id"] == "t5_2_speed_2p5"
    assert degraded["standard_speed_mps"] == 2.5
    assert degraded["actual_speed_mps"] == 2.0


def test_fault_seed_mapping_and_evidence_are_explicit() -> None:
    strong = g26.case_by_id("t5_5_fault_triple_3_5_8")
    assert strong["seed_edges"] == [[13, 23], [14, 46], [31, 32]]
    assert strong["mapping_evidence"] == "STRONG"

    mixed = g26.case_by_id("t5_5_fault_triple_4_6_7")
    assert mixed["seed_edges"] == [[24, 27], [43, 15], [33, 44]]
    assert mixed["mapping_evidence"] == "CONTAINS_RECONSTRUCTION"
    assert mixed["line_mapping_evidence"] == {
        "4": "STRONG",
        "6": "RECONSTRUCTION",
        "7": "RECONSTRUCTION",
    }

    pair_5_7 = g26.case_by_id("t5_5_fault_pair_5_7")
    assert pair_5_7["seed_edges"] == [[33, 44], [46, 36]]
    assert pair_5_7["mapping_evidence"] == (
        "ARCHIVED_CASE_SPECIFIC_LABEL_PROBE_SOURCE_PROTOCOL_UNRESOLVED"
    )
    assert pair_5_7["case_specific_seed_edge_override"] == {
        "source": "archived_workbook_sheet_33-44,46-36",
        "global_line_seed_edges": [[14, 46], [33, 44]],
        "applies_only_to_scenario": "pair_5_7",
        "changes_global_line_mapping": False,
        "fresh_reporting_status": "ARCHIVED_ONLY_SOURCE_PROTOCOL_UNRESOLVED",
        "fresh_hca_probe_canonical_complete_raw_bags": 8_013,
        "archived_workbook_cached_raw_bags": 13_939,
    }
    assert pair_5_7["protocol_fidelity"] == (
        "PROTOCOL_MISMATCH_ARCHIVED_WORKBOOK_LABEL_PROBE_"
        "FRESH_VERDICT_NOT_ADMISSIBLE"
    )
    assert g26.PAPER_LINE_SEED_EDGES[5] == (14, 46)
    assert g26.PAPER_LINE_SEED_EDGES[7] == (33, 44)


def test_dual_speed_graph_uses_actual_edges_and_standard_heuristic() -> None:
    _nodes, edges, heuristic, protocol = g26.build_speed_graph(2.5, 2.0)
    assert {edge[3] for edge in edges} == {2.0}
    assert protocol["physical_edge_speed_mps"] == 2.0
    assert protocol["heuristic_speed_mps"] == 2.5

    _n2, _e2, actual_heuristic, _p2 = g26.build_speed_graph(2.0, 2.0)
    assert any(
        standard_value < actual_value
        for standard_row, actual_row in zip(heuristic, actual_heuristic)
        for standard_value, actual_value in zip(standard_row, actual_row)
        if standard_value < 1.0e9 and actual_value < 1.0e9
    )


def test_all_day_fault_is_active_before_first_release_and_repairs_far_later() -> None:
    case = g26.case_by_id("t5_5_fault_pair_2_4")
    rows = [
        {"pass_time": 100.0, "std": 1_000.0},
        {"pass_time": 200.0, "std": 900.0},
    ]
    windows, protocol = g26.all_day_fault_windows(case, rows)
    assert [window[:2] for window in windows] == [(8, 11), (24, 27)]
    assert all(window[2] == 99.0 for window in windows)
    assert all(
        window[3] == 1_000.0 + g26.ALL_DAY_REPAIR_MARGIN_SECONDS
        for window in windows
    )
    assert protocol["immediate_local_notification"] is True
    assert protocol["fixed_runtime_limit"] == 98_259.0
    assert protocol["max_events"] == 60_000_000
    assert protocol["runtime_limit_semantics"] == (
        "explicit_max_simulation_time_aligned_to_fresh_Java_full_window"
    )
    assert protocol["repair_is_after_fixed_runtime_limit"] is True
    assert protocol["repair_event_expected_before_fixed_horizon"] is False


def test_topology_upper_bound_requires_every_leg_of_a_raw_bag() -> None:
    rows = [
        {"task_id": 1, "start": 0, "goal": 1},
        {"task_id": 1, "start": 1, "goal": 2},
        {"task_id": 2, "start": 0, "goal": 1},
    ]
    edges = [(0, 1, 1.0, 1.0), (1, 2, 1.0, 1.0)]
    evidence = g26.topology_reachable_raw_bag_upper_bound(
        rows, edges, [(1, 2)]
    )
    assert evidence["reachable_segment_count"] == 2
    assert evidence["topology_reachable_raw_bag_upper_bound"] == 1
    assert evidence["topology_unreachable_raw_bag_count"] == 1
    assert evidence["removed_seed_edges"] == [[1, 2]]


def test_real_pair_4_5_topology_upper_bound_is_zero() -> None:
    prefix = harness.load_input_prefix(harness.FULL_SIZE_SEGMENTS, root=g26.ROOT)
    _nodes, edges, _heuristic, _protocol = g26.build_speed_graph(2.5, 2.5)
    case = g26.case_by_id("t5_5_fault_pair_4_5")
    evidence = g26.topology_reachable_raw_bag_upper_bound(
        prefix.rows, edges, case["seed_edges"]
    )
    assert evidence["selected_segment_count"] == 43_603
    assert evidence["selected_raw_bag_count"] == 28_506
    assert evidence["topology_reachable_raw_bag_upper_bound"] == 0


def _real_shape_fixed_horizon_summary() -> dict:
    summary = {name: 0 for name in g26.g24.HARD_SAFETY_ZERO_FIELDS}
    summary.update({name: False for name in g26.g24.HARD_SAFETY_FALSE_FIELDS})
    summary.update(
        {
            "completed_count": 40_381,
            "failed_count": 3_222,
            "unresolved_deadlock_count": 1,
            "time_limit_reached": True,
            "fault_event_count": 1,
            "repair_event_count": 0,
        }
    )
    return summary


def test_fixed_horizon_fault_gate_accepts_real_single_2_terminal_shape() -> None:
    summary = _real_shape_fixed_horizon_summary()
    safety = g26._fixed_horizon_fault_safety(
        summary, requested=43_603, seed_fault_count=1
    )
    assert safety["pass"] is True
    assert safety["gates"]["completed_plus_failed_equals_requested"] is True
    assert safety["gates"]["unresolved_deadlock_count_finite_nonnegative"] is True
    assert safety["gates"]["fixed_time_horizon_reached"] is True
    assert safety["business_failures_counted_as_safety_failures"] is False
    # The unmodified no-fault G24 strict gate must still reject this shape.
    assert g26.g24._strict_s4_safety(summary, 43_603)["pass"] is False


def test_fixed_horizon_fault_gate_rejects_terminal_or_fault_count_drift() -> None:
    mismatch = _real_shape_fixed_horizon_summary()
    mismatch["unresolved_deadlock_count"] = -1
    assert not g26._fixed_horizon_fault_safety(
        mismatch, requested=43_603, seed_fault_count=1
    )["pass"]

    mismatch = _real_shape_fixed_horizon_summary()
    mismatch["fault_event_count"] = 0
    assert not g26._fixed_horizon_fault_safety(
        mismatch, requested=43_603, seed_fault_count=1
    )["pass"]


def _real_shape_event_censored_summary() -> dict:
    summary = {name: 0 for name in g26.g24.HARD_SAFETY_ZERO_FIELDS}
    summary.update({name: False for name in g26.g24.HARD_SAFETY_FALSE_FIELDS})
    summary.update(
        {
            "completed_count": 14_304,
            "failed_count": 29_299,
            "unresolved_deadlock_count": 9,
            "event_limit_reached": True,
            "time_limit_reached": False,
            "fault_event_count": 2,
            "repair_event_count": 0,
        }
    )
    return summary


def test_topology_saturation_gate_accepts_real_pair_4_5_shape_for_primary_only() -> None:
    safety = g26._topology_saturated_fault_safety(
        _real_shape_event_censored_summary(),
        requested=43_603,
        seed_fault_count=2,
        completed_raw_bags=0,
        topology_upper_bound=0,
    )
    assert safety["pass"] is True
    assert safety["mode"] == "TABLE_5_5_TOPOLOGY_SATURATION_EVIDENCE"
    assert safety["gates"]["event_limit_reached_as_censor"] is True
    assert safety["gates"]["completed_raw_bags_equals_topology_upper_bound"] is True
    assert safety["claim_scope"] == {
        "table_5_5_primary_completed_raw_bag_rate": True,
        "fixed_horizon_completion": False,
        "full_horizon_timing": False,
        "paper_raw_bag_tth_distribution": False,
        "deadline_success_rates": False,
    }


def test_topology_saturation_gate_rejects_unsaturated_bound() -> None:
    safety = g26._topology_saturated_fault_safety(
        _real_shape_event_censored_summary(),
        requested=43_603,
        seed_fault_count=2,
        completed_raw_bags=0,
        topology_upper_bound=1,
    )
    assert safety["pass"] is False
    assert safety["gates"]["completed_raw_bags_equals_topology_upper_bound"] is False


def test_paper_outcome_sums_finish_minus_admitted_and_counts_incomplete_as_failure() -> None:
    rows = _input_rows()
    results = [
        {
            "segment_id": "1:in",
            "task_id": 1,
            "release_time": 0.0,
            "admitted_time": 10.0,
            "finish_time": 20.0,
            "completed": True,
        },
        {
            "segment_id": "1:out",
            "task_id": 1,
            "release_time": 20.0,
            "admitted_time": 30.0,
            "finish_time": 50.0,
            "completed": True,
        },
        {
            "segment_id": "2:only",
            "task_id": 2,
            "release_time": 40.0,
            "admitted_time": 40.0,
            "finish_time": -1.0,
            "completed": False,
        },
    ]
    outcome = g26.summarize_paper_outcome(rows, results, total_raw_bags=2)
    tth = outcome["paper_raw_bag_tth"]
    assert tth["denominator"] == "sum_over_segments(finish_time-admitted_time)"
    assert tth["distribution"]["seconds"]["mean"] == 30.0
    assert outcome["completed_raw_bag_count"] == 1
    assert outcome["success"]["primary_completed_raw_bags"] == {
        "count": 1,
        "rate": 0.5,
        "definition": "all_selected_segments_completed",
    }
    assert outcome["success"]["finish_le_std"]["count"] == 1
    assert outcome["success"]["finish_le_std_minus_2700_literal"]["count"] == 1


def test_build_request_overrides_only_case_graph_and_fault_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = _input_rows()
    prefix = _prefix(rows)
    binary = tmp_path / "runtime.pyd"
    binary.write_bytes(b"fake")
    seen: dict = {}

    def fake_base(source_rows, **kwargs):
        seen["rows"] = source_rows
        seen.update(kwargs)
        return {
            "kept_control": 7,
            "fault_windows": [],
            "summary_only": True,
            "max_simulation_time": -1.0,
        }

    monkeypatch.setattr(g26.g20, "build_native_request", fake_base)
    monkeypatch.setattr(
        g26,
        "build_speed_graph",
        lambda standard, actual: (
            ["nodes"],
            ["actual_edges"],
            [["standard_heuristic"]],
            {"standard": standard, "actual": actual},
        ),
    )
    monkeypatch.setattr(
        g26,
        "all_day_fault_windows",
        lambda case, source_rows: (
            ([(8, 11, -1.0, 9.0, 0.0, False)], {"fake": True})
            if case["seed_edges"]
            else ([], {"fake": False})
        ),
    )

    request, reconstruction = g26.build_s4_request(
        g26.case_by_id("t5_5_fault_single_2"), prefix, binary=binary
    )
    assert request["kept_control"] == 7
    assert request["node_records"] == ["nodes"]
    assert request["edge_records"] == ["actual_edges"]
    assert request["heuristic_time"] == [["standard_heuristic"]]
    assert request["fault_windows"] == [(8, 11, -1.0, 9.0, 0.0, False)]
    assert request["max_simulation_time"] == 98_259.0
    assert request["max_events"] == 60_000_000
    assert request["summary_only"] is False
    assert seen["policy"] == "E2"
    assert reconstruction["fault"] == {"fake": True}

    stable, _stable_reconstruction = g26.build_s4_request(
        g26.case_by_id("t5_2_speed_2p5"), prefix, binary=binary
    )
    assert stable["max_simulation_time"] == -1.0


def test_case_resume_does_not_start_a_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    case_id = "t5_2_speed_2p5"
    output = tmp_path / f"{case_id}.json"
    artifact = {
        "schema": g26.CASE_SCHEMA,
        "status": "COMPLETE",
        "case": g26.case_by_id(case_id),
    }
    output.write_text(json.dumps(artifact), encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("completed case must be resumed without a new process")

    monkeypatch.setattr(g26.subprocess, "run", forbidden)
    value, resumed = g26.run_case_subprocess(
        case_id,
        binary=tmp_path / "unused.pyd",
        release_csv=tmp_path / "unused.csv",
        output_dir=tmp_path,
    )
    assert resumed is True
    assert value == artifact

    artifact["status"] = "FAILED_STRICT_S4_GATE"
    output.write_text(json.dumps(artifact), encoding="utf-8")
    assert g26._load_resumable_case(output, case_id) is None


def test_worker_command_is_an_independent_python_process(tmp_path: Path) -> None:
    binary = tmp_path / "runtime.pyd"
    release = tmp_path / "release.csv"
    output = tmp_path / "case.json"
    command = g26._worker_command(
        "t5_2_speed_2p5", binary=binary, release_csv=release, output=output
    )
    assert command[0] == g26.sys.executable
    assert command[2] == "_worker"
    assert command[-1] == str(output.resolve())


def test_strict_gate_failure_is_persisted_outcome_not_worker_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    case_id = "t5_5_fault_pair_4_5"

    def fake_run(command, **kwargs):
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "schema": g26.CASE_SCHEMA,
                    "status": "FAILED_STRICT_S4_GATE",
                    "case": {"case_id": case_id},
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=2, stdout="", stderr="")

    monkeypatch.setattr(g26.subprocess, "run", fake_run)
    value, resumed = g26.run_case_subprocess(
        case_id,
        binary=tmp_path / "runtime.pyd",
        release_csv=tmp_path / "release.csv",
        output_dir=tmp_path,
        force=True,
    )
    assert resumed is False
    assert value["status"] == "FAILED_STRICT_S4_GATE"


def test_aggregate_is_partial_without_running_missing_cases(tmp_path: Path) -> None:
    case_id = "t5_5_fault_single_2"
    artifact = {
        "schema": g26.CASE_SCHEMA,
        "status": "COMPLETE_FIXED_HORIZON",
        "case": g26.case_by_id(case_id),
        "outcome": {},
        "safety": {},
        "runtime": {},
    }
    (tmp_path / f"{case_id}.json").write_text(json.dumps(artifact), encoding="utf-8")
    aggregate = g26.aggregate_case_artifacts(tmp_path)
    assert aggregate["status"] == "PARTIAL_OR_FAILED"
    assert aggregate["completed_artifact_count"] == 1
    assert len(aggregate["missing_case_ids"]) == 30
    assert aggregate["executable_expected_case_count"] == 31
    assert aggregate["archived_only_not_executed_case_ids"] == [
        "t5_5_fault_pair_5_7"
    ]
    assert aggregate["protocol"]["success_denominators"][0] == (
        "completed_raw_bags/28506"
    )


def test_old_pair_5_7_edge_contract_is_archived_only_not_executed(
    tmp_path: Path,
) -> None:
    case_id = "t5_5_fault_pair_5_7"
    stale_case = g26.case_by_id(case_id)
    stale_case["seed_edges"] = [[14, 46], [33, 44]]
    stale_case.pop("case_specific_seed_edge_override")
    stale_case["mapping_evidence"] = "CONTAINS_RECONSTRUCTION"
    artifact = {
        "schema": g26.CASE_SCHEMA,
        "status": "COMPLETE_FIXED_HORIZON",
        "case": stale_case,
        "outcome": {},
        "safety": {},
        "runtime": {},
    }
    path = tmp_path / f"{case_id}.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    assert g26._load_resumable_case(path, case_id) is None
    aggregate = g26.aggregate_case_artifacts(tmp_path)
    assert case_id not in aggregate["invalid_or_failed_case_ids"]
    assert case_id not in aggregate["missing_case_ids"]
    assert aggregate["archived_only_not_executed_case_ids"] == [case_id]
    assert all(row.get("case_id") != case_id for row in aggregate["rows"])


def test_aggregate_completes_with_explicit_archived_only_gap(
    tmp_path: Path,
) -> None:
    archived_only_id = "t5_5_fault_pair_5_7"
    for case in g26.paper_cases():
        case_id = str(case["case_id"])
        if case_id == archived_only_id:
            continue
        status = (
            "COMPLETE_FIXED_HORIZON"
            if case["case_group"] == "all_day_line_interruption"
            else "COMPLETE"
        )
        artifact = {
            "schema": g26.CASE_SCHEMA,
            "status": status,
            "case": case,
            "outcome": {},
            "safety": {},
            "runtime": {},
        }
        (tmp_path / f"{case_id}.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )

    aggregate = g26.aggregate_case_artifacts(tmp_path)

    assert aggregate["status"] == "COMPLETE_WITH_ARCHIVED_ONLY_GAP"
    assert aggregate["executable_expected_case_count"] == 31
    assert aggregate["loaded_artifact_count"] == 31
    assert aggregate["completed_artifact_count"] == 31
    assert aggregate["missing_case_ids"] == []
    assert aggregate["invalid_or_failed_case_ids"] == []
    assert aggregate["archived_only_not_executed_case_ids"] == [
        archived_only_id
    ]
    assert g26.main(
        [
            "aggregate",
            "--output-dir",
            str(tmp_path),
            "--output-json",
            str(tmp_path / "aggregate.json"),
            "--output-csv",
            str(tmp_path / "aggregate.csv"),
        ]
    ) == 0


def test_aggregate_csv_uses_one_portable_line_ending() -> None:
    rendered = g26._csv_text([{"case_id": "one"}, {"case_id": "two"}])

    assert rendered == "case_id\none\ntwo\n"
    assert "\r\r\n" not in rendered


def test_dry_run_cli_never_executes_a_case(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        g26,
        "run_case_subprocess",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    assert g26.main(["dry-run"]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["execution"] == "dry_run_only_no_case_started"
    assert manifest["case_count"] == 32
    assert manifest["default_case_dir"] == (
        "outputs/runtime/g4irsf26_paper_experiments"
    )
    assert manifest["release_csv_by_standard_speed"] == {
        "1.5": "artifacts/datasets/g4irsf26_release_speed_1p5.csv",
        "2": "artifacts/datasets/g4irsf26_release_speed_2p0.csv",
        "2.5": "artifacts/datasets/g4irsf24_release_compact.csv",
        "3": "artifacts/datasets/g4irsf26_release_speed_3p0.csv",
    }


def test_default_release_trace_matches_each_standard_speed() -> None:
    assert g26.default_release_csv_for_case("t5_2_speed_1p5").name == (
        "g4irsf26_release_speed_1p5.csv"
    )
    assert g26.default_release_csv_for_case("t5_4_std_2_dev_30").name == (
        "g4irsf26_release_speed_2p0.csv"
    )
    assert g26.default_release_csv_for_case("t5_5_fault_single_2").name == (
        "g4irsf24_release_compact.csv"
    )


def test_worker_rejects_release_trace_registered_for_another_speed() -> None:
    with pytest.raises(g26.PaperExperimentError, match="registered release trace"):
        g26.execute_case_worker(
            "t5_2_speed_1p5",
            binary=Path("missing-runtime.pyd"),
            release_csv=g26.DEFAULT_RELEASE_CSV,
        )
