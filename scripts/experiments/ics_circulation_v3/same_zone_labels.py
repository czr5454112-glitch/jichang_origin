"""Exact same-zone continuation labels from real loaded routing cursors.

This module only observes and restores the frozen controller. Complete future
tasks are evaluation-engine input, never routing or prebalancing input.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from time import perf_counter, process_time
import traceback

from .network_full_cycle import compare_old_result, cycle_state, forecast_expiry
from .network_role_labels import (SearchBudget, SearchBudgetExceeded, bind_accounting,
                                  observed_role, physical_prefix_signature, validate_tape)
from .phase4_network_workloads import file_sha
from .role_coverage import CursorSimulation, checkpoint_fingerprint, digest
from .routing_cache_contract import CACHE_CONTRACT, ReplayRegionalFactory, routing_cache_state
from .run_network_opportunities import physical_projection
from .run_same_zone_supply import exact_json_value
from .runtime import actual_action_key, assert_invariants
from .same_zone_experiment import without_network
from .same_zone_supply import SameZoneSupplyPrebalancer


METHOD = "same_zone32plus32"
LABEL_BUDGET = SearchBudget(1000, 1000000, 180.)
COLLECTION_BUDGET = SearchBudget(3000, 3000000, 900.)
TAIL_CAP = 720


def qualified(value):
    return type(value).__module__ + "." + type(value).__qualname__


def unwrapped_factory(factory):
    seen = set()
    while not isinstance(factory, ReplayRegionalFactory):
        if id(factory) in seen or not hasattr(factory, "inner_factory"):
            raise ValueError("unrecognized continuation factory")
        seen.add(id(factory))
        factory = factory.inner_factory
    return {"class": qualified(factory), "parameters": asdict(factory)}


def active_continuation_binding(engine):
    """Bind actual method/configuration, not its inherited old builder label."""
    slow = engine.slow_controller
    inner = None if slow is None else slow.controller
    if type(inner) is not SameZoneSupplyPrebalancer:
        raise ValueError("checkpoint is not the exact same-zone continuation")
    source = Path(__file__).parent
    payload = {"schema": "ics_v3_same_zone_continuation_v1", "method": METHOD,
        "authority": "actual continuation overlay supersedes inherited supply-controller name",
        "base_construction_contract": deepcopy(engine.control_contract),
        "controller_class": qualified(inner),
        "controller_scalars": {k: v for k, v in vars(inner).items()
            if isinstance(v, (str, int, float, bool)) or v is None},
        "validator": {"class": qualified(inner.validator), "parameters": deepcopy(vars(inner.validator))},
        "engine_validator": {"class": qualified(engine._validator), "parameters": deepcopy(vars(engine._validator))},
        "generator_factory": unwrapped_factory(engine.generator_factory),
        "slow_generator_factory": unwrapped_factory(inner.generator_factory),
        "fast_generator_config": routing_cache_state(engine)["fast_generator_config"],
        "routing_cache_contract": CACHE_CONTRACT,
        "selector_class": qualified(engine.route_selector),
        "inner_selector_class": qualified(engine.route_selector.selector),
        "selector_spec": asdict(engine.route_selector.selector.spec),
        "forecast_publications": [asdict(f) for f in slow.forecast_publications],
        "routing_forecast_publications": [asdict(f) for f in engine.route_selector.selector.forecast_publications],
        "slow_period": slow.period,
        "engine_settings": {name: getattr(engine, name) for name in
            ("route_mode", "coordination_order", "candidate_count", "search_horizon", "reactive_empty_dispatch")},
        "source_sha256": {name: file_sha(source / name) for name in
            ("same_zone_supply.py", "same_zone_experiment.py", "prebalance.py", "phase4_control.py",
             "routing_cache_contract.py", "role_coverage.py", "runtime.py")},
        "future_access": "engine only; original publication gate on both controllers",
        "centralized_authority": "unchanged full W3 Snapshot and ExecutionValidator permissions"}
    payload["sha256"] = digest(payload)
    return payload


def pending_future(engine):
    return tuple(sorted((b for bags in engine._arrivals.values() for b in bags),
                        key=lambda b: (b.arrival, b.bag_id)))


def checkpoint_metadata(checkpoint):
    """Full per-instance binding; all timing internals remain in fingerprint."""
    engine = CursorSimulation.from_checkpoint(checkpoint)
    if checkpoint.cursor.pending_options is None:
        raise ValueError("metadata requires an actual loaded generation cursor")
    pool = checkpoint.cursor.pending_options
    future = pending_future(engine)
    validate_tape(future, engine.state)
    generator = engine._generator
    while not hasattr(generator, "owner") and hasattr(generator, "generator"):
        generator = generator.generator
    search_prefix = len(generator.owner.rows) if hasattr(generator, "owner") else 0
    return {"schema": "ics_v3_same_zone_checkpoint_v1",
        "checkpoint_fingerprint": checkpoint_fingerprint(checkpoint),
        "state_sha256": digest(asdict(engine.state)), "cursor": asdict(engine._cursor),
        "phase": checkpoint.phase, "next_slow_trigger_at": engine.slow_controller.next_trigger_at,
        "search_prefix_count": search_prefix,
        "selector_prefix_count": len(engine.route_selector.history),
        "trace_prefix_count": len(engine._trace),
        "routing_cache": routing_cache_state(engine),
        "candidates": [asdict(p) for p in pool],
        "candidate_keys": [actual_action_key(engine.state, p, route_mode=engine.route_mode) for p in pool],
        "physical_prefix_signatures": [physical_prefix_signature(engine.state, p) for p in pool],
        "future_sha256": digest([asdict(b) for b in future]),
        "future_task_ids": [b.bag_id for b in future],
        "active_continuation": active_continuation_binding(engine),
        "published_slow_forecasts": [asdict(f) for f in engine.slow_controller.controller.forecasts]}


def validate_checkpoint_binding(checkpoint, metadata):
    """Reject altered cursor/cache/controller/pool/tape before any simulation."""
    actual = checkpoint_metadata(checkpoint)
    checks = {key: exact_json_value(value, metadata.get(key)) for key, value in actual.items()}
    if not all(checks.values()):
        raise ValueError("same-zone checkpoint binding failed: " + str([k for k, ok in checks.items() if not ok]))
    return checks


def restore_matching_continuation(payload, metadata):
    checkpoint = payload["checkpoint"]
    validate_checkpoint_binding(checkpoint, metadata)
    if not exact_json_value([asdict(p) for p in payload["pool"]], metadata["candidates"]):
        raise ValueError("payload pool differs from exact cursor pool")
    if digest([asdict(b) for b in payload["future"]]) != metadata["future_sha256"]:
        raise ValueError("payload future differs from exact pending tape")
    engine = CursorSimulation.from_checkpoint(checkpoint)
    if not exact_json_value([asdict(b) for b in pending_future(engine)], [asdict(b) for b in payload["future"]]):
        raise ValueError("pending arrivals differ from evaluation ledger")
    return engine


def opportunity_row(engine, tray, options, sequence):
    state, bag = engine.state, engine.state.bags[tray.bag_id]
    return {"sequence": sequence, "time": state.now, "version": state.version,
        "node": tray.node, "bag_id": bag.bag_id, "tray_id": tray.tray_id,
        "protected": bag.protected, "candidate_count": len(options),
        "candidate_keys": [actual_action_key(state, p, route_mode=engine.route_mode) for p in options],
        "candidates": [asdict(p) for p in options], "cursor": asdict(engine._cursor),
        "next_slow_trigger_at": engine.slow_controller.next_trigger_at,
        "visible_state": without_network(state)}


def run_cycle(engine, expected_bags, *, minimum_observation_at, forced_index=None,
              budget=LABEL_BUDGET, tail_cap=TAIL_CAP, capture=None, owner=None,
              retain_physical_ticks=False):
    """Light observation of unchanged physics, causal policy and certified drain.

    ``capture`` runs out of band at actual loaded attempts; it is never stored
    in a checkpoint. No controller wrapper retains a back-reference to engine.
    """
    started, cpu = perf_counter(), process_time()
    if minimum_observation_at < engine.state.now or type(tail_cap) is not int or tail_cap < 1:
        raise ValueError("invalid fixed endpoint or tail cap")
    initial_state, initial_cursor = asdict(engine.state), asdict(engine._cursor)
    cache_before = routing_cache_state(engine)
    owner = bind_accounting(engine, budget) if owner is None else owner
    expiry, period = forecast_expiry(engine), engine.slow_controller.period
    last_arrival = max((b.arrival for b in pending_future(engine)), default=engine.state.now)
    cap_at = max(minimum_observation_at, last_arrival, expiry) + tail_cap
    selector_prefix, slow_prefix, trace_prefix = (len(engine.route_selector.history),
        len(engine.slow_controller.history), len(engine._trace))
    opportunities, physical_ticks = [], []

    def record(current, tray, options):
        row = opportunity_row(current, tray, options, len(opportunities))
        opportunities.append(row)
        if capture is not None:
            try:
                capture(current, tray, options, row, owner)
            except Exception as error:
                row["capture_failure"] = {"type": type(error).__name__, "message": str(error)}
                raise

    engine._decision_callback = record
    status, failure, stop, endpoint, forced = "tick_cap_censored", None, None, None, None
    milestones, quiet_since, trigger_count = {}, None, None
    try:
        if forced_index is not None:
            pool = engine._cursor.pending_options
            if type(forced_index) is not int or pool is None or not 0 <= forced_index < len(pool):
                raise ValueError("forced index must belong to saved original pool")
            chosen = pool[forced_index]
            forced = {"candidate_index": forced_index, "candidate": asdict(chosen),
                "actual_action_key": actual_action_key(engine.state, chosen, route_mode=engine.route_mode),
                "selector_accounting": "replaces exactly one current selector call/history entry"}
            engine.choose_pending(chosen)
        while engine.state.now < cap_at:
            owner.check()
            engine.advance(engine.state.now + 1)
            now = engine.state.now
            cycle = cycle_state(engine, expected_bags, expiry)
            projection = physical_projection(engine.state)
            physical_ticks.append(projection)
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
    engine._decision_callback = None
    ledger = [{**asdict(b), "observed": key in engine.state.bags,
        "load_time": engine.state.load_times.get(key), "completed_at": engine.state.completed.get(key)}
        for key, b in sorted(expected_bags.items())]
    return {"status": status, "failure": failure, "budget_stop": stop, "budget": asdict(budget),
        "initial_state": initial_state, "initial_cursor": initial_cursor, "forced_intervention": forced,
        "minimum_observation_at": minimum_observation_at, "original_endpoint": endpoint,
        "last_arrival_at": last_arrival, "forecast_expired_at": expiry, "cap_at": cap_at,
        "stopped_at": engine.state.now, "milestones": milestones,
        "expected_task_ids": sorted(expected_bags), "evaluation_ledger": ledger,
        "last_cycle_state": cycle_state(engine, expected_bags, expiry),
        "result": None if failure else asdict(engine.result()),
        "opportunities": opportunities, "selector_history_suffix": engine.route_selector.history[selector_prefix:],
        "slow_history_suffix": engine.slow_controller.history[slow_prefix:],
        "actual_slow_trigger_times": engine.slow_controller.trigger_times,
        "physical_tick_trace": physical_ticks if retain_physical_ticks else
            [{"time": row["time"], "physical_sha256": digest(row)} for row in physical_ticks],
        "physical_tick_representation": "full" if retain_physical_ticks else "sha256",
        "event_trace_suffix": engine._trace[trace_prefix:],
        "searches": owner.rows, "search_calls": len(owner.rows), "search_work": owner.work,
        "cache_before": cache_before, "cache_after": routing_cache_state(engine),
        "cpu_seconds": process_time() - cpu, "wall_seconds": perf_counter() - started}


def run_label_branch(payload, metadata, *, forced_index=None, minimum_observation_at=None,
                     budget=LABEL_BUDGET, tail_cap=TAIL_CAP):
    engine = restore_matching_continuation(payload, metadata)
    bags = {**engine.state.bags, **{b.bag_id: b for b in payload["future"]}}
    minimum = engine.state.now + 80 if minimum_observation_at is None else minimum_observation_at
    outcome = run_cycle(engine, bags, minimum_observation_at=minimum, forced_index=forced_index,
                        budget=budget, tail_cap=tail_cap)
    outcome["active_continuation"] = metadata["active_continuation"]
    outcome["checkpoint_binding_checks"] = validate_checkpoint_binding(payload["checkpoint"], metadata)
    return outcome


def compare_collection(reference, actual):
    """Every physical result/search/opportunity at the original common endpoint."""
    fields = ("opportunities", "searches", "cache_before", "cache_after", "stopped_at",
              "physical_tick_trace", "event_trace_suffix", "selector_history_suffix", "actual_slow_trigger_times")
    return {"result": compare_old_result(reference["result"], actual["result"]),
            **{key: exact_json_value(reference[key], actual[key]) for key in fields}}


def comparison_passes(comparison):
    return all(value.get("equal", False) if isinstance(value, dict) else value for value in comparison.values())


def compare_normal_resume(reference, actual, metadata):
    """Strict normal-policy continuation at the common absolute collection end."""
    now = actual["initial_state"]["now"]
    prefix = metadata["search_prefix_count"]
    selected_prefix = metadata["selector_prefix_count"]
    ticks = [{"time": row["time"], "physical_sha256": digest(row)}
             for row in reference["physical_tick_trace"] if row["time"] > now]
    return {"result": compare_old_result(reference["result"], actual["result"]),
        "searches": exact_json_value(reference["searches"][prefix:], actual["searches"]),
        "cache_after": exact_json_value(reference["cache_after"], actual["cache_after"]),
        "stopped_at": reference["stopped_at"] == actual["stopped_at"],
        "physical_tick_trace": exact_json_value(ticks, actual["physical_tick_trace"]),
        "selector_history_suffix": exact_json_value(reference["selector_history_suffix"][selected_prefix:], actual["selector_history_suffix"]),
        # result() appends a detached terminal tick preview; it is not an
        # execution event and is never stored in the checkpoint's trace.
        "event_trace_suffix": exact_json_value(reference["result"]["trace"][metadata["trace_prefix_count"]:-1], actual["event_trace_suffix"]),
        "actual_slow_trigger_times": exact_json_value(reference["actual_slow_trigger_times"], actual["actual_slow_trigger_times"])}
