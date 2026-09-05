from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts.eval import run_cie_random_factorial_complete as runner


SEEDS = list(runner.paired.EXPECTED_PAIRED_SEEDS)


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


def _args(tmp_path: Path, manifest: Path, arm: str) -> argparse.Namespace:
    binary = tmp_path / "czr005_cpp.pyd"
    binary.write_bytes(b"frozen-four-arm-binary")
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
        load_manifest=tmp_path / "load-manifest.json",
        nanning_task_dir=tmp_path,
        nanning_map_profile=tmp_path / "nanning.json",
        nanning_hca_root=tmp_path,
        map2_workload_1x=workload,
        map2_workload_2x=workload,
        map2_hca_case_root=tmp_path / "map2-hca",
        dry_run=True,
        force=False,
    )


def _prepared(binary: Path, workload: Path) -> tuple[object, ...]:
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
    workload_view = SimpleNamespace(
        rows=rows,
        raw_bag_count=1,
        segment_count=1,
        source_path=workload,
    )
    request = {
        "node_records": [[0, 1, 0.2], [1, 2, 0.4]],
        "edge_records": [[0, 1, 2.0, 1.0]],
        "heuristic_time": [[0.0, 2.2], [9.0, 0.0]],
        "bag_records": [("1:0", 1, 100.0, 300.0, 0, 1, "node_0")],
        "minimum_service_seconds": 0.001,
        "scorer_mode": "S4_queue_aware_rule_only",
        "s4_score_component_mask": 15,
        "queue_time_scaling": "raw_count_as_seconds",
        "enable_s4_local_potential_descent_guard": True,
        "enable_s4_direct_neighbor_merge_calendar_visibility": True,
        "enable_cie_component_activation": True,
        "merge_grant_rule": "M1",
        "merge_grant_timing_mode": "jit_fifo",
        "g4irsf20_event_hotpath_policy": "E2",
        "expected_binary_path": str(binary.resolve()),
    }
    release = {"mode": "canonical", "formal_same_hca_release_input": False}
    details = {
        "cell_id": "P0D0",
        "potential": {
            "selected": "ff",
            "selected_label": "H_FF",
            "selected_matrix_sha256": "0" * 64,
            "artifacts": {},
            "selection_changes_only_heuristic_time": True,
        },
    }
    return "case", workload_view, request, release, details


def test_missing_arms_use_same_realization_and_only_the_frozen_two_factors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    p1d0 = _args(tmp_path, manifest, "P1D0")
    p0d1 = _args(tmp_path, manifest, "P0D1")
    prepared = _prepared(Path(p1d0.binary), Path(p1d0.map2_workload_2x))
    monkeypatch.setattr(
        runner.paired.factorial, "prepare_cell", lambda _args: deepcopy(prepared)
    )
    contract = runner.paired.load_random_contract(manifest)

    _case, _workload, sa_off, _release, sa_details = (
        runner.prepare_randomized_cell(p1d0, contract)
    )
    _case, _workload, ff_full, _release, ff_details = (
        runner.prepare_randomized_cell(p0d1, contract)
    )

    assert sa_details["perturbation"]["combined_realization_sha256"] == (
        ff_details["perturbation"]["combined_realization_sha256"]
    )
    assert sa_off["node_records"] == ff_full["node_records"]
    assert sa_off["bag_records"] == ff_full["bag_records"]
    assert sa_off["heuristic_time"] != ff_full["heuristic_time"]
    assert sa_off["s4_score_component_mask"] == 0
    assert ff_full["s4_score_component_mask"] == 15
    assert runner.paired.ARMS == {
        "P0D0": ("ff", "off"),
        "P1D1": ("sa", "full"),
    }


