"""Opt-in same-owner, different-node empty service for the frozen W2 protocol.

The original clock/controller modules are unchanged. This module adds a local
service controller and a source-owner authorization extension. A named target
may be served by its dispatched tray only at the validated usable tick. Before
that tick it receives no supply credit. Other demand prefixes retain their
current directed, same-zone matching capacity. This conservative test can refuse
undersupplied simultaneous queues; it is not a complete scheduling algorithm.

Physical FIFO, module timing, export floor, leases, lost-ack recovery and atomic
commit all remain in the existing protocol/runtime. No future tape is inspected.
"""
from __future__ import annotations

from copy import deepcopy

from .distributed_clock import (AnchorMessage, ClockRequest, DistributedClock,
                               LocalRoutePlanner, ResourceParticipant, preserves_source_prefixes)
from .distributed_slow import LocalClockController


def delivered_demands(owner, network, now, waiting, loaded, publications, horizon):
    """Actual queued identity dominates predictions; returns known owner needs."""
    needs, times = {}, {}
    for unit, publication in publications.items():
        if unit in loaded or unit in waiting:
            continue
        if publication is None:
            return {}, {}, "source_forecast_version_conflict"
        if (not publication.cancelled and publication.expires_at > now and publication.at <= now + horizon
                and network.nodes[publication.node].control_partition == owner):
            needs[unit], times[unit] = publication.node, max(now, publication.at)
    for unit, node in waiting.items():
        if unit not in loaded and network.nodes[node].control_partition == owner:
            needs[unit], times[unit] = node, now
    return needs, times, None


def local_service_guard(view, module, pool, tray, needs, times, proposal):
    """Conditional admission arithmetic, not a published inventory forecast."""
    network, candidate, unit = view.public_topology, proposal.candidate, proposal.demand_id
    details = {"unit": unit, "donor": tray.tray_id, "usable_at": candidate.usable_at, "prefixes": []}
    if unit is None or unit not in needs or needs[unit] != candidate.destination_node:
        return "local_service_requires_known_matching_demand", details
    if candidate.bag_id is not None or candidate.prefix_only or not candidate.legs:
        return "local_service_requires_full_empty_path", details
    if network.nodes[candidate.destination_node].control_partition != view.owner or tray.node == candidate.destination_node:
        return "not_same_owner_different_node_service", details
    # Check public witness timing independently of any inventory arithmetic.
    node, tick = tray.node, view.observed_tick
    for leg in candidate.legs:
        edge = network.edges.get(leg.edge_id)
        if (edge is None or edge.source != node or edge.capacity <= 0 or leg.depart < tick
                or leg.arrive != leg.depart + edge.travel_time
                or (leg.depart > tick and not network.nodes[node].can_wait)):
            return "local_service_invalid_witness", details
        node, tick = edge.target, leg.arrive
    if (node != candidate.destination_node or candidate.unload_complete != tick
            or candidate.usable_at != tick + module.hold_ticks(node)):
        return "local_service_invalid_release_time", details
    details["arrival_at"] = tick
    zone = network.nodes[tray.node].logistics_zone
    regional = {key: node for key, node in needs.items() if network.nodes[node].logistics_zone == zone}
    if unit not in regional:
        # A same-owner cross-zone movement is still an export from this zone.
        okay = preserves_source_prefixes(view.owner, network, pool, tray, needs, times)
        return (None if okay else "source_prefix_protection_changed"), details
    regional_pool = [t for t in pool if network.nodes[t.node].logistics_zone == zone]
    def reachable(source, destination):
        pending, seen = [source], {source}
        while pending:
            current = pending.pop()
            if current == destination:
                return True
            for edge in network.edges.values():
                target = network.nodes[edge.target]
                if (edge.source == current and edge.capacity > 0 and target.control_partition == view.owner
                        and target.logistics_zone == zone and edge.target not in seen):
                    seen.add(edge.target)
                    pending.append(edge.target)
        return False
    adjacency = {key: [t.tray_id for t in regional_pool if reachable(t.node, node)]
                 for key, node in regional.items()}
    def matching(units, removed=None):
        assigned = {}
        def augment(key, seen):
            for tray_id in adjacency[key]:
                if tray_id == removed or tray_id in seen:
                    continue
                seen.add(tray_id)
                if tray_id not in assigned or augment(assigned[tray_id], seen):
                    assigned[tray_id] = key
                    return True
            return False
        return sum(augment(key, set()) for key in sorted(units))
    # A real backlog can wait for a positive travel time. Only its own demand
    # time is deferred; every other known prefix keeps its original bound.
    effective_times = {key: times[key] for key in regional}
    effective_times[unit] = max(times[unit], candidate.usable_at)
    service_at = effective_times[unit]
    details["effective_service_tick"] = service_at
    for cutoff in sorted(set(effective_times.values()) | {candidate.usable_at}):
        prefix = [key for key in regional if effective_times[key] <= cutoff]
        before = matching(prefix)
        credited = int(unit in prefix and cutoff >= service_at)
        remaining = [key for key in prefix if key != unit]
        other_before = matching(remaining)
        other_after = matching(remaining, tray.tray_id)
        after = other_after + credited
        details["prefixes"].append({"tick": cutoff, "before": before, "after": after,
                                   "other_before": other_before, "other_after": other_after,
                                   "target_credit": credited})
        # Serving this target cannot compensate for consuming the only tray
        # which could cover another demand at the same or an earlier prefix.
        if other_after < other_before or after < before:
            return "local_service_would_degrade_other_prefix", details
    return None, details


