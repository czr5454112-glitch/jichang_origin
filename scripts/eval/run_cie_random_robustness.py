#!/usr/bin/env python3
"""Run and aggregate the frozen paired CIE random-robustness experiment.

The only stochastic inputs are those frozen in
``configs/eval/cie_revision_manifest.yaml``: one uniform arrival offset per
raw bag and one lognormal multiplier per physical node.  A realization is a
pure function of the registered seed and protected population, so P0D0 and
P1D1 receive byte-identical perturbation hashes.  No scorer, guard,
coordination rule, or ranking condition is introduced here.

``run`` writes one arm/seed JSON.  ``aggregate`` requires every frozen seed
for both arms before it computes a paired bootstrap interval; failed or
missing runs are retained as an incomplete scenario instead of being silently
removed.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import cie_fixed_denominator_business as cie_business  # noqa: E402
from scripts.eval import run_cie_component_activation as activation  # noqa: E402
from scripts.eval import run_cie_potential_factorial as factorial  # noqa: E402


SCHEMA = "czr005.cie_random_robustness.single_cell.v1"
SUMMARY_SCHEMA = "czr005.cie_random_robustness.paired_summary.v1"
REVISION_MANIFEST = ROOT / "configs/eval/cie_revision_manifest.yaml"
DEFAULT_RESULT_ROOT = ROOT / "outputs/runtime/cie_revision/random_robustness"
DEFAULT_SUMMARY_CSV = ROOT / "outputs/tables/cie_random_robustness_summary.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/cie_random_robustness_audit.md"

ARMS: Mapping[str, tuple[str, str]] = {
    "P0D0": ("ff", "off"),
    "P1D1": ("sa", "full"),
}
REGISTERED_LOAD_FACTORS = (1.0, 1.25, 1.5, 1.75, 2.0)
FORMAL_NONFAULT_SCENARIOS = (
    ("map2", 1.0),
    ("map2", 1.75),
    ("map2", 2.0),
    ("nanning", 1.0),
    ("nanning", 2.0),
)
EXPECTED_PAIRED_SEEDS = (
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
)


class RandomRobustnessError(RuntimeError):
    """Raised when paired-random evidence would violate its frozen contract."""


@dataclass(frozen=True)
class RandomContract:
    seeds: tuple[int, ...]
    arrival_low: float
    arrival_high: float
    service_log_mean: float
    service_log_sigma: float
    bootstrap_replicates: int
    confidence_level: float
    seed_removal_forbidden: bool
    manifest_path: Path
    manifest_sha256: str
    representative_faults: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class Metric:
    name: str
    label: str
    preferred_direction: str


METRICS = (
    Metric("completed_raw_bag_count", "completed raw bags", "higher"),
    Metric("completion_rate", "raw-bag completion rate", "higher"),
    Metric("on_time_raw_bag_count", "fixed-denominator on-time bags", "higher"),
    Metric("on_time_rate", "fixed-denominator on-time rate", "higher"),
    Metric("missed_bag_count", "fixed-denominator missed bags", "lower"),
    Metric("missed_bag_rate", "fixed-denominator missed rate", "lower"),
    Metric("tardiness_sum_seconds", "all-population tardiness sum (s)", "lower"),
    Metric("tardiness_mean_seconds", "all-population tardiness mean (s)", "lower"),
    Metric("tardiness_p95_seconds", "all-population tardiness P95 (s)", "lower"),
    Metric("tardiness_p99_seconds", "all-population tardiness P99 (s)", "lower"),
    Metric("tardiness_max_seconds", "all-population tardiness max (s)", "lower"),
    Metric("time_to_90_percent_seconds", "time to 90% completion (s)", "lower"),
    Metric("time_to_95_percent_seconds", "time to 95% completion (s)", "lower"),
    Metric("time_to_99_percent_seconds", "time to 99% completion (s)", "lower"),
    Metric("total_backlog_area_seconds", "total raw-bag backlog area (bag-s)", "lower"),
    Metric("total_backlog_peak", "total raw-bag backlog peak", "lower"),
    Metric("source_backlog_area_seconds", "source backlog area (bag-s)", "lower"),
    Metric("network_backlog_area_seconds", "network backlog area (bag-s)", "lower"),
    Metric("population_latency_mean_seconds", "1x full-population mean THT (s)", "lower"),
    Metric("population_latency_p95_seconds", "1x full-population P95 THT (s)", "lower"),
    Metric("population_latency_p99_seconds", "1x full-population P99 THT (s)", "lower"),
    Metric("population_latency_max_seconds", "1x full-population max THT (s)", "lower"),
)

SUMMARY_FIELDS = (
    "schema",
    "map",
    "load_factor",
    "status",
    "metric",
    "metric_label",
    "preferred_direction",
    "arm_a",
    "arm_b",
    "paired_seed_count",
    "expected_seed_count",
    "missing_seeds",
    "failed_seeds",
    "p0d0_mean",
    "p1d1_mean",
    "mean_delta_p1d1_minus_p0d0",
    "relative_delta_vs_p0d0_percent",
    "relative_delta_status",
    "paired_cohen_dz",
    "paired_cohen_dz_status",
    "seed_win_count",
    "seed_tie_count",
    "seed_loss_count",
    "failed_seed_count",
    "failed_seed_rate",
    "bootstrap_ci_low",
    "bootstrap_ci_high",
    "bootstrap_replicates",
    "confidence_level",
    "timing_protocol",
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RandomRobustnessError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RandomRobustnessError(f"{label} must be finite")
    return result


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RandomRobustnessError(f"{label} must be an integer")
    return value


def load_random_contract(path: Path = REVISION_MANIFEST) -> RandomContract:
    """Read, but never rewrite, the frozen randomization contract."""

    resolved = path.resolve(strict=True)
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RandomRobustnessError("revision manifest must be a YAML object")
    if payload.get("frozen_before_formal_result_read") is not True:
        raise RandomRobustnessError("revision manifest is not marked frozen")
    random_block = payload.get("random_robustness")
    if not isinstance(random_block, Mapping):
        raise RandomRobustnessError("manifest lacks random_robustness")
    arrival = random_block.get("arrival_jitter_seconds")
    service = random_block.get("service_multiplier")
    if not isinstance(arrival, Mapping) or arrival.get("distribution") != "uniform":
        raise RandomRobustnessError("arrival jitter must be the frozen uniform law")
    if not isinstance(service, Mapping) or service.get("distribution") != "lognormal":
        raise RandomRobustnessError("service multiplier must be the frozen lognormal law")
    raw_seeds = random_block.get("paired_seeds")
    if not isinstance(raw_seeds, list) or not raw_seeds:
        raise RandomRobustnessError("paired_seeds must be a non-empty list")
    seeds = tuple(_integer(value, "paired seed") for value in raw_seeds)
    if len(seeds) != len(set(seeds)):
        raise RandomRobustnessError("paired seeds must be unique")
    replicates = _integer(
        random_block.get("bootstrap_replicates"), "bootstrap_replicates"
    )
    confidence = _finite(random_block.get("confidence_level"), "confidence_level")
    arrival_low = _finite(arrival.get("low"), "arrival low")
    arrival_high = _finite(arrival.get("high"), "arrival high")
    service_log_mean = _finite(service.get("log_mean"), "service log mean")
    service_log_sigma = _finite(service.get("log_sigma"), "service log sigma")
    seed_removal_forbidden = (
        random_block.get("result_seed_removal_forbidden") is True
    )
    if replicates <= 0 or not 0.0 < confidence < 1.0:
        raise RandomRobustnessError("bootstrap contract is invalid")
    frozen_gates = {
        "paired_seeds": seeds == EXPECTED_PAIRED_SEEDS,
        "arrival_uniform_minus5_plus5": arrival_low == -5.0
        and arrival_high == 5.0,
        "service_lognormal_mu0_sigma005": service_log_mean == 0.0
        and service_log_sigma == 0.05,
        "bootstrap_10000": replicates == 10_000,
        "confidence_095": confidence == 0.95,
        "seed_removal_forbidden": seed_removal_forbidden,
    }
    if not all(frozen_gates.values()):
        raise RandomRobustnessError(
            f"random-robustness manifest differs from the frozen contract: {frozen_gates}"
        )
    faults = payload.get("representative_faults")
    registered_faults: dict[str, tuple[str, ...]] = {}
    if isinstance(faults, Mapping):
        for map_name in ("map2", "nanning"):
            values = faults.get(map_name, ())
            if isinstance(values, list) and all(isinstance(item, str) for item in values):
                registered_faults[map_name] = tuple(values)
    return RandomContract(
        seeds=seeds,
        arrival_low=arrival_low,
        arrival_high=arrival_high,
        service_log_mean=service_log_mean,
        service_log_sigma=service_log_sigma,
        bootstrap_replicates=replicates,
        confidence_level=confidence,
        seed_removal_forbidden=seed_removal_forbidden,
        manifest_path=resolved,
        manifest_sha256=_file_sha256(resolved),
        representative_faults=registered_faults,
    )


def _derived_rng(seed: int, stream: str) -> random.Random:
    digest = hashlib.sha256(f"cie-random-v1|{seed}|{stream}".encode("ascii")).digest()
    return random.Random(int.from_bytes(digest, "big"))


def _normal_box_muller(rng: random.Random) -> float:
    # Avoid implementation-specific state consumption by spelling out the
    # transform rather than calling Random.lognormvariate.
    u1 = max(rng.random(), sys.float_info.min)
    u2 = rng.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def build_realization(
    *,
    seed: int,
    task_ids: Iterable[int],
    node_ids: Iterable[int],
    contract: RandomContract,
) -> dict[str, Any]:
    """Create one arm-independent paired realization."""

    if seed not in contract.seeds:
        raise RandomRobustnessError(f"seed is not frozen in the manifest: {seed}")
    tasks = sorted(set(int(value) for value in task_ids))
    nodes = sorted(set(int(value) for value in node_ids))
    if not tasks or not nodes:
        raise RandomRobustnessError("realization requires tasks and nodes")
    arrival_rng = _derived_rng(seed, "arrival_by_raw_task_id")
    service_rng = _derived_rng(seed, "service_by_node_id")
    arrival = {
        task_id: arrival_rng.uniform(contract.arrival_low, contract.arrival_high)
        for task_id in tasks
    }
    service = {
        node_id: math.exp(
            contract.service_log_mean
            + contract.service_log_sigma * _normal_box_muller(service_rng)
        )
        for node_id in nodes
    }
    arrival_records = [[key, arrival[key]] for key in tasks]
    service_records = [[key, service[key]] for key in nodes]
    return {
        "algorithm": "PYTHON_MT19937_SHA256_STREAMS_BOX_MULLER_V1",
        "seed": seed,
        "arrival_by_task_id": arrival,
        "service_multiplier_by_node_id": service,
        "arrival_realization_sha256": _sha256_value(arrival_records),
        "service_realization_sha256": _sha256_value(service_records),
        "combined_realization_sha256": _sha256_value(
            {"arrival": arrival_records, "service": service_records}
        ),
    }


def _describe(values: Sequence[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "min": min(values),
        "mean": statistics.fmean(values),
        "max": max(values),
    }


def _jitter_rows(
    rows: Sequence[Mapping[str, Any]], realization: Mapping[str, Any]
) -> tuple[dict[str, Any], ...]:
    offsets = realization["arrival_by_task_id"]
    shifted: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        task_id = int(row["task_id"])
        delta = float(offsets[task_id])
        touched = False
        for field in ("pass_time", "original_entry_time", "release_time", "arrival_time"):
            if field in row and row[field] is not None:
                shifted_value = _finite(row[field], field) + delta
                if shifted_value < 0.0:
                    raise RandomRobustnessError(
                        f"arrival jitter would create a negative {field} for "
                        f"task_id={task_id}"
                    )
                row[field] = shifted_value
                touched = True
        if not touched:
            raise RandomRobustnessError("workload row has no arrival/release field")
        shifted.append(row)
    result = tuple(shifted)
    # One raw-bag offset must preserve all segment ordering and every
    # within-bag release gap.  Check explicitly so a future field-specific
    # perturbation cannot silently change segment precedence.
    originals_by_task: dict[int, list[tuple[str, float]]] = {}
    shifted_by_task: dict[int, list[tuple[str, float]]] = {}
    for original, updated in zip(rows, result):
        task_id = int(original["task_id"])
        segment_id = str(original["segment_id"])
        originals_by_task.setdefault(task_id, []).append(
            (segment_id, _finite(original["pass_time"], "pass_time"))
        )
        shifted_by_task.setdefault(task_id, []).append(
            (segment_id, _finite(updated["pass_time"], "pass_time"))
        )
        if original.get("std") != updated.get("std"):
            raise RandomRobustnessError("arrival jitter changed a deadline")
    for task_id in originals_by_task:
        original_order = [
            segment_id
            for segment_id, _value in sorted(
                originals_by_task[task_id], key=lambda item: (item[1], item[0])
            )
        ]
        shifted_order = [
            segment_id
            for segment_id, _value in sorted(
                shifted_by_task[task_id], key=lambda item: (item[1], item[0])
            )
        ]
        if original_order != shifted_order:
            raise RandomRobustnessError(
                f"arrival jitter changed segment precedence for task_id={task_id}"
            )
    return result


def _perturb_node_service(
    request: Mapping[str, Any], realization: Mapping[str, Any]
) -> dict[str, Any]:
    prepared = dict(request)
    multipliers = realization["service_multiplier_by_node_id"]
    records: list[list[Any]] = []
    for source in request["node_records"]:
        row = list(source)
        if len(row) < 3:
            raise RandomRobustnessError("node record lacks service time")
        node_id = int(row[0])
        service = _finite(row[2], "node service time")
        if service < 0.0:
            raise RandomRobustnessError("node service time must be non-negative")
        if node_id not in multipliers:
            raise RandomRobustnessError(
                f"physical node lacks a service multiplier: {node_id}"
            )
        row[2] = service * float(multipliers[node_id])
        records.append(row)
    prepared["node_records"] = records
    return prepared


def _replace_bag_releases(
    request: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    prepared = dict(request)
    releases = {str(row["segment_id"]): float(row["pass_time"]) for row in rows}
    records: list[tuple[Any, ...]] = []
    observed: set[str] = set()
    for source in request["bag_records"]:
        row = list(source)
        segment_id = str(row[0])
        if segment_id not in releases or segment_id in observed or len(row) != 7:
            raise RandomRobustnessError("bag records do not match jittered workload")
        observed.add(segment_id)
        row[2] = releases[segment_id]
        records.append(tuple(row))
    if observed != set(releases):
        raise RandomRobustnessError("jittered workload is missing from bag records")
    prepared["bag_records"] = records
    return prepared


def _load_factor(value: float) -> float:
    factor = _finite(value, "load factor")
    if not any(math.isclose(factor, item, abs_tol=1.0e-9) for item in REGISTERED_LOAD_FACTORS):
        raise RandomRobustnessError(
            f"load factor must be one of {REGISTERED_LOAD_FACTORS}"
        )
    return next(item for item in REGISTERED_LOAD_FACTORS if math.isclose(factor, item))


def _factorial_args(args: argparse.Namespace, binary: Path) -> argparse.Namespace:
    potential, dynamic = ARMS[args.arm]
    return argparse.Namespace(
        map=args.map,
        scale=int(args.load_factor),
        policy="s4",
        potential=potential,
        dynamic=dynamic,
        service_multiplier=1.0,
        # The frozen revision manifest requires the original 1x subjects to
        # start from the audited HCA-aligned release schedule.  The random
        # offset is applied only after that alignment, identically for both
        # arms.  The 2x population remains canonical by protocol.
        release_mode="same_hca" if args.load_factor == 1.0 else "canonical",
        binary=binary,
        output=args.output,
        nanning_task_dir=args.nanning_task_dir,
        nanning_map_profile=args.nanning_map_profile,
        nanning_hca_root=args.nanning_hca_root,
        map2_workload_1x=args.map2_workload_1x,
        map2_workload_2x=args.map2_workload_2x,
        map2_hca_case_root=args.map2_hca_case_root,
        dry_run=args.dry_run,
        force=args.force,
    )


def _prepare_intermediate(
    args: argparse.Namespace, binary: Path
) -> tuple[str, Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    if args.canonical_workload is not None:
        canonical = factorial.g35._resolve_from_root(args.canonical_workload).resolve(strict=True)
        manifest_cell: Mapping[str, Any] = {}
    else:
        canonical, manifest_cell = activation.canonical_from_load_manifest(
            factorial.g35._resolve_from_root(args.load_manifest),
            args.load_factor,
            args.map,
        )
    rows, request, source_contract = activation.prepare_runtime_request(
        map_name=args.map,
        canonical_path=canonical,
        binary=binary,
        nanning_profile_path=factorial.g35._resolve_from_root(args.nanning_map_profile),
        scenario=f"cie_random_{args.map}_{args.load_factor:.2f}x",
    )
    request = dict(request)
    request["merge_grant_rule"] = "M1"
    request["merge_grant_timing_mode"] = "jit_fifo"
    potential, dynamic = ARMS[args.arm]
    request["s4_score_component_mask"] = 0 if dynamic == "off" else 15
    potentials, artifacts = factorial._potential_pair(request)
    request = dict(potentials[potential])
    workload = SimpleNamespace(
        rows=rows,
        raw_bag_count=len({int(row["task_id"]) for row in rows}),
        segment_count=len(rows),
        source_path=canonical,
    )
    release = {
        "mode": "canonical",
        "formal_same_hca_release_input": False,
        "same_hca_release_trace_pass": False,
        "intermediate_load_manifest_cell": dict(manifest_cell),
    }
    prepared = {
        "cell_id": args.arm,
        "potential": {
            "selected": potential,
            "selected_label": factorial.POTENTIAL_LABELS[potential],
            "selected_matrix_sha256": artifacts[potential]["matrix_sha256"],
            "artifacts": artifacts,
            "pair_matrix_differs": artifacts["ff"]["matrix_sha256"]
            != artifacts["sa"]["matrix_sha256"],
            "selection_changes_only_heuristic_time": True,
        },
        "source_contract": source_contract,
    }
    return (
        f"cie_random_{args.map}_{args.load_factor:.2f}x",
        workload,
        request,
        release,
        prepared,
    )


def prepare_randomized_cell(
    args: argparse.Namespace, contract: RandomContract
) -> tuple[str, Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Prepare one randomized arm while keeping the realization arm-independent."""

    args.load_factor = _load_factor(args.load_factor)
    if args.arm not in ARMS:
        raise RandomRobustnessError(f"unsupported arm: {args.arm}")
    if args.seed not in contract.seeds:
        raise RandomRobustnessError("run seed is not in the frozen paired seed list")
    binary = factorial.g35._resolve_from_root(args.binary).resolve(strict=True)
    args.binary = binary
    if args.load_factor in (1.0, 2.0) and args.canonical_workload is None:
        case_id, workload, request, release, prepared = factorial.prepare_cell(
            _factorial_args(args, binary)
        )
    else:
        case_id, workload, request, release, prepared = _prepare_intermediate(args, binary)

    rows = tuple(dict(row) for row in workload.rows)
    base_arrival_identity = [
        [
            str(row["segment_id"]),
            int(row["task_id"]),
            row.get("pass_time"),
            row.get("original_entry_time"),
            row.get("std"),
        ]
        for row in rows
    ]
    base_service_identity = [
        [int(row[0]), row[2]] for row in request["node_records"]
    ]
    realization = build_realization(
        seed=args.seed,
        task_ids=(int(row["task_id"]) for row in rows),
        node_ids=(int(row[0]) for row in request["node_records"]),
        contract=contract,
    )
    jittered_rows = _jitter_rows(rows, realization)
    randomized = _perturb_node_service(request, realization)
    randomized = _replace_bag_releases(randomized, jittered_rows)
    release = dict(release)
    base_release_mode = str(release.get("mode", "UNKNOWN"))
    base_same_hca_pass = release.get("same_hca_release_trace_pass") is True
    release.update(
        {
            "base_release_mode_before_random_jitter": base_release_mode,
            "base_same_hca_release_trace_pass": base_same_hca_pass,
            "mode": f"paired_random_jitter_from_{base_release_mode}",
            "paired_random_jitter_applied": True,
            # Once the frozen perturbation is applied this is no longer the
            # literal HCA release trace and must not inherit HCA-comparison
            # eligibility, even though the unperturbed base was audited.
            "same_hca_release_trace_pass": False,
            "formal_same_hca_release_input": False,
            "formal_hca_cross_algorithm_timing_eligible": False,
        }
    )
    potential_key, dynamic = ARMS[args.arm]
    potential_requests, potential_artifacts = factorial._potential_pair(randomized)
    randomized = dict(potential_requests[potential_key])
    randomized["s4_score_component_mask"] = 0 if dynamic == "off" else 15

    workload_view = SimpleNamespace(
        rows=jittered_rows,
        raw_bag_count=workload.raw_bag_count,
        segment_count=workload.segment_count,
        source_path=factorial._workload_source_path(workload),
    )
    arrivals = list(realization["arrival_by_task_id"].values())
    services = list(realization["service_multiplier_by_node_id"].values())
    perturbation = {
        "pairing_key": {
            "map": args.map,
            "load_factor": args.load_factor,
            "seed": args.seed,
        },
        "random_generator": realization["algorithm"],
        "arrival_jitter_seconds": {
            "distribution": "uniform",
            "low": contract.arrival_low,
            "high": contract.arrival_high,
            "unit": "one shared offset per raw task_id across all its segments",
            "deadline_shifted": False,
            "within_raw_bag_segment_precedence_preserved": True,
            "negative_arrival_or_release_count": 0,
            "summary": _describe(arrivals),
            "realization_sha256": realization["arrival_realization_sha256"],
        },
        "node_service_multiplier": {
            "distribution": "lognormal",
            "log_mean": contract.service_log_mean,
            "log_sigma": contract.service_log_sigma,
            "unit": "one shared multiplier per physical node_id",
            "all_physical_node_records_receive_multiplier": True,
            "zero_base_service_remains_zero": True,
            "per_bag_goal_service_not_executed": True,
            "goal_exclusion_semantics": (
                "complete_on_goal_arrival terminates each bag before service at "
                "its own goal; H(g,g)=0; the same node remains perturbed when "
                "it is a source or transit node for another bag"
            ),
            "summary": _describe(services),
            "realization_sha256": realization["service_realization_sha256"],
        },
        "combined_realization_sha256": realization[
            "combined_realization_sha256"
        ],
        "base_arrival_schedule_sha256": _sha256_value(base_arrival_identity),
        "base_node_service_profile_sha256": _sha256_value(base_service_identity),
        "randomized_arrival_schedule_sha256": _sha256_value(
            [
                [
                    str(row["segment_id"]),
                    int(row["task_id"]),
                    row.get("pass_time"),
                    row.get("original_entry_time"),
                    row.get("std"),
                ]
                for row in jittered_rows
            ]
        ),
        "randomized_node_service_profile_sha256": _sha256_value(
            [[int(row[0]), row[2]] for row in randomized["node_records"]]
        ),
        "same_realization_required_for_both_arms": True,
        "arm_used_to_generate_randomness": False,
    }
    prepared = {
        **prepared,
        "potential": {
            **prepared["potential"],
            "selected_matrix_sha256": potential_artifacts[potential_key][
                "matrix_sha256"
            ],
            "artifacts": potential_artifacts,
        },
        "perturbation": perturbation,
    }
    return case_id, workload_view, randomized, release, prepared


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def execute_run(
    args: argparse.Namespace,
    *,
    executor: Any | None = None,
) -> dict[str, Any]:
    contract = load_random_contract(args.revision_manifest)
    case_id, workload, request, release, prepared = prepare_randomized_cell(
        args, contract
    )
    binary = Path(args.binary).resolve(strict=True)
    workload_path = Path(workload.source_path).resolve(strict=True)
    potential_key, dynamic = ARMS[args.arm]
    common = {
        "schema": SCHEMA,
        "status": "READY_CIE_RANDOM_ROBUSTNESS_DRY_RUN",
        "native_execution_started": False,
        "case_id": case_id,
        "map": args.map,
        "load_factor": args.load_factor,
        "scale": int(args.load_factor) if args.load_factor in (1.0, 2.0) else None,
        "seed": args.seed,
        "arm": args.arm,
        "population": {
            "raw_bag_count": workload.raw_bag_count,
            "segment_count": workload.segment_count,
            "whole_population": True,
        },
        "release_protocol": release,
        "algorithm": {
            "cell_id": args.arm,
            "policy": "s4",
            "potential": potential_key,
            "potential_label": factorial.POTENTIAL_LABELS[potential_key],
            "dynamic": dynamic,
            "s4_score_component_mask": request["s4_score_component_mask"],
            "coordination_protocol": "neutral_fifo",
            "merge_grant_rule": request["merge_grant_rule"],
            "merge_grant_timing_mode": request["merge_grant_timing_mode"],
            "new_scorer_guard_mode_or_ranker_added": False,
            "posthoc_tuning": False,
        },
        "potential": prepared["potential"],
        "perturbation": prepared["perturbation"],
        "random_contract": {
            "manifest_path": str(contract.manifest_path),
            "manifest_sha256": contract.manifest_sha256,
            "paired_seeds": list(contract.seeds),
            "bootstrap_replicates": contract.bootstrap_replicates,
            "confidence_level": contract.confidence_level,
            "result_seed_removal_forbidden": contract.seed_removal_forbidden,
        },
        "representative_fixed_faults": {
            "status": "BLOCKED_N_M_COMMON_EXECUTOR_FACTORIAL_FAULT_PREPARATION_NOT_AVAILABLE",
            "registered_scenarios": list(
                contract.representative_faults.get(args.map, ())
            ),
            "reason": (
                "the existing map-specific fault runners alter reachability, "
                "bag admission and structural-value artifacts; they cannot be "
                "injected into this paired P0D0/P1D1 common-executor cell "
                "without changing more than the frozen stochastic inputs"
            ),
            "dynamic_recovery_claim": False,
            "fabricated_zero_or_surrogate_result": False,
        },
        "fixed_window": {
            "end_epoch": factorial.g35.nanning_native.FIXED_END_EPOCH,
            "max_events": factorial.g35.nanning_native.MAX_EVENTS,
            "speed_mps": factorial.g35.SPEED_MPS,
        },
        "provenance": {
            "git_commit": _git_value("rev-parse", "HEAD"),
            "git_branch": _git_value("branch", "--show-current"),
            "binary_path": str(binary),
            "binary_sha256": _file_sha256(binary),
            "workload_path": str(workload_path),
            "workload_sha256": _file_sha256(workload_path),
            "survivor_timing_used": False,
        },
    }
    if args.dry_run:
        return common

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = selected_executor(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise RandomRobustnessError("native executor did not return summary and bags")
    if any(not isinstance(row, Mapping) for row in bags):
        raise RandomRobustnessError("native executor returned a non-object bag row")
    integrity, paper = factorial._paper_subjects(
        summary,
        bags,
        workload,
        request,
        release,
        formal_timing_eligible=args.load_factor != 2.0,
    )
    paper["fixed_denominator_business"] = cie_business.summarize(
        workload.rows,
        bags,
        fixed_horizon=factorial.g35.nanning_native.FIXED_END_EPOCH,
    )
    if args.load_factor == 2.0:
        timing = paper["full_population_raw_bag_timing"]
        if timing.get("status") != "FORMAL_2X_TIMING_NA_BY_PROTOCOL" or timing.get(
            "metrics_seconds"
        ) is not None:
            raise RandomRobustnessError("2x formal THT must remain N/A")
    return {
        **common,
        "status": "COMPLETE" if integrity["pass"] else "FAILED_INTEGRITY",
        "native_execution_started": True,
        "execution_integrity": integrity,
        "paper_subjects": paper,
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "peak_rss_bytes": "NOT_MEASURED",
            "native_summary": dict(summary),
        },
    }


