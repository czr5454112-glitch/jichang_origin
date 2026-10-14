"""Opt-in full-witness routing through one announced on-carrier storage node.

Ordinary bags and empty transfers use the supplied generator unchanged. Storage
queries use a bounded physical-edge product search, never two independently
completed transport jobs. The node calendar represents finite proxy storage
slots; this is not a model of a real storage retrieval machine.
"""
from __future__ import annotations

from collections import defaultdict
from heapq import heappop, heappush
from itertools import count
from time import perf_counter

from .model import Leg, RouteCandidate
from .routing import (_SearchBudgetExpired, _StaticTopology,
                      RegionalCandidateGenerator, network_signature)
from .storage_calendar import CapacityCalendarView, StorageCompletionLowerBound, StorageEventTimeSearch
from .runtime import ExecutionValidator, INFINITY


class StorageCandidateGenerator:
    """A transparent ordinary-route delegate plus a bounded storage search.

    The delegate's horizon, expansion budget, deadline and caller K remain the
    limits. Storage preprocessing, event projection and product labels share
    that one budget. Static work may reuse the delegate's existing isolated
    cache with unchanged cold-equivalent logical work. Live calendars are always
    query-local. No new persistent cache escapes checkpoint/cache accounting.
    """

    def __init__(self, generator):
        if isinstance(generator, StorageCandidateGenerator):
            raise ValueError("Storage routing must not be wrapped twice")
        for name in ("generate", "generate_empty", "horizon", "expansion_limit"):
            if not hasattr(generator, name):
                raise ValueError(f"Storage routing delegate lacks {name}")
        self.generator = generator
        self.last_search_status = "not_started"
        self.last_expansions = 0
        self.last_diagnostics = {}

    @property
    def horizon(self):
        return self.generator.horizon

    @property
    def expansion_limit(self):
        return self.generator.expansion_limit

    @property
    def deadline_ms(self):
        return getattr(self.generator, "deadline_ms", None)

    _budget = RegionalCandidateGenerator._budget
    _consume = RegionalCandidateGenerator._consume

    def _delegate(self, method, *args):
        candidates = getattr(self.generator, method)(*args)
        self.last_search_status = self.generator.last_search_status
        self.last_expansions = self.generator.last_expansions
        self.last_diagnostics = getattr(self.generator, "last_diagnostics", {})
        return candidates

    def generate_empty(self, snapshot, tray_id, destination, k=1):
        return self._delegate("generate_empty", snapshot, tray_id, destination, k)

    def generate(self, snapshot, bag_id, tray_id, k=3):
        bag = snapshot.bags.get(bag_id)
        if getattr(bag, "storage", None) is None:
            return self._delegate("generate", snapshot, bag_id, tray_id, k)
        return self._generate_storage(snapshot, bag_id, tray_id, k)

    def _finish(self, found, *, exhausted=False):
        if self.last_search_status == "searching":
            self.last_search_status = "partial_candidate_set" if found else "bounded_no_candidate"
        self.last_diagnostics.update(
            query_ms=(perf_counter() - self._started) * 1000,
            expansions=self.last_expansions, candidate_count=len(found),
            search_queue_exhausted=exhausted)
        return tuple(found)

    def _generate_storage(self, snapshot, bag_id, tray_id, k):
        from .storage_contracts import (effective_storage_progress, storage_contract,
                                        storage_contract_failure)

        if getattr(self.generator, "cache_contract", None) is not None and self.deadline_ms is not None:
            raise ValueError("Deterministic cache replay requires deadline_ms=None")
        self._started = perf_counter()
        self.last_expansions, self.last_search_status = 0, "searching"
        accounting = {"contract": "uncached_storage_graph_v1",
                      "logical_preprocessing": "actual_cold_preprocessing_per_query",
                      "actual_preprocessing_work": {}, "reused_preprocessing_work": {}}
        cache = None
        if getattr(self.generator, "cache_contract", None) == "isolated_replay_v1":
            cache = self.generator._owned_topology_cache
            accounting.update(contract="isolated_replay_v1", logical_preprocessing="cold_equivalent_per_query")
        self.last_diagnostics = {
            "validation_ms": 0., "work_units_by_stage": {},
            "preprocessing_budget_included": True,
            "route_mode": "whole_route", "storage_mode": "announced_on_carrier_node_proxy",
            "completeness": "bounded_storage_product_event_time_labels",
            "missing_candidate_is_not_infeasibility": True,
            "earliest_arrival_certified": False,
            "remote_calendar_access": True, "cache_accounting": accounting,
            "calendar_lower_bound": "mandatory_storage_suffix_edge_calendar_relaxation",
            "calendar_lifetime": "query_local_no_persistent_state",
            "state_dominance": "unchanged_exact_time_and_caller_k",
        }
        bag, tray = snapshot.bags[bag_id], snapshot.trays.get(tray_id)
        if (type(k) is not int or k < 1 or tray is None or tray.node is None
                or tray_id in snapshot.plans or tray.available_at > snapshot.now
                or tray.mode != "loaded" or tray.bag_id != bag_id
                or bag.arrival > snapshot.now or bag_id in snapshot.completed
                or bag.destination not in snapshot.network.nodes
                or any(f.tray_id == tray_id and f.arrive > snapshot.now for f in snapshot.old_in_transit)):
            self.last_search_status = "invalid_request"
            return self._finish([])
        try:
            failure = storage_contract_failure(snapshot, bag_id)
            if failure:
                self.last_search_status = "invalid_storage_contract"
                self.last_diagnostics["contract_failure"] = failure
                return self._finish([])
            contract = storage_contract(snapshot, bag_id)
            progress = effective_storage_progress(snapshot, bag_id)
        except ValueError as error:
            self.last_search_status = "invalid_storage_contract"
            self.last_diagnostics["contract_failure"] = str(error)
            return self._finish([])
        if contract is None:
            self.last_search_status = "invalid_storage_contract"
            return self._finish([])
        waypoint = contract.node_id
        # Contract helpers own legality; these guards also keep this proposal
        # layer fail-closed when a caller supplies a malformed planning view.
        if (waypoint not in snapshot.network.nodes or waypoint == bag.destination
                or not snapshot.network.nodes[waypoint].can_wait
                or contract.published_at > snapshot.now
                or contract.carrier_policy != "on_carrier"):
            self.last_search_status = "invalid_storage_contract"
            return self._finish([])
        visited = progress is not None and progress.arrived_at is not None
        departed = progress is not None and progress.departed_at is not None
        if (progress is not None and (progress.tray_id != tray_id or progress.contract != contract
                or (progress.arrived_at is not None and progress.arrived_at > snapshot.now)
                or (progress.departed_at is not None and progress.departed_at > snapshot.now))
                or (visited and not departed and tray.node != waypoint)
                or (departed and not visited)):
            self.last_search_status = "invalid_storage_progress"
            return self._finish([])
        if tray.node == waypoint and not visited:
            # Physically present at storage is not an invented past event. The
            # runtime must record ingress when loading there or reaching it.
            self.last_search_status = "missing_storage_ingress"
            return self._finish([])
        found = []
        try:
            signature = network_signature(snapshot.network)
            topology = (_StaticTopology(signature, self._consume, accounting=accounting) if cache is None else
                        cache.get(signature, self._consume, accounting))
            final_lower = topology.lower_bounds(bag.destination, self._consume, accounting)
            waypoint_lower = topology.lower_bounds(waypoint, self._consume, accounting)
            if (tray.node not in final_lower or (not visited and
                    (tray.node not in waypoint_lower or waypoint not in final_lower))):
                self.last_search_status = "static_unreachable"
                return self._finish([])
            limit = snapshot.now + self.horizon
            if bag.protected:
                limit = min(limit, bag.deadline - snapshot.module.unload_ticks)

            def static_estimate(node, tick, passed):
                if passed:
                    start = max(tick, contract.release_at) if node == waypoint else tick
                    return start + final_lower.get(node, INFINITY)
                return (max(tick + waypoint_lower.get(node, INFINITY), contract.release_at)
                        + final_lower.get(waypoint, INFINITY))

            lower_estimate = static_estimate(tray.node, snapshot.now, visited)
            self.last_diagnostics.update(
                static_lower_bound=lower_estimate - snapshot.now, storage_already_visited=visited,
                storage_already_departed=departed, storage_release_at=contract.release_at,
                state_label_limit=k, storage_capacity=snapshot.network.nodes[waypoint].capacity,
                heap_priority="arrival_lower_bound_then_remaining_static_travel_then_visited_then_fifo")
            if lower_estimate > limit:
                self.last_search_status = "storage_horizon_or_deadline_bound"
                return self._finish([])
            view = CapacityCalendarView(self, snapshot, tray_id)
            relaxation = StorageCompletionLowerBound(self, topology, view, waypoint, bag.destination,
                                                       contract.release_at)
            required_floor = (relaxation.earliest_final(snapshot.now)
                              if not visited or tray.node == waypoint else None)

            def estimate(node, tick, passed):
                value = static_estimate(node, tick, passed)
                if required_floor is not None:
                    value = max(value, required_floor)
                return value

            lower_estimate = estimate(tray.node, snapshot.now, visited)
            self.last_diagnostics.update(resource_lower_bound=lower_estimate - snapshot.now,
                                         storage_relaxed_completion_floor=required_floor)
            if lower_estimate > limit:
                self.last_search_status = "storage_calendar_horizon_or_deadline_bound"
                return self._finish([])
            search = StorageEventTimeSearch(self, snapshot, topology, final_lower, view, limit,
                                            waypoint=waypoint, release=contract.release_at)
            serial = count()
            def entry(node, tick, passed, legs, arrival_estimate):
                # Before an announced release, many different arrival times
                # have the same final-arrival bound. FIFO alone then expands
                # cycles across that plateau before advancing a full witness.
                # Only ties in the resource-aware primary bound are broken by the
                # remaining mandatory physical travel, never by hidden future
                # events, expanded budgets or a discarded path family.
                remaining = (final_lower.get(node, INFINITY) if passed else
                             waypoint_lower.get(node, INFINITY) + final_lower.get(waypoint, INFINITY))
                return (arrival_estimate, remaining, not passed, next(serial),
                        node, tick, passed, legs)
            queue = [entry(tray.node, snapshot.now, visited, (), lower_estimate)]
            seen, signatures = defaultdict(set), set()
            while queue:
                self._consume("storage_product_time_labels")
                _, _, _, _, node, tick, passed, legs = heappop(queue)
                key = (node, tick, passed)
                if legs in seen[key]:
                    continue
                if len(seen[key]) >= k:
                    self.last_diagnostics["state_label_truncations"] = self.last_diagnostics.get("state_label_truncations", 0) + 1
                    continue
                seen[key].add(legs)
                if node == bag.destination and passed:
                    unload = tick + snapshot.module.unload_ticks
                    usable = unload + snapshot.module.hold_ticks(node)
                    identifier = f"storage:v{snapshot.version}:{bag_id}:{tray_id}"
                    candidate = RouteCandidate(
                        f"{identifier}:{len(found)}", bag_id, tray_id, legs, unload, usable,
                        snapshot.version, f"{identifier}:0", not found, bag.destination)
                    self._consume("storage_full_witness_validation")
                    started = perf_counter()
                    accepted = ExecutionValidator().validate(snapshot, candidate).accepted
                    self.last_diagnostics["validation_ms"] += (perf_counter() - started) * 1000
                    if accepted and legs not in signatures:
                        signatures.add(legs)
                        found.append(candidate)
                        if len(found) >= k:
                            self.last_search_status = "candidate_limit_reached"
                            return self._finish(found)
                earliest_depart = max(tick, contract.release_at) if node == waypoint else tick
                for depart in search.departures(node, earliest_depart):
                    if depart < earliest_depart or not view.available(f"node:{node}", tick, depart):
                        continue
                    for target, travel, edge_id in topology.outgoing[node]:
                        arrive = depart + travel
                        target_passed = passed or target == waypoint
                        arrival_estimate = estimate(target, arrive, target_passed)
                        if arrival_estimate > limit:
                            continue
                        if view.available(f"edge:{edge_id}", depart, arrive):
                            heappush(queue, entry(target, arrive, target_passed,
                                                legs + (Leg(edge_id, depart, arrive),), arrival_estimate))
        except _SearchBudgetExpired:
            return self._finish(found)
        return self._finish(found, exhausted=True)
