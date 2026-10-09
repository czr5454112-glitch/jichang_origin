"""Bounded static portal routing with reservation-aware time refinement.

Control partitions are supplied metadata, not inferred operating permissions.
Each intra-partition macro arc carries one static shortest physical witness.
Alternative local witnesses can therefore be missed. Search-budget exhaustion
and absence in this bounded candidate set are never reported as infeasibility.
Every returned proposal still passes the unchanged execution validator.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from heapq import heappop, heappush
from itertools import count
from time import perf_counter

from .model import Leg, Reservation, RouteCandidate, Snapshot
from .runtime import INFINITY, ExecutionValidator, effective_reservations


def network_signature(network) -> tuple:
    """A content key, since frozen Network records contain mutable dictionaries."""
    return (
        tuple(sorted((key, value.control_partition, value.can_wait, value.capacity)
                     for key, value in network.nodes.items())),
        tuple(sorted((key, edge.source, edge.target, edge.travel_time, edge.capacity)
                     for key, edge in network.edges.items())),
    )


class _StaticTopology:
    def __init__(self, signature: tuple):
        nodes, edges = signature
        self.partitions = {key: partition for key, partition, _, _ in nodes}
        self.edges = {key: (source, target, travel) for key, source, target, travel, _ in edges}
        self.outgoing = defaultdict(list)
        self.incoming = defaultdict(list)
        self.portals: set[str] = set()
        for edge_id, source, target, travel, capacity in edges:
            if not isinstance(travel, int) or travel <= 0 or capacity <= 0:
                raise ValueError("Regional routing requires positive integer travel and capacity")
            if source not in self.partitions or target not in self.partitions:
                raise ValueError("Static edge endpoint is absent")
            self.outgoing[source].append((target, travel, edge_id))
            self.incoming[target].append((source, travel, edge_id))
            if self.partitions[source] != self.partitions[target]:
                self.portals.update((source, target))
        self._local: dict[str, tuple[dict, dict]] = {}
        self._lower: dict[str, dict] = {}

    def lower_bounds(self, goal: str) -> dict[str, int]:
        """Exact static reverse-Dijkstra distances, ignoring all reservations."""
        if goal not in self._lower:
            distances = {goal: 0}
            queue = [(0, goal)]
            while queue:
                distance, node = heappop(queue)
                if distance != distances[node]:
                    continue
                for previous, travel, _ in self.incoming[node]:
                    value = distance + travel
                    if value < distances.get(previous, INFINITY):
                        distances[previous] = value
                        heappush(queue, (value, previous))
            self._lower[goal] = distances
        return self._lower[goal]

    def local_paths(self, source: str) -> tuple[dict[str, int], dict[str, tuple[str, ...]]]:
        if source not in self._local:
            distances, witnesses = {source: 0}, {source: ()}
            queue = [(0, source)]
            while queue:
                distance, node = heappop(queue)
                if distance != distances[node]:
                    continue
                for target, travel, edge_id in self.outgoing[node]:
                    if self.partitions[target] != self.partitions[source]:
                        continue
                    value = distance + travel
                    if value < distances.get(target, INFINITY):
                        distances[target] = value
                        witnesses[target] = witnesses[node] + (edge_id,)
                        heappush(queue, (value, target))
            self._local[source] = distances, witnesses
        return self._local[source]

    def abstraction(self, source: str, goal: str) -> dict[str, list[tuple[str, int, tuple[str, ...]]]]:
        anchors = self.portals | {source, goal}
        groups = defaultdict(list)
        for anchor in sorted(anchors):
            groups[self.partitions[anchor]].append(anchor)
        abstract = defaultdict(list)
        for anchor in sorted(anchors):
            distances, witnesses = self.local_paths(anchor)
            for target in groups[self.partitions[anchor]]:
                if target != anchor and target in distances:
                    abstract[anchor].append((target, distances[target], witnesses[target]))
            for target, travel, edge_id in self.outgoing[anchor]:
                if self.partitions[target] != self.partitions[anchor]:
                    abstract[anchor].append((target, travel, (edge_id,)))
        return abstract


@lru_cache(maxsize=16)
def _topology(signature: tuple) -> _StaticTopology:
    return _StaticTopology(signature)


def clear_static_cache() -> None:
    """Explicit cold-cache benchmark boundary; does not mutate any network."""
    _topology.cache_clear()


class _ResourceView:
    def __init__(self, snapshot: Snapshot, tray_id: str):
        self.snapshot = snapshot
        self.slots = defaultdict(list)
        for slot in effective_reservations(snapshot):
            if slot.tray_id != tray_id:
                self.slots[slot.resource].append(slot)

    def available(self, resource: str, start: int, end: int) -> bool:
        if end <= start:
            return True
        kind, _, key = resource.partition(":")
        capacity = (self.snapshot.network.nodes[key].capacity if kind == "node" else
                    self.snapshot.network.edges[key].capacity if kind == "edge" else
                    self.snapshot.module.reception_capacity)
        deltas = defaultdict(int)
        for slot in self.slots[resource]:
            left, right = max(start, slot.start), min(end, slot.end)
            if left < right:
                deltas[left] += 1
                deltas[right] -= 1
        occupied = 0
        for _, delta in sorted(deltas.items()):
            occupied += delta
            if occupied >= capacity:  # The proposed tray consumes one more unit.
                return False
        return True


class RegionalCandidateGenerator:
    """Same proposal API as CandidateGenerator; bounded completeness only.

    ``horizon`` is a relative integer tick budget. ``expansion_limit`` bounds
    macro-search pops plus refinement labels; ``deadline_ms`` bounds query wall
    time at checkpoints, including static preprocessing. Static preprocessing
    is cached by graph content, but is still included in cold-request timing.
    """

    def __init__(self, horizon: int = 80, expansion_limit: int = 5000,
                 static_path_limit: int = 12, deadline_ms: float | None = 80.0):
        if horizon < 0 or expansion_limit < 1 or static_path_limit < 1:
            raise ValueError("Invalid regional routing budgets")
        if deadline_ms is not None and deadline_ms <= 0:
            raise ValueError("deadline_ms must be positive or None")
        self.horizon, self.expansion_limit = horizon, expansion_limit
        self.static_path_limit, self.deadline_ms = static_path_limit, deadline_ms
        self.last_search_status = "not_started"
        self.last_expansions = 0
        self.last_diagnostics: dict = {}

    def _budget(self) -> bool:
        if self.last_expansions >= self.expansion_limit:
            self.last_search_status = "expansion_budget_exhausted"
            return False
        if self.deadline_ms is not None and (perf_counter() - self._started) * 1000 >= self.deadline_ms:
            self.last_search_status = "deadline_exhausted"
            return False
        return True

    def generate(self, snapshot: Snapshot, bag_id: str, tray_id: str, k: int = 3) -> tuple[RouteCandidate, ...]:
        if bag_id not in snapshot.bags:
            self.last_search_status, self.last_expansions = "invalid_request", 0
            self.last_diagnostics = {}
            return ()
        return self._generate(snapshot, bag_id, tray_id, snapshot.bags[bag_id].destination, k)

    def generate_empty(self, snapshot: Snapshot, tray_id: str, destination: str, k: int = 1) -> tuple[RouteCandidate, ...]:
        return self._generate(snapshot, None, tray_id, destination, k)

    def _static_paths(self, topology, abstract, source, goal, lower):
        serial = count()
        queue = [(lower[source], 0, next(serial), source, (), frozenset((source,)))]
        seen = set()
        while queue and len(seen) < self.static_path_limit and self._budget():
            _, distance, _, node, path, visited = heappop(queue)
            self.last_expansions += 1
            if node == goal:
                if path not in seen:
                    seen.add(path)
                    yield path
                continue
            for target, travel, witness in abstract[node]:
                physical_nodes = tuple(topology.edges[edge_id][1] for edge_id in witness)
                if target not in lower or any(value in visited for value in physical_nodes):
                    continue
                new_distance = distance + travel
                if new_distance + lower[target] > self.horizon:
                    continue
                heappush(queue, (new_distance + lower[target], new_distance, next(serial), target,
                                 path + witness, visited | frozenset(physical_nodes)))

    def _schedule(self, snapshot, path, bag_id, tray_id, destination, view, baseline_id, index):
        edges = [snapshot.network.edges[edge_id] for edge_id in path]
        suffix = [0] * (len(edges) + 1)
        for position in reversed(range(len(edges))):
            suffix[position] = suffix[position + 1] + edges[position].travel_time
        limit = snapshot.now + self.horizon
        if bag_id is not None and snapshot.bags[bag_id].protected:
            limit = min(limit, snapshot.bags[bag_id].deadline - snapshot.module.unload_ticks)
        if snapshot.now + suffix[0] > limit:
            return None
        serial = count()
        queue = [(snapshot.now + suffix[0], next(serial), 0, snapshot.now, ())]
        visited = set()
        while queue and self._budget():
            _, _, position, tick, legs = heappop(queue)
            self.last_expansions += 1
            if (position, tick) in visited:
                continue
            visited.add((position, tick))
            if position == len(edges):
                unload = tick + (snapshot.module.unload_ticks if bag_id is not None else 0)
                usable = unload + snapshot.module.hold_ticks(destination)
                if (not view.available(f"node:{destination}", tick, INFINITY)
                        or not view.available(f"reception:{destination}", tick, usable)):
                    continue
                proposal = RouteCandidate(f"regional:v{snapshot.version}:{bag_id or 'empty'}:{tray_id}:{index}",
                                          bag_id, tray_id, legs, unload, usable, snapshot.version,
                                          baseline_id, index == 0, destination)
                begin = perf_counter()
                accepted = ExecutionValidator().validate(snapshot, proposal).accepted
                self.last_diagnostics["validation_ms"] += (perf_counter() - begin) * 1000
                if accepted:
                    return proposal
                continue
            edge = edges[position]
            departures = {tick}
            if snapshot.network.nodes[edge.source].can_wait:
                # Keep event-aligned delay labels at upstream waitable nodes.
                # Downstream no-wait nodes cannot absorb the delay themselves.
                offset = 0
                for downstream in edges[position:]:
                    for slot in view.slots[f"edge:{downstream.edge_id}"]:
                        departures.add(slot.end - offset)
                    offset += downstream.travel_time
                    for slot in view.slots[f"node:{downstream.target}"]:
                        departures.add(slot.end - offset)
                for slot in view.slots[f"reception:{destination}"]:
                    departures.add(slot.end - suffix[position])
            for depart in sorted(departures):
                if depart < tick or depart + suffix[position] > limit:
                    continue
                arrival = depart + edge.travel_time
                if (view.available(f"node:{edge.source}", tick, depart)
                        and view.available(f"edge:{edge.edge_id}", depart, arrival)):
                    heappush(queue, (arrival + suffix[position + 1], next(serial), position + 1, arrival,
                                     legs + (Leg(edge.edge_id, depart, arrival),)))
        return None

    def _generate(self, snapshot, bag_id, tray_id, destination, k):
        self._started = perf_counter()
        self.last_expansions, self.last_search_status = 0, "searching"
        self.last_diagnostics = {"validation_ms": 0., "static_paths_examined": 0,
                                 "completeness": "bounded_static_witness_and_event_aligned_refinement",
                                 "missing_candidate_is_not_infeasibility": True}
        tray = snapshot.trays.get(tray_id)
        if (k < 1 or tray is None or tray.node is None or tray_id in snapshot.plans
                or tray.available_at > snapshot.now or destination not in snapshot.network.nodes
                or any(f.tray_id == tray_id and f.arrive > snapshot.now for f in snapshot.old_in_transit)
                or (bag_id is not None and (tray.mode != "loaded" or tray.bag_id != bag_id))
                or (bag_id is None and (tray.mode != "empty" or tray.bag_id is not None))):
            self.last_search_status = "invalid_request"
            return ()
        begin = perf_counter()
        topology = _topology(network_signature(snapshot.network))
        lower = topology.lower_bounds(destination)
        if tray.node not in lower:
            self.last_search_status = "static_unreachable"
            return ()
        abstract = topology.abstraction(tray.node, destination)
        self.last_diagnostics.update({"abstraction_ms": (perf_counter() - begin) * 1000,
                                     "static_lower_bound": lower[tray.node], "portal_count": len(topology.portals),
                                     "partition_count": len(set(topology.partitions.values())),
                                     "macro_arc_count": sum(map(len, abstract.values()))})
        view = _ResourceView(snapshot, tray_id)
        baseline_id = f"regional:v{snapshot.version}:{bag_id or 'empty'}:{tray_id}:0"
        found = []
        begin = perf_counter()
        for path in self._static_paths(topology, abstract, tray.node, destination, lower):
            self.last_diagnostics["static_paths_examined"] += 1
            proposal = self._schedule(snapshot, path, bag_id, tray_id, destination, view, baseline_id, len(found))
            if proposal is not None:
                found.append(proposal)
                if len(found) >= k:
                    self.last_search_status = "candidate_limit_reached"
                    break
            if not self._budget():
                break
        if self.last_search_status == "searching":
            self.last_search_status = "partial_candidate_set" if found else "bounded_no_candidate"
        self.last_diagnostics.update({"search_and_refinement_ms": (perf_counter() - begin) * 1000,
                                     "query_ms": (perf_counter() - self._started) * 1000,
                                     "expansions": self.last_expansions, "candidate_count": len(found)})
        return tuple(found)
