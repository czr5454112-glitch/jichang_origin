"""Headless graph model for the Python reference simulator."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from czr005.io.legacy_map import LegacyMap


@dataclass(frozen=True)
class SimNode:
    location: int
    node_type: int
    service_time: float
    x: int
    y: int
    outgoing: tuple[int, ...]


@dataclass(frozen=True)
class SimEdge:
    start: int
    end: int
    length: float
    speed: float

    @property
    def travel_time(self) -> float:
        return self.length / self.speed


@dataclass(frozen=True)
class IcsGraph:
    nodes: dict[int, SimNode]
    edges: dict[tuple[int, int], SimEdge]
    heuristic_time: tuple[tuple[float, ...], ...]
    agv_length: float
    safe_length: float
    fault_threshold: float

    @classmethod
    def from_legacy_map(cls, parsed_map: LegacyMap) -> "IcsGraph":
        return cls(
            nodes={
                node.location: SimNode(
                    location=node.location,
                    node_type=node.node_type,
                    service_time=node.service_time,
                    x=node.x,
                    y=node.y,
                    outgoing=node.outgoing,
                )
                for node in parsed_map.nodes
            },
            edges={
                (edge.start, edge.end): SimEdge(
                    start=edge.start,
                    end=edge.end,
                    length=edge.length,
                    speed=edge.speed,
                )
                for edge in parsed_map.edges
            },
            heuristic_time=parsed_map.heuristic_time,
            agv_length=parsed_map.header.agv_length,
            safe_length=parsed_map.header.safe_length,
            fault_threshold=parsed_map.header.fault_threshold,
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "IcsGraph":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        nodes = {
            int(node["location"]): SimNode(
                location=int(node["location"]),
                node_type=int(node["node_type"]),
                service_time=float(node["service_time"]),
                x=int(node["x"]),
                y=int(node["y"]),
                outgoing=tuple(int(value) for value in node["outgoing"]),
            )
            for node in data["nodes"]
        }
        edges = {
            (int(edge["start"]), int(edge["end"])): SimEdge(
                start=int(edge["start"]),
                end=int(edge["end"]),
                length=float(edge["length"]),
                speed=float(edge["speed"]),
            )
            for edge in data["edges"]
        }
        return cls(
            nodes=nodes,
            edges=edges,
            heuristic_time=tuple(tuple(float(value) for value in row) for row in data["heuristic_time"]),
            agv_length=float(data["header"]["agv_length"]),
            safe_length=float(data["header"]["safe_length"]),
            fault_threshold=float(data["header"]["fault_threshold"]),
        )

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def start_nodes(self) -> tuple[int, ...]:
        return tuple(node.location for node in self.nodes.values() if node.node_type == 1)

    @property
    def end_nodes(self) -> tuple[int, ...]:
        return tuple(node.location for node in self.nodes.values() if node.node_type == 2)

    def node(self, location: int) -> SimNode:
        try:
            return self.nodes[location]
        except KeyError as exc:
            raise KeyError(f"unknown node: {location}") from exc

    def edge(self, start: int, end: int) -> SimEdge:
        try:
            return self.edges[(start, end)]
        except KeyError as exc:
            raise KeyError(f"unknown edge: {start}->{end}") from exc

    def outgoing(self, location: int) -> tuple[int, ...]:
        return self.node(location).outgoing

    def outgoing_edges(self, location: int) -> Iterable[SimEdge]:
        for end in self.outgoing(location):
            yield self.edge(location, end)

    def service_time(self, location: int) -> float:
        return self.node(location).service_time

    def heuristic(self, start: int, goal: int) -> float:
        return self.heuristic_time[start][goal]

    def has_edge(self, start: int, end: int) -> bool:
        return (start, end) in self.edges

