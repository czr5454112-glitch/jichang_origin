#!/usr/bin/env python3
"""Run S4/FIFO with a service-aware static local potential.

G28 changes one existing static input, not the runtime architecture.  For a
non-goal node ``u`` it precomputes

``H(u, g) = service_duration(u) + min_(u,v)(travel(u,v) + H(v,g))``

with ``H(g,g)=0``.  Consequently the unchanged S4 candidate expression
``travel(current,candidate) + H(candidate,goal)`` accounts for the candidate
node's service and every later non-goal service.  Runtime decisions still read
one scalar per direct neighbour, remain O(outdegree), and do not materialise a
future route or call full A*.

The runner is deliberately limited to the four no-fault Table 5.2 speed cases.
It reuses G26's registered exact-release protocol and G27's local FIFO policy.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend
from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf24_native_race as g24
from scripts.eval import run_g4irsf26_paper_experiments as g26
from scripts.eval import run_g4irsf27_fault_values as g27


SCHEMA = "czr005.g4irsf28.service_aware_potential_case.v1"
ADMITTED_STATUS = "COMPLETE_G28_SERVICE_AWARE_POTENTIAL"
ALLOWED_SEGMENT_COUNTS = (512, g26.PAPER_DAY_SEGMENTS)
CASE_IDS = (
    "t5_2_speed_1p5",
    "t5_2_speed_2",
    "t5_2_speed_2p5",
    "t5_2_speed_3",
)
DEFAULT_MINIMUM_SERVICE_SECONDS = 1.0e-3


class ServicePotentialError(RuntimeError):
    """Raised when the static service-aware potential cannot be evaluated."""


def service_aware_potential(
    node_records: Sequence[Sequence[Any]],
    edge_records: Sequence[Sequence[Any]],
    *,
    minimum_service_seconds: float = DEFAULT_MINIMUM_SERVICE_SECONDS,
) -> tuple[list[list[float]], dict[str, Any]]:
    """Return the exact service-aware all-pairs potential and its contract.

    A reverse Dijkstra run per goal computes the scalar matrix.  The value in
    a non-goal row includes that row node's service duration, so the existing
    S4 lookup at a candidate has the intended candidate-inclusive meaning.
    """

    if not math.isfinite(minimum_service_seconds) or minimum_service_seconds <= 0.0:
        raise ServicePotentialError("minimum_service_seconds must be positive")
    nodes = sorted(int(row[0]) for row in node_records)
    if nodes != list(range(len(nodes))):
        raise ServicePotentialError("node IDs must be dense zero-based heuristic indices")

    service = {
        int(row[0]): max(float(row[2]), minimum_service_seconds)
        for row in node_records
    }
    incoming: dict[int, list[tuple[int, float]]] = {node: [] for node in nodes}
    edge_cost_sum = 0.0
    for edge in edge_records:
        source, target = int(edge[0]), int(edge[1])
        length, speed = float(edge[2]), float(edge[3])
        if length <= 0.0 or speed <= 0.0:
            raise ServicePotentialError("edge length and speed must be positive")
        travel = length / speed
        incoming[target].append((source, travel))
        edge_cost_sum += travel
    for values in incoming.values():
        values.sort()

    node_count = len(nodes)
    unreachable = edge_cost_sum + math.fsum(service.values()) + 1.0
    matrix = [[unreachable] * node_count for _ in nodes]
    for goal in nodes:
        distances = [math.inf] * node_count
        distances[goal] = 0.0
        heap: list[tuple[float, int]] = [(0.0, goal)]
        while heap:
            cost, node = heapq.heappop(heap)
            if cost > distances[node]:
                continue
            for predecessor, travel in incoming[node]:
                candidate = cost + travel + service[predecessor]
                if candidate < distances[predecessor]:
                    distances[predecessor] = candidate
                    heapq.heappush(heap, (candidate, predecessor))
        for source, value in enumerate(distances):
            matrix[source][goal] = value if math.isfinite(value) else unreachable

    return matrix, {
        "mode": "SERVICE_AWARE_STATIC_LOCAL_POTENTIAL",
        "formula": (
            "H(g,g)=0; H(u,g)=service_duration(u)+"
            "min_(u,v)(travel(u,v)+H(v,g))"
        ),
        "service_duration": "max(map_node_service,minimum_service_seconds)",
        "minimum_service_seconds": minimum_service_seconds,
        "candidate_score_identity": (
            "travel(current,candidate)+H(candidate,goal) includes candidate and "
            "later non-goal service"
        ),
        "precomputation": "reverse_dijkstra_once_per_goal",
        "node_count": node_count,
        "directed_edge_count": len(edge_records),
        "unreachable_finite_value_seconds": unreachable,
        "runtime_read_scope": "direct_outgoing_candidates_and_one_scalar_each",
        "runtime_decision_complexity": "O(outdegree)",
        "runtime_full_astar_required": False,
        "future_route_materialized": False,
        "global_reservation_table_required": False,
    }


def apply_service_aware_potential(
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copy a native request and replace only its static heuristic matrix."""

    prepared = dict(request)
    minimum_service = float(
        prepared.get("minimum_service_seconds", DEFAULT_MINIMUM_SERVICE_SECONDS)
    )
    potential, contract = service_aware_potential(
        prepared["node_records"],
        prepared["edge_records"],
        minimum_service_seconds=minimum_service,
    )
    prepared["heuristic_time"] = potential
    return prepared, contract


