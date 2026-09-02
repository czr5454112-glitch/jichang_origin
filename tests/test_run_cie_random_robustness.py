from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import statistics
from types import SimpleNamespace

import pytest
import yaml

from scripts.eval import run_cie_random_robustness as runner


SEEDS = [
    104729,
    130363,
    155921,
    181081,
    205759,
    232003,
    257053,
    283303,
    308081,
    333667,
]


def _manifest(path: Path) -> Path:
    value = {
        "frozen_before_formal_result_read": True,
        "random_robustness": {
            "paired_seeds": SEEDS,
            "arrival_jitter_seconds": {
                "distribution": "uniform",
                "low": -5.0,
                "high": 5.0,
            },
            "service_multiplier": {
                "distribution": "lognormal",
                "log_mean": 0.0,
                "log_sigma": 0.05,
            },
            "bootstrap_replicates": 10_000,
            "confidence_level": 0.95,
            "result_seed_removal_forbidden": True,
        },
        "representative_faults": {
            "map2": ["single_4", "pair_2_4"],
            "nanning": ["single_3", "pair_3_5"],
        },
    }
    path.write_text(yaml.safe_dump(value), encoding="utf-8")
    return path


def test_contract_is_read_exactly_from_frozen_manifest(tmp_path: Path) -> None:
    contract = runner.load_random_contract(_manifest(tmp_path / "manifest.yaml"))

    assert contract.seeds == tuple(SEEDS)
    assert contract.arrival_low == -5.0
    assert contract.arrival_high == 5.0
    assert contract.service_log_sigma == 0.05
    assert contract.bootstrap_replicates == 10_000
    assert contract.seed_removal_forbidden is True
    assert contract.representative_faults["map2"] == ("single_4", "pair_2_4")


def test_realization_is_arm_independent_and_keyed_by_task_and_node(
    tmp_path: Path,
) -> None:
    contract = runner.load_random_contract(_manifest(tmp_path / "manifest.yaml"))

    left = runner.build_realization(
        seed=SEEDS[0], task_ids=[7, 4, 7, 2], node_ids=[3, 1, 2], contract=contract
    )
    right = runner.build_realization(
        seed=SEEDS[0], task_ids=[2, 4, 7], node_ids=[2, 3, 1], contract=contract
    )

    assert left["combined_realization_sha256"] == right["combined_realization_sha256"]
    assert left["arrival_by_task_id"] == right["arrival_by_task_id"]
    assert left["service_multiplier_by_node_id"] == right[
        "service_multiplier_by_node_id"
    ]
    assert all(-5.0 <= value <= 5.0 for value in left["arrival_by_task_id"].values())
    assert all(value > 0.0 for value in left["service_multiplier_by_node_id"].values())


def test_arrival_jitter_is_shared_by_raw_bag_and_deadline_is_not_shifted(
    tmp_path: Path,
) -> None:
    contract = runner.load_random_contract(_manifest(tmp_path / "manifest.yaml"))
    realization = runner.build_realization(
        seed=SEEDS[0], task_ids=[10], node_ids=[0], contract=contract
    )
    rows = (
        {
            "segment_id": "10:0",
            "task_id": 10,
            "pass_time": 100.0,
            "original_entry_time": 90.0,
            "std": 200.0,
        },
        {
            "segment_id": "10:1",
            "task_id": 10,
            "pass_time": 120.0,
            "original_entry_time": 90.0,
            "std": 200.0,
        },
    )

    shifted = runner._jitter_rows(rows, realization)
    delta = realization["arrival_by_task_id"][10]

    assert shifted[0]["pass_time"] == pytest.approx(100.0 + delta)
    assert shifted[1]["pass_time"] == pytest.approx(120.0 + delta)
    assert shifted[0]["original_entry_time"] == shifted[1]["original_entry_time"]
    assert shifted[0]["std"] == shifted[1]["std"] == 200.0


