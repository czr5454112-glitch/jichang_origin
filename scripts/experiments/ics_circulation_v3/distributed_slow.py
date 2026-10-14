"""Causal local fast/slow controller for the W2 shared-clock owner protocol.

No Snapshot or future-arrival tape enters this module. Actual stock and task
observations are local; remote counts/claims and predictions arrive as messages.
Identity-aware forecasts remain pending past their nominal time until observed,
explicitly cancelled, or expired. They are demand predictions, never tray supply.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .distributed_clock import CancelUncommitted, ClockRequest, preserves_source_prefixes


@dataclass(frozen=True)
class PublishedDemand:
    unit_id: str
    node: str
    at: int
    published_at: int
    expires_at: int
    revision: int = 1
    cancelled: bool = False

    def __post_init__(self):
        if any(type(value) is not int or value < 0 for value in
               (self.at, self.published_at, self.expires_at, self.revision)):
            raise ValueError("forecast times/revision must be nonnegative integers")
        if self.expires_at <= self.published_at or not self.unit_id or not self.node:
            raise ValueError("invalid publication identity/expiry")


class LocalClockController:
    """Loaded routes every tick; optional empty dispatch on an owner clock.

    All selection inputs are delivered messages and one PartitionObservation.
    Remote prepared claims only suppress duplicate attempts temporarily; they
    are not counted as physical stock. Accepted full-transfer claims cover one
    named demand until the local destination owner reports consumption/release.
    Local publications protect source needs even when nominal arrival is overdue.
    """
    def __init__(self, owner, *, mode="reactive", period=3, departure_lead=4,
                 status_max_age=8, forecast_horizon=20, max_attempts=3):
        if mode not in {"none", "reactive", "predictive", "both"}:
            raise ValueError("unknown slow mode")
        for value in (period, status_max_age, forecast_horizon, max_attempts):
            if type(value) is not int or value <= 0:
                raise ValueError("controller bounds must be positive integers")
        if type(departure_lead) is not int or departure_lead < 0:
            raise ValueError("departure lead must be nonnegative")
        self.owner, self.mode, self.period = owner, mode, period
        self.departure_lead, self.max_attempts = departure_lead, max_attempts
        self.status_max_age, self.forecast_horizon = status_max_age, forecast_horizon
        self.forecasts = {}
        self.forecast_versions = {}
        self.forecast_conflicts = set()
        self.statuses = {}
        self.waiting_units = {}
        self.task_facts_tick = -1
        self.requests = {}
        self.seen_local_loaded = set()
        self.observed_loaded_units = set()
        self.observed_waiting_units = {}
        self.counter = 0
        self.last_slow_tick = None
        self.trace = []

    def receive(self, kind, payload, now):
        if kind == "DEMAND_FORECAST":
            if payload.published_at > now:
                raise ValueError("unpublished demand delivered")
            key = payload.revision, payload.published_at
            old_key = self.forecast_versions.get(payload.unit_id)
            if old_key is None or key > old_key:
                self.forecast_versions[payload.unit_id] = key
                self.forecast_conflicts.discard(payload.unit_id)
                self.forecasts[payload.unit_id] = deepcopy(payload)
                self.trace.append({"time": now, "event": "forecast_received", "unit": payload.unit_id,
                                   "revision": payload.revision, "cancelled": payload.cancelled})
            elif key == old_key and payload.unit_id not in self.forecast_conflicts and self.forecasts[payload.unit_id] != payload:
                self.forecast_conflicts.add(payload.unit_id)
                self.forecasts.pop(payload.unit_id)
                self.trace.append({"time": now, "event": "same_version_forecast_conflict", "unit": payload.unit_id})
        elif kind == "TASK_STATE":
            if payload["observed_tick"] > now:
                raise ValueError("future task facts delivered")
            if payload["observed_tick"] > self.task_facts_tick:
                self.task_facts_tick = payload["observed_tick"]
                self.seen_local_loaded.update(payload["loaded_units"])
                self.waiting_units = deepcopy(payload["waiting_units"])
                self.observed_waiting_units.update(payload["waiting_units"])
        elif kind == "OWNER_STATUS":
            if payload["observed_tick"] > now:
                raise ValueError("future owner status delivered")
            # Task IDs are immutable. A delivered loading fact never expires;
            # the status TTL applies to mutable stock/queue/lease observations.
            self.observed_loaded_units.update(payload["loaded_units"])
            self.observed_waiting_units.update(payload["waiting_units"])
            old = self.statuses.get(payload["owner"])
            if old is None or payload["observed_tick"] > old["observed_tick"]:
                self.statuses[payload["owner"]] = deepcopy(payload)
        elif kind == "RECEIPT":
            request = self.requests.get(payload.get("request_id"))
            if request is not None:
                request["receipt"] = deepcopy(payload)

    def on_outcome(self, request, outcome, now):
        row = self.requests.get(request.request_id)
        if row is not None:
            row["outcome"], row["finished_at"] = outcome, now

    def _new_request(self, view, tray, *, destination=None, unit=None):
        self.counter += 1
        intent = "empty_transfer" if destination is not None else "new_route"
        publication = self.forecasts.get(unit)
        request = ClockRequest(f"{self.owner}:{intent}:{self.counter}", self.owner,
                               None if destination is not None else tray.bag_id, tray.tray_id,
                               intent=intent, max_attempts=self.max_attempts,
                               departure_lead=self.departure_lead,
                               destination_node=destination, demand_id=unit,
                               demand_expires_at=(publication.expires_at if publication is not None
                                                  and unit not in self.observed_waiting_units else None))
        self.requests[request.request_id] = {"request": request, "submitted_at": view.observed_tick,
                                             "outcome": None, "receipt": None}
        self.trace.append({"time": view.observed_tick, "event": intent + "_requested",
                           "tray_id": tray.tray_id, "unit": unit, "destination": destination})
        return request

    def step(self, view, module):
        if view.owner != self.owner:
            raise ValueError("controller received another partition")
        now, network = view.observed_tick, view.public_topology
        self.seen_local_loaded.update(t.bag_id for t in view.local_trays if t.bag_id is not None)
        busy = {slot.tray_id for slot in view.local_calendars
                if slot.resource.startswith("edge:") and slot.end > now}
        own_status = self.statuses.get(self.owner)
        claimed_empty_ids = ({claim["tray_id"] for claim in own_status["accepted_demands"].values()}
                             if own_status is not None else set())
        for row in self.requests.values():
            if row["outcome"] in (None, "outcome_unknown"):
                busy.add(row["request"].tray_id)
            elif row["receipt"] and row["receipt"].get("usable_at", now) > now:
                busy.add(row["request"].tray_id)
        requests = []
        for request_id, row in self.requests.items():
            req = row["request"]
            forecast = self.forecasts.get(req.demand_id)
            known_loaded = req.demand_id in self.observed_loaded_units or req.demand_id in self.seen_local_loaded
            actual_waiting = req.demand_id in self.observed_waiting_units and not known_loaded
            wrong_actual_node = actual_waiting and self.observed_waiting_units[req.demand_id] != req.destination_node
            if (row["outcome"] is None and req.intent == "empty_transfer"
                    and (known_loaded or wrong_actual_node or (not actual_waiting and (req.demand_id in self.forecast_conflicts or (forecast is not None and
                         (forecast.cancelled or forecast.node != req.destination_node or forecast.expires_at <= now)))))
                    and not row.get("cancel_sent")):
                row["cancel_sent"] = True
                reason = "demand_already_loaded" if known_loaded else "observed_demand_origin_differs" if wrong_actual_node else "published_demand_cancelled_or_retargeted"
                requests.append(CancelUncommitted(request_id, reason))
        for tray in sorted(view.local_trays, key=lambda t: t.tray_id):
            if tray.mode != "loaded" or tray.tray_id in busy:
                continue
            previous = [row for row in self.requests.values() if row["request"].bag_id == tray.bag_id]
            if previous and now < max(row.get("finished_at", now) for row in previous) + self.period:
                continue
            requests.append(self._new_request(view, tray))
            busy.add(tray.tray_id)
        if self.mode == "none" or now % self.period or self.last_slow_tick == now:
            return tuple(requests)
        self.last_slow_tick = now
        unresolved_conflicts = self.forecast_conflicts - set(self.observed_waiting_units) - self.observed_loaded_units - self.seen_local_loaded
        if unresolved_conflicts:
            self.trace.append({"time": now, "event": "slow_blocked_forecast_conflict",
                               "units": tuple(sorted(unresolved_conflicts))})
            return tuple(requests)
        statuses = {owner: s for owner, s in self.statuses.items() if now - s["observed_tick"] <= self.status_max_age}
        loaded = set(self.seen_local_loaded) | self.observed_loaded_units
        for status in statuses.values():
            loaded.update(status["loaded_units"])
        local_waiting = {unit: node for unit, node in self.waiting_units.items() if unit not in loaded}
        pending_forecasts = {unit: f for unit, f in self.forecasts.items()
                             if unit not in loaded and unit not in self.observed_waiting_units and not f.cancelled and f.expires_at > now
                             and f.at <= now + self.forecast_horizon}
        source_needs = dict(local_waiting)
        # Source protection consumes only published forecasts. It is shared by
        # all transfer modes so a mode comparison cannot silently disable it.
        source_needs.update({unit: f.node for unit, f in pending_forecasts.items()
                             if network.nodes[f.node].control_partition == self.owner})
        source_need_times = {unit: max(now, pending_forecasts[unit].at) if unit in pending_forecasts else now
                             for unit in source_needs}
        remote_demands = {}
        if self.mode in {"reactive", "both"}:
            remote_demands.update({unit: (node, now) for unit, node in self.observed_waiting_units.items()
                                   if network.nodes[node].control_partition != self.owner})
        if self.mode in {"predictive", "both"}:
            remote_demands.update({unit: (f.node, max(now, f.at)) for unit, f in pending_forecasts.items()
                                  if network.nodes[f.node].control_partition != self.owner})
            # A published unit transitions into a real observed queue entry;
            # prediction expiry/cancellation cannot delete that actual task.
            remote_demands.update({unit: (node, now) for unit, node in self.observed_waiting_units.items()
                                   if unit in self.forecast_versions and network.nodes[node].control_partition != self.owner})
        claimed = set()
        for status in statuses.values():
            claimed.update(status["accepted_demands"])
            claimed.update(status["prepared_demands"])
        for row in self.requests.values():
            unit = row["request"].demand_id
            if unit is None:
                continue
            if row["outcome"] in (None, "outcome_unknown"):
                claimed.add(unit)
            elif row["receipt"] is not None:
                destination_owner = network.nodes[row["request"].destination_node].control_partition
                status = statuses.get(destination_owner)
                if status is None or status["observed_tick"] < row["receipt"]["usable_at"]:
                    claimed.add(unit)
        candidates = {unit: target for unit, target in remote_demands.items() if unit not in loaded and unit not in claimed}
        # Subtract actually reported free stock, never predicted releases.
        free_remote = {}
        for owner, status in statuses.items():
            if owner != self.owner:
                free_remote.update(status["available_empty"])
        demands = []
        for unit, (node, at) in sorted(candidates.items(), key=lambda item: (item[1][1], item[0])):
            if free_remote.get(node, 0) > 0:
                free_remote[node] -= 1
            else:
                demands.append((unit, node, at))
        available = [t for t in sorted(view.local_trays, key=lambda t: t.tray_id)
                     if t.mode == "empty" and t.available_at <= now and t.tray_id not in busy
                     and t.tray_id not in claimed_empty_ids]
        for unit, destination, at in demands:
            for tray in list(available):
                stock = sum(t.node == tray.node for t in available)
                if (stock <= module.export_min_stock or not self._reachable(network, tray.node, destination)
                        or not self._preserves_source_prefixes(view, available, tray, source_needs, source_need_times)):
                    continue
                requests.append(self._new_request(view, tray, destination=destination, unit=unit))
                available.remove(tray)
                break
        self.trace.append({"time": now, "event": "slow_tick", "mode": self.mode,
                           "published_forecast_units": tuple(sorted(pending_forecasts)),
                           "source_protected_units": tuple(sorted(source_needs)),
                           "uncovered_remote_units": tuple(unit for unit, _, _ in demands),
                           "empty_requests": sum(isinstance(r, ClockRequest) and r.intent == "empty_transfer" for r in requests)})
        return tuple(requests)

    def _preserves_source_prefixes(self, view, available, exported, needs, times):
        """Preserve achievable unit matching at every known demand prefix.

        Uses current real trays and directed paths wholly inside the visible
        owner/logistics zone. A tray can cover at most one unit. This is a
        conservative donor screen, not a capacity/timing service guarantee;
        no future release or inaccessible regional tray is counted as supply.
        """
        return preserves_source_prefixes(self.owner, view.public_topology, available, exported, needs, times)

    @staticmethod
    def _reachable(network, source, destination):
        visited, pending = {source}, [source]
        while pending:
            node = pending.pop()
            if node == destination:
                return True
            for edge in network.edges.values():
                if edge.source == node and edge.capacity > 0 and edge.target not in visited:
                    visited.add(edge.target)
                    pending.append(edge.target)
        return False
