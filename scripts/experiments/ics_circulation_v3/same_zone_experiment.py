"""Audited, causal deployment and checkpoint interventions for supply policies.

This experiment helper changes no routing, physical execution, publication gate,
or clock.  Offline tapes determine only event-engine arrivals and evaluation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
import random
from time import perf_counter, process_time
import traceback

from .network_full_cycle import cycle_state, forecast_expiry
from .network_role_labels import SearchBudget, SearchBudgetExceeded, bind_accounting, validate_tape
from .prebalance import known_supply
from .role_coverage import digest
from .routing_cache_contract import routing_cache_state
from .run_network_opportunities import physical_projection
from .runtime import actual_action_key, assert_invariants


POLICIES = ("old32", "old64", "same_zone32plus32")
SEEDS = {"cross_cycle": 1307, "counterflow": 1319, "near_full": 1327}
CASE_BUDGET = SearchBudget(3000, 3000000, 600.)
TAIL_CAP = 720


def saved_error_tapes(scene, count=8):
    """Outcome-blind cancellation/jitter; every protected task stays exact."""
    if scene.name not in SEEDS or type(count) is not int or count < 1:
        raise ValueError("fixed scene seed and positive tape count required")
    validate_tape(scene.future_bags, scene.initial)
    remaining = sorted(scene.future_bags, key=lambda b: b.bag_id)
    rng = random.Random(SEEDS[scene.name])
    tapes = []
    for _ in range(count):
        tasks = []
        for bag in remaining:
            if bag.protected:
                tasks.append(bag)
                continue
            if rng.randrange(8) == 0:
                continue
            arrival = max(scene.initial.now + 1, bag.arrival + rng.choice((-2, 0, 2)))
            tasks.append(replace(bag, arrival=arrival, deadline=bag.deadline + arrival - bag.arrival))
        tape = tuple(sorted(tasks, key=lambda b: (b.arrival, b.bag_id)))
        validate_tape(tape, scene.initial)
        tapes.append(tape)
    return tuple(tapes)


def install_supply_policy(engine, policy):
    """Replace only the inner controller; preserve wrapper phase and caches."""
    if policy not in POLICIES or engine.slow_controller is None:
        raise ValueError("known policy and original periodic controller required")
    old = engine.slow_controller.controller
    if policy == "old64":
        old.max_candidates = 64
    elif policy == "same_zone32plus32":
        from .same_zone_supply import SameZoneSupplyPrebalancer
        new = SameZoneSupplyPrebalancer(old.forecasts,
            planning_horizon=old.planning_horizon, max_forecast_age=old.max_forecast_age,
            max_candidates=32, max_same_zone_candidates=32, max_proposals=old.max_proposals,
            max_demand_units=old.max_demand_units, planning_budget_ms=old.planning_budget_ms,
            generator_factory=old.generator_factory, validator=old.validator)
        new.history, new.last_diagnostics = deepcopy(old.history), deepcopy(old.last_diagnostics)
        engine.slow_controller.controller = new
    return {"policy": policy, "inner_class": type(engine.slow_controller.controller).__name__,
            "next_slow_trigger_at": engine.slow_controller.next_trigger_at,
            "period": engine.slow_controller.period,
            "max_cross_zone_queries": engine.slow_controller.controller.max_candidates,
            "max_same_zone_queries": getattr(engine.slow_controller.controller, "max_same_zone_candidates", 0),
            "information": "unchanged centralized Snapshot and currently published forecast revisions only"}


def without_network(state):
    value = asdict(state)
    value.pop("network")
    return value


class SlowAuditController:
    """Transparent observation at actual calls, after the publication gate."""
    def __init__(self, inner, engine):
        self.inner, self.engine, self.calls = inner, engine, []

    @property
    def forecasts(self):
        return self.inner.forecasts

    @forecasts.setter
    def forecasts(self, value):
        self.inner.forecasts = value

    @property
    def generator_factory(self):
        return self.inner.generator_factory

    @generator_factory.setter
    def generator_factory(self, value):
        self.inner.generator_factory = value

    @property
    def max_forecast_age(self):
        return self.inner.max_forecast_age

    @property
    def last_diagnostics(self):
        return self.inner.last_diagnostics

    def __call__(self, snapshot):
        row = {"time": snapshot.now, "snapshot_before": without_network(snapshot),
               "state_sha256": digest(asdict(snapshot)),
               "published_forecasts": [asdict(f) for f in self.inner.forecasts],
               "known_supply": [asdict(s) for s in known_supply(snapshot)],
               "cursor_at_call": asdict(self.engine._cursor),
               "next_slow_trigger_at_after_clock_advance": self.engine.slow_controller.next_trigger_at,
               "status": "entered"}
        self.calls.append(row)
        try:
            proposals = self.inner(snapshot)
        except Exception as error:
            row.update(status="exception", failure={"type": type(error).__name__, "message": str(error)},
                       last_diagnostics=deepcopy(self.inner.last_diagnostics))
            raise
        row.update(status="returned", proposals=[asdict(p) for p in proposals],
                   diagnostics=deepcopy(self.inner.last_diagnostics),
                   snapshot_after=without_network(snapshot))
        return proposals


def run_observed_cycle(engine, expected_ids, *, minimum_observation_at,
                       budget=CASE_BUDGET, tail_cap=TAIL_CAP, forced_candidate=None):
    """Retain earliest milestones and original endpoint before final stopping."""
    started, cpu = perf_counter(), process_time()
    if minimum_observation_at < engine.state.now or tail_cap < 1:
        raise ValueError("valid fixed observation endpoint and positive cap required")
    expected_ids = set(expected_ids)
    cache_before, state_before = routing_cache_state(engine), asdict(engine.state)
    cursor_before = asdict(engine._cursor)
    owner = bind_accounting(engine, budget)
    audit = SlowAuditController(engine.slow_controller.controller, engine)
    engine.slow_controller.controller = audit
    expiry, period = forecast_expiry(engine), engine.slow_controller.period
    last_arrival = max((b.arrival for bags in engine._arrivals.values() for b in bags), default=engine.state.now)
    cap_at = max(minimum_observation_at, last_arrival, expiry) + tail_cap
    trace_prefix = len(engine._trace)
    selector_prefix = len(engine.route_selector.history)
    slow_prefix = len(engine.slow_controller.history)
    opportunities, physical_ticks = [], []

    def capture(current, tray, options):
        state, bag = current.state, current.state.bags[tray.bag_id]
        row = {"sequence": len(opportunities), "time": state.now, "version": state.version,
               "node": tray.node, "bag_id": bag.bag_id, "tray_id": tray.tray_id,
               "protected": bag.protected, "candidate_count": len(options),
               "candidate_keys": [actual_action_key(state, p, route_mode="next_edge") for p in options],
               "candidates": [asdict(p) for p in options], "cursor": asdict(current._cursor),
               "next_slow_trigger_at": current.slow_controller.next_trigger_at,
               "visible_state": without_network(state)}
        opportunities.append(row)

    engine._decision_callback = capture
    forced = None
    status, failure, stop = "tick_cap_censored", None, None
    milestones, endpoint = {}, None
    quiet_since = trigger_count = None
    try:
        if forced_candidate is not None:
            forced = {"time": engine.state.now, "candidate": asdict(forced_candidate),
                      "actual_action_key": actual_action_key(engine.state, forced_candidate, route_mode="next_edge"),
                      "cursor": cursor_before,
                      "next_slow_trigger_at": engine.slow_controller.next_trigger_at}
            engine.choose_pending(forced_candidate)
        while engine.state.now < cap_at:
            owner.check()
            engine.advance(engine.state.now + 1)
            now = engine.state.now
            cycle = cycle_state(engine, expected_ids, expiry)
            physical_ticks.append(physical_projection(engine.state))
            if now == minimum_observation_at:
                endpoint = {"at": now, "result": asdict(engine.result()), "cycle": cycle,
                            "search_calls": len(owner.rows), "search_work": owner.work,
                            "cache": routing_cache_state(engine)}
            for field in ("task_complete", "transport_drained"):
                if cycle[field] and field not in milestones:
                    milestones[field] = {"time": now, "cycle": cycle}
            quiet = cycle["transport_drained"] and cycle["forecast_expired"]
            if not quiet:
                quiet_since = trigger_count = None
            elif quiet_since is None:
                quiet_since, trigger_count = now, len(engine.slow_controller.trigger_times)
            elif now - quiet_since >= period and len(engine.slow_controller.trigger_times) > trigger_count:
                milestones.setdefault("controller_quiescent", {"time": now, "quiet_since": quiet_since,
                    "actual_slow_triggers_since": len(engine.slow_controller.trigger_times) - trigger_count,
                    "cycle": cycle})
                if now >= minimum_observation_at:
                    status = "controller_quiescent"
                    break
        assert_invariants(engine.state)
    except SearchBudgetExceeded as error:
        status, stop = "budget_censored", str(error)
    except Exception as error:
        status, failure = "execution_failure", {"type": type(error).__name__, "message": str(error),
                                                "traceback": traceback.format_exc()}
    result = None if failure else asdict(engine.result())
    return {"status": status, "failure": failure, "budget_stop": stop, "budget": asdict(budget),
        "initial_state": state_before, "initial_cursor": cursor_before,
        "forced_intervention": forced, "expected_task_ids": sorted(expected_ids),
        "minimum_observation_at": minimum_observation_at, "original_endpoint": endpoint,
        "last_arrival_at": last_arrival, "forecast_expired_at": expiry, "cap_at": cap_at,
        "stopped_at": engine.state.now, "milestones": milestones,
        "last_cycle_state": cycle_state(engine, expected_ids, expiry), "result": result,
        "slow_calls": audit.calls, "slow_history_suffix": engine.slow_controller.history[slow_prefix:],
        "actual_slow_trigger_times": engine.slow_controller.trigger_times,
        "opportunities": opportunities, "selector_history_suffix": engine.route_selector.history[selector_prefix:],
        "physical_tick_trace": physical_ticks, "event_trace_suffix": engine._trace[trace_prefix:],
        "searches": owner.rows, "search_calls": len(owner.rows), "search_work": owner.work,
        "cache_before": cache_before, "cache_after": routing_cache_state(engine),
        "cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - started}
