"""Strong full-graph time search and shared event-time search primitives.

Event departures include reservation endpoints projected through no-wait
chains, including chains across control boundaries. This representation is
bounded and is not labelled globally complete. The tiny-graph integer mode
instead enumerates every feasible integer departure; with sufficient budget
it certifies earliest arrival within the declared finite horizon. Neither
reference uses the regional macro abstraction or its local repair policy.
"""
from collections import defaultdict
from heapq import heappop, heappush
from itertools import count
from time import perf_counter

from .model import Leg, RouteCandidate
from .runtime import ExecutionValidator, INFINITY
from .routing import (_ResourceView, _SearchBudgetExpired, RegionalCandidateGenerator,
                      _TOPOLOGY_CACHE, _topology, network_signature)


def _proposal(owner, snapshot, bag_id, tray_id, destination, legs, tick, index, prefix):
    unload = tick + (snapshot.module.unload_ticks if bag_id is not None else 0)
    usable = unload + snapshot.module.hold_ticks(destination)
    identifier = f"{prefix}:v{snapshot.version}:{bag_id or 'empty'}:{tray_id}"
    candidate = RouteCandidate(f"{identifier}:{index}", bag_id, tray_id, legs, unload, usable,
                               snapshot.version, f"{identifier}:0", index == 0, destination)
    begin = perf_counter()
    valid = ExecutionValidator().validate(snapshot, candidate).accepted
    owner.last_diagnostics["validation_ms"] += (perf_counter() - begin) * 1000
    return candidate if valid else None


class EventTimeSearch:
    """Physical edge search; local users only restrict traversable nodes.

    Projection may inspect the global no-wait chain's calendar. This prototype
    does not claim a private/distributed region observation interface.
    """
    def __init__(self, owner, snapshot, topology, lower, view, limit, *, integer_ticks=False):
        self.owner, self.snapshot, self.topology = owner, snapshot, topology
        self.lower, self.view, self.limit = lower, view, limit
        self.integer_ticks = integer_ticks
        self._departures_cache = {}

    def departures(self, node, tick):
        if not self.snapshot.network.nodes[node].can_wait:
            return (tick,)
        if self.integer_ticks:
            return range(tick, self.limit - self.lower.get(node, 0) + 1)
        if node not in self._departures_cache:
            values, seen = set(), set()
            stack = [(node, 0)]
            while stack:
                current, offset = stack.pop()
                if (current, offset) in seen:
                    continue
                seen.add((current, offset))
                self.owner._consume("event_projection")
                for target, travel, edge_id in self.topology.outgoing[current]:
                    arrival_offset = offset + travel
                    if arrival_offset > self.limit - self.snapshot.now:
                        continue
                    for slot in self.view.slots[f"edge:{edge_id}"]:
                        values.add(slot.end - offset)
                    for slot in self.view.slots[f"node:{target}"]:
                        values.add(slot.end - arrival_offset)
                    for slot in self.view.slots[f"reception:{target}"]:
                        values.add(slot.end - arrival_offset)
                    if not self.snapshot.network.nodes[target].can_wait:
                        stack.append((target, arrival_offset))
            self._departures_cache[node] = tuple(sorted(t for t in values if self.snapshot.now <= t <= self.limit))
        return tuple(sorted({tick, *(t for t in self._departures_cache[node] if t >= tick)}))

    def paths(self, source, start_tick, targets, *, allowed_nodes=None, per_target=None,
              labels_per_state=1, stage="full_graph_time_labels", stop_at_targets=True):
        serial = count()
        queue = [(start_tick + self.lower.get(source, 0), next(serial), source, start_tick, ())]
        seen, reached = defaultdict(set), defaultdict(int)
        while queue:
            self.owner._consume(stage)
            _, _, node, tick, legs = heappop(queue)
            key = (node, tick)
            if legs in seen[key]:
                continue
            if len(seen[key]) >= labels_per_state:
                self.owner.last_diagnostics["state_label_truncations"] = self.owner.last_diagnostics.get("state_label_truncations", 0) + 1
                continue
            seen[key].add(legs)
            if node in targets:
                if per_target is None or reached[node] < per_target:
                    reached[node] += 1
                    yield node, tick, legs
                if per_target is not None and all(reached[target] >= per_target for target in targets):
                    return
                if stop_at_targets:
                    continue
            for depart in self.departures(node, tick):
                if depart < tick or depart + self.lower.get(node, 0) > self.limit:
                    continue
                if not self.view.available(f"node:{node}", tick, depart):
                    continue
                for target, travel, edge_id in self.topology.outgoing[node]:
                    if target not in self.lower or (allowed_nodes is not None and target not in allowed_nodes):
                        continue
                    arrive = depart + travel
                    if arrive + self.lower[target] > self.limit:
                        continue
                    if self.view.available(f"edge:{edge_id}", depart, arrive):
                        heappush(queue, (arrive + self.lower[target], next(serial), target, arrive,
                                         legs + (Leg(edge_id, depart, arrive),)))