def _business(value: float) -> dict[str, object]:
    return {
        "fixed_horizon_seconds": 1000.0,
        "completed_raw_bag_count": 100,
        "completion_rate": 1.0,
        "on_time_raw_bag_count": 40.0 + value,
        "on_time_rate": (40.0 + value) / 100.0,
        "missed_bag_count": 60.0 - value,
        "missed_bag_rate": (60.0 - value) / 100.0,
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
            "raw_bag_total": {
                "backlog_area_seconds": 5000.0 - value,
                "peak_backlog": 50.0 - value,
                "end_backlog": 0,
            },
            "raw_bag_source_until_all_segments_admitted": {
                "backlog_area_seconds": 3000.0 - value,
                "end_backlog": 0,
            },
            "raw_bag_network_after_all_segments_admitted": {
                "backlog_area_seconds": 2000.0 - value,
                "end_backlog": 0,
            },
        },
    }


def _fake_run(
    manifest: Path,
    *,
    map_name: str,
    load: float,
    seed: int,
    arm: str,
    value: float,
) -> dict[str, object]:
    contract = runner.paired.load_random_contract(manifest)
    potential, dynamic = runner.ARMS[arm]
    scenario = f"{map_name}-{load:g}"
    base_release = "same_hca" if load == 1.0 else "canonical"
    timing = (
        {
            "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
            "metrics_seconds": None,
            "survivor_or_common_cohort_used": False,
        }
        if load == 2.0
        else {
            "status": "FULL_POPULATION_RAW_BAG_TIMING",
            "metrics_seconds": {
                "paper_network_from_admission": {
                    "mean": 100.0 - value,
                    "p95": 120.0 - value,
                    "p99": 130.0 - value,
                    "max": 140.0 - value,
                }
            },
            "survivor_or_common_cohort_used": False,
        }
    )
    return {
        "schema": runner.paired.SCHEMA,
        "native_execution_started": True,
        "status": "COMPLETE",
        "map": map_name,
        "load_factor": load,
        "seed": seed,
        "arm": arm,
        "algorithm": {
            "cell_id": arm,
            "policy": "s4",
            "potential": potential,
            "dynamic": dynamic,
            "s4_score_component_mask": 0 if dynamic == "off" else 15,
            "coordination_protocol": "neutral_fifo",
            "merge_grant_rule": "M1",
            "merge_grant_timing_mode": "jit_fifo",
        },
        "potential": {
            "selected_matrix_sha256": (
                f"{scenario}-ff-matrix" if potential == "ff" else f"{scenario}-sa-matrix"
            )
        },
        "random_contract": {
            "manifest_path": str(manifest.resolve()),
            "manifest_sha256": contract.manifest_sha256,
            "paired_seeds": list(contract.seeds),
            "bootstrap_replicates": contract.bootstrap_replicates,
            "confidence_level": contract.confidence_level,
            "result_seed_removal_forbidden": contract.seed_removal_forbidden,
        },
        "perturbation": {
            "arrival_jitter_seconds": {
                "distribution": "uniform",
                "low": contract.arrival_low,
                "high": contract.arrival_high,
            },
            "node_service_multiplier": {
                "distribution": "lognormal",
                "log_mean": contract.service_log_mean,
                "log_sigma": contract.service_log_sigma,
            },
            "combined_realization_sha256": f"{scenario}-realization-{seed}",
            "base_arrival_schedule_sha256": f"{scenario}-base-arrivals",
            "base_node_service_profile_sha256": f"{scenario}-base-services",
            "randomized_arrival_schedule_sha256": f"{scenario}-arrivals-{seed}",
            "randomized_node_service_profile_sha256": f"{scenario}-services-{seed}",
        },
        "provenance": {
            "workload_sha256": f"{scenario}-workload",
            "git_commit": "old-runner" if arm in ("P0D0", "P1D1") else "new-runner",
            "binary_sha256": "one-frozen-binary",
        },
        "release_protocol": {
            "base_release_mode_before_random_jitter": base_release,
            "base_same_hca_release_trace_pass": load == 1.0,
            "mode": f"paired_random_jitter_from_{base_release}",
            "paired_random_jitter_applied": True,
            "same_hca_release_trace_pass": False,
            "formal_same_hca_release_input": False,
            "formal_hca_cross_algorithm_timing_eligible": False,
        },
        "population": {"raw_bag_count": 100, "segment_count": 120},
        "execution_integrity": {"pass": True},
        "paper_subjects": {
            "fixed_denominator_business": _business(value),
            "full_population_raw_bag_timing": timing,
        },
    }


