"""Restricted owner observations, separate from the centralized baseline API.

The public topology is shared; remote calendars, tray IDs and task ledgers are
not. These observations are not a license to plan/commit on another owner. The
legacy global-snapshot planner remains explicitly centralized until a complete
multi-owner protocol consumes these views.
"""
from dataclasses import dataclass

from .model import Network, Reservation, Snapshot, Tray, Bag
from .runtime import effective_reservations


@dataclass(frozen=True)
class BoundaryOccupancy:
    resource: str
    occupied_units_now: int
    capacity: int


@dataclass(frozen=True)
class RemoteSummary:
    owner: str
    observed_tick: int
    version: int
    # Counts at now do not assert future availability or disclose calendars.
    boundary_occupancy: tuple[BoundaryOccupancy, ...]


@dataclass(frozen=True)
class PartitionObservation:
    owner: str
    observed_tick: int
    version: int
    public_topology: Network
    local_calendars: tuple[Reservation, ...]
    local_trays: tuple[Tray, ...]
    local_bags: tuple[Bag, ...]
    remote_summaries: tuple[RemoteSummary, ...]
    version_scope: str = 'global_conservative_watermark'


def resource_owner(snapshot: Snapshot, resource: str) -> str:
    kind, _, key = resource.partition(':')
    if kind == 'edge':
        return snapshot.network.nodes[snapshot.network.edges[key].source].control_partition
    if kind in {'node', 'reception'}:
        return snapshot.network.nodes[key].control_partition
    raise ValueError(f'unknown_resource:{resource}')


def observe_partition(snapshot: Snapshot, partition: str) -> PartitionObservation:
    state = snapshot.clone()
    partitions = {node.control_partition for node in state.network.nodes.values()}
    if partition not in partitions:
        raise ValueError('unknown_control_partition')
    slots = effective_reservations(state)
    local = tuple(s for s in slots if resource_owner(state, s.resource) == partition)
    local_nodes = {key for key, node in state.network.nodes.items() if node.control_partition == partition}
    local_trays = tuple(t for _, t in sorted(state.trays.items()) if t.node in local_nodes)
    carried_ids = {t.bag_id for t in local_trays if t.bag_id is not None}
    local_bags = tuple(b for key, b in sorted(state.bags.items()) if key in carried_ids or b.origin in local_nodes)
    boundary_targets = {edge.target for edge in state.network.edges.values()
                        if edge.source in local_nodes and edge.target not in local_nodes}
    summaries = []
    for remote in sorted(partitions - {partition}):
        boundary = []
        for node_id in sorted(boundary_targets):
            node = state.network.nodes[node_id]
            if node.control_partition != remote:
                continue
            for resource, capacity in ((f'node:{node_id}', node.capacity),
                                       (f'reception:{node_id}', state.module.reception_capacity)):
                count = len({s.tray_id for s in slots if s.resource == resource and s.start <= state.now < s.end})
                boundary.append(BoundaryOccupancy(resource, count, capacity))
        summaries.append(RemoteSummary(remote, state.now, state.version, tuple(boundary)))
    return PartitionObservation(partition, state.now, state.version, state.network,
                                local, local_trays, local_bags, tuple(summaries))
