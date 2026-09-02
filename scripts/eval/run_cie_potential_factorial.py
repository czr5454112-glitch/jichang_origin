#!/usr/bin/env python3
"""Run one preregistered CIE potential-factorial/common-executor cell.

The S4 factorial changes exactly two route-scoring inputs: the static
potential (strict free-flow ``H_FF`` or service-aware ``H_SA``) and the four
dynamic score terms Q/I/wc/ws (off or full).  Merge arbitration is held at the
same neutral FIFO protocol for every cell.  The companion CIE-DH adaptation
pair changes only ``H_FF`` versus ``H_SA``; its moving/stopped path-occupancy
term remains enabled and is not represented as an S4 factorial level.

This runner deliberately reuses the frozen G35 workload/release preparation
and G28 potential builders.  It reports full-population timing only when the
entire selected raw-bag population completes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import run_g4irsf24_native_race as g24  # noqa: E402
from scripts.eval import run_g4irsf26_paper_experiments as g26  # noqa: E402
from scripts.eval import run_g4irsf28_service_potential as g28  # noqa: E402
from scripts.eval import run_g4irsf35_full_population as g35  # noqa: E402


SCHEMA = "czr005.cie_potential_factorial.single_cell.v1"
S4_FULL_COMPONENT_MASK = 15
POTENTIAL_LABELS = {"ff": "H_FF", "sa": "H_SA"}
POTENTIAL_CELL_PREFIX = {"ff": "P0", "sa": "P1"}
DYNAMIC_CELL_SUFFIX = {"off": "D0", "full": "D1"}
POLICY_LABELS = {
    "s4": "G31_S4_NEUTRAL_FIFO",
    "cie_dh": "CIE_DH_COMMON_EXECUTOR_ADAPTED_NOT_EXACT",
}
REVISION_MANIFEST = ROOT / "configs/eval/cie_revision_manifest.yaml"


class PotentialFactorialError(RuntimeError):
    """Raised when a potential-factorial cell violates its fixed contract."""


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PotentialFactorialError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PotentialFactorialError(f"{name} must be finite")
    return result


def _git_value(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_args(args: argparse.Namespace) -> None:
    service_multiplier = _finite(
        getattr(args, "service_multiplier", 1.0), "service_multiplier"
    )
    if service_multiplier < 1.0:
        raise PotentialFactorialError(
            "service_multiplier must be at least 1.0 for the preregistered "
            "heterogeneity control"
        )
    if args.policy == "cie_dh" and args.dynamic != "full":
        raise PotentialFactorialError(
            "CIE-DH is an adaptation-decomposition pair, not an S4 dynamic "
            "factorial arm; use --dynamic full"
        )
    if args.release_mode == "same_hca" and args.scale != 1:
        raise PotentialFactorialError(
            "same-HCA release is eligible only for the 1x cells"
        )


def _g35_args(args: argparse.Namespace) -> argparse.Namespace:
    """Project this runner's CLI onto the frozen G35 preparation interface."""

    return argparse.Namespace(
        map=args.map,
        scale=args.scale,
        arm="g31" if args.policy == "s4" else "cie_dh_2009",
        coordination="neutral_fifo",
        s4_ablation="none",
        release_mode=args.release_mode,
        binary=args.binary,
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


def _changed_keys(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    if set(left) != set(right):
        return sorted(set(left) ^ set(right))
    return sorted(key for key in left if left[key] != right[key])


def _apply_service_multiplier(
    request: Mapping[str, Any], multiplier: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply the preregistered physical service-time stress without retuning.

    Every node retains its identity and all topology, tasks and releases remain
    unchanged.  Destination service is still excluded by the goal-arrival
    completion semantics and by ``H(g,g)=0`` in the potential builders.
    """

    prepared = dict(request)
    original = prepared["node_records"]
    if multiplier == 1.0:
        records = original
    else:
        records = []
        for source in original:
            row = list(source)
            if len(row) < 3:
                raise PotentialFactorialError(
                    "node_records must expose service time at index 2"
                )
            service = _finite(row[2], "node service time")
            if service < 0.0:
                raise PotentialFactorialError("node service time must be nonnegative")
            row[2] = service * multiplier
            records.append(row)
        prepared["node_records"] = records
    return prepared, {
        "enabled": multiplier != 1.0,
        "service_time_multiplier": multiplier,
        "source": "configs/eval/cie_revision_manifest.yaml",
        "topology_edges_tasks_release_unchanged": True,
        "goal_service_excluded_by_goal_arrival_semantics": True,
        "posthoc_tuning": False,
    }


def _potential_pair(
    request: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build and audit both static matrices before selecting either arm."""

    ff_request, ff_contract = g28.apply_free_flow_potential(request)
    sa_request, sa_contract = g28.apply_service_aware_potential(request)
    for label, prepared in (("H_FF", ff_request), ("H_SA", sa_request)):
        changed = _changed_keys(request, prepared)
        if any(key != "heuristic_time" for key in changed):
            raise PotentialFactorialError(
                f"{label} changed non-potential request fields: {changed}"
            )

    ff_matrix = ff_request["heuristic_time"]
    sa_matrix = sa_request["heuristic_time"]
    if not isinstance(ff_matrix, list) or not isinstance(sa_matrix, list):
        raise PotentialFactorialError("potential builders must return matrix lists")
    if len(ff_matrix) != len(sa_matrix):
        raise PotentialFactorialError("H_FF and H_SA matrix sizes differ")
    node_count = len(ff_matrix)
    if any(not isinstance(row, list) or len(row) != node_count for row in ff_matrix):
        raise PotentialFactorialError("H_FF must be a square dense matrix")
    if any(not isinstance(row, list) or len(row) != node_count for row in sa_matrix):
        raise PotentialFactorialError("H_SA must be a square dense matrix")

    ff_contract = {
        **ff_contract,
        "node_service_time_included": False,
        "queue_or_calendar_state_included": False,
        "fault_runtime_state_included": False,
    }
    sa_contract = {
        **sa_contract,
        "node_service_time_included": True,
        "queue_or_calendar_state_included": False,
        "fault_runtime_state_included": False,
    }
    requests = {"ff": ff_request, "sa": sa_request}
    artifacts = {
        key: {
            "label": POTENTIAL_LABELS[key],
            "contract": contract,
            "matrix_shape": [node_count, node_count],
            "matrix_sha256": _canonical_sha256(requests[key]["heuristic_time"]),
            "matrix_canonical_encoding": "sorted-key compact JSON; finite IEEE-754 values",
        }
        for key, contract in (("ff", ff_contract), ("sa", sa_contract))
    }
    return requests, artifacts


def _control_projection(request: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "scorer_mode",
        "s4_score_component_mask",
        "queue_time_scaling",
        "enable_s4_local_potential_descent_guard",
        "enable_s4_direct_neighbor_merge_calendar_visibility",
        "enable_cie_component_activation",
        "merge_grant_rule",
        "merge_grant_timing_mode",
        "g4irsf20_event_hotpath_policy",
        "pibt_mode",
        "pibt_preference_mode",
    )
    return {name: request.get(name) for name in fields if name in request}


def prepare_cell(
    args: argparse.Namespace,
) -> tuple[str, Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Prepare one cell without invoking the native runtime."""

    _validate_args(args)
    case_id, workload, base_request, release = g35._prepare(_g35_args(args))
    base_request, service_control = _apply_service_multiplier(
        base_request, float(getattr(args, "service_multiplier", 1.0))
    )
    if base_request.get("merge_grant_rule") != "M1":
        raise PotentialFactorialError("neutral FIFO requires merge_grant_rule=M1")
    if base_request.get("merge_grant_timing_mode") != "jit_fifo":
        raise PotentialFactorialError("neutral FIFO requires jit_fifo timing")

    requests, artifacts = _potential_pair(base_request)
    request = dict(requests[args.potential])
    if args.policy == "s4":
        inherited_mask = int(
            request.get("s4_score_component_mask", S4_FULL_COMPONENT_MASK)
        )
        if inherited_mask != S4_FULL_COMPONENT_MASK:
            raise PotentialFactorialError(
                f"S4 base request must start with full mask 15, got {inherited_mask}"
            )
        request["s4_score_component_mask"] = (
            0 if args.dynamic == "off" else S4_FULL_COMPONENT_MASK
        )
        request.setdefault("queue_time_scaling", "raw_count_as_seconds")
        request["enable_cie_component_activation"] = True
        cell_id = (
            POTENTIAL_CELL_PREFIX[args.potential]
            + DYNAMIC_CELL_SUFFIX[args.dynamic]
        )
    else:
        request["enable_cie_component_activation"] = False
        cell_id = (
            "CIE_DH_COMMON_EXECUTOR_"
            + ("FREE_FLOW" if args.potential == "ff" else "SERVICE_AWARE")
        )

    expected_scorer = (
        "FENG_DH_REIMPLEMENTATION_COEFFICIENTS_UNDISCLOSED"
        if args.policy == "cie_dh"
        else base_request.get("scorer_mode")
    )
    if request.get("scorer_mode") != expected_scorer:
        raise PotentialFactorialError(
            "prepared scorer identity does not match the requested policy"
        )

    potential = {
        "selected": args.potential,
        "selected_label": POTENTIAL_LABELS[args.potential],
        "selected_matrix_sha256": artifacts[args.potential]["matrix_sha256"],
        "artifacts": artifacts,
        "pair_matrix_differs": (
            artifacts["ff"]["matrix_sha256"]
            != artifacts["sa"]["matrix_sha256"]
        ),
        "topology_node_records_sha256": _canonical_sha256(
            request["node_records"]
        ),
        "topology_edge_records_sha256": _canonical_sha256(
            request["edge_records"]
        ),
        "selection_changes_only_heuristic_time": True,
    }
    return case_id, workload, request, release, {
        "cell_id": cell_id,
        "potential": potential,
        "service_heterogeneity_control": service_control,
    }


def _paper_subjects(
    summary: Mapping[str, Any],
    bags: Sequence[Mapping[str, Any]],
    workload: Any,
    request: Mapping[str, Any],
    release: Mapping[str, Any],
    *,
    formal_timing_eligible: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    integrity = g35._execution_integrity(summary, bags, workload, request)
    outcome = g26.summarize_paper_outcome(
        workload.rows, bags, total_raw_bags=workload.raw_bag_count
    )
    full_population = bool(
        integrity["pass"]
        and outcome.get("completed_raw_bag_count") == workload.raw_bag_count
        and int(summary.get("completed_count", -1)) == workload.segment_count
    )
    capacity = {
        "formal_fixed_horizon_eligible": integrity["pass"],
        "denominator_raw_bags": workload.raw_bag_count,
        "completed_raw_bag_count": outcome["completed_raw_bag_count"],
        "completion_rate": outcome["success"]["primary_completed_raw_bags"][
            "rate"
        ],
        "finish_le_std": outcome["success"]["finish_le_std"],
        "finish_le_std_minus_2700_literal": outcome["success"][
            "finish_le_std_minus_2700_literal"
        ],
    }
    if full_population and formal_timing_eligible:
        distributions, raw = g24.timing_distributions(workload.rows, bags)
        timing = {
            "status": "FULL_POPULATION_RAW_BAG_TIMING",
            "raw_bag_count": len(raw),
            "survivor_or_common_cohort_used": False,
            "formal_same_hca_release_arm_eligible": bool(
                release["formal_same_hca_release_input"]
            ),
            "formal_comparison_requires_matching_other_arm": True,
            "metrics_seconds": {
                "paper_network_from_admission": g35._paper_five(
                    outcome["paper_raw_bag_tth"]["distribution"]
                ),
                "segment_release": g35._five(distributions["java_release"]),
                "original_entry": g35._five(distributions["original_entry"]),
            },
        }
    elif not formal_timing_eligible:
        timing = {
            "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
            "raw_bag_count": None,
            "survivor_or_common_cohort_used": False,
            "formal_same_hca_release_arm_eligible": False,
            "formal_comparison_requires_matching_other_arm": True,
            "metrics_seconds": None,
        }
    else:
        timing = {
            "status": "NOT_MEASURED_FULL_POPULATION_INCOMPLETE",
            "raw_bag_count": None,
            "survivor_or_common_cohort_used": False,
            "formal_same_hca_release_arm_eligible": False,
            "formal_comparison_requires_matching_other_arm": True,
            "metrics_seconds": None,
        }
    return integrity, {
        "fixed_horizon_capacity": capacity,
        "full_population_raw_bag_timing": timing,
    }


def _mechanism_fields(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Retain activation plus J2/M3, P2 and E2 evidence without trace growth."""

    tokens = (
        "activation",
        "s4_",
        "merge_grant",
        "destination_merge",
        "pibt",
        "priority_",
        "event_hotpath",
        "arbitration_event",
        "stale_arbitration",
        "superseded_arbitration",
        "reservation",
        "fault_",
        "calendar",
    )
    return {
        key: value
        for key, value in summary.items()
        if any(token in key for token in tokens)
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    _validate_args(args)
    binary = g35._resolve_from_root(Path(args.binary)).resolve(strict=True)
    args.binary = binary
    case_id, workload, request, release, prepared = prepare_cell(args)
    control_projection = _control_projection(request)
    common = {
        "schema": SCHEMA,
        "case_id": case_id,
        "map": args.map,
        "scale": args.scale,
        "population": {
            "raw_bag_count": workload.raw_bag_count,
            "segment_count": workload.segment_count,
            "whole_population": True,
        },
        "release_protocol": release,
        "provenance": {
            "git_commit": _git_value("rev-parse", "HEAD"),
            "git_branch": _git_value("branch", "--show-current"),
            "experiment_manifest_path": str(REVISION_MANIFEST.resolve()),
            "experiment_manifest_sha256": _file_sha256(REVISION_MANIFEST),
            "workload_path": str(workload.source_path.resolve()),
            "workload_sha256": _file_sha256(workload.source_path.resolve()),
            "executor_identity": "COMMON_CPP_EVENT_EXECUTOR",
            "random_seed": None,
            "survivor_timing_used": False,
        },
        "binary": {
            "path": str(binary),
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "same_binary_required_for_every_common_executor_cell": True,
        },
        "algorithm": {
            "cell_id": prepared["cell_id"],
            "policy": args.policy,
            "policy_label": POLICY_LABELS[args.policy],
            "baseline_family": (
                "G31_S4"
                if args.policy == "s4"
                else "CIE_DH_2009_COMMON_EXECUTOR_ADAPTATION"
            ),
            "reproduction_or_adaptation_label": (
                "COMMON_EXECUTOR_ROUTE_ISOLATION"
                if args.policy == "s4"
                else "ADAPTED_NOT_EXACT_NOT_FENG_NATIVE"
            ),
            "scorer_mode": request["scorer_mode"],
            "factorial_membership": args.policy == "s4",
            "dynamic": args.dynamic,
            "dynamic_scope": (
                "Q_I_wc_ws_mask_only"
                if args.policy == "s4"
                else "moving_stopped_path_occupancy_held_full"
            ),
            "s4_score_component_mask": request.get("s4_score_component_mask"),
            "coordination_protocol": "neutral_fifo",
            "merge_grant_rule": request["merge_grant_rule"],
            "merge_grant_timing_mode": request["merge_grant_timing_mode"],
            "strict_descent_held_at_base_setting": request.get(
                "enable_s4_local_potential_descent_guard"
            ),
            "control_projection": control_projection,
            "control_projection_sha256": _canonical_sha256(control_projection),
            "posthoc_tuning": False,
        },
        "potential": prepared["potential"],
        "service_heterogeneity_control": prepared[
            "service_heterogeneity_control"
        ],
        "fixed_window": {
            "start_epoch": g35.nanning_native.FIXED_START_EPOCH,
            "max_epochs": g35.nanning_native.HCA_MAX_EPOCHS,
            "end_epoch": g35.nanning_native.FIXED_END_EPOCH,
            "max_events": g35.nanning_native.MAX_EVENTS,
            "speed_mps": g35.SPEED_MPS,
        },
    }
    if args.dry_run:
        return {
            **common,
            "status": "READY_CIE_POTENTIAL_FACTORIAL_DRY_RUN",
            "native_execution_started": False,
        }

    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise PotentialFactorialError(
            "native runtime did not return summary and bag rows"
        )
    if any(not isinstance(row, Mapping) for row in bags):
        raise PotentialFactorialError("native runtime returned a non-object bag row")

    integrity, paper_subjects = _paper_subjects(
        summary,
        bags,
        workload,
        request,
        release,
        formal_timing_eligible=args.scale == 1,
    )
    native_summary = dict(summary)
    return {
        **common,
        "status": "COMPLETE" if integrity["pass"] else "FAILED_INTEGRITY",
        "native_execution_started": True,
        "paper_subjects": paper_subjects,
        "execution_integrity": integrity,
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "peak_rss_bytes": "NOT_MEASURED",
            "native_summary": native_summary,
            "mechanism_activation_j2_p2_e2": _mechanism_fields(native_summary),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", choices=("nanning", "map2"), required=True)
    parser.add_argument("--scale", type=int, choices=(1, 2), required=True)
    parser.add_argument("--policy", choices=("s4", "cie_dh"), required=True)
    parser.add_argument("--potential", choices=("ff", "sa"), required=True)
    parser.add_argument("--dynamic", choices=("off", "full"), default="full")
    parser.add_argument(
        "--service-multiplier",
        type=float,
        default=1.0,
        help="Preregistered multiplier for the physical node service profile.",
    )
    parser.add_argument(
        "--release-mode", choices=("canonical", "same_hca"), default="canonical"
    )
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--nanning-task-dir",
        type=Path,
        default=g35.nanning_native.DEFAULT_TASK_DIR,
    )
    parser.add_argument(
        "--nanning-map-profile",
        type=Path,
        default=g35.nanning_native.DEFAULT_MAP_PROFILE,
    )
    parser.add_argument(
        "--nanning-hca-root",
        type=Path,
        default=g35.nanning_paired.DEFAULT_HCA_ROOT,
    )
    parser.add_argument(
        "--map2-workload-1x",
        type=Path,
        default=g35.map2_native.DEFAULT_WORKLOAD_1X,
    )
    parser.add_argument(
        "--map2-workload-2x",
        type=Path,
        default=g35.map2_native.DEFAULT_WORKLOAD_2X,
    )
    parser.add_argument("--map2-hca-case-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _validate_args(args)
    output = g35._resolve_from_root(args.output)
    if output.exists() and not args.force:
        raise PotentialFactorialError(
            f"output exists; pass --force to replace: {output}"
        )
    result = execute(args)
    g35._write_json(output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "case_id": result["case_id"],
                "cell_id": result["algorithm"]["cell_id"],
                "output": str(output),
            }
        )
    )
    return 0 if result["status"] in {
        "COMPLETE",
        "READY_CIE_POTENTIAL_FACTORIAL_DRY_RUN",
    } else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        PotentialFactorialError,
        g35.FullPopulationError,
        g28.ServicePotentialError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"CIE potential-factorial run failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
