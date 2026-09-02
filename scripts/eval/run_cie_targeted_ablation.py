#!/usr/bin/env python3
"""Run preregistered high-load CIE component ablations.

This runner deliberately has no activation-classification or arm-selection
logic.  It may be invoked only after the separate activation scan has supplied
an evidence artifact.  Every registered arm uses the complete 2x canonical
population and the unchanged G31 native request (H_SA, J2/M3, E2, strict local
descent and direct-neighbour calendar visibility); the sole algorithmic request
field allowed to vary is ``s4_score_component_mask``.
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


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import cie_fixed_denominator_business as cie_business  # noqa: E402
from scripts.eval import run_cie_component_activation as activation  # noqa: E402
from scripts.eval import run_g4irsf26_paper_experiments as g26  # noqa: E402


SCHEMA = "czr005.cie_targeted_ablation.run.v1"
MAPS = ("map2", "nanning")
REGISTERED_SCALE = 2
REGISTERED_2X_RAW_BAG_COUNT = 57_012
REGISTERED_2X_SEGMENT_COUNT = 87_206

# Bit contract: Q=1, I=2, wc=4 and ws=8.  The catalog is fixed in code so the
# runner cannot add a post-hoc arm in response to an observed outcome.
ARMS: dict[str, int] = {
    "FULL_S4": 15,
    "H_ONLY_SERVICE_AWARE": 0,
    "FULL_MINUS_Q": 14,
    "FULL_MINUS_I": 13,
    "FULL_MINUS_WS": 7,
    "H_PLUS_Q_PLUS_I": 3,
    "FULL_MINUS_WC": 11,
}
COMPONENT_BITS = {"Q": 1, "I": 2, "wc": 4, "ws": 8}


class TargetedAblationError(RuntimeError):
    """Raised when a targeted ablation violates its frozen protocol."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(
            value, ensure_ascii=False, indent=2, sort_keys=True,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _validate_scale(scale: int) -> None:
    if isinstance(scale, bool) or int(scale) != REGISTERED_SCALE:
        raise TargetedAblationError(
            "targeted component ablations are registered only for the 2x load"
        )


def validate_registered_2x_population(
    *, raw_bag_count: int, segment_count: int
) -> None:
    expected = (REGISTERED_2X_RAW_BAG_COUNT, REGISTERED_2X_SEGMENT_COUNT)
    actual = (int(raw_bag_count), int(segment_count))
    if actual != expected:
        raise TargetedAblationError(
            "canonical workload is not the registered complete 2x population: "
            f"expected raw/segments={expected}, got {actual}"
        )


