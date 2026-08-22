#!/usr/bin/env python3
"""Convert the two Nanning topology workbooks into an auditable map profile.

The source workbooks are small OOXML files with a node sheet and a directed
adjacency sheet.  This adapter deliberately stays separate from G26--G30 and
the Java benchmark.  It preserves the workbook rows, gives every physical row
a dense runtime ID, and records the few assumptions required by the current
native and legacy-map interfaces.

The raw node identifier ``ICS156`` occurs once in each workbook with different
aliases and attributes.  By default the two rows remain distinct, keyed by
their workbook system.  An edge first resolves an identifier in its own
workbook; only an identifier absent there may resolve to a unique row in the
other workbook.  This also admits the five explicit cross-system edges without
silently merging the two ``ICS156`` devices.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import heapq
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[2]
WORKBOOK_NAMES = (
    ("international", "附件：拓扑结构示例1.xlsx"),
    ("domestic", "附件：拓扑结构示例2.xlsx"),
)
SCHEMA = "czr005.g4irsf31.nanning_map_profile.v1"
STATUS = "COMPLETE_WITH_DOCUMENTED_ASSUMPTIONS"

DEFAULT_PROFILE_OUTPUT = ROOT / "data/processed/maps/nanning_airport_profile.json"
DEFAULT_LEGACY_MAP_OUTPUT = ROOT / "data/processed/maps/nanning_legacy.txt"
LEGACY_HEURISTIC_BASE_SPEED_MPS = 2.5

# These three legacy header fields do not occur in the workbooks.  They are
# routing-only placeholders matching the existing no-fault benchmark format;
# the profile marks fault comparisons as blocked until the owner supplies a
# Nanning-specific fault threshold.
DEFAULT_AGV_LENGTH_METERS = 1.0
DEFAULT_SAFE_LENGTH_METERS = 0.0
DEFAULT_FAULT_THRESHOLD_SECONDS = 4.0

DOCUMENTED_NODE_TYPES: Mapping[int, str] = {
    1: "loader",
    2: "unloader",
    4: "divert",
    7: "empty_pallet_storage",
    11: "recode_station",
}
UNDOCUMENTED_NODE_TYPES = (5, 10, 12)

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF_RE = re.compile(r"([A-Z]+)([0-9]+)")


class NanningMapError(RuntimeError):
    """Raised when the two source tables cannot form one auditable graph."""


@dataclass(frozen=True)
class SourceNode:
    workbook_key: str
    workbook_name: str
    row_number: int
    alias: str
    raw_id: str
    system: str
    node_type: int
    source_service: float | None
    empty_pallet_storage_id: int | None

    @property
    def key(self) -> str:
        return f"{self.workbook_key}:{self.raw_id}"


@dataclass(frozen=True)
class SourceEdge:
    workbook_key: str
    workbook_name: str
    row_number: int
    raw_start: str
    raw_end: str
    length_m: float
    speed_mps: float
    system: str
    pallet_capacity: int


@dataclass(frozen=True)
class SourceWorkbook:
    key: str
    name: str
    nodes: tuple[SourceNode, ...]
    edges: tuple[SourceEdge, ...]
    node_range: str
    edge_range: str


def default_source_dir() -> Path:
    """Return the checked-out or adjacent user-provided source directory."""

    in_checkout = ROOT / "map_nanning"
    return in_checkout if in_checkout.is_dir() else ROOT.parent / "map_nanning"


def _column_index(reference: str) -> int:
    match = _CELL_REF_RE.fullmatch(reference)
    if match is None:
        raise NanningMapError(f"unsupported OOXML cell reference: {reference}")
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(item.itertext())
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    ]


def _sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        row.attrib["Id"]: row.attrib["Target"]
        for row in relationships.findall(f"{{{_PKG_REL_NS}}}Relationship")
    }
    result: dict[str, str] = {}
    for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
        relation_id = sheet.attrib[f"{{{_DOC_REL_NS}}}id"]
        target = targets[relation_id].lstrip("/")
        if not target.startswith("xl/"):
            target = str(PurePosixPath("xl") / target)
        result[sheet.attrib["name"]] = str(PurePosixPath(target))
    return result


def _cell_value(cell: ET.Element, shared: Sequence[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{_MAIN_NS}}}is")
        return "" if inline is None else "".join(inline.itertext())
    value = cell.find(f"{{{_MAIN_NS}}}v")
    if value is None or value.text is None:
        return None
    text = value.text
    if cell_type == "s":
        return shared[int(text)]
    if cell_type in {"str", "e"}:
        return text
    if cell_type == "b":
        return text == "1"
    number = float(text)
    return int(number) if number.is_integer() else number


def _sheet_rows(
    archive: zipfile.ZipFile,
    path: str,
    shared: Sequence[str],
) -> tuple[list[tuple[int, list[Any]]], str]:
    root = ET.fromstring(archive.read(path))
    dimension = root.find(f"{{{_MAIN_NS}}}dimension")
    used_range = dimension.attrib.get("ref", "") if dimension is not None else ""
    rows: list[tuple[int, list[Any]]] = []
    for row in root.findall(f".//{{{_MAIN_NS}}}row"):
        values: dict[int, Any] = {}
        for cell in row.findall(f"{{{_MAIN_NS}}}c"):
            reference = cell.attrib.get("r", "")
            values[_column_index(reference)] = _cell_value(cell, shared)
        if values:
            width = max(values) + 1
            rows.append(
                (int(row.attrib["r"]), [values.get(index) for index in range(width)])
            )
    return rows, used_range


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NanningMapError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise NanningMapError(f"{label} must be finite")
    return result


def _integer(value: Any, label: str) -> int:
    number = _number(value, label)
    if number != int(number):
        raise NanningMapError(f"{label} must be an integer")
    return int(number)


def load_source_workbook(path: Path, key: str) -> SourceWorkbook:
    """Read the two simple source sheets without an Excel dependency."""

    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive)
        sheets = _sheet_paths(archive)
        try:
            node_rows, node_range = _sheet_rows(
                archive, sheets["节点表"], shared
            )
            edge_rows, edge_range = _sheet_rows(
                archive, sheets["邻接表"], shared
            )
        except KeyError as exc:
            raise NanningMapError(f"{path.name} lacks 节点表 or 邻接表") from exc

    nodes: list[SourceNode] = []
    for row_number, row in node_rows[1:]:
        if len(row) < 2 or not _text(row[1]):
            continue
        service_cell = row[4] if len(row) > 4 else None
        source_service = (
            float(service_cell)
            if isinstance(service_cell, (int, float)) and not isinstance(service_cell, bool)
            else None
        )
        empty_cell = row[5] if len(row) > 5 else None
        empty_id = (
            _integer(empty_cell, f"{path.name} 节点表 F{row_number}")
            if isinstance(empty_cell, (int, float)) and not isinstance(empty_cell, bool)
            else None
        )
        nodes.append(
            SourceNode(
                workbook_key=key,
                workbook_name=path.name,
                row_number=row_number,
                alias=_text(row[0]),
                raw_id=_text(row[1]),
                system=_text(row[2] if len(row) > 2 else ""),
                node_type=_integer(row[3], f"{path.name} 节点表 D{row_number}"),
                source_service=source_service,
                empty_pallet_storage_id=empty_id,
            )
        )

    edges: list[SourceEdge] = []
    for row_number, row in edge_rows[1:]:
        if len(row) < 2 or not _text(row[0]) or not _text(row[1]):
            continue
        edges.append(
            SourceEdge(
                workbook_key=key,
                workbook_name=path.name,
                row_number=row_number,
                raw_start=_text(row[0]),
                raw_end=_text(row[1]),
                length_m=_number(row[2], f"{path.name} 邻接表 C{row_number}"),
                speed_mps=_number(row[3], f"{path.name} 邻接表 D{row_number}"),
                system=_text(row[4] if len(row) > 4 else ""),
                pallet_capacity=_integer(
                    row[5], f"{path.name} 邻接表 F{row_number}"
                ),
            )
        )
    return SourceWorkbook(
        key=key,
        name=path.name,
        nodes=tuple(nodes),
        edges=tuple(edges),
        node_range=node_range,
        edge_range=edge_range,
    )


def load_source_dir(source_dir: Path) -> tuple[SourceWorkbook, ...]:
    return tuple(
        load_source_workbook(source_dir / filename, key)
        for key, filename in WORKBOOK_NAMES
    )


def _service_seconds(node: SourceNode) -> tuple[float, str]:
    if node.source_service is not None:
        return node.source_service, "SOURCE_NUMERIC"
    if node.node_type in {7, 11}:
        return 0.0, "IMPUTED_ZERO_FROM_SAME_TYPES_IN_DOMESTIC_WORKBOOK"
    raise NanningMapError(
        f"no numeric service-time rule for {node.key} type {node.node_type}"
    )


def _role(node: SourceNode) -> list[str]:
    documented = DOCUMENTED_NODE_TYPES.get(node.node_type)
    if documented == "loader":
        return [documented, "bag_source_candidate"]
    if documented == "unloader":
        return [documented, "bag_sink_candidate"]
    if documented is not None:
        return [documented]
    return [f"undocumented_type_{node.node_type}", "transit_candidate"]


def _resolved_edges(
    sources: Sequence[SourceWorkbook],
) -> tuple[list[tuple[SourceEdge, str, str]], list[dict[str, Any]]]:
    local: dict[str, dict[str, str]] = {}
    global_rows: dict[str, list[str]] = defaultdict(list)
    for source in sources:
        current: dict[str, str] = {}
        for node in source.nodes:
            if node.raw_id in current:
                raise NanningMapError(
                    f"duplicate raw ID inside {source.name}: {node.raw_id}"
                )
            current[node.raw_id] = node.key
            global_rows[node.raw_id].append(node.key)
        local[source.key] = current

    resolved: list[tuple[SourceEdge, str, str]] = []
    external: list[dict[str, Any]] = []
    for source in sources:
        for edge in source.edges:
            endpoints: list[str] = []
            external_endpoint = False
            for raw_id in (edge.raw_start, edge.raw_end):
                if raw_id in local[source.key]:
                    endpoints.append(local[source.key][raw_id])
                    continue
                matches = global_rows.get(raw_id, [])
                if len(matches) != 1:
                    raise NanningMapError(
                        f"{source.name} 邻接表 row {edge.row_number} cannot uniquely "
                        f"resolve external node {raw_id}"
                    )
                endpoints.append(matches[0])
                external_endpoint = True
            resolved.append((edge, endpoints[0], endpoints[1]))
            if external_endpoint:
                external.append(
                    {
                        "workbook": source.name,
                        "row": edge.row_number,
                        "raw_start": edge.raw_start,
                        "raw_end": edge.raw_end,
                        "resolved_start_key": endpoints[0],
                        "resolved_end_key": endpoints[1],
                    }
                )
    return resolved, external


def _shortest_paths(
    node_count: int,
    edges: Sequence[Mapping[str, Any]],
    *,
    cost_field: str,
) -> list[list[float]]:
    adjacency: list[list[tuple[int, float]]] = [[] for _ in range(node_count)]
    for edge in edges:
        adjacency[int(edge["start"])].append(
            (int(edge["end"]), float(edge[cost_field]))
        )
    result: list[list[float]] = []
    for start in range(node_count):
        distances = [math.inf] * node_count
        distances[start] = 0.0
        queue: list[tuple[float, int]] = [(0.0, start)]
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            for target, cost in adjacency[node]:
                candidate = distance + cost
                if candidate < distances[target]:
                    distances[target] = candidate
                    heapq.heappush(queue, (candidate, target))
        result.append(distances)
    return result


def _component_counts(
    node_count: int, edges: Sequence[Mapping[str, Any]]
) -> tuple[int, int]:
    outgoing: list[list[int]] = [[] for _ in range(node_count)]
    undirected: list[set[int]] = [set() for _ in range(node_count)]
    for edge in edges:
        start, end = int(edge["start"]), int(edge["end"])
        outgoing[start].append(end)
        undirected[start].add(end)
        undirected[end].add(start)

    weak_count = 0
    seen: set[int] = set()
    for start in range(node_count):
        if start in seen:
            continue
        weak_count += 1
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            for neighbour in undirected[node]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)

    index = 0
    indices: dict[int, int] = {}
    low: dict[int, int] = {}
    stack: list[int] = []
    on_stack: set[int] = set()
    strong_count = 0

    def visit(node: int) -> None:
        nonlocal index, strong_count
        indices[node] = index
        low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for neighbour in outgoing[node]:
            if neighbour not in indices:
                visit(neighbour)
                low[node] = min(low[node], low[neighbour])
            elif neighbour in on_stack:
                low[node] = min(low[node], indices[neighbour])
        if low[node] == indices[node]:
            strong_count += 1
            while True:
                popped = stack.pop()
                on_stack.remove(popped)
                if popped == node:
                    break

    for node in range(node_count):
        if node not in indices:
            visit(node)
    return weak_count, strong_count


def build_profile_from_sources(
    sources: Sequence[SourceWorkbook],
    *,
    agv_length_m: float = DEFAULT_AGV_LENGTH_METERS,
    safe_length_m: float = DEFAULT_SAFE_LENGTH_METERS,
    fault_threshold_seconds: float = DEFAULT_FAULT_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    """Build the dense profile while retaining every source-row identity."""

    source_nodes = [node for source in sources for node in source.nodes]
    key_to_dense = {node.key: index for index, node in enumerate(source_nodes)}
    if len(key_to_dense) != len(source_nodes):
        raise NanningMapError("workbook-system node keys are not unique")

    raw_groups: dict[str, list[SourceNode]] = defaultdict(list)
    for node in source_nodes:
        raw_groups[node.raw_id].append(node)
    collisions = {
        raw_id: rows for raw_id, rows in raw_groups.items() if len(rows) > 1
    }

    resolved_edges, external_edges = _resolved_edges(sources)
    edge_keys: set[tuple[int, int]] = set()
    edges: list[dict[str, Any]] = []
    outgoing: list[list[int]] = [[] for _ in source_nodes]
    incoming_count = [0] * len(source_nodes)
    for edge, start_key, end_key in resolved_edges:
        start, end = key_to_dense[start_key], key_to_dense[end_key]
        if (start, end) in edge_keys:
            raise NanningMapError(f"duplicate directed edge: {start_key}->{end_key}")
        if edge.length_m <= 0.0 or edge.speed_mps <= 0.0:
            raise NanningMapError("edge length and speed must be positive")
        edge_keys.add((start, end))
        outgoing[start].append(end)
        incoming_count[end] += 1
        edges.append(
            {
                "start": start,
                "end": end,
                "length": edge.length_m,
                "speed": edge.speed_mps,
                "capacity": edge.pallet_capacity,
                "pallet_capacity": edge.pallet_capacity,
                "travel_time_seconds": edge.length_m / edge.speed_mps,
                "system": edge.system,
                "source": {
                    "workbook": edge.workbook_name,
                    "sheet": "邻接表",
                    "row": edge.row_number,
                    "raw_start": edge.raw_start,
                    "raw_end": edge.raw_end,
                    "resolved_start_key": start_key,
                    "resolved_end_key": end_key,
                },
            }
        )

    nodes: list[dict[str, Any]] = []
    imputed: list[str] = []
    for location, node in enumerate(source_nodes):
        service, service_source = _service_seconds(node)
        if service_source != "SOURCE_NUMERIC":
            imputed.append(node.key)
        nodes.append(
            {
                "location": location,
                "node_type": node.node_type,
                "service_time": service,
                "x": 0,
                "y": 0,
                # Preserve adjacency-sheet order because the legacy reader
                # validates node adjacency against the subsequent edge rows.
                "outgoing": list(outgoing[location]),
                "alias": node.alias,
                "external_id": node.raw_id,
                "raw_id": node.raw_id,
                "system_key": node.workbook_key,
                "system": node.system,
                "business_roles": _role(node),
                "empty_pallet_storage_id": node.empty_pallet_storage_id,
                "service_time_source": service_source,
                "coordinate_status": "NOT_PROVIDED_ROUTING_ONLY_ZERO_PLACEHOLDER",
                "source": {
                    "workbook": node.workbook_name,
                    "sheet": "节点表",
                    "row": node.row_number,
                },
            }
        )

    weak_components, strong_components = _component_counts(len(nodes), edges)
    heuristic_time = _shortest_paths(
        len(nodes), edges, cost_field="travel_time_seconds"
    )
    if any(not math.isfinite(value) for row in heuristic_time for value in row):
        raise NanningMapError("the resolved directed graph is not strongly connected")

    type_counts = Counter(node.node_type for node in source_nodes)
    speed_counts = Counter(edge.speed_mps for edge, _, _ in resolved_edges)
    cross_system_count = sum(
        nodes[edge["start"]]["system_key"]
        != nodes[edge["end"]]["system_key"]
        for edge in edges
    )
    capacity_matches = all(
        edge.pallet_capacity == math.floor(edge.length_m / 2.0)
        for edge, _, _ in resolved_edges
    )
    source_candidates = [node["location"] for node in nodes if node["node_type"] == 1]
    transfer_loaders = [
        node["location"]
        for node in nodes
        if node["node_type"] == 1 and str(node["alias"]).startswith("GTC")
    ]
    standard_loaders = [
        location for location in source_candidates if location not in transfer_loaders
    ]
    sink_candidates = [node["location"] for node in nodes if node["node_type"] == 2]
    empty_pallet_nodes = [
        node["location"] for node in nodes if node["node_type"] == 7
    ]
    recode_nodes = [node["location"] for node in nodes if node["node_type"] == 11]
    # The workbooks do not identify a real early-bag-storage in/out pair.
    # Type 7 is documented only as empty-pallet storage.  Keep every such
    # location as an explicit same-node proxy candidate so a later workload
    # can freeze one candidate without misclassifying an ordinary loader as a
    # storage exit.
    storage_pairs = [
        {
            "storage_in_goal": node["location"],
            "storage_out_start": node["location"],
            "storage_external_id": node["external_id"],
            "storage_alias": node["alias"],
            "system_key": node["system_key"],
            "role_status": "EMPTY_PALLET_STORAGE_EBS_PROXY_CANDIDATE",
        }
        for node in nodes
        if node["node_type"] == 7
    ]

    return {
        "schema": SCHEMA,
        "status": STATUS,
        "map_id": "nanning_topology_examples_1_2_namespaced_ics156",
        "profile_id": "nanning_two_workbook_namespaced_ics156",
        "source_files": [
            {
                "workbook_key": source.key,
                "file_name": source.name,
                "sheets": {
                    "节点表": source.node_range,
                    "邻接表": source.edge_range,
                },
                "node_row_count": len(source.nodes),
                "edge_row_count": len(source.edges),
            }
            for source in sources
        ],
        "dense_id_rule": (
            "workbook order international then domestic; source node-row order; "
            "runtime IDs are contiguous 0..N-1"
        ),
        "duplicate_raw_id_policy": {
            "mode": "WORKBOOK_SYSTEM_NAMESPACE",
            "edge_resolution": (
                "current workbook first; otherwise unique external raw ID"
            ),
            "collision_count": len(collisions),
            "collisions": [
                {
                    "raw_id": raw_id,
                    "rows": [
                        {
                            "key": node.key,
                            "alias": node.alias,
                            "system": node.system,
                            "node_type": node.node_type,
                            "source_service": node.source_service,
                            "workbook": node.workbook_name,
                            "row": node.row_number,
                        }
                        for node in rows
                    ],
                }
                for raw_id, rows in sorted(collisions.items())
            ],
        },
        "source_resolution": {
            "rule": "current workbook first; otherwise unique external raw ID",
            "duplicate_policy": "split by workbook system namespace",
            "ics156_split": {
                "international_key": "international:ICS156",
                "domestic_key": "domestic:ICS156",
                "merged": False,
            },
        },
        "counts": {
            "source_node_rows": len(source_nodes),
            "dense_node_count": len(nodes),
            "directed_edge_count": len(edges),
            "cross_system_edge_count": cross_system_count,
            "external_reference_edge_count": len(external_edges),
            "weak_component_count": weak_components,
            "strong_component_count": strong_components,
            "max_outdegree": max(map(len, outgoing), default=0),
            "max_indegree": max(incoming_count, default=0),
            "imputed_service_node_count": len(imputed),
        },
        "node_type_counts": {
            str(key): value for key, value in sorted(type_counts.items())
        },
        "speed_mps_counts": {
            f"{key:g}": value for key, value in sorted(speed_counts.items())
        },
        "topology_contract": {
            "directed_edges_preserved_exactly": True,
            "reverse_edges_synthesized": False,
            "all_edge_endpoints_resolved": True,
            "all_distances_positive": True,
            "all_speeds_positive": True,
            "strongly_connected": strong_components == 1,
            "pallet_capacity_equals_floor_distance_over_2m": capacity_matches,
            "zero_capacity_edge_count": sum(
                edge.pallet_capacity == 0 for edge, _, _ in resolved_edges
            ),
        },
        "business_roles": {
            "source_rule": "documented node type 1 loader",
            "sink_rule": "documented node type 2 unloader",
            "standard_loader_nodes": standard_loaders,
            "transfer_loader_nodes": transfer_loaders,
            "transfer_loader_inference": (
                "documented type 1 nodes whose alias begins GTC"
            ),
            "unloader_nodes": sink_candidates,
            "storage_pairs": storage_pairs,
            "storage_pair_status": "EMPTY_PALLET_STORAGE_EBS_PROXY_CANDIDATE",
            "source_candidate_ids": source_candidates,
            "sink_candidate_ids": sink_candidates,
            "empty_pallet_storage_ids": empty_pallet_nodes,
            "recode_station_ids": recode_nodes,
            "undocumented_node_types": list(UNDOCUMENTED_NODE_TYPES),
            "ebs": {
                "status": "NOT_IDENTIFIED_IN_SOURCE_WORKBOOKS",
                "in_ids": [],
                "out_ids": [],
                "type_7_is_empty_pallet_storage_not_ebs": True,
                "proxy_candidate_pair_count": len(storage_pairs),
                "proxy_selection_rule": (
                    "each type-7 location is a same-node in/out proxy; a "
                    "workload must pre-register one candidate explicitly; "
                    "the map adapter never promotes a proxy to real EBS"
                ),
            },
        },
        "external_reference_edges": external_edges,
        "assumptions": {
            "coordinates": (
                "source workbooks contain no x/y coordinates; x=y=0 is a "
                "routing-only placeholder and has no layout meaning"
            ),
            "missing_service_time": {
                "rule": (
                    "example1 '/' on type 7 and 11 becomes 0 seconds, matching "
                    "the numeric values of the same documented types in example2"
                ),
                "node_keys": imputed,
            },
            "legacy_header": {
                "agv_length_m": agv_length_m,
                "safe_length_m": safe_length_m,
                "fault_threshold_seconds": fault_threshold_seconds,
                "heuristic_base_speed_mps": LEGACY_HEURISTIC_BASE_SPEED_MPS,
                "hcost_file_semantics": (
                    "DIRECTED_SHORTEST_DISTANCE_METRES_BEFORE_JAVA_2P5_MPS_NORMALIZATION"
                ),
                "source_status": "NOT_PRESENT_IN_WORKBOOKS_PROVISIONAL_NO_FAULT_ONLY",
            },
            "pallet_capacity": (
                "preserved as metadata; the current legacy map text has no "
                "per-edge capacity field"
            ),
            "task_data": "NOT_PROVIDED",
            "fault_scenarios": "NOT_PROVIDED",
        },
        "nodes": nodes,
        "edges": edges,
        "heuristic_time": heuristic_time,
        "heuristic_time_semantics": (
            "directed shortest edge travel time at each source edge speed; "
            "node service is added separately by the G28 service-aware potential"
        ),
    }


def build_profile(
    source_dir: Path,
    *,
    agv_length_m: float = DEFAULT_AGV_LENGTH_METERS,
    safe_length_m: float = DEFAULT_SAFE_LENGTH_METERS,
    fault_threshold_seconds: float = DEFAULT_FAULT_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    return build_profile_from_sources(
        load_source_dir(source_dir),
        agv_length_m=agv_length_m,
        safe_length_m=safe_length_m,
        fault_threshold_seconds=fault_threshold_seconds,
    )


def _format_number(value: float) -> str:
    return f"{value:.12g}"


def legacy_map_text(profile: Mapping[str, Any]) -> str:
    """Render the dense profile in the legacy Java ``map.txt`` format."""

    nodes = list(profile["nodes"])
    edges = list(profile["edges"])
    assumptions = profile["assumptions"]["legacy_header"]
    node_count = len(nodes)
    lines = [
        " ".join(
            (
                str(node_count),
                _format_number(float(assumptions["agv_length_m"])),
                _format_number(float(assumptions["safe_length_m"])),
                _format_number(float(assumptions["fault_threshold_seconds"])),
            )
        )
    ]
    for node in nodes:
        fields = [
            str(node["location"]),
            str(node["node_type"]),
            _format_number(float(node["service_time"])),
            "0",
            "0",
            *(str(value) for value in node["outgoing"]),
        ]
        lines.append(" ".join(fields))

    distance_edges = [
        {
            "start": edge["start"],
            "end": edge["end"],
            "distance_m": edge["length"],
        }
        for edge in edges
    ]
    distances = _shortest_paths(
        node_count, distance_edges, cost_field="distance_m"
    )
    if any(not math.isfinite(value) for row in distances for value in row):
        raise NanningMapError("legacy heuristic requires a strongly connected graph")
    # Legacy Map.read divides every map-file Hcost value by 2.5, producing
    # seconds at the historical reference speed.  The benchmark then applies
    # 2.5 / case_speed, so writing raw metres here yields distance / case_speed
    # exactly once.  Pre-dividing in the converter would divide by 2.5 twice.
    lines.extend(
        " ".join(_format_number(value) for value in row)
        for row in distances
    )
    lines.extend(
        " ".join(
            (
                str(edge["start"]),
                str(edge["end"]),
                _format_number(float(edge["length"])),
            )
        )
        for edge in edges
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    profile: Mapping[str, Any],
    *,
    profile_output: Path,
    legacy_map_output: Path,
) -> None:
    profile_output.parent.mkdir(parents=True, exist_ok=True)
    legacy_map_output.parent.mkdir(parents=True, exist_ok=True)
    profile_output.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    legacy_map_output.write_text(
        legacy_map_text(profile), encoding="utf-8", newline="\n"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=default_source_dir())
    parser.add_argument("--profile-output", type=Path, default=DEFAULT_PROFILE_OUTPUT)
    parser.add_argument(
        "--legacy-map-output", type=Path, default=DEFAULT_LEGACY_MAP_OUTPUT
    )
    parser.add_argument(
        "--agv-length-m", type=float, default=DEFAULT_AGV_LENGTH_METERS
    )
    parser.add_argument(
        "--safe-length-m", type=float, default=DEFAULT_SAFE_LENGTH_METERS
    )
    parser.add_argument(
        "--fault-threshold-seconds",
        type=float,
        default=DEFAULT_FAULT_THRESHOLD_SECONDS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    profile = build_profile(
        args.source_dir,
        agv_length_m=args.agv_length_m,
        safe_length_m=args.safe_length_m,
        fault_threshold_seconds=args.fault_threshold_seconds,
    )
    write_outputs(
        profile,
        profile_output=args.profile_output,
        legacy_map_output=args.legacy_map_output,
    )
    print(
        json.dumps(
            {
                "status": profile["status"],
                "profile_output": str(args.profile_output),
                "legacy_map_output": str(args.legacy_map_output),
                **profile["counts"],
                "ebs_status": profile["business_roles"]["ebs"]["status"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