def test_arrival_jitter_rejects_negative_time_and_preserves_precedence(
    tmp_path: Path,
) -> None:
    contract = runner.load_random_contract(_manifest(tmp_path / "manifest.yaml"))
    realization = runner.build_realization(
        seed=SEEDS[0], task_ids=[10], node_ids=[0], contract=contract
    )
    delta = realization["arrival_by_task_id"][10]
    precedence_rows = (
        {"segment_id": "10:0", "task_id": 10, "pass_time": 20.0, "std": 100.0},
        {"segment_id": "10:1", "task_id": 10, "pass_time": 25.0, "std": 100.0},
    )

    shifted = runner._jitter_rows(precedence_rows, realization)

    assert shifted[1]["pass_time"] - shifted[0]["pass_time"] == pytest.approx(5.0)
    assert shifted[0]["pass_time"] == pytest.approx(20.0 + delta)

    negative = dict(realization)
    negative["arrival_by_task_id"] = {10: -5.0}
    with pytest.raises(runner.RandomRobustnessError, match="negative pass_time"):
        runner._jitter_rows(
            ({"segment_id": "10:0", "task_id": 10, "pass_time": 1.0, "std": 100.0},),
            negative,
        )


def test_service_perturbation_covers_shared_nodes_including_other_bag_goals(
    tmp_path: Path,
) -> None:
    contract = runner.load_random_contract(_manifest(tmp_path / "manifest.yaml"))
    realization = runner.build_realization(
        seed=SEEDS[0], task_ids=[1], node_ids=[0, 1, 2], contract=contract
    )
    request = {
        "node_records": [[0, 1, 2.0], [1, 4, 3.0], [2, 2, 7.0]],
    }

    perturbed = runner._perturb_node_service(request, realization)

    for index, base in enumerate((2.0, 3.0, 7.0)):
        node_id = request["node_records"][index][0]
        assert perturbed["node_records"][index][2] == pytest.approx(
            base * realization["service_multiplier_by_node_id"][node_id]
        )


def _args(tmp_path: Path, manifest: Path, *, arm: str = "P0D0") -> argparse.Namespace:
    binary = tmp_path / "czr005_cpp.pyd"
    binary.write_bytes(b"random-test-binary")
    workload = tmp_path / "workload.jsonl"
    workload.write_text('{"segment_id":"1:0"}\n', encoding="utf-8")
    return argparse.Namespace(
        map="map2",
        load_factor=2.0,
        arm=arm,
        seed=SEEDS[0],
        binary=binary,
        output=tmp_path / f"{arm}.json",
        revision_manifest=manifest,
        canonical_workload=None,
        load_manifest=tmp_path / "loads.json",
        nanning_task_dir=tmp_path,
        nanning_map_profile=tmp_path / "nanning.json",
        nanning_hca_root=tmp_path,
        map2_workload_1x=workload,
        map2_workload_2x=workload,
        map2_hca_case_root=tmp_path / "map2_hca",
        dry_run=True,
        force=False,
    )


def _base_prepare(binary: Path, workload_path: Path) -> tuple[object, ...]:
    rows = (
        {
            "segment_id": "1:0",
            "task_id": 1,
            "pass_time": 100.0,
            "original_entry_time": 95.0,
            "std": 300.0,
            "start": 0,
            "goal": 1,
        },
    )
    workload = SimpleNamespace(
        rows=rows,
        raw_bag_count=1,
        segment_count=1,
        source_path=workload_path,
    )
    request = {
        "node_records": [[0, 1, 0.2], [1, 2, 0.4]],
        "edge_records": [[0, 1, 2.0, 1.0]],
        "heuristic_time": [[0.0, 2.2], [9.0, 0.0]],
        "bag_records": [("1:0", 1, 100.0, 300.0, 0, 1, "node_0")],
        "minimum_service_seconds": 0.001,
        "scorer_mode": "S4_queue_aware_rule_only",
        "s4_score_component_mask": 0,
        "queue_time_scaling": "raw_count_as_seconds",
        "enable_s4_local_potential_descent_guard": True,
        "enable_s4_direct_neighbor_merge_calendar_visibility": True,
        "enable_cie_component_activation": True,
        "merge_grant_rule": "M1",
        "merge_grant_timing_mode": "jit_fifo",
        "g4irsf20_event_hotpath_policy": "E2",
        "expected_binary_path": str(binary.resolve()),
    }
    prepared = {
        "cell_id": "P0D0",
        "potential": {
            "selected": "ff",
            "selected_label": "H_FF",
            "selected_matrix_sha256": "0" * 64,
            "artifacts": {},
            "selection_changes_only_heuristic_time": True,
        },
    }
    release = {"mode": "canonical", "formal_same_hca_release_input": False}
    return "case", workload, request, release, prepared


