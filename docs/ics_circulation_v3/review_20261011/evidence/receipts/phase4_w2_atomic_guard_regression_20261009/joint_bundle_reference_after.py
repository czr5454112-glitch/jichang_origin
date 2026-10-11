"""Finite integer control domain expanded with atomic new-route bundles.

All nonempty eligible tray subsets and all member integer-route products are
enumerated under one budget. Relaxed member views are proposal construction
only. The unchanged physical snapshot is authorized exclusively by the atomic
owner transaction. No accepted itinerary or entered edge can be cancelled.
"""
from dataclasses import asdict, dataclass
from itertools import combinations
from time import perf_counter

from .joint_reference import (JointDomain, JointMPC, TimedJointAction, _Budget, _StopSearch,
                              _digest, _paid_lower_bound, _routes)
from .joint_transactions import validate_joint, commit_joint_actions
from .learning import active_forecasts
from .model import Bag
from .prebalance import PredictivePrebalancer, known_supply
from .runtime import Simulation


@dataclass(frozen=True)
class AtomicJointDomain(JointDomain):
    atomic_bundles: bool = True
    source_protection_contract: str = "module_only"
    guard_max_forecast_age: int = 60

    def __post_init__(self):
        super().__post_init__()
        if type(self.atomic_bundles) is not bool:
            raise ValueError("atomic_bundles must be a bool")
        if self.source_protection_contract not in {"module_only", "shared_forecast_prefix"}:
            raise ValueError("Unknown source_protection_contract")
        if type(self.guard_max_forecast_age) is not int or self.guard_max_forecast_age < 0:
            raise ValueError("guard_max_forecast_age must be nonnegative integer")


@dataclass(frozen=True)
class TimedJointBundle:
    tick: int
    actions: tuple[TimedJointAction, ...]

    def proposals(self, snapshot):
        return tuple(action.proposal(snapshot) for action in self.actions)


@dataclass(frozen=True)
class AtomicJointSearchResult:
    status: str
    complete: bool
    total_cost: float | None
    lower_bound: float | None
    gap: float | None
    first_bundles: tuple[tuple, ...]
    schedule: tuple[TimedJointBundle, ...]
    cost_components: dict | None
    diagnostics: dict

    @property
    def first_actions(self):
        if any(len(bundle) > 1 for bundle in self.first_bundles):
            raise ValueError("Atomic bundle must not be flattened into sequential interventions")
        return tuple(bundle[0] for bundle in self.first_bundles)


def _member_routes(state, group, tray_id, domain, budget, priorities):
    relaxed = state.clone()
    peers = set(group) - {tray_id}
    # Peers are eligible stationary, uncommitted entities. They remain in the
    # actual owner state and will be provisionally reserved by validate_joint.
    # Removing them here avoids wrongly demanding an executable single route
    # before a capacity-releasing simultaneous bundle has even been assembled.
    relaxed.trays = {key: tray for key, tray in relaxed.trays.items() if key not in peers}
    relaxed.reservations = tuple(slot for slot in relaxed.reservations if slot.tray_id not in peers)
    tray = relaxed.trays[tray_id]
    if tray.bag_id is not None:
        destinations = (state.bags[tray.bag_id].destination,)
    elif tray_id in state.empty_targets:
        destinations = (state.empty_targets[tray_id],)
    else:
        destinations = sorted((node for node, item in state.network.nodes.items() if item.can_wait),
                              key=lambda node: (node not in priorities, priorities.index(node) if node in priorities else 0, node))
    for destination in destinations:
        yield from _routes(relaxed, tray_id, destination, domain, budget)


def source_protection_failure(state, proposals, domain, published_forecasts=()):
    """Optional first-known-supply guard, separate from owner permissions.

    Single exports use the exact greedy donor-prefix predicate. For a bundle,
    all other simultaneous exporters are removed from the supply set before
    checking each donor. New incoming routes and possible reuse are not credited.
    This conservative atomic extension is explicit, not the default exact domain.
    """
    if domain.source_protection_contract == "module_only":
        return None
    # A pending accepted destination is a continuation obligation, not a new
    # export. Loaded routes are also outside this optional empty-donor policy.
    new_empty = tuple(p for p in proposals if p.bag_id is None and p.tray_id not in state.empty_targets)
    if any(p.tray_id not in state.trays or state.trays[p.tray_id].node is None
           or p.destination_node not in state.network.nodes for p in new_empty):
        return "source_guard_requires_stationary_known_member"
    exported = {p.tray_id for p in new_empty if state.network.nodes[state.trays[p.tray_id].node].logistics_zone
                != state.network.nodes[p.destination_node].logistics_zone}
    if not exported:
        return None
    guard = PredictivePrebalancer(planning_horizon=max(1, domain.horizon - state.now),
                                 max_forecast_age=domain.guard_max_forecast_age)
    demand = guard._demand(state, published_forecasts, {"accepted_forecasts": [], "ignored_forecasts": []})
    supplies = known_supply(state)
    for tray_id in sorted(exported):
        remaining = tuple(s for s in supplies if s.tray_id == tray_id or s.tray_id not in exported)
        reason = guard._donor_protection(state, tray_id, remaining, demand)
        if reason:
            return reason
    return None


