"""Offline whole-tape continuation from an actual saved routing cursor.

The offline task ledger controls evaluation only. The restored causal policy,
planning horizon, publications and owner permissions are never replaced.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, is_dataclass
import json
from time import perf_counter, process_time
import traceback

from .network_role_labels import SearchBudget, SearchBudgetExceeded, bind_accounting, validate_tape
from .role_coverage import CursorSimulation
from .routing_cache_contract import routing_cache_state
from .runtime import INFINITY, assert_invariants


def physical_result(value):
    """Exact saved result, excluding only measured policy wall-clock fields."""
    raw = asdict(value) if is_dataclass(value) else value
    raw = json.loads(json.dumps(raw))
    raw["policy_stats"] = {k: v for k, v in raw.get("policy_stats", {}).items()
                           if not k.endswith("_ms")}
    return raw


def compare_old_result(old, current):
    old, current = physical_result(old), physical_result(current)
    different = sorted(k for k in old.keys() | current.keys() if old.get(k) != current.get(k))
    return {"equal": not different, "different_fields": different,
            "excluded": "policy_stats keys ending in _ms only"}


def forecast_expiry(engine):
    """Time strictly beyond every original slow-controller publication TTL."""
    slow = engine.slow_controller
    if slow is None:
        return engine.state.now
    controller = slow.controller
    if not hasattr(controller, "max_forecast_age") or not hasattr(slow, "forecast_publications"):
        raise ValueError("quiescence requires the declared finite-TTL periodic controller")
    return max((f.published_at + controller.max_forecast_age + 1
                for f in slow.forecast_publications), default=engine.state.now)


def cycle_snapshot(state, pending_tasks, expected_ids, forecast_expired_at, *,
                   next_slow_trigger_at=None, protected_unadmitted_decisions=0):
    """Separate entire evaluation-ledger completion and residual obligations."""
    expected_ids = set(expected_ids)
    pending = sorted(b.bag_id for b in pending_tasks)
    missing = sorted(expected_ids - state.bags.keys())
    unfinished = sorted(expected_ids - state.completed.keys())
    task_complete = not missing and not unfinished and not pending
    stationary_occupancy, active_reservations = [], []
    for reservation in state.reservations:
        if reservation.end <= state.now:
            continue
        tray = state.trays.get(reservation.tray_id)
        is_stock = (tray is not None and tray.mode == "empty" and tray.bag_id is None
            and tray.available_at <= state.now and tray.tray_id not in state.plans
            and tray.tray_id not in state.empty_targets and tray.node is not None
            and reservation.resource == "node:" + tray.node
            and reservation.start <= state.now and reservation.end == INFINITY)
        (stationary_occupancy if is_stock else active_reservations).append(asdict(reservation))
    active_transit = [asdict(t) for t in state.old_in_transit if t.arrive > state.now]
    nonempty_trays = [t.tray_id for t in state.trays.values()
                      if t.mode != "empty" or t.bag_id is not None or t.available_at > state.now]
    transport = (task_complete and not state.plans and not state.empty_targets
                 and not active_reservations and not active_transit and not nonempty_trays)
    protected = {k for k in expected_ids if k in state.bags and state.bags[k].protected}
    return {"time": state.now, "expected_task_count": len(expected_ids),
        "unobserved_task_ids": missing, "uncompleted_task_ids": unfinished,
        "pending_arrival_ids": pending, "task_complete": task_complete,
        "transport_drained": transport, "forecast_expired": state.now >= forecast_expired_at,
        "forecast_expired_at": forecast_expired_at, "nonempty_tray_ids": nonempty_trays,
        "plan_tray_ids": sorted(state.plans), "empty_target_tray_ids": sorted(state.empty_targets),
        "active_reservation_count": len(active_reservations), "active_old_in_transit": active_transit,
        "stationary_occupancy_reservations": stationary_occupancy,
        "protected_observed": len(protected), "protected_completed": len(protected & state.completed.keys()),
        "protected_late": sum(state.completed.get(k, state.now) > state.bags[k].deadline for k in protected),
        "protected_unadmitted_decisions": protected_unadmitted_decisions,
        "next_slow_trigger_at": next_slow_trigger_at}


def cycle_state(engine, expected_ids, forecast_expired_at):
    return cycle_snapshot(engine.state, (b for tasks in engine._arrivals.values() for b in tasks),
        expected_ids, forecast_expired_at,
        next_slow_trigger_at=getattr(engine.slow_controller, "next_trigger_at", None),
        protected_unadmitted_decisions=engine.policy_stats.get("protected_unadmitted_decisions", 0))


def branch_full_cycle(checkpoint, candidate, future, *, old_result=None,
                      budget=SearchBudget(1000, 1000000, 180.), tail_cap=720):
    """Replay h80 exactly, then run every original task until certified drain.

    A finite tick/resource cutoff is censored, never an infeasibility result.
    Quiescence requires expired forecasts and a full actual slow-clock period
    with no task/transport obligation, including an actual slow trigger.
    """
    started, cpu = perf_counter(), process_time()
    if type(tail_cap) is not int or tail_cap < 1:
        raise ValueError("tail_cap must be a positive integer")
    if checkpoint.cursor.pending_options is None or candidate not in checkpoint.cursor.pending_options:
        raise ValueError("candidate must belong to this exact pending decision")
    validate_tape(future, checkpoint.state)
    if any(b.arrival <= checkpoint.state.now or b.bag_id in checkpoint.state.bags for b in future):
        raise ValueError("offline future contains observed or nonfuture tasks")
    restored = checkpoint.clone()
    restored.base.pending_arrivals = defaultdict(list)
    for bag in future:
        restored.base.pending_arrivals[bag.arrival].append(bag)
    engine = CursorSimulation.from_checkpoint(restored)
    owner = bind_accounting(engine, budget)
    cache_before = routing_cache_state(engine)
    expiry = forecast_expiry(engine)
    period = getattr(engine.slow_controller, "period", 1)
    expected = set(checkpoint.state.bags) | {b.bag_id for b in future}
    old_at = checkpoint.state.now + 80
    tape_end = max(old_at, max((b.arrival for b in future), default=checkpoint.state.now))
    cap_at = max(tape_end, expiry) + tail_cap
    fixed_times = sorted({old_at, tape_end, tape_end + 180, tape_end + 360, cap_at})
    engine.choose_pending(candidate)
    endpoints, milestones = {}, {}
    equal80 = None
    quiet_since = trigger_count = None
    status, failure, stop = "tick_cap_censored", None, None
    last_state = None
    try:
        while engine.state.now < cap_at:
            owner.check()
            engine.advance(engine.state.now + 1)
            last_state = cycle_state(engine, expected, expiry)
            now = engine.state.now
            if now in fixed_times:
                endpoints[str(now)] = {"result": asdict(engine.result()), "cycle": last_state}
            if now == old_at:
                equal80 = None if old_result is None else compare_old_result(old_result, engine.result())
                if equal80 is not None and not equal80["equal"]:
                    status = "old80_mismatch"
                    break
            for field in ("task_complete", "transport_drained"):
                if last_state[field] and field not in milestones:
                    milestones[field] = {"time": now, "result": asdict(engine.result()), "cycle": last_state}
            quiet = last_state["transport_drained"] and last_state["forecast_expired"]
            if not quiet:
                quiet_since = trigger_count = None
            elif quiet_since is None:
                quiet_since = now
                trigger_count = len(getattr(engine.slow_controller, "trigger_times", ()))
            elif (now - quiet_since >= period and now >= old_at
                  and (engine.slow_controller is None or
                       len(engine.slow_controller.trigger_times) > trigger_count)):
                status = "controller_quiescent"
                milestones["controller_quiescent"] = {"time": now, "quiet_since": quiet_since,
                    "actual_slow_triggers_since": len(getattr(engine.slow_controller, "trigger_times", ())) - trigger_count,
                    "cycle": last_state}
                break
        assert_invariants(engine.state)
    except SearchBudgetExceeded as exc:
        status, stop = "budget_censored", str(exc)
    except Exception as exc:
        status = "execution_failure"
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    result = engine.result() if failure is None else None
    return {"status": status, "failure": failure, "budget_stop": stop,
        "old80_comparison": equal80, "old80_at": old_at, "tape_end_at": tape_end,
        "fixed_endpoint_times": fixed_times, "cap_at": cap_at, "stopped_at": engine.state.now,
        "expected_task_ids": sorted(expected), "last_cycle_state": cycle_state(engine, expected, expiry),
        "milestones": milestones, "endpoints": endpoints, "result": result,
        "search_calls": len(owner.rows), "search_work": owner.work, "searches": owner.rows,
        "cache_before": cache_before, "cache_after": routing_cache_state(engine),
        "wall_seconds": perf_counter() - started, "cpu_seconds": process_time() - cpu}
