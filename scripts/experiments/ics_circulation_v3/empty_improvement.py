"""One-step empty-transfer improvement under a public point forecast.

The mandatory incumbent is the existing greedy controller's entire legal
sequence.  Alternative empty sequences keep its donor-prefix protections and
the unchanged owner validator.  Every scored action resumes *after* the current
slow stage, then uses timed routing and the old greedy controller.  Repeating
this improvement online is not a recursively matched MPC value or a guarantee
under the unknown actual future.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

from .joint_feedback import published_proxy
from .phase4_control import ControlSpec, PeriodicSlowController, build_engine
from .prebalance import PredictivePrebalancer, PrebalancePlan, known_supply
from .prebalance_reference import BoundedForecastPrebalancer, _action_key
from .role_coverage import ControlCursor, CursorSimulation, VisibleDecisionContext, digest
from .routing_cache_contract import CACHE_CONTRACT, enable_replay_cache
from .runtime import ExecutionValidator


@dataclass(frozen=True)
class EmptyImprovementSettings:
    score_horizon: int = 40
    max_rollouts: int = 24
    max_transfer_depth: int = 2
    paths_per_request: int = 2
    max_pool_per_state: int = 8
    max_search_calls: int = 32
    branch_search_calls: int = 256
    branch_search_work: int = 300000

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in asdict(self).values()):
            raise ValueError("empty improvement limits must be positive integers")
        if self.max_rollouts < 2:
            raise ValueError("greedy and no-transfer require at least two rollouts")


class ProxyBudgetExceeded(RuntimeError):
    pass


class _SearchLedger:
    def __init__(self, settings):
        self.settings, self.rows, self.work = settings, [], 0

    def check(self):
        if len(self.rows) >= self.settings.branch_search_calls:
            raise ProxyBudgetExceeded("proxy_search_calls")
        if self.work >= self.settings.branch_search_work:
            raise ProxyBudgetExceeded("proxy_search_work_between_queries")


class _CountedGenerator:
    def __init__(self, generator, ledger):
        self.generator, self.ledger = generator, ledger

    @property
    def last_expansions(self):
        return self.generator.last_expansions

    @property
    def last_search_status(self):
        return self.generator.last_search_status

    def _call(self, method, snapshot, *args, **kwargs):
        self.ledger.check()
        try:
            return getattr(self.generator, method)(snapshot, *args, **kwargs)
        finally:
            work = self.generator.last_expansions
            self.ledger.work += work
            self.ledger.rows.append({"time": snapshot.now, "method": method,
                "work": work, "status": self.generator.last_search_status})

    def generate(self, snapshot, bag_id, tray_id, k=4):
        return self._call("generate", snapshot, bag_id, tray_id, k=k)

    def generate_empty(self, snapshot, tray_id, destination, k=1):
        return self._call("generate_empty", snapshot, tray_id, destination, k=k)


class _CountedFactory:
    def __init__(self, inner_factory, ledger):
        self.inner_factory, self.ledger = inner_factory, ledger

    def __call__(self, horizon=None):
        return _CountedGenerator(self.inner_factory(horizon), self.ledger)


def _bind_counts(engine, settings):
    ledger = _SearchLedger(settings)
    engine._generator = _CountedGenerator(engine._generator, ledger)
    engine.generator_factory = _CountedFactory(engine.generator_factory, ledger)
    if engine.slow_controller is not None:
        old = engine.slow_controller.controller.generator_factory
        engine.slow_controller.controller.generator_factory = _CountedFactory(old, ledger)
    return ledger


def slow_after_context(spec, next_slow_trigger_at):
    stage = 4 if spec.coordination_order == "route_then_prebalance" else 2
    return VisibleDecisionContext(ControlCursor(stage_index=stage), next_slow_trigger_at, CACHE_CONTRACT)


class OneStepEmptyPrebalancer(PredictivePrebalancer):
    """Change only the current legal empty assignment, never loaded routing."""
    def __init__(self, forecasts=(), *, spec=None, settings=EmptyImprovementSettings(), generator_factory=None):
        self.spec = spec or ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
        if self.spec.routing != "timed" or not self.spec.predictive:
            raise ValueError("one-step empty improvement requires timed predictive continuation")
        super().__init__(forecasts, planning_horizon=self.spec.planning_horizon,
                         planning_budget_ms=None, generator_factory=generator_factory)
        self.settings = settings
        self.slow_context = None

    def set_slow_context(self, snapshot_time, next_slow_trigger_at):
        if type(snapshot_time) is not int or type(next_slow_trigger_at) is not int or next_slow_trigger_at <= snapshot_time:
            raise ValueError("slow context must name the next future trigger")
        self.slow_context = (snapshot_time, next_slow_trigger_at)

    def _candidate_pool(self, state, demand, diagnostics):
        # Reuse the established first-known-supply gap definition and guard;
        # enumerate request rows before any route/output truncation.
        helper = BoundedForecastPrebalancer(planning_horizon=self.planning_horizon,
            generator_factory=self.generator_factory, max_demand_units=self.max_demand_units)
        gaps, truncated = helper._gaps(state, demand)
        diagnostics["demand_units_truncated"] |= truncated
        supplies = known_supply(state)
        requests = defaultdict(list)
        for event, promised in gaps:
            for tray_id, tray in sorted(state.trays.items()):
                if (tray.mode != "empty" or tray.node is None or tray.bag_id is not None
                        or tray.available_at > state.now or tray_id in state.plans
                        or tray_id in state.empty_targets
                        or any(f.tray_id == tray_id for f in state.old_in_transit)):
                    continue
                if state.network.nodes[tray.node].logistics_zone == state.network.nodes[event.node].logistics_zone:
                    continue
                reason = self._donor_protection(state, tray_id, supplies, demand)
                if reason:
                    diagnostics["donor_rejections"].append({"tray_id": tray_id, "node": event.node, "reason": reason})
                    continue
                requests[tray_id].append((event, promised))
        donors = sorted(requests)
        if donors:
            rotation = (state.now // self.spec.slow_period) % len(donors)
            donors = donors[rotation:] + donors[:rotation]
        # One request per donor per round; deterministic rotation is independent
        # of scores/truth and avoids a permanently favored tray-name prefix.
        ordered = [(tray_id, *requests[tray_id][i])
                   for i in range(max((len(v) for v in requests.values()), default=0))
                   for tray_id in donors if i < len(requests[tray_id])]
        batches = []
        for request_index, (tray_id, event, promised) in enumerate(ordered):
            if diagnostics["proposal_search_calls"] >= self.settings.max_search_calls:
                diagnostics["proposal_unsearched_requests"] += len(ordered) - request_index
                break
            generator = self.generator_factory()
            diagnostics["proposal_search_calls"] += 1
            options = generator.generate_empty(state, tray_id, event.node, k=self.settings.paths_per_request)
            diagnostics["proposal_search_work"] += generator.last_expansions
            diagnostics["proposal_queries"].append({"time": state.now, "tray_id": tray_id,
                "destination": event.node, "need_at": event.at, "work": generator.last_expansions,
                "status": generator.last_search_status, "raw_candidates": len(options)})
            variants = []
            # Interleave path and departure variants after all request batches
            # have been constructed, rather than filling the pool with donor 0.
            for candidate in options:
                if candidate.tray_id != tray_id or candidate.bag_id is not None or candidate.destination_node != event.node:
                    diagnostics["candidate_rejections"].append("candidate_identity_or_destination_mismatch")
                    continue
                if promised is not None and candidate.usable_at >= promised:
                    continue
                variants.append(candidate)
                shift = event.at - candidate.usable_at
                if shift > 0:
                    variants.append(replace(candidate,
                        legs=tuple(replace(leg, depart=leg.depart + shift, arrive=leg.arrive + shift) for leg in candidate.legs),
                        unload_complete=candidate.unload_complete + shift, usable_at=candidate.usable_at + shift))
            batches.append(variants)
        pool, seen = [], set()
        for index in range(max((len(batch) for batch in batches), default=0)):
            for batch in batches:
                if index >= len(batch):
                    continue
                variant = batch[index]
                key = _action_key((variant,))
                if key in seen:
                    continue
                seen.add(key)
                diagnostics["proposal_validations"] += 1
                verdict = self.validator.validate(state, variant)
                if not verdict.accepted:
                    diagnostics["candidate_rejections"].append(verdict.reason)
                    continue
                if len(pool) == self.settings.max_pool_per_state:
                    diagnostics["proposal_pool_discarded_valid"] += 1
                else:
                    pool.append(variant)
        return tuple(pool)

    def _project(self, state, forecasts, proxy, next_slow):
        return CursorSimulation.from_visible(state, slow_after_context(self.spec, next_slow),
            proxy, self.spec, forecasts)

    def _prefer_complete(self, cost, sequence, ordinal, best_cost, best_sequence, best_ordinal):
        """Default behavior: keep the incumbent on proxy ties within tolerance."""
        return cost < best_cost - 1e-9

    def _score(self, snapshot, sequence, forecasts, proxy, next_slow):
        start, cpu = perf_counter(), process_time()
        row = {"status": "started", "proposals": [asdict(p) for p in sequence], "proxy_cost": None,
               "search_calls": 0, "search_work": 0, "ticks": 0}
        ledger = engine = None
        try:
            state = snapshot.clone()
            for proposal in sequence:
                verdict = self.validator.commit(state, proposal)
                if not verdict.accepted:
                    raise ValueError("alternative_sequence_rejected:" + verdict.reason)
            engine = self._project(state, forecasts, proxy, next_slow)
            ledger = _bind_counts(engine, self.settings)
            end = snapshot.now + self.settings.score_horizon
            while engine.state.now < end:
                engine.advance(engine.state.now + 1)
                row["ticks"] += 1
            result = engine.result()
            row.update(status="complete", proxy_cost=result.total_cost, cost_components=result.cost_components,
                completed=len(result.completed), unfinished_ids=list(result.uncompleted_bag_ids),
                slow_trigger_times=engine.slow_controller.trigger_times if engine.slow_controller else [],
                invariant_checks=result.invariant_checks)
        except ProxyBudgetExceeded as error:
            row.update(status="budget_exhausted", reason=str(error))
        except (ValueError, AssertionError) as error:
            row.update(status="projection_failure", reason=str(error), failure_type=type(error).__name__)
        finally:
            if ledger is not None:
                row.update(search_calls=len(ledger.rows), search_work=ledger.work, searches=ledger.rows)
            if engine is not None:
                row["stopped_at"] = engine.state.now
            row.update(wall_seconds=perf_counter() - start, cpu_seconds=process_time() - cpu)
        return row

    def plan(self, snapshot, forecasts):
        start, cpu = perf_counter(), process_time()
        if self.slow_context is None or self.slow_context[0] != snapshot.now:
            raise ValueError("one-step planning requires this actual slow trigger's public context")
        _, next_slow = self.slow_context
        self.slow_context = None
        forecasts = tuple(forecasts)
        if any(f.published_at > snapshot.now for f in forecasts):
            raise ValueError("unpublished forecasts cannot enter one-step planning")
        # Use the original plan without a weaker depth/output limit.
        greedy = super().plan(snapshot, forecasts)
        diagnostics = {"method": "one_step_empty_public_forecast_improvement",
            "snapshot_time": snapshot.now, "snapshot_version": snapshot.version,
            "snapshot_sha256": digest(asdict(snapshot)), "settings": asdict(self.settings),
            "published_forecasts": [asdict(f) for f in forecasts], "next_slow_trigger_at": next_slow,
            "continuation": "timed_routing_and_original_greedy_at_future_slow_triggers",
            "cursor": asdict(slow_after_context(self.spec, next_slow).cursor),
            "permissions": "unchanged_empty_only_sequential_owner_and_original_donor_prefix_guard",
            "budget_contract": "per_proxy_limits_between_queries; one unchanged route-query may overshoot work cap; no wall deadline",
            "claim": "best_complete_scored_action_under_one_public_proxy_not_recursive_or_actual_future_guarantee",
            "greedy_diagnostics": greedy.diagnostics, "scored_actions": [],
            "proposal_search_calls": 0, "proposal_search_work": 0, "proposal_queries": [],
            "proposal_validations": 0, "proposal_unsearched_requests": 0, "proposal_pool_discarded_valid": 0,
            "donor_rejections": [], "candidate_rejections": [], "demand_units_truncated": False}
        demand = self._demand(snapshot, forecasts, {"accepted_forecasts": [], "ignored_forecasts": []})
        unadmitted = [tray.bag_id for tray in snapshot.trays.values()
            if tray.mode == "loaded" and tray.tray_id not in snapshot.plans
            and tray.bag_id is not None and snapshot.bags[tray.bag_id].protected]
        diagnostics["unadmitted_protected_bags"] = unadmitted
        diagnostics["enhancement_domain_guard"] = (
            "only_original_greedy_and_no_transfer_due_to_unadmitted_protected_load"
            if unadmitted else "extra_empty_sequences_allowed")
        if not demand and not greedy.proposals:
            # No demand events means _gaps has no requests at any search node.
            # All available actions in THIS declared method are the identical
            # empty sequence; this says nothing about unknown future demand.
            diagnostics.update(status="identical_no_demand_action", selected_action_index=0,
                selected_proxy_cost=None, fallback_to_greedy=False, rollout_calls=0,
                mandatory_identical_actions_not_simulated=2, enumerated_actions=2,
                unscored_enumerated_actions=0, unexplored_sequence_nodes=0,
                proposal_count=0, actual_sequence_changed=False,
                omitted_projection_reason="demand_empty_implies_gap_requests_empty_and_only_empty_sequence",
                elapsed_ms=(perf_counter() - start) * 1000, cpu_seconds=process_time() - cpu)
            return PrebalancePlan((), diagnostics)
        proxy = published_proxy(snapshot, forecasts, snapshot.now + self.settings.score_horizon)
        diagnostics.update(proxy_bags=[asdict(b) for b in proxy], proxy_sha256=digest([asdict(b) for b in proxy]))
        actions = [(greedy.proposals, "greedy_incumbent"), ((), "no_transfer")]
        seen = {_action_key(greedy.proposals), ()}
        queued = {()}
        # The older bounded reference suppresses new transfers when a protected
        # load has no admitted route. Do not expand its enhancement domain in
        # that case; the original greedy incumbent remains explicitly retained
        # because PredictivePrebalancer itself has no such extra heuristic.
        queue = deque([] if unadmitted else [(snapshot.clone(), ())])
        # Construct and score mandatory alternatives first. Equal actions are
        # intentionally scored separately so their identical budget is visible.
        best, best_cost, selected = greedy.proposals, None, 0
        index = 0
        while index < self.settings.max_rollouts:
            if index >= len(actions):
                while queue and index >= len(actions):
                    state, sequence = queue.popleft()
                    if len(sequence) >= self.settings.max_transfer_depth:
                        continue
                    for proposal in self._candidate_pool(state, demand, diagnostics):
                        combined = sequence + (proposal,)
                        key = _action_key(combined)
                        if key in queued:
                            continue
                        child = state.clone()
                        verdict = self.validator.commit(child, proposal)
                        if not verdict.accepted:
                            diagnostics["candidate_rejections"].append(verdict.reason)
                            continue
                        queued.add(key)
                        queue.append((child, combined))
                        if key not in seen:
                            seen.add(key)
                            actions.append((combined, "bounded_empty_sequence"))
                if index >= len(actions):
                    break
            sequence, kind = actions[index]
            row = self._score(snapshot, sequence, forecasts, proxy, next_slow)
            row.update(ordinal=index, kind=kind)
            diagnostics["scored_actions"].append(row)
            if index == 0 and row["status"] != "complete":
                # Still run mandatory no-transfer for honest budget accounting,
                # but a partial incumbent cannot support improvement selection.
                best_cost = None
            elif row["status"] == "complete" and (index == 0 or (
                    diagnostics["scored_actions"][0]["status"] == "complete"
                    and self._prefer_complete(row["proxy_cost"], sequence, index, best_cost, best, selected))):
                best, best_cost, selected = sequence, row["proxy_cost"], index
            index += 1
        fallback = diagnostics["scored_actions"][0]["status"] != "complete"
        if fallback:
            best, best_cost, selected = greedy.proposals, None, 0
        diagnostics.update(selected_action_index=selected, selected_proxy_cost=best_cost,
            fallback_to_greedy=fallback, rollout_calls=len(diagnostics["scored_actions"]),
            enumerated_actions=len(actions), unscored_enumerated_actions=len(actions) - index,
            unexplored_sequence_nodes=len(queue), proposal_count=len(best),
            actual_sequence_changed=_action_key(best) != _action_key(greedy.proposals),
            status="fallback_incumbent_projection_incomplete" if fallback else "best_complete_scored_action",
            elapsed_ms=(perf_counter() - start) * 1000, cpu_seconds=process_time() - cpu)
        return PrebalancePlan(best, diagnostics)


class ImprovementPeriodicSlowController(PeriodicSlowController):
    def __call__(self, snapshot):
        if snapshot.now >= self.next_trigger_at:
            next_trigger = self.next_trigger_at + ((snapshot.now - self.next_trigger_at) // self.period + 1) * self.period
            self.controller.set_slow_context(snapshot.now, next_trigger)
        return super().__call__(snapshot)


def build_empty_improvement_engine(scene, spec=None, *, settings=EmptyImprovementSettings(), enabled=True):
    """Actual tasks go only to build_engine; the new controller sees no tape."""
    spec = spec or ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
    if spec.routing != "timed" or not spec.predictive:
        raise ValueError("builder requires timed routing and predictive slow control")
    engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    enable_replay_cache(engine)
    if not enabled:
        return engine
    old = engine.slow_controller
    controller = OneStepEmptyPrebalancer(spec=spec, settings=settings,
                                        generator_factory=old.controller.generator_factory)
    contract = engine.control_contract
    contract["continuation"]["prebalancer"] = "OneStepEmptyPrebalancer"
    contract["continuation"]["empty_improvement_settings"] = asdict(settings)
    contract["continuation"].setdefault("implementation_sha256", {}).update({
        name: sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
        for name in ("empty_improvement.py", "prebalance_reference.py", "joint_feedback.py", "role_coverage.py")})
    contract["continuation_sha256"] = digest(contract["continuation"])
    contract.pop("contract_sha256", None)
    contract["contract_sha256"] = digest(contract)
    engine.slow_controller = ImprovementPeriodicSlowController(controller, period=old.period,
        first_trigger_at=old.next_trigger_at, contract=contract, forecast_publications=scene.forecasts)
    engine.route_selector.contract = contract
    return engine