def _get(root: Mapping[str, Any], *path: str) -> Any:
    value: Any = root
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _metrics_from_run(data: Mapping[str, Any]) -> dict[str, float | None]:
    business = _get(data, "paper_subjects", "fixed_denominator_business")
    business = business if isinstance(business, Mapping) else {}
    tardiness = _get(
        business, "tardiness_seconds", "fixed_horizon_all_population_lower_bound"
    )
    tardiness = tardiness if isinstance(tardiness, Mapping) else {}
    targets = business.get("completion_targets")
    targets = targets if isinstance(targets, Mapping) else {}
    backlog = business.get("backlog")
    backlog = backlog if isinstance(backlog, Mapping) else {}

    def target(percent: str) -> float | None:
        value = targets.get(f"time_to_{percent}_percent")
        if not isinstance(value, Mapping) or value.get("reached") is not True:
            return None
        return _number(value.get("elapsed_from_first_arrival_seconds"))

    def backlog_value(group: str, field: str) -> float | None:
        value = backlog.get(group)
        return _number(value.get(field)) if isinstance(value, Mapping) else None

    timing = _get(data, "paper_subjects", "full_population_raw_bag_timing")
    timing = timing if isinstance(timing, Mapping) else {}
    scale = _number(data.get("load_factor"))
    if scale == 2.0:
        if timing.get("status") != "FORMAL_2X_TIMING_NA_BY_PROTOCOL":
            raise RandomRobustnessError("aggregate rejected non-N/A 2x timing")
        if timing.get("metrics_seconds") is not None:
            raise RandomRobustnessError("aggregate rejected populated 2x timing")
        timing_series: Mapping[str, Any] = {}
    else:
        series = _get(timing, "metrics_seconds", "paper_network_from_admission")
        timing_series = series if isinstance(series, Mapping) else {}
    return {
        "completed_raw_bag_count": _number(business.get("completed_raw_bag_count")),
        "completion_rate": _number(business.get("completion_rate")),
        "on_time_raw_bag_count": _number(business.get("on_time_raw_bag_count")),
        "on_time_rate": _number(business.get("on_time_rate")),
        "missed_bag_count": _number(business.get("missed_bag_count")),
        "missed_bag_rate": _number(business.get("missed_bag_rate")),
        "tardiness_sum_seconds": _number(tardiness.get("sum")),
        "tardiness_mean_seconds": _number(tardiness.get("mean")),
        "tardiness_p95_seconds": _number(tardiness.get("p95")),
        "tardiness_p99_seconds": _number(tardiness.get("p99")),
        "tardiness_max_seconds": _number(tardiness.get("max")),
        "time_to_90_percent_seconds": target("90"),
        "time_to_95_percent_seconds": target("95"),
        "time_to_99_percent_seconds": target("99"),
        "total_backlog_area_seconds": backlog_value("raw_bag_total", "backlog_area_seconds"),
        "total_backlog_peak": backlog_value("raw_bag_total", "peak_backlog"),
        "source_backlog_area_seconds": backlog_value(
            "raw_bag_source_until_all_segments_admitted", "backlog_area_seconds"
        ),
        "network_backlog_area_seconds": backlog_value(
            "raw_bag_network_after_all_segments_admitted", "backlog_area_seconds"
        ),
        "population_latency_mean_seconds": _number(timing_series.get("mean")),
        "population_latency_p95_seconds": _number(timing_series.get("p95")),
        "population_latency_p99_seconds": _number(timing_series.get("p99")),
        "population_latency_max_seconds": _number(timing_series.get("max")),
    }


