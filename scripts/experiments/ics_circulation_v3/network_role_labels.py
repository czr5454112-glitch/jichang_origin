"""Bounded, actual-decision labels on reused original-map development flows.

The route planning horizon remains the original workload contract. Evaluation
windows and offline sampled task tapes are separate experiment parameters.
No synthetic graph or fabricated decision is substituted for an empty role.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import math
import random
from time import perf_counter, process_time
import traceback

from .learning import TimedAnalyticEvaluator
from .phase4_control import ControlSpec, build_engine
from .phase4_network_workloads import shortest_paths
from .role_coverage import CursorSimulation, checkpoint_fingerprint, digest
from .role_features import physical_features
from .runtime import ExecutionValidator, actual_action_key, assert_invariants


SPEC = ControlSpec(routing="timed", predictive=True, planning_horizon=180,
                   slow_period=2, route_mode="next_edge", candidate_count=4,
                   expansion_limit=3000, static_path_limit=8)
ROLES = ("origin", "continuation", "arrival_at_destination")
BANDS = (0, 40, 80)


class SearchBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchBudget:
    calls: int = 300
    work: int = 300000
    wall_seconds: float = 300.

    def __post_init__(self):
        if any(type(x) is not int or x < 1 for x in (self.calls, self.work)):
            raise ValueError("search call/work budgets must be positive integers")
        if not math.isfinite(self.wall_seconds) or self.wall_seconds <= 0:
            raise ValueError("wall safeguard must be finite and positive")


class SearchAccounting:
    """Instrumentation only; stop between searches, never alter their budget."""
    def __init__(self, budget):
        self.budget = budget
        self.rows, self.work = [], 0
        self.started = perf_counter()

    def check(self):
        if len(self.rows) >= self.budget.calls:
            raise SearchBudgetExceeded("search_call_cap")
        if self.work >= self.budget.work:
            raise SearchBudgetExceeded("search_work_cap_between_queries")
        if perf_counter() - self.started >= self.budget.wall_seconds:
            raise SearchBudgetExceeded("wall_safeguard_between_queries_or_ticks")


class BudgetFactory:
    def __init__(self, inner_factory, owner):
        self.inner_factory, self.owner = inner_factory, owner

    def __call__(self, horizon=None):
        return BudgetGenerator(self.inner_factory(horizon), self.owner)


class BudgetGenerator:
    def __init__(self, generator, owner):
        self.generator, self.owner = generator, owner

    @property
    def last_expansions(self):
        return self.generator.last_expansions

    @property
    def last_search_status(self):
        return self.generator.last_search_status

    def generate(self, state, bag_id, tray_id, k=4):
        return self._call(state, bag_id, tray_id, None, k)

    def generate_empty(self, state, tray_id, destination, k=1):
        return self._call(state, None, tray_id, destination, k)

    def _call(self, state, bag_id, tray_id, destination, k):
        self.owner.check()
        options = (self.generator.generate(state, bag_id, tray_id, k) if bag_id is not None
                   else self.generator.generate_empty(state, tray_id, destination, k))
        work = self.generator.last_expansions
        self.owner.work += work
        self.owner.rows.append({"time": state.now, "node": state.trays[tray_id].node,
            "bag_id": bag_id, "tray_id": tray_id, "candidate_count": len(options),
            "work": work, "status": self.generator.last_search_status,
            "cache_accounting": deepcopy(getattr(self.generator, "last_diagnostics", {}).get("cache_accounting")),
            "work_units_by_stage": deepcopy(getattr(self.generator, "last_diagnostics", {}).get("work_units_by_stage"))})
        return options


def bind_accounting(engine, budget):
    """Replace only counters; retained generator and cache state stay intact."""
    owner = SearchAccounting(budget)
    generator = engine._generator
    while isinstance(generator, BudgetGenerator):
        generator = generator.generator
    factory = engine.generator_factory
    while isinstance(factory, BudgetFactory):
        factory = factory.inner_factory
    engine._generator = BudgetGenerator(generator, owner)
    engine.generator_factory = BudgetFactory(factory, owner)
    if engine.slow_controller is not None:
        slow_factory = engine.slow_controller.controller.generator_factory
        while isinstance(slow_factory, BudgetFactory):
            slow_factory = slow_factory.inner_factory
        engine.slow_controller.controller.generator_factory = BudgetFactory(slow_factory, owner)
    return owner


def observed_role(state, tray):
    bag = state.bags[tray.bag_id]
    return ("arrival_at_destination" if tray.node == bag.destination else
            "origin" if tray.node == bag.origin else "continuation")


def physical_prefix_signature(state, proposal):
    prefix = ExecutionValidator._safe_prefix(state, proposal)
    end = state.network.edges[prefix.legs[-1].edge_id].target if prefix.legs else state.trays[prefix.tray_id].node
    return digest({"tray_id": prefix.tray_id, "bag_id": prefix.bag_id,
        "legs": [asdict(leg) for leg in prefix.legs], "destination_node": end,
        "unload_complete": prefix.unload_complete, "usable_at": prefix.usable_at, "prefix_only": prefix.prefix_only})


def eligible_cell(row, used, *, bands=BANDS, max_samples=6):
    band = max((b for b in bands if b <= row["time"]), default=None)
    cell = (row["role"], band)
    return cell if (band is not None and not row["protected"] and row["role"] in ROLES
                    and cell not in used and len(used) < max_samples) else None


def collect_network_decisions(scene, *, spec=SPEC, budget=SearchBudget(),
                              bands=BANDS, max_samples=6):
    # Import lazily so pure tape and quota tests do not require the opt-in API.
    from .routing_cache_contract import enable_replay_cache, routing_cache_state
    base = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    enable_replay_cache(base)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    owner = bind_accounting(engine, budget)
    samples, opportunities, used = [], [], set()

    def record(current, tray, options):
        state, bag = current.state, current.state.bags[tray.bag_id]
        unique, keys, seen = [], [], set()
        for option in options:
            key = actual_action_key(state, option, route_mode=spec.route_mode)
            if key not in seen:
                unique.append(option)
                keys.append(key)
                seen.add(key)
        row = {"identity": f"{scene.name}:network_timed:d{len(opportunities)}:t{state.now}:{bag.bag_id}:{tray.node}",
            "time": state.now, "source_node": tray.node, "role": observed_role(state, tray),
            "protected": bag.protected, "bag_id": bag.bag_id, "tray_id": tray.tray_id,
            "candidate_count": len(unique), "raw_candidate_count": len(options),
            "selector_called": bool(options), "cursor": asdict(current._cursor),
            "sampled": False, "version": state.version,
            "next_slow_trigger_at": current.visible_decision_context().next_slow_trigger_at}
        cell = eligible_cell(row, used, bands=bands, max_samples=max_samples)
        if cell is not None:
            used.add(cell)
            row.update(sampled=True, band=cell[1])
            # The base checkpoint stores factory by reference: clone immediately
            # so later collection accounting cannot mutate a captured sample.
            checkpoint = current.checkpoint().clone()
            published = tuple(f for f in scene.forecasts if f.published_at <= state.now)
            evaluator = TimedAnalyticEvaluator(state.now + spec.planning_horizon, published)
            samples.append({**row, "checkpoint": checkpoint, "pool": tuple(unique),
                "checkpoint_sha256": checkpoint_fingerprint(checkpoint), "normal_keys": tuple(keys),
                "physical_prefix_signatures": tuple(physical_prefix_signature(state, p) for p in unique),
                "features": tuple(evaluator.features(state, p) for p in unique),
                "features_physical": tuple(physical_features(state, p, state.now + spec.planning_horizon,
                    published, route_mode=spec.route_mode) for p in unique),
                "routing_cache": routing_cache_state(current),
                "policy_sha": digest(base.control_contract["continuation"]["selector"]),
                "continuation_contract": deepcopy(current.control_contract)})
        opportunities.append(row)

    engine._decision_callback = record
    started, cpu = perf_counter(), process_time()
    failure, stop = None, None
    try:
        while engine.state.now < scene.horizon:
            owner.check()
            engine.advance(engine.state.now + 1)
        assert_invariants(engine.state)
    except SearchBudgetExceeded as exc:
        stop = str(exc)
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    result = None if failure else engine.result()
    return {"samples": samples, "opportunities": opportunities, "result": result,
        "metadata": {"scene": scene.name, "status": "execution_failure" if failure else "budget_exhausted" if stop else "reached_horizon",
            "stopped_at": engine.state.now, "horizon": scene.horizon, "budget_stop": stop,
            "failure": failure, "samples": len(samples), "attempts": len(opportunities),
            "selector_calls": sum(r["selector_called"] for r in opportunities),
            "roles": dict(Counter(r["role"] for r in opportunities)),
            "missing_role_band_cells": [{"role": role, "band": band} for role in ROLES for band in bands if (role, band) not in used],
            "search_calls": len(owner.rows), "search_work": owner.work, "searches": owner.rows,
            "wall_seconds": perf_counter() - started, "cpu_seconds": process_time() - cpu,
            "slow_trigger_times": list(engine.slow_controller.trigger_times) if engine.slow_controller else [],
            "slow_next_trigger_at": engine.slow_controller.next_trigger_at if engine.slow_controller else None}}


def validate_tape(tasks, state):
    """Reject invalid tasks, never repair OD, identity or permission fields."""
    seen, paths = set(), {}
    for bag in tasks:
        if not isinstance(bag.bag_id, str) or not bag.bag_id or bag.bag_id in seen:
            raise ValueError("task IDs must be distinct nonempty strings")
        seen.add(bag.bag_id)
        if (any(type(value) is not int for value in (bag.arrival, bag.deadline))
                or bag.arrival < 0 or bag.deadline < bag.arrival):
            raise ValueError("invalid integer task arrival/deadline")
        if type(bag.protected) is not bool or bag.origin not in state.network.nodes or bag.destination not in state.network.nodes:
            raise ValueError("invalid task node or protection field")
        if bag.origin not in paths:
            paths[bag.origin] = shortest_paths(state.network, bag.origin)[0]
        if bag.destination not in paths[bag.origin]:
            raise ValueError("task has no directed positive-capacity OD witness")


def network_futures(nominal, state, *, count, seed):
    """Offline stress: cancel 1/8, jitter -2/0/+2; preserve OD and time slack."""
    if type(count) is not int or count < 1:
        raise ValueError("future count must be positive integer")
    validate_tape(nominal, state)
    remaining = sorted((b for b in nominal if b.bag_id not in state.bags and b.arrival > state.now), key=lambda b: b.bag_id)
    rng, tapes = random.Random(seed), []
    for _ in range(count):
        tasks = []
        for bag in remaining:
            if rng.randrange(8) == 0:
                continue
            arrival = max(state.now + 1, bag.arrival + rng.choice((-2, 0, 2)))
            tasks.append(replace(bag, arrival=arrival, deadline=bag.deadline + arrival - bag.arrival))
        tapes.append(tuple(sorted(tasks, key=lambda b: (b.arrival, b.bag_id))))
    return tuple(tapes)


def branch_network_decision(checkpoint, candidate, future, *, horizon_ticks,
                            budget=SearchBudget(100, 100000, 60.)):
    """Exact pending intervention, unchanged continuation; fresh experiment cap."""
    from .routing_cache_contract import routing_cache_state
    if type(horizon_ticks) is not int or horizon_ticks < 1:
        raise ValueError("evaluation window must be a positive integer")
    if checkpoint.cursor.pending_options is None or candidate not in checkpoint.cursor.pending_options:
        raise ValueError("candidate must belong to this pending decision")
    validate_tape(future, checkpoint.state)
    if any(b.arrival <= checkpoint.state.now or b.bag_id in checkpoint.state.bags for b in future):
        raise ValueError("offline future can contain only unobserved later tasks")
    restored = checkpoint.clone()
    restored.base.pending_arrivals = defaultdict(list)
    for bag in future:
        restored.base.pending_arrivals[bag.arrival].append(bag)
    engine = CursorSimulation.from_checkpoint(restored)
    owner = bind_accounting(engine, budget)
    cache_before = routing_cache_state(engine)
    engine.choose_pending(candidate)
    started, cpu = perf_counter(), process_time()
    failure, stop = None, None
    try:
        end = checkpoint.state.now + horizon_ticks
        while engine.state.now < end:
            owner.check()
            engine.advance(engine.state.now + 1)
        assert_invariants(engine.state)
    except SearchBudgetExceeded as exc:
        stop = str(exc)
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    result = None if failure else engine.result()
    return {"status": "execution_failure" if failure else "budget_exhausted" if stop else "reached_horizon",
        "failure": failure, "budget_stop": stop, "stopped_at": engine.state.now,
        "result": result, "search_calls": len(owner.rows), "search_work": owner.work,
        "searches": owner.rows, "cache_before": cache_before, "cache_after": routing_cache_state(engine),
        "wall_seconds": perf_counter() - started, "cpu_seconds": process_time() - cpu}
