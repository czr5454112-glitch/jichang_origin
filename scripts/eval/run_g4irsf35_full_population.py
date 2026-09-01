#!/usr/bin/env python3
"""Run one full-population G31/S5/literature-baseline stable cell at 2.5 m/s.

The primary view uses the canonical scheduled arrivals and the frozen G31
fixed horizon.  An exact same-HCA-release input is optionally available for
eligible 1x evidence only.  This runner never reports survivor/common-cohort
timing: raw-bag latency is emitted only when every selected raw bag completes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
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
from scripts.eval import run_g4irsf31_map2_native as map2_native  # noqa: E402
from scripts.eval import (  # noqa: E402
    run_g4irsf31_map2_same_hca_release_timing as map2_paired,
)
from scripts.eval import run_g4irsf31_nanning_native as nanning_native  # noqa: E402
from scripts.eval import (  # noqa: E402
    run_g4irsf31_same_hca_release_timing as nanning_paired,
)


SCHEMA = "czr005.g4irsf35.full_population_single_arm.v1"
SPEED_MPS = 2.5
S5_DELTA: Mapping[str, Any] = {
    "scorer_mode": "S5_dynamic_workload_oracle",
    "enable_s4_local_potential_descent_guard": False,
    "enable_s4_direct_neighbor_merge_calendar_visibility": False,
}
SSP_TIME_DELTA: Mapping[str, Any] = {
    "scorer_mode": "S3_shortest_potential_only",
    "enable_s4_local_potential_descent_guard": False,
    "enable_s4_direct_neighbor_merge_calendar_visibility": False,
}
FENG_DH_DELTA: Mapping[str, Any] = {
    "scorer_mode": "FENG_DH_REIMPLEMENTATION_COEFFICIENTS_UNDISCLOSED",
    "enable_s4_local_potential_descent_guard": False,
    "enable_s4_direct_neighbor_merge_calendar_visibility": False,
}
TARAU_DISTRIBUTED_2010_DELTA: Mapping[str, Any] = {
    "scorer_mode": "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY",
    "enable_s4_local_potential_descent_guard": False,
    "enable_s4_direct_neighbor_merge_calendar_visibility": False,
}
NEUTRAL_FIFO_DELTA: Mapping[str, Any] = {
    "merge_grant_rule": "M1",
    "merge_grant_timing_mode": "jit_fifo",
}
S4_ABLATION_DELTAS: Mapping[str, Mapping[str, Any]] = {
    "none": {},
    "a0_h_only": {"s4_score_component_mask": 0},
    "a1_h_q": {"s4_score_component_mask": 1},
    "a2_h_q_i": {"s4_score_component_mask": 3},
    "b1_full_minus_q": {"s4_score_component_mask": 14},
    "b2_full_minus_i": {"s4_score_component_mask": 13},
    "b4_full_minus_ws": {"s4_score_component_mask": 7},
    "b5_full_minus_strict_descent": {
        "enable_s4_local_potential_descent_guard": False,
    },
    "f1_service_rate_normalized": {
        "queue_time_scaling": "service_rate_normalized",
    },
}
MODEL_BACKED_REQUEST_FIELDS = (
    "scorer_model_path",
    "g4irsf24_dlp_artifact",
)
ARM_LABELS = {
    "g31": "G31_S4",
    "s5": "G35_S5_DYNAMIC_WORKLOAD_ORACLE",
    # This is the repository's physical-time adaptation of Sorensen SSP.  It
    # is not the DHA implementation from Feng's paper.
    "ssp_time": "SSP_TIME_ADAPTATION_NOT_FENG_DHA",
    "feng_dh": "TARAU_LOCAL_2009_CIE_DH_ADAPTED_NOT_EXACT",
    "tarau_local_2009": "TARAU_LOCAL_2009_CIE_DH_ADAPTED_NOT_EXACT",
    "cie_dh_2009": "TARAU_LOCAL_2009_CIE_DH_ADAPTED_NOT_EXACT",
    "tarau_distributed_2010": (
        "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY_NOT_EXACT"
    ),
}
FIVE_FIELDS = {
    "min": "min_seconds",
    "mean": "mean_seconds",
    "p95": "p95_seconds",
    "p99": "p99_seconds",
    "max": "max_seconds",
}


class FullPopulationError(RuntimeError):
    """Raised when a requested full-population cell is not well formed."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FullPopulationError(f"JSON object required: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _resolve_from_root(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FullPopulationError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise FullPopulationError(f"{name} must be finite")
    return result


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise FullPopulationError(
                    f"JSONL object required at {path}:{line_number}"
                )
            rows.append(row)
    return tuple(rows)


def _nanning_canonical_path(task_dir: Path, manifest: Mapping[str, Any]) -> Path:
    reference = Path(str(manifest["canonical_output"]))
    if reference.is_absolute():
        return reference.resolve(strict=True)
    candidates = [ROOT / reference, task_dir / reference.name]
    candidates.extend(parent / reference for parent in task_dir.parents)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FullPopulationError(
        f"cannot resolve Nanning canonical workload {reference} from {task_dir}"
    )


def _load_nanning_workload(
    scale: int, task_dir: Path
) -> nanning_native.Workload:
    manifest_path = task_dir / f"nanning_{scale}x_manifest.json"
    manifest = _read_json(manifest_path)
    expected_raw, expected_segments = nanning_native.SCALE_COUNTS[scale]
    canonical_path = _nanning_canonical_path(task_dir, manifest)
    rows = _read_jsonl(canonical_path)
    segment_ids = [str(row.get("segment_id", "")) for row in rows]
    raw_ids = {int(row["task_id"]) for row in rows}
    lifecycle = manifest.get("lifecycle")
    gates = {
        "schema": manifest.get("schema") == nanning_native.WORKLOAD_SCHEMA,
        "status": manifest.get("status") == "COMPLETE",
        "scale": manifest.get("scale") == scale,
        "map": manifest.get("map_id") == nanning_native.MAP_ID,
        "raw_count": len(raw_ids) == expected_raw,
        "segment_count": len(rows) == expected_segments,
        "unique_nonempty_segment_ids": (
            all(segment_ids) and len(segment_ids) == len(set(segment_ids))
        ),
        "storage_lifecycle": (
            isinstance(lifecycle, Mapping)
            and lifecycle.get("storage_in_goal") == nanning_native.STORAGE_NODE
            and lifecycle.get("storage_out_start") == nanning_native.STORAGE_NODE
        ),
    }
    if not all(gates.values()):
        raise FullPopulationError(f"Nanning workload gate failed: {gates}")
    return nanning_native.Workload(
        scale=scale,
        manifest_path=manifest_path.resolve(),
        canonical_path=canonical_path,
        manifest=manifest,
        rows=rows,
        raw_bag_count=expected_raw,
        segment_count=expected_segments,
    )


def _align_nanning_1x(
    case: nanning_native.CaseSpec,
    workload: nanning_native.Workload,
    hca_root: Path,
) -> tuple[nanning_native.Workload, dict[str, Any]]:
    alignment = nanning_paired.align_to_audited_hca_release(
        case, workload, hca_root
    )
    if alignment.workload is None:
        raise FullPopulationError(
            "Nanning same-HCA release is not eligible: "
            f"trace={alignment.trace_gate.get('status')} "
            f"timing={alignment.hca_timing.get('status')}"
        )
    return alignment.workload, {
        "status": alignment.trace_gate.get("status"),
        "pass": alignment.trace_gate.get("pass") is True,
        "hca_case_id": alignment.trace_gate.get("hca_case_id"),
        "reference_run_id": alignment.trace_gate.get("reference_run_id"),
        "hca_full_population_timing_pass": (
            alignment.hca_timing.get("pass") is True
        ),
        "source_root": str(hca_root.resolve()),
    }


def _align_map2_1x(
    case: map2_native.CaseSpec,
    workload: map2_native.Workload,
    hca_case_root: Path,
) -> tuple[map2_native.Workload, dict[str, Any]]:
    # The archived canonical G24 2.5 m/s run predates an explicit speed field.
    # The existing G31 gate identifies that run by its registered formal root.
    # A caller-supplied relocated archive is therefore registered as that same
    # root for this read-only gate invocation; all release/population/repeat
    # checks in inspect_hca_case remain active.
    original_roots = map2_paired.FORMAL_HCA_CASE_ROOTS
    relocated_roots = dict(original_roots)
    relocated_roots[(1, SPEED_MPS)] = hca_case_root.resolve()
    map2_paired.FORMAL_HCA_CASE_ROOTS = relocated_roots
    try:
        alignment = map2_paired.align_to_hca_release(
            case, workload, hca_case_root.resolve()
        )
    finally:
        map2_paired.FORMAL_HCA_CASE_ROOTS = original_roots
    if alignment.workload is None:
        raise FullPopulationError(
            "map2 same-HCA release is not eligible: "
            f"trace={alignment.trace_gate.get('status')} "
            f"timing={alignment.hca_timing.get('status')}"
        )
    return alignment.workload, {
        "status": alignment.trace_gate.get("status"),
        "pass": alignment.trace_gate.get("pass") is True,
        "reference_run_id": "run_01",
        "hca_full_population_timing_pass": (
            alignment.hca_timing.get("pass") is True
        ),
        "source_root": str(hca_case_root.resolve()),
    }


def _five(distribution: Mapping[str, Any]) -> dict[str, float]:
    return {
        name: _finite(distribution.get(field), f"timing.{field}")
        for name, field in FIVE_FIELDS.items()
    }


def _paper_five(distribution: Mapping[str, Any]) -> dict[str, float]:
    seconds = distribution.get("seconds")
    if not isinstance(seconds, Mapping):
        raise FullPopulationError("paper raw-bag distribution lacks seconds")
    return {
        name: _finite(seconds.get(name), f"paper_timing.{name}")
        for name in FIVE_FIELDS
    }


def _execution_integrity(
    summary: Mapping[str, Any],
    bags: Sequence[Mapping[str, Any]],
    workload: nanning_native.Workload | map2_native.Workload,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    expected_ids = sorted(str(row["segment_id"]) for row in workload.rows)
    returned_ids = sorted(str(row.get("segment_id", "")) for row in bags)
    completed = int(summary.get("completed_count", -1))
    failed = int(summary.get("failed_count", -1))
    gates = {
        "returned_exact_selected_segments": returned_ids == expected_ids,
        "terminal_segment_partition": (
            completed + failed == workload.segment_count
        ),
        "fixed_end_epoch_echo": (
            _finite(
                summary.get("declared_max_simulation_time"),
                "declared_max_simulation_time",
            )
            == nanning_native.FIXED_END_EPOCH
        ),
        "max_events_echo": (
            int(summary.get("declared_max_events", -1))
            == nanning_native.MAX_EVENTS
        ),
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "reservation_conflicts_zero": (
            int(summary.get("reservation_conflicts", -1)) == 0
        ),
        "stable_fault_events_zero": int(summary.get("fault_event_count", -1)) == 0,
        "stable_repair_events_zero": (
            int(summary.get("repair_event_count", -1)) == 0
        ),
        "loaded_expected_binary": (
            Path(str(summary.get("loaded_cpp_binary_path", ""))).resolve()
            == Path(request["expected_binary_path"]).resolve()
        ),
        "scorer_mode_echo": summary.get("scorer_mode_echo")
        == request.get("scorer_mode"),
        "scorer_id_present": bool(str(summary.get("scorer_id", ""))),
    }
    if request.get("scorer_mode") == TARAU_DISTRIBUTED_2010_DELTA["scorer_mode"]:
        gates.update(
            {
                "tarau_neutral_fifo_merge_rule": (
                    summary.get("merge_grant_rule") == "M1"
                ),
                "tarau_neutral_fifo_timing": (
                    summary.get("merge_grant_timing_mode") == "jit_fifo"
                ),
                "tarau_s4_local_guard_disabled": not bool(
                    summary.get("s4_local_potential_descent_guard_enabled", False)
                ),
                "tarau_s4_calendar_visibility_disabled": not bool(
                    summary.get(
                        "s4_direct_neighbor_merge_calendar_visibility_enabled",
                        False,
                    )
                ),
                "tarau_runtime_full_astar_zero": (
                    int(summary.get("runtime_full_astar_calls", -1)) == 0
                ),
                "tarau_runtime_global_scan_zero": (
                    int(summary.get("scorer_runtime_global_scan_count", -1)) == 0
                ),
            }
        )
    return {"pass": all(gates.values()), "gates": gates}


def _validate_protocol_args(args: argparse.Namespace) -> None:
    if (
        args.arm == "tarau_distributed_2010"
        and args.coordination != "neutral_fifo"
    ):
        raise FullPopulationError(
            "Tarau-2010 route-only adaptation requires the preregistered "
            "neutral_fifo coordination protocol"
        )
    if args.release_mode == "same_hca" and args.scale != 1:
        raise FullPopulationError(
            "same-HCA release mode is intentionally limited to eligible 1x cells"
        )


def _prepare(args: argparse.Namespace) -> tuple[
    str,
    nanning_native.Workload | map2_native.Workload,
    dict[str, Any],
    dict[str, Any],
]:
    _validate_protocol_args(args)
    case_id = f"t5_2_{args.map}_{args.scale}x_speed_2p5"
    release = {
        "mode": args.release_mode,
        "same_hca_release_trace_pass": False,
        "formal_same_hca_release_input": False,
    }
    if args.map == "nanning":
        case = nanning_native.case_by_id(case_id)
        workload = _load_nanning_workload(
            args.scale, _resolve_from_root(args.nanning_task_dir)
        )
        if args.release_mode == "same_hca":
            workload, trace = _align_nanning_1x(
                case,
                workload,
                _resolve_from_root(args.nanning_hca_root),
            )
            release.update(
                same_hca_release_trace_pass=trace["pass"],
                formal_same_hca_release_input=trace["pass"],
                evidence=trace,
            )
        request, _runtime_rows, rejected, _local = (
            nanning_native.prepare_native_request(
                case,
                workload,
                map_profile_path=_resolve_from_root(args.nanning_map_profile),
                fault_protocol_path=_resolve_from_root(
                    nanning_native.DEFAULT_FAULT_PROTOCOL
                ),
                binary=args.binary,
            )
        )
    else:
        case = map2_native.case_by_id(case_id)
        workload = map2_native.load_workload(
            args.scale,
            _resolve_from_root(args.map2_workload_1x),
            _resolve_from_root(args.map2_workload_2x),
        )
        if args.release_mode == "same_hca":
            root = (
                _resolve_from_root(args.map2_hca_case_root)
                if args.map2_hca_case_root is not None
                else map2_paired.formal_hca_case_root(args.scale, SPEED_MPS)
            )
            workload, trace = _align_map2_1x(case, workload, root)
            release.update(
                same_hca_release_trace_pass=trace["pass"],
                formal_same_hca_release_input=trace["pass"],
                evidence=trace,
            )
        request, _runtime_rows, rejected, _local = map2_native.prepare_native_request(
            case, workload, binary=args.binary
        )
    if rejected:
        raise FullPopulationError("stable full-population case rejected source rows")
    base_request = request
    request = dict(base_request)
    delta: dict[str, Any] = {}
    removed_fields: list[str] = []
    if args.arm == "s5":
        request.update(S5_DELTA)
        delta = dict(S5_DELTA)
    elif args.arm == "ssp_time":
        request.update(SSP_TIME_DELTA)
        delta = dict(SSP_TIME_DELTA)
        for field in MODEL_BACKED_REQUEST_FIELDS:
            if field in request:
                request.pop(field)
                removed_fields.append(field)
    elif args.arm in {"feng_dh", "tarau_local_2009", "cie_dh_2009"}:
        request.update(FENG_DH_DELTA)
        delta = dict(FENG_DH_DELTA)
        for field in MODEL_BACKED_REQUEST_FIELDS:
            if field in request:
                request.pop(field)
                removed_fields.append(field)
    elif args.arm == "tarau_distributed_2010":
        request.update(TARAU_DISTRIBUTED_2010_DELTA)
        delta = dict(TARAU_DISTRIBUTED_2010_DELTA)
        for field in MODEL_BACKED_REQUEST_FIELDS:
            if field in request:
                request.pop(field)
                removed_fields.append(field)
    if args.coordination == "neutral_fifo":
        request.update(NEUTRAL_FIFO_DELTA)
        delta.update(NEUTRAL_FIFO_DELTA)
    if args.s4_ablation != "none":
        if args.arm != "g31":
            raise FullPopulationError("S4 ablations are valid only for --arm g31")
        selected = S4_ABLATION_DELTAS[args.s4_ablation]
        request.update(selected)
        delta.update(selected)
    changed = {
        key: request[key]
        for key in request
        if key not in base_request or request[key] != base_request[key]
    }
    removed = sorted(set(base_request) - set(request))
    if changed != delta or removed != sorted(removed_fields):
        raise FullPopulationError(
            "arm changed fields outside its registered delta: "
            f"changed={changed} removed={removed}"
        )
    return case_id, workload, request, {
        **release,
        "request_delta_from_g31": delta,
        "removed_request_fields_from_g31": removed_fields,
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    case_id, workload, request, release = _prepare(args)
    binary = Path(args.binary).resolve(strict=True)
    common = {
        "schema": SCHEMA,
        "case_id": case_id,
        "map": args.map,
        "scale": args.scale,
        "arm": args.arm,
        "arm_label": ARM_LABELS[args.arm],
        "population": {
            "raw_bag_count": workload.raw_bag_count,
            "segment_count": workload.segment_count,
            "whole_population": True,
        },
        "fixed_window": {
            "start_epoch": nanning_native.FIXED_START_EPOCH,
            "max_epochs": nanning_native.HCA_MAX_EPOCHS,
            "end_epoch": nanning_native.FIXED_END_EPOCH,
            "max_events": nanning_native.MAX_EVENTS,
            "speed_mps": SPEED_MPS,
        },
        "release_protocol": release,
        "binary": {
            "requested_path": str(binary),
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "same_binary_required_for_arm_comparison": True,
        },
        "algorithm": {
            "label": ARM_LABELS[args.arm],
            "scorer_mode": request["scorer_mode"],
            "enable_s4_local_potential_descent_guard": request[
                "enable_s4_local_potential_descent_guard"
            ],
            "enable_s4_direct_neighbor_merge_calendar_visibility": request[
                "enable_s4_direct_neighbor_merge_calendar_visibility"
            ],
            "request_delta_from_g31": release["request_delta_from_g31"],
            "removed_request_fields_from_g31": release[
                "removed_request_fields_from_g31"
            ],
            "baseline_family": (
                "TARAU_LOCAL_2009_CIE_DH"
                if args.arm in {"feng_dh", "tarau_local_2009", "cie_dh_2009"}
                else (
                    "TARAU_DISTRIBUTED_2010"
                    if args.arm == "tarau_distributed_2010"
                    else None
                )
            ),
            "aliases_not_independent_methods": (
                ["TARAU_LOCAL_2009", "CIE_DH_2009", "FENG_DH"]
                if args.arm in {"feng_dh", "tarau_local_2009", "cie_dh_2009"}
                else []
            ),
            "coordination_protocol": args.coordination,
            "s4_ablation": args.s4_ablation,
            **(
                {
                    "literature_reimplementation": {
                        "exact_reproduction": False,
                        "reason": "moving/stopped penalty coefficients are undisclosed",
                        "frozen_before_outcomes": True,
                        "posthoc_tuning": False,
                        "moving_weight": 1.0,
                        "stopped_weight": 2.0,
                        "score_formula": (
                            "travel(u,v)+H_service_aware(v,g)+"
                            "sum_path_r_not_goal(q_r*(M_r+2*S_r))"
                        ),
                        "q_r": "max(node_service_time,minimum_service_seconds)",
                        "path_tie_break": "lowest_next_node_id",
                        "live_state_included": [
                            "scheduled_incoming_on_free_flow_path",
                            "junction_queue_on_free_flow_path",
                        ],
                        "live_state_excluded": [
                            "source_queue",
                            "pending_release",
                            "completed",
                            "failed",
                        ],
                    }
                }
                if args.arm in {"feng_dh", "tarau_local_2009", "cie_dh_2009"}
                else {}
            ),
            **(
                {
                    "literature_adaptation": {
                        "exact_reproduction": False,
                        "formal_name": "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY",
                        "reason": (
                            "published calibrated weights, mechanical switch state, "
                            "historical branching rates, and route-time data are unavailable"
                        ),
                        "frozen_before_outcomes": True,
                        "posthoc_tuning": False,
                        "tau_pred_seconds": 5.0,
                        "dynamic_link_radius": 2,
                        "switch_cost": 0.0,
                        "high_degree_adaptation": "stable argmin over every legal outgoing edge",
                        "excluded_information": [
                            "global future tasks",
                            "global reservation tables",
                            "S4 strict-potential residuals",
                            "S4 service-calendar score",
                        ],
                    }
                }
                if args.arm == "tarau_distributed_2010"
                else {}
            ),
        },
    }
    if args.dry_run:
        return {
            **common,
            "status": "READY_FULL_POPULATION_DRY_RUN",
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
        raise FullPopulationError("native runtime did not return summary and bags")
    if any(not isinstance(row, Mapping) for row in bags):
        raise FullPopulationError("native runtime returned a non-object bag row")

    integrity = _execution_integrity(summary, bags, workload, request)
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
    if full_population:
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
                "paper_network_from_admission": _paper_five(
                    outcome["paper_raw_bag_tth"]["distribution"]
                ),
                "segment_release": _five(distributions["java_release"]),
                "original_entry": _five(distributions["original_entry"]),
            },
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
    runtime_fields = (
        "completed_count",
        "failed_count",
        "event_count",
        "decision_count",
        "event_limit_reached",
        "time_limit_reached",
        "reservation_conflicts",
        "loop_count",
        "runtime_full_astar_calls",
        "scorer_runtime_global_scan_count",
        "loaded_cpp_binary_path",
        "loaded_cpp_binary_sha256",
    )
    return {
        **common,
        "status": "COMPLETE" if integrity["pass"] else "FAILED_INTEGRITY",
        "native_execution_started": True,
        "paper_subjects": {
            "fixed_horizon_capacity": capacity,
            "full_population_raw_bag_timing": timing,
        },
        "execution_integrity": integrity,
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            **{name: summary.get(name) for name in runtime_fields},
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", choices=("nanning", "map2"), required=True)
    parser.add_argument("--scale", type=int, choices=(1, 2), required=True)
    parser.add_argument(
        "--arm",
        choices=(
            "g31",
            "s5",
            "ssp_time",
            "feng_dh",
            "tarau_local_2009",
            "cie_dh_2009",
            "tarau_distributed_2010",
        ),
        required=True,
    )
    parser.add_argument(
        "--coordination",
        choices=("g31", "neutral_fifo"),
        default="g31",
        help="Shared merge executor; neutral_fifo is the P1 route-isolation control.",
    )
    parser.add_argument(
        "--s4-ablation",
        choices=tuple(S4_ABLATION_DELTAS),
        default="none",
    )
    parser.add_argument(
        "--release-mode", choices=("canonical", "same_hca"), default="canonical"
    )
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--nanning-task-dir",
        type=Path,
        default=nanning_native.DEFAULT_TASK_DIR,
    )
    parser.add_argument(
        "--nanning-map-profile",
        type=Path,
        default=nanning_native.DEFAULT_MAP_PROFILE,
    )
    parser.add_argument(
        "--nanning-hca-root",
        type=Path,
        default=nanning_paired.DEFAULT_HCA_ROOT,
    )
    parser.add_argument(
        "--map2-workload-1x",
        type=Path,
        default=map2_native.DEFAULT_WORKLOAD_1X,
    )
    parser.add_argument(
        "--map2-workload-2x",
        type=Path,
        default=map2_native.DEFAULT_WORKLOAD_2X,
    )
    parser.add_argument("--map2-hca-case-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _validate_protocol_args(args)
    args.binary = _resolve_from_root(args.binary).resolve(strict=True)
    output = _resolve_from_root(args.output)
    if output.exists() and not args.force:
        raise FullPopulationError(f"output exists; pass --force to replace: {output}")
    result = execute(args)
    _write_json(output, result)
    print(json.dumps({"status": result["status"], "case_id": result["case_id"]}))
    return 0 if result["status"] in {"COMPLETE", "READY_FULL_POPULATION_DRY_RUN"} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FullPopulationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G35 full-population run failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
