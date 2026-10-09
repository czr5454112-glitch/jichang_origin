"""Explicit physical entities for the synthetic V3 circulation pilot.

Time is an integer tick. Reservations use half-open intervals. Logistics zones
and routing control partitions are distinct labels, even in small examples.
This module describes a fixed synthetic local controller, not a supplier API.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


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
    # Internal committed prefix records are constructed only by the owner from
    # a fully validated witness. They never imply unloading at an intermediate.
    prefix_only: bool = False
    continuation_destination: str | None = None


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


@dataclass(frozen=True)
class ForecastDependency:
    resource: str
    fingerprint: str


@dataclass(frozen=True)
class ConditionalRouteForecast:
    """A versioned, revocable prediction; it is never an empty-tray commitment."""

    forecast_id: str
    tray_id: str
    bag_id: str | None
    destination_node: str
    unload_complete: int
    usable_at: int
    witness_legs: tuple[Leg, ...]
    remaining_legs: tuple[Leg, ...]
    created_at: int
    updated_at: int
    source_version: int
    revision: int
    parent_forecast_id: str | None
    dependencies: tuple[ForecastDependency, ...]
    status: str = "active"
    reason: str = "validated_full_witness_prefix_only_committed"
    model_version: str = "fixed_module_route_witness_v1"


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
    empty_targets: dict[str, str] = field(default_factory=dict)
    conditional_forecasts: dict[str, ConditionalRouteForecast] = field(default_factory=dict)
    forecast_history: tuple[ConditionalRouteForecast, ...] = ()
    # Explicit synthetic owner permission. No supplier cancellation permission
    # is inferred. Protected and empty-transfer obligations remain immutable.
    replaceable_trays: tuple[str, ...] = ()

    def clone(self) -> Snapshot:
        """Branch isolation includes mutable dictionaries inside frozen records."""
        return deepcopy(self)


@dataclass(frozen=True)
class ReplacementContext:
    """Private reservation planning view at the next safe anchor, not a rollout."""

    planning_snapshot: Snapshot
    source_version: int
    source_state_fingerprint: str
    frozen_legs: tuple[Leg, ...]
    anchor_node: str
    anchor_time: int
    tray_id: str
    bag_id: str


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
    # Wall-clock diagnostics are intentionally excluded from semantic replay
    # equality; state, event trace and objective components remain exact.
    policy_stats: dict[str, float] = field(default_factory=dict, compare=False)


@dataclass
class SimulationCheckpoint:
    """Engine-only checkpoint: never an observation supplied to a controller.

    The private exogenous tape is necessary for exact replay but is deliberately
    absent from Snapshot and all policy callback arguments. Callbacks are copied
    where possible; user-supplied function closures must remain deterministic.
    """

    state: Snapshot
    cost_components: dict[str, float]
    trace: tuple[dict, ...]
    invariant_checks: int
    pending_arrivals: dict[int, list[Bag]]
    entered_legs: set[tuple[str, str, int]]
    initial_tray_ids: set[str]
    phase: str
    route_mode: str
    search_horizon: int
    candidate_count: int
    generator: Any
    generator_factory: Any
    route_selector: Any
    slow_controller: Any
    observer: Any
    policy_stats: dict[str, float]
    reactive_empty_dispatch: bool = True
    coordination_order: str = "route_then_prebalance"

    def clone(self) -> SimulationCheckpoint:
        return deepcopy(self)