def test_both_arms_receive_identical_random_realization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    left_args = _args(tmp_path, manifest, arm="P0D0")
    right_args = _args(tmp_path, manifest, arm="P1D1")
    prepared = _base_prepare(Path(left_args.binary), Path(left_args.map2_workload_2x))
    monkeypatch.setattr(
        runner.factorial,
        "prepare_cell",
        lambda _args: deepcopy(prepared),
    )
    contract = runner.load_random_contract(manifest)

    _case, _workload, left_request, _release, left = runner.prepare_randomized_cell(
        left_args, contract
    )
    _case, _workload, right_request, _release, right = runner.prepare_randomized_cell(
        right_args, contract
    )

    assert left["perturbation"]["combined_realization_sha256"] == right[
        "perturbation"
    ]["combined_realization_sha256"]
    assert left_request["node_records"] == right_request["node_records"]
    assert left_request["node_records"][1][2] != 0.4
    assert left_request["bag_records"] == right_request["bag_records"]
    assert left_request["s4_score_component_mask"] == 0
    assert right_request["s4_score_component_mask"] == 15
    assert left_request["heuristic_time"] != right_request["heuristic_time"]
    service_contract = left["perturbation"]["node_service_multiplier"]
    assert service_contract["all_physical_node_records_receive_multiplier"] is True
    assert service_contract["per_bag_goal_service_not_executed"] is True
    assert "source or transit" in service_contract["goal_exclusion_semantics"]


def test_one_x_starts_from_hca_aligned_base_but_randomized_release_is_not_hca_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    args = _args(tmp_path, manifest)
    args.load_factor = 1.0
    prepared = list(
        _base_prepare(Path(args.binary), Path(args.map2_workload_1x))
    )
    prepared[3] = {
        "mode": "same_hca",
        "same_hca_release_trace_pass": True,
        "formal_same_hca_release_input": True,
        "evidence": {"pass": True},
    }
    observed: dict[str, object] = {}

    def fake_prepare(projected: argparse.Namespace) -> tuple[object, ...]:
        observed["release_mode"] = projected.release_mode
        observed["map2_hca_case_root"] = projected.map2_hca_case_root
        return deepcopy(tuple(prepared))

    monkeypatch.setattr(runner.factorial, "prepare_cell", fake_prepare)
    contract = runner.load_random_contract(manifest)

    _case, _workload, _request, release, _details = (
        runner.prepare_randomized_cell(args, contract)
    )

    assert observed["release_mode"] == "same_hca"
    assert observed["map2_hca_case_root"] == args.map2_hca_case_root
    assert release["base_release_mode_before_random_jitter"] == "same_hca"
    assert release["base_same_hca_release_trace_pass"] is True
    assert release["mode"] == "paired_random_jitter_from_same_hca"
    assert release["paired_random_jitter_applied"] is True
    assert release["same_hca_release_trace_pass"] is False
    assert release["formal_same_hca_release_input"] is False
    assert release["formal_hca_cross_algorithm_timing_eligible"] is False


def test_two_x_execution_forces_timing_na_and_reports_fault_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    args = _args(tmp_path, manifest)
    args.dry_run = False
    prepared = _base_prepare(Path(args.binary), Path(args.map2_workload_2x))
    monkeypatch.setattr(runner.factorial, "prepare_cell", lambda _args: deepcopy(prepared))
    monkeypatch.setattr(
        runner.factorial,
        "_paper_subjects",
        lambda *_args, **_kwargs: (
            {"pass": True},
            {
                "full_population_raw_bag_timing": {
                    "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
                    "raw_bag_count": None,
                    "survivor_or_common_cohort_used": False,
                    "metrics_seconds": None,
                }
            },
        ),
    )
    monkeypatch.setattr(
        runner.cie_business,
        "summarize",
        lambda *_args, **_kwargs: {"denominator_raw_bags": 1},
    )

    result = runner.execute_run(
        args,
        executor=lambda **_request: {
            "summary": {"completed_count": 1, "failed_count": 0},
            "bags": [{"segment_id": "1:0"}],
        },
    )

    assert result["status"] == "COMPLETE"
    assert result["paper_subjects"]["full_population_raw_bag_timing"]["metrics_seconds"] is None
    assert result["representative_fixed_faults"]["status"].startswith("BLOCKED_N_M")
    assert result["representative_fixed_faults"]["fabricated_zero_or_surrogate_result"] is False


