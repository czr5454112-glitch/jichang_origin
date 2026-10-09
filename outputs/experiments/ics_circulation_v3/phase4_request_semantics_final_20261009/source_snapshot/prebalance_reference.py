"""Bounded forecast-rollout reference for empty-tray prebalancing.

This searches explicit short action sequences, not a globally optimal MPC.
Its proxy tape is built only from published forecasts; evaluation truth is not
an accepted input. Source-demand protection is the existing greedy contract.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, replace
from hashlib import sha256
import json
from time import perf_counter

from .model import Bag, RouteCandidate, Snapshot
from .prebalance import (
    PredictivePrebalancer, PrebalancePlan, _forecast_unit_ids, known_supply,
)
from .runtime import Simulation


def _action_key(sequence):
    """Physical sequence equivalence ignores serial commit-version labels."""
    return tuple(sorted((candidate.tray_id, candidate.destination_node,
                         tuple((leg.edge_id, leg.depart, leg.arrive) for leg in candidate.legs),
                         candidate.usable_at) for candidate in sequence))


def _latest_published(forecasts, now):
    # Conflicting versions have already been rejected by inherited _demand.
    latest = {}
    for forecast in forecasts:
        if forecast.published_at > now:
            continue
        key = ("id", forecast.forecast_id) if getattr(forecast, "forecast_id", None) is not None else ("bin", forecast.node, forecast.at)
        if key not in latest or forecast.published_at > latest[key].published_at:
            latest[key] = forecast
    return tuple(latest.values())


class BoundedForecastPrebalancer(PredictivePrebalancer):
    """Evaluate no transfer and bounded legal sequences under one proxy future.

    ``max_transfer_depth`` and the two departure variants define the action
    family. Path generation, per-state candidate limits, global search calls
    and rollout counts can further truncate it, which is always disclosed.
    Every selected transfer is finally submitted through the inherited owner.
    """

    def __init__(self, forecasts=(), *, planning_horizon=40, score_horizon=40,
                 max_rollouts=12, max_transfer_depth=2, paths_per_request=2,
                 max_pool_per_state=8, max_search_calls=32,
                 proxy_destinations=None, proxy_deadline_slack=20,
                 proxy_route_mode="whole_route", **kwargs):
        if min(score_horizon, max_rollouts, max_transfer_depth, paths_per_request,
               max_pool_per_state, max_search_calls, proxy_deadline_slack) < 1:
            raise ValueError("reference budgets must be positive")
        if proxy_route_mode not in {"whole_route", "next_edge"}:
            raise ValueError("invalid proxy route mode")
        kwargs.pop("planning_budget_ms", None)
        super().__init__(forecasts, planning_horizon=planning_horizon,
                         max_candidates=max_search_calls, max_proposals=max_transfer_depth,
                         planning_budget_ms=None, **kwargs)
        self.score_horizon = score_horizon
        self.max_rollouts = max_rollouts
        self.max_transfer_depth = max_transfer_depth
        self.paths_per_request = paths_per_request
        self.max_pool_per_state = max_pool_per_state
        self.max_search_calls = max_search_calls
        self.proxy_destinations = dict(proxy_destinations or {})
        self.proxy_deadline_slack = proxy_deadline_slack
        self.proxy_route_mode = proxy_route_mode

    def _proxy_future(self, snapshot, forecasts):
        """One causal point forecast; no real future or closed-loop labels."""
        future = []
        horizon = snapshot.now + self.score_horizon
        for forecast in _latest_published(forecasts, snapshot.now):
            if snapshot.now - forecast.published_at > self.max_forecast_age:
                continue
            units = _forecast_unit_ids(forecast)
            if units is None and forecast.at <= snapshot.now:
                continue
            arrival = max(snapshot.now + 1, forecast.at)
            if arrival > horizon or forecast.at > snapshot.now + self.planning_horizon:
                continue
            if units is None:
                token = sha256(json.dumps((forecast.node, forecast.at, forecast.published_at)).encode()).hexdigest()[:12]
                units = tuple(f"forecast_proxy:{token}:{index}" for index in range(forecast.count))
            pending = [unit for unit in units if unit not in snapshot.bags]
            if not pending:
                continue
            destination = getattr(forecast, "destination", self.proxy_destinations.get(forecast.node))
            if destination not in snapshot.network.nodes:
                raise ValueError(f"published forecast at {forecast.node} needs a configured proxy destination")
            deadline = getattr(forecast, "deadline", arrival + self.proxy_deadline_slack)
            if not isinstance(deadline, int) or isinstance(deadline, bool):
                raise ValueError("proxy deadline must be an integer tick")
            future.extend(Bag(unit, forecast.node, destination, arrival, deadline)
                          for unit in pending)
        if len({bag.bag_id for bag in future}) != len(future):
            raise ValueError("published forecasts duplicate a pending unit identity")
        return tuple(sorted(future, key=lambda bag: (bag.arrival, bag.bag_id)))

    def _gaps(self, snapshot, demand):
        supplies = known_supply(snapshot)
        known_ids = {item.tray_id for item in supplies}
        pending = defaultdict(int)
        for tray_id, destination in snapshot.empty_targets.items():
            if tray_id not in known_ids:
                pending[destination] += 1
        ordinals = defaultdict(int)
        gaps = []
        units = 0
        for event in demand:
            for _ in range(event.count):
                units += 1
                if units > self.max_demand_units:
                    return gaps, True
                ordinal = ordinals[event.node]
                ordinals[event.node] += 1
                if ordinal < pending[event.node]:
                    continue
                ordinal -= pending[event.node]
                times = sorted(item.at for item in supplies if item.node == event.node)
                promised = times[ordinal] if ordinal < len(times) else None
                if promised is None or promised > event.at:
                    gaps.append((event, promised))
        return gaps, False

    def _candidate_pool(self, snapshot, demand, diagnostics):
        gaps, truncated = self._gaps(snapshot, demand)
        diagnostics["demand_units_truncated"] |= truncated
        supplies = known_supply(snapshot)
        pool, seen = [], set()
        for event, promised in gaps:
            for tray_id, tray in sorted(snapshot.trays.items()):
                if (tray.mode != "empty" or tray.node is None or tray.bag_id is not None
                        or tray.available_at > snapshot.now or tray_id in snapshot.plans
                        or tray_id in snapshot.empty_targets
                        or any(flight.tray_id == tray_id for flight in snapshot.old_in_transit)):
                    continue
                if snapshot.network.nodes[tray.node].logistics_zone == snapshot.network.nodes[event.node].logistics_zone:
                    continue
                reason = self._donor_protection(snapshot, tray_id, supplies, demand)
                if reason:
                    diagnostics["donor_rejections"].append({"tray_id": tray_id, "node": event.node, "reason": reason})
                    continue
                if diagnostics["search_calls"] >= self.max_search_calls:
                    diagnostics["search_budget_exhausted"] = True
                    return tuple(pool)
                generator = self.generator_factory()
                diagnostics["search_calls"] += 1
                candidates = generator.generate_empty(snapshot, tray_id, event.node, k=self.paths_per_request)
                diagnostics["search_expansions"] += getattr(generator, "last_expansions", 0)
                diagnostics["generator_statuses"].append(getattr(generator, "last_search_status", "unknown"))
                for candidate in candidates:
                    if (candidate.tray_id != tray_id or candidate.bag_id is not None
                            or candidate.destination_node != event.node):
                        diagnostics["candidate_rejections"].append({"tray_id": tray_id, "reason": "candidate_identity_or_destination_mismatch"})
                        continue
                    if promised is not None and candidate.usable_at >= promised:
                        continue
                    variants = [candidate]
                    shift = event.at - candidate.usable_at
                    if shift > 0:
                        variants.append(replace(candidate,
                                                legs=tuple(replace(leg, depart=leg.depart + shift, arrive=leg.arrive + shift) for leg in candidate.legs),
                                                unload_complete=candidate.unload_complete + shift,
                                                usable_at=candidate.usable_at + shift))
                    for variant in variants:
                        key = _action_key((variant,))
                        if key in seen:
                            continue
                        verdict = self.validator.validate(snapshot, variant)
                        if not verdict.accepted:
                            diagnostics["candidate_rejections"].append({"tray_id": tray_id, "reason": verdict.reason})
                            continue
                        if len(pool) >= self.max_pool_per_state:
                            diagnostics["candidate_pool_truncated"] = True
                            return tuple(pool)
                        seen.add(key)
                        pool.append(variant)
        return tuple(pool)

    def _score(self, snapshot, proxy_future):
        engine = Simulation(snapshot, proxy_future, route_mode=self.proxy_route_mode,
                            generator_factory=self.generator_factory,
                            reactive_empty_dispatch=True, slow_controller=None,
                            search_horizon=self.score_horizon)
        return engine.advance(snapshot.now + self.score_horizon)

    def plan(self, snapshot: Snapshot, forecasts) -> PrebalancePlan:
        begin = perf_counter()
        diagnostics = {
            "method": "bounded_legal_empty_sequence_forecast_rollout",
            "snapshot_time": snapshot.now, "snapshot_version": snapshot.version,
            "accepted_forecasts": [], "ignored_forecasts": [], "donor_rejections": [],
            "candidate_rejections": [], "proposal_details": [], "search_calls": 0,
            "search_expansions": 0, "generator_statuses": [], "rollout_calls": 0,
            "rollout_ms": 0.0, "scored_actions": [], "candidate_pool_truncated": False,
            "demand_units_truncated": False, "search_budget_exhausted": False,
            "rollout_budget_exhausted": False, "failed_proxy_rollouts": [],
            "limits": {"max_rollouts": self.max_rollouts, "max_transfer_depth": self.max_transfer_depth,
                       "paths_per_request": self.paths_per_request, "max_pool_per_state": self.max_pool_per_state,
                       "max_search_calls": self.max_search_calls, "score_horizon": self.score_horizon},
            "claim": "best_scored_action_only_under_one_published_forecast_proxy_not_global_optimum",
            "continuation": "fixed_earliest_route_and_reactive_empty_dispatch_no_recursive_predictor",
            "action_family": "up_to_depth_cross_zone_empty_transfers_earliest_or_valid_need_time_shift",
        }
        demand = self._demand(snapshot, forecasts, diagnostics)
        diagnostics["demand"] = [asdict(event) for event in demand]
        unadmitted = [tray.bag_id for tray in snapshot.trays.values()
                      if tray.mode == "loaded" and tray.tray_id not in snapshot.plans
                      and tray.bag_id is not None and snapshot.bags[tray.bag_id].protected]
        if unadmitted:
            diagnostics.update({"status": "no_transfer_protected_obligation_not_admitted", "unadmitted_protected_bags": unadmitted,
                                "proposal_count": 0, "elapsed_ms": (perf_counter() - begin) * 1000})
            return PrebalancePlan((), diagnostics)
        pool = self._candidate_pool(snapshot, demand, diagnostics)
        diagnostics["initial_pool_size"] = len(pool)
        if not pool:
            # Empty bounded search is not a proof that every physical transfer
            # is impossible; path search may itself be incomplete.
            diagnostics.update({"status": "no_transfer_only_from_bounded_candidate_search", "selected_action_index": 0,
                                "proposal_count": 0, "elapsed_ms": (perf_counter() - begin) * 1000})
            return PrebalancePlan((), diagnostics)
        proxy = self._proxy_future(snapshot, forecasts)
        diagnostics["proxy_future"] = [asdict(bag) for bag in proxy]
        diagnostics["proxy_future_sha256"] = sha256(json.dumps(diagnostics["proxy_future"], sort_keys=True).encode()).hexdigest()
        # Queue root first to make no transfer a mandatory, equally scored action.
        queue = deque([(snapshot.clone(), (), pool)])
        visited = {()}
        best_sequence, best_value, best_index = (), None, None
        while queue and diagnostics["rollout_calls"] < self.max_rollouts:
            state, sequence, known_pool = queue.popleft()
            rollout_started = perf_counter()
            diagnostics["rollout_calls"] += 1
            try:
                result = self._score(state, proxy)
                cost = result.total_cost
                index = len(diagnostics["scored_actions"])
                diagnostics["scored_actions"].append({"action_index": index, "transfers": [asdict(candidate) for candidate in sequence],
                                                       "proxy_cost": cost, "cost_components": result.cost_components,
                                                       "uncompleted_bag_ids": list(result.uncompleted_bag_ids),
                                                       "invariant_checks": result.invariant_checks})
                ranking = (cost, len(sequence), _action_key(sequence))
                if best_value is None or ranking < best_value:
                    best_sequence, best_value, best_index = sequence, ranking, index
            except (ValueError, AssertionError) as error:
                diagnostics["failed_proxy_rollouts"].append({"transfers": [asdict(candidate) for candidate in sequence],
                                                              "type": type(error).__name__, "message": str(error)})
            finally:
                diagnostics["rollout_ms"] += (perf_counter() - rollout_started) * 1000
            if len(sequence) >= self.max_transfer_depth:
                continue
            candidates = known_pool if known_pool is not None else self._candidate_pool(state, demand, diagnostics)
            for candidate in candidates:
                combined = sequence + (candidate,)
                key = _action_key(combined)
                if key in visited:
                    continue
                child = state.clone()
                verdict = self.validator.commit(child, candidate)
                if not verdict.accepted:
                    diagnostics["candidate_rejections"].append({"tray_id": candidate.tray_id, "reason": verdict.reason})
                    continue
                visited.add(key)
                queue.append((child, combined, None))
        diagnostics["rollout_budget_exhausted"] = bool(queue)
        diagnostics["enumerated_action_count"] = len(visited)
        diagnostics["unscored_enumerated_actions"] = len(queue)
        diagnostics["selected_action_index"] = best_index
        diagnostics["selected_proxy_cost"] = None if best_value is None else best_value[0]
        diagnostics["status"] = ("partial_bounded_search" if queue or diagnostics["candidate_pool_truncated"]
                                 or diagnostics["search_budget_exhausted"] or diagnostics["demand_units_truncated"]
                                 or diagnostics["failed_proxy_rollouts"]
                                 else "all_generated_sequences_scored_within_declared_depth")
        diagnostics["proposal_count"] = len(best_sequence)
        diagnostics["proposal_details"] = [{"tray_id": candidate.tray_id, "destination": candidate.destination_node,
                                             "first_depart": candidate.legs[0].depart if candidate.legs else snapshot.now,
                                             "usable_at": candidate.usable_at, "dependency_version": candidate.dependency_version}
                                            for candidate in best_sequence]
        diagnostics["elapsed_ms"] = (perf_counter() - begin) * 1000
        return PrebalancePlan(best_sequence, diagnostics)
