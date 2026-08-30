#!/usr/bin/env python3
"""Map-profile adapter for the model-free S4/J2/E2 runtime.

This module only loads a graph profile and constructs a native runtime request.
It does not execute a campaign, mutate G26--G30 artifacts, or write a report.
The service-aware potential is precomputed once; each live S4 decision still
examines only the current node's direct outgoing neighbours.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import g4irsf14_opportunity_census as g14
from scripts.eval import run_g4irsf28_service_potential as g28


NodeRecord = tuple[int, int, float, int, int, tuple[int, ...]]
EdgeRecord = tuple[int, int, float, float]

PORTABLE_MAP_SCHEMA = "czr005.g4irsf32.portable_map_profile.v1"

# G31 models physical junction service through the R3 service calendar and
# E4/J2 grants.  It does not impose an additional software bag-count cap.
G31_LOCAL_QUEUE_CAPACITY = 0


class MapProfileError(ValueError):
    """Raised when a map profile cannot satisfy the native graph contract."""


@dataclass(frozen=True)
class RuntimeStoragePair:
    pair_id: str
    storage_in_goal: int
    storage_out_start: int


@dataclass(frozen=True)
class RuntimeMapProfile:
    name: str
    source_path: Path
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    start_nodes: tuple[int, ...]
    goal_nodes: tuple[int, ...]
    storage_source_nodes: tuple[int, ...]
    schema: str = ""
    map_id: str = ""
    external_node_ids: tuple[str, ...] = ()
    explicit_roles: bool = False
    storage_mode: str = "legacy"
    storage_pairs: tuple[RuntimeStoragePair, ...] = ()


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MapProfileError(f"{label} must be an integer")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MapProfileError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise MapProfileError(f"{label} must be finite")
    return result


def _role_nodes(
    raw: Any,
    *,
    label: str,
    node_ids: set[int],
) -> tuple[int, ...]:
    if not isinstance(raw, (list, tuple)):
        raise MapProfileError(f"{label} must be a list of node IDs")
    values = tuple(_integer(value, f"{label}[]") for value in raw)
    if len(set(values)) != len(values):
        raise MapProfileError(f"{label} must not contain duplicates")
    missing = sorted(set(values) - node_ids)
    if missing:
        raise MapProfileError(f"{label} references unknown nodes: {missing}")
    return tuple(sorted(values))


def _external_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise MapProfileError(f"{label} must be a non-empty string")
    return value


def _external_role_ids(
    raw: Any,
    *,
    label: str,
    node_ids: set[str],
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise MapProfileError(f"{label} must be a list of external node IDs")
    values = tuple(
        _external_id(value, f"{label}[]") for value in raw
    )
    if len(set(values)) != len(values):
        raise MapProfileError(f"{label} must not contain duplicates")
    missing = sorted(set(values) - node_ids)
    if missing:
        raise MapProfileError(f"{label} references unknown nodes: {missing}")
    return values


def _load_portable_map_profile(
    path: Path,
    payload: Mapping[str, Any],
) -> RuntimeMapProfile:
    """Load the normalized third-map boundary without guessing business roles."""

    map_id = _external_id(payload.get("map_id"), "map_id")
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise MapProfileError("map profile nodes must be a non-empty list")
    if not isinstance(raw_edges, list):
        raise MapProfileError("map profile edges must be a list")

    parsed_nodes: dict[str, tuple[int, float, int, int, tuple[str, ...]]] = {}
    for index, raw_node in enumerate(raw_nodes):
        if not isinstance(raw_node, Mapping):
            raise MapProfileError(f"nodes[{index}] must be an object")
        external = _external_id(
            raw_node.get("external_id"), f"nodes[{index}].external_id"
        )
        if external in parsed_nodes:
            raise MapProfileError(f"duplicate external node ID: {external}")
        node_type = _integer(
            raw_node.get("node_type"), f"nodes[{index}].node_type"
        )
        service = _finite(
            raw_node.get("service_time"), f"nodes[{index}].service_time"
        )
        if service < 0.0:
            raise MapProfileError("node service_time must be non-negative")
        x = _integer(raw_node.get("x", 0), f"nodes[{index}].x")
        y = _integer(raw_node.get("y", 0), f"nodes[{index}].y")
        raw_outgoing = raw_node.get("outgoing", [])
        if not isinstance(raw_outgoing, list):
            raise MapProfileError(f"nodes[{index}].outgoing must be a list")
        outgoing = tuple(
            _external_id(value, f"nodes[{index}].outgoing[]")
            for value in raw_outgoing
        )
        if len(set(outgoing)) != len(outgoing):
            raise MapProfileError(f"nodes[{index}].outgoing contains duplicates")
        parsed_nodes[external] = (node_type, service, x, y, outgoing)

    # Lexical external-ID order makes the remap independent of source row order.
    external_ids = tuple(sorted(parsed_nodes))
    external_to_dense = {
        external: dense for dense, external in enumerate(external_ids)
    }
    node_ids = set(external_ids)

    parsed_edges: list[EdgeRecord] = []
    external_edge_pairs: set[tuple[str, str]] = set()
    for index, raw_edge in enumerate(raw_edges):
        if not isinstance(raw_edge, Mapping):
            raise MapProfileError(f"edges[{index}] must be an object")
        start_external = _external_id(
            raw_edge.get("start"), f"edges[{index}].start"
        )
        end_external = _external_id(
            raw_edge.get("end"), f"edges[{index}].end"
        )
        if start_external not in node_ids or end_external not in node_ids:
            raise MapProfileError(f"edges[{index}] references an unknown node")
        length = _finite(raw_edge.get("length"), f"edges[{index}].length")
        speed = _finite(raw_edge.get("speed"), f"edges[{index}].speed")
        if length <= 0.0 or speed <= 0.0:
            raise MapProfileError("edge length and speed must be positive")
        pair = (start_external, end_external)
        if pair in external_edge_pairs:
            raise MapProfileError(f"duplicate directed edge: {pair}")
        external_edge_pairs.add(pair)
        parsed_edges.append(
            (
                external_to_dense[start_external],
                external_to_dense[end_external],
                length,
                speed,
            )
        )

    declared_pairs = {
        (external, target)
        for external, attributes in parsed_nodes.items()
        for target in attributes[4]
    }
    unknown_outgoing = sorted(
        target for _source, target in declared_pairs if target not in node_ids
    )
    if unknown_outgoing:
        raise MapProfileError(
            f"node outgoing lists reference unknown nodes: {unknown_outgoing}"
        )
    if declared_pairs != external_edge_pairs:
        raise MapProfileError("node outgoing lists and directed edge records differ")

    roles = payload.get("roles")
    if not isinstance(roles, Mapping):
        raise MapProfileError("portable map profile roles must be an object")
    sources_external = _external_role_ids(
        roles.get("source_nodes"),
        label="roles.source_nodes",
        node_ids=node_ids,
    )
    goals_external = _external_role_ids(
        roles.get("goal_nodes"),
        label="roles.goal_nodes",
        node_ids=node_ids,
    )
    if not sources_external or not goals_external:
        raise MapProfileError(
            "portable map profile must explicitly declare a source and goal"
        )

    raw_storage = roles.get("storage")
    if not isinstance(raw_storage, Mapping):
        raise MapProfileError("roles.storage must be an object")
    storage_mode = raw_storage.get("mode")
    if storage_mode not in {"none", "explicit_ebs"}:
        raise MapProfileError(
            "roles.storage.mode must be 'none' or 'explicit_ebs'"
        )
    raw_pairs = raw_storage.get("pairs", [])
    if not isinstance(raw_pairs, list):
        raise MapProfileError("roles.storage.pairs must be a list")
    if storage_mode == "none" and raw_pairs:
        raise MapProfileError("storage mode 'none' must not declare EBS pairs")
    if storage_mode == "explicit_ebs" and not raw_pairs:
        raise MapProfileError("storage mode 'explicit_ebs' requires a pair")

    storage_pairs: list[RuntimeStoragePair] = []
    pair_ids: set[str] = set()
    for index, raw_pair in enumerate(raw_pairs):
        if not isinstance(raw_pair, Mapping):
            raise MapProfileError(f"roles.storage.pairs[{index}] must be an object")
        pair_id = _external_id(
            raw_pair.get("pair_id"), f"roles.storage.pairs[{index}].pair_id"
        )
        if pair_id in pair_ids:
            raise MapProfileError(f"duplicate storage pair ID: {pair_id}")
        pair_ids.add(pair_id)
        storage_in_external = _external_id(
            raw_pair.get("storage_in_goal"),
            f"roles.storage.pairs[{index}].storage_in_goal",
        )
        storage_out_external = _external_id(
            raw_pair.get("storage_out_start"),
            f"roles.storage.pairs[{index}].storage_out_start",
        )
        missing = sorted(
            {storage_in_external, storage_out_external} - node_ids
        )
        if missing:
            raise MapProfileError(
                f"roles.storage.pairs[{index}] references unknown nodes: {missing}"
            )
        storage_pairs.append(
            RuntimeStoragePair(
                pair_id=pair_id,
                storage_in_goal=external_to_dense[storage_in_external],
                storage_out_start=external_to_dense[storage_out_external],
            )
        )

    node_records = tuple(
        (
            external_to_dense[external],
            parsed_nodes[external][0],
            parsed_nodes[external][1],
            parsed_nodes[external][2],
            parsed_nodes[external][3],
            tuple(
                external_to_dense[target]
                for target in parsed_nodes[external][4]
            ),
        )
        for external in external_ids
    )
    storage_source_nodes = tuple(
        sorted({pair.storage_out_start for pair in storage_pairs})
    )
    return RuntimeMapProfile(
        name=str(payload.get("name", map_id)),
        source_path=path,
        node_records=node_records,
        edge_records=tuple(sorted(parsed_edges)),
        start_nodes=tuple(
            sorted(external_to_dense[value] for value in sources_external)
        ),
        goal_nodes=tuple(
            sorted(external_to_dense[value] for value in goals_external)
        ),
        storage_source_nodes=storage_source_nodes,
        schema=PORTABLE_MAP_SCHEMA,
        map_id=map_id,
        external_node_ids=external_ids,
        explicit_roles=True,
        storage_mode=str(storage_mode),
        storage_pairs=tuple(storage_pairs),
    )


def load_map_profile(
    profile_path: str | Path,
    *,
    storage_source_nodes: Sequence[int] | None = None,
) -> RuntimeMapProfile:
    """Load a processed legacy-map-shaped JSON profile.

    The active native heuristic indexes nodes directly, so IDs must be dense
    ``0..N-1``.  Node/edge counts and semantic source IDs are otherwise taken
    from the profile rather than fixed to the original 54-node map.
    """

    path = Path(profile_path).resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MapProfileError(f"cannot load map profile {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise MapProfileError("map profile root must be an object")
    schema = payload.get("schema")
    if schema == PORTABLE_MAP_SCHEMA:
        if storage_source_nodes is not None:
            raise MapProfileError(
                "portable map storage roles cannot be overridden at load time"
            )
        return _load_portable_map_profile(path, payload)
    if isinstance(schema, str) and schema.startswith(
        "czr005.g4irsf32.portable_map_profile."
    ):
        raise MapProfileError(f"unsupported portable map schema: {schema}")
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise MapProfileError("map profile nodes must be a non-empty list")
    if not isinstance(raw_edges, list):
        raise MapProfileError("map profile edges must be a list")

    parsed_nodes: dict[int, tuple[int, float, int, int, tuple[int, ...]]] = {}
    for index, raw_node in enumerate(raw_nodes):
        if not isinstance(raw_node, Mapping):
            raise MapProfileError(f"nodes[{index}] must be an object")
        location = _integer(raw_node.get("location"), f"nodes[{index}].location")
        node_type = _integer(
            raw_node.get("node_type"), f"nodes[{index}].node_type"
        )
        service = _finite(
            raw_node.get("service_time"), f"nodes[{index}].service_time"
        )
        if service < 0.0:
            raise MapProfileError("node service_time must be non-negative")
        x = _integer(raw_node.get("x", 0), f"nodes[{index}].x")
        y = _integer(raw_node.get("y", 0), f"nodes[{index}].y")
        raw_outgoing = raw_node.get("outgoing", [])
        if not isinstance(raw_outgoing, list):
            raise MapProfileError(f"nodes[{index}].outgoing must be a list")
        outgoing = tuple(
            _integer(value, f"nodes[{index}].outgoing[]")
            for value in raw_outgoing
        )
        if len(set(outgoing)) != len(outgoing):
            raise MapProfileError(f"nodes[{index}].outgoing contains duplicates")
        if location in parsed_nodes:
            raise MapProfileError(f"duplicate node ID: {location}")
        parsed_nodes[location] = (node_type, service, x, y, outgoing)

    locations = sorted(parsed_nodes)
    if locations != list(range(len(locations))):
        raise MapProfileError("node IDs must be dense zero-based indices")
    node_ids = set(locations)

    parsed_edges: list[EdgeRecord] = []
    edge_pairs: set[tuple[int, int]] = set()
    for index, raw_edge in enumerate(raw_edges):
        if not isinstance(raw_edge, Mapping):
            raise MapProfileError(f"edges[{index}] must be an object")
        start = _integer(raw_edge.get("start"), f"edges[{index}].start")
        end = _integer(raw_edge.get("end"), f"edges[{index}].end")
        if start not in node_ids or end not in node_ids:
            raise MapProfileError(f"edges[{index}] references an unknown node")
        length = _finite(raw_edge.get("length"), f"edges[{index}].length")
        speed = _finite(raw_edge.get("speed"), f"edges[{index}].speed")
        if length <= 0.0 or speed <= 0.0:
            raise MapProfileError("edge length and speed must be positive")
        pair = (start, end)
        if pair in edge_pairs:
            raise MapProfileError(f"duplicate directed edge: {pair}")
        edge_pairs.add(pair)
        parsed_edges.append((start, end, length, speed))

    declared_pairs = {
        (location, target)
        for location, attributes in parsed_nodes.items()
        for target in attributes[4]
    }
    unknown_outgoing = sorted(
        target
        for _source, target in declared_pairs
        if target not in node_ids
    )
    if unknown_outgoing:
        raise MapProfileError(
            f"node outgoing lists reference unknown nodes: {unknown_outgoing}"
        )
    if declared_pairs != edge_pairs:
        raise MapProfileError("node outgoing lists and directed edge records differ")

    inferred_starts = [
        location
        for location, (node_type, *_rest) in parsed_nodes.items()
        if node_type == 1
    ]
    inferred_goals = [
        location
        for location, (node_type, *_rest) in parsed_nodes.items()
        if node_type == 2
    ]
    starts = _role_nodes(
        payload.get("start_nodes", inferred_starts),
        label="start_nodes",
        node_ids=node_ids,
    )
    goals = _role_nodes(
        payload.get("end_nodes", payload.get("goal_nodes", inferred_goals)),
        label="goal_nodes",
        node_ids=node_ids,
    )
    if not starts or not goals:
        raise MapProfileError("map profile must declare at least one start and goal")

    if storage_source_nodes is None:
        raw_storage = payload.get("storage_source_nodes")
        business_roles = payload.get("business_roles", {})
        if not isinstance(business_roles, Mapping):
            raise MapProfileError("business_roles must be an object")
        if raw_storage is None:
            raw_storage = business_roles.get("storage_source_nodes")
        if raw_storage is None:
            raw_storage = [52] if 52 in starts else []
    else:
        raw_storage = list(storage_source_nodes)
    storage = _role_nodes(
        raw_storage,
        label="storage_source_nodes",
        node_ids=node_ids,
    )
    node_records = tuple(
        (
            location,
            parsed_nodes[location][0],
            parsed_nodes[location][1],
            parsed_nodes[location][2],
            parsed_nodes[location][3],
            parsed_nodes[location][4],
        )
        for location in locations
    )
    return RuntimeMapProfile(
        name=str(payload.get("name", path.stem)),
        source_path=path,
        node_records=node_records,
        edge_records=tuple(sorted(parsed_edges)),
        start_nodes=starts,
        goal_nodes=goals,
        storage_source_nodes=storage,
        schema=str(schema or ""),
        map_id=str(payload.get("map_id", payload.get("name", path.stem))),
        external_node_ids=tuple(str(location) for location in locations),
    )


def build_s4_request(
    profile: RuntimeMapProfile,
    task_rows: Sequence[Mapping[str, Any]],
    *,
    binary: str | Path | None = None,
    scenario: str = "g4irsf31_map_adapter",
    max_events: int = 20_000_000,
    max_simulation_time: float = -1.0,
    trace_limit: int = 0,
    event_trace_limit: int = 0,
    summary_only: bool = False,
    edge_speed_mps: float | None = None,
    enable_s4_local_potential_descent_guard: bool = False,
    enable_s4_direct_neighbor_merge_calendar_visibility: bool = False,
    complete_on_goal_arrival: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Construct, but do not execute, an S4/J2/E2/FIFO native request."""

    if not task_rows:
        raise MapProfileError("task_rows must not be empty")
    if (
        isinstance(max_events, bool)
        or not isinstance(max_events, int)
        or max_events <= 0
    ):
        raise MapProfileError("max_events must be a positive integer")
    graph_nodes = {row[0] for row in profile.node_records}
    bag_records: list[tuple[str, int, float, float, int, int, str]] = []
    segment_ids: set[str] = set()
    for index, row in enumerate(task_rows):
        if not isinstance(row, Mapping):
            raise MapProfileError(f"task_rows[{index}] must be an object")
        segment_id = row.get("segment_id")
        if not isinstance(segment_id, str) or not segment_id:
            raise MapProfileError(
                f"task_rows[{index}].segment_id must be non-empty"
            )
        if segment_id in segment_ids:
            raise MapProfileError(f"duplicate segment_id: {segment_id}")
        segment_ids.add(segment_id)
        task_id = _integer(row.get("task_id"), f"task_rows[{index}].task_id")
        release = _finite(row.get("pass_time"), f"task_rows[{index}].pass_time")
        deadline = _finite(row.get("std"), f"task_rows[{index}].std")
        start = _integer(row.get("start"), f"task_rows[{index}].start")
        goal = _integer(row.get("goal"), f"task_rows[{index}].goal")
        if start not in graph_nodes or goal not in graph_nodes:
            raise MapProfileError(f"task_rows[{index}] references an unknown node")
        source = row.get("source")
        if source is None:
            source = (
                "storage"
                if start in profile.storage_source_nodes
                else f"node_{start}"
            )
        if not isinstance(source, str):
            raise MapProfileError(f"task_rows[{index}].source must be a string")
        bag_records.append(
            (segment_id, task_id, release, deadline, start, goal, source)
        )

    if edge_speed_mps is None:
        edge_records = profile.edge_records
    else:
        active_speed = _finite(edge_speed_mps, "edge_speed_mps")
        if active_speed <= 0.0:
            raise MapProfileError("edge_speed_mps must be positive")
        edge_records = tuple(
            (start, end, length, active_speed)
            for start, end, length, _profile_speed in profile.edge_records
        )
    minimum_service = float(
        g14.FROZEN_RUNTIME_CONTROLS["minimum_service_seconds"]
    )
    potential, potential_contract = g28.service_aware_potential(
        profile.node_records,
        edge_records,
        minimum_service_seconds=minimum_service,
    )
    request = dict(g14.FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=[
            (location, node_type, service, x, y, list(outgoing))
            for location, node_type, service, x, y, outgoing in profile.node_records
        ],
        edge_records=list(edge_records),
        heuristic_time=potential,
        bag_records=bag_records,
        fault_windows=(),
        queue_discipline="fifo",
        scorer_mode="S4_queue_aware_rule_only",
        merge_grant_rule="M3",
        merge_grant_timing_mode="jit_fair_aging_deadline",
        g4irsf20_event_hotpath_policy="E2",
        g4irsf16_supervisor_mode="off",
        local_queue_capacity=G31_LOCAL_QUEUE_CAPACITY,
        enable_opportunity_telemetry=False,
        opportunity_trace_limit=0,
        storage_source_nodes=list(profile.storage_source_nodes),
        enable_s4_local_potential_descent_guard=(
            enable_s4_local_potential_descent_guard
        ),
        enable_s4_direct_neighbor_merge_calendar_visibility=(
            enable_s4_direct_neighbor_merge_calendar_visibility
        ),
        complete_on_goal_arrival=complete_on_goal_arrival,
        scenario=scenario,
        max_events=max_events,
        max_simulation_time=float(max_simulation_time),
        trace_limit=trace_limit,
        event_trace_limit=event_trace_limit,
        summary_only=summary_only,
    )
    request.pop("scorer_model_path", None)
    request.pop("g4irsf24_dlp_artifact", None)
    if binary is not None:
        resolved_binary = Path(binary).resolve(strict=True)
        request["expected_binary_path"] = resolved_binary
        request["search_path"] = resolved_binary.parent
    return request, potential_contract
