#!/usr/bin/env python3
"""Audit a static-free-flow control across the Feng and common executors.

The control changes no default algorithm.  Feng uses the exact ``alpha=beta=0``
diagnostic seam; the common executor uses the existing P0D0 cell (H_FF and the
four dynamic score terms off).  OD probes are separated by 1000 seconds so
that each is an independently empty-network, single-bag measurement.  The
full-population runs retain each executor's own coordination mechanics and are
therefore reported as an executor bridge, never as a causal subtraction.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from czr005.io.legacy_map import LegacyMap, parse_legacy_map  # noqa: E402
from scripts.eval import run_cie_potential_factorial as factorial  # noqa: E402
from scripts.eval import run_feng_paper_env_cie_dh as feng_runner  # noqa: E402
from scripts.eval import run_g4irsf28_service_potential as potential  # noqa: E402


SCHEMA = "czr005.feng_common_executor_bridge.v1"
MAP_PATH = ROOT / "legacy" / "jichang_origin_readonly" / "map2.txt"
INPUT_PATH = ROOT / "legacy" / "jichang_origin_readonly" / "inputdata.txt"
CLASSES_DIR = ROOT / "build" / "feng_cie_dh_java_bridge"
RUNTIME_ROOT = ROOT / "outputs" / "runtime" / "feng_common_executor_bridge"
FENG_OD_RAW = RUNTIME_ROOT / "feng_static_od.csv"
COMMON_OD_RAW = RUNTIME_ROOT / "common_static_od.csv"
COMMON_OD_META = RUNTIME_ROOT / "common_static_od_metadata.json"
FENG_FULL_DIR = RUNTIME_ROOT / "feng_static_map2_1x"
COMMON_FULL_PATH = RUNTIME_ROOT / "common_static_map2_1x.json"
TABLE_PATH = ROOT / "outputs" / "tables" / "feng_common_executor_bridge.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "feng_common_executor_bridge_audit.md"

OD_RELEASE_START = 8_260.0
OD_RELEASE_SEPARATION = 1_000.0
EPSILON = 1.0e-8


class BridgeError(RuntimeError):
    """Raised when the static bridge ceases to be an empty-network control."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise BridgeError("bridge table cannot be empty")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    temporary.replace(path)


def _binary_candidates() -> Iterable[Path]:
    yield ROOT / "build_cie_revision/python/Release/czr005_cpp.cp311-win_amd64.pyd"
    yield ROOT.parent / ".cie_native_dh_worktree/build_cie_revision/python/Release/czr005_cpp.cp311-win_amd64.pyd"
    yield ROOT / "build_vs/python/Release/czr005_cpp.cp311-win_amd64.pyd"


def resolve_binary(value: Path | None) -> Path:
    if value is not None:
        return value.resolve(strict=True)
    for candidate in _binary_candidates():
        if candidate.is_file():
            return candidate.resolve()
    raise BridgeError("common C++ binary not found; pass --binary")


def _factorial_args(binary: Path, output: Path) -> argparse.Namespace:
    """Project the bridge onto the frozen common-executor P0D0 interface."""

    return argparse.Namespace(
        map="map2",
        scale=1,
        policy="s4",
        potential="ff",
        dynamic="off",
        service_multiplier=1.0,
        release_mode="canonical",
        binary=binary,
        output=output,
        nanning_task_dir=factorial.g35.nanning_native.DEFAULT_TASK_DIR,
        nanning_map_profile=factorial.g35.nanning_native.DEFAULT_MAP_PROFILE,
        nanning_hca_root=factorial.g35.nanning_paired.DEFAULT_HCA_ROOT,
        map2_workload_1x=factorial.g35.map2_native.DEFAULT_WORKLOAD_1X,
        map2_workload_2x=factorial.g35.map2_native.DEFAULT_WORKLOAD_2X,
        map2_hca_case_root=None,
        dry_run=False,
        force=True,
    )


