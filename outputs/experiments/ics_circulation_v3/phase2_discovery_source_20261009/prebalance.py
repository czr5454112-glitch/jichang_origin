"""Bounded, non-learning cross-zone empty-tray prebalancing.

Forecasts are incremental *future* arrivals, not cumulative inventory targets.
Elapsed forecast arrival times are discarded: the visible bag queue then owns
that demand. The inventory approximation uses only each real tray's first known
empty release and never invents further cycles or a supplier-module response.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Callable, Protocol, Sequence

from .model import RouteCandidate, Snapshot
from .runtime import CandidateGenerator, ExecutionValidator


class DemandForecast(Protocol):
    node: str
    at: int
    count: int
    published_at: int


@dataclass(frozen=True)
class SupplyEvent:
    tray_id: str
    node: str
    at: int
    source: str


@dataclass(frozen=True)
class DemandEvent:
    node: str
    at: int
    count: int
    source: str


@dataclass(frozen=True)
class PrebalancePlan:
    proposals: tuple[RouteCandidate, ...]
    diagnostics: dict


def known_supply(snapshot: Snapshot) -> tuple[SupplyEvent, ...]:
    """Count each tray once, after unload/hold, prioritizing irrevocable plans."""
    supplies = []
    old = {flight.tray_id: flight for flight in snapshot.old_in_transit}
    for tray_id, tray in sorted(snapshot.trays.items()):
        if tray_id in snapshot.plans:
            plan = snapshot.plans[tray_id]
            if getattr(plan, "prefix_only", False):
                continue  # A safe stopping prefix is not a terminal empty release.
            destination = (snapshot.bags[plan.bag_id].destination if plan.bag_id is not None
                           else plan.destination_node)
            last_node = snapshot.network.edges[plan.legs[-1].edge_id].target if plan.legs else tray.node
            if last_node != destination:
                continue
            supplies.append(SupplyEvent(tray_id, destination, max(snapshot.now, plan.usable_at), "committed_release"))
        elif tray_id in old:
            flight = old[tray_id]
            node = snapshot.network.edges[flight.edge_id].target
            available = flight.arrive + snapshot.module.hold_ticks(node)
            if tray.bag_id is not None:
                if snapshot.bags[tray.bag_id].destination != node:
                    continue  # Entering another node while loaded is not empty supply.
                available += snapshot.module.unload_ticks
            supplies.append(SupplyEvent(tray_id, node, max(snapshot.now, available), "old_in_transit_release"))
        elif (tray.node is not None and tray.mode in {"empty", "holding", "unloading"}
              and tray_id not in getattr(snapshot, "empty_targets", {})):
            supplies.append(SupplyEvent(tray_id, tray.node, max(snapshot.now, tray.available_at), "stationary_release"))
    return tuple(supplies)


class PredictivePrebalancer:
    """Greedy first-use inventory repair; no global optimality or MPC claim.

    Only generator calls/proposals and checks *between* generator calls are
    bounded here. A wall-time budget cannot interrupt an individual search.
    Executable permissions, capacity and physical identity remain with the
    existing ExecutionValidator. ``plan`` only mutates a private clone.
    """

    def __init__(self, forecasts: Sequence[DemandForecast] = (), *,
                 planning_horizon: int = 40, max_forecast_age: int = 60,
                 max_candidates: int = 32, max_proposals: int = 8,
                 max_demand_units: int = 256, planning_budget_ms: float | None = 100.0,
                 generator_factory: Callable[[], CandidateGenerator] | None = None,
                 validator: ExecutionValidator | None = None):
        if min(planning_horizon, max_candidates, max_proposals, max_demand_units) <= 0 or max_forecast_age < 0:
            raise ValueError("planning/count bounds must be positive and forecast age nonnegative")
        if planning_budget_ms is not None and planning_budget_ms <= 0:
            raise ValueError("planning_budget_ms must be positive or None")
        self.forecasts = tuple(forecasts)
        self.planning_horizon = planning_horizon
        self.max_forecast_age = max_forecast_age
        self.max_candidates = max_candidates
        self.max_proposals = max_proposals
        self.max_demand_units = max_demand_units
        self.planning_budget_ms = planning_budget_ms
        self.generator_factory = generator_factory or (lambda: CandidateGenerator(horizon=planning_horizon))
        self.validator = validator or ExecutionValidator()
        self.last_diagnostics: dict = {}
        self.history: list[dict] = []

    def _demand(self, snapshot: Snapshot, forecasts: Sequence[DemandForecast], diagnostics: dict) -> tuple[DemandEvent, ...]:
        carried = {tray.bag_id for tray in snapshot.trays.values() if tray.bag_id is not None}
        events = [DemandEvent(bag.origin, snapshot.now, 1, f"visible_queue:{bag.bag_id}")
                  for bag in snapshot.bags.values()
                  if bag.bag_id not in snapshot.completed and bag.bag_id not in carried]
        latest = {}
        for forecast in forecasts:
            values = (forecast.at, forecast.count, forecast.published_at)
            if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
                raise ValueError("forecast times/count must be integer ticks/counts")
            if forecast.node not in snapshot.network.nodes or forecast.count < 0:
                raise ValueError("invalid forecast node/count")
            row = {"node": forecast.node, "at": forecast.at, "count": forecast.count,
                   "published_at": forecast.published_at}
            reason = ("future_publication" if forecast.published_at > snapshot.now else
                      "expired_arrival_use_visible_queue" if forecast.at <= snapshot.now else
                      "stale_publication" if snapshot.now - forecast.published_at > self.max_forecast_age else
                      "beyond_planning_horizon" if forecast.at > snapshot.now + self.planning_horizon else None)
            if reason:
                diagnostics["ignored_forecasts"].append({**row, "reason": reason})
                continue
            # An optional stable ID supports revisions that move the arrival.
            # Without IDs, equal node/time bins are successive forecast vintages.
            key = ("id", forecast.forecast_id) if getattr(forecast, "forecast_id", None) is not None else ("bin", forecast.node, forecast.at)
            previous = latest.get(key)
            if previous is None or forecast.published_at > previous.published_at:
                latest[key] = forecast
            elif forecast.published_at == previous.published_at and (forecast.node, forecast.at, forecast.count) != (previous.node, previous.at, previous.count):
                raise ValueError("conflicting forecast values for one identity/publication")
        for forecast in latest.values():
            count = forecast.count
            identity_details = {}
            if hasattr(forecast, "unit_ids"):
                unit_ids = tuple(forecast.unit_ids)
                if not unit_ids and count:
                    forecast_id = getattr(forecast, "forecast_id", None)
                    if forecast_id is None:
                        raise ValueError("identity-aware forecasts need explicit unit_ids or forecast_id")
                    unit_ids = tuple(f"{forecast_id}:{index}" for index in range(count))
                if len(unit_ids) != count or len(set(unit_ids)) != count:
                    raise ValueError("forecast unit_ids must be unique and match count")
                observed = tuple(unit for unit in unit_ids if unit in snapshot.bags)
                remaining = tuple(unit for unit in unit_ids if unit not in snapshot.bags)
                count = len(remaining)
                identity_details = {"unit_ids": remaining, "observed_units_removed": observed}
            diagnostics["accepted_forecasts"].append({"node": forecast.node, "at": forecast.at,
                                                     "count": count, "published_at": forecast.published_at,
                                                     **identity_details})
            if count:
                events.append(DemandEvent(forecast.node, forecast.at, count, "published_forecast"))
        return tuple(sorted(events, key=lambda event: (event.at, event.node, event.source)))

    @staticmethod
    def _donor_protection(snapshot: Snapshot, tray_id: str, supplies: tuple[SupplyEvent, ...],
                          demand: tuple[DemandEvent, ...]) -> str | None:
        tray = snapshot.trays[tray_id]
        zone = snapshot.network.nodes[tray.node].logistics_zone
        local_supplies = [item for item in supplies if snapshot.network.nodes[item.node].logistics_zone == zone]
        local_demand = [item for item in demand if snapshot.network.nodes[item.node].logistics_zone == zone]
        times = sorted({snapshot.now} | {item.at for item in local_demand})
        for tick in times:
            supply_count = sum(item.at <= tick for item in local_supplies) - 1
            demand_count = sum(item.count for item in local_demand if item.at <= tick)
            if supply_count - demand_count < snapshot.module.export_min_stock:
                return f"source_zone_prefix_min_stock:{zone}@{tick}"
            # Protect the donor's own loading point too; remote same-zone stock
            # is not an assumed instantaneous response from the local module.
            node_supply = sum(item.node == tray.node and item.at <= tick for item in supplies) - 1
            node_demand = sum(item.count for item in demand if item.node == tray.node and item.at <= tick)
            if node_supply < node_demand:
                return f"source_node_demand_prefix:{tray.node}@{tick}"
        return None

    def plan(self, snapshot: Snapshot, forecasts: Sequence[DemandForecast]) -> PrebalancePlan:
        started = perf_counter()
        scratch = snapshot.clone()
        diagnostics = {
            "method": "bounded_greedy_first_known_empty_release",
            "snapshot_time": snapshot.now, "snapshot_version": snapshot.version,
            "horizon_end": snapshot.now + self.planning_horizon,
            "accepted_forecasts": [], "ignored_forecasts": [],
            "donor_rejections": [], "candidate_rejections": [], "proposal_details": [],
            "pending_empty_obligations": [], "demand_covered_by_pending_empty_obligation": [],
            "search_calls": 0, "search_expansions": 0, "bounded_stop": None,
            "irrevocable_existing_plans": len(snapshot.plans),
            "old_in_transit_count": len(snapshot.old_in_transit),
            "limits": {"max_candidates": self.max_candidates, "max_proposals": self.max_proposals,
                       "max_demand_units": self.max_demand_units, "planning_budget_ms": self.planning_budget_ms},
            "assumptions": ["Forecast bins are incremental future arrivals; elapsed bins are replaced by the visible queue.",
                            "Identity-aware forecast units already in the visible bag ledger are removed; aggregate forecasts have no inferred identity matching.",
                            "Only the first known empty release per tray is credited; uncommitted reuse is not forecast.",
                            "An accepted empty continuation with unknown final ETA conservatively covers one target demand; no timed release is invented and no duplicate replacement is sent.",
                            "Source logistics-zone and donor-node demand prefixes are protected within the finite planning horizon.",
                            "Capacity and module permissions are revalidated; accepted routes remain irrevocable.",
                            "Latest-departure shifting is attempted on an earliest route; failed shifts retain the feasible earliest route."],
        }
        demand = self._demand(snapshot, forecasts, diagnostics)
        diagnostics["initial_supply"] = [vars(event) for event in known_supply(snapshot)]
        known_ids = {event.tray_id for event in known_supply(snapshot)}
        diagnostics["pending_empty_obligations"] = [
            {"tray_id": tray_id, "destination": destination, "final_available_at": None}
            for tray_id, destination in sorted(getattr(snapshot, "empty_targets", {}).items())
            if tray_id not in known_ids
        ]
        diagnostics["demand"] = [vars(event) for event in demand]
        slots = []
        for event in demand:
            for _ in range(min(event.count, max(0, self.max_demand_units - len(slots)))):
                slots.append(event)
        if sum(event.count for event in demand) > len(slots):
            diagnostics["demand_units_truncated"] = True
        proposals = []
        node_ordinals: dict[str, int] = defaultdict(int)

        def budget_exhausted() -> bool:
            if diagnostics["search_calls"] >= self.max_candidates:
                diagnostics["bounded_stop"] = "max_candidates"
            elif len(proposals) >= self.max_proposals:
                diagnostics["bounded_stop"] = "max_proposals"
            elif self.planning_budget_ms is not None and (perf_counter() - started) * 1000 >= self.planning_budget_ms:
                diagnostics["bounded_stop"] = "planning_budget_between_searches"
            return diagnostics["bounded_stop"] is not None

        for event in slots:
            ordinal = node_ordinals[event.node]
            node_ordinals[event.node] += 1
            if budget_exhausted():
                break
            supplies = known_supply(scratch)
            known_ids = {item.tray_id for item in supplies}
            pending = sum(destination == event.node and tray_id not in known_ids
                          for tray_id, destination in getattr(scratch, "empty_targets", {}).items())
            if ordinal < pending:
                diagnostics["demand_covered_by_pending_empty_obligation"].append(
                    {"node": event.node, "need_at": event.at, "ordinal": ordinal,
                     "reason": "accepted_empty_continuation_final_eta_unknown"})
                continue
            ordinal -= pending
            target_supplies = sorted((item.at, item.tray_id) for item in supplies if item.node == event.node)
            promised_at = target_supplies[ordinal][0] if ordinal < len(target_supplies) else None
            if promised_at is not None and promised_at <= event.at:
                continue
            choices = []
            for tray_id, tray in sorted(scratch.trays.items()):
                if budget_exhausted():
                    break
                if (tray.mode != "empty" or tray.node is None or tray.available_at > scratch.now
                        or tray.bag_id is not None or tray_id in scratch.plans
                        or tray_id in getattr(scratch, "empty_targets", {})
                        or any(flight.tray_id == tray_id for flight in scratch.old_in_transit)):
                    continue
                if scratch.network.nodes[tray.node].logistics_zone == scratch.network.nodes[event.node].logistics_zone:
                    continue
                protection = self._donor_protection(scratch, tray_id, supplies, demand)
                if protection:
                    diagnostics["donor_rejections"].append({"tray_id": tray_id, "node": event.node, "reason": protection})
                    continue
                generator = self.generator_factory()
                diagnostics["search_calls"] += 1
                generated = generator.generate_empty(scratch, tray_id, event.node, k=1)
                diagnostics["search_expansions"] += getattr(generator, "last_expansions", 0)
                if not generated:
                    diagnostics["candidate_rejections"].append({"tray_id": tray_id, "node": event.node,
                                                                "reason": "no_feasible_candidate", "search_status": getattr(generator, "last_search_status", "unknown")})
                    continue
                candidate = generated[0]
                if (candidate.tray_id != tray_id or candidate.bag_id is not None
                        or candidate.destination_node != event.node):
                    diagnostics["candidate_rejections"].append({"tray_id": tray_id, "reason": "candidate_identity_or_destination_mismatch"})
                    continue
                result = self.validator.validate(scratch, candidate)
                if not result.accepted:
                    diagnostics["candidate_rejections"].append({"tray_id": tray_id, "reason": result.reason})
                    continue
                if promised_at is not None and candidate.usable_at >= promised_at:
                    diagnostics["candidate_rejections"].append({"tray_id": tray_id, "reason": "existing_supply_arrives_no_later"})
                    continue
                shift = max(0, event.at - candidate.usable_at)
                if shift:
                    delayed = replace(candidate,
                                      legs=tuple(replace(leg, depart=leg.depart + shift, arrive=leg.arrive + shift) for leg in candidate.legs),
                                      unload_complete=candidate.unload_complete + shift,
                                      usable_at=candidate.usable_at + shift)
                    if self.validator.validate(scratch, delayed).accepted:
                        candidate = delayed
                choices.append(candidate)
            if not choices:
                continue
            # Compare tardiness first, then empty travel. Route generation and
            # source protection use exactly the same observable snapshot.
            choice = min(choices, key=lambda c: (max(0, c.usable_at - event.at),
                                                sum(scratch.network.edges[leg.edge_id].travel_time for leg in c.legs), c.tray_id))
            result = self.validator.commit(scratch, choice)
            if not result.accepted:
                diagnostics["candidate_rejections"].append({"tray_id": choice.tray_id, "reason": result.reason})
                continue
            proposals.append(choice)
            diagnostics["proposal_details"].append({"tray_id": choice.tray_id, "destination": event.node,
                                                    "need_at": event.at, "usable_at": choice.usable_at,
                                                    "first_depart": choice.legs[0].depart if choice.legs else scratch.now,
                                                    "previous_supply_at": promised_at,
                                                    "dependency_version": choice.dependency_version})
        diagnostics["proposal_count"] = len(proposals)
        diagnostics["elapsed_ms"] = (perf_counter() - started) * 1000
        return PrebalancePlan(tuple(proposals), diagnostics)

    def __call__(self, snapshot: Snapshot) -> tuple[RouteCandidate, ...]:
        plan = self.plan(snapshot, self.forecasts)
        accepted = []
        diagnostics = dict(plan.diagnostics)
        diagnostics["commit_results"] = []
        for proposal in plan.proposals:
            result = self.validator.commit(snapshot, proposal)
            diagnostics["commit_results"].append({"tray_id": proposal.tray_id,
                                                   "accepted": result.accepted, "reason": result.reason})
            if not result.accepted:
                break  # Dependent versions are stale; do not re-stamp or bypass validation.
            accepted.append(proposal)
        diagnostics["committed_count"] = len(accepted)
        self.last_diagnostics = diagnostics
        self.history.append(diagnostics)
        return tuple(accepted)


@dataclass(frozen=True)
class SyntheticPrebalanceFixture:
    name: str
    snapshot: Snapshot
    forecasts: tuple
    future_bags: tuple  # Event-engine/runner input only; never an argument to the controller.
    horizon: int


def synthetic_prebalance_fixtures() -> tuple[SyntheticPrebalanceFixture, ...]:
    """Four deterministic mechanism examples, with explicitly assumed timings."""
    from .evaluation import ForecastDemand
    from .model import Bag, Edge, FixedLocalModule, InFlight, Network, Node, Tray

    network = Network(
        {name: Node(name, zone, f"control:{name}", capacity=4)
         for name, zone in (("A", "domestic"), ("B", "international"), ("C", "domestic"))},
        {edge.edge_id: edge for edge in (Edge("A-B", "A", "B", 8), Edge("B-A", "B", "A", 8), Edge("old-C-B", "C", "B", 8))},
    )
    base = Snapshot(0, network, {"donor": Tray("donor", "A")}, {})
    forecast = (ForecastDemand("B", 8),)
    future = (Bag("B:future", "B", "A", 8, 28),)
    old = base.clone()
    old.trays["old"] = Tray("old", None, "in_transit")
    old.old_in_transit = (InFlight("old", "old-C-B", -2, 6),)
    old.module = FixedLocalModule(hold_by_node={"B": 2})
    local = base.clone()
    local_forecast = (ForecastDemand("A", 4), ForecastDemand("B", 8))
    local_future = (Bag("A:future", "A", "B", 4, 24),) + future
    return (
        SyntheticPrebalanceFixture("long_connection_needs_advance", base, forecast, future, 28),
        SyntheticPrebalanceFixture("old_arrival_prevents_duplicate", old, forecast, future, 28),
        SyntheticPrebalanceFixture("source_near_term_demand_protected", local, local_forecast, local_future, 32),
        SyntheticPrebalanceFixture("forecast_reversal_irrevocable", base.clone(), forecast,
                                   (Bag("A:unexpected", "A", "B", 2, 20),), 32),
    )
