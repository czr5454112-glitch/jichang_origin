"""Bounded routing and a causal, fixed-rule discrete-event proxy simulator.

Accepted whole routes are conservatively frozen until release. New routing
requests are supported at stationary nodes; rerouting an entered edge or an
accepted itinerary is deliberately outside this pilot. Every occupied node is
reserved until the next accepted departure, including terminal empty stock.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from heapq import heappop, heappush
from itertools import count
from threading import RLock

from .model import (
    Bag, InFlight, Leg, Reservation, RolloutResult, RouteCandidate, Snapshot,
    Tray, ValidationResult,
)

INFINITY = 10**12
_OWNER_LOCK = RLock()
COST_WEIGHTS = {
    "tray_wait": 1.0, "nonprotected_tardiness": 1.0,
    "empty_distance": 0.1, "terminal_backlog": 10.0,
    "terminal_inflight": 2.0,
}


def _destination(snapshot: Snapshot, candidate: RouteCandidate) -> str:
    if candidate.bag_id is not None:
        return snapshot.bags[candidate.bag_id].destination
    if candidate.destination_node is None:
        raise ValueError("empty transfer requires destination_node")
    return candidate.destination_node


def candidate_reservations(snapshot: Snapshot, candidate: RouteCandidate) -> tuple[Reservation, ...]:
    """Physical occupancy, including waiting and terminal reception/stock."""
    tray = snapshot.trays[candidate.tray_id]
    node, tick = tray.node, snapshot.now
    result: list[Reservation] = []
    for leg in candidate.legs:
        if leg.depart > tick:
            result.append(Reservation(f"node:{node}", tick, leg.depart, tray.tray_id))
        result.append(Reservation(f"edge:{leg.edge_id}", leg.depart, leg.arrive, tray.tray_id))
        node, tick = snapshot.network.edges[leg.edge_id].target, leg.arrive
    result.append(Reservation(f"node:{node}", tick, INFINITY, tray.tray_id))
    if candidate.usable_at > tick:
        result.append(Reservation(f"reception:{node}", tick, candidate.usable_at, tray.tray_id))
    return tuple(result)


def _merge_reservations(reservations: list[Reservation] | tuple[Reservation, ...], now: int) -> tuple[Reservation, ...]:
    # Duplicate descriptions of one physical tray never consume two units.
    groups: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for item in reservations:
        if item.end > max(item.start, now):
            groups[item.resource, item.tray_id].append((max(now, item.start), item.end))
    result = []
    for (resource, tray_id), intervals in sorted(groups.items()):
        merged: list[list[int]] = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        result.extend(Reservation(resource, start, end, tray_id) for start, end in merged)
    return tuple(result)


def effective_reservations(snapshot: Snapshot) -> tuple[Reservation, ...]:
    """Include idle stock and irrevocable old transit, even without explicit slots."""
    result = list(snapshot.reservations)
    old_ids = set()
    for flight in snapshot.old_in_transit:
        old_ids.add(flight.tray_id)
        edge = snapshot.network.edges[flight.edge_id]
        result.extend((
            Reservation(f"edge:{edge.edge_id}", flight.depart, flight.arrive, flight.tray_id),
            Reservation(f"node:{edge.target}", flight.arrive, INFINITY, flight.tray_id),
        ))
        tray = snapshot.trays[flight.tray_id]
        if tray.bag_id is None or snapshot.bags[tray.bag_id].destination == edge.target:
            result.append(Reservation(
                f"reception:{edge.target}", flight.arrive,
                flight.arrive + (snapshot.module.unload_ticks if tray.bag_id else 0) + snapshot.module.hold_ticks(edge.target),
                tray.tray_id,
            ))
    for tray in snapshot.trays.values():
        if tray.tray_id not in snapshot.plans and tray.tray_id not in old_ids and tray.node is not None:
            result.append(Reservation(f"node:{tray.node}", snapshot.now, INFINITY, tray.tray_id))
            if tray.mode in ("unloading", "holding") and tray.available_at > snapshot.now:
                result.append(Reservation(f"reception:{tray.node}", snapshot.now, tray.available_at, tray.tray_id))
    return _merge_reservations(result, snapshot.now)


def capacity_conflict(snapshot: Snapshot, reservations: tuple[Reservation, ...]) -> str | None:
    """Sweep half-open intervals; release happens before acquisition at a tie."""
    events: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for slot in _merge_reservations(reservations, snapshot.now):
        if slot.tray_id not in snapshot.trays:
            return f"unknown_reservation_owner:{slot.tray_id}"
        events[slot.resource][slot.start] += 1
        events[slot.resource][slot.end] -= 1
    for resource in sorted(events):
        kind, _, key = resource.partition(":")
        if kind == "node" and key in snapshot.network.nodes:
            capacity = snapshot.network.nodes[key].capacity
        elif kind == "edge" and key in snapshot.network.edges:
            capacity = snapshot.network.edges[key].capacity
        elif kind == "reception" and key in snapshot.network.nodes:
            capacity = snapshot.module.reception_capacity
        else:
            return f"unknown_resource:{resource}"
        occupancy = 0
        for tick, delta in sorted(events[resource].items()):
            occupancy += delta
            if occupancy > capacity:
                return f"capacity:{resource}@{tick}"
    return None


class ExecutionValidator:
    """The resource owner revalidates the complete proposal before any mutation."""

    def validate(self, snapshot: Snapshot, candidate: RouteCandidate) -> ValidationResult:
        def reject(reason: str) -> ValidationResult:
            return ValidationResult(False, reason)

        if candidate.dependency_version != snapshot.version:
            return reject("stale_version")
        if candidate.tray_id not in snapshot.trays:
            return reject("unknown_tray")
        tray = snapshot.trays[candidate.tray_id]
        if any(f.tray_id == tray.tray_id and f.arrive > snapshot.now for f in snapshot.old_in_transit):
            return reject("old_in_transit_irrevocable")
        if tray.node is None or tray.mode == "in_transit":
            return reject("entered_edge_irrevocable")
        if tray.tray_id in snapshot.plans:
            return reject("accepted_itinerary_irrevocable")
        if tray.available_at > snapshot.now:
            return reject("tray_not_available")
        if candidate.bag_id is not None:
            if candidate.bag_id not in snapshot.bags:
                return reject("unknown_bag")
            bag = snapshot.bags[candidate.bag_id]
            if bag.arrival > snapshot.now or bag.bag_id in snapshot.completed:
                return reject("bag_not_active")
            if tray.mode != "loaded" or tray.bag_id != candidate.bag_id:
                return reject("source_not_carrying_bag")
        else:
            if tray.mode != "empty" or tray.bag_id is not None:
                return reject("source_not_empty")
            if candidate.destination_node not in snapshot.network.nodes:
                return reject("unknown_destination")
            source_zone = snapshot.network.nodes[tray.node].logistics_zone
            target_zone = snapshot.network.nodes[candidate.destination_node].logistics_zone
            stock = sum(t.mode == "empty" and t.available_at <= snapshot.now and t.node is not None
                        and t.tray_id not in snapshot.plans
                        and snapshot.network.nodes[t.node].logistics_zone == source_zone
                        for t in snapshot.trays.values())
            if source_zone != target_zone and stock <= snapshot.module.export_min_stock:
                return reject("module_export_min_stock")
        node, tick = tray.node, snapshot.now
        for leg in candidate.legs:
            if leg.edge_id not in snapshot.network.edges:
                return reject("unknown_edge")
            edge = snapshot.network.edges[leg.edge_id]
            if not isinstance(leg.depart, int) or not isinstance(leg.arrive, int):
                return reject("noninteger_time")
            if edge.source != node or leg.depart < tick or leg.arrive != leg.depart + edge.travel_time:
                return reject("invalid_path_or_time")
            if leg.depart > tick and not snapshot.network.nodes[node].can_wait:
                return reject("waiting_forbidden")
            node, tick = edge.target, leg.arrive
        if node != _destination(snapshot, candidate):
            return reject("wrong_destination")
        unload = tick + (snapshot.module.unload_ticks if candidate.bag_id is not None else 0)
        usable = unload + snapshot.module.hold_ticks(node)
        if candidate.unload_complete != unload or candidate.usable_at != usable:
            return reject("module_response_mismatch")
        if not snapshot.network.nodes[node].can_wait:
            return reject("terminal_waiting_forbidden")
        if candidate.bag_id is not None and bag.protected and unload > bag.deadline:
            return reject("protected_deadline")
        slots = tuple(s for s in effective_reservations(snapshot) if s.tray_id != tray.tray_id)
        conflict = capacity_conflict(snapshot, slots + candidate_reservations(snapshot, candidate))
        return reject(conflict) if conflict else ValidationResult(True, "accepted")

    def commit(self, snapshot: Snapshot, candidate: RouteCandidate) -> ValidationResult:
        with _OWNER_LOCK:
            result = self.validate(snapshot, candidate)
            if not result.accepted:
                return result
            # A local owner lock makes compare/revalidate/publish atomic against
            # other commits. No distributed transaction protocol is claimed.
            slots = tuple(s for s in effective_reservations(snapshot) if s.tray_id != candidate.tray_id)
            snapshot.reservations = _merge_reservations(slots + candidate_reservations(snapshot, candidate), snapshot.now)
            snapshot.plans[candidate.tray_id] = candidate
            snapshot.version += 1
            return result


class CandidateGenerator:
    """Bounded uniform-cost search on simple directed paths with time labels.

    Zero heuristic is admissible A*. Non-waitable nodes keep their exact
    arrival label. Distinct candidates have distinct edge sequences. Search
    truncation is reported separately from absence inside the bounded model.
    """

    def __init__(self, expansion_limit: int = 2000, horizon: int = 80):
        self.expansion_limit = expansion_limit
        self.horizon = horizon
        self.last_search_status = "not_started"
        self.last_expansions = 0

    def generate(self, snapshot: Snapshot, bag_id: str, tray_id: str, k: int = 3) -> tuple[RouteCandidate, ...]:
        if bag_id not in snapshot.bags:
            self.last_search_status = "invalid_request"
            return ()
        return self._generate(snapshot, bag_id, tray_id, snapshot.bags[bag_id].destination, k)

    def generate_empty(self, snapshot: Snapshot, tray_id: str, destination: str, k: int = 1) -> tuple[RouteCandidate, ...]:
        return self._generate(snapshot, None, tray_id, destination, k)

    def _generate(self, snapshot: Snapshot, bag_id: str | None, tray_id: str, destination: str, k: int) -> tuple[RouteCandidate, ...]:
        self.last_expansions = 0
        tray = snapshot.trays.get(tray_id)
        if (tray is None or tray.node is None or tray_id in snapshot.plans
                or tray.available_at > snapshot.now or destination not in snapshot.network.nodes
                or any(f.tray_id == tray_id and f.arrive > snapshot.now for f in snapshot.old_in_transit)):
            self.last_search_status = "invalid_request"
            return ()
        if (bag_id is not None and (tray.mode != "loaded" or tray.bag_id != bag_id)) or (bag_id is None and tray.mode != "empty"):
            self.last_search_status = "invalid_request"
            return ()
        adjacency: dict[str, list] = defaultdict(list)
        for edge in sorted(snapshot.network.edges.values(), key=lambda edge: edge.edge_id):
            adjacency[edge.source].append(edge)
        others = tuple(s for s in effective_reservations(snapshot) if s.tray_id != tray_id)
        serial = count()
        queue = [(snapshot.now, next(serial), tray.node, (), (tray.node,))]
        enqueued = set()
        found: list[RouteCandidate] = []
        seen_paths: set[tuple[str, ...]] = set()
        validator = ExecutionValidator()
        limit_tick = snapshot.now + self.horizon
        baseline_id = f"v{snapshot.version}:{bag_id or 'empty'}:{tray_id}:0"
        while queue and self.last_expansions < self.expansion_limit and len(found) < k:
            tick, _, node, legs, visited = heappop(queue)
            self.last_expansions += 1
            if node == destination:
                path = tuple(leg.edge_id for leg in legs)
                if path in seen_paths:
                    continue
                unload = tick + (snapshot.module.unload_ticks if bag_id is not None else 0)
                candidate = RouteCandidate(
                    f"v{snapshot.version}:{bag_id or 'empty'}:{tray_id}:{len(found)}", bag_id,
                    tray_id, legs, unload, unload + snapshot.module.hold_ticks(node),
                    snapshot.version, baseline_id, len(found) == 0, destination,
                )
                if validator.validate(snapshot, candidate).accepted:
                    found.append(candidate)
                    seen_paths.add(path)
                continue
            for edge in adjacency[node]:
                if edge.target in visited:
                    continue
                # Every feasible departure label is retained, since delaying at
                # an earlier waitable node can be necessary before a no-wait node.
                departures = range(tick, limit_tick - edge.travel_time + 1) if snapshot.network.nodes[node].can_wait else (tick,)
                for depart in departures:
                    arrive = depart + edge.travel_time
                    if arrive > limit_tick:
                        break
                    partial = list(others)
                    previous_node, previous_tick = tray.node, snapshot.now
                    for old_leg in legs:
                        if old_leg.depart > previous_tick:
                            partial.append(Reservation(f"node:{previous_node}", previous_tick, old_leg.depart, tray_id))
                        partial.append(Reservation(f"edge:{old_leg.edge_id}", old_leg.depart, old_leg.arrive, tray_id))
                        previous_node, previous_tick = snapshot.network.edges[old_leg.edge_id].target, old_leg.arrive
                    if depart > tick:
                        partial.append(Reservation(f"node:{node}", tick, depart, tray_id))
                    partial.append(Reservation(f"edge:{edge.edge_id}", depart, arrive, tray_id))
                    if capacity_conflict(snapshot, tuple(partial)) is None:
                        label = (tuple(leg.edge_id for leg in legs) + (edge.edge_id,), arrive)
                        if label not in enqueued:
                            enqueued.add(label)
                            heappush(queue, (arrive, next(serial), edge.target, legs + (Leg(edge.edge_id, depart, arrive),), visited + (edge.target,)))
        self.last_search_status = ("complete" if len(found) >= k else
                                   "exhausted" if queue and self.last_expansions >= self.expansion_limit else
                                   "bounded_search_finished")
        return tuple(found)


def assert_invariants(snapshot: Snapshot) -> None:
    """Identity, physical occupancy and committed future occupancy checks."""
    carried: set[str] = set()
    physical_edges: dict[str, int] = defaultdict(int)
    slots = effective_reservations(snapshot)
    assert snapshot.module.unload_ticks >= 0 and snapshot.module.reception_capacity > 0
    assert all(hold >= 0 for hold in snapshot.module.hold_by_node.values())
    for edge_id, edge in snapshot.network.edges.items():
        assert edge_id == edge.edge_id and edge.source in snapshot.network.nodes and edge.target in snapshot.network.nodes
        assert isinstance(edge.travel_time, int) and edge.travel_time > 0 and edge.capacity > 0
    old_ids = [flight.tray_id for flight in snapshot.old_in_transit]
    assert len(old_ids) == len(set(old_ids)), "multiple old flights for one tray"
    assert not (set(old_ids) & set(snapshot.plans)), "old flight overwritten by new itinerary"
    for key, tray in snapshot.trays.items():
        assert key == tray.tray_id, "tray identity key mismatch"
        assert tray.mode in {"empty", "loaded", "in_transit", "unloading", "holding"}, "unknown tray mode"
        assert tray.node is None or tray.node in snapshot.network.nodes, "unknown tray node"
        assert tray.mode != "in_transit" or tray.node is None, "in-transit tray parked at node"
        assert tray.node is not None or tray.mode == "in_transit", "stationary tray without node"
        if tray.mode == "in_transit":
            old = [f for f in snapshot.old_in_transit if f.tray_id == key and f.depart <= snapshot.now < f.arrive]
            active = [leg for leg in snapshot.plans[key].legs if leg.depart <= snapshot.now < leg.arrive] if key in snapshot.plans else []
            # A release-before-acquire event prefix can temporarily retain a
            # just-arrived tray while another tray departs at the same tick.
            just_arrived = any(f.tray_id == key and f.arrive == snapshot.now for f in snapshot.old_in_transit)
            just_arrived |= key in snapshot.plans and any(leg.arrive == snapshot.now for leg in snapshot.plans[key].legs)
            assert len(old) + len(active) == 1 or just_arrived, "moving tray has no physical edge witness"
            if old or active:
                edge_id = (old or active)[0].edge_id
                physical_edges[edge_id] += 1
                assert any(slot.tray_id == key and slot.resource == f"edge:{edge_id}"
                           and slot.start <= snapshot.now < slot.end for slot in slots), "physical edge occupancy not reserved"
        if tray.bag_id is not None:
            assert tray.bag_id in snapshot.bags, "lost bag identity"
            assert tray.bag_id not in carried, "bag carried on multiple trays"
            assert tray.bag_id not in snapshot.completed, "completed bag still loaded"
            carried.add(tray.bag_id)
        assert tray.mode != "empty" or tray.bag_id is None, "empty tray carries bag"
        assert tray.mode != "loaded" or tray.bag_id is not None, "loaded tray has no bag"
    for bag_id, bag in snapshot.bags.items():
        assert bag_id == bag.bag_id and bag.arrival <= snapshot.now, "future or mismatched bag visible"
    assert set(snapshot.completed) <= set(snapshot.bags), "completed bag missing from ledger"
    conflict = capacity_conflict(snapshot, effective_reservations(snapshot))
    assert conflict is None, conflict
    physical: dict[str, int] = defaultdict(int)
    for tray in snapshot.trays.values():
        if tray.node is not None:
            physical[tray.node] += 1
    assert all(value <= snapshot.network.nodes[node].capacity for node, value in physical.items()), "physical node capacity"
    assert all(value <= snapshot.network.edges[edge].capacity for edge, value in physical_edges.items()), "physical edge capacity"


def simulate(snapshot: Snapshot, candidate: RouteCandidate | None, future_bags: tuple[Bag, ...] | list[Bag], horizon: int) -> RolloutResult:
    """Run until absolute tick ``horizon``; future input is event-engine-only.

    The same fixed continuation is used after each first candidate: FIFO loads,
    earliest feasible route, then demand-triggered empty dispatch. A waiting
    bag remains in the ledger when no tray/path exists. Terminal backlog counts
    all uncompleted bags and terminal inflight counts moving trays, intentionally
    charging both when a loaded tray is still traveling at the horizon.
    """
    state = snapshot.clone()
    if horizon < state.now:
        raise ValueError("horizon precedes snapshot")
    tray_ids = set(state.trays)
    trace: list[dict] = []
    components = {name: 0.0 for name in COST_WEIGHTS}
    checks = 0
    validator = ExecutionValidator()
    generator = CandidateGenerator(horizon=max(20, horizon - state.now + 10))
    arrivals: dict[int, list[Bag]] = defaultdict(list)
    entered_legs: set[tuple[str, str, int]] = set()
    for bag in future_bags:
        if bag.arrival < state.now or bag.bag_id in state.bags:
            raise ValueError("future event overlaps the initial observable ledger")
        arrivals[bag.arrival].append(bag)
    if len({bag.bag_id for bags in arrivals.values() for bag in bags}) != sum(map(len, arrivals.values())):
        raise ValueError("duplicate future bag ID")

    def check(event: str, **details) -> None:
        nonlocal checks
        assert set(state.trays) == tray_ids, "finite tray identity set changed"
        assert_invariants(state)
        checks += 1
        trace.append({"time": state.now, "event": event, **details})

    check("initial")
    # Existing loaded bags may predate the observation. Their past tray wait is
    # a branch-common constant and is excluded; future waiting is integrated.
    for tray in state.trays.values():
        if tray.bag_id is not None:
            state.load_times.setdefault(tray.bag_id, state.now)
    if candidate is not None:
        result = validator.commit(state, candidate)
        if not result.accepted:
            raise ValueError(f"initial candidate rejected: {result.reason}")
        check("initial_commit", candidate_id=candidate.candidate_id)

    def update_motion() -> None:
        # Departure/release is processed before arrivals/acquisitions at a tick.
        # Synchronization builds the atomic simultaneous physical state first;
        # per-event checks then see the released-before-acquired valid prefix.
        departing = []
        for tray_id, plan in list(state.plans.items()):
            tray = state.trays[tray_id]
            leg = next((leg for leg in plan.legs if leg.depart <= state.now < leg.arrive), None)
            if leg is not None:
                if tray.node is not None:
                    state.trays[tray_id] = replace(tray, node=None, mode="in_transit")
                entry = (tray_id, leg.edge_id, leg.depart)
                if entry not in entered_legs:
                    entered_legs.add(entry)
                    departing.append((tray_id, leg))
        for tray_id, leg in departing:
            if state.plans[tray_id].bag_id is None and leg.depart == state.now:
                components["empty_distance"] += state.network.edges[leg.edge_id].travel_time
            check("depart", tray_id=tray_id, edge_id=leg.edge_id)
        for flight in tuple(state.old_in_transit):
            if flight.arrive > state.now:
                continue
            tray = state.trays[flight.tray_id]
            node = state.network.edges[flight.edge_id].target
            state.old_in_transit = tuple(f for f in state.old_in_transit if f != flight)
            state.reservations = tuple(r for r in state.reservations if r.tray_id != tray.tray_id)
            hold = state.module.hold_ticks(node)
            state.trays[tray.tray_id] = replace(
                tray, node=node, mode="loaded" if tray.bag_id else "holding" if hold else "empty",
                available_at=state.now if tray.bag_id else state.now + hold,
            )
            if tray.bag_id is not None and state.bags[tray.bag_id].destination == node:
                unload = state.now + state.module.unload_ticks
                plan_id = f"old:{tray.tray_id}:{state.now}"
                plan = RouteCandidate(plan_id, tray.bag_id, tray.tray_id, (), unload, unload + hold,
                                      state.version, plan_id, destination_node=node)
                state.plans[tray.tray_id] = plan
                state.reservations += candidate_reservations(state, plan)
            state.version += 1
            check("old_arrive", tray_id=tray.tray_id, node=node)
        for tray_id, plan in list(state.plans.items()):
            tray = state.trays[tray_id]
            if any(leg.depart <= state.now < leg.arrive for leg in plan.legs):
                continue
            past = [leg for leg in plan.legs if leg.arrive <= state.now]
            node = state.network.edges[past[-1].edge_id].target if past else tray.node
            arrival = plan.legs[-1].arrive if plan.legs else state.now
            if state.now < arrival:
                if tray.node is None:
                    state.trays[tray_id] = replace(tray, node=node, mode="loaded" if tray.bag_id else "empty")
                    check("intermediate_arrive", tray_id=tray_id, node=node)
                continue
            if tray.node is None:
                tray = replace(tray, node=node)
            if plan.bag_id is not None and state.now < plan.unload_complete:
                new_tray = replace(tray, mode="unloading", available_at=plan.usable_at)
            else:
                if plan.bag_id is not None and plan.bag_id not in state.completed:
                    state.completed[plan.bag_id] = plan.unload_complete
                    trace.append({"time": state.now, "event": "unload_complete", "bag_id": plan.bag_id, "tray_id": tray_id})
                new_tray = replace(tray, bag_id=None, mode="holding" if state.now < plan.usable_at else "empty", available_at=plan.usable_at)
            changed = new_tray != state.trays[tray_id]
            state.trays[tray_id] = new_tray
            if state.now >= plan.usable_at:
                del state.plans[tray_id]
                state.reservations = tuple(r for r in state.reservations if r.tray_id != tray_id)
                state.version += 1
            if changed:
                check("tray_state", tray_id=tray_id, mode=new_tray.mode, node=node)
        for tray_id, tray in list(state.trays.items()):
            if tray_id not in state.plans and tray.mode == "holding" and tray.available_at <= state.now:
                state.trays[tray_id] = replace(tray, mode="empty")
                state.version += 1
                check("module_release", tray_id=tray_id)

    def continue_causally() -> None:
        # Only state.bags is available here; arrivals is never read by control.
        carried = {tray.bag_id for tray in state.trays.values() if tray.bag_id}
        waiting = sorted((bag for bag in state.bags.values() if bag.bag_id not in state.completed
                          and bag.bag_id not in carried), key=lambda bag: (bag.arrival, bag.bag_id))
        for bag in waiting:
            free = sorted((tray for tray in state.trays.values() if tray.mode == "empty"
                           and tray.node == bag.origin and tray.available_at <= state.now
                           and tray.tray_id not in state.plans), key=lambda tray: tray.tray_id)
            if not free:
                continue
            tray = free[0]
            state.trays[tray.tray_id] = replace(tray, mode="loaded", bag_id=bag.bag_id)
            state.load_times[bag.bag_id] = state.now
            state.version += 1
            check("load", bag_id=bag.bag_id, tray_id=tray.tray_id)
        for tray in sorted(state.trays.values(), key=lambda tray: tray.tray_id):
            if tray.mode != "loaded" or tray.tray_id in state.plans:
                continue
            candidates = generator.generate(state, tray.bag_id, tray.tray_id, k=1)
            if candidates:
                result = validator.commit(state, candidates[0])
                assert result.accepted, result.reason
                check("route_commit", candidate_id=candidates[0].candidate_id)
        carried = {tray.bag_id for tray in state.trays.values() if tray.bag_id}
        waiting = sorted((bag for bag in state.bags.values() if bag.bag_id not in state.completed
                          and bag.bag_id not in carried), key=lambda bag: (bag.arrival, bag.bag_id))
        reserved_origins: dict[str, int] = defaultdict(int)
        for plan in state.plans.values():
            if plan.bag_id is None:
                reserved_origins[_destination(state, plan)] += 1
        for bag in waiting:
            if reserved_origins[bag.origin]:
                reserved_origins[bag.origin] -= 1
                continue
            choices = []
            for tray in sorted(state.trays.values(), key=lambda tray: tray.tray_id):
                if tray.mode != "empty" or tray.node == bag.origin or tray.tray_id in state.plans:
                    continue
                options = generator.generate_empty(state, tray.tray_id, bag.origin, k=1)
                if options:
                    choices.append(options[0])
            if choices:
                choice = min(choices, key=lambda option: (option.usable_at, option.tray_id))
                result = validator.commit(state, choice)
                assert result.accepted, result.reason
                check("empty_dispatch", candidate_id=choice.candidate_id, visible_bag_id=bag.bag_id)

    start = state.now
    for tick in range(start, horizon + 1):
        if tick != state.now:
            state.now = tick
            state.version += 1
            state.reservations = tuple(r for r in state.reservations if r.end > tick)
        update_motion()
        for bag in sorted(arrivals.get(tick, []), key=lambda bag: bag.bag_id):
            state.bags[bag.bag_id] = bag
            state.version += 1
            check("bag_arrival", bag_id=bag.bag_id)
        if tick < horizon:
            continue_causally()
            update_motion()
            components["tray_wait"] += sum(bag_id not in state.load_times and bag_id not in state.completed for bag_id in state.bags)
            assert all(tray.node is None or state.network.nodes[tray.node].can_wait for tray in state.trays.values()), "tray left waiting at a non-waitable node"
        check("tick")
    uncompleted = tuple(sorted(set(state.bags) - set(state.completed)))
    carried = {tray.bag_id for tray in state.trays.values() if tray.bag_id}
    waiting = tuple(sorted(set(uncompleted) - carried))
    components["nonprotected_tardiness"] = float(sum(
        max(0, state.completed.get(bag_id, horizon) - bag.deadline)
        for bag_id, bag in state.bags.items() if not bag.protected
    ))
    components["terminal_backlog"] = float(len(uncompleted))
    components["terminal_inflight"] = float(sum(tray.mode == "in_transit" for tray in state.trays.values()))
    return RolloutResult(
        components, sum(COST_WEIGHTS[key] * value for key, value in components.items()),
        dict(state.completed), waiting, uncompleted, dict(state.trays), tuple(trace), checks, state,
    )