def compile_java(*, javac: str) -> None:
    feng_runner.compile_java(javac=javac, classes_dir=CLASSES_DIR)


def run_feng_od(*, java: str) -> list[dict[str, str]]:
    FENG_OD_RAW.parent.mkdir(parents=True, exist_ok=True)
    command = [
        java,
        "-Djava.awt.headless=true",
        "-cp",
        str(CLASSES_DIR.resolve()),
        feng_runner.MAIN_CLASS,
        "static-bridge",
        "--map",
        str(MAP_PATH.resolve()),
        "--csv-out",
        str(FENG_OD_RAW.resolve()),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    rows = _read_csv(FENG_OD_RAW)
    if not rows or any(
        row[
            "observed_matches_edge_plus_post_admission_node_service_quantization"
        ]
        != "true"
        for row in rows
    ):
        raise BridgeError(
            "Feng OD probe did not reproduce edge-lattice plus legacy node service time"
        )
    return rows


def _map_records(parsed: LegacyMap) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    nodes = [
        (
            node.location,
            node.node_type,
            node.service_time,
            node.y,
            node.x,
            tuple(node.outgoing),
        )
        for node in parsed.nodes
    ]
    edges = [(edge.start, edge.end, edge.length, edge.speed) for edge in parsed.edges]
    return nodes, edges


def shared_hff_path(
    parsed: LegacyMap,
    heuristic: Sequence[Sequence[float]],
    start: int,
    goal: int,
) -> list[int]:
    """Apply the common runtime's exact static comparator: (score,next node)."""

    outgoing: dict[int, list[Any]] = {node.location: [] for node in parsed.nodes}
    for edge in parsed.edges:
        outgoing[edge.start].append(edge)
    for values in outgoing.values():
        values.sort(key=lambda edge: edge.end)
    path = [start]
    current = start
    for _ in range(len(parsed.nodes) + 1):
        if current == goal:
            return path
        candidates = outgoing[current]
        if not candidates:
            raise BridgeError(f"H_FF path unexpectedly stops at {current} for {start}->{goal}")
        chosen = min(
            candidates,
            key=lambda edge: (edge.travel_time + heuristic[edge.end][goal], edge.end),
        )
        current = chosen.end
        if current in path:
            raise BridgeError(f"H_FF control loop for {start}->{goal}: {path + [current]}")
        path.append(current)
    raise BridgeError(f"H_FF control exceeded node bound for {start}->{goal}")


def run_common_od(
    feng_rows: Sequence[Mapping[str, str]], *, binary: Path
) -> tuple[list[dict[str, Any]], dict[str, Any], list[list[float]]]:
    args = _factorial_args(binary, COMMON_OD_META)
    _case_id, _workload, request, _release, prepared = factorial.prepare_cell(args)
    if prepared["cell_id"] != "P0D0" or request.get("s4_score_component_mask") != 0:
        raise BridgeError("common OD probe must be the frozen H_FF/dynamic-off P0D0 cell")

    parsed = parse_legacy_map(MAP_PATH)
    nodes, edges = _map_records(parsed)
    hff, contract = potential.free_flow_potential(nodes, edges)
    if request["heuristic_time"] != hff:
        raise BridgeError("prepared common request does not contain the audited H_FF matrix")

    records: list[tuple[Any, ...]] = []
    for ordinal, row in enumerate(feng_rows):
        release = OD_RELEASE_START + ordinal * OD_RELEASE_SEPARATION
        records.append(
            (
                f"bridge:{row['start_node']}:{row['goal_node']}",
                ordinal,
                release,
                release + 100_000.0,
                int(row["start_node"]),
                int(row["goal_node"]),
                "bridge_nonoverlap",
            )
        )
    final_release = OD_RELEASE_START + len(records) * OD_RELEASE_SEPARATION
    probe = dict(request)
    probe.update(
        bag_records=records,
        max_simulation_time=final_release + OD_RELEASE_SEPARATION,
        max_events=max(1_000_000, len(records) * 1_000),
        scenario="feng_common_static_bridge_all_reachable_od_nonoverlap",
        trace_limit=0,
        event_trace_limit=0,
    )
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**probe)
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    if not isinstance(bags, list) or not isinstance(summary, Mapping):
        raise BridgeError("common OD probe returned no bag/summary payload")
    if int(summary.get("completed_count", -1)) != len(records) or len(bags) != len(records):
        raise BridgeError("common OD probe did not complete every reachable OD")
    by_segment = {str(row["segment_id"]): dict(row) for row in bags}
    if len(by_segment) != len(records):
        raise BridgeError("common OD probe segment IDs are not unique")

    rows: list[dict[str, Any]] = []
    for feng in feng_rows:
        start, goal = int(feng["start_node"]), int(feng["goal_node"])
        segment = f"bridge:{start}:{goal}"
        bag = by_segment.get(segment)
        if bag is None or bag.get("completed") is not True:
            raise BridgeError(f"missing completed common OD probe {start}->{goal}")
        path = shared_hff_path(parsed, hff, start, goal)
        common_path = ">".join(str(value) for value in path)
        edge_travel = float(bag["edge_travel_time_seconds"])
        ideal = float(feng["ideal_free_flow_seconds"])
        source_wait = float(bag["source_queue_delay"])
        local_wait = float(bag["total_local_wait"])
        completion = float(bag["goal_completion_time_seconds"])
        if source_wait > EPSILON or local_wait > EPSILON or int(bag["retry_count"]) != 0:
            raise BridgeError(f"OD probe {start}->{goal} was not an empty-network run")
        if completion >= OD_RELEASE_SEPARATION - EPSILON:
            raise BridgeError("OD release separation is too small for independent probes")
        rows.append(
            {
                "segment_id": segment,
                "start_node": start,
                "goal_node": goal,
                "common_path": common_path,
                "common_edge_travel_seconds": edge_travel,
                "common_node_service_seconds": float(bag["node_service_time_seconds"]),
                "common_single_bag_tht_seconds": completion,
                "common_source_queue_delay_seconds": source_wait,
                "common_local_wait_seconds": local_wait,
                "common_retry_count": int(bag["retry_count"]),
                "common_edge_time_matches_feng_ideal": math.isclose(
                    edge_travel, ideal, rel_tol=0.0, abs_tol=EPSILON
                ),
            }
        )
    _write_csv(COMMON_OD_RAW, rows)
    summary_fields = (
        "requested_count",
        "completed_count",
        "failed_count",
        "time_limit_reached",
        "peak_active_bag_count",
        "max_source_queue_delay",
        "max_individual_wait",
        "conflicts",
        "reservation_conflicts",
        "scorer_mode",
        "s4_score_component_mask",
        "complete_on_goal_arrival_enabled",
        "runtime_full_astar_calls",
        "full_future_routes_stored",
        "merge_grant_rule",
        "merge_grant_timing_mode",
        "pibt_mode",
        "g4irsf20_event_hotpath_policy",
    )
    metadata = {
        "schema": SCHEMA,
        "probe": "COMMON_EXECUTOR_NONOVERLAPPING_SINGLE_BAG_OD",
        "method": "STATIC_FREE_FLOW_COMMON_EXECUTOR",
        "cell_id": "P0D0",
        "potential": "H_FF",
        "dynamic_score_component_mask": 0,
        "release_start_seconds": OD_RELEASE_START,
        "release_separation_seconds": OD_RELEASE_SEPARATION,
        "empty_network_gate": {
            "all_source_queue_delay_zero": True,
            "all_local_wait_zero": True,
            "all_retry_count_zero": True,
        },
        "binary_path": str(binary),
        "binary_sha256": _sha256(binary),
        "map_sha256": _sha256(MAP_PATH),
        "potential_contract": contract,
        "native_summary": {key: summary.get(key) for key in summary_fields},
    }
    _write_json(COMMON_OD_META, metadata)
    return rows, metadata, hff