def _discover(paths: Iterable[Path]) -> list[tuple[Path, Mapping[str, Any]]]:
    found: set[Path] = set()
    for source in paths:
        resolved = source.resolve(strict=True)
        candidates = [resolved] if resolved.is_file() else resolved.rglob("*.json")
        found.update(path.resolve() for path in candidates)
    rows: list[tuple[Path, Mapping[str, Any]]] = []
    for path in sorted(found, key=lambda item: str(item).casefold()):
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, Mapping) and value.get("schema") == SCHEMA:
            if value.get("native_execution_started") is True:
                rows.append((path, value))
    return rows


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise RandomRobustnessError("cannot take a quantile of no values")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def paired_bootstrap_ci(
    differences: Sequence[float],
    *,
    replicates: int,
    confidence_level: float,
    bootstrap_seed: int,
) -> tuple[float, float]:
    if not differences:
        raise RandomRobustnessError("paired bootstrap needs at least one pair")
    rng = random.Random(bootstrap_seed)
    count = len(differences)
    estimates = sorted(
        statistics.fmean(differences[rng.randrange(count)] for _ in range(count))
        for _ in range(replicates)
    )
    alpha = (1.0 - confidence_level) / 2.0
    return _quantile(estimates, alpha), _quantile(estimates, 1.0 - alpha)


