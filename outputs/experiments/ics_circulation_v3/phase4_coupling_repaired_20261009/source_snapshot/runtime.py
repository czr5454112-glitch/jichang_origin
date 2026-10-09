"""Bounded routing and a causal, fixed-rule discrete-event proxy simulator.

Whole-route mode conservatively freezes accepted itineraries until release,
unless an explicitly permitted loaded, unprotected suffix is atomically replaced.
Next-edge mode validates a full witness, then commits only the shortest prefix
ending at a waitable node. Ordinary commits never cancel accepted plans. The
separate replacement transaction preserves entered/uninterruptible segments.
Every occupied node is reserved until its next accepted departure.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from heapq import heappop, heappush
from itertools import count
from threading import RLock
from inspect import signature
from time import perf_counter

from .model import (
    Bag, InFlight, Leg, Reservation, RolloutResult, RouteCandidate, Snapshot,
    Tray, ValidationResult, SimulationCheckpoint, ConditionalRouteForecast,
    ForecastDependency, ReplacementContext,
)

INFINITY = 10**12
_OWNER_LOCK = RLock()
COST_WEIGHTS = {
    "tray_wait": 1.0, "nonprotected_tardiness": 1.0,
    "empty_distance": 0.1, "terminal_backlog": 10.0,
    "terminal_inflight": 2.0,
}


def _destination(snapshot: Snapshot, candidate: RouteCandidate) -> str:
    if candidate.prefix_only and candidate.destination_node is not None:
        return candidate.destination_node
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


def _fingerprint(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             default=lambda x: sorted(x) if isinstance(x, set) else asdict(x),
                             allow_nan=False).encode()).hexdigest()


def _forecast_dependencies(snapshot, candidate):
    resources = {f"edge:{leg.edge_id}" for leg in candidate.legs}
    resources |= {f"node:{snapshot.network.edges[leg.edge_id].target}" for leg in candidate.legs}
    resources.add(f"module:{_destination(snapshot, candidate)}")
    return tuple(ForecastDependency(resource, _dependency_fingerprint(snapshot, resource)) for resource in sorted(resources))


def _dependency_fingerprint(snapshot, resource):
    kind, key = resource.split(":", 1)
    if kind == "edge":
        return _fingerprint(snapshot.network.edges.get(key))
    if kind == "node":
        return _fingerprint(snapshot.network.nodes.get(key))
    return _fingerprint(snapshot.module)


def _revise_forecast(snapshot, previous, **updates):
    revision = previous.revision + 1
    current = replace(previous, forecast_id=f"{previous.tray_id}:forecast:{revision}",
                      revision=revision, parent_forecast_id=previous.forecast_id,
                      updated_at=snapshot.now, source_version=snapshot.version, **updates)
    snapshot.forecast_history += (previous,)
    snapshot.conditional_forecasts[previous.tray_id] = current
    return current


def _publish_forecast(snapshot, witness, committed):
    previous = snapshot.conditional_forecasts.get(witness.tray_id)
    if not committed.prefix_only:
        if previous is not None:
            _revise_forecast(snapshot, previous, status="firm", reason="replaced_by_complete_commitment",
                             bag_id=witness.bag_id, destination_node=_destination(snapshot, witness),
                             unload_complete=witness.unload_complete, usable_at=witness.usable_at,
                             witness_legs=witness.legs,
                             remaining_legs=tuple(leg for leg in witness.legs if leg.arrive > snapshot.now),
                             created_at=snapshot.now, dependencies=_forecast_dependencies(snapshot, witness))
        return
    revision = previous.revision + 1 if previous else 1
    if previous:
        snapshot.forecast_history += (previous,)
    snapshot.conditional_forecasts[witness.tray_id] = ConditionalRouteForecast(
        f"{witness.tray_id}:forecast:{revision}", witness.tray_id, witness.bag_id,
        _destination(snapshot, witness), witness.unload_complete, witness.usable_at,
        witness.legs, tuple(leg for leg in witness.legs if leg.arrive > snapshot.now),
        snapshot.now, snapshot.now, snapshot.version, revision,
        previous.forecast_id if previous else None, _forecast_dependencies(snapshot, witness),
    )


def conditional_forecast_failure(snapshot: Snapshot, forecast: ConditionalRouteForecast) -> str | None:
    """Read-only freshness/feasibility check, also usable by forecast consumers."""
    if forecast.status != "active":
        return forecast.reason
    tray = snapshot.trays.get(forecast.tray_id)
    if tray is None or tray.bag_id != forecast.bag_id:
        return "identity_or_load_changed"
    if forecast.bag_id in snapshot.completed:
        return "bag_completed"
    if forecast.usable_at < snapshot.now:
        return "predicted_release_missed"
    for dependency in forecast.dependencies:
        # Passed edges may disappear from future planning, but their completed
        # history cannot invalidate a surviving remaining prediction.
        if dependency.resource.startswith("edge:") and not any(
                "edge:" + leg.edge_id == dependency.resource and leg.arrive > snapshot.now for leg in forecast.witness_legs):
            continue
        if _dependency_fingerprint(snapshot, dependency.resource) != dependency.fingerprint:
            return "dependency_changed:" + dependency.resource
    plan = snapshot.plans.get(forecast.tray_id)
    for leg in forecast.witness_legs:
        if leg.arrive > snapshot.now and leg.depart < snapshot.now and (plan is None or leg not in plan.legs):
            return "uncommitted_departure_missed"
    # Recheck the full conditional reservation witness against CURRENT other
    # commitments. Its own safe-prefix terminal reservation is replaced only in
    # this private calculation; no prediction acquires or releases a resource.
    if any(leg.edge_id not in snapshot.network.edges for leg in forecast.witness_legs):
        return "witness_edge_missing"
    origin = snapshot.network.edges[forecast.witness_legs[0].edge_id].source if forecast.witness_legs else tray.node
    # Only these two fields are used differently by candidate_reservations;
    # avoid copying an ever-growing history for a read-only calendar check.
    view = replace(snapshot, now=forecast.created_at,
                   trays={**snapshot.trays, tray.tray_id: replace(tray, node=origin)})
    witness = RouteCandidate("forecast", forecast.bag_id, forecast.tray_id, forecast.witness_legs,
                             forecast.unload_complete, forecast.usable_at, snapshot.version, "forecast",
                             destination_node=forecast.destination_node)
    slots = tuple(s for s in effective_reservations(snapshot) if s.tray_id != tray.tray_id)
    conflict = capacity_conflict(snapshot, slots + candidate_reservations(view, witness))
    return "conditional_" + conflict if conflict else None


def refresh_conditional_forecasts(snapshot: Snapshot) -> None:
    """Advance predictions deterministically; invalid records never reactivate."""
    changed = False
    for forecast in tuple(snapshot.conditional_forecasts.values()):
        if forecast.status == "firm" and snapshot.now >= forecast.usable_at:
            tray = snapshot.trays.get(forecast.tray_id)
            if tray is not None and tray.mode == "empty" and tray.bag_id is None:
                _revise_forecast(snapshot, forecast, status="realized", reason="physical_empty_release")
                changed = True
            continue
        if forecast.status != "active":
            continue
        reason = conditional_forecast_failure(snapshot, forecast)
        if reason:
            _revise_forecast(snapshot, forecast, status="invalid", reason=reason)
            changed = True
        else:
            remaining = tuple(leg for leg in forecast.witness_legs if leg.arrive > snapshot.now)
            if remaining != forecast.remaining_legs:
                _revise_forecast(snapshot, forecast, remaining_legs=remaining, reason="physical_progress")
                changed = True
    if changed:
        snapshot.version += 1


def invalidate_conditional_forecasts(snapshot: Snapshot, reason: str, resources=()) -> None:
    """Explicit observed fault/revision notification, without cancelling motion."""
    if not reason:
        raise ValueError("invalidation_reason_required")
    resources = set(resources)
    with _OWNER_LOCK:
        selected = [f for f in snapshot.conditional_forecasts.values() if f.status == "active"
                    and (not resources or resources & {d.resource for d in f.dependencies})]
        if selected:
            snapshot.version += 1
        for forecast in selected:
            _revise_forecast(snapshot, forecast, status="invalid", reason=reason)


def actual_action_key(snapshot: Snapshot, candidate: RouteCandidate, *, route_mode="next_edge") -> str:
    """The physical prefix AND retained conditional route state define action."""
    if route_mode not in {"whole_route", "next_edge"}:
        raise ValueError("unknown_route_mode")
    committed = ExecutionValidator._safe_prefix(snapshot, candidate) if route_mode == "next_edge" else candidate
    def semantic(c):
        return {"bag_id": c.bag_id, "tray_id": c.tray_id, "legs": [asdict(leg) for leg in c.legs],
                "unload_complete": c.unload_complete, "usable_at": c.usable_at,
                "destination_node": _destination(snapshot, c), "prefix_only": c.prefix_only,
                "continuation_destination": c.continuation_destination}
    return _fingerprint({"committed": semantic(committed), "conditional": semantic(candidate) if committed.prefix_only else None,
                         "module": asdict(snapshot.module), "dependencies": [asdict(d) for d in _forecast_dependencies(snapshot, candidate)]})


class ExecutionValidator:
    """The resource owner revalidates the complete proposal before any mutation."""

    def validate(self, snapshot: Snapshot, candidate: RouteCandidate, *, route_mode: str = "whole_route") -> ValidationResult:
        if route_mode not in {"whole_route", "next_edge"}:
            return ValidationResult(False, "unknown_route_mode")
        if candidate.prefix_only:
            return ValidationResult(False, "prefix_requires_full_witness")
        result = self._validate_whole(snapshot, candidate)
        if not result.accepted or route_mode == "whole_route":
            return result
        prefix = self._safe_prefix(snapshot, candidate)
        slots = tuple(s for s in effective_reservations(snapshot) if s.tray_id != candidate.tray_id)
        conflict = capacity_conflict(snapshot, slots + candidate_reservations(snapshot, prefix))
        return ValidationResult(False, f"prefix_{conflict}") if conflict else result

    @staticmethod
    def _safe_prefix(snapshot: Snapshot, candidate: RouteCandidate) -> RouteCandidate:
        # Protected service keeps its entire witness and reservations. Merely
        # proving a downstream deadline once cannot protect it if a later empty
        # transfer is allowed to consume that unreserved downstream slot.
        if candidate.bag_id is not None and snapshot.bags[candidate.bag_id].protected:
            return candidate
        for index, leg in enumerate(candidate.legs):
            node = snapshot.network.edges[leg.edge_id].target
            if snapshot.network.nodes[node].can_wait:
                if index == len(candidate.legs) - 1:
                    return candidate
                return replace(candidate, legs=candidate.legs[:index + 1],
                               unload_complete=leg.arrive, usable_at=leg.arrive,
                               destination_node=node, prefix_only=True,
                               continuation_destination=_destination(snapshot, candidate))
        return candidate

    def _validate_whole(self, snapshot: Snapshot, candidate: RouteCandidate) -> ValidationResult:
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
        obligation = snapshot.empty_targets.get(tray.tray_id)
        if obligation is not None and (candidate.bag_id is not None or candidate.destination_node != obligation):
            return reject("empty_destination_obligation")
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
                        and t.tray_id not in snapshot.empty_targets
                        and snapshot.network.nodes[t.node].logistics_zone == source_zone
                        for t in snapshot.trays.values())
            # A prefix-continuation tray is still executing its original export;
            # it is not newly usable local stock in an intermediate logistics zone.
            if obligation is None and source_zone != target_zone and stock <= snapshot.module.export_min_stock:
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

    def commit(self, snapshot: Snapshot, candidate: RouteCandidate, *, route_mode: str = "whole_route") -> ValidationResult:
        with _OWNER_LOCK:
            result = self.validate(snapshot, candidate, route_mode=route_mode)
            if not result.accepted:
                return result
            # A local owner lock makes compare/revalidate/publish atomic against
            # other commits. No distributed transaction protocol is claimed.
            slots = tuple(s for s in effective_reservations(snapshot) if s.tray_id != candidate.tray_id)
            committed = self._safe_prefix(snapshot, candidate) if route_mode == "next_edge" else candidate
            snapshot.reservations = _merge_reservations(slots + candidate_reservations(snapshot, committed), snapshot.now)
            snapshot.plans[candidate.tray_id] = committed
            if committed.bag_id is None and committed.prefix_only:
                snapshot.empty_targets[committed.tray_id] = committed.continuation_destination
            snapshot.version += 1
            _publish_forecast(snapshot, candidate, committed)
            refresh_conditional_forecasts(snapshot)
            return result

    def prepare_replacement(self, snapshot: Snapshot, tray_id: str) -> ReplacementContext:
        """Expose only a declared replaceable loaded suffix at a safe anchor.

        The returned snapshot projects reservation time, not physical events of
        other trays. Their existing reservations remain conservative. This is
        intentionally not a permission to cancel protected or empty transfers.
        """
        if tray_id not in snapshot.trays:
            raise ValueError("unknown_tray")
        if any(f.tray_id == tray_id for f in snapshot.old_in_transit):
            raise ValueError("old_in_transit_irrevocable")
        if tray_id not in snapshot.plans:
            raise ValueError("replacement_requires_existing_plan")
        tray, plan = snapshot.trays[tray_id], snapshot.plans[tray_id]
        if plan.bag_id is None or tray_id in snapshot.empty_targets:
            raise ValueError("empty_destination_obligation")
        if plan.bag_id not in snapshot.bags or snapshot.bags[plan.bag_id].protected:
            raise ValueError("protected_itinerary_irrevocable")
        if tray_id not in snapshot.replaceable_trays:
            raise ValueError("suffix_replacement_not_authorized")
        if tray.bag_id != plan.bag_id or tray.mode not in {"loaded", "in_transit"}:
            raise ValueError("replacement_requires_active_loaded_tray")
        if plan.bag_id in snapshot.completed:
            raise ValueError("bag_not_active")
        frozen = tuple(leg for leg in plan.legs if leg.arrive <= snapshot.now)
        anchor_node, anchor_time = tray.node, snapshot.now
        if tray.mode == "in_transit" or tray.node is None or not snapshot.network.nodes[tray.node].can_wait:
            active = next((i for i, leg in enumerate(plan.legs) if leg.depart <= snapshot.now < leg.arrive), None)
            if active is None:
                raise ValueError("entered_edge_witness_missing")
            stop = active
            while True:
                leg = plan.legs[stop]
                edge = snapshot.network.edges.get(leg.edge_id)
                if edge is None or edge.capacity <= 0 or edge.travel_time != leg.arrive - leg.depart:
                    raise ValueError("entered_or_uninterruptible_segment_changed")
                if snapshot.network.nodes[edge.target].can_wait:
                    break
                stop += 1
                if stop >= len(plan.legs) or plan.legs[stop].depart != leg.arrive:
                    raise ValueError("uninterruptible_chain_missing")
            frozen = plan.legs[:stop + 1]
            anchor_node, anchor_time = edge.target, leg.arrive
        if anchor_node is None or not snapshot.network.nodes[anchor_node].can_wait:
            raise ValueError("replacement_anchor_not_waitable")
        # Only frozen history needs to exist. A missing/closed FUTURE edge in
        # the replaceable suffix must not prevent planning a legal bypass.
        for leg in frozen:
            if leg.arrive > snapshot.now and leg.edge_id not in snapshot.network.edges:
                raise ValueError("frozen_edge_missing")
        planning = snapshot.clone()
        planning.now = anchor_time
        planning.plans.pop(tray_id)
        planning.reservations = tuple(r for r in planning.reservations if r.tray_id != tray_id)
        planning.trays[tray_id] = replace(tray, node=anchor_node, mode="loaded", available_at=anchor_time)
        return ReplacementContext(planning, snapshot.version, _fingerprint(snapshot), frozen,
                                  anchor_node, anchor_time, tray_id, plan.bag_id)

    def _replacement(self, snapshot, context, candidate, route_mode):
        if not isinstance(context, ReplacementContext):
            return ValidationResult(False, "invalid_replacement_context"), None
        if context.source_version != snapshot.version or context.source_state_fingerprint != _fingerprint(snapshot):
            return ValidationResult(False, "stale_replacement_context"), None
        try:
            fresh = self.prepare_replacement(snapshot, context.tray_id)
        except ValueError as error:
            return ValidationResult(False, str(error)), None
        if fresh != context:
            return ValidationResult(False, "replacement_context_modified"), None
        if candidate.tray_id != context.tray_id or candidate.bag_id != context.bag_id:
            return ValidationResult(False, "replacement_identity_mismatch"), None
        result = self.validate(fresh.planning_snapshot, candidate, route_mode=route_mode)
        if not result.accepted:
            return result, None
        suffix = self._safe_prefix(fresh.planning_snapshot, candidate) if route_mode == "next_edge" else candidate
        combined = replace(suffix, legs=fresh.frozen_legs + suffix.legs)
        own_frozen = tuple(replace(r, end=min(r.end, fresh.anchor_time)) for r in snapshot.reservations
                           if r.tray_id == fresh.tray_id and r.start < fresh.anchor_time and r.end > snapshot.now)
        others = tuple(r for r in effective_reservations(snapshot) if r.tray_id != fresh.tray_id)
        slots = _merge_reservations(others + own_frozen + candidate_reservations(fresh.planning_snapshot, suffix), snapshot.now)
        conflict = capacity_conflict(snapshot, slots)
        if conflict:
            return ValidationResult(False, "replacement_" + conflict), None
        witness = replace(candidate, legs=fresh.frozen_legs + candidate.legs)
        return ValidationResult(True, "replacement_accepted"), (combined, slots, witness)

    def validate_replacement(self, snapshot: Snapshot, context: ReplacementContext, candidate: RouteCandidate,
                             *, route_mode="whole_route") -> ValidationResult:
        return self._replacement(snapshot, context, candidate, route_mode)[0]

    def replace_suffix(self, snapshot: Snapshot, context: ReplacementContext, candidate: RouteCandidate,
                       *, route_mode="whole_route") -> ValidationResult:
        with _OWNER_LOCK:
            result, prepared = self._replacement(snapshot, context, candidate, route_mode)
            if not result.accepted:
                return result
            combined, slots, witness = prepared
            staged = snapshot.clone()
            staged.plans[context.tray_id] = combined
            staged.reservations = slots
            staged.version += 1
            _publish_forecast(staged, witness, combined)
            refresh_conditional_forecasts(staged)
            try:
                assert_invariants(staged)
            except AssertionError as error:
                return ValidationResult(False, "replacement_physical_state_invalid:" + str(error))
            # Publish only after all derived prediction state has succeeded.
            # No old resource is released in the caller's state before here.
            snapshot.__dict__.update(staged.__dict__)
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
        # A declared future-entry closure may have capacity zero. It does not
        # excuse an already-entered edge losing its physical reservation.
        assert isinstance(edge.travel_time, int) and edge.travel_time > 0 and edge.capacity >= 0
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



class Simulation:
    """Resumable event engine with policy callbacks restricted to observations.

    ``advance(t)`` stops after physical and exogenous events at t, before normal
    control at t. ``observe()`` additionally performs FIFO loading and returns
    a branch-isolated snapshot at the routing boundary. Checkpoints retain the
    engine's remaining exogenous tape; that object is never passed to a policy.
    """

    def __init__(self, snapshot: Snapshot, future_bags=(), *, route_mode="whole_route",
                 generator_factory=None, route_selector=None, slow_controller=None,
                 observer=None, search_horizon=80, candidate_count=3,
                 reactive_empty_dispatch=True, coordination_order="route_then_prebalance"):
        if route_mode not in {"whole_route", "next_edge"}:
            raise ValueError("unknown route_mode")
        if coordination_order not in {"route_then_prebalance", "prebalance_then_route"}:
            raise ValueError("unknown coordination_order")
        self.state = snapshot.clone()
        self.route_mode = route_mode
        self.search_horizon = search_horizon
        self.candidate_count = candidate_count
        self.reactive_empty_dispatch = reactive_empty_dispatch
        self.coordination_order = coordination_order
        self.generator_factory = generator_factory
        self.route_selector = deepcopy(route_selector)
        self.slow_controller = deepcopy(slow_controller)
        self.observer = observer
        self._generator = self._make_generator()
        self._validator = ExecutionValidator()
        self._components = {name: 0.0 for name in COST_WEIGHTS}
        self._trace = []
        self._checks = 0
        self._tray_ids = set(self.state.trays)
        self._phase = "events"
        self._entered_legs = {(tray_id, leg.edge_id, leg.depart)
                              for tray_id, plan in self.state.plans.items()
                              for leg in plan.legs if leg.depart < self.state.now}
        self._arrivals = defaultdict(list)
        self.policy_stats = {name: 0.0 for name in (
            "generation_calls", "generation_ms", "selection_calls", "selection_ms",
            "slow_calls", "slow_ms", "candidate_count", "route_commits", "slow_commits",
            "generation_no_candidates", "generation_no_authorized_candidates", "commit_rejections",
            "protected_unadmitted_decisions", "protected_commits",
        )}
        seen = set(self.state.bags)
        for bag in future_bags:
            if bag.arrival < self.state.now or bag.bag_id in seen:
                raise ValueError("future event overlaps the initial observable ledger or duplicates an ID")
            seen.add(bag.bag_id)
            self._arrivals[bag.arrival].append(bag)
        self._check("initial")
        for tray in self.state.trays.values():
            if tray.bag_id is not None:
                self.state.load_times.setdefault(tray.bag_id, self.state.now)

    def _make_generator(self):
        if self.generator_factory is None:
            return CandidateGenerator(horizon=self.search_horizon)
        try:
            signature(self.generator_factory).bind(horizon=self.search_horizon)
        except (TypeError, ValueError):
            return self.generator_factory()
        return self.generator_factory(horizon=self.search_horizon)

    def _check(self, event, **details):
        assert set(self.state.trays) == self._tray_ids, "finite tray identity set changed"
        assert_invariants(self.state)
        self._checks += 1
        self._trace.append({"time": self.state.now, "event": event, **details})

    def _update_motion(self) -> None:
        # Departure/release is processed before arrivals/acquisitions at a tick.
        # Synchronization builds the atomic simultaneous physical self.state first;
        # per-event checks then see the released-before-acquired valid prefix.
        departing = []
        for tray_id, plan in list(self.state.plans.items()):
            tray = self.state.trays[tray_id]
            leg = next((leg for leg in plan.legs if leg.depart <= self.state.now < leg.arrive), None)
            if leg is not None:
                if tray.node is not None:
                    self.state.trays[tray_id] = replace(tray, node=None, mode="in_transit")
                entry = (tray_id, leg.edge_id, leg.depart)
                if entry not in self._entered_legs:
                    self._entered_legs.add(entry)
                    departing.append((tray_id, leg))
        for tray_id, leg in departing:
            if self.state.plans[tray_id].bag_id is None and leg.depart == self.state.now:
                self._components["empty_distance"] += self.state.network.edges[leg.edge_id].travel_time
            self._check("depart", tray_id=tray_id, edge_id=leg.edge_id)
        for flight in tuple(self.state.old_in_transit):
            if flight.arrive > self.state.now:
                continue
            tray = self.state.trays[flight.tray_id]
            node = self.state.network.edges[flight.edge_id].target
            self.state.old_in_transit = tuple(f for f in self.state.old_in_transit if f != flight)
            self.state.reservations = tuple(r for r in self.state.reservations if r.tray_id != tray.tray_id)
            hold = self.state.module.hold_ticks(node)
            self.state.trays[tray.tray_id] = replace(
                tray, node=node, mode="loaded" if tray.bag_id else "holding" if hold else "empty",
                available_at=self.state.now if tray.bag_id else self.state.now + hold,
            )
            if tray.bag_id is not None and self.state.bags[tray.bag_id].destination == node:
                unload = self.state.now + self.state.module.unload_ticks
                plan_id = f"old:{tray.tray_id}:{self.state.now}"
                plan = RouteCandidate(plan_id, tray.bag_id, tray.tray_id, (), unload, unload + hold,
                                      self.state.version, plan_id, destination_node=node)
                self.state.plans[tray.tray_id] = plan
                self.state.reservations += candidate_reservations(self.state, plan)
            self.state.version += 1
            self._check("old_arrive", tray_id=tray.tray_id, node=node)
        for tray_id, plan in list(self.state.plans.items()):
            tray = self.state.trays[tray_id]
            if any(leg.depart <= self.state.now < leg.arrive for leg in plan.legs):
                continue
            past = [leg for leg in plan.legs if leg.arrive <= self.state.now]
            node = self.state.network.edges[past[-1].edge_id].target if past else tray.node
            arrival = plan.legs[-1].arrive if plan.legs else self.state.now
            if self.state.now < arrival:
                if tray.node is None:
                    self.state.trays[tray_id] = replace(tray, node=node, mode="loaded" if tray.bag_id else "empty")
                    self._check("intermediate_arrive", tray_id=tray_id, node=node)
                continue
            if tray.node is None:
                tray = replace(tray, node=node)
            if plan.prefix_only:
                self.state.trays[tray_id] = replace(tray, node=node, mode="loaded" if tray.bag_id else "empty",
                                                   available_at=self.state.now)
                del self.state.plans[tray_id]
                self.state.reservations = tuple(r for r in self.state.reservations if r.tray_id != tray_id)
                self.state.version += 1
                self._check("prefix_arrive", tray_id=tray_id, node=node)
                continue
            if plan.bag_id is not None and self.state.now < plan.unload_complete:
                new_tray = replace(tray, mode="unloading", available_at=plan.usable_at)
            else:
                if plan.bag_id is not None and plan.bag_id not in self.state.completed:
                    self.state.completed[plan.bag_id] = plan.unload_complete
                    self._trace.append({"time": self.state.now, "event": "unload_complete", "bag_id": plan.bag_id, "tray_id": tray_id})
                new_tray = replace(tray, bag_id=None, mode="holding" if self.state.now < plan.usable_at else "empty", available_at=plan.usable_at)
            changed = new_tray != self.state.trays[tray_id]
            self.state.trays[tray_id] = new_tray
            if self.state.now >= plan.usable_at:
                del self.state.plans[tray_id]
                self.state.empty_targets.pop(tray_id, None)
                self.state.reservations = tuple(r for r in self.state.reservations if r.tray_id != tray_id)
                self.state.version += 1
            if changed:
                self._check("tray_state", tray_id=tray_id, mode=new_tray.mode, node=node)
        for tray_id, tray in list(self.state.trays.items()):
            if tray_id not in self.state.plans and tray.mode == "holding" and tray.available_at <= self.state.now:
                self.state.trays[tray_id] = replace(tray, mode="empty")
                self.state.version += 1
                self._check("module_release", tray_id=tray_id)
        refresh_conditional_forecasts(self.state)

    def _prepare_events(self):
        if self._phase != "events":
            return
        self._update_motion()
        for bag in sorted(self._arrivals.pop(self.state.now, ()), key=lambda bag: bag.bag_id):
            self.state.bags[bag.bag_id] = bag
            self.state.version += 1
            self._check("bag_arrival", bag_id=bag.bag_id)
        self._phase = "load"

    def _waiting(self):
        carried = {tray.bag_id for tray in self.state.trays.values() if tray.bag_id}
        return sorted((bag for bag in self.state.bags.values()
                       if bag.bag_id not in self.state.completed and bag.bag_id not in carried),
                      key=lambda bag: (bag.arrival, bag.bag_id))

    def _prepare_routes(self):
        self._prepare_events()
        if self._phase != "load":
            return
        for bag in self._waiting():
            free = sorted((tray for tray in self.state.trays.values() if tray.mode == "empty"
                           and tray.node == bag.origin and tray.available_at <= self.state.now
                           and tray.tray_id not in self.state.plans
                           and tray.tray_id not in self.state.empty_targets), key=lambda tray: tray.tray_id)
            if not free:
                continue
            tray = free[0]
            self.state.trays[tray.tray_id] = replace(tray, mode="loaded", bag_id=bag.bag_id)
            self.state.load_times[bag.bag_id] = self.state.now
            self.state.version += 1
            self._check("load", bag_id=bag.bag_id, tray_id=tray.tray_id)
        self._phase = "routes"
        if self.observer is not None:
            self.observer(self.state.clone())

    def observe(self) -> Snapshot:
        """A reachable routing boundary; no future events or engine state."""
        self._prepare_routes()
        return self.state.clone()

    def _generate(self, tray, destination=None):
        started = perf_counter()
        if destination is None:
            raw = self._generator.generate(self.state.clone(), tray.bag_id, tray.tray_id,
                                           k=self.candidate_count if self.route_selector else 1)
        else:
            raw = self._generator.generate_empty(self.state.clone(), tray.tray_id, destination, k=1)
        self.policy_stats["generation_calls"] += 1
        self.policy_stats["generation_ms"] += (perf_counter() - started) * 1000
        valid = tuple(candidate for candidate in raw
                      if self._validator.validate(self.state, candidate, route_mode=self.route_mode).accepted)
        self.policy_stats["candidate_count"] += len(valid)
        self.policy_stats["generation_no_candidates"] += not raw
        self.policy_stats["generation_no_authorized_candidates"] += not valid
        return valid

    def _select(self, candidates):
        if self.route_selector is None:
            return candidates[0]
        started = perf_counter()
        chosen = self.route_selector(self.state.clone(), candidates)
        self.policy_stats["selection_calls"] += 1
        self.policy_stats["selection_ms"] += (perf_counter() - started) * 1000
        if chosen not in candidates:
            raise ValueError("route_selector returned an action outside the validated candidate set")
        return chosen

    def _commit(self, candidate, event, **details):
        result = self._validator.commit(self.state, candidate, route_mode=self.route_mode)
        if result.accepted:
            action_key = actual_action_key(self.state, candidate, route_mode=self.route_mode)
            self.policy_stats["route_commits"] += 1
            if candidate.bag_id is not None and self.state.bags[candidate.bag_id].protected:
                self.policy_stats["protected_commits"] += 1
            self._check(event, candidate_id=candidate.candidate_id, action_key=action_key, **details)
        else:
            self.policy_stats["commit_rejections"] += 1
        return result

    def intervene(self, candidate: RouteCandidate) -> ValidationResult:
        """Commit one candidate at a prepared, current-version decision boundary.

        The proposal must be generated from ``observe()``. An intervention never
        cancels an accepted full route or an entered edge. In next_edge mode the
        resource owner reserves the shortest uninterruptible safe prefix.
        """
        self._prepare_routes()
        return self._commit(candidate, "intervention_commit", route_mode=self.route_mode)

    def branch(self, candidate: RouteCandidate):
        branch = self.fork()
        result = branch.intervene(candidate)
        if not result.accepted:
            raise ValueError(f"branch intervention rejected: {result.reason}")
        return branch

    def _run_slow_controller(self):
        if self.slow_controller is None:
            return
        visible = self.state.clone()
        started = perf_counter()
        returned = self.slow_controller(visible)
        self.policy_stats["slow_calls"] += 1
        self.policy_stats["slow_ms"] += (perf_counter() - started) * 1000
        new_plans = tuple(plan for key, plan in visible.plans.items() if key not in self.state.plans)
        proposals = tuple(returned) if returned is not None else new_plans
        # Returned tuples may include rejected proposals. Only complete legal
        # sequential transactions are published; partial controller mutations
        # and edits to fixed module rules never cross this boundary.
        expected = self.state.clone()
        for proposal in proposals:
            if proposal.bag_id is not None:
                raise ValueError("slow_controller may only submit empty transfers")
            result = self._validator.commit(expected, proposal)
            if not result.accepted:
                raise ValueError(f"slow_controller proposal rejected: {result.reason}")
        if visible != self.state and visible != expected:
            raise ValueError("slow_controller modified state outside ExecutionValidator commits")
        for proposal in proposals:
            result = self._validator.commit(self.state, proposal)
            assert result.accepted, result.reason
            self.policy_stats["slow_commits"] += 1
            self._check("slow_commit", candidate_id=proposal.candidate_id, tray_id=proposal.tray_id)

    def _route_loaded(self, *, protected_only=None):
        for tray in sorted(self.state.trays.values(), key=lambda tray: tray.tray_id):
            if tray.mode != "loaded" or tray.tray_id in self.state.plans:
                continue
            protected = self.state.bags[tray.bag_id].protected
            if protected_only is not None and protected != protected_only:
                continue
            options = self._generate(tray)
            if options:
                result = self._commit(self._select(options), "route_commit")
                assert result.accepted, result.reason
            elif protected:
                self.policy_stats["protected_unadmitted_decisions"] += 1

    def _continue_causally(self):
        self._prepare_routes()
        # Protection is admitted before either soft optimization order. A bag
        # with no legal witness stays in the ledger with an explicit unadmitted
        # decision count; the protected flag itself is not an admission proof.
        self._route_loaded(protected_only=True)
        if self.coordination_order == "route_then_prebalance":
            self._route_loaded(protected_only=False)
        else:
            self._run_slow_controller()
        # A causal empty trip interrupted only at a safe prefix boundary keeps
        # its requested destination; it never becomes a fictitious spare tray.
        for tray_id, destination in sorted(tuple(self.state.empty_targets.items())):
            tray = self.state.trays[tray_id]
            if tray_id in self.state.plans or tray.mode != "empty":
                continue
            if tray.node == destination:
                del self.state.empty_targets[tray_id]
                continue
            options = self._generate(tray, destination)
            if options:
                result = self._commit(options[0], "empty_continue")
                assert result.accepted, result.reason
        if self.coordination_order == "route_then_prebalance":
            self._run_slow_controller()
        else:
            self._route_loaded(protected_only=False)
        if not self.reactive_empty_dispatch:
            return
        reserved_origins = defaultdict(int)
        for plan in self.state.plans.values():
            if plan.bag_id is None:
                reserved_origins[plan.continuation_destination or _destination(self.state, plan)] += 1
        for tray_id, destination in self.state.empty_targets.items():
            if tray_id not in self.state.plans:
                reserved_origins[destination] += 1
        for bag in self._waiting():
            if reserved_origins[bag.origin]:
                reserved_origins[bag.origin] -= 1
                continue
            choices = []
            for tray in sorted(self.state.trays.values(), key=lambda tray: tray.tray_id):
                if (tray.mode != "empty" or tray.node == bag.origin or tray.tray_id in self.state.plans
                        or tray.tray_id in self.state.empty_targets):
                    continue
                options = self._generate(tray, bag.origin)
                if options:
                    choices.append(options[0])
            if choices:
                choice = min(choices, key=lambda option: (option.usable_at, option.tray_id))
                result = self._commit(choice, "empty_dispatch", visible_bag_id=bag.bag_id)
                assert result.accepted, result.reason

    def advance(self, horizon: int) -> RolloutResult:
        if not isinstance(horizon, int) or horizon < self.state.now:
            raise ValueError("horizon precedes snapshot or is not an integer tick")
        while self.state.now < horizon:
            self._prepare_events()
            self._continue_causally()
            self._update_motion()
            self._components["tray_wait"] += sum(
                bag_id not in self.state.load_times and bag_id not in self.state.completed
                for bag_id in self.state.bags)
            assert all(tray.node is None or self.state.network.nodes[tray.node].can_wait
                       for tray in self.state.trays.values()), "tray left waiting at a non-waitable node"
            self._check("tick")
            self.state.now += 1
            self.state.version += 1
            self.state.reservations = tuple(r for r in self.state.reservations if r.end > self.state.now)
            self._phase = "events"
        self._prepare_events()
        return self.result()

    def result(self) -> RolloutResult:
        """A detached view; the terminal tick marker is a non-mutating preview.

        Keeping this preview out of the execution log permits exact no-op
        pause/resume: a resumed tick has one marker after its control actions.
        """
        assert_invariants(self.state)
        uncompleted = tuple(sorted(set(self.state.bags) - set(self.state.completed)))
        carried = {tray.bag_id for tray in self.state.trays.values() if tray.bag_id}
        waiting = tuple(sorted(set(uncompleted) - carried))
        components = dict(self._components)
        components["nonprotected_tardiness"] = float(sum(
            max(0, self.state.completed.get(bag_id, self.state.now) - bag.deadline)
            for bag_id, bag in self.state.bags.items() if not bag.protected))
        components["terminal_backlog"] = float(len(uncompleted))
        components["terminal_inflight"] = float(sum(tray.mode == "in_transit" for tray in self.state.trays.values()))
        trace = tuple(deepcopy(self._trace)) + ({"time": self.state.now, "event": "tick"},)
        return RolloutResult(components, sum(COST_WEIGHTS[key] * value for key, value in components.items()),
                             dict(self.state.completed), waiting, uncompleted, dict(self.state.trays), trace,
                             self._checks + 1, self.state.clone(), dict(self.policy_stats))

    def checkpoint(self) -> SimulationCheckpoint:
        return SimulationCheckpoint(
            self.state.clone(), dict(self._components), tuple(deepcopy(self._trace)), self._checks,
            deepcopy(dict(self._arrivals)), set(self._entered_legs), set(self._tray_ids), self._phase,
            self.route_mode, self.search_horizon, self.candidate_count, deepcopy(self._generator),
            self.generator_factory, deepcopy(self.route_selector), deepcopy(self.slow_controller),
            self.observer, dict(self.policy_stats), self.reactive_empty_dispatch, self.coordination_order)

    @classmethod
    def from_checkpoint(cls, checkpoint: SimulationCheckpoint):
        checkpoint = checkpoint.clone()
        simulation = cls.__new__(cls)
        simulation.state = checkpoint.state
        simulation._components = checkpoint.cost_components
        simulation._trace = list(checkpoint.trace)
        simulation._checks = checkpoint.invariant_checks
        simulation._arrivals = defaultdict(list, checkpoint.pending_arrivals)
        simulation._entered_legs = checkpoint.entered_legs
        simulation._tray_ids = checkpoint.initial_tray_ids
        simulation._phase = checkpoint.phase
        simulation.route_mode = checkpoint.route_mode
        simulation.search_horizon = checkpoint.search_horizon
        simulation.candidate_count = checkpoint.candidate_count
        simulation._generator = checkpoint.generator
        simulation.generator_factory = checkpoint.generator_factory
        simulation.route_selector = checkpoint.route_selector
        simulation.slow_controller = checkpoint.slow_controller
        simulation.observer = checkpoint.observer
        simulation.policy_stats = checkpoint.policy_stats
        simulation.reactive_empty_dispatch = checkpoint.reactive_empty_dispatch
        simulation.coordination_order = checkpoint.coordination_order
        simulation._validator = ExecutionValidator()
        assert_invariants(simulation.state)
        return simulation

    def fork(self):
        return self.from_checkpoint(self.checkpoint())


def simulate(snapshot: Snapshot, candidate: RouteCandidate | None, future_bags: tuple[Bag, ...] | list[Bag],
             horizon: int) -> RolloutResult:
    """Backward-compatible whole-route pilot wrapper with absolute horizon."""
    engine = Simulation(snapshot, future_bags, search_horizon=max(20, horizon - snapshot.now + 10))
    if candidate is not None:
        result = engine._validator.commit(engine.state, candidate)
        if not result.accepted:
            raise ValueError(f"initial candidate rejected: {result.reason}")
        engine._check("initial_commit", candidate_id=candidate.candidate_id)
    return engine.advance(horizon)
