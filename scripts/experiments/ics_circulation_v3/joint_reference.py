"""Finite-domain joint control and causal rolling enumeration MPC.

The search uses the real external-control Simulation kernel, all integer
departures and positive-time walks (including cycles), arbitrary same-tick
commit orders, and future physical releases/reuse. Completeness refers only to
the declared whole-route domain, never to a bounded candidate pool. Existing
commitments cannot be cancelled. Source protection is the same fixed module
export floor and mandatory FIFO loading for every controller in this module;
the extra first-supply donor heuristic from PredictivePrebalancer is not used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from collections import defaultdict
from heapq import heappop, heappush
from itertools import count
import hashlib
import json
from time import perf_counter

from .learning import active_forecasts
from .model import Bag, Leg, RouteCandidate, Snapshot
from .routing import _ResourceView
from .runtime import COST_WEIGHTS, ExecutionValidator, Simulation


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class JointDomain:
    horizon: int
    route_tail_ticks: int = 0
    expansion_limit: int = 100000
    deadline_ms: float | None = None

    def __post_init__(self):
        if (type(self.horizon) is not int or type(self.route_tail_ticks) is not int or self.route_tail_ticks < 0
                or type(self.expansion_limit) is not int or self.expansion_limit < 1):
            raise ValueError("Invalid finite joint domain")
        if self.deadline_ms is not None and (self.deadline_ms <= 0 or not float(self.deadline_ms) < float("inf")):
            raise ValueError("deadline_ms must be finite positive or None")

    @property
    def route_end_tick(self):
        return self.horizon + self.route_tail_ticks


@dataclass(frozen=True)
class TimedJointAction:
    tick: int
    tray_id: str
    bag_id: str | None
    destination: str
    legs: tuple[Leg, ...]
    unload_complete: int
    usable_at: int

    @classmethod
    def from_candidate(cls, tick, candidate):
        return cls(tick, candidate.tray_id, candidate.bag_id, candidate.destination_node,
                   candidate.legs, candidate.unload_complete, candidate.usable_at)

    def proposal(self, snapshot):
        # New proposal at the current version; never a bypass of validation.
        identifier = "joint:" + _digest(asdict(self))[:20]
        return RouteCandidate(identifier, self.bag_id, self.tray_id, self.legs, self.unload_complete,
                              self.usable_at, snapshot.version, identifier, True, self.destination)


@dataclass(frozen=True)
class JointSearchResult:
    status: str
    complete: bool
    total_cost: float | None
    lower_bound: float | None
    gap: float | None
    first_actions: tuple[RouteCandidate, ...]
    schedule: tuple[TimedJointAction, ...]
    cost_components: dict | None
    diagnostics: dict


class _StopSearch(Exception):
    pass


class _Budget:
    def __init__(self, domain):
        self.domain, self.started, self.used = domain, perf_counter(), 0
        self.counts, self.reason = defaultdict(int), None

    def spend(self, kind):
        if self.used >= self.domain.expansion_limit:
            self.reason = "work_budget_exhausted"
            raise _StopSearch
        if self.domain.deadline_ms is not None and (perf_counter() - self.started) * 1000 >= self.domain.deadline_ms:
            self.reason = "deadline_exhausted"
            raise _StopSearch
        self.used += 1
        self.counts[kind] += 1


def _routes(state, tray_id, destination, domain, budget):
    """Lazy complete integer walk enumeration within route_end_tick.

    Calendar pruning is exact for the physical resource intervals. Terminal
    acceptance always comes from ExecutionValidator, including protected
    deadlines, export floors, reception hold and empty destination obligations.
    """
    tray = state.trays[tray_id]
    if (tray.node is None or tray.mode not in {"loaded", "empty"} or tray.available_at > state.now
            or tray_id in state.plans or any(f.tray_id == tray_id for f in state.old_in_transit)):
        return
    outgoing, incoming = defaultdict(list), defaultdict(list)
    for edge in sorted(state.network.edges.values(), key=lambda edge: edge.edge_id):
        budget.spend("route_preprocessing_edges")
        if edge.capacity > 0:
            outgoing[edge.source].append(edge)
            incoming[edge.target].append(edge)
    lower, reverse = {destination: 0}, [(0, destination)]
    while reverse:
        budget.spend("route_reverse_labels")
        distance, node = heappop(reverse)
        if distance != lower[node]:
            continue
        for edge in incoming[node]:
            value = distance + edge.travel_time
            if value < lower.get(edge.source, float("inf")):
                lower[edge.source] = value
                heappush(reverse, (value, edge.source))
    if tray.node not in lower:
        return
    view, serial = _ResourceView(state, tray_id), count()
    queue = [(state.now + lower[tray.node], next(serial), tray.node, state.now, ())]
    validator = ExecutionValidator()
    while queue:
        budget.spend("route_time_labels")
        _, _, node, tick, legs = heappop(queue)
        if node == destination and (legs or tray.bag_id is not None):
            unload = tick + (state.module.unload_ticks if tray.bag_id is not None else 0)
            action = TimedJointAction(state.now, tray_id, tray.bag_id, destination, legs, unload,
                                      unload + state.module.hold_ticks(destination))
            proposal = action.proposal(state)
            budget.spend("candidate_validations")
            if validator.validate(state, proposal, route_mode="whole_route").accepted:
                yield proposal
        latest = domain.route_end_tick - lower[node]
        departures = range(tick, latest + 1) if state.network.nodes[node].can_wait else (tick,)
        for depart in departures:
            for edge in outgoing[node]:
                budget.spend("integer_transitions")
                if edge.target not in lower or depart + edge.travel_time + lower[edge.target] > domain.route_end_tick:
                    continue
                arrive = depart + edge.travel_time
                if (view.available(f"node:{node}", tick, depart)
                        and view.available(f"edge:{edge.edge_id}", depart, arrive)):
                    heappush(queue, (arrive + lower[edge.target], next(serial), edge.target, arrive,
                                     legs + (Leg(edge.edge_id, depart, arrive),)))


def _actions(state, used, domain, budget, future_priorities=()):
    visible = [bag.origin for bag in state.bags.values() if bag.bag_id not in state.completed
               and bag.bag_id not in state.load_times]
    priority = tuple(dict.fromkeys(visible + list(future_priorities)))
    trays = sorted(state.trays.values(), key=lambda tray: (
        tray.bag_id is None, not (tray.bag_id is not None and state.bags[tray.bag_id].protected), tray.tray_id))
    for tray in trays:
        if tray.tray_id in used or tray.tray_id in state.plans or tray.mode not in {"loaded", "empty"}:
            continue
        if tray.bag_id is not None:
            destinations = (state.bags[tray.bag_id].destination,)
        elif tray.tray_id in state.empty_targets:
            destinations = (state.empty_targets[tray.tray_id],)
        else:
            destinations = sorted((node for node, item in state.network.nodes.items() if item.can_wait),
                                  key=lambda node: (node not in priority, priority.index(node) if node in priority else 0, node))
        for destination in destinations:
            yield from _routes(state, tray.tray_id, destination, domain, budget)


def _paid_lower_bound(result):
    # These components cannot decrease as the physical episode advances.
    return sum(COST_WEIGHTS[key] * result.cost_components[key]
               for key in ("tray_wait", "empty_distance", "nonprotected_tardiness"))


def _seed_episode(initial, future_bags, domain, budget, warm_start=()):
    """Feasible incumbent only; it never defines or truncates the exact domain."""
    engine = Simulation(initial, future_bags, control_mode="external", route_mode="whole_route")
    schedule = []
    warm = defaultdict(list)
    for action in warm_start:
        warm[action.tick].append(action)
    while engine.state.now < domain.horizon:
        state, used = engine.observe(), set()
        for action in warm[state.now]:
            if action.tray_id in used:
                continue
            proposal = action.proposal(engine.observe())
            budget.spend("warm_validations")
            if engine.intervene(proposal).accepted:
                schedule.append(action)
                used.add(action.tray_id)
        # Same module/FIFO source protection as the exact search; reactive empty
        # targets only visible demand, plus obligations, with no predictive pool.
        for tray_id in sorted(state.trays):
            state = engine.observe()
            tray = state.trays[tray_id]
            if tray_id in used or tray_id in state.plans:
                continue
            if tray.mode == "loaded":
                destinations = (state.bags[tray.bag_id].destination,)
            elif tray.mode == "empty":
                destinations = ((state.empty_targets[tray_id],) if tray_id in state.empty_targets else
                                tuple(dict.fromkeys(b.origin for b in state.bags.values()
                                      if b.bag_id not in state.completed and b.bag_id not in state.load_times)))
            else:
                continue
            for destination in destinations:
                proposal = next(_routes(state, tray_id, destination, domain, budget), None)
                if proposal is not None and engine.intervene(proposal).accepted:
                    schedule.append(TimedJointAction.from_candidate(state.now, proposal))
                    used.add(tray_id)
                    break
        budget.spend("seed_tick")
        engine.advance(state.now + 1)
    return engine.result(), tuple(schedule)


def solve_joint(initial: Snapshot, future_bags=(), *, domain: JointDomain, warm_start=()) -> JointSearchResult:
    """Offline finite-domain solver; future_bags is an explicitly declared tape.

    For an online solve this must be a synthetic tape made only from published
    forecasts. This function never reads engine private arrivals/checkpoints.
    """
    if domain.horizon < initial.now:
        raise ValueError("Joint horizon precedes observation")
    future_bags = tuple(future_bags)
    from .storage_contracts import reject_unsupported_storage
    reject_unsupported_storage(initial, future_bags, 'joint_reference')
    budget = _Budget(domain)
    best, best_schedule, pruned, dead_ends = None, (), 0, 0
    complete = False

    def consider(result, schedule):
        nonlocal best, best_schedule
        if best is None or result.total_cost < best.total_cost - 1e-12:
            best, best_schedule = result, tuple(schedule)

    def visit(engine, schedule, used):
        nonlocal pruned, dead_ends
        budget.spend("joint_states")
        state = engine.observe()
        if state.now == domain.horizon:
            budget.counts["terminal_rollouts"] += 1
            consider(engine.result(), schedule)
            return
        if best is not None and _paid_lower_bound(engine.result()) >= best.total_cost - 1e-12:
            pruned += 1
            return
        priorities = [bag.origin for bag in future_bags if bag.arrival >= state.now]
        for proposal in _actions(state, used, domain, budget, priorities):
            branch = engine.fork()
            if branch.intervene(proposal).accepted:
                budget.counts["joint_action_branches"] += 1
                visit(branch, schedule + (TimedJointAction.from_candidate(state.now, proposal),), used | {proposal.tray_id})
        # Ending this tick without further commitments is itself a legal choice
        # only when the unchanged physical kernel can advance (no illegal wait).
        branch = engine.fork()
        try:
            branch.advance(state.now + 1)
        except AssertionError as error:
            if "non-waitable" not in str(error):
                raise
            dead_ends += 1
        else:
            visit(branch, schedule, frozenset())

    try:
        # The no-action episode is cheap and gives a usable incumbent even if
        # route enumeration exhausts its budget before the first legal route.
        idle = Simulation(initial, future_bags, control_mode="external", route_mode="whole_route")
        try:
            for tick in range(initial.now, domain.horizon):
                budget.spend("idle_seed_tick")
                idle.advance(tick + 1)
            consider(idle.result(), ())
        except AssertionError as error:
            if "non-waitable" not in str(error):
                raise
        for seed in (tuple(warm_start),):
            try:
                result, schedule = _seed_episode(initial, future_bags, domain, budget, seed)
                consider(result, schedule)
            except AssertionError as error:
                if "non-waitable" not in str(error):
                    raise
        visit(Simulation(initial, future_bags, control_mode="external", route_mode="whole_route"), (), frozenset())
        complete = True
    except _StopSearch:
        pass
    first, reconstruction = [], Simulation(initial, future_bags, control_mode="external", route_mode="whole_route")
    for action in best_schedule:
        if action.tick != initial.now:
            break
        proposal = action.proposal(reconstruction.observe())
        accepted = reconstruction.intervene(proposal)
        if not accepted.accepted:
            raise AssertionError("incumbent reconstruction failed: " + accepted.reason)
        first.append(proposal)
    diagnostics = {
        "domain": asdict(domain), "route_mode": "whole_route", "control_mode": "external",
        "domain_description": "all positive-time walks and integer departures ending by horizon+tail; at most one commitment per tray per tick; all tray orders; future physical reuse; no cancellation",
        "source_protection": "mandatory FIFO loading plus fixed_module.export_min_stock; no additional greedy donor-prefix restriction",
        "protected_semantics": "validator enforces deadlines on accepted routes; unadmitted protected backlog remains in objective/ledger",
        "future_input": "explicit caller tape; offline truth or published-forecast proxy must be identified by caller",
        "input_sha256": _digest(asdict(initial)), "declared_future_sha256": _digest([asdict(b) for b in future_bags]),
        "work_used": budget.used, "work_counts": dict(budget.counts), "elapsed_ms": (perf_counter() - budget.started) * 1000,
        "admissibly_pruned_states": pruned, "illegal_no_wait_tick_branches": dead_ends,
        "bound_rule": "accrued waiting + empty travel + nonprotected tardiness; nonnegative terminal penalties excluded",
        "best_is_executable": best is not None, "incumbent_completed": dict(best.completed) if best else {},
        "incumbent_uncompleted": list(best.uncompleted_bag_ids) if best else [],
        "deadline_is_cooperative": True, "gap_unknown_if_incomplete": not complete,
    }
    status = ("finite_domain_optimal" if best is not None else "finite_domain_infeasible") if complete else budget.reason
    return JointSearchResult(status, complete, best.total_cost if best else None,
                             best.total_cost if complete and best else None, 0. if complete and best else None,
                             tuple(first), best_schedule, dict(best.cost_components) if best else None, diagnostics)


def reactive_reference(initial, future_bags=(), *, domain):
    """Same permissions/kernel, fixed reactive earliest-route incumbent policy."""
    from .storage_contracts import reject_unsupported_storage
    future_bags = tuple(future_bags)
    reject_unsupported_storage(initial, future_bags, 'joint_reactive_reference')
    budget = _Budget(domain)
    result, schedule = _seed_episode(initial, future_bags, domain, budget)
    return result, schedule


class JointMPC:
    """Observation-only receding-horizon controller; no truth-engine argument."""
    def __init__(self, planning_horizon=12, route_tail_ticks=None, expansion_limit=5000,
                 deadline_ms=None, max_forecast_age=60):
        if type(planning_horizon) is not int or planning_horizon < 1:
            raise ValueError("planning_horizon must be a positive integer")
        if route_tail_ticks is not None and (type(route_tail_ticks) is not int or route_tail_ticks < 0):
            raise ValueError("route_tail_ticks must be nonnegative or None")
        if type(max_forecast_age) is not int or max_forecast_age < 0:
            raise ValueError("max_forecast_age must be nonnegative")
        JointDomain(planning_horizon, route_tail_ticks or 0, expansion_limit, deadline_ms)
        self.planning_horizon, self.route_tail_ticks = planning_horizon, route_tail_ticks
        self.expansion_limit, self.deadline_ms, self.max_forecast_age = expansion_limit, deadline_ms, max_forecast_age
        self._warm, self.history = (), []

    def plan(self, observation: Snapshot, published_forecasts=()) -> JointSearchResult:
        from .storage_contracts import reject_unsupported_storage
        reject_unsupported_storage(observation, (), 'joint_mpc')
        published = tuple(published_forecasts)
        active = active_forecasts(observation, published, max_forecast_age=self.max_forecast_age)
        horizon = observation.now + self.planning_horizon
        proxy, identities = [], set(observation.bags)
        for forecast in sorted(active, key=lambda f: (f.at, f.forecast_id)):
            if forecast.at > horizon:
                continue
            for identity in forecast.unit_ids:
                if identity in identities:
                    raise ValueError("Conflicting forecast unit identity across active bins")
                identities.add(identity)
                proxy.append(Bag(identity, forecast.node, forecast.destination, forecast.at, forecast.deadline))
        tail = self.route_tail_ticks
        if tail is None:
            tail = max((edge.travel_time for edge in observation.network.edges.values()), default=0)
        domain = JointDomain(horizon, tail, self.expansion_limit, self.deadline_ms)
        result = solve_joint(observation, proxy, domain=domain,
                             warm_start=tuple(action for action in self._warm if action.tick >= observation.now))
        self._warm = result.schedule
        record = {"observed_tick": observation.now, "published_forecasts": [asdict(f) for f in published],
                  "proxy_bags": [asdict(bag) for bag in proxy], "information_sha256": _digest(
                      {"observation": asdict(observation), "published": [asdict(f) for f in published]}),
                  "input_kind": "published_forecast_proxy_only", "solver_status": result.status,
                  "proxy_optimality_only": result.complete, "actual_world_optimality_claim": False,
                  "first_action_count": len(result.first_actions), "work_used": result.diagnostics["work_used"]}
        self.history.append(record)
        return result