def _finish(owner, candidates, *, exhausted=False):
    if owner.last_search_status == "searching":
        owner.last_search_status = "partial_candidate_set" if candidates else "bounded_no_candidate"
    owner.last_diagnostics.update(query_ms=(perf_counter() - owner._started) * 1000,
                                   expansions=owner.last_expansions, candidate_count=len(candidates),
                                   search_queue_exhausted=exhausted)
    return tuple(candidates)


def dynamic_regional_candidates(owner, snapshot, bag_id, tray_id, destination, k, topology, lower):
    """Time-labelled macro search with reservation-aware local re-search.

    A local search stops at the next portal/source/goal anchor. It retains
    multiple arrival/path labels per anchor, then the outer search combines
    them with crossing edges. Thus an internal bypass is generated even when
    it was absent from the old static macro witness. Local label truncation
    is explicit and can still omit valuable routes or arrival windows.
    """
    source = snapshot.trays[tray_id].node
    limit = snapshot.now + owner.horizon
    if bag_id is not None and snapshot.bags[bag_id].protected:
        limit = min(limit, snapshot.bags[bag_id].deadline - snapshot.module.unload_ticks)
    anchors = topology.portals | {source, destination}
    regions = defaultdict(set)
    region_anchors = defaultdict(set)
    for node, region in topology.partitions.items():
        regions[region].add(node)
        if node in anchors:
            region_anchors[region].add(node)
    owner.last_diagnostics.update(completeness="bounded_dynamic_local_time_labels", portal_count=len(topology.portals),
                                   partition_count=len(regions), local_label_limit=owner.local_label_limit,
                                   local_search_calls=0, local_labels_returned=0, remote_calendar_access=True,
                                   static_lower_bound=lower[source], local_label_truncation_possible=True)
    view = _ResourceView(snapshot, tray_id)
    search = EventTimeSearch(owner, snapshot, topology, lower, view, limit)
    serial = count()
    queue = [(snapshot.now + lower[source], next(serial), source, snapshot.now, ())]
    seen, local_cache, candidates = defaultdict(set), {}, []
    signatures = set()
    try:
        while queue:
            owner._consume("regional_macro_time_labels")
            _, _, node, tick, legs = heappop(queue)
            if legs in seen[(node, tick)] or len(seen[(node, tick)]) >= k:
                continue
            seen[(node, tick)].add(legs)
            if node == destination:
                candidate = _proposal(owner, snapshot, bag_id, tray_id, destination, legs, tick, len(candidates), "dynamic_regional")
                if candidate is not None and legs not in signatures:
                    candidates.append(candidate)
                    signatures.add(legs)
                    if len(candidates) >= k:
                        owner.last_search_status = "candidate_limit_reached"
                        return _finish(owner, candidates)
                # Invalid terminal occupancy need not rule out a later arrival.
            region = topology.partitions[node]
            targets = region_anchors[region] - {node}
            if targets and (node, tick) not in local_cache:
                owner.last_diagnostics["local_search_calls"] += 1
                local_cache[(node, tick)] = tuple(search.paths(
                    node, tick, targets, allowed_nodes=regions[region], per_target=owner.local_label_limit,
                    labels_per_state=owner.local_label_limit, stage="dynamic_local_time_labels"))
                owner.last_diagnostics["local_labels_returned"] += len(local_cache[(node, tick)])
            for target, arrive, local_legs in local_cache.get((node, tick), ()):
                heappush(queue, (arrive + lower[target], next(serial), target, arrive, legs + local_legs))
            for depart in search.departures(node, tick):
                if depart < tick or not view.available(f"node:{node}", tick, depart):
                    continue
                for target, travel, edge_id in topology.outgoing[node]:
                    if topology.partitions[target] == region or target not in lower:
                        continue
                    arrive = depart + travel
                    if arrive + lower[target] <= limit and view.available(f"edge:{edge_id}", depart, arrive):
                        heappush(queue, (arrive + lower[target], next(serial), target, arrive,
                                         legs + (Leg(edge_id, depart, arrive),)))
    except _SearchBudgetExpired:
        return _finish(owner, candidates)
    return _finish(owner, candidates, exhausted=True)


