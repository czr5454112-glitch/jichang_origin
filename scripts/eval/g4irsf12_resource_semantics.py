"""Static resource-semantics evidence for the fixed real-map event runtime.

This module deliberately does not execute a routing policy.  It provides the
fail-closed topology and source-code evidence needed before any G4IRSF12
resource-semantics A/B is allowed to run.  In particular, an unmeasured
headway is represented as ``None`` and can never become a promoted physical
constant merely because one sensitivity run is fast.
"""

from __future__ import annotations

from collections import defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_RELATIVE_PATH,
    CANONICAL_MAP_SHA256,
    canonical_map_data,
    normalised_text_sha256,
    raw_bytes_sha256,
)


ROOT = Path(__file__).resolve().parents[2]
RESOURCE_CONFIG_DIR = Path("artifacts/configs/g4irsf12_resource_semantics")

DIRECTED_CORRIDOR_TABLE = Path(
    "outputs/tables/g4irsf12_directed_corridor_audit.csv"
)
MERGE_INVENTORY_TABLE = Path("outputs/tables/g4irsf12_merge_inventory.csv")
RESOURCE_AB_TABLE = Path("outputs/tables/g4irsf12_resource_semantics_ab.csv")
RESOURCE_AUDIT_REPORT = Path(
    "outputs/reports/g4irsf12_resource_semantics_audit.md"
)
BUFFER_BOUNDARY_REPORT = Path(
    "outputs/reports/g4irsf12_buffer_semantics_boundary.md"
)

LEGACY_SOURCE_PATHS = {
    "astar": Path("legacy/jichang_origin_readonly/src/App/Astar.java"),
    "ics": Path("legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java"),
    "map": Path("legacy/jichang_origin_readonly/src/App/Map.java"),
    "tasks": Path("legacy/jichang_origin_readonly/src/App/Tasks.java"),
}
EVENT_RUNTIME_PATH = Path("cpp/ics_core/runtime/event_driven_junction.hpp")

RESOURCE_MODE_SCHEMA = "czr005.g4irsf12.resource_semantics_config.v1"
RESOURCE_MANIFEST_SCHEMA = "czr005.g4irsf12.resource_semantics_manifest.v1"
AUDIT_SCHEMA = "czr005.g4irsf12.resource_semantics_static_audit.v1"


def _normalised_sha256(path: Path) -> str:
    payload = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _line_number(path: Path, needle: str) -> int:
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if needle in line:
            return line_number
    raise ValueError(f"required evidence token {needle!r} is missing from {path}")


def _line_number_any(path: Path, needles: Sequence[str]) -> int:
    text = path.read_text(encoding="utf-8").splitlines()
    for needle in needles:
        for line_number, line in enumerate(text, start=1):
            if needle in line:
                return line_number
    raise ValueError(
        f"none of the required evidence tokens {list(needles)!r} is present in {path}"
    )


def _strongly_connected_components(
    nodes: Sequence[int], adjacency: Mapping[int, Sequence[int]]
) -> list[tuple[int, ...]]:
    """Return deterministic Tarjan SCCs, ordered by their smallest node."""

    index = 0
    indices: dict[int, int] = {}
    lowlinks: dict[int, int] = {}
    stack: list[int] = []
    on_stack: set[int] = set()
    components: list[tuple[int, ...]] = []

    def visit(node: int) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for successor in sorted(adjacency.get(node, ())):
            if successor not in indices:
                visit(successor)
                lowlinks[node] = min(lowlinks[node], lowlinks[successor])
            elif successor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[successor])

        if lowlinks[node] != indices[node]:
            return
        component: list[int] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(tuple(sorted(component)))

    for node in sorted(nodes):
        if node not in indices:
            visit(node)
    return sorted(components, key=lambda component: (component[0], len(component), component))