def _changed_top_level_fields(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    keys = set(before) | set(after)
    return sorted(
        key
        for key in keys
        if _canonical_json(before.get(key)) != _canonical_json(after.get(key))
    )


def _request_identity_gates(
    request: Mapping[str, Any],
    base_contract: Mapping[str, Any],
    *,
    selected_mask: int,
    changed_fields: Sequence[str],
) -> dict[str, bool]:
    potential = base_contract.get("potential_contract")
    potential_mode = (
        potential.get("mode") if isinstance(potential, Mapping) else None
    )
    permitted_delta = [] if selected_mask == 15 else ["s4_score_component_mask"]
    return {
        "s4_native_scorer": request.get("scorer_mode")
        == "S4_queue_aware_rule_only",
        "service_aware_static_potential_h_sa": (
            base_contract.get("static_potential") == "H_SA"
            and potential_mode == "SERVICE_AWARE_STATIC_LOCAL_POTENTIAL"
        ),
        "selected_mask_exact": request.get("s4_score_component_mask")
        == selected_mask,
        "only_mask_changed_from_full_s4": list(changed_fields)
        == permitted_delta,
        "j2_m3": request.get("merge_grant_rule") == "M3",
        "j2_jit_fair_aging_deadline": request.get("merge_grant_timing_mode")
        == "jit_fair_aging_deadline",
        "e2": request.get("g4irsf20_event_hotpath_policy") == "E2",
        "strict_local_descent": request.get(
            "enable_s4_local_potential_descent_guard"
        ) is True,
        "direct_neighbor_calendar_visibility": request.get(
            "enable_s4_direct_neighbor_merge_calendar_visibility"
        ) is True,
        "goal_arrival_completion": request.get("complete_on_goal_arrival")
        is True,
        "activation_telemetry_enabled": request.get(
            "enable_cie_component_activation"
        ) is True,
        "fixed_horizon": request.get("max_simulation_time")
        == activation.FIXED_END_EPOCH,
        "event_budget": request.get("max_events") == activation.MAX_EVENTS,
    }


def prepare_targeted_request(
    *,
    map_name: str,
    scale: int,
    arm: str,
    canonical_path: Path,
    binary: Path,
    nanning_profile_path: Path = activation.DEFAULT_NANNING_PROFILE,
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any], dict[str, Any]]:
    """Prepare a frozen G31 request and alter only its S4 component mask."""

    _validate_scale(scale)
    if map_name not in MAPS:
        raise TargetedAblationError(f"unsupported map: {map_name}")
    if arm not in ARMS:
        raise TargetedAblationError(f"unregistered ablation arm: {arm}")

    rows, full_request, base_contract = activation.prepare_runtime_request(
        map_name=map_name,
        canonical_path=canonical_path,
        binary=binary,
        nanning_profile_path=nanning_profile_path,
        # Deliberately identical across arms on a map: scenario cannot become a
        # hidden second factor when request payloads are compared.
        scenario=f"cie_targeted_ablation_{map_name}_2x",
    )
    raw_bag_count = len({int(row["task_id"]) for row in rows})
    validate_registered_2x_population(
        raw_bag_count=raw_bag_count, segment_count=len(rows)
    )
    # The Python binding's omitted/default value is exactly mask 15.  Normalize
    # it to an explicit field before comparing arms so every executed request
    # has an auditable mask echo and FULL_S4 remains the zero-delta reference.
    if int(full_request.get("s4_score_component_mask", 15)) != ARMS["FULL_S4"]:
        raise TargetedAblationError(
            "activation request was not the unchanged full-S4 G31 base"
        )

    base_request = dict(full_request)
    base_request["s4_score_component_mask"] = ARMS["FULL_S4"]
    request = dict(base_request)
    selected_mask = ARMS[arm]
    request["s4_score_component_mask"] = selected_mask
    changed_fields = _changed_top_level_fields(base_request, request)
    identity_gates = _request_identity_gates(
        request,
        base_contract,
        selected_mask=selected_mask,
        changed_fields=changed_fields,
    )
    if not all(identity_gates.values()):
        raise TargetedAblationError(
            f"targeted ablation identity failed: {identity_gates}"
        )

    contract = {
        "map": map_name,
        "scale": REGISTERED_SCALE,
        "raw_bag_count": raw_bag_count,
        "segment_count": len(rows),
        "registered_complete_2x_population": True,
        "base_algorithm": "G31_S4_NATIVE",
        "static_potential": "H_SA",
        "coordination": "J2_M3_JIT_FAIR_AGING_DEADLINE",
        "event_hotpath": "E2",
        "strict_local_descent": True,
        "direct_neighbor_calendar_visibility": True,
        "arm": arm,
        "s4_score_component_mask": selected_mask,
        "component_enabled": {
            name: bool(selected_mask & bit)
            for name, bit in COMPONENT_BITS.items()
        },
        "changed_request_fields_from_full_s4": changed_fields,
        "sole_permitted_algorithmic_delta": "s4_score_component_mask",
        "base_full_s4_request_sha256": _json_sha256(base_request),
        "selected_request_sha256": _json_sha256(request),
        "identity_gates": identity_gates,
        "identity_pass": all(identity_gates.values()),
    }
    return rows, request, contract


