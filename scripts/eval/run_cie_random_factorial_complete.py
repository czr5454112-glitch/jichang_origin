#!/usr/bin/env python3
"""Complete and aggregate the frozen four-arm CIE random factorial.

The already executed P0D0/P1D1 random-robustness artifacts are immutable
inputs.  This module adds only the two missing cells, P1D0 and P0D1, by
calling the same workload, perturbation, and native-executor path used by
``run_cie_random_robustness.py``.  It does not change the G31 defaults.

``run`` executes (or dry-runs) one arm/seed.  ``generate`` derives the exact
frozen input paths from the existing artifacts and writes commands for the
missing cells without deleting a seed.  ``aggregate`` requires all four arms
for every one of the ten frozen seeds in all five registered scenarios and
reports A0, A1, B0, B1, and the interaction with paired bootstrap intervals.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any, Iterable, Iterator, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import run_cie_random_robustness as paired  # noqa: E402


SUMMARY_SCHEMA = "czr005.cie_random_factorial_complete.summary.v1"
AUDIT_SCHEMA = "czr005.cie_random_factorial_complete.audit.v1"
DEFAULT_RESULT_ROOT = paired.DEFAULT_RESULT_ROOT
DEFAULT_TABLE = ROOT / "outputs/tables/cie_random_factorial_full.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/cie_random_factorial_full.md"

# P denotes the static potential and D the four dynamic S4 score terms.  These
# are the two factors already frozen in the revision manifest; this script
# does not add a scorer, guard, mode, ranker, or tunable parameter.
ARMS: Mapping[str, tuple[str, str]] = {
    "P0D0": ("ff", "off"),
    "P1D0": ("sa", "off"),
    "P0D1": ("ff", "full"),
    "P1D1": ("sa", "full"),
}
NEW_ARMS = ("P1D0", "P0D1")
FORMAL_SCENARIOS = paired.FORMAL_NONFAULT_SCENARIOS

# Coefficients are in the requested raw-difference orientation.
CONTRASTS: Mapping[str, Mapping[str, float]] = {
    "A0": {"P1D0": 1.0, "P0D0": -1.0},
    "A1": {"P1D1": 1.0, "P0D1": -1.0},
    "B0": {"P0D1": 1.0, "P0D0": -1.0},
    "B1": {"P1D1": 1.0, "P1D0": -1.0},
    "Interaction": {
        "P1D1": 1.0,
        "P1D0": -1.0,
        "P0D1": -1.0,
        "P0D0": 1.0,
    },
}
CONTRAST_FORMULAS = {
    "A0": "P1D0 - P0D0",
    "A1": "P1D1 - P0D1",
    "B0": "P0D1 - P0D0",
    "B1": "P1D1 - P1D0",
    "Interaction": "P1D1 - P1D0 - P0D1 + P0D0",
}
TIMING_METRICS = {
    metric.name
    for metric in paired.METRICS
    if metric.name.startswith("population_latency_")
}

SUMMARY_FIELDS = (
    "schema",
    "map",
    "load_factor",
    "metric",
    "metric_label",
    "preferred_direction",
    "contrast",
    "contrast_formula",
    "status",
    "paired_seed_count",
    "expected_seed_count",
    "missing_seeds",
    "failed_seeds",
    "p0d0_mean",
    "p1d0_mean",
    "p0d1_mean",
    "p1d1_mean",
    "mean_contrast",
    "bootstrap_ci_low",
    "bootstrap_ci_high",
    "bootstrap_replicates",
    "confidence_level",
    "seed_win_count",
    "seed_tie_count",
    "seed_loss_count",
    "completion_gate_status",
    "completion_gate_pass",
    "all_four_full_population_seed_count",
    "all_four_equal_completion_seed_count",
    "factorial_relationship",
    "cross_map_direction",
    "timing_protocol",
)


class RandomFactorialError(RuntimeError):
    """Raised when four-arm evidence violates the frozen paired contract."""


@contextmanager
def _four_arm_base_runner() -> Iterator[None]:
    """Expose four arms to the frozen runner only for the current call."""

    original = paired.ARMS
    paired.ARMS = ARMS
    try:
        yield
    finally:
        paired.ARMS = original


def prepare_randomized_cell(
    args: argparse.Namespace, contract: paired.RandomContract
) -> tuple[str, Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    if args.arm not in NEW_ARMS:
        raise RandomFactorialError(
            f"run interface accepts only missing arms {NEW_ARMS}: {args.arm}"
        )
    with _four_arm_base_runner():
        return paired.prepare_randomized_cell(args, contract)


def execute_run(
    args: argparse.Namespace, *, executor: Any | None = None
) -> dict[str, Any]:
    """Execute one frozen cell through the unchanged random runner."""

    if args.arm not in NEW_ARMS:
        raise RandomFactorialError(
            f"run interface accepts only missing arms {NEW_ARMS}: {args.arm}"
        )
    with _four_arm_base_runner():
        result = paired.execute_run(args, executor=executor)
    potential, dynamic = ARMS[args.arm]
    return {
        **result,
        "factorial_completion": {
            "schema": SUMMARY_SCHEMA,
            "arm": args.arm,
            "potential_factor": potential,
            "dynamic_factor": dynamic,
            "existing_arms_reused": ["P0D0", "P1D1"],
            "new_arms": list(NEW_ARMS),
            "same_frozen_realization_generator": True,
            "g31_defaults_changed": False,
            "new_scorer_guard_mode_ranker_or_parameter_added": False,
        },
    }


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise RandomFactorialError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RandomFactorialError(f"{label} must be an integer") from exc
    if result != value:
        raise RandomFactorialError(f"{label} must be an integer")
    return result


def _load(value: Any) -> float:
    try:
        return paired._load_factor(float(value))
    except (TypeError, ValueError, paired.RandomRobustnessError) as exc:
        raise RandomFactorialError(f"invalid load factor: {value}") from exc


def _get(root: Mapping[str, Any], *path: str) -> Any:
    return paired._get(root, *path)


def _artifact_complete(run: Mapping[str, Any]) -> bool:
    return (
        run.get("schema") == paired.SCHEMA
        and run.get("native_execution_started") is True
        and run.get("status") == "COMPLETE"
        and _get(run, "execution_integrity", "pass") is True
    )


def _contract_fingerprint(contract: paired.RandomContract) -> str:
    payload = {
        "seeds": list(contract.seeds),
        "arrival": {
            "distribution": "uniform",
            "low": contract.arrival_low,
            "high": contract.arrival_high,
        },
        "service": {
            "distribution": "lognormal",
            "log_mean": contract.service_log_mean,
            "log_sigma": contract.service_log_sigma,
        },
        "bootstrap_replicates": contract.bootstrap_replicates,
        "confidence_level": contract.confidence_level,
        "seed_removal_forbidden": contract.seed_removal_forbidden,
    }
    return paired._sha256_value(payload)


def _artifact_contract_fingerprint(run: Mapping[str, Any]) -> str:
    random_contract = run.get("random_contract")
    perturbation = run.get("perturbation")
    if not isinstance(random_contract, Mapping) or not isinstance(
        perturbation, Mapping
    ):
        raise RandomFactorialError("artifact lacks its random contract")
    arrival = perturbation.get("arrival_jitter_seconds")
    service = perturbation.get("node_service_multiplier")
    if not isinstance(arrival, Mapping) or not isinstance(service, Mapping):
        raise RandomFactorialError("artifact lacks random distribution identity")
    payload = {
        "seeds": random_contract.get("paired_seeds"),
        "arrival": {
            "distribution": arrival.get("distribution"),
            "low": arrival.get("low"),
            "high": arrival.get("high"),
        },
        "service": {
            "distribution": service.get("distribution"),
            "log_mean": service.get("log_mean"),
            "log_sigma": service.get("log_sigma"),
        },
        "bootstrap_replicates": random_contract.get("bootstrap_replicates"),
        "confidence_level": random_contract.get("confidence_level"),
        "seed_removal_forbidden": random_contract.get(
            "result_seed_removal_forbidden"
        ),
    }
    return paired._sha256_value(payload)


def _validate_algorithm_identity(run: Mapping[str, Any], path: Path) -> None:
    arm = str(run.get("arm"))
    if arm not in ARMS:
        raise RandomFactorialError(f"unknown arm in {path}: {arm}")
    potential, dynamic = ARMS[arm]
    algorithm = run.get("algorithm")
    if not isinstance(algorithm, Mapping):
        raise RandomFactorialError(f"algorithm identity missing: {path}")
    expected = {
        "cell_id": arm,
        "policy": "s4",
        "potential": potential,
        "dynamic": dynamic,
        "s4_score_component_mask": 0 if dynamic == "off" else 15,
        "coordination_protocol": "neutral_fifo",
        "merge_grant_rule": "M1",
        "merge_grant_timing_mode": "jit_fifo",
    }
    mismatches = [key for key, value in expected.items() if algorithm.get(key) != value]
    if mismatches:
        raise RandomFactorialError(
            f"factorial algorithm identity mismatch in {path}: {mismatches}"
        )


def _validate_release(run: Mapping[str, Any], path: Path, load: float) -> None:
    release = run.get("release_protocol")
    base = "same_hca" if load == 1.0 else "canonical"
    if not isinstance(release, Mapping) or any(
        (
            release.get("base_release_mode_before_random_jitter") != base,
            release.get("mode") != f"paired_random_jitter_from_{base}",
            release.get("paired_random_jitter_applied") is not True,
            release.get("base_same_hca_release_trace_pass") is not (load == 1.0),
            release.get("same_hca_release_trace_pass") is not False,
            release.get("formal_same_hca_release_input") is not False,
            release.get("formal_hca_cross_algorithm_timing_eligible") is not False,
        )
    ):
        raise RandomFactorialError(f"randomized release contract mismatch: {path}")


def _discover_index(
    inputs: Sequence[Path],
    *,
    contract: paired.RandomContract,
    scenarios: Sequence[tuple[str, float]],
) -> tuple[
    dict[tuple[str, float, int, str], tuple[Path, Mapping[str, Any]]],
    dict[str, Any],
]:
    normalized = tuple((str(name), _load(load)) for name, load in scenarios)
    if len(normalized) != len(set(normalized)):
        raise RandomFactorialError("required scenarios must be unique")
    expected = {
        (name, load, seed, arm)
        for name, load in normalized
        for seed in contract.seeds
        for arm in ARMS
    }
    discovered = paired._discover(inputs)
    if not discovered:
        raise RandomFactorialError("no executed random artifacts were found")
    indexed: dict[
        tuple[str, float, int, str], tuple[Path, Mapping[str, Any]]
    ] = {}
    expected_contract_fingerprint = _contract_fingerprint(contract)
    manifest_hashes: set[str] = set()
    for path, run in discovered:
        key = (
            str(run.get("map")),
            _load(run.get("load_factor")),
            _integer(run.get("seed"), "run seed"),
            str(run.get("arm")),
        )
        if key not in expected or key in indexed:
            raise RandomFactorialError(f"duplicate or unknown run identity: {key}")
        random_contract = run.get("random_contract")
        if not isinstance(random_contract, Mapping) or not isinstance(
            random_contract.get("manifest_sha256"), str
        ):
            raise RandomFactorialError(f"manifest identity missing: {path}")
        manifest_hashes.add(str(random_contract["manifest_sha256"]))
        if _artifact_contract_fingerprint(run) != expected_contract_fingerprint:
            raise RandomFactorialError(f"semantic random contract mismatch: {path}")
        _validate_algorithm_identity(run, path)
        _validate_release(run, path, key[1])
        indexed[key] = (path, run)

    missing = sorted(expected - set(indexed))
    if len(indexed) != len(expected) or missing:
        raise RandomFactorialError(
            "formal four-arm campaign requires exactly "
            f"{len(expected)} executed artifacts; found={len(indexed)}; "
            f"missing_run_count={len(missing)}; missing={missing[:12]}"
        )

    binary_hashes = {
        _get(run, "provenance", "binary_sha256") for _path, run in indexed.values()
    }
    if None in binary_hashes or len(binary_hashes) != 1:
        raise RandomFactorialError("all four arms must use one native binary SHA256")
    git_commits = sorted(
        {str(_get(run, "provenance", "git_commit")) for _path, run in indexed.values()}
    )
    if "None" in git_commits:
        raise RandomFactorialError("every artifact must record a git commit")

    base_paths = (
        ("provenance", "workload_sha256"),
        ("perturbation", "base_arrival_schedule_sha256"),
        ("perturbation", "base_node_service_profile_sha256"),
        ("release_protocol", "base_release_mode_before_random_jitter"),
        ("release_protocol", "mode"),
        ("population", "raw_bag_count"),
        ("population", "segment_count"),
    )
    pair_paths = base_paths + (
        ("perturbation", "combined_realization_sha256"),
        ("perturbation", "randomized_arrival_schedule_sha256"),
        ("perturbation", "randomized_node_service_profile_sha256"),
        ("provenance", "binary_sha256"),
    )
    for name, load in normalized:
        scenario_runs = [
            run
            for (map_name, factor, _seed, _arm), (_path, run) in indexed.items()
            if map_name == name and factor == load
        ]
        for identity_path in base_paths:
            values = {_get(run, *identity_path) for run in scenario_runs}
            if None in values or len(values) != 1:
                raise RandomFactorialError(
                    f"scenario base identity mismatch for {name} {load}x: "
                    f"{'.'.join(identity_path)}"
                )
        for seed in contract.seeds:
            runs = [indexed[(name, load, seed, arm)][1] for arm in ARMS]
            for identity_path in pair_paths:
                values = {_get(run, *identity_path) for run in runs}
                if None in values or len(values) != 1:
                    raise RandomFactorialError(
                        f"four-arm paired identity mismatch for {name} {load}x "
                        f"seed={seed}: {'.'.join(identity_path)}"
                    )
            matrices = {
                arm: _get(indexed[(name, load, seed, arm)][1], "potential", "selected_matrix_sha256")
                for arm in ARMS
            }
            if (
                not all(matrices.values())
                or matrices["P0D0"] != matrices["P0D1"]
                or matrices["P1D0"] != matrices["P1D1"]
                or matrices["P0D0"] == matrices["P1D0"]
            ):
                raise RandomFactorialError(
                    f"potential factor matrix identity mismatch for {name} {load}x "
                    f"seed={seed}"
                )
    return indexed, {
        "expected_artifact_count": len(expected),
        "executed_artifact_count": len(indexed),
        "binary_sha256": next(iter(binary_hashes)),
        "manifest_sha256_values": sorted(manifest_hashes),
        "semantic_random_contract_sha256": expected_contract_fingerprint,
        "full_manifest_hash_split_allowed_only_when_semantic_contract_matches": (
            len(manifest_hashes) > 1
        ),
        # Existing and newly completed arms necessarily come from different
        # runner commits.  The executable SHA and every physical/random input
        # remain exact; retaining both commits is more honest than rewriting
        # the original artifacts.
        "git_commits": git_commits,
        "split_runner_commit_allowed_only_for_reused_existing_arms": len(git_commits) > 1,
    }


def _raw_contrast(
    values: Mapping[str, float], coefficients: Mapping[str, float]
) -> float:
    return math.fsum(coefficients.get(arm, 0.0) * values[arm] for arm in ARMS)


def _wins_ties_losses(
    differences: Sequence[float], preferred_direction: str
) -> tuple[int, int, int]:
    if preferred_direction == "higher":
        signed = list(differences)
    elif preferred_direction == "lower":
        signed = [-value for value in differences]
    else:
        raise RandomFactorialError(
            f"unknown preferred direction: {preferred_direction}"
        )
    return (
        sum(value > 0.0 for value in signed),
        sum(value == 0.0 for value in signed),
        sum(value < 0.0 for value in signed),
    )


def _completion_gate(
    runs_by_seed: Mapping[int, Mapping[str, Mapping[str, Any]]],
    contract: paired.RandomContract,
) -> dict[str, Any]:
    full = 0
    equal = 0
    for seed in contract.seeds:
        arms = runs_by_seed.get(seed)
        if not arms:
            continue
        counts = []
        full_this_seed = True
        for arm in ARMS:
            run = arms[arm]
            count = paired._number(
                _get(run, "paper_subjects", "fixed_denominator_business", "completed_raw_bag_count")
            )
            denominator = paired._number(_get(run, "population", "raw_bag_count"))
            counts.append(count)
            full_this_seed = bool(
                full_this_seed
                and count is not None
                and denominator is not None
                and count == denominator
            )
        if None not in counts and len(set(counts)) == 1:
            equal += 1
        if full_this_seed:
            full += 1
    return {
        "all_four_full_population_seed_count": full,
        "all_four_equal_completion_seed_count": equal,
        "completion_gate_pass": full == len(contract.seeds),
        "completion_gate_status": (
            "PASS_ALL_FOUR_ARMS_FULL_POPULATION"
            if full == len(contract.seeds)
            else "FAIL_AT_LEAST_ONE_ARM_INCOMPLETE_FIXED_DENOMINATOR_ONLY"
        ),
    }


def _relationship(row: Mapping[str, Any]) -> str:
    if row.get("contrast") != "Interaction":
        raise RandomFactorialError("relationship classification needs interaction row")
    if row.get("status") != "COMPLETE_FROZEN_FOUR_ARM_SEEDS":
        return "INCONCLUSIVE"
    low = paired._number(row.get("bootstrap_ci_low"))
    high = paired._number(row.get("bootstrap_ci_high"))
    estimate = paired._number(row.get("mean_contrast"))
    if low is None or high is None or estimate is None:
        return "INCONCLUSIVE"
    if low == 0.0 and high == 0.0 and estimate == 0.0:
        return "ADDITIVE"
    if row.get("preferred_direction") == "lower":
        low, high = -high, -low
    if low > 0.0:
        return "SYNERGISTIC"
    if high < 0.0:
        return "ANTAGONISTIC"
    return "INCONCLUSIVE"


def _annotate_relationships_and_cross_map(rows: list[dict[str, Any]]) -> None:
    relationships: dict[tuple[str, float, str], str] = {}
    for row in rows:
        if row["contrast"] == "Interaction":
            relationships[(row["map"], row["load_factor"], row["metric"])] = (
                _relationship(row)
            )
    for row in rows:
        row["factorial_relationship"] = relationships.get(
            (row["map"], row["load_factor"], row["metric"]), "INCONCLUSIVE"
        )

    indexed = {
        (row["map"], row["load_factor"], row["metric"], row["contrast"]): row
        for row in rows
    }
    for row in rows:
        other_map = "nanning" if row["map"] == "map2" else "map2"
        other = indexed.get(
            (other_map, row["load_factor"], row["metric"], row["contrast"])
        )
        if other is None:
            row["cross_map_direction"] = "N_M_NO_MATCHED_OTHER_MAP_LOAD"
            continue
        left = paired._number(row.get("mean_contrast"))
        right = paired._number(other.get("mean_contrast"))
        if left is None or right is None:
            row["cross_map_direction"] = "N_M_CONTRAST_UNAVAILABLE"
            continue
        if row["preferred_direction"] == "lower":
            left, right = -left, -right
        signs = ((left > 0.0) - (left < 0.0), (right > 0.0) - (right < 0.0))
        if signs == (1, 1):
            status = "BOTH_MAPS_IMPROVE"
        elif signs == (-1, -1):
            status = "BOTH_MAPS_WORSEN"
        elif signs == (0, 0):
            status = "BOTH_MAPS_TIE"
        elif 0 in signs:
            status = "ONE_MAP_TIE_OTHER_NONZERO"
        else:
            status = "OPPOSITE_MAP_DIRECTIONS"
        row["cross_map_direction"] = status


def _aggregate_for_scenarios(
    *,
    inputs: Sequence[Path],
    manifest_path: Path,
    required_scenarios: Sequence[tuple[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    contract = paired.load_random_contract(manifest_path)
    scenarios = tuple((str(name), _load(load)) for name, load in required_scenarios)
    indexed, identity_audit = _discover_index(
        inputs, contract=contract, scenarios=scenarios
    )
    rows: list[dict[str, Any]] = []
    scenario_audits: list[dict[str, Any]] = []

    for map_name, load in scenarios:
        failed: list[int] = []
        valid: dict[int, dict[str, Mapping[str, Any]]] = {}
        for seed in contract.seeds:
            arm_runs = {
                arm: indexed[(map_name, load, seed, arm)][1] for arm in ARMS
            }
            if all(_artifact_complete(run) for run in arm_runs.values()):
                valid[seed] = arm_runs
            else:
                failed.append(seed)
        complete = not failed and len(valid) == len(contract.seeds)
        scenario_status = (
            "COMPLETE_FROZEN_FOUR_ARM_SEEDS"
            if complete
            else "INCOMPLETE_NO_SEED_REMOVAL_OR_BOOTSTRAP"
        )
        gate = _completion_gate(valid, contract)

        correction_views: dict[tuple[int, str], Mapping[str, Any] | None] = {}
        correction_statuses: dict[str, int] = {}
        for seed, arm_runs in valid.items():
            run_values = list(arm_runs.values())
            if any(
                paired.backlog_correction.requires_legacy_tail_reconstruction(run)
                for run in run_values
            ):
                recorded_manifest = _get(
                    arm_runs["P0D0"], "random_contract", "manifest_path"
                )
                reconstruction_manifest = Path(manifest_path)
                if isinstance(recorded_manifest, str):
                    candidate = Path(recorded_manifest)
                    expected_hash = _get(
                        arm_runs["P0D0"], "random_contract", "manifest_sha256"
                    )
                    if (
                        candidate.is_file()
                        and isinstance(expected_hash, str)
                        and paired._file_sha256(candidate) == expected_hash
                    ):
                        reconstruction_manifest = candidate
                raw_last_arrival, _identity = (
                    paired.backlog_correction.regenerate_random_last_raw_arrival(
                        arm_runs["P0D0"], manifest_path=reconstruction_manifest
                    )
                )
            else:
                raw_last_arrival = (
                    paired.backlog_correction.embedded_or_zero_tail_last_arrival(
                        arm_runs["P0D0"]
                    )
                )
            for arm, run in arm_runs.items():
                try:
                    view = paired.backlog_correction.correction_view(
                        paired.backlog_correction.business_payload(run),
                        raw_last_arrival=raw_last_arrival,
                    )
                    statuses = {
                        str(item.get("status"))
                        for item in view["groups"].values()
                        if isinstance(item, Mapping)
                    }
                    status = ";".join(sorted(statuses))
                except paired.backlog_correction.BacklogAreaCorrectionError as exc:
                    view = None
                    status = f"N_M_{type(exc).__name__}"
                correction_views[(seed, arm)] = view
                correction_statuses[status] = correction_statuses.get(status, 0) + 1

        values_by_seed: dict[int, dict[str, dict[str, float | None]]] = {}
        for seed, arm_runs in valid.items():
            values_by_seed[seed] = {
                arm: paired._metrics_from_run(
                    run, backlog_view=correction_views.get((seed, arm))
                )
                for arm, run in arm_runs.items()
            }

        for metric in paired.METRICS:
            arm_values: dict[str, list[float]] = {arm: [] for arm in ARMS}
            metric_status = scenario_status
            if complete:
                for seed in contract.seeds:
                    current = values_by_seed[seed]
                    if any(current[arm][metric.name] is None for arm in ARMS):
                        metric_status = (
                            "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
                            if load == 2.0 and metric.name in TIMING_METRICS
                            else "N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED"
                        )
                        break
                    for arm in ARMS:
                        arm_values[arm].append(float(current[arm][metric.name]))

            for contrast, coefficients in CONTRASTS.items():
                means: dict[str, float | None]
                differences: list[float]
                if metric_status == "COMPLETE_FROZEN_FOUR_ARM_SEEDS":
                    means = {
                        arm: statistics.fmean(values) for arm, values in arm_values.items()
                    }
                    differences = [
                        _raw_contrast(
                            {arm: arm_values[arm][index] for arm in ARMS}, coefficients
                        )
                        for index in range(len(contract.seeds))
                    ]
                    estimate: float | None = statistics.fmean(differences)
                    bootstrap_key = (
                        f"cie-four-arm-bootstrap-v1|{contract.manifest_sha256}|"
                        f"{map_name}|{load}|{metric.name}|{contrast}"
                    )
                    bootstrap_seed = int.from_bytes(
                        hashlib.sha256(bootstrap_key.encode("ascii")).digest(), "big"
                    )
                    low, high = paired.paired_bootstrap_ci(
                        differences,
                        replicates=contract.bootstrap_replicates,
                        confidence_level=contract.confidence_level,
                        bootstrap_seed=bootstrap_seed,
                    )
                    wins, ties, losses = _wins_ties_losses(
                        differences, metric.preferred_direction
                    )
                else:
                    means = {arm: None for arm in ARMS}
                    differences = []
                    estimate = low = high = None
                    wins = ties = losses = None
                rows.append(
                    {
                        "schema": SUMMARY_SCHEMA,
                        "map": map_name,
                        "load_factor": load,
                        "metric": metric.name,
                        "metric_label": metric.label,
                        "preferred_direction": metric.preferred_direction,
                        "contrast": contrast,
                        "contrast_formula": CONTRAST_FORMULAS[contrast],
                        "status": metric_status,
                        "paired_seed_count": len(valid),
                        "expected_seed_count": len(contract.seeds),
                        "missing_seeds": "",
                        "failed_seeds": ";".join(str(seed) for seed in failed),
                        "p0d0_mean": means["P0D0"],
                        "p1d0_mean": means["P1D0"],
                        "p0d1_mean": means["P0D1"],
                        "p1d1_mean": means["P1D1"],
                        "mean_contrast": estimate,
                        "bootstrap_ci_low": low,
                        "bootstrap_ci_high": high,
                        "bootstrap_replicates": contract.bootstrap_replicates,
                        "confidence_level": contract.confidence_level,
                        "seed_win_count": wins,
                        "seed_tie_count": ties,
                        "seed_loss_count": losses,
                        **gate,
                        "factorial_relationship": "PENDING",
                        "cross_map_direction": "PENDING",
                        "timing_protocol": (
                            "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
                            if load == 2.0
                            else "FULL_POPULATION_ONLY_NO_SURVIVOR_TIMING"
                        ),
                    }
                )
        scenario_audits.append(
            {
                "map": map_name,
                "load_factor": load,
                "status": scenario_status,
                "valid_seed_count": len(valid),
                "failed_seeds": failed,
                **gate,
                "backlog_area_correction_status_counts": correction_statuses,
            }
        )

    _annotate_relationships_and_cross_map(rows)
    audit = {
        "schema": AUDIT_SCHEMA,
        "manifest_path": str(Path(manifest_path).resolve()),
        "manifest_sha256": contract.manifest_sha256,
        "arms": {
            arm: {"potential": values[0], "dynamic": values[1]}
            for arm, values in ARMS.items()
        },
        "contrasts": dict(CONTRAST_FORMULAS),
        "formal_scenarios": [
            {"map": name, "load_factor": load} for name, load in scenarios
        ],
        "paired_seeds": list(contract.seeds),
        "seed_removal_forbidden": contract.seed_removal_forbidden,
        "existing_artifacts_reused_without_rewrite": ["P0D0", "P1D1"],
        "newly_executed_arms": list(NEW_ARMS),
        "g31_defaults_changed": False,
        "identity": identity_audit,
        "scenario_audit": scenario_audits,
    }
    return rows, audit


def aggregate(
    *, inputs: Sequence[Path], manifest_path: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate the exact five-scenario, 200-artifact campaign."""

    return _aggregate_for_scenarios(
        inputs=inputs,
        manifest_path=manifest_path,
        required_scenarios=FORMAL_SCENARIOS,
    )


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    from io import StringIO

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    _atomic_text(path, stream.getvalue())