def _weak_projection_analysis(
    nodes: Sequence[int], edges: Iterable[tuple[int, int]]
) -> tuple[list[tuple[int, ...]], set[int], set[tuple[int, int]]]:
    """Compute weak components, articulation points and bridges.

    Articulation/bridge terminology is ambiguous for directed graphs.  The
    audit therefore computes those two properties only on the explicitly
    labelled undirected weak projection while retaining SCCs for direction.
    """

    adjacency: dict[int, set[int]] = {node: set() for node in nodes}
    for start, end in edges:
        adjacency[start].add(end)
        adjacency[end].add(start)

    seen: set[int] = set()
    weak_components: list[tuple[int, ...]] = []
    for root in sorted(nodes):
        if root in seen:
            continue
        pending = [root]
        component: list[int] = []
        seen.add(root)
        while pending:
            node = pending.pop()
            component.append(node)
            for neighbour in sorted(adjacency[node], reverse=True):
                if neighbour not in seen:
                    seen.add(neighbour)
                    pending.append(neighbour)
        weak_components.append(tuple(sorted(component)))

    discovery: dict[int, int] = {}
    low: dict[int, int] = {}
    parent: dict[int, int | None] = {}
    articulations: set[int] = set()
    bridges: set[tuple[int, int]] = set()
    clock = 0

    def dfs(node: int) -> None:
        nonlocal clock
        discovery[node] = clock
        low[node] = clock
        clock += 1
        child_count = 0
        for neighbour in sorted(adjacency[node]):
            if neighbour not in discovery:
                parent[neighbour] = node
                child_count += 1
                dfs(neighbour)
                low[node] = min(low[node], low[neighbour])
                if parent[node] is None and child_count > 1:
                    articulations.add(node)
                if parent[node] is not None and low[neighbour] >= discovery[node]:
                    articulations.add(node)
                if low[neighbour] > discovery[node]:
                    bridges.add((min(node, neighbour), max(node, neighbour)))
            elif neighbour != parent[node]:
                low[node] = min(low[node], discovery[neighbour])

    for root in sorted(nodes):
        if root in discovery:
            continue
        parent[root] = None
        dfs(root)

    return sorted(weak_components), articulations, bridges


def _node_role(node_type: int) -> str:
    return {
        1: "source",
        2: "goal",
        4: "declared_split",
        5: "declared_merge",
    }.get(node_type, f"type_{node_type}")