def _business(value: float) -> dict[str, object]:
    return {
        "completed_raw_bag_count": 100,
        "completion_rate": 1.0,
        "on_time_raw_bag_count": 90 + value,
        "on_time_rate": (90 + value) / 100.0,
        "missed_bag_count": 10 - value,
        "missed_bag_rate": (10 - value) / 100.0,
        "tardiness_seconds": {
            "fixed_horizon_all_population_lower_bound": {
                "sum": 1000.0 - value,
                "mean": 10.0 - value / 100.0,
                "p95": 20.0 - value,
                "p99": 30.0 - value,
                "max": 40.0 - value,
            }
        },
        "completion_targets": {
            f"time_to_{percent}_percent": {
                "reached": True,
                "elapsed_from_first_arrival_seconds": 1000.0 + int(percent) - value,
            }
            for percent in ("90", "95", "99")
        },
        "backlog": {
            "raw_bag_total": {"backlog_area_seconds": 5000.0 - value, "peak_backlog": 50 - value},
            "raw_bag_source_until_all_segments_admitted": {"backlog_area_seconds": 3000.0 - value},
            "raw_bag_network_after_all_segments_admitted": {"backlog_area_seconds": 2000.0 - value},
        },
    }


def test_random_metric_extractor_rejects_uncorrected_incomplete_legacy_area() -> None:
    business = _business(0.0)
    business["fixed_horizon_seconds"] = 100.0
    backlog = business["backlog"]
    backlog["raw_bag_total"].update(
        arrival_count=10,
        departure_count=8,
        end_backlog=2,
        drain_time_seconds=5.0,
    )
    backlog["raw_bag_source_until_all_segments_admitted"].update(
        arrival_count=10,
        departure_count=9,
        end_backlog=1,
        drain_time_seconds=3.0,
    )
    backlog["raw_bag_network_after_all_segments_admitted"].update(
        arrival_count=9,
        departure_count=8,
        end_backlog=1,
        drain_time_seconds=2.0,
    )
    artifact = {
        "load_factor": 2.0,
        "paper_subjects": {
            "fixed_denominator_business": business,
            "full_population_raw_bag_timing": {
                "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
                "metrics_seconds": None,
            },
        },
    }

    uncorrected = runner._metrics_from_run(artifact)
    view = runner.backlog_correction.correction_view(
        business, raw_last_arrival=80.0
    )
    corrected = runner._metrics_from_run(artifact, backlog_view=view)

    assert uncorrected["total_backlog_area_seconds"] is None
    assert corrected["total_backlog_area_seconds"] == 5030.0
    assert corrected["source_backlog_area_seconds"] == 3017.0
    assert corrected["network_backlog_area_seconds"] == 2015.0


def _fake_run(manifest: Path, seed: int, arm: str, value: float) -> dict[str, object]:
    contract = runner.load_random_contract(manifest)
    return {
        "schema": runner.SCHEMA,
        "native_execution_started": True,
        "status": "COMPLETE",
        "map": "map2",
        "load_factor": 2.0,
        "seed": seed,
        "arm": arm,
        "random_contract": {"manifest_sha256": contract.manifest_sha256},
        "perturbation": {
            "combined_realization_sha256": f"paired-{seed}",
            "base_arrival_schedule_sha256": "base-arrivals",
            "base_node_service_profile_sha256": "base-services",
            "randomized_arrival_schedule_sha256": f"random-arrivals-{seed}",
            "randomized_node_service_profile_sha256": f"random-services-{seed}",
        },
        "provenance": {
            "workload_sha256": "workload",
            "git_commit": "experiment-commit",
            "binary_sha256": "binary",
        },
        "release_protocol": {
            "base_release_mode_before_random_jitter": "canonical",
            "base_same_hca_release_trace_pass": False,
            "mode": "paired_random_jitter_from_canonical",
            "paired_random_jitter_applied": True,
            "same_hca_release_trace_pass": False,
            "formal_same_hca_release_input": False,
            "formal_hca_cross_algorithm_timing_eligible": False,
        },
        "population": {"raw_bag_count": 100, "segment_count": 120},
        "execution_integrity": {"pass": True},
        "paper_subjects": {
            "fixed_denominator_business": _business(value),
            "full_population_raw_bag_timing": {
                "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
                "metrics_seconds": None,
            },
        },
    }