def _display(value: Any) -> str:
    number = paired._number(value)
    return "N/A" if number is None else f"{number:.6g}"


def _write_report(
    path: Path, rows: Sequence[Mapping[str, Any]], audit: Mapping[str, Any]
) -> None:
    scenario_lines = []
    for item in audit["scenario_audit"]:
        scenario_lines.append(
            f"| {item['map']} | {item['load_factor']:g} | {item['status']} | "
            f"{item['valid_seed_count']}/10 | {item['completion_gate_status']} |"
        )
    selected = {
        "completed_raw_bag_count",
        "on_time_raw_bag_count",
        "tardiness_p95_seconds",
        "tardiness_p99_seconds",
        "tardiness_max_seconds",
        "time_to_95_percent_seconds",
        "time_to_99_percent_seconds",
        "total_backlog_area_seconds",
        "source_backlog_area_seconds",
        "population_latency_mean_seconds",
        "population_latency_p95_seconds",
        "population_latency_p99_seconds",
    }
    effect_lines = []
    for row in rows:
        if row["metric"] not in selected:
            continue
        effect_lines.append(
            "| {map} | {load:g} | {metric} | {contrast} | {status} | {mean} | "
            "[{low}, {high}] | {w}/{t}/{l} | {relation} | {cross} |".format(
                map=row["map"],
                load=row["load_factor"],
                metric=row["metric"],
                contrast=row["contrast"],
                status=row["status"],
                mean=_display(row["mean_contrast"]),
                low=_display(row["bootstrap_ci_low"]),
                high=_display(row["bootstrap_ci_high"]),
                w=row["seed_win_count"] if row["seed_win_count"] is not None else "N/A",
                t=row["seed_tie_count"] if row["seed_tie_count"] is not None else "N/A",
                l=row["seed_loss_count"] if row["seed_loss_count"] is not None else "N/A",
                relation=row["factorial_relationship"],
                cross=row["cross_map_direction"],
            )
        )
    lines = [
        "# CIE frozen random 2×2 factorial completion",
        "",
        "The original P0D0/P1D1 artifacts are reused without rewriting. P1D0 and "
        "P0D1 use the same frozen bag-arrival and physical-node-service realization "
        "for each scenario/seed. No G31 default, scorer, guard, ranker, mode, or "
        "parameter is changed.",
        "",
        "Raw contrast definitions: `A0=P1D0-P0D0`, `A1=P1D1-P0D1`, "
        "`B0=P0D1-P0D0`, `B1=P1D1-P1D0`, and "
        "`Interaction=P1D1-P1D0-P0D1+P0D0`.",
        "",
        "## Campaign gate",
        "",
        "| map | load | status | valid seeds | completion gate |",
        "|---|---:|---|---:|---|",
        *scenario_lines,
        "",
        "## Paired contrasts",
        "",
        "W/T/L is oriented to the metric's preferred direction. Relationship is "
        "ADDITIVE only for an exactly zero interaction, SYNERGISTIC/ANTAGONISTIC "
        "only when the preferred-direction interaction bootstrap interval excludes "
        "zero, and INCONCLUSIVE otherwise.",
        "",
        "| map | load | metric | contrast | status | mean | paired CI | W/T/L | relationship | cross-map direction |",
        "|---|---:|---|---|---|---:|---|---:|---|---|",
        *effect_lines,
        "",
        "## Interpretation boundary",
        "",
        "The 2× full-population THT cells remain N/A; no survivor/common-cohort "
        "timing is substituted. Fixed-denominator completion, on-time, tardiness, "
        "and backlog outcomes retain the entire raw-bag population. A failed or "
        "missing frozen seed suppresses every bootstrap contrast rather than being "
        "deleted. This is a common-executor G31 component factorial, not a Feng-native "
        "CIE-DH identity claim.",
        "",
    ]
    _atomic_text(path, "\n".join(lines))