def build_topology_audit() -> dict[str, Any]:
    """Audit every directed edge and every node of the protected map2."""

    data = canonical_map_data()
    nodes_by_id = {int(row["location"]): dict(row) for row in data["nodes"]}
    node_ids = sorted(nodes_by_id)
    edge_rows = [dict(row) for row in data["edges"]]
    edge_pairs = [(int(row["start"]), int(row["end"])) for row in edge_rows]
    edge_set = set(edge_pairs)
    if len(edge_pairs) != len(edge_set):
        raise ValueError("canonical map contains duplicate directed edges")

    outgoing: dict[int, list[int]] = {node: [] for node in node_ids}
    incoming: dict[int, list[int]] = {node: [] for node in node_ids}
    for start, end in edge_pairs:
        if start not in nodes_by_id or end not in nodes_by_id:
            raise ValueError(f"edge {start}->{end} references a missing node")
        outgoing[start].append(end)
        incoming[end].append(start)
    for values in outgoing.values():
        values.sort()
    for values in incoming.values():
        values.sort()

    sccs = _strongly_connected_components(node_ids, outgoing)
    scc_by_node: dict[int, tuple[str, int]] = {}
    for index, component in enumerate(sccs):
        scc_id = f"SCC{index:03d}"
        for node in component:
            scc_by_node[node] = (scc_id, len(component))

    weak_components, articulations, bridges = _weak_projection_analysis(
        node_ids, edge_pairs
    )
    weak_by_node: dict[int, tuple[str, int]] = {}
    for index, component in enumerate(weak_components):
        component_id = f"WCC{index:03d}"
        for node in component:
            weak_by_node[node] = (component_id, len(component))

    corridor_members: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for start, end in edge_pairs:
        corridor_members[(min(start, end), max(start, end))].append((start, end))
    for members in corridor_members.values():
        members.sort()

    directed_rows: list[dict[str, Any]] = []
    for source in sorted(edge_rows, key=lambda row: (int(row["start"]), int(row["end"]))):
        start = int(source["start"])
        end = int(source["end"])
        length = float(source["length"])
        speed = float(source["speed"])
        travel_time = float(source.get("travel_time", length / speed))
        if abs(travel_time - length / speed) > 1.0e-9:
            raise ValueError(f"edge {start}->{end} travel_time disagrees with length/speed")
        key = (min(start, end), max(start, end))
        members = corridor_members[key]
        reverse_exists = (end, start) in edge_set
        directed_rows.append(
            {
                "start": start,
                "end": end,
                "directed_edge": f"{start}->{end}",
                "length": length,
                "speed": speed,
                "travel_time": travel_time,
                "start_node_type": int(nodes_by_id[start]["node_type"]),
                "start_node_role": _node_role(int(nodes_by_id[start]["node_type"])),
                "end_node_type": int(nodes_by_id[end]["node_type"]),
                "end_node_role": _node_role(int(nodes_by_id[end]["node_type"])),
                "start_out_degree": len(outgoing[start]),
                "end_in_degree": len(incoming[end]),
                "is_split_exit": len(outgoing[start]) > 1,
                "is_merge_entry": len(incoming[end]) > 1,
                "reverse_edge_exists": reverse_exists,
                "reverse_directed_edge": f"{end}->{start}" if reverse_exists else "",
                "current_undirected_corridor_key": f"{key[0]}<->{key[1]}",
                "current_corridor_directed_member_count": len(members),
                "current_corridor_directed_members": ";".join(
                    f"{left}->{right}" for left, right in members
                ),
                "current_cross_direction_calendar_share": reverse_exists,
                "direction_aliasing_audit": (
                    "WRONG_DIRECTIONAL_SHARING_CANDIDATE"
                    if reverse_exists
                    else "NO_REVERSE_EDGE_TO_ALIAS"
                ),
                "weak_projection_bridge": key in bridges,
                "start_weak_projection_articulation": start in articulations,
                "end_weak_projection_articulation": end in articulations,
                "start_scc_id": scc_by_node[start][0],
                "start_scc_size": scc_by_node[start][1],
                "end_scc_id": scc_by_node[end][0],
                "end_scc_size": scc_by_node[end][1],
                "weak_component_id": weak_by_node[start][0],
            }
        )

    node_rows: list[dict[str, Any]] = []
    for node in node_ids:
        source = nodes_by_id[node]
        incident_bridges = sum(
            (min(node, neighbour), max(node, neighbour)) in bridges
            for neighbour in set(incoming[node]) | set(outgoing[node])
        )
        node_rows.append(
            {
                "node": node,
                "node_type": int(source["node_type"]),
                "declared_role": _node_role(int(source["node_type"])),
                "service_time": float(source.get("service_time", 0.0)),
                "x": int(source.get("x", 0)),
                "y": int(source.get("y", 0)),
                "in_degree": len(incoming[node]),
                "out_degree": len(outgoing[node]),
                "incoming_nodes": ";".join(str(value) for value in incoming[node]),
                "outgoing_nodes": ";".join(str(value) for value in outgoing[node]),
                "topological_merge": len(incoming[node]) > 1,
                "topological_split": len(outgoing[node]) > 1,
                "declared_merge_matches_topology": (
                    int(source["node_type"]) != 5 or len(incoming[node]) > 1
                ),
                "declared_split_matches_topology": (
                    int(source["node_type"]) != 4 or len(outgoing[node]) > 1
                ),
                "scc_id": scc_by_node[node][0],
                "scc_size": scc_by_node[node][1],
                "weak_component_id": weak_by_node[node][0],
                "weak_component_size": weak_by_node[node][1],
                "weak_projection_articulation": node in articulations,
                "incident_weak_projection_bridge_count": incident_bridges,
                "is_source": int(source["node_type"]) == 1,
                "is_goal": int(source["node_type"]) == 2,
            }
        )

    reverse_pairs = sorted(
        key for key, members in corridor_members.items() if len(members) > 1
    )
    summary = {
        "node_count": len(node_ids),
        "directed_edge_count": len(edge_pairs),
        "undirected_corridor_key_count": len(corridor_members),
        "reverse_pair_count": len(reverse_pairs),
        "directed_edges_aliased_by_reverse_pair_count": 2 * len(reverse_pairs),
        "direction_aliasing_present_on_fixed_map": bool(reverse_pairs),
        "topological_merge_count": sum(len(incoming[node]) > 1 for node in node_ids),
        "topological_split_count": sum(len(outgoing[node]) > 1 for node in node_ids),
        "declared_merge_node_count": sum(
            int(nodes_by_id[node]["node_type"]) == 5 for node in node_ids
        ),
        "declared_split_node_count": sum(
            int(nodes_by_id[node]["node_type"]) == 4 for node in node_ids
        ),
        "directed_scc_count": len(sccs),
        "nontrivial_directed_scc_count": sum(len(component) > 1 for component in sccs),
        "largest_directed_scc_size": max(map(len, sccs)),
        "weak_component_count": len(weak_components),
        "weak_projection_articulation_count": len(articulations),
        "weak_projection_bridge_count": len(bridges),
    }
    return {
        "summary": summary,
        "directed_corridors": directed_rows,
        "nodes": node_rows,
        "reverse_pairs": [
            {
                "corridor_key": f"{left}<->{right}",
                "forward": f"{left}->{right}",
                "reverse": f"{right}->{left}",
            }
            for left, right in reverse_pairs
        ],
        "sccs": [list(component) for component in sccs],
        "weak_components": [list(component) for component in weak_components],
        "weak_projection_articulations": sorted(articulations),
        "weak_projection_bridges": [list(pair) for pair in sorted(bridges)],
    }