class LocalServiceParticipant(ResourceParticipant):
    """The new permission is checked by the resource owner, not just selection."""
    def _source_guard(self, proposal, *, ignore_key):
        view = self.observation
        destination = proposal.candidate.destination_node
        is_local = destination in view.public_topology.nodes and view.public_topology.nodes[destination].control_partition == view.owner
        if not self.local_dispatch or not is_local or destination == proposal.anchor.node:
            return super()._source_guard(proposal, ignore_key=ignore_key)
        needs, times, reason = delivered_demands(view.owner, view.public_topology, view.observed_tick,
                self.waiting_units, self.seen_loaded_bags, self.demand_publications, self.source_guard_horizon or 20)
        busy = {slot.tray_id for slot in view.local_calendars
                if slot.resource.startswith("edge:") and slot.end > view.observed_tick}
        busy.update(claim["tray_id"] for claim in self.accepted_demands.values())
        for key, lease in self.leases.items():
            if key != ignore_key:
                busy.update(slot.tray_id for slot in lease.slots)
        pool = [tray for tray in view.local_trays if tray.mode == "empty" and tray.available_at <= view.observed_tick
                and tray.tray_id not in busy]
        tray = next((t for t in pool if t.tray_id == proposal.candidate.tray_id), None)
        details = {}
        if reason is None:
            if tray is None:
                reason = "source_stock_no_longer_available"
            else:
                reason, details = local_service_guard(view, self.module, pool, tray, needs, times, proposal)
        self.local_service_audit.append({"time": view.observed_tick, "request_id": proposal.request_id,
             "stage": "authorize" if ignore_key is not None else "prepare", "accepted": reason is None,
             "reason": reason, **details})
        return reason