def _bundles(state, used, domain, budget, future_priorities, published_forecasts):
    old = {flight.tray_id for flight in state.old_in_transit}
    eligible = sorted(tray.tray_id for tray in state.trays.values()
                      if tray.tray_id not in used and tray.tray_id not in state.plans and tray.tray_id not in old
                      and tray.node is not None and tray.mode in {"loaded", "empty"} and tray.available_at <= state.now)
    visible = [bag.origin for bag in state.bags.values() if bag.bag_id not in state.completed and bag.bag_id not in state.load_times]
    priorities = tuple(dict.fromkeys(visible + list(future_priorities)))
    sizes = range(len(eligible), 0, -1) if domain.atomic_bundles else (1,)
    for size in sizes:
        for group in combinations(eligible, size):
            budget.spend("participant_subsets")

            def product(index, partial):
                if index == len(group):
                    budget.spend("joint_bundle_validations")
                    if (source_protection_failure(state, partial, domain, published_forecasts) is None
                            and validate_joint(state, partial).accepted):
                        yield partial
                    return
                for proposal in _member_routes(state, group, group[index], domain, budget, priorities):
                    yield from product(index + 1, partial + (proposal,))

            yield from product(0, ())


def _complete_reactively(engine, domain, budget, initial_used=frozenset(), published_forecasts=()):
    """Feasible continuation from an exact engine phase, not a snapshot restart.

    This preserves cost, event phase and already used trays at the current
    tick, including zero-duration unloads. It reads observations only; the
    authorized engine carries its declared truth/proxy event tape internally.
    """
    branch, suffix, first_tick = engine.fork(), [], True
    while branch.state.now < domain.horizon:
        state = branch.observe()
        used = set(initial_used) if first_tick else set()
        first_tick = False
        for tray_id in sorted(state.trays):
            state = branch.observe()
            tray = state.trays[tray_id]
            if tray_id in used or tray_id in state.plans:
                continue
            if tray.mode == "loaded":
                destinations = (state.bags[tray.bag_id].destination,)
            elif tray.mode == "empty":
                destinations = ((state.empty_targets[tray_id],) if tray_id in state.empty_targets else tuple(dict.fromkeys(
                    b.origin for b in state.bags.values() if b.bag_id not in state.completed and b.bag_id not in state.load_times)))
            else:
                continue
            for destination in destinations:
                proposal = next(_routes(state, tray_id, destination, domain, budget), None)
                if proposal is not None:
                    budget.spend("completion_seed_commit")
                    if (source_protection_failure(state, (proposal,), domain, published_forecasts) is None
                            and commit_joint_actions(branch, (proposal,)).accepted):
                        suffix.append(TimedJointBundle(state.now, (TimedJointAction.from_candidate(state.now, proposal),)))
                        used.add(tray_id)
                        break
        budget.spend("completion_seed_tick")
        branch.advance(state.now + 1)
    return branch.result(), tuple(suffix)