def build_source_evidence(repository_root: Path = ROOT) -> dict[str, Any]:
    """Extract review anchors from protected legacy and current-runtime sources."""

    root = repository_root.resolve()
    resolved = {name: root / path for name, path in LEGACY_SOURCE_PATHS.items()}
    runtime = root / EVENT_RUNTIME_PATH
    required_paths = [*resolved.values(), runtime]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("required resource-semantics sources missing: " + ", ".join(missing))
    runtime_text = runtime.read_text(encoding="utf-8")
    runtime_has_resource_ladder = (
        "double corridor_reservation_duration(double travel_time) const" in runtime_text
    )

    anchors = {
        "legacy_map_directed_adjacency": {
            "path": LEGACY_SOURCE_PATHS["map"].as_posix(),
            "line": _line_number(resolved["map"], "for (int i=5;i<line.length;i++)"),
            "evidence": "Map.N stores each node's listed outgoing neighbours.",
        },
        "legacy_map_directed_edge_start": {
            "path": LEGACY_SOURCE_PATHS["map"].as_posix(),
            "line": _line_number(resolved["map"], "edge.setStar(Integer.valueOf(line[0]))"),
            "evidence": "The first edge endpoint is parsed as directed start.",
        },
        "legacy_astar_directed_edge_lookup": {
            "path": LEGACY_SOURCE_PATHS["astar"].as_posix(),
            "line": _line_number(
                resolved["astar"], "findEdge(currNode.getLocation(), i, map)"
            ),
            "evidence": "A* looks up the exact current-to-next directed edge.",
        },
        "legacy_astar_travel_then_node_service": {
            "path": LEGACY_SOURCE_PATHS["astar"].as_posix(),
            "line": _line_number(
                resolved["astar"], "double t1=currNode.t2+edge.length/edge.v"
            ),
            "evidence": "Travel advances arrival time; the destination service interval follows.",
        },
        "legacy_astar_node_window_conflict": {
            "path": LEGACY_SOURCE_PATHS["astar"].as_posix(),
            "line": _line_number(
                resolved["astar"], "constrain_Set.containsKey(i)&&i!=goal.location"
            ),
            "evidence": "Conflict checks index destination-node windows and exempt the goal.",
        },
        "legacy_constraint_is_node_interval": {
            "path": LEGACY_SOURCE_PATHS["ics"].as_posix(),
            "line": _line_number(resolved["ics"], "constrain.add(n.t1)"),
            "evidence": "update_constrain records task, arrival and departure per path node.",
        },
        "legacy_source_single_unfinished_per_start": {
            "path": LEGACY_SOURCE_PATHS["tasks"].as_posix(),
            "line": _line_number(
                resolved["tasks"],
                "!contains(ics_pf.getUnfinishTasks(),ics_pf.getMap().star.get(i).getLocation())",
            ),
            "evidence": "Task generation gates a source when an unfinished task already uses it.",
        },
        "current_runtime_undirected_corridor_key": {
            "path": EVENT_RUNTIME_PATH.as_posix(),
            "line": _line_number(runtime, "inline long long corridor_key"),
            "evidence": "The current runtime canonicalises both directions to min/max.",
        },
        "current_runtime_corridor_reservation_duration": {
            "path": EVENT_RUNTIME_PATH.as_posix(),
            "line": _line_number_any(
                runtime,
                (
                    "double corridor_reservation_duration(double travel_time) const",
                    "corridor.reserve(bag.request.runtime_bag_id, time, exit_time)",
                ),
            ),
            "evidence": (
                "The runtime selects full-travel versus entry-headway reservation "
                "duration from the declared resource mode."
                if runtime_has_resource_ladder
                else "R0 reserves the selected corridor for the complete travel interval."
            ),
        },
        "current_runtime_destination_service_calendar": {
            "path": EVENT_RUNTIME_PATH.as_posix(),
            "line": _line_number(
                runtime,
                "target.service_calendar.reserve(bag.request.runtime_bag_id",
            ),
            "evidence": "The destination service interval is reserved separately.",
        },
        "current_runtime_unbounded_queue_default": {
            "path": EVENT_RUNTIME_PATH.as_posix(),
            "line": _line_number(runtime, "int local_queue_capacity = 0"),
            "evidence": "Zero is explicitly documented as no configured local queue cap.",
        },
    }

    source_files = []
    for path in sorted(required_paths):
        source_files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "normalised_text_sha256": _normalised_sha256(path),
            }
        )

    declared_modes = [
        mode_id
        for mode_id in (
            "R0_current_undirected_full_travel_exclusive",
            "R1_directed_full_travel_exclusive",
            "R2_directed_entry_headway",
            "R3_java_node_window_compatible",
            "R4_directed_headway_plus_merge_service_calendar",
        )
        if mode_id in runtime_text
    ]

    return {
        "anchors": anchors,
        "source_files": source_files,
        "conclusions": {
            "legacy_reviewed_graph_is_directed": True,
            "legacy_reviewed_conflict_resource": "node_arrival_departure_windows",
            "legacy_reviewed_edge_capacity_one_implemented": False,
            "legacy_reviewed_full_travel_edge_exclusivity_implemented": False,
            "legacy_reviewed_reverse_pair_calendar_merge_implemented": False,
            "legacy_goal_node_window_exemption_observed": True,
            "authoritative_edge_entry_headway_seconds": None,
            "headway_status": "UNKNOWN_REQUIRES_EVIDENCE_OR_SENSITIVITY_ONLY",
            "current_runtime_resource_semantics_id": (
                "R0_current_undirected_full_travel_exclusive"
            ),
            "current_runtime_declared_resource_modes": declared_modes,
            "current_runtime_declares_full_r0_r4_ladder": len(declared_modes) == 5,
            "physical_buffer_capacity_proven_by_reviewed_sources": False,
        },
    }