def _aggregate_one_scenario(
    root: Path, manifest: Path
) -> tuple[list[dict[str, object]], dict[str, object]]:
    return runner._aggregate_for_scenarios(
        inputs=[root],
        manifest_path=manifest,
        required_scenarios=(("map2", 2.0),),
    )


def test_aggregate_uses_all_frozen_pairs_and_deterministic_bootstrap(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    for index, seed in enumerate(SEEDS):
        for arm, value in (("P0D0", float(index)), ("P1D1", float(index + 2))):
            run = _fake_run(manifest, seed, arm, value)
            run["paper_subjects"]["fixed_denominator_business"][
                "completed_raw_bag_count"
            ] = 0
            (root / f"{seed}_{arm}.json").write_text(
                json.dumps(run), encoding="utf-8"
            )

    rows, audit = _aggregate_one_scenario(root, manifest)
    rows_again, _ = _aggregate_one_scenario(root, manifest)
    on_time = next(row for row in rows if row["metric"] == "on_time_raw_bag_count")
    missed = next(row for row in rows if row["metric"] == "missed_bag_count")
    tied = next(row for row in rows if row["metric"] == "completion_rate")
    zero_baseline = next(
        row for row in rows if row["metric"] == "completed_raw_bag_count"
    )
    timing = next(row for row in rows if row["metric"] == "population_latency_mean_seconds")

    assert audit["scenario_audit"][0]["valid_seed_count"] == 10
    assert on_time["status"] == "COMPLETE_FROZEN_PAIRED_SEEDS"
    assert on_time["mean_delta_p1d1_minus_p0d0"] == pytest.approx(2.0)
    assert on_time["bootstrap_ci_low"] == pytest.approx(2.0)
    assert on_time["bootstrap_ci_high"] == pytest.approx(2.0)
    assert on_time["relative_delta_vs_p0d0_percent"] == pytest.approx(
        100.0 * 2.0 / 94.5
    )
    assert on_time["relative_delta_status"] == "AVAILABLE"
    assert on_time["paired_cohen_dz"] is None
    assert on_time["paired_cohen_dz_status"] == "N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD"
    assert (on_time["seed_win_count"], on_time["seed_tie_count"], on_time["seed_loss_count"]) == (10, 0, 0)
    assert (missed["seed_win_count"], missed["seed_tie_count"], missed["seed_loss_count"]) == (10, 0, 0)
    assert (tied["seed_win_count"], tied["seed_tie_count"], tied["seed_loss_count"]) == (0, 10, 0)
    assert on_time["failed_seed_rate"] == 0.0
    assert zero_baseline["relative_delta_vs_p0d0_percent"] is None
    assert zero_baseline["relative_delta_status"] == "N_M_ZERO_P0D0_MEAN"
    assert rows == rows_again
    assert timing["status"] == "N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED"
    assert timing["mean_delta_p1d1_minus_p0d0"] is None


def test_paired_cohen_dz_and_directional_seed_counts(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    for index, seed in enumerate(SEEDS):
        for arm, value in (("P0D0", float(index)), ("P1D1", float(2 * index))):
            (root / f"{seed}_{arm}.json").write_text(
                json.dumps(_fake_run(manifest, seed, arm, value)), encoding="utf-8"
            )

    rows, audit = _aggregate_one_scenario(root, manifest)
    on_time = next(row for row in rows if row["metric"] == "on_time_raw_bag_count")

    expected_differences = [float(index) for index in range(10)]
    assert on_time["mean_delta_p1d1_minus_p0d0"] == pytest.approx(4.5)
    assert on_time["paired_cohen_dz"] == pytest.approx(
        statistics.fmean(expected_differences)
        / statistics.stdev(expected_differences)
    )
    assert on_time["paired_cohen_dz_status"] == "AVAILABLE"
    assert (on_time["seed_win_count"], on_time["seed_tie_count"], on_time["seed_loss_count"]) == (9, 1, 0)
    assert audit["scenario_audit"][0]["failed_seed_rate"] == 0.0


def test_failed_seed_rate_blocks_bootstrap_and_effects(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    for index, seed in enumerate(SEEDS):
        for arm in runner.ARMS:
            value = _fake_run(manifest, seed, arm, float(index))
            if seed == SEEDS[-1] and arm == "P1D1":
                value["status"] = "FAILED_INTEGRITY"
                value["execution_integrity"] = {"pass": False}
            (root / f"{seed}_{arm}.json").write_text(
                json.dumps(value), encoding="utf-8"
            )

    rows, audit = _aggregate_one_scenario(root, manifest)
    on_time = next(row for row in rows if row["metric"] == "on_time_raw_bag_count")

    assert audit["scenario_audit"][0]["failed_seed_count"] == 1
    assert audit["scenario_audit"][0]["failed_seed_rate"] == pytest.approx(0.1)
    assert on_time["failed_seed_count"] == 1
    assert on_time["failed_seed_rate"] == pytest.approx(0.1)
    assert on_time["status"] == "INCOMPLETE_NO_BOOTSTRAP_SEED_REMOVAL_FORBIDDEN"
    assert on_time["bootstrap_ci_low"] is None
    assert on_time["paired_cohen_dz"] is None
    assert on_time["seed_win_count"] is None


def test_aggregate_refuses_mismatched_paired_realization(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    for seed in SEEDS:
        for arm in runner.ARMS:
            value = _fake_run(manifest, seed, arm, 0.0)
            if seed == SEEDS[0] and arm == "P1D1":
                value["perturbation"]["combined_realization_sha256"] = "different"
            (root / f"{seed}_{arm}.json").write_text(
                json.dumps(value), encoding="utf-8"
            )

    with pytest.raises(runner.RandomRobustnessError, match="realization mismatch"):
        _aggregate_one_scenario(root, manifest)


def test_aggregate_rejects_populated_two_x_timing(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    for seed in SEEDS:
        for arm in runner.ARMS:
            value = _fake_run(manifest, seed, arm, 0.0)
            if seed == SEEDS[0]:
                value["paper_subjects"]["full_population_raw_bag_timing"] = {
                    "status": "FULL_POPULATION_RAW_BAG_TIMING",
                    "metrics_seconds": {
                        "paper_network_from_admission": {"mean": 1.0}
                    },
                }
            (root / f"{seed}_{arm}.json").write_text(
                json.dumps(value), encoding="utf-8"
            )

    with pytest.raises(runner.RandomRobustnessError, match="non-N/A 2x timing"):
        _aggregate_one_scenario(root, manifest)


def test_aggregate_rejects_randomized_release_contract_mismatch(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    value = _fake_run(manifest, SEEDS[0], "P0D0", 0.0)
    value["release_protocol"]["mode"] = "canonical"
    (root / "bad_release.json").write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        runner.RandomRobustnessError, match="randomized release contract mismatch"
    ):
        _aggregate_one_scenario(root, manifest)


def test_unreached_time_to_x_is_nm_not_imputed(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    for index, seed in enumerate(SEEDS):
        for arm in runner.ARMS:
            value = _fake_run(manifest, seed, arm, float(index))
            if seed == SEEDS[-1] and arm == "P1D1":
                value["paper_subjects"]["fixed_denominator_business"][
                    "completion_targets"
                ]["time_to_95_percent"] = {
                    "reached": False,
                    "elapsed_from_first_arrival_seconds": None,
                }
            (root / f"{seed}_{arm}.json").write_text(
                json.dumps(value), encoding="utf-8"
            )

    rows, _audit = _aggregate_one_scenario(root, manifest)
    time_to_95 = next(
        row for row in rows if row["metric"] == "time_to_95_percent_seconds"
    )

    assert time_to_95["status"] == "N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED"
    assert time_to_95["p1d1_mean"] is None
    assert time_to_95["bootstrap_ci_low"] is None


def test_incomplete_seed_set_is_rejected_before_aggregation(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    for arm in runner.ARMS:
        (root / f"{arm}.json").write_text(
            json.dumps(_fake_run(manifest, SEEDS[0], arm, 0.0)), encoding="utf-8"
        )

    with pytest.raises(runner.RandomRobustnessError, match="executed artifacts"):
        _aggregate_one_scenario(root, manifest)


def _formal_campaign_run(
    manifest: Path,
    *,
    map_name: str,
    load: float,
    seed: int,
    arm: str,
) -> dict[str, object]:
    value = _fake_run(manifest, seed, arm, 0.0)
    scenario = f"{map_name}-{load:g}"
    base_release = "same_hca" if load == 1.0 else "canonical"
    value["map"] = map_name
    value["load_factor"] = load
    value["perturbation"].update(
        {
            "combined_realization_sha256": f"{scenario}-paired-{seed}",
            "base_arrival_schedule_sha256": f"{scenario}-base-arrivals",
            "base_node_service_profile_sha256": f"{scenario}-base-services",
            "randomized_arrival_schedule_sha256": (
                f"{scenario}-random-arrivals-{seed}"
            ),
            "randomized_node_service_profile_sha256": (
                f"{scenario}-random-services-{seed}"
            ),
        }
    )
    value["provenance"]["workload_sha256"] = f"{scenario}-workload"
    value["release_protocol"].update(
        {
            "base_release_mode_before_random_jitter": base_release,
            "base_same_hca_release_trace_pass": load == 1.0,
            "mode": f"paired_random_jitter_from_{base_release}",
        }
    )
    value["population"] = {
        "raw_bag_count": int(100 * load),
        "segment_count": int(120 * load),
    }
    # Preserve all 100 executed artifacts while avoiding expensive bootstrap
    # work in campaign-gate tests.
    value["status"] = "FAILED_INTEGRITY"
    value["execution_integrity"] = {"pass": False}
    return value


def _write_formal_campaign(
    root: Path,
    manifest: Path,
    *,
    omit_scenario: tuple[str, float] | None = None,
    mutate: object | None = None,
) -> None:
    root.mkdir()
    for map_name, load in runner.FORMAL_NONFAULT_SCENARIOS:
        if (map_name, load) == omit_scenario:
            continue
        for seed in SEEDS:
            for arm in runner.ARMS:
                value = _formal_campaign_run(
                    manifest,
                    map_name=map_name,
                    load=load,
                    seed=seed,
                    arm=arm,
                )
                if callable(mutate):
                    mutate(value, map_name, load, seed, arm)
                (root / f"{map_name}_{load:g}_{seed}_{arm}.json").write_text(
                    json.dumps(value), encoding="utf-8"
                )


def test_formal_aggregate_requires_and_accepts_exactly_100_executed_artifacts(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    _write_formal_campaign(root, manifest)

    rows, audit = runner.aggregate(inputs=[root], manifest_path=manifest)

    assert audit["executed_artifact_count"] == 100
    assert audit["expected_executed_artifact_count"] == 100
    assert len(audit["scenario_audit"]) == 5
    assert rows


def test_formal_aggregate_rejects_wholly_missing_scenario(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    _write_formal_campaign(root, manifest, omit_scenario=("map2", 1.75))

    with pytest.raises(
        runner.RandomRobustnessError, match="missing_scenarios.*map2"
    ):
        runner.aggregate(inputs=[root], manifest_path=manifest)


def test_formal_aggregate_requires_one_git_and_binary_for_all_100_runs(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"

    def mutate(
        value: dict[str, object],
        map_name: str,
        load: float,
        seed: int,
        arm: str,
    ) -> None:
        if (map_name, load, seed, arm) == ("map2", 1.0, SEEDS[0], "P0D0"):
            value["provenance"]["git_commit"] = "different-commit"

    _write_formal_campaign(root, manifest, mutate=mutate)

    with pytest.raises(runner.RandomRobustnessError, match="git_commit"):
        runner.aggregate(inputs=[root], manifest_path=manifest)


def test_formal_aggregate_requires_scenario_base_identity_across_seeds(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"

    def mutate(
        value: dict[str, object],
        map_name: str,
        load: float,
        seed: int,
        arm: str,
    ) -> None:
        if (map_name, load, seed, arm) == ("map2", 1.75, SEEDS[-1], "P1D1"):
            value["perturbation"]["base_arrival_schedule_sha256"] = (
                "different-base-arrivals"
            )

    _write_formal_campaign(root, manifest, mutate=mutate)

    with pytest.raises(
        runner.RandomRobustnessError, match="scenario base identity mismatch"
    ):
        runner.aggregate(inputs=[root], manifest_path=manifest)