def _scenario_dir(map_name: str, load: float) -> str:
    return f"{map_name}_{load:.2f}x".replace(".", "p")


def _output_path(root: Path, map_name: str, load: float, seed: int, arm: str) -> Path:
    return root / _scenario_dir(map_name, load) / f"{seed}_{arm}.json"


def campaign_cells(
    *, arms: Sequence[str] = NEW_ARMS
) -> list[tuple[str, float, int, str]]:
    unknown = sorted(set(arms) - set(ARMS))
    if unknown:
        raise RandomFactorialError(f"unknown generated arms: {unknown}")
    return [
        (map_name, load, seed, arm)
        for map_name, load in FORMAL_SCENARIOS
        for seed in paired.EXPECTED_PAIRED_SEEDS
        for arm in arms
    ]


def _existing_artifacts(root: Path) -> dict[tuple[str, float, int, str], Mapping[str, Any]]:
    result: dict[tuple[str, float, int, str], Mapping[str, Any]] = {}
    for _path, run in paired._discover([root]):
        key = (
            str(run.get("map")),
            _load(run.get("load_factor")),
            _integer(run.get("seed"), "run seed"),
            str(run.get("arm")),
        )
        if key in result:
            raise RandomFactorialError(f"duplicate existing artifact: {key}")
        result[key] = run
    return result