def _run_feng_full(*, java: str, force: bool) -> dict[str, str]:
    summary_path = FENG_FULL_DIR / "summary.csv"
    if force or not summary_path.is_file():
        FENG_FULL_DIR.mkdir(parents=True, exist_ok=True)
        command = feng_runner.java_run_command(
            java=java,
            classes_dir=CLASSES_DIR,
            map_path=MAP_PATH,
            input_path=INPUT_PATH,
            output_dir=FENG_FULL_DIR,
            alpha_seconds=0.0,
            beta_seconds=0.0,
            max_raw_bags=0,
            workload_scale=1.0,
            seed=0,
            horizon_seconds=90_000.0,
            trace_sample_modulo=0,
        )
        subprocess.run(command, cwd=ROOT, check=True)
    rows = _read_csv(summary_path)
    if len(rows) != 1 or rows[0].get("method") != "STATIC_FREE_FLOW_FENG_EXECUTOR":
        raise BridgeError("Feng full-population output is not the exact static control")
    return rows[0]


def _run_common_full(*, binary: Path, force: bool) -> dict[str, Any]:
    if COMMON_FULL_PATH.is_file() and not force:
        payload = json.loads(COMMON_FULL_PATH.read_text(encoding="utf-8"))
    else:
        args = _factorial_args(binary, COMMON_FULL_PATH)
        payload = factorial.execute(args)
        _write_json(COMMON_FULL_PATH, payload)
    if payload.get("status") != "COMPLETE":
        raise BridgeError("common static 1x full-population run is not complete")
    algorithm = payload.get("algorithm", {})
    if algorithm.get("cell_id") != "P0D0" or algorithm.get("dynamic") != "off":
        raise BridgeError("common full-population output is not H_FF/dynamic-off P0D0")
    return payload