def resource_mode_configs() -> list[dict[str, Any]]:
    """Return the predeclared R0--R4 configuration ladder.

    R2 and R4 intentionally have a null headway and are not executable as
    physical-evidence cases.  A later sensitivity runner must bind an explicit
    labelled value without rewriting these base declarations.
    """

    common = {
        "schema": RESOURCE_MODE_SCHEMA,
        "map_semantic_sha256": CANONICAL_MAP_SHA256,
        "reservation_depth": 1,
        "runtime_full_astar_allowed": False,
        "global_reservation_scan_allowed": False,
        "physical_fault_interlock_required": True,
    }
    modes = [
        {
            **common,
            "resource_semantics_id": "R0_current_undirected_full_travel_exclusive",
            "short_id": "R0",
            "edge_directionality": "undirected_minmax_corridor_alias",
            "edge_occupancy": "exclusive_full_travel_interval",
            "edge_capacity": 1,
            "entry_headway_seconds": None,
            "destination_node_window": "exclusive_service_interval",
            "merge_service_calendar": "destination_node_calendar_only",
            "evidence_role": "negative_control_current_implementation",
            "execution_readiness": "READY_AS_NEGATIVE_CONTROL",
            "promotion_eligible": False,
        },
        {
            **common,
            "resource_semantics_id": "R1_directed_full_travel_exclusive",
            "short_id": "R1",
            "edge_directionality": "directed",
            "edge_occupancy": "exclusive_full_travel_interval",
            "edge_capacity": 1,
            "entry_headway_seconds": None,
            "destination_node_window": "exclusive_service_interval",
            "merge_service_calendar": "destination_node_calendar_only",
            "evidence_role": "directionality_isolation",
            "execution_readiness": "DECLARED_FOR_CONTROLLED_AB_NOT_EXECUTED",
            "promotion_eligible": False,
        },
        {
            **common,
            "resource_semantics_id": "R2_directed_entry_headway",
            "short_id": "R2",
            "edge_directionality": "directed",
            "edge_occupancy": "entry_headway_only_multiple_inflight_allowed",
            "edge_capacity": None,
            "entry_headway_seconds": None,
            "destination_node_window": "exclusive_service_interval",
            "merge_service_calendar": "destination_node_calendar_only",
            "evidence_role": "headway_sensitivity",
            "execution_readiness": "REQUIRES_EXPLICIT_SENSITIVITY_HEADWAY_BEFORE_EXECUTION",
            "promotion_eligible": False,
        },
        {
            **common,
            "resource_semantics_id": "R3_java_node_window_compatible",
            "short_id": "R3",
            "edge_directionality": "directed_topology_no_edge_calendar_in_reviewed_java_path",
            "edge_occupancy": "travel_time_without_reviewed_edge_exclusivity",
            "edge_capacity": None,
            "entry_headway_seconds": None,
            "destination_node_window": "java_arrival_departure_window_goal_exempt",
            "merge_service_calendar": "shared_destination_node_window",
            "evidence_role": "legacy_semantics_diagnostic_not_physical_capacity_claim",
            "execution_readiness": "DECLARED_FOR_CONTROLLED_AB_NOT_EXECUTED",
            "promotion_eligible": False,
        },
        {
            **common,
            "resource_semantics_id": "R4_directed_headway_plus_merge_service_calendar",
            "short_id": "R4",
            "edge_directionality": "directed",
            "edge_occupancy": "entry_headway_only_multiple_inflight_allowed",
            "edge_capacity": None,
            "entry_headway_seconds": None,
            "destination_node_window": "exclusive_service_interval",
            "merge_service_calendar": "explicit_destination_conditioned_merge_calendar",
            "evidence_role": "engineering_candidate_after_headway_and_buffer_evidence",
            "execution_readiness": "REQUIRES_EXPLICIT_SENSITIVITY_HEADWAY_BEFORE_EXECUTION",
            "promotion_eligible": False,
        },
    ]
    return modes