def prepare_request(
    case: Mapping[str, Any],
    prefix: harness.InputPrefix,
    *,
    binary: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build the unchanged G27 FIFO request and replace only its potential."""

    if case.get("seed_edges"):
        raise ServicePotentialError("G28 service-potential runner accepts no-fault cases only")
    request, runtime_rows, rejected_rows, local = g27.prepare_request(
        case, prefix, binary=binary
    )
    if len(runtime_rows) != len(prefix.rows) or rejected_rows:
        raise ServicePotentialError("a no-fault G28 case must admit the complete prefix")
    if "g4irsf24_dlp_artifact" in request:
        raise ServicePotentialError("G28 does not activate the G24 learning seam")

    prepared, contract = apply_service_aware_potential(request)
    return prepared, contract, local


def execute_case(
    case_id: str,
    *,
    segments: int,
    binary: Path,
) -> dict[str, Any]:
    """Run one registered no-fault speed case under the G28 potential."""

    if case_id not in CASE_IDS:
        raise ServicePotentialError(f"unsupported G28 case: {case_id}")
    if segments not in ALLOWED_SEGMENT_COUNTS:
        raise ServicePotentialError(f"segments must be one of {ALLOWED_SEGMENT_COUNTS}")

    case = g26.case_by_id(case_id)
    canonical = harness.load_input_prefix(segments, root=ROOT)
    full_workload_gates = (
        g26._full_workload_gate(canonical)
        if segments == g26.PAPER_DAY_SEGMENTS
        else None
    )
    registered_release = g26.default_release_csv_for_case(case_id).resolve(strict=True)
    prefix, alignment = g24.apply_exact_hca_releases(canonical, registered_release)
    request, potential, local = prepare_request(
        case,
        prefix,
        binary=binary.resolve(strict=True),
    )

    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    if not isinstance(payload, Mapping):
        raise ServicePotentialError("native S4 result is not an object")
    summary, bags = payload.get("summary"), payload.get("bags")
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise ServicePotentialError("native S4 result lacks summary or bag rows")

    outcome = g26.summarize_paper_outcome(
        prefix.rows,
        bags,
        total_raw_bags=prefix.raw_bag_count,
    )
    custom_safety = g27.g27_source_admission_safety(
        summary,
        selected_segment_count=segments,
        runtime_requested_segment_count=segments,
        source_rejected_segment_count=0,
        seed_fault_count=0,
        expected_runtime_segment_ids=[str(row["segment_id"]) for row in prefix.rows],
        runtime_bags=bags,
    )
    echo_gates = g26._runtime_echo_gates(summary)
    dlp = g27._dlp_evidence(summary, None)
    outcome_gates = {
        "all_selected_segments_completed": int(summary.get("completed_count", -1))
        == segments,
        "all_selected_raw_bags_completed": int(outcome["completed_raw_bag_count"])
        == prefix.raw_bag_count,
        "registered_release_covers_prefix": int(alignment["aligned_segment_count"])
        == segments,
    }
    admitted = (
        bool(custom_safety["pass"])
        and all(echo_gates.values())
        and bool(dlp["pass"])
        and all(outcome_gates.values())
    )

    return {
        "schema": SCHEMA,
        "status": ADMITTED_STATUS if admitted else "FAILED_G28_ADMISSION_GATE",
        "case": dict(case),
        "protocol": {
            "framework": "decentralized_S4_J2_E2_plus_local_FIFO",
            "active_policy": local["active_policy"],
            "selected_segment_count": segments,
            "selected_raw_bag_count": prefix.raw_bag_count,
            "full_43603_input_audit": full_workload_gates,
            "registered_release_csv": alignment["source"],
            "exact_hca_release_alignment": alignment,
            "change_scope": "static_heuristic_matrix_only",
            "learning_active": False,
            "runtime_full_astar_used": False,
            "future_route_materialized": False,
            "hca_global_reservation_table_used": False,
        },
        "potential": potential,
        "outcome": {
            "requested_segment_count": segments,
            "runtime_completed_segment_count": int(summary.get("completed_count", 0)),
            "runtime_failed_segment_count": int(summary.get("failed_count", 0)),
            **outcome,
        },
        "safety": {
            "pass": admitted,
            "local_source_admission": custom_safety,
            "runtime_echo_gates": echo_gates,
            "dlp_exact_off": dlp,
            "outcome_gates": outcome_gates,
        },
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "event_count": int(summary.get("event_count", 0)),
            "decision_count": int(summary.get("decision_count", 0)),
        },
    }


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    case = commands.add_parser("case", help="run one Table 5.2 case with G28")
    case.add_argument("--case-id", required=True, choices=CASE_IDS)
    case.add_argument(
        "--segments", type=int, required=True, choices=ALLOWED_SEGMENT_COUNTS
    )
    case.add_argument("--binary", type=Path, required=True)
    case.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    value = execute_case(args.case_id, segments=args.segments, binary=args.binary)
    output = _rooted(args.output)
    g26._atomic_json(output, value)
    print(
        json.dumps(
            {
                "case_id": args.case_id,
                "segments": args.segments,
                "status": value["status"],
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if value["status"] == ADMITTED_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
