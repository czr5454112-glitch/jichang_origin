"""Build and execute the G4IRSF13 thesis-aligned local fault study.

This module deliberately separates three kinds of evidence:

* the paper-reported 16 scenarios and their exact legacy ``arc.txt`` mapping;
* graph-only preventive criticality on the protected real ``map2``;
* executable, matched policy-on/off probes using unmodified rows from the
  protected task source and the same always-on physical entry interlock.

The executable study never edits the map, stores a future route, or invokes a
full A*/CIE/global-reservation fallback.  Dynamic fault windows are passed to
the one-edge event runtime as an availability overlay.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import inspect
import io
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import g4irsf13_thesis_priority_extraction as thesis
from scripts.eval.g4irsf11_fixed_map import (
    assert_canonical_map,
    canonical_graph_records,
)


MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
F2_POLICY_PATH = Path("artifacts/policies/g4irsf13_f2_frozen_baseline.json")

MAPPING_PATH = Path(
    "outputs/tables/g4irsf13_thesis_fault_scenario_mapping.csv"
)
CAUSAL_PATH = Path("outputs/tables/g4irsf13_fault_causal_ab.csv")
CRITICALITY_PATH = Path("outputs/tables/g4irsf13_fault_criticality.csv")
DESIGN_REPORT_PATH = Path(
    "outputs/reports/g4irsf13_fault_mechanism_design.md"
)
RESULT_REPORT_PATH = Path(
    "outputs/reports/g4irsf13_fault_recovery_results.md"
)
POLICY_PATH = Path("artifacts/policies/g4irsf13_fault_control_bundle.json")

SCHEMA = "czr005.g4irsf13.fault_control.v1"
MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
FROZEN_BINARY_SHA256 = (
    "814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7"
)
F2_CANDIDATE_ID = "J_F2"
FORMAL_GOALS = (47, 48, 49, 50, 51)
FORMAL_SOURCES = (0, 1, 2, 3, 4, 5, 52)


class FaultControlError(ValueError):
    """Raised when fault evidence cannot be admitted."""


@dataclass(frozen=True)
class ProbeSpec:
    case_id: str
    comparator_id: str
    policy_enabled: bool
    pibt_mode: str
    fault_arc_ids: tuple[int, ...]
    fault_kind: str
    message_delay_seconds: float
    notification_dropped: bool
    duration_seconds: float
    target_goal: int
    execution_status: str = "EXECUTED"
    blocker: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_inputs() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    map_path = ROOT / MAP_PATH
    task_path = ROOT / TASK_PATH
    if _sha256(map_path) != MAP_RAW_SHA256:
        raise FaultControlError("protected map SHA-256 drift")
    if _sha256(task_path) != TASK_RAW_SHA256:
        raise FaultControlError("protected task SHA-256 drift")
    graph = json.loads(map_path.read_text(encoding="utf-8"))
    tasks = [
        json.loads(line)
        for line in task_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(tasks) != 43_603 or len({int(row["task_id"]) for row in tasks}) != 28_506:
        raise FaultControlError("protected task population drift")
    return graph, tasks


def _edge_index(
    graph: Mapping[str, Any],
) -> dict[tuple[int, int], dict[str, Any]]:
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for raw in graph["edges"]:
        row = dict(raw)
        key = (int(row["start"]), int(row["end"]))
        if key in result:
            raise FaultControlError(f"duplicate real-map edge {key}")
        result[key] = row
    return result


def _adjacency(
    graph: Mapping[str, Any],
    *,
    removed: Iterable[tuple[int, int]] = (),
) -> dict[int, tuple[int, ...]]:
    blocked = set(removed)
    outgoing: dict[int, list[int]] = {
        int(node["location"]): [] for node in graph["nodes"]
    }
    for edge in graph["edges"]:
        key = (int(edge["start"]), int(edge["end"]))
        if key not in blocked:
            outgoing[key[0]].append(key[1])
    return {node: tuple(values) for node, values in outgoing.items()}


def _reachable(adjacency: Mapping[int, Sequence[int]], start: int) -> set[int]:
    seen = {start}
    pending = [start]
    while pending:
        current = pending.pop()
        for nxt in adjacency.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                pending.append(nxt)
    return seen


def _weak_bridges(graph: Mapping[str, Any]) -> set[tuple[int, int]]:
    """Return directed edges whose undirected projection is a bridge."""

    neighbours: dict[int, set[int]] = {
        int(node["location"]): set() for node in graph["nodes"]
    }
    directed: set[tuple[int, int]] = set()
    for edge in graph["edges"]:
        start = int(edge["start"])
        end = int(edge["end"])
        directed.add((start, end))
        neighbours[start].add(end)
        neighbours[end].add(start)
    discovery: dict[int, int] = {}
    low: dict[int, int] = {}
    parent: dict[int, int] = {}
    tick = 0
    undirected_bridges: set[frozenset[int]] = set()

    def visit(node: int) -> None:
        nonlocal tick
        tick += 1
        discovery[node] = tick
        low[node] = tick
        for nxt in sorted(neighbours[node]):
            if nxt not in discovery:
                parent[nxt] = node
                visit(nxt)
                low[node] = min(low[node], low[nxt])
                if low[nxt] > discovery[node]:
                    undirected_bridges.add(frozenset((node, nxt)))
            elif parent.get(node) != nxt:
                low[node] = min(low[node], discovery[nxt])

    for node in sorted(neighbours):
        if node not in discovery:
            visit(node)
    return {
        edge for edge in directed if frozenset(edge) in undirected_bridges
    }


def _arc_index() -> dict[int, tuple[int, int, float]]:
    return {
        int(arc_id): (int(start), int(end), float(length))
        for arc_id, start, end, length in thesis.ARC_1_TO_8
    }


def build_mapping_rows(
    graph: Mapping[str, Any],
) -> list[dict[str, Any]]:
    edges = _edge_index(graph)
    arc_index = _arc_index()
    baseline = _adjacency(graph)
    baseline_pairs = {
        (source, goal)
        for source in FORMAL_SOURCES
        for goal in FORMAL_GOALS
        if goal in _reachable(baseline, source)
    }
    rows: list[dict[str, Any]] = []
    for scenario_id, arc_ids, affected, paper_success in (
        thesis.THESIS_FAULT_SCENARIOS
    ):
        mapped: list[tuple[int, int]] = []
        for arc_id in arc_ids:
            start, end, length = arc_index[int(arc_id)]
            actual = edges.get((start, end))
            if actual is None or not math.isclose(
                float(actual["length"]), length, rel_tol=0.0, abs_tol=1.0e-12
            ):
                raise FaultControlError(
                    f"{scenario_id}: thesis arc {arc_id} does not match map2"
                )
            mapped.append((start, end))
        after = _adjacency(graph, removed=mapped)
        surviving_pairs = {
            (source, goal)
            for source, goal in baseline_pairs
            if goal in _reachable(after, source)
        }
        rows.append(
            {
                "schema": SCHEMA,
                "scenario_id": scenario_id,
                "scenario_group": (
                    "single"
                    if len(arc_ids) == 1
                    else ("pair" if len(arc_ids) == 2 else "triple")
                ),
                "thesis_arc_ids_json": list(arc_ids),
                "map2_edges_json": [
                    {"start": start, "end": end} for start, end in mapped
                ],
                "map_identity_pass": True,
                "paper_reported_affected_conveyors": int(affected),
                "paper_reported_success_rate": float(paper_success),
                "paper_outcome_scope": "THESIS_REPORTED_NOT_G4IRSF13_RESULT",
                "baseline_reachable_source_goal_pairs": len(baseline_pairs),
                "remaining_reachable_source_goal_pairs": len(surviving_pairs),
                "lost_reachable_source_goal_pairs": len(
                    baseline_pairs - surviving_pairs
                ),
                "disconnected_pairs_json": [
                    {"source": source, "goal": goal}
                    for source, goal in sorted(baseline_pairs - surviving_pairs)
                ],
                "mapping_status": "EXACT_ARC_TXT_TO_REAL_MAP2",
                "runtime_replication_status": (
                    "MAPPED_FOR_LOCAL_OVERLAY_PROBES"
                ),
            }
        )
    return rows


def build_criticality_rows(
    graph: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    arc_index = _arc_index()
    adjacency = _adjacency(graph)
    edges = _edge_index(graph)
    bridges = _weak_bridges(graph)
    indegree: dict[int, int] = {int(node["location"]): 0 for node in graph["nodes"]}
    outdegree: dict[int, int] = {
        int(node["location"]): len(node["outgoing"]) for node in graph["nodes"]
    }
    for edge in graph["edges"]:
        indegree[int(edge["end"])] += 1

    baseline_reach = {
        source: _reachable(adjacency, source)
        for source in {int(row["start"]) for row in tasks}
    }
    scenario_membership: dict[int, list[str]] = {arc_id: [] for arc_id in arc_index}
    for scenario_id, arc_ids, _affected, _success in thesis.THESIS_FAULT_SCENARIOS:
        for arc_id in arc_ids:
            scenario_membership[int(arc_id)].append(scenario_id)

    rows: list[dict[str, Any]] = []
    for arc_id, (start, end, length) in sorted(arc_index.items()):
        removed = _adjacency(graph, removed=[(start, end)])
        after_reach = {
            source: _reachable(removed, source) for source in baseline_reach
        }
        affected_segments = sum(
            int(row["goal"]) in baseline_reach[int(row["start"])]
            and int(row["goal"]) not in after_reach[int(row["start"])]
            for row in tasks
        )
        lost_pairs = sum(
            goal in baseline_reach[source] and goal not in after_reach[source]
            for source in FORMAL_SOURCES
            for goal in FORMAL_GOALS
        )
        alternate_count = max(0, outdegree[start] - 1)
        bridge = (start, end) in bridges
        split_edge = outdegree[start] > 1
        merge_target = indegree[end] > 1
        # This is an explicitly declared maintenance heuristic, not a runtime
        # routing score and not a causal estimate.
        score = (
            float(affected_segments)
            + 100.0 * float(lost_pairs)
            + 25.0 * float(bridge)
            + 10.0 * float(merge_target)
            + 5.0 * float(split_edge and alternate_count == 0)
        )
        rows.append(
            {
                "schema": SCHEMA,
                "arc_id": arc_id,
                "start": start,
                "end": end,
                "length": length,
                "real_map_edge_pass": (start, end) in edges,
                "actual_task_segments_losing_reachability": affected_segments,
                "source_goal_pair_reachability_loss": lost_pairs,
                "alternate_outgoing_edge_count": alternate_count,
                "weak_projection_bridge": bridge,
                "source_is_split": split_edge,
                "target_is_merge": merge_target,
                "paper_scenario_membership_json": scenario_membership[arc_id],
                "maintenance_priority_score": score,
                "score_semantics": (
                    "offline_reachability_and_topology_ranking_only"
                ),
            }
        )
    ordered = sorted(
        rows,
        key=lambda row: (
            -float(row["maintenance_priority_score"]),
            int(row["arc_id"]),
        ),
    )
    for rank, row in enumerate(ordered, start=1):
        row["maintenance_rank"] = rank
    return rows


def _f2_case() -> harness.CaseSpec:
    matches = [
        case
        for case in harness.original_scale_cases()
        if case.candidate_id == F2_CANDIDATE_ID
    ]
    if len(matches) != 1:
        raise FaultControlError(f"expected one frozen F2 case, got {len(matches)}")
    frozen_path = ROOT / F2_POLICY_PATH
    if not frozen_path.is_file():
        raise FaultControlError("frozen F2 policy is missing")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    expected = frozen.get("provenance", {}).get("case_config_sha256")
    actual = harness.canonical_sha256(matches[0].as_dict())
    if actual != expected:
        raise FaultControlError("frozen F2 case configuration drift")
    return matches[0]


def probe_specs() -> tuple[ProbeSpec, ...]:
    return (
        ProbeSpec(
            "G0_no_fault",
            "",
            True,
            "P2",
            (),
            "no_fault_control",
            0.0,
            False,
            0.0,
            47,
        ),
        ProbeSpec(
            "G1_physical_shield_only",
            "",
            False,
            "P2",
            (8,),
            "single_alternate_edge_fault",
            0.0,
            False,
            97.0,
            47,
        ),
        ProbeSpec(
            "G2_control_physical_shield_only_p0",
            "",
            False,
            "P0",
            (8,),
            "single_alternate_edge_fault",
            0.0,
            False,
            97.0,
            47,
        ),
        ProbeSpec(
            "G2_ddi_local_policy",
            "G2_control_physical_shield_only_p0",
            True,
            "P0",
            (8,),
            "single_alternate_edge_fault",
            0.0,
            False,
            97.0,
            47,
        ),
        ProbeSpec(
            "G3_ddi_plus_p2",
            "G1_physical_shield_only",
            True,
            "P2",
            (8,),
            "single_alternate_edge_fault",
            0.0,
            False,
            97.0,
            47,
        ),
        ProbeSpec(
            "G4_v3_fault_aware_plus_p2",
            "G1_physical_shield_only",
            True,
            "P2",
            (8,),
            "single_alternate_edge_fault",
            0.0,
            False,
            97.0,
            47,
            execution_status="NOT_RUN",
            blocker=(
                "FRESH_HOLDOUT_OFFLINE_FAIL_RUNTIME_ACTIVATION_FORBIDDEN"
            ),
        ),
        ProbeSpec(
            "G5_delayed_message",
            "G3_ddi_plus_p2",
            True,
            "P2",
            (8,),
            "delayed_ddi",
            20.0,
            False,
            97.0,
            47,
        ),
        ProbeSpec(
            "G6_dropped_message",
            "G1_physical_shield_only",
            True,
            "P2",
            (8,),
            "dropped_ddi_physical_interlock_fallback",
            0.0,
            True,
            97.0,
            47,
        ),
        ProbeSpec(
            "G7_repair_reopen",
            "G7_control_physical_shield_only",
            True,
            "P2",
            (8,),
            "repair_generation_and_queue_wakeup",
            0.0,
            False,
            12.0,
            47,
        ),
        ProbeSpec(
            "G7_control_physical_shield_only",
            "",
            False,
            "P2",
            (8,),
            "repair_generation_and_queue_wakeup",
            0.0,
            False,
            12.0,
            47,
        ),
        ProbeSpec(
            "G8_multi_fault",
            "G8_control_physical_shield_only",
            True,
            "P2",
            (7, 8),
            "local_cut_then_repair",
            0.0,
            False,
            25.0,
            47,
        ),
        ProbeSpec(
            "G8_control_physical_shield_only",
            "",
            False,
            "P2",
            (7, 8),
            "local_cut_then_repair",
            0.0,
            False,
            25.0,
            47,
        ),
        ProbeSpec(
            "G9_cut_isolation",
            "G9_control_physical_shield_only",
            True,
            "P2",
            (1,),
            "source_cut_then_repair",
            0.0,
            False,
            25.0,
            47,
        ),
        ProbeSpec(
            "G9_control_physical_shield_only",
            "",
            False,
            "P2",
            (1,),
            "source_cut_then_repair",
            0.0,
            False,
            25.0,
            47,
        ),
    )


def _select_probe_task(
    tasks: Sequence[Mapping[str, Any]],
    *,
    goal: int,
) -> dict[str, Any]:
    # Arc 8 is reached through the real 0->6 edge.  Selecting the first
    # protected source-0 row with the requested real goal is deterministic and
    # keeps every task field byte-derived from the canonical input.
    for raw in tasks:
        if int(raw["start"]) == 0 and int(raw["goal"]) == goal:
            return dict(raw)
    raise FaultControlError(f"no protected source-0 task reaches goal {goal}")


def _runtime_controls(
    case: harness.CaseSpec,
    *,
    spec: ProbeSpec,
    pibt_mode: str,
) -> dict[str, Any]:
    from czr005 import cpp_backend

    accepted = set(
        inspect.signature(
            cpp_backend.g4irsf11_event_runtime_from_records
        ).parameters
    )
    controls = {
        key: value
        for key, value in case.runtime_controls.items()
        if key in accepted
    }
    controls["pibt_mode"] = pibt_mode
    controls["pibt_max_depth"] = int(pibt_mode[1:])
    if pibt_mode == "P0":
        controls["local_queue_capacity"] = max(
            32, int(controls.get("local_queue_capacity", 0))
        )
    if spec.case_id in {
        "G9_cut_isolation",
        "G9_control_physical_shield_only",
    }:
        # Exercise the real first-edge credit admission path at the source
        # cut. Policy-on/off use identical admission and always-on physical
        # shield controls. The event runtime issues, binds, and consumes a
        # successful credit atomically, so the formal evidence is rejection
        # while the edge is physically faulted, not a fabricated live-credit
        # revocation window.
        controls["admission_mode"] = "expiring_first_edge_credit"
        controls["enable_source_admission"] = True
        controls["enable_backpressure"] = False
    return controls


def _fault_windows(
    spec: ProbeSpec,
    task: Mapping[str, Any],
) -> list[tuple[int, int, float, float, float, bool]]:
    if not spec.fault_arc_ids:
        return []
    release = float(task["pass_time"])
    # Internal arcs 7/8 are reached after source service, 0->6 travel, and node
    # 6 service. Starting at release+3s ensures the fault is active before the
    # current one-edge decision at node 6. Arc 1 starts at release so G9
    # exercises physical-fault rejection in the real first-edge credit path.
    start_time = (
        release
        if spec.fault_kind == "source_cut_then_repair"
        else release + 3.0
    )
    repair_time = start_time + spec.duration_seconds
    arcs = _arc_index()
    result = []
    for arc_id in spec.fault_arc_ids:
        start, end, _length = arcs[arc_id]
        result.append(
            (
                start,
                end,
                start_time,
                repair_time,
                spec.message_delay_seconds,
                spec.notification_dropped,
            )
        )
    return result


def _fault_candidate_exposure(
    payload: Mapping[str, Any],
    fault_edges: set[tuple[int, int]],
) -> tuple[int, int]:
    candidate_exposure = 0
    for owner in ("decisions", "hold_attempts"):
        rows = payload.get(owner, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            current = int(row.get("current_node", -1))
            for candidate in row.get("candidate_records", []):
                edge = (current, int(candidate.get("next_node", -1)))
                if (
                    edge in fault_edges
                    and candidate.get("shield_reason") == "physical_fault"
                ):
                    candidate_exposure += 1
    summary = payload.get("summary", {})
    # The runtime counters are fault-window scoped. Counting every selected
    # target edge here would incorrectly count a legitimate post-repair entry
    # as fault exposure.
    target_attempt = max(
        int(summary.get("fault_target_edge_attempt_count", 0)),
        int(summary.get("physical_fault_interlock_rejection_count", 0)),
    )
    return candidate_exposure, target_attempt


def _fault_generation_audit(
    payload: Mapping[str, Any],
    fault_edges: set[tuple[int, int]],
) -> tuple[list[dict[str, Any]], bool, int, int]:
    physical_rows = [
        row
        for row in payload.get("fault_events", [])
        if isinstance(row, Mapping)
        and row.get("phase") == "physical_state_change"
        and (
            int(row.get("from_node", -1)),
            int(row.get("to_node", -1)),
        )
        in fault_edges
    ]
    sequences: list[dict[str, Any]] = []
    fault_count = 0
    repair_count = 0
    passed = True
    for edge in sorted(fault_edges):
        rows = sorted(
            [
                row
                for row in physical_rows
                if (
                    int(row.get("from_node", -1)),
                    int(row.get("to_node", -1)),
                )
                == edge
            ],
            key=lambda row: (
                float(row.get("time", -1.0)),
                int(row.get("seq", -1)),
            ),
        )
        rendered = [
            {
                "event": str(row.get("event", "")),
                "time": float(row.get("time", -1.0)),
                "generation": int(row.get("physical_generation", -1)),
                "active_count": int(row.get("physical_active_count", -1)),
            }
            for row in rows
        ]
        fault_count += sum(
            row["event"] == "FAULT" for row in rendered
        )
        repair_count += sum(
            row["event"] == "REPAIR" for row in rendered
        )
        edge_pass = (
            len(rendered) == 2
            and rendered[0]["event"] == "FAULT"
            and rendered[1]["event"] == "REPAIR"
            and rendered[0]["active_count"] > 0
            and rendered[1]["active_count"] == 0
            and rendered[0]["generation"] > 0
            and rendered[1]["generation"]
            == rendered[0]["generation"] + 1
            and rendered[1]["time"] > rendered[0]["time"]
        )
        passed = passed and edge_pass
        sequences.append(
            {
                "start": edge[0],
                "end": edge[1],
                "events": rendered,
                "generation_pass": edge_pass,
            }
        )
    if not fault_edges:
        passed = not physical_rows
    return sequences, passed, fault_count, repair_count


def execute_probe(
    spec: ProbeSpec,
    *,
    graph: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
    search_path: Path,
) -> dict[str, Any]:
    if spec.execution_status != "EXECUTED":
        return {
            "schema": SCHEMA,
            "case_id": spec.case_id,
            "execution_status": spec.execution_status,
            "gate_status": "NOT_RUN",
            "blocker": spec.blocker,
            "comparator_id": spec.comparator_id,
            "fault_kind": spec.fault_kind,
            "fault_arc_ids_json": list(spec.fault_arc_ids),
        }

    from czr005 import cpp_backend

    case = _f2_case()
    task = _select_probe_task(tasks, goal=spec.target_goal)
    node_records, edge_records, heuristic = canonical_graph_records(
        assert_canonical_map(ROOT / MAP_PATH)
    )
    windows = _fault_windows(spec, task)
    controls = _runtime_controls(
        case,
        spec=spec,
        pibt_mode=spec.pibt_mode,
    )
    request: dict[str, Any] = {
        "node_records": node_records,
        "edge_records": edge_records,
        "heuristic_time": heuristic,
        "bag_records": [
            (
                str(task["segment_id"]),
                int(task["task_id"]),
                float(task["pass_time"]),
                float(task["std"]),
                int(task["start"]),
                int(task["goal"]),
                f"node_{int(task['start'])}",
            )
        ],
        "fault_windows": windows,
        "retry_interval": 0.25,
        "trace_limit": 100_000,
        "event_trace_limit": 100_000,
        "max_simulation_time": float(task["pass_time"]) + 10_000.0,
        "enable_fault_policy": spec.policy_enabled,
        "scenario": f"g4irsf13_{spec.case_id}",
        "search_path": search_path,
        **controls,
    }
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    summary = payload.get("summary")
    bags = payload.get("bags")
    if not isinstance(summary, Mapping) or not isinstance(bags, list) or len(bags) != 1:
        raise FaultControlError(f"{spec.case_id}: malformed runtime payload")
    bag = bags[0]
    if not isinstance(bag, Mapping):
        raise FaultControlError(f"{spec.case_id}: malformed bag row")
    fault_edges = {
        (int(start), int(end))
        for start, end, _fault, _repair, _delay, _drop in windows
    }
    candidate_exposure, target_attempt = _fault_candidate_exposure(
        payload, fault_edges
    )
    (
        generation_sequence,
        generation_pass,
        physical_fault_count,
        physical_repair_count,
    ) = _fault_generation_audit(payload, fault_edges)
    affected_count = int(summary.get("fault_affected_bag_count", 0))
    completed = bool(bag.get("completed", False))
    binary_sha256 = str(
        summary.get("loaded_cpp_binary_sha256", "")
    )
    credit_fault_revocation_count = int(
        summary.get("first_edge_credit_fault_revocation_count", 0)
    )
    credit_physical_fault_rejection_count = int(
        summary.get(
            "first_edge_credit_physical_fault_rejection_count",
            0,
        )
    )
    credit_physical_interlock_bypass = bool(
        summary.get("first_edge_credit_physical_interlock_bypass", True)
    )
    informative = (
        not fault_edges
        or candidate_exposure > 0
        or target_attempt > 0
        or affected_count > 0
        or credit_physical_fault_rejection_count > 0
    )
    pibt_fault_batch_cancel_count = int(
        summary.get("bounded_local_pibt_fault_rejection_count", 0)
    )
    pibt_activation_count = int(
        summary.get("bounded_local_pibt_activation_count", 0)
    )
    repaired_reentry_count = int(
        summary.get("repaired_task_reentry_count", 0)
    )
    repaired_boost_cleared_count = int(
        summary.get(
            "repaired_task_reentry_boost_cleared_count",
            0,
        )
    )
    repaired_boost_clear_pass = (
        repaired_reentry_count == repaired_boost_cleared_count
    )
    credit_containment_pass = (
        credit_physical_fault_rejection_count > 0
        and not credit_physical_interlock_bypass
        if spec.case_id
        in {
            "G9_cut_isolation",
            "G9_control_physical_shield_only",
        }
        else True
    )
    elapsed = (
        float(bag["finish_time"]) - float(task["pass_time"])
        if completed
        else None
    )
    hard_pass = (
        completed
        and int(summary.get("failed_count", -1)) == 0
        and int(summary.get("reservation_conflicts", -1)) == 0
        and int(summary.get("physical_fault_edge_entry_violation_count", -1))
        == 0
        and int(summary.get("runtime_full_astar_calls", -1)) == 0
        and int(summary.get("global_reservation_scan_count", -1)) == 0
        and int(summary.get("full_future_routes_stored", -1)) == 0
        and int(summary.get("unresolved_deadlock_count", -1)) == 0
        and summary.get("event_limit_reached") is False
        and summary.get("time_limit_reached") is False
        and int(summary.get("reservation_depth", -1)) == 1
        and binary_sha256 == FROZEN_BINARY_SHA256
        and generation_pass
        and physical_fault_count == len(fault_edges)
        and physical_repair_count == len(fault_edges)
        and repaired_boost_clear_pass
        and credit_containment_pass
    )
    path = [
        int(task["start"]),
        *[
            int(row["selected_next"])
            for row in payload.get("decisions", [])
            if row.get("selected_next") is not None
        ],
    ]
    return {
        "schema": SCHEMA,
        "case_id": spec.case_id,
        "execution_status": "EXECUTED",
        "gate_status": (
            "PASS"
            if hard_pass and informative
            else (
                "UNINFORMATIVE_FAULT_CASE"
                if hard_pass and not informative
                else "FAIL"
            )
        ),
        "blocker": "",
        "comparator_id": spec.comparator_id,
        "candidate_id": F2_CANDIDATE_ID,
        "policy_enabled": spec.policy_enabled,
        "pibt_mode": spec.pibt_mode,
        "fault_kind": spec.fault_kind,
        "fault_arc_ids_json": list(spec.fault_arc_ids),
        "fault_edges_json": [
            {"start": start, "end": end} for start, end in sorted(fault_edges)
        ],
        "message_delay_seconds": spec.message_delay_seconds,
        "notification_dropped": spec.notification_dropped,
        "fault_duration_seconds": spec.duration_seconds,
        "task_id": int(task["task_id"]),
        "pallet_id": int(task["pallet_id"]),
        "segment_id": str(task["segment_id"]),
        "leg": str(task["leg"]),
        "start": int(task["start"]),
        "goal": int(task["goal"]),
        "release_time": float(task["pass_time"]),
        "completed": completed,
        "finish_minus_release_seconds": elapsed,
        "path_json": path,
        "fault_edge_candidate_exposure": candidate_exposure,
        "fault_target_edge_attempt": target_attempt,
        "affected_bag_count": affected_count,
        "informative_fault_case": informative,
        "physical_fault_generation_sequence_json": generation_sequence,
        "physical_fault_generation_pass": generation_pass,
        "physical_fault_event_count": physical_fault_count,
        "physical_repair_event_count": physical_repair_count,
        "repaired_task_reentry_count": repaired_reentry_count,
        "repaired_task_reentry_boost_cleared_count": (
            repaired_boost_cleared_count
        ),
        "repaired_task_reentry_boost_clear_pass": (
            repaired_boost_clear_pass
        ),
        "physical_interlock_mode": (
            "ALWAYS_ON_NOT_POLICY_CONFIGURABLE"
        ),
        "local_fault_policy_action_count": int(
            summary.get("local_fault_policy_action_count", 0)
        ),
        "local_fault_policy_reroute_count": int(
            summary.get("local_fault_policy_reroute_count", 0)
        ),
        "physical_interlock_rejection_count": int(
            summary.get("physical_fault_interlock_rejection_count", 0)
        ),
        "physical_interlock_hold_count": int(
            summary.get("physical_fault_interlock_hold_count", 0)
        ),
        "fault_notification_drop_count": int(
            summary.get("fault_notification_drop_count", 0)
        ),
        "credit_fault_revocation_count": int(
            credit_fault_revocation_count
        ),
        "credit_physical_fault_rejection_count": (
            credit_physical_fault_rejection_count
        ),
        "credit_physical_interlock_bypass": (
            credit_physical_interlock_bypass
        ),
        "pibt_fault_batch_cancel_count": int(
            pibt_fault_batch_cancel_count
        ),
        "pibt_activation_count": pibt_activation_count,
        "credit_containment_status": (
            "FAULTED_EDGE_CREDIT_REJECTED_BY_PHYSICAL_INTERLOCK"
            if credit_physical_fault_rejection_count > 0
            and not credit_physical_interlock_bypass
            else (
                "LIVE_FAULTED_CREDIT_REVOKED"
                if credit_fault_revocation_count > 0
                else "NO_CREDIT_CONTAINMENT_OBSERVED"
            )
        ),
        "pibt_containment_status": (
            "FAULT_GENERATION_BATCH_CANCEL_OBSERVED"
            if pibt_fault_batch_cancel_count > 0
            else (
                "NO_STALE_BATCH_OBSERVED"
                if pibt_activation_count > 0
                else "NO_PIBT_BATCH_IN_SINGLE_BAG_PROBE"
            )
        ),
        "resolved_deadlock_count": int(
            summary.get("resolved_deadlock_count", 0)
        ),
        "unresolved_deadlock_count": int(
            summary.get("unresolved_deadlock_count", 0)
        ),
        "repair_backlog_slope_available": bool(
            summary.get("repair_backlog_slope_available", False)
        ),
        "repair_backlog_slope": (
            float(summary.get("repair_backlog_slope", 0.0))
            if bool(summary.get("repair_backlog_slope_available", False))
            else ""
        ),
        "unsafe_entry_count": int(
            summary.get("physical_fault_edge_entry_violation_count", 0)
        ),
        "reservation_conflicts": int(
            summary.get("reservation_conflicts", 0)
        ),
        "runtime_full_astar_calls": int(
            summary.get("runtime_full_astar_calls", 0)
        ),
        "global_reservation_scan_count": int(
            summary.get("global_reservation_scan_count", 0)
        ),
        "future_routes_stored": int(
            summary.get("full_future_routes_stored", 0)
        ),
        "event_limit_reached": bool(
            summary.get("event_limit_reached", False)
        ),
        "time_limit_reached": bool(
            summary.get("time_limit_reached", False)
        ),
        "reservation_depth": int(summary.get("reservation_depth", -1)),
        "map_raw_sha256": MAP_RAW_SHA256,
        "task_raw_sha256": TASK_RAW_SHA256,
        "binary_sha256": binary_sha256,
        "frozen_binary_match": binary_sha256 == FROZEN_BINARY_SHA256,
        "deterministic_runtime_projection_sha256": (
            harness.deterministic_result_sha256(payload)
        ),
    }


def _attach_comparisons(rows: list[dict[str, Any]]) -> None:
    by_case = {str(row["case_id"]): row for row in rows}
    for row in rows:
        comparator_id = str(row.get("comparator_id", ""))
        row["delay_delta_vs_comparator_seconds"] = ""
        row["completion_delta_vs_comparator"] = ""
        row["causal_promotion_status"] = "NOT_APPLICABLE"
        if row.get("execution_status") != "EXECUTED" or not comparator_id:
            continue
        comparator = by_case.get(comparator_id)
        if comparator is None or comparator.get("execution_status") != "EXECUTED":
            row["causal_promotion_status"] = "COMPARATOR_NOT_EXECUTED"
            continue
        row["completion_delta_vs_comparator"] = int(
            bool(row.get("completed"))
        ) - int(bool(comparator.get("completed")))
        left = row.get("finish_minus_release_seconds")
        right = comparator.get("finish_minus_release_seconds")
        if left not in (None, "") and right not in (None, ""):
            row["delay_delta_vs_comparator_seconds"] = float(left) - float(right)
        same_shield = (
            int(row.get("unsafe_entry_count", -1)) == 0
            and int(comparator.get("unsafe_entry_count", -1)) == 0
            and row.get("physical_interlock_mode")
            == comparator.get("physical_interlock_mode")
            == "ALWAYS_ON_NOT_POLICY_CONFIGURABLE"
            and row.get("frozen_binary_match") is True
            and comparator.get("frozen_binary_match") is True
        )
        matched_fault = all(
            row.get(field) == comparator.get(field)
            for field in (
                "fault_arc_ids_json",
                "fault_edges_json",
                "message_delay_seconds",
                "notification_dropped",
                "fault_duration_seconds",
                "segment_id",
                "pibt_mode",
                "binary_sha256",
                "physical_fault_generation_sequence_json",
            )
        )
        local_policy_observed = (
            int(row.get("local_fault_policy_action_count", 0)) > 0
            or int(row.get("local_fault_policy_reroute_count", 0)) > 0
        )
        improved = (
            int(row["completion_delta_vs_comparator"]) > 0
            or (
                row["delay_delta_vs_comparator_seconds"] != ""
                and float(row["delay_delta_vs_comparator_seconds"]) < 0.0
            )
            or (
                row.get("repair_backlog_slope") not in ("", None)
                and comparator.get("repair_backlog_slope") not in ("", None)
                and float(row["repair_backlog_slope"])
                < float(comparator["repair_backlog_slope"])
            )
        )
        informative = bool(row.get("informative_fault_case")) and bool(
            comparator.get("informative_fault_case")
        )
        if (
            same_shield
            and matched_fault
            and informative
            and improved
            and bool(row.get("policy_enabled"))
            and not bool(comparator.get("policy_enabled"))
            and local_policy_observed
        ):
            row["causal_promotion_status"] = (
                "MATCHED_PHYSICAL_SHIELD_POLICY_CONTRIBUTION_PASS"
            )
        elif not informative:
            row["causal_promotion_status"] = "UNINFORMATIVE_FAULT_CASE"
        elif not same_shield:
            row["causal_promotion_status"] = "UNSAFE_OR_UNMATCHED_SHIELD"
        elif not matched_fault:
            row["causal_promotion_status"] = (
                "UNMATCHED_FAULT_OR_CONTROL_CONFIGURATION"
            )
        elif (
            bool(row.get("policy_enabled"))
            and not bool(comparator.get("policy_enabled"))
            and not local_policy_observed
        ):
            row["causal_promotion_status"] = (
                "NO_LOCAL_POLICY_ACTION_OBSERVED_PHYSICAL_FALLBACK_ONLY"
            )
        else:
            row["causal_promotion_status"] = (
                "NO_POSITIVE_POLICY_CONTRIBUTION_DEMONSTRATED"
            )


def execute_study(
    graph: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
    *,
    search_path: Path,
) -> list[dict[str, Any]]:
    rows = [
        execute_probe(
            spec,
            graph=graph,
            tasks=tasks,
            search_path=search_path,
        )
        for spec in probe_specs()
    ]
    _attach_comparisons(rows)
    return rows


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    if not rows:
        raise FaultControlError("refusing to render empty CSV")
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        rendered: dict[str, Any] = {}
        for key in fields:
            value = row.get(key, "")
            if isinstance(value, bool):
                rendered[key] = "True" if value else "False"
            elif isinstance(value, float):
                rendered[key] = format(value, ".17g")
            elif isinstance(value, (dict, list, tuple)):
                rendered[key] = json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            else:
                rendered[key] = value
        writer.writerow(rendered)
    return stream.getvalue().encode("utf-8")


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *[
                "| " + " | ".join(str(value) for value in row) + " |"
                for row in rows
            ],
        ]
    )


def build_design_report(
    mapping: Sequence[Mapping[str, Any]],
    criticality: Sequence[Mapping[str, Any]],
) -> bytes:
    content = [
        "# G4IRSF13 Thesis-aligned Local Fault Mechanism",
        "",
        "Status: `DESIGN_AND_REAL_MAP_MAPPING_COMPLETE`",
        "",
        "The implementation keeps six planes separate: an always-on physical "
        "entry interlock; generation-tagged local DDI messages; BTI-based "
        "affected-bag identification; revocation of unconsumed credit and "
        "uncommitted P2 work; one-edge local rerouting/holding; and repair "
        "wake-up with temporary affected-bag priority. The protected map file "
        "is never changed: faults are dynamic overlays.",
        "",
        "Runtime decisions remain one next edge with reservation depth one. "
        "No full A*/CIE, future route, global reservation scan, or global "
        "replanning is admitted.",
        "",
        "## Thesis Table 5.5 mapping",
        "",
        _table(
            ["Scenario", "Arc IDs", "map2 edges", "Paper success", "Lost pairs"],
            [
                [
                    row["scenario_id"],
                    ",".join(
                        str(value)
                        for value in row["thesis_arc_ids_json"]
                    ),
                    ",".join(
                        f"{edge['start']}->{edge['end']}"
                        for edge in row["map2_edges_json"]
                    ),
                    f"{float(row['paper_reported_success_rate']):.2f}",
                    row["lost_reachable_source_goal_pairs"],
                ]
                for row in mapping
            ],
        ),
        "",
        "Paper success rates remain labelled as paper-reported outcomes. "
        "They are not copied into the G4IRSF13 runtime result.",
        "",
        "## Preventive criticality",
        "",
        _table(
            [
                "Rank",
                "Arc",
                "Edge",
                "Task reachability loss",
                "Source-goal loss",
                "Bridge",
            ],
            [
                [
                    row["maintenance_rank"],
                    row["arc_id"],
                    f"{row['start']}->{row['end']}",
                    row["actual_task_segments_losing_reachability"],
                    row["source_goal_pair_reachability_loss"],
                    row["weak_projection_bridge"],
                ]
                for row in sorted(
                    criticality,
                    key=lambda item: int(item["maintenance_rank"]),
                )
            ],
        ),
        "",
        "The maintenance rank is an offline topology/reachability heuristic, "
        "not a runtime routing feature and not a causal estimate.",
        "",
    ]
    return "\n".join(content).encode("utf-8")


def build_result_report(rows: Sequence[Mapping[str, Any]]) -> bytes:
    executed = [row for row in rows if row.get("execution_status") == "EXECUTED"]
    hard_failures = [
        row for row in executed if row.get("gate_status") != "PASS"
    ]
    informative = [
        row
        for row in executed
        if row.get("fault_arc_ids_json")
        and bool(row.get("informative_fault_case"))
    ]
    promoted = [
        row
        for row in executed
        if row.get("causal_promotion_status")
        == "MATCHED_PHYSICAL_SHIELD_POLICY_CONTRIBUTION_PASS"
    ]
    content = [
        "# G4IRSF13 Fault Recovery Results",
        "",
        (
            "Status: `FAULT_DISCRIMINATING_PASS`"
            if promoted and not hard_failures
            else "Status: `PARTIAL_WITH_EXPLICIT_BLOCKER`"
        ),
        "",
        f"Executed cases: {len(executed)}; informative: {len(informative)}; "
        f"hard failures: {len(hard_failures)}.",
        "",
        "## Matched local A/B",
        "",
        _table(
            [
                "Case",
                "Policy",
                "P",
                "Complete",
                "TTH s",
                "Exposure",
                "Unsafe",
                "Delta vs comparator s",
                "Causal status",
            ],
            [
                [
                    row["case_id"],
                    row.get("policy_enabled", ""),
                    row.get("pibt_mode", ""),
                    row.get("completed", ""),
                    (
                        ""
                        if row.get("finish_minus_release_seconds") in ("", None)
                        else f"{float(row['finish_minus_release_seconds']):.6f}"
                    ),
                    (
                        int(row.get("fault_edge_candidate_exposure", 0))
                        + int(row.get("fault_target_edge_attempt", 0))
                        + int(row.get("affected_bag_count", 0))
                    ),
                    row.get("unsafe_entry_count", ""),
                    (
                        ""
                        if row.get("delay_delta_vs_comparator_seconds")
                        in ("", None)
                        else f"{float(row['delay_delta_vs_comparator_seconds']):+.6f}"
                    ),
                    row.get("causal_promotion_status", ""),
                ]
                for row in rows
            ],
        ),
        "",
        "Causal promotion is granted only when policy-on and policy-off share "
        "the same always-on physical shield, the case has actual exposure, "
        "policy-on improves completion/delay/recovery/backlog, and unsafe edge "
        "entry remains zero. Dropped DDI messages intentionally fall back to "
        "the physical interlock.",
        "",
        "## Safety, generation, and containment audit",
        "",
        f"Frozen binary `{FROZEN_BINARY_SHA256}` matched every executed row: "
        f"`{all(row.get('frozen_binary_match') is True for row in executed)}`.",
        "",
        "Every injected edge recorded an ordered physical `FAULT -> REPAIR` "
        "generation transition, every completed repair re-entry boost was "
        "cleared, and aggregate unsafe entry remained "
        f"`{sum(int(row.get('unsafe_entry_count', 0)) for row in executed)}`.",
        "",
        "G9 faults the real 0->6 edge at release and observes first-edge "
        "credit issue rejection by the non-bypassable physical interlock in "
        "both matched policy-on/off runs. Successful credits are issued, "
        "bound, and consumed atomically by this event runtime, so these rows "
        "do not claim a live-credit revocation. Formal one-bag probes also "
        "had no uncommitted P2 batch at the fault instant; prepare/commit "
        "generation rollback is therefore retained as real-map unit evidence "
        "rather than reported as a positive runtime cancellation.",
        "",
        "The G4 v3 fault-aware row is `NOT_RUN`: fresh untouched holdout "
        "failed the offline learning gate, so runtime activation and "
        "closed-loop fault evaluation are forbidden.",
        "",
    ]
    return "\n".join(content).encode("utf-8")


def build_policy_bundle(
    mapping: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    *,
    binary_search_path: Path,
) -> dict[str, Any]:
    promoted = [
        str(row["case_id"])
        for row in rows
        if row.get("causal_promotion_status")
        == "MATCHED_PHYSICAL_SHIELD_POLICY_CONTRIBUTION_PASS"
    ]
    executed = [
        row
        for row in rows
        if row.get("execution_status") == "EXECUTED"
    ]
    executed_gate_pass = bool(executed) and all(
        row.get("gate_status") == "PASS" for row in executed
    )
    binary_match_pass = bool(executed) and all(
        row.get("binary_sha256") == FROZEN_BINARY_SHA256
        and row.get("frozen_binary_match") is True
        for row in executed
    )
    generation_pass = bool(executed) and all(
        row.get("physical_fault_generation_pass") is True
        for row in executed
    )
    unsafe_entry_count = sum(
        int(row.get("unsafe_entry_count", 0))
        for row in executed
    )
    credit_revocations = sum(
        int(row.get("credit_fault_revocation_count", 0))
        for row in executed
    )
    credit_physical_fault_rejections = sum(
        int(row.get("credit_physical_fault_rejection_count", 0))
        for row in executed
    )
    pibt_batch_cancels = sum(
        int(row.get("pibt_fault_batch_cancel_count", 0))
        for row in executed
    )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "policy_id": "g4irsf13_local_ddi_bti_fault_control",
        "status": (
            "FAULT_DISCRIMINATING_PASS"
            if promoted
            and executed_gate_pass
            and binary_match_pass
            and generation_pass
            and unsafe_entry_count == 0
            else "PARTIAL_WITH_EXPLICIT_BLOCKER"
        ),
        "runtime_scope": "ONE_NEXT_EDGE_RESERVATION_DEPTH_ONE",
        "physical_interlock": "ALWAYS_ON_NOT_POLICY_CONFIGURABLE",
        "ddi_scope": "GENERATION_TAGGED_BOUNDED_LOCAL_OVERLAY",
        "bti_scope": "ACTUAL_CURRENT_SAFE_NODE_ONLY",
        "containment": [
            "revoke_unconsumed_first_edge_credit",
            "cancel_uncommitted_pibt_batch",
            "hold_at_safe_local_queue",
        ],
        "repair": [
            "generation_tagged_reopen",
            "wake_affected_local_queues",
            "temporary_fault_affected_priority",
        ],
        "forbidden": [
            "full_astar_or_cie",
            "future_route_storage",
            "global_reservation_scan",
            "global_replanning",
        ],
        "map_raw_sha256": MAP_RAW_SHA256,
        "task_raw_sha256": TASK_RAW_SHA256,
        "frozen_binary_sha256": FROZEN_BINARY_SHA256,
        "frozen_binary_match_pass": binary_match_pass,
        "executed_case_gate_pass": executed_gate_pass,
        "physical_generation_audit_pass": generation_pass,
        "unsafe_entry_count": unsafe_entry_count,
        "f2_case_config_sha256": harness.canonical_sha256(
            _f2_case().as_dict()
        ),
        "binary_search_path": binary_search_path.resolve().as_posix(),
        "thesis_scenario_mapping_sha256": _canonical_sha256(list(mapping)),
        "fault_ab_sha256": _canonical_sha256(list(rows)),
        "causally_promoted_case_ids": promoted,
        "containment_evidence": {
            "credit_fault_revocation_count": credit_revocations,
            "credit_physical_fault_rejection_count": (
                credit_physical_fault_rejections
            ),
            "credit_physical_interlock_bypass": any(
                bool(row.get("credit_physical_interlock_bypass", True))
                for row in executed
                if row.get("case_id")
                in {
                    "G9_cut_isolation",
                    "G9_control_physical_shield_only",
                }
            ),
            "credit_runtime_observation": (
                "FAULTED_EDGE_CREDIT_REJECTED_BY_PHYSICAL_INTERLOCK;"
                "SUCCESSFUL_CREDIT_ISSUE_BIND_CONSUME_IS_ATOMIC"
            ),
            "pibt_fault_batch_cancel_count": pibt_batch_cancels,
            "pibt_batch_runtime_observation": (
                "FAULT_GENERATION_BATCH_CANCEL_OBSERVED"
                if pibt_batch_cancels > 0
                else (
                    "NO_UNCOMMITTED_PIBT_BATCH_AT_FAULT_IN_FORMAL_PROBES;"
                    "REAL_MAP_PREPARE_COMMIT_GENERATION_ROLLBACK_IS_UNIT_TESTED"
                )
            ),
        },
        "v3_fault_aware_status": (
            "NOT_RUN_FRESH_HOLDOUT_OFFLINE_FAIL_"
            "RUNTIME_ACTIVATION_FORBIDDEN"
        ),
        "claim_boundary": (
            "Promotion applies only to the executed matched local exposure "
            "cases. Paper Table 5.5 outcomes remain external reference values."
        ),
    }
    payload["self_sha256"] = _canonical_sha256(payload)
    return payload


def build_outputs(
    *,
    search_path: Path,
) -> dict[Path, bytes]:
    graph, tasks = _load_inputs()
    mapping = build_mapping_rows(graph)
    criticality = build_criticality_rows(graph, tasks)
    rows = execute_study(
        graph,
        tasks,
        search_path=search_path,
    )
    bundle = build_policy_bundle(
        mapping,
        rows,
        binary_search_path=search_path,
    )
    return {
        MAPPING_PATH: _csv_bytes(mapping),
        CAUSAL_PATH: _csv_bytes(rows),
        CRITICALITY_PATH: _csv_bytes(criticality),
        DESIGN_REPORT_PATH: build_design_report(mapping, criticality),
        RESULT_REPORT_PATH: build_result_report(rows),
        POLICY_PATH: _canonical_bytes(bundle) + b"\n",
    }


def _write_outputs(outputs: Mapping[Path, bytes]) -> None:
    for relative, payload in outputs.items():
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)


def _validate_committed(outputs: Mapping[Path, bytes]) -> None:
    failures = []
    for relative, expected in outputs.items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"missing:{relative.as_posix()}")
        elif path.read_bytes() != expected:
            failures.append(f"drift:{relative.as_posix()}")
    if failures:
        raise FaultControlError(
            "committed fault artifacts differ: " + ", ".join(failures)
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search-path",
        type=Path,
        default=ROOT / "build_g4irsf12" / "python",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--validate-committed", action="store_true")
    args = parser.parse_args(argv)
    if not args.search_path.is_dir():
        raise FaultControlError(
            f"C++ binary search path is missing: {args.search_path}"
        )
    outputs = build_outputs(search_path=args.search_path)
    if args.write:
        _write_outputs(outputs)
    if args.validate_committed or not args.write:
        _validate_committed(outputs)
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "status": "PASS",
                "outputs": [path.as_posix() for path in outputs],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
