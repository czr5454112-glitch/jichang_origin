#!/usr/bin/env python3
"""Run the G31 final policy on map2 in the non-exact Table-5.4 grid.

The 24 cells reuse the Nanning reconstruction protocol exactly: 1x/2x by
four nominal speeds and deterministic local ``U(0, k seconds)`` observation
delay for ``k`` equal to 1, 2, or 3, with seed 20260816.  Only the map and
fixed population come from the map2 final-policy runner.

This is secondary ``LEGACY_VARIANT_RECONSTRUCTION_NON_EXACT`` context.  The
unperturbed HCA stable cell is a conservative reference, not a matched bias
arm; no result from this runner drives the fresh exact or cross-map target.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import run_g4irsf26_paper_experiments as g26  # noqa: E402
from scripts.eval import run_g4irsf31_map2_native as map2_native  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_bias as nanning_bias  # noqa: E402


SCHEMA = "czr005.g4irsf31.map2_bias_case.v1"
AGGREGATE_SCHEMA = "czr005.g4irsf31.map2_bias_aggregate.v1"
PROTOCOL_FIDELITY = nanning_bias.PROTOCOL_FIDELITY
EVIDENCE_ROLE = nanning_bias.EVIDENCE_ROLE
MAP_ID = map2_native.MAP_ID
SPEEDS_MPS = nanning_bias.SPEEDS_MPS
DEVIATIONS_PERCENT = nanning_bias.DEVIATIONS_PERCENT
FIXED_SEED = nanning_bias.FIXED_SEED
FIXED_END_EPOCH = map2_native.FIXED_END_EPOCH
MAX_EVENTS = map2_native.MAX_EVENTS

COMPLETE = "COMPLETE_G31_MAP2_BIAS_RECONSTRUCTION"
DRY_RUN_READY = "READY_G31_MAP2_BIAS_DRY_RUN"
FAILED = "FAILED_G31_MAP2_BIAS_ADMISSION"

DEFAULT_WORKLOAD_1X = map2_native.DEFAULT_WORKLOAD_1X
DEFAULT_WORKLOAD_2X = map2_native.DEFAULT_WORKLOAD_2X
DEFAULT_CASE_ROOT = ROOT / "outputs/runtime/g4irsf31_map2_bias"
DEFAULT_AGGREGATE = ROOT / "outputs/tables/g4irsf31_map2_bias.json"

Executor = Callable[..., Mapping[str, Any]]


class Map2BiasError(RuntimeError):
    """Raised when a map2 bias reconstruction cell is not admissible."""


@dataclass(frozen=True)
class BiasCase:
    case_id: str
    scale: int
    standard_speed_mps: float
    deviation_percent: int

    @property
    def maximum_seconds(self) -> float:
        return self.deviation_percent / 10.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "paper_table": "5.4",
            "group": "observation_bias_reconstruction",
            "scale": self.scale,
            "standard_speed_mps": self.standard_speed_mps,
            "physical_edge_speed_mps": self.standard_speed_mps,
            "deviation_percent": self.deviation_percent,
            "protocol_fidelity": PROTOCOL_FIDELITY,
        }


def _speed_label(value: float) -> str:
    return f"{value:g}".replace(".", "p")


CASES = tuple(
    BiasCase(
        case_id=f"t5_4_map2_{scale}x_std_{_speed_label(speed)}_dev_{deviation}",
        scale=scale,
        standard_speed_mps=speed,
        deviation_percent=deviation,
    )
    for scale in (1, 2)
    for speed in SPEEDS_MPS
    for deviation in DEVIATIONS_PERCENT
)
CASE_IDS = tuple(case.case_id for case in CASES)
_CASE_BY_ID = {case.case_id: case for case in CASES}


def case_by_id(case_id: str) -> BiasCase:
    try:
        return _CASE_BY_ID[case_id]
    except KeyError as exc:
        raise Map2BiasError(f"unsupported map2 bias case: {case_id}") from exc


def bias_contract(case: BiasCase) -> dict[str, Any]:
    # Keep the exact same U(0, k), seed and non-learning declaration used on
    # Nanning; map-specific code must not reinterpret the 10/20/30 labels.
    return nanning_bias.bias_contract(case)


def hca_reference_contract(case: BiasCase) -> dict[str, Any]:
    return {
        "case_id": f"t5_2_speed_{_speed_label(case.standard_speed_mps)}",
        "evidence_source": (
            "g4irsf26_fresh_hca_1x"
            if case.scale == 1
            else "g4irsf29_fixed_population_hca_2x"
        ),
        "condition": "SAME_SPEED_UNBIASED_STABLE_HCA",
        "role": "CONSERVATIVE_UNPERTURBED_REFERENCE_ONLY",
        "same_population_scale": True,
        "same_nominal_speed": True,
        "observation_disturbance_present": False,
        "matched_disturbance_comparison": False,
        "exact_table_5_4_reproduction": False,
        "fresh_exact_primary_target_driver": False,
        "claim_boundary": (
            "unbiased HCA is an easier conservative reference, not a matched "
            "observation-delay arm"
        ),
    }


def campaign_manifest() -> dict[str, Any]:
    return {
        "protocol_fidelity": PROTOCOL_FIDELITY,
        "evidence_role": EVIDENCE_ROLE,
        "case_count": len(CASES),
        "map_id": MAP_ID,
        "scales": [1, 2],
        "standard_speeds_mps": list(SPEEDS_MPS),
        "deviation_levels_percent": list(DEVIATIONS_PERCENT),
        "fixed_seed": FIXED_SEED,
        "per_cell_tuning": False,
        "fresh_exact_primary_target_eligible": False,
        "cross_map_target_eligible": False,
        "cases": [
            {
                **case.as_dict(),
                "observation_bias": bias_contract(case),
                "hca_reference": hca_reference_contract(case),
            }
            for case in CASES
        ],
    }


def _base_case(case: BiasCase) -> map2_native.CaseSpec:
    return map2_native.case_by_id(
        f"t5_2_map2_{case.scale}x_speed_"
        f"{_speed_label(case.standard_speed_mps)}"
    )


def prepare_bias_request(
    case: BiasCase,
    workload: map2_native.Workload,
    *,
    binary: Path | None,
) -> tuple[
    dict[str, Any],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    dict[str, Any],
]:
    request, runtime_rows, rejected, local = map2_native.prepare_native_request(
        _base_case(case), workload, binary=binary
    )
    request = map2_native.g31_native.apply_observation_bias_context(
        request, {"observation_bias": bias_contract(case)}
    )
    request["scenario"] = f"g4irsf31_map2_bias_{case.case_id}"
    local = dict(local)
    local["observation_bias"] = bias_contract(case)
    return request, runtime_rows, rejected, local


def _comparison_contract(
    case: BiasCase, workload: map2_native.Workload
) -> dict[str, Any]:
    return {
        "capacity": {
            "protocol": "OWN_CANONICAL_SCHEDULE_FIXED_DENOMINATOR_AND_WINDOW",
            "raw_bag_denominator": workload.raw_bag_count,
            "fixed_start_epoch": map2_native.FIXED_START_EPOCH,
            "fixed_end_epoch": FIXED_END_EPOCH,
            "max_events": MAX_EVENTS,
        },
        "hca_reference": hca_reference_contract(case),
        "table_5_4_claim": {
            "protocol_fidelity": PROTOCOL_FIDELITY,
            "matched_disturbance": False,
            "exact_reproduction": False,
            "fresh_exact_primary_target_eligible": False,
            "cross_map_target_eligible": False,
        },
        "timing": {
            "survivor_only_comparison_allowed": False,
            "requires_full_population_for_descriptive_S4_timing": True,
            "cross_framework_verdict_generated_here": False,
        },
    }


def execute_case(
    case_id: str,
    *,
    workload_1x: Path = DEFAULT_WORKLOAD_1X,
    workload_2x: Path = DEFAULT_WORKLOAD_2X,
    binary: Path | None,
    dry_run: bool = False,
    executor: Executor | None = None,
) -> dict[str, Any]:
    case = case_by_id(case_id)
    base = _base_case(case)
    workload = map2_native.load_workload(case.scale, workload_1x, workload_2x)
    request, runtime_rows, rejected, local = prepare_bias_request(
        case, workload, binary=binary
    )
    common = {
        "schema": SCHEMA,
        "case_id": case.case_id,
        "case": case.as_dict(),
        "map_id": MAP_ID,
        "map_profile": map2_native._map_contract(map2_native.map2_profile()),
        "protocol_fidelity": PROTOCOL_FIDELITY,
        "evidence_role": EVIDENCE_ROLE,
        "fresh_exact_primary_target_eligible": False,
        "cross_map_target_eligible": False,
        "workload_protocol": workload.protocol,
        "selection": map2_native._selection(base, workload),
        "observation_bias": bias_contract(case),
        "comparison_contract": _comparison_contract(case, workload),
        "request_contract": map2_native.g31_native._request_contract(
            request, runtime_rows, rejected, local
        ),
    }
    if dry_run:
        return {
            **common,
            "status": DRY_RUN_READY,
            "native_execution_started": False,
        }
    if binary is None:
        raise Map2BiasError("binary is required unless --dry-run is used")

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = selected_executor(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise Map2BiasError("native executor did not return summary and bag rows")
    if any(not isinstance(row, Mapping) for row in bags):
        raise Map2BiasError("native bag result contains a non-object row")

    outcome = g26.summarize_paper_outcome(
        workload.rows, bags, total_raw_bags=workload.raw_bag_count
    )
    base_safety = map2_native.g31_native._runtime_admission(
        base,
        workload,
        request,
        runtime_rows,
        rejected,
        local,
        summary,
        bags,
        outcome,
    )
    bias_echo = nanning_bias._bias_echo(summary, bias_contract(case))
    safety = {
        "pass": base_safety["pass"] and bias_echo["pass"],
        "final_policy": base_safety,
        "observation_bias_echo": bias_echo,
    }
    return {
        **common,
        "status": COMPLETE if safety["pass"] else FAILED,
        "native_execution_started": True,
        "outcome": {
            "requested_segment_count": workload.segment_count,
            **outcome,
        },
        "timing": map2_native.g31_native._timing_evidence(
            workload, bags, outcome
        ),
        "safety": safety,
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "event_count": int(summary.get("event_count", 0)),
            "decision_count": int(summary.get("decision_count", 0)),
            "declared_max_events": summary.get("declared_max_events"),
            "declared_max_simulation_time": summary.get(
                "declared_max_simulation_time"
            ),
            "event_limit_reached": summary.get("event_limit_reached"),
            "time_limit_reached": summary.get("time_limit_reached"),
        },
    }


def _contract_current(value: Mapping[str, Any]) -> bool:
    case_id = value.get("case_id")
    if case_id not in _CASE_BY_ID:
        return False
    case = _CASE_BY_ID[str(case_id)]
    expected_raw, expected_segments = map2_native.SCALE_COUNTS[case.scale]
    selection = value.get("selection")
    request = value.get("request_contract")
    policy = request.get("policy") if isinstance(request, Mapping) else None
    comparison = value.get("comparison_contract")
    return (
        value.get("schema") == SCHEMA
        and value.get("map_id") == MAP_ID
        and value.get("case") == case.as_dict()
        and value.get("protocol_fidelity") == PROTOCOL_FIDELITY
        and value.get("evidence_role") == EVIDENCE_ROLE
        and value.get("fresh_exact_primary_target_eligible") is False
        and value.get("cross_map_target_eligible") is False
        and value.get("observation_bias") == bias_contract(case)
        and isinstance(selection, Mapping)
        and selection.get("mode") == "full"
        and selection.get("selected_raw_bag_count") == expected_raw
        and selection.get("selected_segment_count") == expected_segments
        and selection.get("hca_release_trace_applied") is False
        and isinstance(request, Mapping)
        and request.get("max_simulation_time") == FIXED_END_EPOCH
        and request.get("max_events") == MAX_EVENTS
        and request.get("local_queue_capacity")
        == map2_native.map_adapter.G31_LOCAL_QUEUE_CAPACITY
        and isinstance(policy, Mapping)
        and policy.get("local_potential_descent_guard")
        == map2_native.LOCAL_POTENTIAL_DESCENT_GUARD
        and policy.get("local_software_queue_cap")
        == map2_native.LOCAL_SOFTWARE_QUEUE_CAP
        and policy.get("direct_neighbor_merge_calendar_visibility")
        == map2_native.DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
        and policy.get("goal_arrival_completion")
        == map2_native.GOAL_ARRIVAL_COMPLETION
        and isinstance(comparison, Mapping)
        and comparison.get("hca_reference") == hca_reference_contract(case)
        and comparison.get("table_5_4_claim", {}).get(
            "fresh_exact_primary_target_eligible"
        )
        is False
        and comparison.get("table_5_4_claim", {}).get(
            "cross_map_target_eligible"
        )
        is False
    )


def _artifact_admitted(value: Mapping[str, Any]) -> bool:
    safety = value.get("safety")
    return (
        _contract_current(value)
        and value.get("status") == COMPLETE
        and isinstance(safety, Mapping)
        and safety.get("pass") is True
    )


def _dry_artifact_ready(value: Mapping[str, Any]) -> bool:
    return (
        _contract_current(value)
        and value.get("status") == DRY_RUN_READY
        and value.get("native_execution_started") is False
    )


def aggregate_results(case_root: Path) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    stale: list[str] = []
    for case_id in CASE_IDS:
        path = case_root / f"{case_id}.json"
        if not path.is_file():
            continue
        value = map2_native._read_json(path)
        if not _contract_current(value):
            stale.append(case_id)
            continue
        by_id[case_id] = map2_native._portable_artifact_paths(value)
    complete = sorted(
        case_id for case_id, value in by_id.items() if _artifact_admitted(value)
    )
    ready = sorted(
        case_id for case_id, value in by_id.items() if _dry_artifact_ready(value)
    )
    failed = sorted(
        case_id for case_id, value in by_id.items() if value.get("status") == FAILED
    )
    missing = sorted(set(CASE_IDS) - by_id.keys() - set(stale))
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": "COMPLETE" if len(complete) == len(CASE_IDS) else "PARTIAL",
        "map_id": MAP_ID,
        "protocol_fidelity": PROTOCOL_FIDELITY,
        "evidence_role": EVIDENCE_ROLE,
        "fresh_exact_primary_target_eligible": False,
        "cross_map_target_eligible": False,
        "expected_case_count": len(CASE_IDS),
        "observed_current_case_count": len(by_id),
        "complete_case_ids": complete,
        "dry_run_ready_case_ids": ready,
        "failed_case_ids": failed,
        "stale_case_ids": sorted(stale),
        "missing_case_ids": missing,
        "campaign_manifest": campaign_manifest(),
        "cases": [by_id[case_id] for case_id in sorted(by_id)],
    }


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _resolve_binary(path: Path | None) -> Path:
    try:
        return map2_native._resolve_binary(path)
    except map2_native.Map2NativeError as exc:
        raise Map2BiasError(str(exc)) from exc


def _add_workload_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workload-1x", type=Path, default=DEFAULT_WORKLOAD_1X)
    parser.add_argument("--workload-2x", type=Path, default=DEFAULT_WORKLOAD_2X)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    case = commands.add_parser("case", help="run or dry-run one map2 bias cell")
    case.add_argument("--case-id", required=True, choices=CASE_IDS)
    _add_workload_args(case)
    case.add_argument("--binary", type=Path)
    case.add_argument("--output", type=Path, required=True)
    case.add_argument("--dry-run", action="store_true")
    case.add_argument("--force", action="store_true")

    resume = commands.add_parser("resume", help="resume map2 bias cells")
    resume.add_argument("--case-id", action="append", choices=CASE_IDS)
    _add_workload_args(resume)
    resume.add_argument("--binary", type=Path)
    resume.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    resume.add_argument("--dry-run", action="store_true")
    resume.add_argument("--force", action="store_true")

    aggregate = commands.add_parser("aggregate", help="aggregate bias case JSON")
    aggregate.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    aggregate.add_argument("--output", type=Path, default=DEFAULT_AGGREGATE)
    return parser


def _run_one(args: argparse.Namespace, case_id: str, output: Path) -> int:
    if output.is_file() and not args.force:
        existing = map2_native._read_json(output)
        if _artifact_admitted(existing) or (
            args.dry_run and _dry_artifact_ready(existing)
        ):
            print(json.dumps({"status": "SKIPPED_EXISTING", "case_id": case_id}))
            return 0
        raise Map2BiasError(
            f"existing artifact is stale or incompatible for {case_id}; "
            "use --force to replace it"
        )
    binary = None if args.dry_run else _resolve_binary(args.binary)
    payload = execute_case(
        case_id,
        workload_1x=_rooted(args.workload_1x),
        workload_2x=_rooted(args.workload_2x),
        binary=binary,
        dry_run=args.dry_run,
    )
    map2_native._write_json(output, payload)
    print(json.dumps({"status": payload["status"], "case_id": case_id}))
    return 0 if payload["status"] in {COMPLETE, DRY_RUN_READY} else 2


def _resume(args: argparse.Namespace) -> int:
    case_root = _rooted(args.case_root)
    selected = tuple(dict.fromkeys(args.case_id or CASE_IDS))
    exit_code = 0
    for case_id in selected:
        exit_code = _run_one(args, case_id, case_root / f"{case_id}.json")
        if exit_code:
            break
    aggregate = aggregate_results(case_root)
    map2_native._write_json(case_root / "aggregate.json", aggregate)
    print(
        json.dumps(
            {
                "status": "RESUME_COMPLETE" if exit_code == 0 else "RESUME_STOPPED",
                "aggregate_status": aggregate["status"],
                "dry_run_ready": len(aggregate["dry_run_ready_case_ids"]),
            }
        )
    )
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "aggregate":
        payload = aggregate_results(_rooted(args.case_root))
        output = _rooted(args.output)
        map2_native._write_json(output, payload)
        print(json.dumps({"status": payload["status"], "output": str(output)}))
        return 0 if payload["status"] == "COMPLETE" else 2
    if args.command == "resume":
        return _resume(args)
    return _run_one(args, args.case_id, _rooted(args.output))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        Map2BiasError,
        map2_native.Map2NativeError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"G31 map2 bias failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