def solve_atomic_joint(initial, future_bags=(), *, domain: AtomicJointDomain, warm_start=(), published_forecasts=()):
    if domain.horizon < initial.now:
        raise ValueError("Joint horizon precedes observation")
    future_bags = tuple(future_bags)
    published_forecasts = tuple(published_forecasts)
    # A truth tape is not silently promoted to public source-protection demand.
    active_forecasts(initial, published_forecasts, max_forecast_age=domain.guard_max_forecast_age)
    budget, best, best_schedule = _Budget(domain), None, ()
    complete, pruned, dead = False, 0, 0

    def consider(result, schedule):
        nonlocal best, best_schedule
        if best is None or result.total_cost < best.total_cost - 1e-12:
            best, best_schedule = result, tuple(schedule)

    def visit(engine, schedule, used):
        nonlocal pruned, dead
        budget.spend("joint_states")
        state = engine.observe()
        if state.now == domain.horizon:
            budget.counts["terminal_rollouts"] += 1
            consider(engine.result(), schedule)
            return
        if state.now == initial.now and schedule:
            # Assess a feasible completion before spending the entire budget
            # on deeper voluntary empty movements. This affects search order
            # and incumbents, never the exhaustive domain or its certificate.
            budget.spend("root_completion_probes")
            try:
                result, suffix = _complete_reactively(engine, domain, budget, used, published_forecasts)
                consider(result, schedule + suffix)
            except AssertionError as error:
                if "non-waitable" not in str(error):
                    raise
        if best is not None and _paid_lower_bound(engine.result()) >= best.total_cost - 1e-12:
            pruned += 1
            return
        priorities = [bag.origin for bag in future_bags if bag.arrival >= state.now]
        for proposals in _bundles(state, used, domain, budget, priorities, published_forecasts):
            branch = engine.fork()
            budget.spend("joint_bundle_commits")
            accepted = commit_joint_actions(branch, proposals)
            if not accepted.accepted:
                raise AssertionError("Validated bundle rejected without intervening mutation: " + accepted.reason)
            budget.counts["multi_tray_branches"] += len(proposals) > 1
            action = TimedJointBundle(state.now, tuple(TimedJointAction.from_candidate(state.now, c) for c in proposals))
            visit(branch, schedule + (action,), used | {c.tray_id for c in proposals})
        branch = engine.fork()
        try:
            branch.advance(state.now + 1)
        except AssertionError as error:
            if "non-waitable" not in str(error):
                raise
            dead += 1
        else:
            visit(branch, schedule, frozenset())

    try:
        idle = Simulation(initial, future_bags, control_mode="external", route_mode="whole_route")
        try:
            for tick in range(initial.now, domain.horizon):
                budget.spend("idle_seed_tick")
                idle.advance(tick + 1)
            consider(idle.result(), ())
        except AssertionError as error:
            if "non-waitable" not in str(error):
                raise
        # Replay warm bundles atomically; a changed observation can reject one
        # without authorizing a partial bundle or cancelling any old commitment.
        warm_engine = Simulation(initial, future_bags, control_mode="external", route_mode="whole_route")
        accepted_warm = []
        try:
            for tick in range(initial.now, domain.horizon):
                budget.spend("warm_seed_tick")
                used = set()
                for bundle in warm_start:
                    if (bundle.tick == tick and (domain.atomic_bundles or len(bundle.actions) == 1)
                            and not used.intersection(a.tray_id for a in bundle.actions)
                            and all((a.legs or a.bag_id is not None)
                                    and all(leg.arrive <= domain.route_end_tick for leg in a.legs)
                                    and (a.bag_id is not None or initial.network.nodes[a.destination].can_wait)
                                    for a in bundle.actions)):
                        budget.spend("warm_bundle_validation")
                        state = warm_engine.observe()
                        proposals = bundle.proposals(state)
                        if (source_protection_failure(state, proposals, domain, published_forecasts) is None
                                and commit_joint_actions(warm_engine, proposals).accepted):
                            accepted_warm.append(bundle)
                            used.update(a.tray_id for a in bundle.actions)
                warm_engine.advance(tick + 1)
            consider(warm_engine.result(), accepted_warm)
        except AssertionError as error:
            if "non-waitable" not in str(error):
                raise
        # A sequential reactive seed is feasible in both permission domains.
        try:
            result, seed = _complete_reactively(
                Simulation(initial, future_bags, control_mode="external", route_mode="whole_route"),
                domain, budget, published_forecasts=published_forecasts)
            consider(result, seed)
        except AssertionError as error:
            if "non-waitable" not in str(error):
                raise
        visit(Simulation(initial, future_bags, control_mode="external", route_mode="whole_route"), (), frozenset())
        complete = True
    except _StopSearch:
        pass
    reconstruction_started = perf_counter()
    first, reconstruction = [], Simulation(initial, future_bags, control_mode="external", route_mode="whole_route")
    for bundle in best_schedule:
        if bundle.tick != initial.now:
            break
        proposals = bundle.proposals(reconstruction.observe())
        if source_protection_failure(reconstruction.observe(), proposals, domain, published_forecasts):
            raise AssertionError("Incumbent violates declared source protection contract")
        accepted = commit_joint_actions(reconstruction, proposals)
        if not accepted.accepted:
            raise AssertionError("Atomic incumbent reconstruction failed: " + accepted.reason)
        first.append(proposals)
    status = ("finite_atomic_domain_optimal" if best else "finite_atomic_domain_infeasible") if complete else budget.reason
    if complete and not domain.atomic_bundles:
        status = "finite_sequential_domain_optimal" if best else "finite_sequential_domain_infeasible"
    diagnostics = {"domain": asdict(domain), "route_mode": "whole_route", "control_mode": "external",
                   "permission_domain": "atomic_new_commit_bundles" if domain.atomic_bundles else "sequential_single_commits",
                   "domain_description": "all eligible tray subsets, Cartesian products of positive-time walks/integer departures, all same-tick bundle orders, at most one commitment per tray per tick, immutable old plans",
                   "proposal_relaxation": "only other selected eligible members removed from private member view; actual owner state checked atomically",
                   "source_protection_contract": domain.source_protection_contract,
                   "source_protection": "fixed-module cumulative export floor and FIFO; optional shared_forecast_prefix adds greedy first-known-supply source zone/node prefixes, aggregate outgoing peers removed, no credit for same-bundle new inflow or uncommitted reuse",
                   "guard_published_forecasts_sha256": _digest([asdict(f) for f in published_forecasts]),
                   "bound_rule": "accrued wait, empty travel, nonprotected tardiness; no decreasing terminal penalties",
                   "anytime_strategy": "independent idle/warm/reactive incumbents plus exact-phase reactive completion of initial-tick prefixes; all search and seed work charged to shared expansion counter",
                   "budget_scope": "named work units, not primitive operations; forecast projection and final incumbent reconstruction are included in controller wall/CPU timing but outside search expansion counter; cooperative deadline cannot interrupt one validator call",
                   "incumbent_reconstruction_ms": (perf_counter() - reconstruction_started) * 1000,
                   "incumbent_reconstruction_bundle_count": len(first),
                   "input_sha256": _digest(asdict(initial)), "declared_future_sha256": _digest([asdict(b) for b in future_bags]),
                   "work_used": budget.used, "work_counts": dict(budget.counts), "admissibly_pruned_states": pruned,
                   "illegal_no_wait_tick_branches": dead, "elapsed_ms": (perf_counter() - budget.started) * 1000,
                   "gap_unknown_if_incomplete": not complete, "incumbent_completed": dict(best.completed) if best else {},
                   "incumbent_uncompleted": list(best.uncompleted_bag_ids) if best else []}
    return AtomicJointSearchResult(status, complete, best.total_cost if best else None,
        best.total_cost if complete and best else None, 0. if complete and best else None,
        tuple(first), best_schedule, dict(best.cost_components) if best else None, diagnostics)


