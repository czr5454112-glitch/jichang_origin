#!/usr/bin/env python3
"""Run one frozen 1x CIE service-rate-normalization comparison cell.

The three arms use only the two existing S4 request controls.  The raw and
normalized arms retain the full Q/I/wc/ws mask.  ``NO_QI_BUT_CALENDAR`` uses
mask 12 (wc + ws), so both calendar-derived score terms, direct-neighbour
calendar visibility, and the physical service calendars remain enabled.

The transparent control is read from the frozen CIE revision manifest.  Its
2x service profile is applied to the shared physical node records and H_SA is
rebuilt before selecting an arm.  A node that is one bag's goal may still be
another bag's transit node; goal service is excluded per bag by the existing
goal-arrival completion semantics, not by removing a global union of nodes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import cie_fixed_denominator_business as cie_business  # noqa: E402
from scripts.eval import run_cie_potential_factorial as factorial  # noqa: E402
from scripts.eval import run_g4irsf35_full_population as g35  # noqa: E402


SCHEMA = "czr005.cie_service_normalization.single_cell.v1"
REVISION_MANIFEST = ROOT / "configs/eval/cie_revision_manifest.yaml"
MAPS = ("map2", "nanning")
SCALE = 1
SERVICE_CONDITIONS = ("REAL_SERVICE", "SERVICE_X2")
COMPONENT_BITS = {"Q": 1, "I": 2, "wc": 4, "ws": 8}
ARMS: Mapping[str, Mapping[str, Any]] = {
    "RAW_COUNT_AS_SECONDS": {
        "queue_time_scaling": "raw_count_as_seconds",
        "s4_score_component_mask": 15,
    },
    "SERVICE_RATE_NORMALIZED": {
        "queue_time_scaling": "service_rate_normalized",
        "s4_score_component_mask": 15,
    },
    "NO_QI_BUT_CALENDAR": {
        "queue_time_scaling": "raw_count_as_seconds",
        "s4_score_component_mask": 12,
    },
}


class ServiceNormalizationError(RuntimeError):
    """Raised when a cell would violate the frozen three-arm contract."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def _changed_fields(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    return sorted(
        key
        for key in set(before) | set(after)
        if _canonical_bytes(before.get(key)) != _canonical_bytes(after.get(key))
    )


def load_service_control(path: Path = REVISION_MANIFEST) -> dict[str, Any]:
    """Read and validate the frozen service-pressure-enhancement control."""

    resolved = path.resolve(strict=True)
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ServiceNormalizationError("revision manifest must be a YAML object")
    if payload.get("frozen_before_formal_result_read") is not True:
        raise ServiceNormalizationError("revision manifest is not marked frozen")
    block = payload.get("service_heterogeneity_control")
    if not isinstance(block, Mapping):
        raise ServiceNormalizationError(
            "revision manifest lacks service_heterogeneity_control"
        )
    gates = {
        "registered_construction": (
            block.get("construction") == "multiply_existing_non_goal_service_time"
        ),
        "registered_multiplier": block.get("multiplier") == 2.0,
        "topology_tasks_release_unchanged": (
            block.get("topology_tasks_and_release_unchanged") is True
        ),
    }
    if not all(gates.values()):
        raise ServiceNormalizationError(
            f"service control differs from the frozen contract: {gates}"
        )
    return {
        "manifest_path": str(resolved),
        "manifest_sha256": _file_sha256(resolved),
        "construction": str(block["construction"]),
        "multiplier": float(block["multiplier"]),
        "topology_tasks_and_release_unchanged": True,
        "validation_gates": gates,
    }