def _write_scenario(
    root: Path,
    manifest: Path,
    *,
    map_name: str = "map2",
    load: float = 2.0,
    mutate: object | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for index, seed in enumerate(SEEDS):
        values = {
            "P0D0": float(index),
            "P1D0": float(index + 1),
            "P0D1": float(index + 2),
            "P1D1": float(index + 5),
        }
        for arm, value in values.items():
            run = _fake_run(
                manifest,
                map_name=map_name,
                load=load,
                seed=seed,
                arm=arm,
                value=value,
            )
            if callable(mutate):
                mutate(run, seed, arm)
            (root / f"{map_name}_{load:g}_{seed}_{arm}.json").write_text(
                json.dumps(run), encoding="utf-8"
            )


def test_all_five_paired_contrasts_and_interaction_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    _write_scenario(root, manifest)
    monkeypatch.setattr(
        runner.paired,
        "paired_bootstrap_ci",
        lambda differences, **_kwargs: (min(differences), max(differences)),
    )

    rows, audit = runner._aggregate_for_scenarios(
        inputs=[root],
        manifest_path=manifest,
        required_scenarios=(("map2", 2.0),),
    )
    on_time = {
        row["contrast"]: row
        for row in rows
        if row["metric"] == "on_time_raw_bag_count"
    }

    assert {name: row["mean_contrast"] for name, row in on_time.items()} == {
        "A0": pytest.approx(1.0),
        "A1": pytest.approx(3.0),
        "B0": pytest.approx(2.0),
        "B1": pytest.approx(4.0),
        "Interaction": pytest.approx(2.0),
    }
    interaction = on_time["Interaction"]
    assert interaction["bootstrap_ci_low"] == pytest.approx(2.0)
    assert interaction["bootstrap_ci_high"] == pytest.approx(2.0)
    assert (
        interaction["seed_win_count"],
        interaction["seed_tie_count"],
        interaction["seed_loss_count"],
    ) == (10, 0, 0)
    assert all(row["factorial_relationship"] == "SYNERGISTIC" for row in on_time.values())
    assert interaction["completion_gate_pass"] is True
    assert audit["identity"]["git_commits"] == ["new-runner", "old-runner"]
    assert audit["identity"]["split_runner_commit_allowed_only_for_reused_existing_arms"] is True


def test_two_x_population_timing_remains_na_for_every_contrast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"
    _write_scenario(root, manifest)
    monkeypatch.setattr(
        runner.paired,
        "paired_bootstrap_ci",
        lambda differences, **_kwargs: (min(differences), max(differences)),
    )

    rows, _audit = runner._aggregate_for_scenarios(
        inputs=[root],
        manifest_path=manifest,
        required_scenarios=(("map2", 2.0),),
    )
    timing = [
        row for row in rows if row["metric"] == "population_latency_mean_seconds"
    ]

    assert len(timing) == 5
    assert all(row["status"] == "FORMAL_2X_TIMING_NA_BY_PROTOCOL" for row in timing)
    assert all(row["mean_contrast"] is None for row in timing)
    assert all(row["bootstrap_ci_low"] is None for row in timing)
    assert all(row["timing_protocol"] == "FORMAL_2X_TIMING_NA_BY_PROTOCOL" for row in timing)


def test_missing_or_failed_seed_is_never_dropped_for_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"

    def fail(run: dict[str, object], seed: int, arm: str) -> None:
        if seed == SEEDS[-1] and arm == "P0D1":
            run["status"] = "FAILED_INTEGRITY"
            run["execution_integrity"] = {"pass": False}

    _write_scenario(root, manifest, mutate=fail)
    called = False

    def forbidden_bootstrap(*_args: object, **_kwargs: object) -> tuple[float, float]:
        nonlocal called
        called = True
        return 0.0, 0.0

    monkeypatch.setattr(runner.paired, "paired_bootstrap_ci", forbidden_bootstrap)
    rows, audit = runner._aggregate_for_scenarios(
        inputs=[root],
        manifest_path=manifest,
        required_scenarios=(("map2", 2.0),),
    )

    on_time = next(
        row
        for row in rows
        if row["metric"] == "on_time_raw_bag_count" and row["contrast"] == "A0"
    )
    assert called is False
    assert on_time["status"] == "INCOMPLETE_NO_SEED_REMOVAL_OR_BOOTSTRAP"
    assert on_time["paired_seed_count"] == 9
    assert on_time["failed_seeds"] == str(SEEDS[-1])
    assert on_time["mean_contrast"] is None
    assert audit["seed_removal_forbidden"] is True


def test_four_arm_realization_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    root = tmp_path / "runs"

    def mutate(run: dict[str, object], seed: int, arm: str) -> None:
        if seed == SEEDS[0] and arm == "P1D0":
            run["perturbation"]["combined_realization_sha256"] = "different"

    _write_scenario(root, manifest, mutate=mutate)

    with pytest.raises(runner.RandomFactorialError, match="paired identity mismatch"):
        runner._aggregate_for_scenarios(
            inputs=[root],
            manifest_path=manifest,
            required_scenarios=(("map2", 2.0),),
        )


def test_cross_map_direction_annotation_uses_preferred_direction() -> None:
    rows = [
        {
            "map": map_name,
            "load_factor": 1.0,
            "metric": "tardiness_p99_seconds",
            "preferred_direction": "lower",
            "contrast": contrast,
            "status": "COMPLETE_FROZEN_FOUR_ARM_SEEDS",
            "mean_contrast": value,
            "bootstrap_ci_low": low,
            "bootstrap_ci_high": high,
        }
        for map_name, value in (("map2", -2.0), ("nanning", -1.0))
        for contrast, low, high in (("Interaction", -3.0, -0.5),)
    ]

    runner._annotate_relationships_and_cross_map(rows)

    assert all(row["factorial_relationship"] == "SYNERGISTIC" for row in rows)
    assert all(row["cross_map_direction"] == "BOTH_MAPS_IMPROVE" for row in rows)


def test_generator_emits_only_100_missing_arm_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest(tmp_path / "manifest.yaml")
    dummy = tmp_path / "input.dat"
    dummy.write_bytes(b"input")
    inputs = {
        "binary": dummy,
        "revision_manifest": manifest,
        "map2_workload_1x": dummy,
        "map2_workload_2x": dummy,
        "map2_hca_case_root": tmp_path,
        "nanning_task_dir": tmp_path,
        "nanning_hca_root": tmp_path,
        "nanning_map_profile": dummy,
        "load_manifest": dummy,
        "canonical_1p75": {"map2": dummy},
    }
    monkeypatch.setattr(runner, "_execution_inputs", lambda *_args, **_kwargs: inputs)

    commands, plan = runner.generate_commands(
        existing_root=tmp_path,
        output_root=tmp_path / "outputs",
        revision_manifest=manifest,
        dry_run=True,
    )

    assert len(commands) == 100
    assert plan["command_count"] == 100
    assert plan["seed_deletion_performed"] is False
    assert all("--arm P1D0" in command or "--arm P0D1" in command for command in commands)
    assert all("--arm P0D0" not in command and "--arm P1D1" not in command for command in commands)
    assert all("--dry-run" in command for command in commands)
    assert sum("--canonical-workload" in command for command in commands) == 20
    assert {cell[3] for cell in runner.campaign_cells()} == {"P1D0", "P0D1"}
