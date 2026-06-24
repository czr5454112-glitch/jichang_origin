"""Parser for the legacy Java ICS `map2.txt` format."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

DEFAULT_EDGE_SPEED = 2.5


@dataclass(frozen=True)
class MapHeader:
    node_count: int
    agv_length: float
    safe_length: float
    fault_threshold: float


@dataclass(frozen=True)
class LegacyNode:
    location: int
    node_type: int
    service_time: float
    y: int
    x: int
    outgoing: tuple[int, ...]


@dataclass(frozen=True)
class LegacyEdge:
    start: int
    end: int
    length: float
    speed: float
    file_speed: float | None = None

    @property
    def travel_time(self) -> float:
        return self.length / self.speed


@dataclass(frozen=True)
class LegacyMap:
    path: str
    header: MapHeader
    nodes: tuple[LegacyNode, ...]
    heuristic_raw: tuple[tuple[float, ...], ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    edges: tuple[LegacyEdge, ...]
    edge_speed: float = DEFAULT_EDGE_SPEED

    @property
    def start_nodes(self) -> tuple[int, ...]:
        return tuple(node.location for node in self.nodes if node.node_type == 1)

    @property
    def end_nodes(self) -> tuple[int, ...]:
        return tuple(node.location for node in self.nodes if node.node_type == 2)

    @property
    def max_x(self) -> int:
        return max(node.x for node in self.nodes)

    @property
    def max_y(self) -> int:
        return max(node.y for node in self.nodes)

    @property
    def node_type_counts(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for node in self.nodes:
            counts[node.node_type] = counts.get(node.node_type, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "czr005.legacy_map.v1",
            "source_path": self.path,
            "header": asdict(self.header),
            "constants": {
                "edge_speed": self.edge_speed,
                "heuristic_divisor": self.edge_speed,
            },
            "node_type_counts": {str(k): v for k, v in self.node_type_counts.items()},
            "start_nodes": list(self.start_nodes),
            "end_nodes": list(self.end_nodes),
            "max_x": self.max_x,
            "max_y": self.max_y,
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [
                {
                    **asdict(edge),
                    "travel_time": edge.travel_time,
                }
                for edge in self.edges
            ],
            "heuristic_raw": [list(row) for row in self.heuristic_raw],
            "heuristic_time": [list(row) for row in self.heuristic_time],
        }


def parse_legacy_map(
    path: str | Path,
    edge_speed: float = DEFAULT_EDGE_SPEED,
    allow_ragged_heuristic: bool = False,
) -> LegacyMap:
    map_path = Path(path)
    lines = map_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"empty map file: {map_path}")

    header_parts = _parts(lines[0], 1)
    if len(header_parts) != 4:
        raise ValueError("map header must contain 4 fields")
    header = MapHeader(
        node_count=int(header_parts[0]),
        agv_length=float(header_parts[1]),
        safe_length=float(header_parts[2]),
        fault_threshold=float(header_parts[3]),
    )

    min_lines = 1 + header.node_count + header.node_count
    if len(lines) < min_lines:
        raise ValueError(
            f"map has {len(lines)} lines, expected at least {min_lines} for nodes and heuristics"
        )

    nodes: list[LegacyNode] = []
    for offset in range(header.node_count):
        line_no = 2 + offset
        parts = _parts(lines[1 + offset], line_no)
        if len(parts) < 5:
            raise ValueError(f"node line {line_no} must contain at least 5 fields")
        nodes.append(
            LegacyNode(
                location=int(parts[0]),
                node_type=int(parts[1]),
                service_time=float(parts[2]),
                y=int(parts[3]),
                x=int(parts[4]),
                outgoing=tuple(int(value) for value in parts[5:]),
            )
        )

    node_ids = {node.location for node in nodes}
    expected_node_ids = set(range(header.node_count))
    if node_ids != expected_node_ids:
        raise ValueError(
            f"legacy map assumes contiguous node ids 0..{header.node_count - 1}; got {sorted(node_ids)}"
        )

    heuristic_raw: list[tuple[float, ...]] = []
    heuristic_time: list[tuple[float, ...]] = []
    heuristic_start = 1 + header.node_count
    for offset in range(header.node_count):
        line_no = heuristic_start + offset + 1
        values = tuple(float(value) for value in _parts(lines[heuristic_start + offset], line_no))
        if len(values) != header.node_count and not allow_ragged_heuristic:
            raise ValueError(
                f"heuristic row {line_no} has {len(values)} values, expected {header.node_count}"
            )
        if len(values) > header.node_count:
            raise ValueError(
                f"heuristic row {line_no} has {len(values)} values, expected at most {header.node_count}"
            )
        if len(values) < header.node_count:
            values = values + (0.0,) * (header.node_count - len(values))
        heuristic_raw.append(values)
        heuristic_time.append(tuple(value / edge_speed for value in values))

    edges: list[LegacyEdge] = []
    edge_start = 1 + header.node_count + header.node_count
    for index, line in enumerate(lines[edge_start:], start=edge_start + 1):
        if not line.strip():
            continue
        parts = _parts(line, index)
        if len(parts) not in (3, 4):
            raise ValueError(f"edge line {index} must contain 3 or 4 fields")
        start = int(parts[0])
        end = int(parts[1])
        if start not in node_ids or end not in node_ids:
            raise ValueError(f"edge line {index} references unknown node: {start}->{end}")
        file_speed = float(parts[3]) if len(parts) == 4 else None
        edges.append(
            LegacyEdge(
                start=start,
                end=end,
                length=float(parts[2]),
                speed=edge_speed,
                file_speed=file_speed,
            )
        )

    _validate_adjacency(nodes, edges)

    return LegacyMap(
        path=str(map_path),
        header=header,
        nodes=tuple(nodes),
        heuristic_raw=tuple(heuristic_raw),
        heuristic_time=tuple(heuristic_time),
        edges=tuple(edges),
        edge_speed=edge_speed,
    )


def write_map_json(parsed_map: LegacyMap, output_path: str | Path) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(parsed_map.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out


def _parts(line: str, line_no: int) -> list[str]:
    parts = line.strip().split()
    if not parts:
        raise ValueError(f"blank line at {line_no}")
    return parts


def _validate_adjacency(nodes: list[LegacyNode], edges: list[LegacyEdge]) -> None:
    edge_adjacency: dict[int, list[int]] = {}
    for edge in edges:
        edge_adjacency.setdefault(edge.start, []).append(edge.end)
    for node in nodes:
        from_edges = tuple(edge_adjacency.get(node.location, []))
        if from_edges != node.outgoing:
            raise ValueError(
                "node adjacency does not match edge list for "
                f"{node.location}: node row={node.outgoing}, edge rows={from_edges}"
            )