def _g35_args(args: argparse.Namespace) -> argparse.Namespace:
    """Project the specialty CLI onto the unchanged G31 preparation path."""

    return argparse.Namespace(
        map=args.map,
        scale=SCALE,
        arm="g31",
        coordination="g31",
        s4_ablation="none",
        release_mode="canonical",
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


def _validate_args(args: argparse.Namespace) -> None:
    if args.map not in MAPS:
        raise ServiceNormalizationError(f"unsupported map: {args.map}")
    if int(args.scale) != SCALE:
        raise ServiceNormalizationError("service normalization is frozen at 1x")
    if args.arm not in ARMS:
        raise ServiceNormalizationError(f"unregistered arm: {args.arm}")
    if args.service_condition not in SERVICE_CONDITIONS:
        raise ServiceNormalizationError(
            f"unregistered service condition: {args.service_condition}"
        )
    if args.release_mode != "canonical":
        raise ServiceNormalizationError(
            "service normalization uses the canonical original-paper release"
        )


def prepare_cell(
    args: argparse.Namespace,
) -> tuple[str, Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Prepare a cell without invoking the native runtime."""

    _validate_args(args)
    manifest = load_service_control(Path(args.revision_manifest))
    case_id, workload, original, release = g35._prepare(_g35_args(args))
    multiplier = (
        1.0
        if args.service_condition == "REAL_SERVICE"
        else float(manifest["multiplier"])
    )

    stressed, helper_contract = factorial._apply_service_multiplier(
        original, multiplier
    )
    expected_service_delta = [] if multiplier == 1.0 else ["node_records"]
    actual_service_delta = _changed_fields(original, stressed)
    if actual_service_delta != expected_service_delta:
        raise ServiceNormalizationError(
            "service control changed unexpected request fields: "
            f"{actual_service_delta}"
        )
    if _canonical_bytes(original.get("edge_records")) != _canonical_bytes(
        stressed.get("edge_records")
    ) or _canonical_bytes(original.get("bag_records")) != _canonical_bytes(
        stressed.get("bag_records")
    ):
        raise ServiceNormalizationError(
            "service control changed topology, tasks, or releases"
        )

    potential_requests, potential_artifacts = factorial._potential_pair(stressed)
    raw_reference = dict(potential_requests["sa"])
    raw_reference["queue_time_scaling"] = "raw_count_as_seconds"
    raw_reference["s4_score_component_mask"] = 15

    base_gates = {
        "scale_1x": args.scale == SCALE,
        "canonical_release": args.release_mode == "canonical",
        "native_s4": raw_reference.get("scorer_mode")
        == "S4_queue_aware_rule_only",
        "full_mask_base": raw_reference.get("s4_score_component_mask") == 15,
        "raw_count_base": raw_reference.get("queue_time_scaling")
        == "raw_count_as_seconds",
        "strict_local_descent_unchanged": raw_reference.get(
            "enable_s4_local_potential_descent_guard"
        )
        is True,
        "direct_neighbor_calendar_visibility_unchanged": raw_reference.get(
            "enable_s4_direct_neighbor_merge_calendar_visibility"
        )
        is True,
        "goal_arrival_completion_unchanged": raw_reference.get(
            "complete_on_goal_arrival"
        )
        is True,
        "j2_m3_unchanged": raw_reference.get("merge_grant_rule") == "M3",
        "jit_fair_aging_deadline_unchanged": raw_reference.get(
            "merge_grant_timing_mode"
        )
        == "jit_fair_aging_deadline",
        "e2_unchanged": raw_reference.get("g4irsf20_event_hotpath_policy")
        == "E2",
    }
    if not all(base_gates.values()):
        raise ServiceNormalizationError(
            f"G31 service-normalization base identity failed: {base_gates}"
        )

    request = dict(raw_reference)
    request.update(ARMS[args.arm])
    arm_delta = _changed_fields(raw_reference, request)
    expected_arm_delta = {
        "RAW_COUNT_AS_SECONDS": [],
        "SERVICE_RATE_NORMALIZED": ["queue_time_scaling"],
        "NO_QI_BUT_CALENDAR": ["s4_score_component_mask"],
    }[args.arm]
    if arm_delta != expected_arm_delta:
        raise ServiceNormalizationError(
            f"arm changed fields outside its exact contract: {arm_delta}"
        )

    mask = int(request["s4_score_component_mask"])
    component_enabled = {
        name: bool(mask & bit) for name, bit in COMPONENT_BITS.items()
    }
    if args.arm == "NO_QI_BUT_CALENDAR" and component_enabled != {
        "Q": False,
        "I": False,
        "wc": True,
        "ws": True,
    }:
        raise ServiceNormalizationError(
            "NO_QI_BUT_CALENDAR is not the exact existing mask-12 interface"
        )

    comparison_identity = {
        "case_id": case_id,
        "map": args.map,
        "scale": SCALE,
        "release_protocol_sha256": _sha256_value(release),
        "raw_reference_request_sha256": _sha256_value(raw_reference),
        "node_records_sha256": _sha256_value(request["node_records"]),
        "edge_records_sha256": _sha256_value(request["edge_records"]),
        "bag_records_sha256": _sha256_value(request["bag_records"]),
        "h_sa_matrix_sha256": _sha256_value(request["heuristic_time"]),
        "service_condition": args.service_condition,
        "service_time_multiplier": multiplier,
    }
    non_service_reference = {
        key: value
        for key, value in raw_reference.items()
        if key not in {"node_records", "heuristic_time", "expected_binary_path"}
    }
    cross_service_condition_identity = {
        "case_id": case_id,
        "map": args.map,
        "scale": SCALE,
        "release_protocol_sha256": _sha256_value(release),
        "base_node_records_sha256": _sha256_value(original["node_records"]),
        "edge_records_sha256": _sha256_value(original["edge_records"]),
        "bag_records_sha256": _sha256_value(original["bag_records"]),
        "non_service_reference_request_sha256": _sha256_value(
            non_service_reference
        ),
    }
    contract = {
        "arm": args.arm,
        "arm_delta_from_raw_reference": arm_delta,
        "sole_arm_controls": [
            "queue_time_scaling",
            "s4_score_component_mask",
        ],
        "queue_time_scaling": request["queue_time_scaling"],
        "s4_score_component_mask": mask,
        "component_enabled": component_enabled,
        "no_qi_but_calendar_exact_existing_interface": (
            args.arm != "NO_QI_BUT_CALENDAR"
            or (
                mask == 12
                and request["queue_time_scaling"] == "raw_count_as_seconds"
                and request[
                    "enable_s4_direct_neighbor_merge_calendar_visibility"
                ]
                is True
            )
        ),
        "calendar_semantics": {
            "corridor_wait_score_component_retained": bool(mask & 4),
            "target_service_wait_score_component_retained": bool(mask & 8),
            "direct_neighbor_calendar_visibility_retained": request[
                "enable_s4_direct_neighbor_merge_calendar_visibility"
            ]
            is True,
            "physical_service_calendar_not_controlled_by_score_mask": True,
            "new_native_mode_added": False,
        },
        "base_identity_gates": base_gates,
        "service_control": {
            **manifest,
            **helper_contract,
            "condition": args.service_condition,
            "service_time_multiplier": multiplier,
            "changed_request_fields_before_h_sa_rebuild": actual_service_delta,
            "all_shared_physical_node_records_receive_multiplier": (
                multiplier != 1.0
            ),
            "per_bag_goal_service_not_executed_by_goal_arrival_semantics": True,
            "goal_union_was_not_globally_excluded": True,
            "same_node_remains_perturbed_when_transit_for_another_bag": True,
        },
        "potential": {
            "selected": "sa",
            "selected_label": "H_SA",
            "rebuilt_after_service_control": True,
            "artifact": potential_artifacts["sa"],
        },
        "comparison_identity": comparison_identity,
        "comparison_identity_sha256": _sha256_value(comparison_identity),
        "cross_service_condition_identity": cross_service_condition_identity,
        "cross_service_condition_identity_sha256": _sha256_value(
            cross_service_condition_identity
        ),
    }
    return case_id, workload, request, release, contract


def execute(
    args: argparse.Namespace, *, executor: Any | None = None
) -> dict[str, Any]:
    """Execute one map/service/arm cell or return its dry-run contract."""

    _validate_args(args)
    args.binary = g35._resolve_from_root(Path(args.binary)).resolve(strict=True)
    args.revision_manifest = g35._resolve_from_root(
        Path(args.revision_manifest)
    ).resolve(strict=True)
    case_id, workload, request, release, contract = prepare_cell(args)
    workload_path = factorial._workload_source_path(workload)
    binary_sha = _file_sha256(args.binary)
    workload_sha = _file_sha256(workload_path)
    git_commit = _git_value("rev-parse", "HEAD")
    git_branch = _git_value("branch", "--show-current")
    comparison_identity = {
        **contract["comparison_identity"],
        "binary_sha256": binary_sha,
        "workload_sha256": workload_sha,
        "git_commit": git_commit,
    }
    contract["comparison_identity"] = comparison_identity
    contract["comparison_identity_sha256"] = _sha256_value(comparison_identity)
    cross_service_condition_identity = {
        **contract["cross_service_condition_identity"],
        "binary_sha256": binary_sha,
        "workload_sha256": workload_sha,
        "git_commit": git_commit,
    }
    contract[
        "cross_service_condition_identity"
    ] = cross_service_condition_identity
    contract["cross_service_condition_identity_sha256"] = _sha256_value(
        cross_service_condition_identity
    )
    common = {
        "schema": SCHEMA,
        "case_id": case_id,
        "map": args.map,
        "scale": SCALE,
        "service_condition": args.service_condition,
        "population": {
            "raw_bag_count": workload.raw_bag_count,
            "segment_count": workload.segment_count,
            "whole_population": True,
        },
        "release_protocol": release,
        "algorithm": {
            "policy": "s4_service_normalization_specialty",
            "policy_label": "G31_S4_NATIVE_SERVICE_NORMALIZATION_SPECIALTY",
            "arm": args.arm,
            "cell_id": f"{args.service_condition}__{args.arm}",
            "coordination_protocol": "G31_J2_M3",
            "scorer_mode": request["scorer_mode"],
            "queue_time_scaling": request["queue_time_scaling"],
            "s4_score_component_mask": request["s4_score_component_mask"],
            "component_enabled": contract["component_enabled"],
            "posthoc_tuning": False,
        },
        "potential": {
            "selected": "sa",
            "selected_label": "H_SA",
            "matrix_sha256": contract["potential"]["artifact"]["matrix_sha256"],
            "rebuilt_after_service_control": True,
        },
        "service_normalization_contract": contract,
        "fixed_window": {
            "start_epoch": g35.nanning_native.FIXED_START_EPOCH,
            "max_epochs": g35.nanning_native.HCA_MAX_EPOCHS,
            "end_epoch": g35.nanning_native.FIXED_END_EPOCH,
            "max_events": g35.nanning_native.MAX_EVENTS,
            "speed_mps": g35.SPEED_MPS,
        },
        "provenance": {
            "git_commit": git_commit,
            "git_branch": git_branch,
            "revision_manifest_path": str(args.revision_manifest),
            "revision_manifest_sha256": _file_sha256(args.revision_manifest),
            "workload_path": str(workload_path),
            "workload_sha256": workload_sha,
            "executor_identity": "COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE",
            "random_seed": None,
            "survivor_timing_used": False,
        },
        "binary": {
            "path": str(args.binary),
            "sha256": binary_sha,
            "same_binary_required_for_all_three_arms": True,
        },
    }
    if args.dry_run:
        return {
            **common,
            "status": "READY_CIE_SERVICE_NORMALIZATION_DRY_RUN",
            "native_execution_started": False,
        }

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = selected_executor(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise ServiceNormalizationError(
            "native runtime did not return summary and bag rows"
        )
    if any(not isinstance(row, Mapping) for row in bags):
        raise ServiceNormalizationError(
            "native runtime returned a non-object bag row"
        )

    integrity, paper_subjects = factorial._paper_subjects(
        summary,
        bags,
        workload,
        request,
        release,
        formal_timing_eligible=True,
    )
    gates = dict(integrity["gates"])
    gates.update(
        {
            "queue_time_scaling_echo": summary.get("queue_time_scaling")
            == request["queue_time_scaling"],
            "s4_score_component_mask_echo": summary.get(
                "s4_score_component_mask"
            )
            == request["s4_score_component_mask"],
            "strict_local_descent_echo": summary.get(
                "s4_local_potential_descent_guard_enabled"
            )
            is True,
            "direct_neighbor_calendar_visibility_echo": summary.get(
                "s4_direct_neighbor_merge_calendar_visibility_enabled"
            )
            is True,
            "goal_arrival_completion_echo": summary.get(
                "complete_on_goal_arrival_enabled"
            )
            is True,
            "loaded_cpp_binary_sha256_echo": summary.get(
                "loaded_cpp_binary_sha256"
            )
            == binary_sha,
        }
    )
    integrity = {"gates": gates, "pass": all(gates.values())}
    if not integrity["pass"]:
        paper_subjects["fixed_horizon_capacity"][
            "formal_fixed_horizon_eligible"
        ] = False
        timing = paper_subjects["full_population_raw_bag_timing"]
        if timing.get("status") == "FULL_POPULATION_RAW_BAG_TIMING":
            timing.update(
                status="REJECTED_SERVICE_NORMALIZATION_INTEGRITY",
                raw_bag_count=None,
                metrics_seconds=None,
            )
    paper_subjects["fixed_denominator_business"] = cie_business.summarize(
        workload.rows,
        bags,
        fixed_horizon=g35.nanning_native.FIXED_END_EPOCH,
    )
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
            "native_summary": dict(summary),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", choices=MAPS, required=True)
    parser.add_argument("--scale", type=int, choices=(SCALE,), default=SCALE)
    parser.add_argument("--arm", choices=tuple(ARMS), required=True)
    parser.add_argument(
        "--service-condition", choices=SERVICE_CONDITIONS, required=True
    )
    parser.add_argument(
        "--release-mode", choices=("canonical",), default="canonical"
    )
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--revision-manifest", type=Path, default=REVISION_MANIFEST
    )
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
        raise ServiceNormalizationError(
            f"output exists; pass --force to replace: {output}"
        )
    result = execute(args)
    g35._write_json(output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "map": result["map"],
                "service_condition": result["service_condition"],
                "arm": result["algorithm"]["arm"],
                "output": str(output),
            }
        )
    )
    return 0 if result["status"] in {
        "COMPLETE",
        "READY_CIE_SERVICE_NORMALIZATION_DRY_RUN",
    } else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ServiceNormalizationError,
        factorial.PotentialFactorialError,
        g35.FullPopulationError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ) as exc:
        print(f"CIE service-normalization run failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