def build_static_audit(repository_root: Path = ROOT) -> dict[str, Any]:
    topology = build_topology_audit()
    source_evidence = build_source_evidence(repository_root)
    map_path = ROOT / CANONICAL_MAP_RELATIVE_PATH
    return {
        "schema": AUDIT_SCHEMA,
        "status": "STATIC_EVIDENCE_COMPLETE_RUNTIME_AB_NOT_EXECUTED",
        "map_identity": {
            "path": CANONICAL_MAP_RELATIVE_PATH.as_posix(),
            "raw_sha256": raw_bytes_sha256(map_path),
            "semantic_sha256": normalised_text_sha256(map_path),
            "expected_semantic_sha256": CANONICAL_MAP_SHA256,
            "topology_mutation_allowed": False,
        },
        "topology": topology,
        "source_evidence": source_evidence,
        "resource_modes": resource_mode_configs(),
        "claim_boundary": {
            "runtime_ab_executed": False,
            "headway_calibrated": False,
            "buffer_capacity_calibrated": False,
            "fastest_mode_may_be_promoted": False,
            "next_allowed_ladder": [144, 512, 2048],
            "best_two_only_after_static_review": 8192,
            "full_43603_allowed": False,
        },
    }


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    def value(item: Any) -> str:
        return str(item).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(value(item) for item in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(value(item) for item in row) + " |" for row in rows)
    return "\n".join(lines)