class AtomicJointMPC(JointMPC):
    def __init__(self, *args, atomic_bundles=True, source_protection_contract="module_only", **kwargs):
        super().__init__(*args, **kwargs)
        if type(atomic_bundles) is not bool:
            raise ValueError("atomic_bundles must be a bool")
        self.atomic_bundles = atomic_bundles
        AtomicJointDomain(1, source_protection_contract=source_protection_contract)
        self.source_protection_contract = source_protection_contract

    def plan(self, observation, published_forecasts=()):
        published = tuple(published_forecasts)
        active = active_forecasts(observation, published, max_forecast_age=self.max_forecast_age)
        horizon, proxy, ids = observation.now + self.planning_horizon, [], set(observation.bags)
        for forecast in sorted(active, key=lambda f: (f.at, f.forecast_id)):
            if forecast.at > horizon:
                continue
            for identity in forecast.unit_ids:
                if identity in ids:
                    raise ValueError("Conflicting forecast unit identity across active bins")
                ids.add(identity)
                proxy.append(Bag(identity, forecast.node, forecast.destination, forecast.at, forecast.deadline))
        tail = self.route_tail_ticks
        if tail is None:
            tail = max((edge.travel_time for edge in observation.network.edges.values()), default=0)
        domain = AtomicJointDomain(horizon, tail, self.expansion_limit, self.deadline_ms, self.atomic_bundles,
                                   self.source_protection_contract, self.max_forecast_age)
        result = solve_atomic_joint(observation, proxy, domain=domain,
                                    warm_start=tuple(b for b in self._warm if b.tick >= observation.now),
                                    published_forecasts=published)
        self._warm = result.schedule
        self.history.append({"observed_tick": observation.now, "published_forecasts": [asdict(f) for f in published],
                             "proxy_bags": [asdict(b) for b in proxy], "input_kind": "published_forecast_proxy_only",
                             "information_sha256": _digest({"observation": asdict(observation), "published": [asdict(f) for f in published]}),
                             "solver_status": result.status, "proxy_optimality_only": result.complete,
                             "actual_world_optimality_claim": False, "atomic_bundles": self.atomic_bundles,
                             "source_protection_contract": self.source_protection_contract})
        return result