class LocalDispatchController(LocalClockController):
    """Opt-in local service after the unchanged loaded/cross-owner controller."""
    def __init__(self, owner, *, local_dispatch=False, **kwargs):
        super().__init__(owner, **kwargs)
        if type(local_dispatch) is not bool:
            raise ValueError("local_dispatch must be bool")
        self.local_dispatch = local_dispatch
        self.local_planner = LocalRoutePlanner()

    def step(self, view, module):
        previous_slow_tick = self.last_slow_tick
        actions = list(super().step(view, module))
        now, network = view.observed_tick, view.public_topology
        if (not self.local_dispatch or self.mode == "none" or now % self.period
                or previous_slow_tick == now or self.last_slow_tick != now):
            return tuple(actions)
        loaded = self.seen_local_loaded | self.observed_loaded_units
        publications = dict(self.forecasts)
        publications.update({key: None for key in self.forecast_conflicts})
        waiting = {key: node for key, node in self.observed_waiting_units.items()
                   if network.nodes[node].control_partition == self.owner}
        needs, times, reason = delivered_demands(self.owner, network, now, waiting, loaded,
                                                publications, self.forecast_horizon)
        if reason:
            return tuple(actions)
        eligible = set(waiting) if self.mode in {"reactive", "both"} else set()
        if self.mode in {"predictive", "both"}:
            eligible.update(unit for unit in needs if unit in self.forecast_versions)
        busy = {slot.tray_id for slot in view.local_calendars if slot.resource.startswith("edge:") and slot.end > now}
        claimed = set()
        own_status = self.statuses.get(self.owner)
        if own_status:
            claimed.update(own_status["accepted_demands"])
            claimed.update(own_status["prepared_demands"])
            busy.update(claim["tray_id"] for claim in own_status["accepted_demands"].values())
        for row in self.requests.values():
            request, receipt = row["request"], row["receipt"]
            if row["outcome"] in (None, "outcome_unknown"):
                busy.add(request.tray_id)
                claimed.add(request.demand_id)
            elif receipt and (own_status is None or own_status["observed_tick"] < receipt.get("usable_at", now)):
                claimed.add(request.demand_id)
                if receipt.get("usable_at", now) > now:
                    busy.add(request.tray_id)
        pool = [tray for tray in sorted(view.local_trays, key=lambda t: t.tray_id)
                if tray.mode == "empty" and tray.available_at <= now and tray.tray_id not in busy]
        stock_at_destination = {}
        for tray in pool:
            stock_at_destination[tray.node] = stock_at_destination.get(tray.node, 0) + 1
        for unit in sorted(set(needs) & eligible - claimed - loaded, key=lambda key: (times[key], key)):
            destination = needs[unit]
            if stock_at_destination.get(destination, 0):
                stock_at_destination[destination] -= 1
                continue
            for tray in list(pool):
                if tray.node == destination:
                    continue
                source_zone, target_zone = network.nodes[tray.node].logistics_zone, network.nodes[destination].logistics_zone
                if source_zone != target_zone and sum(t.node == tray.node for t in pool) <= module.export_min_stock:
                    continue
                probe = ClockRequest("local-probe", self.owner, None, tray.tray_id, intent="empty_transfer",
                        departure_lead=self.departure_lead, destination_node=destination, demand_id=unit)
                anchor = AnchorMessage(tray.tray_id, None, tray.node, now, view.version, destination_node=destination)
                proposal, search = self.local_planner.plan(view, module, probe, anchor, 1)
                if proposal is None:
                    self.trace.append({"time": now, "event": "local_service_probe", "unit": unit,
                                       "tray_id": tray.tray_id, "accepted": False, "reason": search})
                    continue
                rejection, details = local_service_guard(view, module, pool, tray, needs, times, proposal)
                self.trace.append({"time": now, "event": "local_service_probe", "accepted": rejection is None,
                                   "reason": rejection, **details})
                if rejection is None:
                    actions.append(self._new_request(view, tray, destination=destination, unit=unit))
                    pool.remove(tray)
                    break
        return tuple(actions)


class LocalDispatchClock(DistributedClock):
    """Preserves the old clock when disabled; checkpoint keeps the opt-in flag."""
    def __init__(self, *args, local_dispatch=False, **kwargs):
        if type(local_dispatch) is not bool:
            raise ValueError("local_dispatch must be bool")
        super().__init__(*args, **kwargs)
        self.local_dispatch = local_dispatch
        for owner, original in list(self.participants.items()):
            participant = LocalServiceParticipant.__new__(LocalServiceParticipant)
            participant.__dict__.update(deepcopy(original.__dict__))
            participant.local_dispatch = local_dispatch
            participant.local_service_audit = []
            self.participants[owner] = participant