def _fixed_denominator_business(
    rows: Sequence[Mapping[str, Any]],
    bags: Sequence[Mapping[str, Any]],
    raw_bag_count: int,
) -> dict[str, Any]:
    outcome = g26.summarize_paper_outcome(
        rows, bags, total_raw_bags=raw_bag_count
    )
    on_time = outcome["success"]["finish_le_std"]
    return {
        "capacity": outcome["success"]["primary_completed_raw_bags"],
        "on_time": on_time,
        "missed_bag_count": raw_bag_count - int(on_time["count"]),
        "missed_bag_rate": 1.0 - float(on_time["rate"]),
        "literal_early_margin": outcome["success"][
            "finish_le_std_minus_2700_literal"
        ],
        "detailed": cie_business.summarize(
            rows, bags, fixed_horizon=activation.FIXED_END_EPOCH
        ),
    }


def execute_run(
    *,
    map_name: str,
    scale: int,
    arm: str,
    canonical_path: Path,
    binary: Path,
    activation_evidence_path: Path,
    revision_manifest_path: Path = activation.DEFAULT_REVISION_MANIFEST,
    nanning_profile_path: Path = activation.DEFAULT_NANNING_PROFILE,
    dry_run: bool = False,
    executor: Any | None = None,
) -> dict[str, Any]:
    """Execute one arm; activation evidence is referenced, never interpreted."""

    canonical_path = canonical_path.resolve(strict=True)
    binary = binary.resolve(strict=True)
    activation_evidence_path = activation_evidence_path.resolve(strict=True)
    revision_manifest_path = revision_manifest_path.resolve(strict=True)
    rows, request, contract = prepare_targeted_request(
        map_name=map_name,
        scale=scale,
        arm=arm,
        canonical_path=canonical_path,
        binary=binary,
        nanning_profile_path=nanning_profile_path,
    )
    raw_bag_count = int(contract["raw_bag_count"])
    common = {
        "schema": SCHEMA,
        "status": "READY_CIE_TARGETED_ABLATION_DRY_RUN" if dry_run else None,
        "map": map_name,
        "scale": REGISTERED_SCALE,
        "population": {
            "raw_bag_denominator": raw_bag_count,
            "segment_count": len(rows),
            "whole_population": True,
            "registered_complete_2x_population": True,
        },
        "algorithm": {
            "baseline_family": "G31_S4_NATIVE",
            "reproduction_or_adaptation_label": "NATIVE_CURRENT_SYSTEM",
            "arm": arm,
            "s4_score_component_mask": ARMS[arm],
            "component_enabled": contract["component_enabled"],
            "static_potential": "H_SA",
            "coordination_protocol": "J2_M3_JIT_FAIR_AGING_DEADLINE",
            "event_hotpath_policy": "E2",
            "strict_local_descent": True,
            "direct_neighbor_calendar_visibility": True,
            "posthoc_tuning": False,
        },
        "ablation_contract": contract,
        "selection_protocol": {
            "activation_gate": "REQUIRED_BEFORE_INVOCATION",
            "activation_evidence_path": str(activation_evidence_path),
            "activation_evidence_sha256": _file_sha256(
                activation_evidence_path
            ),
            "activation_evidence_interpreted_by_runner": False,
            "arm_selected_from_outcomes_by_runner": False,
            "preregistered_arm_catalog": ARMS,
        },
        "provenance": {
            "git_commit": _git_value("rev-parse", "HEAD"),
            "git_branch": _git_value("branch", "--show-current"),
            "binary_path": str(binary),
            "binary_sha256": _file_sha256(binary),
            "canonical_workload_path": str(canonical_path),
            "canonical_workload_sha256": _file_sha256(canonical_path),
            "revision_manifest_path": str(revision_manifest_path),
            "revision_manifest_sha256": _file_sha256(revision_manifest_path),
            "executor_identity": "COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE",
            "release_protocol": "canonical_complete_flight_population",
            "random_seed": None,
            "survivor_timing_used": False,
        },
        "native_execution_started": not dry_run,
    }
    if dry_run:
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
        raise TargetedAblationError(
            "native executor did not return summary and bags"
        )
    if any(not isinstance(row, Mapping) for row in bags):
        raise TargetedAblationError("native executor returned a non-object bag row")

    integrity = activation._execution_integrity(summary, bags, rows, request)
    gates = dict(integrity["gates"])
    gates.update(
        {
            "registered_2x_population": (
                raw_bag_count == REGISTERED_2X_RAW_BAG_COUNT
                and len(rows) == REGISTERED_2X_SEGMENT_COUNT
            ),
            "targeted_request_identity": contract["identity_pass"] is True,
            "s4_score_component_mask_echo": summary.get(
                "s4_score_component_mask"
            ) == ARMS[arm],
            "activation_telemetry_present": isinstance(
                summary.get("cie_component_activation"), Mapping
            ),
        }
    )
    integrity = {
        **integrity,
        "gates": gates,
        "pass": all(gates.values()),
    }
    return {
        **common,
        "status": "COMPLETE" if integrity["pass"] else "FAILED_INTEGRITY",
        "fixed_denominator_business": _fixed_denominator_business(
            rows, bags, raw_bag_count
        ),
        # The frozen paper protocol forbids survivor/common-cohort THT at 2x,
        # even when an arm happens to complete every bag.
        "full_population_timing": {
            "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
            "raw_bag_count": None,
            "survivor_or_common_cohort_used": False,
            "distributions": None,
        },
        "execution_integrity": integrity,
        "activation_telemetry": dict(summary["cie_component_activation"]),
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "peak_rss_bytes": "NOT_MEASURED",
            "event_count": int(summary.get("event_count", 0)),
            "decision_count": int(summary.get("decision_count", 0)),
            "mechanism_activation_j2_p2_e2": activation._mechanism_projection(
                summary
            ),
            "native_summary": dict(summary),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", choices=MAPS, required=True)
    parser.add_argument("--scale", type=int, choices=(REGISTERED_SCALE,), required=True)
    parser.add_argument("--arm", choices=tuple(ARMS), required=True)
    parser.add_argument(
        "--canonical",
        type=Path,
        required=True,
        help="Explicit complete 2x canonical JSONL; no workload discovery occurs.",
    )
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument(
        "--activation-evidence",
        type=Path,
        required=True,
        help="Existing activation-scan artifact authorizing this targeted run.",
    )
    parser.add_argument(
        "--revision-manifest",
        type=Path,
        default=activation.DEFAULT_REVISION_MANIFEST,
    )
    parser.add_argument(
        "--nanning-map-profile",
        type=Path,
        default=activation.DEFAULT_NANNING_PROFILE,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = _rooted(args.output)
    if output.exists() and not args.force:
        raise TargetedAblationError(
            f"output exists; pass --force to replace: {output}"
        )
    result = execute_run(
        map_name=args.map,
        scale=args.scale,
        arm=args.arm,
        canonical_path=_rooted(args.canonical),
        binary=_rooted(args.binary),
        activation_evidence_path=_rooted(args.activation_evidence),
        revision_manifest_path=_rooted(args.revision_manifest),
        nanning_profile_path=_rooted(args.nanning_map_profile),
        dry_run=args.dry_run,
    )
    _write_json(output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "map": result["map"],
                "scale": result["scale"],
                "arm": result["algorithm"]["arm"],
                "output": str(output),
            }
        )
    )
    return 0 if result["status"] in {
        "COMPLETE",
        "READY_CIE_TARGETED_ABLATION_DRY_RUN",
    } else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        TargetedAblationError,
        activation.ActivationError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"CIE targeted ablation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