def _execution_inputs(
    existing_root: Path,
    *,
    binary_override: Path | None,
    nanning_profile: Path,
    load_manifest: Path,
) -> dict[str, Any]:
    existing = _existing_artifacts(existing_root)
    references: dict[tuple[str, float], Mapping[str, Any]] = {}
    for map_name, load in FORMAL_SCENARIOS:
        key = (map_name, load, paired.EXPECTED_PAIRED_SEEDS[0], "P0D0")
        run = existing.get(key)
        if run is None:
            raise RandomFactorialError(
                f"cannot derive frozen inputs; existing reference is missing: {key}"
            )
        references[(map_name, load)] = run

    binary_hashes = {
        str(_get(run, "provenance", "binary_sha256")) for run in references.values()
    }
    binary_paths = {
        str(_get(run, "provenance", "binary_path")) for run in references.values()
    }
    if len(binary_hashes) != 1 or len(binary_paths) != 1:
        raise RandomFactorialError("existing artifacts do not share one binary")
    manifest_paths = {
        str(_get(run, "random_contract", "manifest_path"))
        for run in references.values()
    }
    manifest_hashes = {
        str(_get(run, "random_contract", "manifest_sha256"))
        for run in references.values()
    }
    if len(manifest_paths) != 1 or len(manifest_hashes) != 1:
        raise RandomFactorialError(
            "existing artifacts do not share one frozen random manifest"
        )
    frozen_manifest = Path(next(iter(manifest_paths))).resolve(strict=True)
    if paired._file_sha256(frozen_manifest) != next(iter(manifest_hashes)):
        raise RandomFactorialError(
            "recorded frozen random manifest path no longer matches its SHA256"
        )
    binary = (
        binary_override.resolve(strict=True)
        if binary_override is not None
        else Path(next(iter(binary_paths))).resolve(strict=True)
    )
    if paired._file_sha256(binary) != next(iter(binary_hashes)):
        raise RandomFactorialError("selected binary differs from existing artifact SHA256")

    def workload(map_name: str, load: float) -> Path:
        value = _get(references[(map_name, load)], "provenance", "workload_path")
        if not isinstance(value, str):
            raise RandomFactorialError(f"workload provenance missing: {map_name} {load}x")
        return Path(value).resolve(strict=True)

    def hca_root(map_name: str) -> Path:
        value = _get(references[(map_name, 1.0)], "release_protocol", "evidence", "source_root")
        if not isinstance(value, str):
            raise RandomFactorialError(f"same-HCA source root missing: {map_name}")
        return Path(value).resolve(strict=True)

    profile = nanning_profile.resolve(strict=True)
    manifest = load_manifest.resolve(strict=True)
    return {
        "binary": binary,
        "revision_manifest": frozen_manifest,
        "map2_workload_1x": workload("map2", 1.0),
        "map2_workload_2x": workload("map2", 2.0),
        "map2_hca_case_root": hca_root("map2"),
        "nanning_task_dir": workload("nanning", 1.0).parent,
        "nanning_hca_root": hca_root("nanning"),
        "nanning_map_profile": profile,
        "load_manifest": manifest,
        "canonical_1p75": {
            "map2": workload("map2", 1.75),
        },
    }