def _aggregate_for_scenarios(
    *,
    inputs: Sequence[Path],
    manifest_path: Path,
    required_scenarios: Sequence[tuple[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    contract = load_random_contract(manifest_path)
    normalized_scenarios = tuple(
        (str(map_name), _load_factor(load))
        for map_name, load in required_scenarios
    )
    if len(normalized_scenarios) != len(set(normalized_scenarios)):
        raise RandomRobustnessError("required random scenarios must be unique")
    runs = _discover(inputs)
    if not runs:
        raise RandomRobustnessError("no executed random-robustness JSON was found")
    expected_run_keys = {
        (map_name, load, seed, arm)
        for map_name, load in normalized_scenarios
        for seed in contract.seeds
        for arm in ARMS
    }
    indexed: dict[tuple[str, float, int, str], Mapping[str, Any]] = {}
    for path, run in runs:
        map_name = str(run.get("map"))
        load = _load_factor(float(run.get("load_factor")))
        seed = _integer(run.get("seed"), "run seed")
        arm = str(run.get("arm"))
        key = (map_name, load, seed, arm)
        if arm not in ARMS or key not in expected_run_keys or key in indexed:
            raise RandomRobustnessError(f"duplicate or unknown run identity: {key}")
        random_contract = run.get("random_contract")
        if not isinstance(random_contract, Mapping) or random_contract.get(
            "manifest_sha256"
        ) != contract.manifest_sha256:
            raise RandomRobustnessError(f"manifest hash mismatch: {path}")
        release = run.get("release_protocol")
        expected_base_release = "same_hca" if load == 1.0 else "canonical"
        expected_release_mode = (
            f"paired_random_jitter_from_{expected_base_release}"
        )
        if not isinstance(release, Mapping) or any(
            (
                release.get("base_release_mode_before_random_jitter")
                != expected_base_release,
                release.get("mode") != expected_release_mode,
                release.get("paired_random_jitter_applied") is not True,
                release.get("base_same_hca_release_trace_pass")
                is not (load == 1.0),
                release.get("same_hca_release_trace_pass") is not False,
                release.get("formal_same_hca_release_input") is not False,
                release.get("formal_hca_cross_algorithm_timing_eligible")
                is not False,
            )
        ):
            raise RandomRobustnessError(
                f"randomized release contract mismatch: {path}"
            )
        indexed[key] = run

    missing_run_keys = sorted(expected_run_keys - set(indexed))
    if len(runs) != len(expected_run_keys) or missing_run_keys:
        missing_scenarios = sorted(
            set(normalized_scenarios)
            - {(key[0], key[1]) for key in indexed}
        )
        raise RandomRobustnessError(
            "formal random campaign requires exactly "
            f"{len(expected_run_keys)} executed artifacts; found {len(runs)}; "
            f"missing_run_count={len(missing_run_keys)}; "
            f"missing_scenarios={missing_scenarios}"
        )

    global_identity_paths = (
        ("provenance", "git_commit"),
        ("provenance", "binary_sha256"),
    )
    for path in global_identity_paths:
        values = {_get(run, *path) for run in indexed.values()}
        if None in values or len(values) != 1:
            raise RandomRobustnessError(
                "formal random campaign global identity mismatch: "
                f"{'.'.join(path)}"
            )

    scenario_identity_paths = (
        ("provenance", "workload_sha256"),
        ("perturbation", "base_arrival_schedule_sha256"),
        ("perturbation", "base_node_service_profile_sha256"),
        ("release_protocol", "base_release_mode_before_random_jitter"),
        ("release_protocol", "mode"),
        ("population", "raw_bag_count"),
        ("population", "segment_count"),
    )
    for map_name, load in normalized_scenarios:
        scenario_runs = [
            run
            for (candidate_map, candidate_load, _seed, _arm), run in indexed.items()
            if candidate_map == map_name and candidate_load == load
        ]
        mismatches = []
        for path in scenario_identity_paths:
            values = {_get(run, *path) for run in scenario_runs}
            if None in values or len(values) != 1:
                mismatches.append(".".join(path))
        if mismatches:
            raise RandomRobustnessError(
                f"scenario base identity mismatch for {map_name} {load}x: "
                f"{mismatches}"
            )

    scenarios = sorted(normalized_scenarios)
    summary: list[dict[str, Any]] = []
    scenario_audit: list[dict[str, Any]] = []
    expected = set(contract.seeds)
    for map_name, load in scenarios:
        observed = {
            seed
            for (candidate_map, candidate_load, seed, _arm) in indexed
            if candidate_map == map_name and candidate_load == load
        }
        extra = sorted(observed - expected)
        if extra:
            raise RandomRobustnessError(f"unregistered seeds present: {extra}")
        missing = sorted(expected - observed)
        failed: set[int] = set()
        valid_pairs: dict[int, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
        for seed in sorted(expected):
            left = indexed.get((map_name, load, seed, "P0D0"))
            right = indexed.get((map_name, load, seed, "P1D1"))
            if left is None or right is None:
                if seed not in missing:
                    missing.append(seed)
                continue
            left_hash = _get(left, "perturbation", "combined_realization_sha256")
            right_hash = _get(right, "perturbation", "combined_realization_sha256")
            if not left_hash or left_hash != right_hash:
                raise RandomRobustnessError(
                    f"paired realization mismatch: {map_name} {load}x seed={seed}"
                )
            paired_identity_paths = (
                ("perturbation", "base_arrival_schedule_sha256"),
                ("perturbation", "base_node_service_profile_sha256"),
                ("perturbation", "randomized_arrival_schedule_sha256"),
                ("perturbation", "randomized_node_service_profile_sha256"),
                ("provenance", "workload_sha256"),
                ("provenance", "git_commit"),
                ("provenance", "binary_sha256"),
                ("release_protocol", "mode"),
                ("population", "raw_bag_count"),
                ("population", "segment_count"),
            )
            mismatches = [
                ".".join(path)
                for path in paired_identity_paths
                if _get(left, *path) is None
                or _get(left, *path) != _get(right, *path)
            ]
            if mismatches:
                raise RandomRobustnessError(
                    f"paired base/executor identity mismatch for seed={seed}: {mismatches}"
                )
            if left.get("status") != "COMPLETE" or right.get("status") != "COMPLETE":
                failed.add(seed)
                continue
            if _get(left, "execution_integrity", "pass") is not True or _get(
                right, "execution_integrity", "pass"
            ) is not True:
                failed.add(seed)
                continue
            valid_pairs[seed] = (left, right)
        complete = not missing and not failed and len(valid_pairs) == len(expected)
        scenario_status = (
            "COMPLETE_FROZEN_PAIRED_SEEDS"
            if complete
            else "INCOMPLETE_NO_BOOTSTRAP_SEED_REMOVAL_FORBIDDEN"
        )
        scenario_audit.append(
            {
                "map": map_name,
                "load_factor": load,
                "status": scenario_status,
                "valid_seed_count": len(valid_pairs),
                "missing_seeds": sorted(set(missing)),
                "failed_seeds": sorted(failed),
                "failed_seed_count": len(failed),
                "failed_seed_rate": len(failed) / len(contract.seeds),
            }
        )
        metric_values = {
            seed: (_metrics_from_run(pair[0]), _metrics_from_run(pair[1]))
            for seed, pair in valid_pairs.items()
        }
        for metric in METRICS:
            status = scenario_status
            left_values: list[float] = []
            right_values: list[float] = []
            if complete:
                for seed in contract.seeds:
                    left_value = metric_values[seed][0][metric.name]
                    right_value = metric_values[seed][1][metric.name]
                    if left_value is None or right_value is None:
                        status = "N_M_METRIC_NOT_AVAILABLE_FOR_EVERY_FROZEN_SEED"
                        break
                    left_values.append(left_value)
                    right_values.append(right_value)
            if status == "COMPLETE_FROZEN_PAIRED_SEEDS":
                differences = [right - left for left, right in zip(left_values, right_values)]
                bootstrap_key = (
                    f"cie-bootstrap-v1|{contract.manifest_sha256}|{map_name}|"
                    f"{load}|{metric.name}"
                )
                bootstrap_seed = int.from_bytes(
                    hashlib.sha256(bootstrap_key.encode("ascii")).digest(), "big"
                )
                low, high = paired_bootstrap_ci(
                    differences,
                    replicates=contract.bootstrap_replicates,
                    confidence_level=contract.confidence_level,
                    bootstrap_seed=bootstrap_seed,
                )
                left_mean: float | None = statistics.fmean(left_values)
                right_mean: float | None = statistics.fmean(right_values)
                delta: float | None = statistics.fmean(differences)
                if left_mean != 0.0:
                    relative_delta: float | None = 100.0 * delta / left_mean
                    relative_status = "AVAILABLE"
                else:
                    relative_delta = None
                    relative_status = "N_M_ZERO_P0D0_MEAN"
                difference_sd = statistics.stdev(differences)
                if difference_sd != 0.0:
                    cohen_dz: float | None = delta / difference_sd
                    cohen_status = "AVAILABLE"
                else:
                    cohen_dz = None
                    cohen_status = "N_M_ZERO_PAIRED_DIFFERENCE_SAMPLE_SD"
                if metric.preferred_direction == "higher":
                    wins = sum(value > 0.0 for value in differences)
                    losses = sum(value < 0.0 for value in differences)
                elif metric.preferred_direction == "lower":
                    wins = sum(value < 0.0 for value in differences)
                    losses = sum(value > 0.0 for value in differences)
                else:
                    raise RandomRobustnessError(
                        f"unknown preferred direction: {metric.preferred_direction}"
                    )
                ties = sum(value == 0.0 for value in differences)
            else:
                left_mean = right_mean = delta = low = high = None
                relative_delta = cohen_dz = None
                wins = ties = losses = None
                relative_status = "N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE"
                cohen_status = "N_M_INCOMPLETE_OR_METRIC_UNAVAILABLE"
            summary.append(
                {
                    "schema": SUMMARY_SCHEMA,
                    "map": map_name,
                    "load_factor": load,
                    "status": status,
                    "metric": metric.name,
                    "metric_label": metric.label,
                    "preferred_direction": metric.preferred_direction,
                    "arm_a": "P0D0",
                    "arm_b": "P1D1",
                    "paired_seed_count": len(valid_pairs),
                    "expected_seed_count": len(contract.seeds),
                    "missing_seeds": ";".join(str(value) for value in sorted(set(missing))),
                    "failed_seeds": ";".join(str(value) for value in sorted(failed)),
                    "p0d0_mean": left_mean,
                    "p1d1_mean": right_mean,
                    "mean_delta_p1d1_minus_p0d0": delta,
                    "relative_delta_vs_p0d0_percent": relative_delta,
                    "relative_delta_status": relative_status,
                    "paired_cohen_dz": cohen_dz,
                    "paired_cohen_dz_status": cohen_status,
                    "seed_win_count": wins,
                    "seed_tie_count": ties,
                    "seed_loss_count": losses,
                    "failed_seed_count": len(failed),
                    "failed_seed_rate": len(failed) / len(contract.seeds),
                    "bootstrap_ci_low": low,
                    "bootstrap_ci_high": high,
                    "bootstrap_replicates": contract.bootstrap_replicates,
                    "confidence_level": contract.confidence_level,
                    "timing_protocol": (
                        "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
                        if load == 2.0
                        else "FULL_POPULATION_ONLY_NO_SURVIVOR_TIMING"
                    ),
                }
            )
    audit = {
        "schema": SUMMARY_SCHEMA,
        "manifest_sha256": contract.manifest_sha256,
        "formal_nonfault_scenarios": [
            {"map": map_name, "load_factor": load}
            for map_name, load in normalized_scenarios
        ],
        "expected_executed_artifact_count": len(expected_run_keys),
        "executed_artifact_count": len(runs),
        "paired_seeds": list(contract.seeds),
        "seed_removal_forbidden": contract.seed_removal_forbidden,
        "bootstrap_replicates": contract.bootstrap_replicates,
        "confidence_level": contract.confidence_level,
        "scenario_audit": scenario_audit,
        "representative_faults": {
            "status": "BLOCKED_N_M_COMMON_EXECUTOR_FACTORIAL_FAULT_PREPARATION_NOT_AVAILABLE",
            "registered": {
                key: list(value) for key, value in contract.representative_faults.items()
            },
            "dynamic_recovery_claim": False,
        },
    }
    return summary, audit


def aggregate(
    *,
    inputs: Sequence[Path],
    manifest_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate the fixed five-scenario, 100-artifact formal campaign."""

    return _aggregate_for_scenarios(
        inputs=inputs,
        manifest_path=manifest_path,
        required_scenarios=FORMAL_NONFAULT_SCENARIOS,
    )


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    output = []
    if rows:
        from io import StringIO

        stream = StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        output.append(stream.getvalue())
    else:
        output.append(",".join(SUMMARY_FIELDS) + "\n")
    _atomic_text(path, "".join(output))


def _write_report(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any],
) -> None:
    lines = [
        "# CIE paired random-robustness audit",
        "",
        f"- manifest SHA-256: `{audit['manifest_sha256']}`",
        f"- executed artifacts: {audit['executed_artifact_count']}/"
        f"{audit['expected_executed_artifact_count']}",
        f"- frozen paired seeds: `{audit['paired_seeds']}`",
        f"- bootstrap: {audit['bootstrap_replicates']} paired resamples, "
        f"{float(audit['confidence_level']) * 100:g}% percentile CI",
        "- contrast: `P1D1 - P0D0`; negative is better only for lower-is-better metrics",
        "- relative delta is `100 * mean(P1D1-P0D0) / mean(P0D0)` and is N/M "
        "when the P0D0 mean is zero",
        "- paired Cohen dz is the paired-difference mean divided by its sample "
        "standard deviation; zero difference SD is explicitly N/M",
        "- win/tie/loss counts orient each seed by the metric's preferred direction; "
        "failure rate uses all frozen seeds as its denominator",
        "- incomplete and failed seeds are never removed or replaced",
        "- 1x cells start from the audited same-HCA release schedule, then apply "
        "the frozen paired arrival jitter; the resulting trace is not eligible "
        "for a direct HCA timing comparison",
        "- intermediate and 2x cells start from their canonical complete-flight "
        "population before the same paired jitter contract is applied",
        "- 2x THT is N/A even when every bag completes; fixed-denominator capacity, "
        "deadline, tardiness, completion-target and backlog metrics remain eligible",
        "",
        "## Scenario gates",
        "",
        "| Map | Load | Status | Valid pairs | Missing seeds | Failed seeds | Failure rate |",
        "|---|---:|---|---:|---|---|---:|",
    ]
    for item in audit["scenario_audit"]:
        lines.append(
            f"| {item['map']} | {item['load_factor']:.2f}x | {item['status']} | "
            f"{item['valid_seed_count']} | {item['missing_seeds'] or 'none'} | "
            f"{item['failed_seeds'] or 'none'} | {item['failed_seed_rate']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Paired estimates",
            "",
            "| Map | Load | Metric | Status | P0D0 mean | P1D1 mean | Delta | Delta % | dz | W/T/L | 95% CI |",
            "|---|---:|---|---|---:|---:|---:|---|---|---|---|",
        ]
    )
    for row in rows:
        if row["status"] == "COMPLETE_FROZEN_PAIRED_SEEDS":
            interval = f"[{row['bootstrap_ci_low']:.6g}, {row['bootstrap_ci_high']:.6g}]"
            left = f"{row['p0d0_mean']:.6g}"
            right = f"{row['p1d1_mean']:.6g}"
            delta = f"{row['mean_delta_p1d1_minus_p0d0']:.6g}"
            relative = (
                f"{row['relative_delta_vs_p0d0_percent']:.6g}%"
                if row["relative_delta_status"] == "AVAILABLE"
                else f"N/M ({row['relative_delta_status']})"
            )
            cohen = (
                f"{row['paired_cohen_dz']:.6g}"
                if row["paired_cohen_dz_status"] == "AVAILABLE"
                else f"N/M ({row['paired_cohen_dz_status']})"
            )
            counts = (
                f"{row['seed_win_count']}/{row['seed_tie_count']}/"
                f"{row['seed_loss_count']}"
            )
        else:
            interval = left = right = delta = "N/M"
            relative = f"N/M ({row['relative_delta_status']})"
            cohen = f"N/M ({row['paired_cohen_dz_status']})"
            counts = "N/M"
        lines.append(
            f"| {row['map']} | {row['load_factor']:.2f}x | {row['metric_label']} | "
            f"{row['status']} | {left} | {right} | {delta} | {relative} | "
            f"{cohen} | {counts} | {interval} |"
        )
    faults = audit["representative_faults"]
    lines.extend(
        [
            "",
            "## Fixed-fault scope",
            "",
            f"Status: `{faults['status']}`.",
            "",
            "The existing map-specific fault paths change reachability, admission and "
            "structural-value artifacts. They cannot be reused here while preserving the "
            "two-arm stochastic-input-only contrast, so no fault number or dynamic-recovery "
            "claim is fabricated.",
            "",
            "## Interpretation boundary",
            "",
            "These intervals quantify robustness of the frozen P0D0/P1D1 contrast. They do "
            "not convert a common-executor adaptation into a Feng-native result and do not "
            "authorize cross-protocol ranking.",
        ]
    )
    _atomic_text(path, "\n".join(lines) + "\n")


def _run_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("run", help="run one arm and frozen seed")
    parser.add_argument("--map", choices=("map2", "nanning"), required=True)
    parser.add_argument("--load-factor", type=float, required=True)
    parser.add_argument("--arm", choices=tuple(ARMS), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision-manifest", type=Path, default=REVISION_MANIFEST)
    parser.add_argument("--canonical-workload", type=Path)
    parser.add_argument("--load-manifest", type=Path, default=activation.DEFAULT_LOAD_MANIFEST)
    parser.add_argument("--nanning-task-dir", type=Path, default=factorial.g35.nanning_native.DEFAULT_TASK_DIR)
    parser.add_argument("--nanning-map-profile", type=Path, default=factorial.g35.nanning_native.DEFAULT_MAP_PROFILE)
    parser.add_argument("--nanning-hca-root", type=Path, default=factorial.g35.nanning_paired.DEFAULT_HCA_ROOT)
    parser.add_argument("--map2-workload-1x", type=Path, default=factorial.g35.map2_native.DEFAULT_WORKLOAD_1X)
    parser.add_argument("--map2-workload-2x", type=Path, default=factorial.g35.map2_native.DEFAULT_WORKLOAD_2X)
    parser.add_argument("--map2-hca-case-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")


def _aggregate_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("aggregate", help="aggregate complete paired seeds")
    parser.add_argument("--input-root", type=Path, action="append", required=True)
    parser.add_argument("--revision-manifest", type=Path, default=REVISION_MANIFEST)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _run_parser(subparsers)
    _aggregate_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        args.load_factor = _load_factor(args.load_factor)
        output = factorial.g35._resolve_from_root(args.output)
        if output.exists() and not args.force:
            raise RandomRobustnessError(f"output exists; pass --force: {output}")
        result = execute_run(args)
        factorial.g35._write_json(output, result)
        print(json.dumps({"status": result["status"], "output": str(output)}))
        return 0 if result["status"] in {
            "COMPLETE",
            "READY_CIE_RANDOM_ROBUSTNESS_DRY_RUN",
        } else 2
    rows, audit = aggregate(
        inputs=args.input_root,
        manifest_path=args.revision_manifest,
    )
    summary_path = factorial.g35._resolve_from_root(args.summary_csv)
    report_path = factorial.g35._resolve_from_root(args.report)
    _write_csv(summary_path, rows)
    _write_report(report_path, rows, audit)
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "summary_rows": len(rows),
                "summary_csv": str(summary_path),
                "report": str(report_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        RandomRobustnessError,
        factorial.PotentialFactorialError,
        factorial.g35.FullPopulationError,
        OSError,
        ValueError,
        yaml.YAMLError,
        json.JSONDecodeError,
    ) as exc:
        print(f"CIE random-robustness run failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