def _paired_od_rows(
    feng_rows: Sequence[Mapping[str, str]],
    common_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    common = {(int(row["start_node"]), int(row["goal_node"])): row for row in common_rows}
    paired: list[dict[str, Any]] = []
    for feng in feng_rows:
        key = (int(feng["start_node"]), int(feng["goal_node"]))
        right = common.get(key)
        if right is None:
            raise BridgeError(f"common OD table misses {key[0]}->{key[1]}")
        feng_observed = float(feng["observed_single_bag_seconds"])
        common_tht = float(right["common_single_bag_tht_seconds"])
        paired.append(
            {
                "row_type": "OD_SINGLE_BAG",
                "executor": "PAIRED_STATIC_FREE_FLOW",
                "start_node": key[0],
                "goal_node": key[1],
                "feng_path": feng["node_path"],
                "common_path": right["common_path"],
                "path_match": feng["node_path"] == right["common_path"],
                "origin_equal_score_candidate_count": int(
                    feng["origin_equal_score_candidates"]
                ),
                "feng_ideal_edge_seconds": float(feng["ideal_free_flow_seconds"]),
                "common_edge_travel_seconds": float(right["common_edge_travel_seconds"]),
                "edge_travel_difference_seconds": float(
                    right["common_edge_travel_seconds"]
                )
                - float(feng["ideal_free_flow_seconds"]),
                "feng_edge_quantized_seconds": float(feng["edge_quantized_seconds"]),
                "feng_path_node_service_seconds": float(
                    feng["legacy_path_node_service_seconds"]
                ),
                "feng_post_admission_node_service_seconds": float(
                    feng["post_admission_node_service_seconds"]
                ),
                "feng_edge_plus_post_admission_node_service_quantized_seconds": float(
                    feng[
                        "edge_plus_post_admission_node_service_quantized_seconds"
                    ]
                ),
                "feng_single_bag_tht_seconds": feng_observed,
                "feng_quantization_bias_seconds": float(feng["quantization_bias_seconds"]),
                "common_node_service_seconds": float(
                    right["common_node_service_seconds"]
                ),
                "common_single_bag_tht_seconds": common_tht,
                "single_bag_mechanical_gap_common_minus_feng_seconds": (
                    common_tht - feng_observed
                ),
                "empty_network_gate": (
                    float(right["common_source_queue_delay_seconds"]) <= EPSILON
                    and float(right["common_local_wait_seconds"]) <= EPSILON
                    and int(right["common_retry_count"]) == 0
                ),
                "metric_definition": (
                    "one bag per reachable ordered OD; releases separated by 1000s; "
                    "Feng is 0.2s position lattice; common is continuous event time"
                ),
            }
        )
    return paired


def _full_rows(feng: Mapping[str, str], common: Mapping[str, Any]) -> list[dict[str, Any]]:
    common_capacity = common["paper_subjects"]["fixed_horizon_capacity"]
    common_timing = common["paper_subjects"]["full_population_raw_bag_timing"]
    metrics = common_timing["metrics_seconds"]["paper_network_from_admission"]
    return [
        {
            "row_type": "FULL_POPULATION_1X",
            "executor": "STATIC_FREE_FLOW_FENG_EXECUTOR",
            "status": feng["status"],
            "raw_bag_count": int(feng["raw_bag_count"]),
            "completed_raw_bags": int(feng["completed_raw_bags"]),
            "segment_count": int(feng["segment_count"]),
            "completed_segments": int(feng["completed_segments"]),
            "tht_min_seconds": float(
                feng["diagnostic_first_admission_to_completion_min_seconds"]
            ),
            "tht_mean_seconds": float(
                feng["diagnostic_first_admission_to_completion_mean_seconds"]
            ),
            "tht_p95_seconds": float(
                feng["diagnostic_first_admission_to_completion_p95_seconds"]
            ),
            "tht_p99_seconds": float(
                feng["diagnostic_first_admission_to_completion_p99_seconds"]
            ),
            "tht_max_seconds": float(
                feng["diagnostic_first_admission_to_completion_max_seconds"]
            ),
            "metric_definition": (
                "raw bag; sum segment first-admission-to-goal-arrival; EBS storage and "
                "source wait excluded"
            ),
            "artifact": str((FENG_FULL_DIR / "summary.csv").relative_to(ROOT)),
        },
        {
            "row_type": "FULL_POPULATION_1X",
            "executor": "STATIC_FREE_FLOW_COMMON_EXECUTOR",
            "status": common["status"],
            "raw_bag_count": int(common["population"]["raw_bag_count"]),
            "completed_raw_bags": int(common_capacity["completed_raw_bag_count"]),
            "segment_count": int(common["population"]["segment_count"]),
            "completed_segments": int(common["runtime"]["native_summary"]["completed_count"]),
            "tht_min_seconds": float(metrics["min"]),
            "tht_mean_seconds": float(metrics["mean"]),
            "tht_p95_seconds": float(metrics["p95"]),
            "tht_p99_seconds": float(metrics["p99"]),
            "tht_max_seconds": float(metrics["max"]),
            "metric_definition": (
                "raw bag; paper_network_from_admission under canonical release; common "
                "executor coordination remains active"
            ),
            "artifact": str(COMMON_FULL_PATH.relative_to(ROOT)),
        },
    ]


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else math.nan


def _render_report(
    od_rows: Sequence[Mapping[str, Any]],
    full_rows: Sequence[Mapping[str, Any]],
    *,
    binary: Path,
) -> None:
    path_matches = sum(row["path_match"] is True for row in od_rows)
    empty_matches = sum(row["empty_network_gate"] is True for row in od_rows)
    edge_diffs = [abs(float(row["edge_travel_difference_seconds"])) for row in od_rows]
    quantization = [float(row["feng_quantization_bias_seconds"]) for row in od_rows]
    mechanical = [
        float(row["single_bag_mechanical_gap_common_minus_feng_seconds"])
        for row in od_rows
    ]
    tie_rows = sum(int(row["origin_equal_score_candidate_count"]) > 1 for row in od_rows)
    full_by_executor = {row["executor"]: row for row in full_rows}
    feng = full_by_executor["STATIC_FREE_FLOW_FENG_EXECUTOR"]
    common = full_by_executor["STATIC_FREE_FLOW_COMMON_EXECUTOR"]
    text = f"""# Feng/common executor static-free-flow bridge audit

## Outcome

The route input is aligned: all **{path_matches}/{len(od_rows)}** reachable ordered
map2 OD pairs selected the same full node sequence, and their edge-only travel
times agree to at most **{max(edge_diffs):.12g} s**.  All {empty_matches} common
OD probes had zero source queue, zero local wait, and zero retry, so these are
genuine non-overlapping single-bag controls.

This does **not** make the executors mechanically equivalent.  The Feng control
uses a 0.2 s position lattice and the recovered legacy node-through service;
the common executor retains continuous event time, node service, calendars,
immediate source arbitration, and coordination machinery.  The single-bag mechanical gap
(common minus Feng) is [{min(mechanical):.6f}, {max(mechanical):.6f}] s
(mean {_mean(mechanical):.6f} s),
which is recorded rather than subtracted from any G31--DH result.

## Static OD control

- Map: `legacy/jichang_origin_readonly/map2.txt` ({_sha256(MAP_PATH)})
- Reachable ordered OD pairs (excluding start=goal): {len(od_rows)}
- Shared score: `edge_length / 2.5 + H_FF(next, goal)`
- Shared tie-break: minimum next-node ID; recursively this is the lexicographically
  minimum full node sequence. Origin score ties observed: {tie_rows}.
- Feng edge-lattice quantization bias: {min(quantization):.12g}--{max(quantization):.12g} s
  (mean {_mean(quantization):.12g} s). Map2 edge times are exact 0.2 s multiples,
  so this specific map has zero quantization bias; the audit did not assume it.
- Common binary: `{binary}` ({_sha256(binary)})

The common OD execution is the existing `P0D0` configuration: H_FF selected,
Q/I/corridor-wait/service-wait score terms masked off. Releases are 1000 s apart,
larger than every observed single-bag completion time, solely to keep each OD
probe empty-network. No route or timing result was used to tune the control.

## Original map2 1x full population

| executor | completed raw | completed segments | min | mean | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Feng static | {feng['completed_raw_bags']}/{feng['raw_bag_count']} | {feng['completed_segments']}/{feng['segment_count']} | {feng['tht_min_seconds']:.3f} | {feng['tht_mean_seconds']:.3f} | {feng['tht_p95_seconds']:.3f} | {feng['tht_p99_seconds']:.3f} | {feng['tht_max_seconds']:.3f} |
| Common H_FF / dynamic off | {common['completed_raw_bags']}/{common['raw_bag_count']} | {common['completed_segments']}/{common['segment_count']} | {common['tht_min_seconds']:.3f} | {common['tht_mean_seconds']:.3f} | {common['tht_p95_seconds']:.3f} | {common['tht_p99_seconds']:.3f} | {common['tht_max_seconds']:.3f} |

Both rows use the original 28,506-raw / 43,603-segment canonical workload and
admission-to-goal-arrival raw-bag timing, excluding EBS scheduled storage wait.
The common row still contains its executor release/injection and coordination semantics (including
strict descent, FIFO merge grants, event hotpath and bounded-local feasibility),
even though the four dynamic route-score terms are off. Therefore the full-run
difference is a package-level executor/mechanics contrast, not a route-only
effect and not an estimate to subtract from the G31--DH gap.

## Goal completion boundary

Feng completes after the final-edge arrival and any positive goal service on a
discrete tick.  The common cell completes on physical goal arrival and does not
execute goal-node service. Both execute source/intermediate service, but their
service and time-discretization mechanics differ. The OD table exposes both
executors' node-service seconds separately. The Feng single-bag THT is measured
from first edge admission, so its post-admission field excludes source service
and includes intermediate/goal service; edge travel remains identical.

## Artifacts

- `{TABLE_PATH.relative_to(ROOT)}`: every OD plus the two 1x population rows
- `{FENG_OD_RAW.relative_to(ROOT)}`: Java position-lattice OD output
- `{COMMON_OD_RAW.relative_to(ROOT)}`: native common-executor OD output
- `{COMMON_OD_META.relative_to(ROOT)}`: binary, H_FF and empty-network identity
- `{(FENG_FULL_DIR / 'summary.csv').relative_to(ROOT)}`: Feng static 1x summary
- `{COMMON_FULL_PATH.relative_to(ROOT)}`: common P0D0 canonical 1x result
"""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(text, encoding="utf-8", newline="\n")


def run(*, binary: Path, java: str, javac: str, force: bool, skip_full: bool) -> dict[str, Any]:
    if _sha256(MAP_PATH) != feng_runner.EXPECTED_MAP_SHA256:
        raise BridgeError("frozen map2 identity drift")
    if _sha256(INPUT_PATH) != feng_runner.EXPECTED_INPUT_SHA256:
        raise BridgeError("frozen inputdata identity drift")
    compile_java(javac=javac)
    feng_od = run_feng_od(java=java)
    common_od, metadata, _hff = run_common_od(feng_od, binary=binary)
    od_rows = _paired_od_rows(feng_od, common_od)
    if any(row["path_match"] is not True for row in od_rows):
        raise BridgeError("Feng and common static tie-break paths differ")
    if any(abs(float(row["edge_travel_difference_seconds"])) > EPSILON for row in od_rows):
        raise BridgeError("Feng and common static edge travel times differ")

    full_rows: list[dict[str, Any]] = []
    if not skip_full:
        feng_full = _run_feng_full(java=java, force=force)
        common_full = _run_common_full(binary=binary, force=force)
        full_rows = _full_rows(feng_full, common_full)
    _write_csv(TABLE_PATH, [*od_rows, *full_rows])
    if full_rows:
        _render_report(od_rows, full_rows, binary=binary)
    return {
        "schema": SCHEMA,
        "status": "COMPLETE" if full_rows else "OD_AUDIT_COMPLETE_FULL_POPULATION_SKIPPED",
        "reachable_od_count": len(od_rows),
        "path_match_count": sum(row["path_match"] is True for row in od_rows),
        "empty_network_probe_count": sum(
            row["empty_network_gate"] is True for row in od_rows
        ),
        "max_absolute_edge_time_difference_seconds": max(
            abs(float(row["edge_travel_difference_seconds"])) for row in od_rows
        ),
        "max_absolute_feng_quantization_bias_seconds": max(
            abs(float(row["feng_quantization_bias_seconds"])) for row in od_rows
        ),
        "common_od_metadata_path": str(COMMON_OD_META),
        "common_binary_sha256": metadata["binary_sha256"],
        "table": str(TABLE_PATH),
        "report": str(REPORT_PATH) if full_rows else None,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--java", default="java")
    parser.add_argument("--javac", default="javac")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-full", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run(
        binary=resolve_binary(args.binary),
        java=args.java,
        javac=args.javac,
        force=args.force,
        skip_full=args.skip_full,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        BridgeError,
        factorial.PotentialFactorialError,
        factorial.g35.FullPopulationError,
        potential.ServicePotentialError,
        cpp_backend.CppBackendUnavailable,
        OSError,
        ValueError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"Feng/common executor bridge failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