def _command_line(parts: Sequence[str]) -> str:
    # The formal environment is Windows/PowerShell; list2cmdline preserves
    # spaces and quotes without invoking a shell during generation.
    return subprocess.list2cmdline(list(parts))


def generate_commands(
    *,
    existing_root: Path,
    output_root: Path,
    revision_manifest: Path,
    binary: Path | None = None,
    nanning_profile: Path = paired.factorial.g35.nanning_native.DEFAULT_MAP_PROFILE,
    load_manifest: Path = paired.activation.DEFAULT_LOAD_MANIFEST,
    dry_run: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    """Generate exact commands for missing P1D0/P0D1 artifacts."""

    inputs = _execution_inputs(
        existing_root,
        binary_override=binary,
        nanning_profile=nanning_profile,
        load_manifest=load_manifest,
    )
    contract = paired.load_random_contract(inputs["revision_manifest"])
    requested_contract = paired.load_random_contract(revision_manifest)
    if _contract_fingerprint(contract) != _contract_fingerprint(requested_contract):
        raise RandomFactorialError(
            "requested and artifact-recorded manifests have different random contracts"
        )
    if contract.seeds != paired.EXPECTED_PAIRED_SEEDS:
        raise RandomFactorialError("manifest seed order differs from frozen campaign")
    commands: list[str] = []
    skipped: list[str] = []
    replacements: list[str] = []
    for map_name, load, seed, arm in campaign_cells():
        output = _output_path(output_root, map_name, load, seed, arm)
        force = False
        if output.exists():
            try:
                current = json.loads(output.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = None
            if isinstance(current, Mapping) and _artifact_complete(current):
                skipped.append(str(output))
                continue
            force = True
            replacements.append(str(output))
        parts = [
            sys.executable,
            str(Path(__file__).resolve()),
            "run",
            "--map",
            map_name,
            "--load-factor",
            str(load),
            "--arm",
            arm,
            "--seed",
            str(seed),
            "--binary",
            str(inputs["binary"]),
            "--output",
            str(output.resolve()),
            "--revision-manifest",
            str(inputs["revision_manifest"]),
            "--load-manifest",
            str(inputs["load_manifest"]),
            "--nanning-task-dir",
            str(inputs["nanning_task_dir"]),
            "--nanning-map-profile",
            str(inputs["nanning_map_profile"]),
            "--nanning-hca-root",
            str(inputs["nanning_hca_root"]),
            "--map2-workload-1x",
            str(inputs["map2_workload_1x"]),
            "--map2-workload-2x",
            str(inputs["map2_workload_2x"]),
            "--map2-hca-case-root",
            str(inputs["map2_hca_case_root"]),
        ]
        if load == 1.75:
            parts.extend(
                ["--canonical-workload", str(inputs["canonical_1p75"][map_name])]
            )
        if dry_run:
            parts.append("--dry-run")
        if force:
            parts.append("--force")
        commands.append(_command_line(parts))
    return commands, {
        "schema": AUDIT_SCHEMA,
        "status": "COMMANDS_GENERATED_NOT_EXECUTED",
        "command_count": len(commands),
        "skipped_complete_count": len(skipped),
        "replace_nonexecuted_placeholder_count": len(replacements),
        "skipped_complete_paths": skipped,
        "replace_nonexecuted_placeholder_paths": replacements,
        "dry_run_commands": dry_run,
        "arms": list(NEW_ARMS),
        "scenario_count": len(FORMAL_SCENARIOS),
        "seed_count": len(contract.seeds),
        "binary": str(inputs["binary"]),
        "binary_sha256": paired._file_sha256(inputs["binary"]),
        "requested_manifest": str(Path(revision_manifest).resolve()),
        "artifact_recorded_manifest": str(inputs["revision_manifest"]),
        "artifact_recorded_manifest_sha256": paired._file_sha256(
            inputs["revision_manifest"]
        ),
        "existing_artifacts_never_rewritten": ["P0D0", "P1D1"],
        "seed_deletion_performed": False,
    }


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--map", choices=("map2", "nanning"), required=True)
    parser.add_argument("--load-factor", type=float, required=True)
    parser.add_argument("--arm", choices=NEW_ARMS, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision-manifest", type=Path, default=paired.REVISION_MANIFEST)
    parser.add_argument("--canonical-workload", type=Path)
    parser.add_argument("--load-manifest", type=Path, default=paired.activation.DEFAULT_LOAD_MANIFEST)
    parser.add_argument("--nanning-task-dir", type=Path, default=paired.factorial.g35.nanning_native.DEFAULT_TASK_DIR)
    parser.add_argument("--nanning-map-profile", type=Path, default=paired.factorial.g35.nanning_native.DEFAULT_MAP_PROFILE)
    parser.add_argument("--nanning-hca-root", type=Path, default=paired.factorial.g35.nanning_paired.DEFAULT_HCA_ROOT)
    parser.add_argument("--map2-workload-1x", type=Path, default=paired.factorial.g35.map2_native.DEFAULT_WORKLOAD_1X)
    parser.add_argument("--map2-workload-2x", type=Path, default=paired.factorial.g35.map2_native.DEFAULT_WORKLOAD_2X)
    parser.add_argument("--map2-hca-case-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run one frozen arm/seed")
    _add_common_run_args(run)

    generate = subparsers.add_parser(
        "generate", help="generate commands for missing P1D0/P0D1 cells"
    )
    generate.add_argument("--existing-root", type=Path, default=DEFAULT_RESULT_ROOT)
    generate.add_argument("--output-root", type=Path)
    generate.add_argument("--revision-manifest", type=Path, default=paired.REVISION_MANIFEST)
    generate.add_argument("--binary", type=Path)
    generate.add_argument("--nanning-map-profile", type=Path, default=paired.factorial.g35.nanning_native.DEFAULT_MAP_PROFILE)
    generate.add_argument("--load-manifest", type=Path, default=paired.activation.DEFAULT_LOAD_MANIFEST)
    generate.add_argument("--commands-out", type=Path)
    generate.add_argument("--plan-json", type=Path)
    generate.add_argument(
        "--dry-run",
        action="store_true",
        help="append --dry-run to every generated command",
    )

    aggregate_parser = subparsers.add_parser(
        "aggregate", help="aggregate the complete four-arm campaign"
    )
    aggregate_parser.add_argument("--input-root", type=Path, action="append", required=True)
    aggregate_parser.add_argument("--revision-manifest", type=Path, default=paired.REVISION_MANIFEST)
    aggregate_parser.add_argument("--summary-csv", type=Path, default=DEFAULT_TABLE)
    aggregate_parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        args.load_factor = _load(args.load_factor)
        output = paired.factorial.g35._resolve_from_root(args.output)
        if output.exists() and not args.force:
            raise RandomFactorialError(f"output exists; pass --force: {output}")
        result = execute_run(args)
        paired.factorial.g35._write_json(output, result)
        print(json.dumps({"status": result["status"], "output": str(output)}))
        return 0 if result["status"] in {
            "COMPLETE",
            "READY_CIE_RANDOM_ROBUSTNESS_DRY_RUN",
        } else 2

    if args.command == "generate":
        existing_root = paired.factorial.g35._resolve_from_root(args.existing_root)
        if args.output_root is None:
            output_root = (
                DEFAULT_RESULT_ROOT / "_dry_run_factorial_completion"
                if args.dry_run
                else DEFAULT_RESULT_ROOT
            )
        else:
            output_root = paired.factorial.g35._resolve_from_root(args.output_root)
        commands, plan = generate_commands(
            existing_root=existing_root,
            output_root=output_root,
            revision_manifest=paired.factorial.g35._resolve_from_root(args.revision_manifest),
            binary=args.binary,
            nanning_profile=paired.factorial.g35._resolve_from_root(args.nanning_map_profile),
            load_manifest=paired.factorial.g35._resolve_from_root(args.load_manifest),
            dry_run=args.dry_run,
        )
        text = "\n".join(commands) + ("\n" if commands else "")
        if args.commands_out is not None:
            _atomic_text(paired.factorial.g35._resolve_from_root(args.commands_out), text)
        if args.plan_json is not None:
            _atomic_text(
                paired.factorial.g35._resolve_from_root(args.plan_json),
                json.dumps(plan, indent=2, sort_keys=True) + "\n",
            )
        print(json.dumps(plan, sort_keys=True))
        return 0

    rows, audit = aggregate(
        inputs=args.input_root,
        manifest_path=args.revision_manifest,
    )
    table = paired.factorial.g35._resolve_from_root(args.summary_csv)
    report = paired.factorial.g35._resolve_from_root(args.report)
    _write_csv(table, rows)
    _write_report(report, rows, audit)
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "rows": len(rows),
                "summary_csv": str(table),
                "report": str(report),
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        RandomFactorialError,
        paired.RandomRobustnessError,
        paired.factorial.PotentialFactorialError,
        paired.factorial.g35.FullPopulationError,
        OSError,
        ValueError,
        yaml.YAMLError,
        json.JSONDecodeError,
    ) as exc:
        print(f"CIE random factorial completion failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
