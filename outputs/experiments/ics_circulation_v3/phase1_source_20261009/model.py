"""Explicit physical entities for the synthetic V3 circulation pilot.

Time is an integer tick. Reservations use half-open intervals. Logistics zones
and routing control partitions are distinct labels, even in small examples.
This module describes a fixed synthetic local controller, not a supplier API.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    node_id: str
    logistics_zone: str
    control_partition: str
    capacity: int = 4
    can_wait: bool = True


@dataclass(frozen=True)
class Edge:
    edge_id: str
    source: str
    target: str
    travel_time: int
    capacity: int = 1


@dataclass(frozen=True)
class Network:
    nodes: dict[str, Node]
    edges: dict[str, Edge]


@dataclass(frozen=True)
class Bag:
    bag_id: str
    origin: str
    destination: str
    arrival: int
    deadline: int
    protected: bool = False


@dataclass(frozen=True)
class Tray:
    tray_id: str
    node: str | None
    mode: str = "empty"
    bag_id: str | None = None
    available_at: int = 0


@dataclass(frozen=True)
class Reservation:
    resource: str
    start: int
    end: int
    tray_id: str


@dataclass(frozen=True)
class Leg:
    edge_id: str
    depart: int
    arrive: int


@dataclass(frozen=True)
class RouteCandidate:
    candidate_id: str
    bag_id: str | None
    tray_id: str
    legs: tuple[Leg, ...]
    unload_complete: int
    usable_at: int
    dependency_version: int
    baseline_id: str
    is_baseline: bool = False
    # Only empty transfers require an explicit destination. Loaded routes use
    # the corresponding bag's immutable destination.
    destination_node: str | None = None


@dataclass(frozen=True)
class InFlight:
    tray_id: str
    edge_id: str
    depart: int
    arrive: int


@dataclass(frozen=True)
class FixedLocalModule:
    """Frozen FIFO proxy parameters; no learned rule or hidden optimization."""

    unload_ticks: int = 1
    hold_by_node: dict[str, int] = field(default_factory=dict)
    export_min_stock: int = 0
    reception_capacity: int = 1

    def hold_ticks(self, node: str) -> int:
        return self.hold_by_node.get(node, 0)


@dataclass
class Snapshot:
    now: int
    network: Network
    trays: dict[str, Tray]
    bags: dict[str, Bag]
    reservations: tuple[Reservation, ...] = ()
    version: int = 0
    old_in_transit: tuple[InFlight, ...] = ()
    module: FixedLocalModule = field(default_factory=FixedLocalModule)
    plans: dict[str, RouteCandidate] = field(default_factory=dict)
    completed: dict[str, int] = field(default_factory=dict)
    load_times: dict[str, int] = field(default_factory=dict)

    def clone(self) -> Snapshot:
        """Branch isolation includes mutable dictionaries inside frozen records."""
        return deepcopy(self)


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str


@dataclass(frozen=True)
class RolloutResult:
    cost_components: dict[str, float]
    total_cost: float
    completed: dict[str, int]
    waiting_bag_ids: tuple[str, ...]
    uncompleted_bag_ids: tuple[str, ...]
    final_trays: dict[str, Tray]
    trace: tuple[dict, ...]
    invariant_checks: int
    final_snapshot: Snapshot