def render_resource_audit_report(audit: Mapping[str, Any]) -> str:
    identity = audit["map_identity"]
    topology = audit["topology"]
    summary = topology["summary"]
    source = audit["source_evidence"]
    conclusions = source["conclusions"]
    anchors = source["anchors"]

    source_rows = [
        (
            name,
            f"{row['path']}:{row['line']}",
            row["evidence"],
        )
        for name, row in sorted(anchors.items())
    ]
    mode_rows = [
        (
            mode["short_id"],
            mode["resource_semantics_id"],
            mode["edge_directionality"],
            mode["edge_occupancy"],
            mode["entry_headway_seconds"],
            mode["execution_readiness"],
        )
        for mode in audit["resource_modes"]
    ]
    reverse_rows = [
        (row["corridor_key"], row["forward"], row["reverse"])
        for row in topology["reverse_pairs"]
    ]
    if not reverse_rows:
        reverse_rows = [("none", "", "")]
    if summary["reverse_pair_count"]:
        aliasing_finding = (
            f"The current min/max key aliases `{summary['reverse_pair_count']}` real reverse "
            f"pairs, affecting `{summary['directed_edges_aliased_by_reverse_pair_count']}` "
            "directed edge rows. This is real cross-direction sharing in R0, but it does "
            "not by itself establish a safe physical headway for R2/R4."
        )
    else:
        aliasing_finding = (
            "The protected map contains no reverse edge pair. The current min/max key "
            "therefore aliases zero real directed-edge calendars on this topology, so an "
            "R0-versus-R1 runtime delta is not expected from directionality alone. The "
            "full-travel exclusivity question remains separate."
        )

    return "\n".join(
        [
            "# G4IRSF12 Resource Semantics Audit",
            "",
            f"Status: `{audit['status']}`.",
            "",
            "This is a static topology/source audit. It does not claim that R1--R4 "
            "have been implemented, executed, or promoted.",
            "",
            "## Fixed evidence identity",
            "",
            _markdown_table(
                ["Field", "Value"],
                [
                    ("map", identity["path"]),
                    ("raw SHA-256", identity["raw_sha256"]),
                    ("semantic SHA-256", identity["semantic_sha256"]),
                    ("topology mutation", identity["topology_mutation_allowed"]),
                ],
            ),
            "",
            "## Static topology",
            "",
            _markdown_table(
                ["Measure", "Count"],
                [(name, value) for name, value in summary.items()],
            ),
            "",
            "Articulation points and bridges are computed on the explicitly labelled "
            "undirected weak projection. Directional structure is reported separately "
            "through strongly connected components.",
            "",
            "### Reverse directions currently sharing one corridor calendar",
            "",
            _markdown_table(["Current key", "Direction A", "Direction B"], reverse_rows),
            "",
            aliasing_finding,
            "",
            "## Reviewed source evidence",
            "",
            _markdown_table(["Evidence", "Location", "Meaning"], source_rows),
            "",
            "## Legacy semantics answers",
            "",
            "1. **Edge capacity=1:** not implemented by the reviewed Java planning "
            "constraint path. This is not proof that the physical conveyor has unlimited capacity.",
            "2. **Full-travel edge exclusivity:** not implemented by that reviewed path; "
            "travel advances time between node windows.",
            "3. **Reverse-pair merging:** not observed. Map adjacency and edge lookup are directed.",
            "4. **Primary conflict object:** node arrival/departure windows; the goal is exempt "
            "in `Astar.research`.",
            "5. **Special handling:** the goal-window exemption and a source gate for one "
            "unfinished task per start are explicit. No authoritative physical merge-buffer "
            "capacity was found in the reviewed files.",
            "6. **Minimum carrier headway:** not extractable from the reviewed code. It remains "
            "unknown and any R2/R4 value must be labelled sensitivity-only until sourced.",
            "",
            "## Predeclared R0--R4 ladder",
            "",
            _markdown_table(
                ["ID", "Semantics", "Direction", "Occupancy", "Headway s", "Readiness"],
                mode_rows,
            ),
            "",
            f"Reviewed Java conflict resource: `{conclusions['legacy_reviewed_conflict_resource']}`. "
            f"Authoritative entry headway: `{conclusions['authoritative_edge_entry_headway_seconds']}`.",
            "",
            "R0 is the existing negative control. R1/R3 are declared controlled A/B modes; "
            "R2/R4 additionally require an explicit sensitivity-only headway binding. This "
            "static audit does not establish build/runtime readiness for any new mode. Execute "
            "144/512/2048 first and validate the runtime echo. No static result authorizes "
            "43,603-segment full execution.",
            "",
        ]
    )


def render_buffer_boundary_report(audit: Mapping[str, Any]) -> str:
    anchors = audit["source_evidence"]["anchors"]
    queue_anchor = anchors["current_runtime_unbounded_queue_default"]
    source_anchor = anchors["legacy_source_single_unfinished_per_start"]
    return "\n".join(
        [
            "# G4IRSF12 Buffer Semantics Boundary",
            "",
            "Status: `PHYSICAL_BUFFER_CAPACITY_NOT_ESTABLISHED`.",
            "",
            "The fixed map contains node type, service time, coordinates and directed "
            "outgoing edges. It does not declare a queue/buffer capacity per node.",
            "",
            f"The current event runtime default at `{queue_anchor['path']}:{queue_anchor['line']}` "
            "uses `local_queue_capacity = 0`, explicitly meaning no configured cap. Therefore "
            "a conflict-free run under that setting is not evidence that a physical waiting "
            "location can hold the observed queue.",
            "",
            f"The reviewed Java task generator at `{source_anchor['path']}:{source_anchor['line']}` "
            "gates new work when a start already has an unfinished task. This is an observed "
            "source-generation rule, not an authoritative capacity for every source, merge, "
            "diverter, EBS, or destination buffer.",
            "",
            "## Required boundary for later A/B",
            "",
            "- Keep unknown capacities explicit; do not substitute a convenient finite value.",
            "- Report source queue, admitted network queue, scheduled incoming, and service "
            "calendar occupancy separately.",
            "- Treat `capacity=0` as unbounded configuration, never zero physical spaces.",
            "- Bind any finite capacity to an authoritative project source and a source hash.",
            "- Until then, R2/R4 headway and buffer values are sensitivity-only and cannot "
            "support a physical-capacity or throughput-optimality claim.",
            "",
        ]
    )