class FullGraphReferenceGenerator(RegionalCandidateGenerator):
    """Reverse-Dijkstra A*, without portal abstraction.

    integer_ticks=True is a small-graph oracle for earliest arrival in the
    finite integer horizon. Exhaustion before the first valid arrival disables
    its earliest certificate; truncation of later labels does not revoke that
    already established earliest result. Event mode uses the same departure representation as dynamic local
    search for a fairer computation comparison than the old zero heuristic.
    """
    def __init__(self, horizon=80, expansion_limit=5000, deadline_ms=80., *, integer_ticks=False):
        if type(integer_ticks) is not bool:
            raise ValueError("integer_ticks must be a bool")
        super().__init__(horizon=horizon, expansion_limit=expansion_limit, deadline_ms=deadline_ms)
        self.integer_ticks = integer_ticks

    def _generate(self, snapshot, bag_id, tray_id, destination, k):
        self._started = perf_counter()
        self.last_expansions, self.last_search_status = 0, "searching"
        self.last_diagnostics = {"validation_ms": 0., "work_units_by_stage": {}, "preprocessing_budget_included": True,
                                 "completeness": "finite_integer_earliest" if self.integer_ticks else "bounded_event_time_full_graph",
                                 "earliest_arrival_certified": False, "finite_horizon_exhausted": False,
                                 "missing_candidate_is_not_infeasibility": True}
        tray = snapshot.trays.get(tray_id)
        if (k < 1 or tray is None or tray.node is None or tray_id in snapshot.plans
                or tray.available_at > snapshot.now or destination not in snapshot.network.nodes
                or any(f.tray_id == tray_id and f.arrive > snapshot.now for f in snapshot.old_in_transit)
                or (bag_id is not None and (tray.mode != "loaded" or tray.bag_id != bag_id))
                or (bag_id is None and (tray.mode != "empty" or tray.bag_id is not None))):
            self.last_search_status = "invalid_request"
            return _finish(self, [])
        candidates = []
        try:
            signature = network_signature(snapshot.network)
            self.last_diagnostics["cold_topology"] = signature not in _TOPOLOGY_CACHE
            topology = _topology(signature, self._consume)
            lower = topology.lower_bounds(destination, self._consume)
            if tray.node not in lower:
                self.last_search_status = "static_unreachable"
                return _finish(self, [])
            limit = snapshot.now + self.horizon
            if bag_id is not None and snapshot.bags[bag_id].protected:
                limit = min(limit, snapshot.bags[bag_id].deadline - snapshot.module.unload_ticks)
            self.last_diagnostics["static_lower_bound"] = lower[tray.node]
            search = EventTimeSearch(self, snapshot, topology, lower, _ResourceView(snapshot, tray_id), limit,
                                     integer_ticks=self.integer_ticks)
            for _, tick, legs in search.paths(tray.node, snapshot.now, {destination}, labels_per_state=k,
                                             stop_at_targets=False):
                candidate = _proposal(self, snapshot, bag_id, tray_id, destination, legs, tick, len(candidates), "full_graph")
                if candidate is not None:
                    candidates.append(candidate)
                    self.last_diagnostics["earliest_arrival_certified"] = self.integer_ticks
                    if len(candidates) >= k:
                        self.last_search_status = "candidate_limit_reached"
                        return _finish(self, candidates)
        except _SearchBudgetExpired:
            # If an integer search already found a valid earliest candidate,
            # that earliest certificate survives truncation of later K labels.
            return _finish(self, candidates)
        self.last_diagnostics["finite_horizon_exhausted"] = self.integer_ticks
        return _finish(self, candidates, exhausted=True)
