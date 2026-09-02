from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
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
    assert left_request["bag_records"] == right_request["bag_records"]
    assert left_request["s4_score_component_mask"] == 0
    assert right_request["s4_score_component_mask"] == 15
    assert left_request["heuristic_time"] != right_request["heuristic_time"]


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
            "binary_sha256": "binary",
        },
        "release_protocol": {"mode": "canonical"},
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


def test_aggregate_uses_all_frozen_pairs_and_deterministic_bootstrap(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    for index, seed in enumerate(SEEDS):
        for arm, value in (("P0D0", float(index)), ("P1D1", float(index + 2))):
            (root / f"{seed}_{arm}.json").write_text(
                json.dumps(_fake_run(manifest, seed, arm, value)), encoding="utf-8"
            )

    rows, audit = runner.aggregate(inputs=[root], manifest_path=manifest)
    rows_again, _ = runner.aggregate(inputs=[root], manifest_path=manifest)
    on_time = next(row for row in rows if row["metric"] == "on_time_raw_bag_count")
    timing = next(row for row in rows if row["metric"] == "population_latency_mean_seconds")

    assert audit["scenario_audit"][0]["valid_seed_count"] == 10
    assert on_time["status"] == "COMPLETE_FROZEN_PAIRED_SEEDS"
    assert on_time["mean_delta_p1d1_minus_p0d0"] == pytest.approx(2.0)
    assert on_time["bootstrap_ci_low"] == pytest.approx(2.0)
    assert on_time["bootstrap_ci_high"] == pytest.approx(2.0)
    assert rows == rows_again
    assert timing["status"] == "N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED"
    assert timing["mean_delta_p1d1_minus_p0d0"] is None


def test_aggregate_refuses_mismatched_paired_realization(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    left = _fake_run(manifest, SEEDS[0], "P0D0", 0.0)
    right = _fake_run(manifest, SEEDS[0], "P1D1", 1.0)
    right["perturbation"]["combined_realization_sha256"] = "different"
    (root / "left.json").write_text(json.dumps(left), encoding="utf-8")
    (root / "right.json").write_text(json.dumps(right), encoding="utf-8")

    with pytest.raises(runner.RandomRobustnessError, match="realization mismatch"):
        runner.aggregate(inputs=[root], manifest_path=manifest)


def test_incomplete_seed_set_is_reported_without_bootstrap(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    root.mkdir()
    for arm in runner.ARMS:
        (root / f"{arm}.json").write_text(
            json.dumps(_fake_run(manifest, SEEDS[0], arm, 0.0)), encoding="utf-8"
        )

    rows, audit = runner.aggregate(inputs=[root], manifest_path=manifest)

    assert audit["scenario_audit"][0]["status"].startswith("INCOMPLETE")
    assert len(audit["scenario_audit"][0]["missing_seeds"]) == 9
    assert all(row["bootstrap_ci_low"] is None for row in rows)