def resource_ab_rows(audit: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mode in audit["resource_modes"]:
        rows.append(
            {
                "resource_semantics_id": mode["resource_semantics_id"],
                "short_id": mode["short_id"],
                "edge_directionality": mode["edge_directionality"],
                "edge_occupancy": mode["edge_occupancy"],
                "edge_capacity": mode["edge_capacity"],
                "entry_headway_seconds": mode["entry_headway_seconds"],
                "destination_node_window": mode["destination_node_window"],
                "merge_service_calendar": mode["merge_service_calendar"],
                "evidence_role": mode["evidence_role"],
                "execution_readiness": mode["execution_readiness"],
                "execution_status": "NOT_EXECUTED_STATIC_CONFIGURATION_ONLY",
                "segments_requested": "",
                "segments_completed": "",
                "capacity_pass": "",
                "promotion_eligible": mode["promotion_eligible"],
                "claim_boundary": (
                    "No runtime comparison; null headway is not a physical value."
                ),
            }
        )
    return rows


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        raise ValueError("refusing to write a headerless empty CSV")
    fieldnames = list(rows[0])
    if any(list(row) != fieldnames for row in rows):
        raise ValueError("CSV rows must use one deterministic field order")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: (
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (list, dict))
                    else value
                )
                for key, value in row.items()
            }
        )
    return buffer.getvalue()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def write_resource_semantics_artifacts(
    audit: Mapping[str, Any], output_root: Path = ROOT
) -> dict[str, Any]:
    """Write deterministic static evidence and return a publication manifest."""

    destination = output_root.resolve()
    written: list[Path] = []

    table_payloads = {
        DIRECTED_CORRIDOR_TABLE: _csv_text(audit["topology"]["directed_corridors"]),
        MERGE_INVENTORY_TABLE: _csv_text(audit["topology"]["nodes"]),
        RESOURCE_AB_TABLE: _csv_text(resource_ab_rows(audit)),
    }
    report_payloads = {
        RESOURCE_AUDIT_REPORT: render_resource_audit_report(audit),
        BUFFER_BOUNDARY_REPORT: render_buffer_boundary_report(audit),
    }
    for relative, payload in {**table_payloads, **report_payloads}.items():
        path = destination / relative
        _atomic_write_text(path, payload)
        written.append(relative)

    config_bindings: list[dict[str, Any]] = []
    for mode in audit["resource_modes"]:
        filename = f"{str(mode['short_id']).lower()}_{mode['resource_semantics_id'][3:]}.json"
        relative = RESOURCE_CONFIG_DIR / filename
        payload = _json_text(mode)
        _atomic_write_text(destination / relative, payload)
        written.append(relative)
        config_bindings.append(
            {
                "resource_semantics_id": mode["resource_semantics_id"],
                "path": relative.as_posix(),
                "sha256": _sha256_bytes(payload.encode("utf-8")),
                "execution_readiness": mode["execution_readiness"],
            }
        )

    manifest = {
        "schema": RESOURCE_MANIFEST_SCHEMA,
        "status": audit["status"],
        "map_identity": audit["map_identity"],
        "source_files": audit["source_evidence"]["source_files"],
        "configs": config_bindings,
        "static_outputs": [path.as_posix() for path in written],
        "runtime_ab_executed": False,
        "protected_inputs_modified": False,
    }
    manifest_relative = RESOURCE_CONFIG_DIR / "manifest.json"
    _atomic_write_text(destination / manifest_relative, _json_text(manifest))
    written.append(manifest_relative)
    manifest["manifest_path"] = manifest_relative.as_posix()
    manifest["written_paths"] = [path.as_posix() for path in written]
    return manifest


__all__ = [
    "AUDIT_SCHEMA",
    "BUFFER_BOUNDARY_REPORT",
    "DIRECTED_CORRIDOR_TABLE",
    "MERGE_INVENTORY_TABLE",
    "RESOURCE_AB_TABLE",
    "RESOURCE_AUDIT_REPORT",
    "RESOURCE_CONFIG_DIR",
    "build_source_evidence",
    "build_static_audit",
    "build_topology_audit",
    "render_buffer_boundary_report",
    "render_resource_audit_report",
    "resource_ab_rows",
    "resource_mode_configs",
    "write_resource_semantics_artifacts",
]
